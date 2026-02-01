# K1 Intelligence Kernel - All Flows

> **Status**: Skeleton - Flow names only
> **Source**: `k1_diagram.mmd` (1101 lines)
> **Last Updated**: 2026-01-31

---

## 1. CORE CONVERSATION FLOWS

### 1.1 Main Conversation Loop

#### F01: User Input to ACKING Flow

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                         F01: USER INPUT TO ACKING                           │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│   ┌──────────┐    k1.concierge.user_input    ┌──────────────────────────┐  │
│   │LISTENING │ ─────────────────────────────▶│        ACKING            │  │
│   │          │                               │  Intent Classification   │  │
│   │ Waiting  │                               │  Gap Detection           │  │
│   │ for User │                               │  Fast Validation         │  │
│   └──────────┘                               │  (UltraBERT 22ms)        │  │
│        ▲                                     └──────────────────────────┘  │
│        │                                              │                    │
│        │ user.ack                                     │                    │
│        │ (turn complete)                              ▼                    │
│   ┌──────────┐                               ┌──────────────────────────┐  │
│   │DELIVERING│ ◀─────────────────────────────│      DISPATCHING         │  │
│   │          │      (after execution)        │  Route based on tier:    │  │
│   │ Final    │                               │  LOW → Fabric            │  │
│   │ Results  │                               │  MED/HIGH → Orchestrator │  │
│   └──────────┘                               └──────────────────────────┘  │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

#### F02: Uncertainty Check & Clarification Flow

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                    F02: UNCERTAINTY CHECK & CLARIFICATION                   │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│   ┌──────────────────────────────────────────────────────────────────────┐  │
│   │                           ACKING                                     │  │
│   │  ┌─────────────────┐                                                 │  │
│   │  │UNCERTAINTY      │                                                 │  │
│   │  │ESTIMATOR        │─────────────────┐                               │  │
│   │  │                 │                 │ uncertainty score             │  │
│   │  │(UltraBERT conf) │                 ▼                               │  │
│   │  └─────────────────┘         ┌───────────────┐                       │  │
│   │                              │  uncertainty  │                       │  │
│   │                              │   ≥ 0.2 ?     │                       │  │
│   │                              └───────┬───────┘                       │  │
│   │                         YES          │          NO                   │  │
│   │                    ┌─────────────────┼─────────────────┐             │  │
│   │                    ▼                                   ▼             │  │
│   │           ┌─────────────────┐               ┌─────────────────┐      │  │
│   │           │   CLARIFYING    │               │  DISPATCHING    │      │  │
│   │           │                 │               │                 │      │  │
│   │           │ Progressive     │               │ Ready to        │      │  │
│   │           │ Disclosure      │               │ Execute         │      │  │
│   │           │ (1-2 Questions) │               │                 │      │  │
│   │           └────────┬────────┘               └─────────────────┘      │  │
│   │                    │                                                 │  │
│   │                    │ user_response                                   │  │
│   │                    └──────────────────▶ ACKING (re-evaluate)         │  │
│   └──────────────────────────────────────────────────────────────────────┘  │
│                                                                             │
│   Clarification Generation:                                                 │
│   ENTROPY_MIN_QUESTION_PLANNER ──▶ CLARIFYING ──▶ MODEL_GATEWAY            │
│                                         │                                   │
│                                         ▼                                   │
│                               PENDING_CLARIFICATIONS                        │
│                               (SessionState update)                         │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

#### F03: Interrupt Handling Flow

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                        F03: INTERRUPT HANDLING FLOW                         │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│   User changes topic mid-conversation or sub-agent needs clarification      │
│                                                                             │
│   ┌──────────┐   k1.concierge.user_input    ┌───────────────────────────┐  │
│   │LISTENING │ ────────(interrupt)─────────▶│   INTERRUPT_HANDLING      │  │
│   └──────────┘                              │                           │  │
│                                             │   User Changes Topic      │  │
│                                             │   Graceful State Save     │  │
│                                             └─────────────┬─────────────┘  │
│                                                           │                │
│                                        user.intent.override                │
│                                                           │                │
│                                                           ▼                │
│                                             ┌───────────────────────────┐  │
│                                             │         ACKING            │  │
│                                             │   Re-classify new intent  │  │
│                                             └───────────────────────────┘  │
│                                                                             │
│   Sub-Agent Clarification Interrupt (Single Writer Pattern):                │
│   ┌───────────────────────────────────────────────────────────────────────┐ │
│   │ L4_SUBAGENTS ──▶ DELTA_BUS ──▶ AGGREGATION_WINDOW ──▶ CONCIERGE_FSM  │ │
│   │                                                            │          │ │
│   │                                               write pending│          │ │
│   │                                                            ▼          │ │
│   │ CLARIFYING ◀── INTERRUPT_HANDLING ◀── PENDING_CLARIFICATIONS         │ │
│   └───────────────────────────────────────────────────────────────────────┘ │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

### 1.2 Complexity-Tier Dispatch Flows

#### F04: LOW Tier Fast Path Flow

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                    F04: LOW TIER FAST PATH (Tool First)                     │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│   Example: "Remind me at 5pm" → Tool (~500ms) → LLM Response                │
│                                                                             │
│   ┌─────────────────────────────────────────────────────────────────────┐   │
│   │                    COMPLEXITY_CLASSIFIER                            │   │
│   │                           │                                         │   │
│   │      LOW: single intent + single domain                             │   │
│   │                           │                                         │   │
│   │                           ▼                                         │   │
│   │   ┌───────────┐   route to tool   ┌───────────────┐                 │   │
│   │   │ TIER_LOW  │ ────────────────▶ │ DISPATCHING   │                 │   │
│   │   │           │    execution      │               │                 │   │
│   │   │ ~500 tok  │                   │ Route: LOW →  │                 │   │
│   │   └───────────┘                   │ Fabric        │                 │   │
│   │                                   └───────┬───────┘                 │   │
│   │                                           │                         │   │
│   │                            simple task (LOW)                        │   │
│   │                                           │                         │   │
│   │                                           ▼                         │   │
│   │                               ┌───────────────────┐                 │   │
│   │                               │ CAPABILITY_FABRIC │                 │   │
│   │                               │                   │                 │   │
│   │                               │ Tool First        │                 │   │
│   │                               │ No Preliminary Ack│                 │   │
│   │                               └───────────────────┘                 │   │
│   └─────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
│   Key: NO preliminary ack - tool executes first, then LLM response          │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

#### F05: MEDIUM Tier Reasoning Flow

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                    F05: MEDIUM TIER REASONING FLOW                          │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│   Example: Multi-intent OR multi-domain request                             │
│                                                                             │
│   ┌───────────────────────────────────────────────────────────────────────┐ │
│   │                    COMPLEXITY_CLASSIFIER                              │ │
│   │                           │                                           │ │
│   │      MEDIUM: multi-intent OR multi-domain                             │ │
│   │                           │                                           │ │
│   │                           ▼                                           │ │
│   │   ┌─────────────┐   llm.reasoning   ┌───────────────────────┐         │ │
│   │   │ TIER_MEDIUM │ ────────────────▶ │    MODEL_GATEWAY      │         │ │
│   │   │             │    (2K tokens)    │                       │         │ │
│   │   │ 2K tokens   │                   │ LLM reasons about     │         │ │
│   │   └─────────────┘                   │ multi-intent request  │         │ │
│   │                                     └───────────┬───────────┘         │ │
│   │                                                 │                     │ │
│   │                              reasoning/plan complete                  │ │
│   │                                                 │                     │ │
│   │                                                 ▼                     │ │
│   │                                     ┌───────────────────────┐         │ │
│   │                                     │     DISPATCHING       │         │ │
│   │                                     │                       │         │ │
│   │                                     │ Route: MED/HIGH →     │         │ │
│   │                                     │ ORCHESTRATOR_ACTOR    │         │ │
│   │                                     └───────────────────────┘         │ │
│   └───────────────────────────────────────────────────────────────────────┘ │
│                                                                             │
│   Key: LLM reasoning FIRST, then execution via Orchestrator                 │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

#### F06: HIGH Tier Planning Flow

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                      F06: HIGH TIER PLANNING FLOW                           │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│   Example: Complex + emotional request requiring full planning              │
│                                                                             │
│   ┌───────────────────────────────────────────────────────────────────────┐ │
│   │                    COMPLEXITY_CLASSIFIER                              │ │
│   │                           │                                           │ │
│   │      HIGH: complex + emotional                                        │ │
│   │                           │                                           │ │
│   │                           ▼                                           │ │
│   │   ┌────────────┐    llm.planning    ┌───────────────────────┐         │ │
│   │   │ TIER_HIGH  │ ─────────────────▶ │    MODEL_GATEWAY      │         │ │
│   │   │            │    (8K tokens)     │                       │         │ │
│   │   │ 8K tokens  │                    │ LLM creates full plan │         │ │
│   │   └────────────┘                    └───────────┬───────────┘         │ │
│   │                                                 │                     │ │
│   │                              reasoning/plan complete                  │ │
│   │                                                 │                     │ │
│   │                                                 ▼                     │ │
│   │                                     ┌───────────────────────┐         │ │
│   │                                     │     DISPATCHING       │         │ │
│   │                                     └───────────┬───────────┘         │ │
│   │                                                 │                     │ │
│   │                                  complex task (MEDIUM/HIGH)           │ │
│   │                                                 │                     │ │
│   │                                                 ▼                     │ │
│   │                                     ┌───────────────────────┐         │ │
│   │                                     │  ORCHESTRATOR_ACTOR   │         │ │
│   │                                     │                       │         │ │
│   │                                     │  → PLANNER_AGENT      │         │ │
│   │                                     │  → 4-Stage Pipeline   │         │ │
│   │                                     └───────────────────────┘         │ │
│   └───────────────────────────────────────────────────────────────────────┘ │
│                                                                             │
│   Key: Full LLM planning (8K tokens), then 4-Stage Planner Pipeline         │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

#### F07: CRISIS Tier Safety Protocol Flow

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                    F07: CRISIS TIER SAFETY PROTOCOL                         │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│   CRISIS detection happens FIRST - before any complexity routing            │
│                                                                             │
│   ┌───────────────────────────────────────────────────────────────────────┐ │
│   │                      ULTRABERT_SAFETY                                 │ │
│   │                           │                                           │ │
│   │                     safety_band = CRISIS                              │ │
│   │                           │                                           │ │
│   │                           ▼                                           │ │
│   │                  ┌─────────────────┐                                  │ │
│   │                  │ CRISIS_DETECTOR │                                  │ │
│   │                  │                 │                                  │ │
│   │                  │ CRISIS band =   │                                  │ │
│   │                  │ immediate       │                                  │ │
│   │                  │ protocol        │                                  │ │
│   │                  └────────┬────────┘                                  │ │
│   │                           │                                           │ │
│   │                   CRISIS detected                                     │ │
│   │                           │                                           │ │
│   │                           ▼                                           │ │
│   │                  ┌─────────────────┐                                  │ │
│   │                  │ SAFETY_OVERRIDE │                                  │ │
│   │                  │                 │                                  │ │
│   │                  │ Bypasses ALL    │                                  │ │
│   │                  │ routing         │                                  │ │
│   │                  └────────┬────────┘                                  │ │
│   │                           │ immediate                                 │ │
│   │                           ▼                                           │ │
│   │                  ┌─────────────────┐  safety.crisis   ┌────────────┐  │ │
│   │                  │   TIER_CRISIS   │ ────────────────▶│SAFETY_     │  │ │
│   │                  │                 │    .protocol     │MAILBOX     │  │ │
│   │                  │ Safety Protocol │                  │            │  │ │
│   │                  └─────────────────┘                  │WFQ: URGENT │  │ │
│   │                                                       └────────────┘  │ │
│   └───────────────────────────────────────────────────────────────────────┘ │
│                                                                             │
│   Key: Bypasses ALL other routing - immediate safety response               │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

### 1.3 Response Delivery Flows

#### F08: LOW Tier Response Delivery Flow

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                    F08: LOW TIER RESPONSE DELIVERY                          │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│   Fast path: Tool result → LLM response with result (~500 tokens)           │
│                                                                             │
│   ┌───────────────────────────────────────────────────────────────────────┐ │
│   │  (After tool execution completes)                                     │ │
│   │                                                                       │ │
│   │   ┌─────────────────┐    LOW: tool done    ┌────────────────────┐     │ │
│   │   │   COMPANIONING  │ ───────────────────▶ │    DELIVERING      │     │ │
│   │   │                 │                      │                    │     │ │
│   │   │ Tool result     │                      │ Final Results      │     │ │
│   │   │ staged          │                      │ + Next Steps       │     │ │
│   │   └─────────────────┘                      └─────────┬──────────┘     │ │
│   │                                                      │                │ │
│   │                                        fetch tool_results             │ │
│   │                                                      │                │ │
│   │                                                      ▼                │ │
│   │                                        ┌────────────────────────┐     │ │
│   │                                        │  TOOL_RESULT_BUFFER    │     │ │
│   │                                        │                        │     │ │
│   │                                        │  LOW: tool_result[]    │     │ │
│   │                                        └───────────┬────────────┘     │ │
│   │                                                    │                  │ │
│   │            ┌───────────────────────────────────────┘                  │ │
│   │            │                                                          │ │
│   │            ▼                                                          │ │
│   │   ┌────────────────────┐  LOW: tool_result +   ┌──────────────────┐   │ │
│   │   │    DELIVERING      │  context (~500 tok)   │  MODEL_GATEWAY   │   │ │
│   │   │                    │ ─────────────────────▶│                  │   │ │
│   │   └────────────────────┘                       │  Generate        │   │ │
│   │            ▲                                   │  response with   │   │ │
│   │            │     LOW: response with result     │  tool result     │   │ │
│   │            └───────────────────────────────────┤                  │   │ │
│   │                                                └──────────────────┘   │ │
│   └───────────────────────────────────────────────────────────────────────┘ │
│                                                                             │
│   Then: DELIVERING ──▶ clear buffer ──▶ user.ack ──▶ LISTENING              │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

#### F09: MEDIUM/HIGH Tier Response Delivery Flow

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                F09: MEDIUM/HIGH TIER RESPONSE DELIVERY                      │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│   Complex path: Progress updates → All tool results → Final response        │
│                                                                             │
│   ┌───────────────────────────────────────────────────────────────────────┐ │
│   │  (During orchestrator execution)                                      │ │
│   │                                                                       │ │
│   │  ┌──────────────────┐   execution deltas   ┌─────────────────────┐    │ │
│   │  │ORCHESTRATOR_ACTOR│ ───────────────────▶ │   COMPANIONING      │    │ │
│   │  │                  │                      │                     │    │ │
│   │  │  Multi-step      │                      │ Keep conversation   │    │ │
│   │  │  execution       │                      │ moving              │    │ │
│   │  └──────────────────┘                      └──────────┬──────────┘    │ │
│   │                                                       │               │ │
│   │                                        k1.agent.*.delta.v1            │ │
│   │                                                       │               │ │
│   │                                                       ▼               │ │
│   │                                            ┌─────────────────────┐    │ │
│   │                                            │    PROGRESSING      │    │ │
│   │                                            │                     │    │ │
│   │                                            │ Stream Deltas as    │    │ │
│   │                                            │ Updates to user     │    │ │
│   │                                            └──────────┬──────────┘    │ │
│   │                                                       │               │ │
│   │                            k1.orchestration.execution.completed       │ │
│   │                                                       │               │ │
│   │                                                       ▼               │ │
│   │                                            ┌─────────────────────┐    │ │
│   │                                            │    DELIVERING       │    │ │
│   │                                            └──────────┬──────────┘    │ │
│   │                                                       │               │ │
│   │                                         fetch all tool_results        │ │
│   │                                                       ▼               │ │
│   │   ┌────────────────────────┐     MEDIUM/HIGH: all tool_results[]      │ │
│   │   │   TOOL_RESULT_BUFFER   │ ────────────────────────────────────┐    │ │
│   │   └────────────────────────┘                                     │    │ │
│   │                                                                  │    │ │
│   │   ┌────────────────────────┐  tool_results + context  ┌──────────▼──┐ │ │
│   │   │      DELIVERING        │  (2-8K tokens)           │MODEL_GATEWAY│ │ │
│   │   │                        │ ────────────────────────▶│             │ │ │
│   │   │                        │◀─────────────────────────│final resp   │ │ │
│   │   └────────────────────────┘      final response      └─────────────┘ │ │
│   └───────────────────────────────────────────────────────────────────────┘ │
│                                                                             │
│   Then: DELIVERING ──▶ clear buffer ──▶ user.ack ──▶ LISTENING              │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

#### F10: Preliminary Ack Generation Flow (Conversational Continuity)

```
┌─────────────────────────────────────────────────────────────────────────────┐
│              F10: PRELIMINARY ACK GENERATION (MED/HIGH only)                │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│   "Let me work on that..." - keeps conversation flowing for long tasks      │
│                                                                             │
│   ┌───────────────────────────────────────────────────────────────────────┐ │
│   │                       DISPATCHING                                     │ │
│   │                           │                                           │ │
│   │         ┌─────────────────┴─────────────────┐                         │ │
│   │         │                                   │                         │ │
│   │         ▼                                   ▼                         │ │
│   │  ┌──────────────────┐            ┌──────────────────────────────┐     │ │
│   │  │ complex task     │            │ MEDIUM/HIGH: generate        │     │ │
│   │  │ (MEDIUM/HIGH)    │            │ preliminary ack              │     │ │
│   │  │      │           │            │              │                │     │ │
│   │  │      ▼           │            │              ▼                │     │ │
│   │  │ ORCHESTRATOR_    │            │       MODEL_GATEWAY          │     │ │
│   │  │ ACTOR            │            │              │                │     │ │
│   │  │                  │            │    preliminary ack sent       │     │ │
│   │  │ (background      │            │              │                │     │ │
│   │  │  execution       │            │              ▼                │     │ │
│   │  │  10-30s)         │            │       COMPANIONING           │     │ │
│   │  └──────────────────┘            │              │                │     │ │
│   │                                  │    (user sees "Working...")   │     │ │
│   │                                  └──────────────────────────────┘     │ │
│   │                                                                       │ │
│   │  PARALLEL EXECUTION:                                                  │ │
│   │  - User receives preliminary ack immediately                          │ │
│   │  - Orchestrator works in background                                   │ │
│   │  - Progress updates stream to user via PROGRESSING                    │ │
│   │                                                                       │ │
│   └───────────────────────────────────────────────────────────────────────┘ │
│                                                                             │
│   Key: Conversational continuity - user never waits in silence             │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## 2. ULTRABERT CLASSIFICATION FLOWS

### 2.1 UltraBERT 12-Head Parallel Flow

#### F11: UltraBERT Core Forward Pass Flow (22ms)

```
┌─────────────────────────────────────────────────────────────────────────────┐
│              F11: ULTRABERT CORE FORWARD PASS (22ms Total)                  │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│   Single forward pass through ModernBERT-base (149M params)                 │
│   ALL heads execute in parallel - no sequential dependency                  │
│                                                                             │
│   ┌───────────────────────────────────────────────────────────────────────┐ │
│   │                       ACKING (FSM State)                              │ │
│   │                            │                                          │ │
│   │                       user_input                                      │ │
│   │                            │                                          │ │
│   │                            ▼                                          │ │
│   │              ┌──────────────────────────┐                             │ │
│   │              │     ULTRABERT_CORE       │                             │ │
│   │              │                          │                             │ │
│   │              │  ModernBERT-base 149M    │                             │ │
│   │              │  Single Forward Pass     │                             │ │
│   │              │  22ms latency            │                             │ │
│   │              └────────────┬─────────────┘                             │ │
│   │                           │                                           │ │
│   │           ┌───────────────┼───────────────┐                           │ │
│   │           │  12 heads parallel            │                           │ │
│   │           ▼               ▼               ▼                           │ │
│   │   ┌─────────────┐ ┌─────────────┐ ┌─────────────┐                     │ │
│   │   │INTENT HEAD  │ │INGRESS HEAD │ │SAFETY HEAD  │                     │ │
│   │   │Multi-Label  │ │Multi-Label  │ │4 bands      │                     │ │
│   │   │8 classes    │ │12 domains   │ │GREEN→CRISIS │                     │ │
│   │   └─────────────┘ └─────────────┘ └─────────────┘                     │ │
│   │                                                                       │ │
│   │   ┌─────────────┐ ┌─────────────┐ ┌─────────────┐                     │ │
│   │   │EMOTIONS     │ │SENTIMENT    │ │NER HEAD     │                     │ │
│   │   │44 classes   │ │5 levels     │ │GlobalPointer│                     │ │
│   │   │joy,sadness..│ │neg→positive │ │PER,ORG,LOC..│                     │ │
│   │   └─────────────┘ └─────────────┘ └─────────────┘                     │ │
│   │                                                                       │ │
│   │   ┌─────────────┐                                                     │ │
│   │   │RELATIONS    │  (+ 5 more specialized heads)                       │ │
│   │   │spouse_of... │                                                     │ │
│   │   └─────────────┘                                                     │ │
│   └───────────────────────────────────────────────────────────────────────┘ │
│                                                                             │
│   Performance: 22ms total regardless of head count (parallel execution)     │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

#### F12: Intent Classification Flow (Multi-Label)

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                F12: INTENT CLASSIFICATION (MULTI-LABEL)                     │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│   Returns: primary intent + all[] intents + scores{} for each              │
│   Example: "Remind me about my doctor appt and log how I'm feeling"        │
│   → primary: set_reminder, all: [set_reminder, log_memory], scores: {...}  │
│                                                                             │
│   ┌───────────────────────────────────────────────────────────────────────┐ │
│   │                     ULTRABERT_INTENT HEAD                             │ │
│   │                                                                       │ │
│   │   Input: User utterance                                               │ │
│   │          │                                                            │ │
│   │          ▼                                                            │ │
│   │   ┌─────────────────────────────────────────────────────────────┐     │ │
│   │   │ 8 Intent Classes (Multi-Label Output)                       │     │ │
│   │   ├─────────────────────────────────────────────────────────────┤     │ │
│   │   │ □ log_memory     □ set_reminder    □ query_knowledge       │     │ │
│   │   │ □ schedule       □ emotional_support □ task_management     │     │ │
│   │   │ □ information    □ conversation                            │     │ │
│   │   └─────────────────────────────────────────────────────────────┘     │ │
│   │          │                                                            │ │
│   │          ▼                                                            │ │
│   │   ┌─────────────────────────────────────────────────────────────┐     │ │
│   │   │ Output Structure:                                           │     │ │
│   │   │   {                                                         │     │ │
│   │   │     "primary": "set_reminder",                              │     │ │
│   │   │     "all": ["set_reminder", "log_memory"],                  │     │ │
│   │   │     "scores": {                                             │     │ │
│   │   │       "set_reminder": 0.92,                                 │     │ │
│   │   │       "log_memory": 0.78,                                   │     │ │
│   │   │       "query_knowledge": 0.12,                              │     │ │
│   │   │       ...                                                   │     │ │
│   │   │     }                                                       │     │ │
│   │   │   }                                                         │     │ │
│   │   └─────────────────────────────────────────────────────────────┘     │ │
│   └───────────────────────────────────────────────────────────────────────┘ │
│                                                                             │
│   Downstream: → MULTI_INTENT_SCORER → COMPLEXITY_CLASSIFIER                 │
│               → HYPOTHESIS_GENERATOR → gap detection                        │
│               → CONTROL.intents update in SessionState                      │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

#### F13: Ingress/Domain Classification Flow (Multi-Label)

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                F13: INGRESS/DOMAIN CLASSIFICATION (MULTI-LABEL)             │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│   Returns: domains[] above threshold (multi-domain requests possible)       │
│   Example: "My health insurance claim for therapy" → [HEALTH, FINANCE]      │
│                                                                             │
│   ┌───────────────────────────────────────────────────────────────────────┐ │
│   │                     ULTRABERT_INGRESS HEAD                            │ │
│   │                                                                       │ │
│   │   Input: User utterance                                               │ │
│   │          │                                                            │ │
│   │          ▼                                                            │ │
│   │   ┌─────────────────────────────────────────────────────────────┐     │ │
│   │   │ 12 Domain Classes (Multi-Label, Threshold-based)            │     │ │
│   │   ├─────────────────────────────────────────────────────────────┤     │ │
│   │   │ □ HEALTH         □ FINANCE        □ FAMILY                  │     │ │
│   │   │ □ WORK           □ SOCIAL         □ HOME                    │     │ │
│   │   │ □ TRAVEL         □ EDUCATION      □ ENTERTAINMENT           │     │ │
│   │   │ □ SELF_CARE      □ LEGAL          □ GENERAL                 │     │ │
│   │   └─────────────────────────────────────────────────────────────┘     │ │
│   │          │                                                            │ │
│   │    threshold = 0.4                                                    │ │
│   │          │                                                            │ │
│   │          ▼                                                            │ │
│   │   ┌─────────────────────────────────────────────────────────────┐     │ │
│   │   │ Output: domains[] = ["HEALTH", "FINANCE"]                   │     │ │
│   │   │                                                             │     │ │
│   │   │ len(domains) > 1 → multi-domain complexity bump             │     │ │
│   │   └─────────────────────────────────────────────────────────────┘     │ │
│   └───────────────────────────────────────────────────────────────────────┘ │
│                                                                             │
│   Downstream: → CROSS_DOMAIN_DETECTOR → domain_complexity                   │
│               → HYPOTHESIS_GENERATOR → context enrichment                   │
│               → CONTROL.domains[] update in SessionState                    │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

#### F14: Safety Band Classification Flow

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                     F14: SAFETY BAND CLASSIFICATION                         │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│   4 bands: GREEN (safe) → AMBER (caution) → RED (restrict) → CRISIS         │
│   CRISIS bypasses ALL routing - immediate safety protocol                   │
│                                                                             │
│   ┌───────────────────────────────────────────────────────────────────────┐ │
│   │                     ULTRABERT_SAFETY HEAD                             │ │
│   │                                                                       │ │
│   │   Input: User utterance                                               │ │
│   │          │                                                            │ │
│   │          ▼                                                            │ │
│   │   ┌─────────────────────────────────────────────────────────────┐     │ │
│   │   │ Safety Classification                                       │     │ │
│   │   ├─────────────────────────────────────────────────────────────┤     │ │
│   │   │                                                             │     │ │
│   │   │  ┌───────┐   ┌────────┐   ┌───────┐   ┌──────────┐         │     │ │
│   │   │  │ GREEN │ → │ AMBER  │ → │  RED  │ → │  CRISIS  │         │     │ │
│   │   │  │ Safe  │   │Caution │   │Restrict│   │Immediate │         │     │ │
│   │   │  │       │   │        │   │        │   │Protocol  │         │     │ │
│   │   │  └───────┘   └────────┘   └───────┘   └──────────┘         │     │ │
│   │   │      │           │            │             │               │     │ │
│   │   │      ▼           ▼            ▼             ▼               │     │ │
│   │   │  Normal      Heightened   Restricted    BYPASS ALL          │     │ │
│   │   │  Processing  Awareness    Actions       ROUTING             │     │ │
│   │   │                                                             │     │ │
│   │   └─────────────────────────────────────────────────────────────┘     │ │
│   │          │                                                            │ │
│   │          ▼                                                            │ │
│   │   Output: safety_band enum                                            │ │
│   └───────────────────────────────────────────────────────────────────────┘ │
│                                                                             │
│   Downstream: → CRISIS_DETECTOR (first check, before any routing)           │
│               → COMPLEXITY_CLASSIFIER (affects tier calculation)            │
│               → CONTROL.safety_band update in SessionState                  │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

#### F15: Emotion Detection Flow

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                       F15: EMOTION DETECTION FLOW                           │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│   44 emotion classes for fine-grained emotional understanding               │
│   Feeds into affective mirroring and tone adjustment                        │
│                                                                             │
│   ┌───────────────────────────────────────────────────────────────────────┐ │
│   │                     ULTRABERT_EMOTIONS HEAD                           │ │
│   │                                                                       │ │
│   │   Input: User utterance                                               │ │
│   │          │                                                            │ │
│   │          ▼                                                            │ │
│   │   ┌─────────────────────────────────────────────────────────────┐     │ │
│   │   │ 44 Emotion Classes                                          │     │ │
│   │   ├─────────────────────────────────────────────────────────────┤     │ │
│   │   │ joy, sadness, anger, fear, surprise, disgust, trust,        │     │ │
│   │   │ anticipation, anxiety, frustration, excitement, relief,     │     │ │
│   │   │ guilt, shame, pride, love, gratitude, hope, contentment,    │     │ │
│   │   │ boredom, loneliness, jealousy, embarrassment, confusion,    │     │ │
│   │   │ curiosity, nostalgia, empathy, sympathy, admiration,        │     │ │
│   │   │ amusement, awe, contempt, disappointment, envy, optimism,   │     │ │
│   │   │ pessimism, remorse, serenity, interest, acceptance,         │     │ │
│   │   │ apprehension, annoyance, distraction, pensiveness, ecstasy  │     │ │
│   │   └─────────────────────────────────────────────────────────────┘     │ │
│   │          │                                                            │ │
│   │          ▼                                                            │ │
│   │   Output: {emotion: "anxiety", intensity: 0.85}                       │ │
│   └───────────────────────────────────────────────────────────────────────┘ │
│                                                                             │
│   Downstream: → AFFECTIVE_MIRRORING_ENGINE (tone adjustment)                │
│               → COMPLEXITY_CLASSIFIER (emotion_intensity factor)            │
│               → AFFECTIVE_NOW update in SessionState                        │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

#### F16: NER Entity Extraction Flow

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                    F16: NER ENTITY EXTRACTION FLOW                          │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│   GlobalPointer architecture for nested entity extraction                   │
│   Extracts: PERSON, ORG, LOC, DATE, TIME, MONEY, etc.                       │
│                                                                             │
│   ┌───────────────────────────────────────────────────────────────────────┐ │
│   │                       ULTRABERT_NER HEAD                              │ │
│   │                                                                       │ │
│   │   Input: "Meet Dr. Smith at Mayo Clinic on Friday at 3pm"             │ │
│   │          │                                                            │ │
│   │          ▼                                                            │ │
│   │   ┌─────────────────────────────────────────────────────────────┐     │ │
│   │   │ GlobalPointer NER (supports nested entities)                │     │ │
│   │   ├─────────────────────────────────────────────────────────────┤     │ │
│   │   │                                                             │     │ │
│   │   │ PERSON:  "Dr. Smith"                                        │     │ │
│   │   │ ORG:     "Mayo Clinic"                                      │     │ │
│   │   │ DATE:    "Friday"                                           │     │ │
│   │   │ TIME:    "3pm"                                              │     │ │
│   │   │                                                             │     │ │
│   │   └─────────────────────────────────────────────────────────────┘     │ │
│   │          │                                                            │ │
│   │          ▼                                                            │ │
│   │   Output: entities[] with spans and types                             │ │
│   └───────────────────────────────────────────────────────────────────────┘ │
│                                                                             │
│   Downstream: → CONTEXT_INFERENCE (entity resolution with SessionState)     │
│               → BELIEFS_ACTIVE update (facts about entities)                │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

#### F17: Relations Extraction Flow

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                     F17: RELATIONS EXTRACTION FLOW                          │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│   Extracts relationships between entities for knowledge graph               │
│                                                                             │
│   ┌───────────────────────────────────────────────────────────────────────┐ │
│   │                    ULTRABERT_RELATIONS HEAD                           │ │
│   │                                                                       │ │
│   │   Input: "My wife Sarah works at Google with her brother"             │ │
│   │          │                                                            │ │
│   │          ▼                                                            │ │
│   │   ┌─────────────────────────────────────────────────────────────┐     │ │
│   │   │ Relation Types                                              │     │ │
│   │   ├─────────────────────────────────────────────────────────────┤     │ │
│   │   │ spouse_of, parent_of, child_of, sibling_of, works_at,       │     │ │
│   │   │ lives_in, friend_of, colleague_of, reports_to, member_of    │     │ │
│   │   └─────────────────────────────────────────────────────────────┘     │ │
│   │          │                                                            │ │
│   │          ▼                                                            │ │
│   │   ┌─────────────────────────────────────────────────────────────┐     │ │
│   │   │ Extracted Relations:                                        │     │ │
│   │   │   (USER, spouse_of, Sarah)                                  │     │ │
│   │   │   (Sarah, works_at, Google)                                 │     │ │
│   │   │   (Sarah, sibling_of, [brother])                            │     │ │
│   │   │   ([brother], works_at, Google)                             │     │ │
│   │   └─────────────────────────────────────────────────────────────┘     │ │
│   └───────────────────────────────────────────────────────────────────────┘ │
│                                                                             │
│   Downstream: → CONTEXT_INFERENCE (enrich entity understanding)             │
│               → K0 Knowledge Graph (long-term relation storage)             │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

#### F18: Sentiment Analysis Flow

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                      F18: SENTIMENT ANALYSIS FLOW                           │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│   5-level sentiment scale for overall conversational tone                   │
│                                                                             │
│   ┌───────────────────────────────────────────────────────────────────────┐ │
│   │                    ULTRABERT_SENTIMENT HEAD                           │ │
│   │                                                                       │ │
│   │   Input: User utterance                                               │ │
│   │          │                                                            │ │
│   │          ▼                                                            │ │
│   │   ┌─────────────────────────────────────────────────────────────┐     │ │
│   │   │ 5-Level Sentiment Scale                                     │     │ │
│   │   ├─────────────────────────────────────────────────────────────┤     │ │
│   │   │                                                             │     │ │
│   │   │  ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌────────┐ │ │
│   │   │  │very_neg  │ │negative  │ │neutral   │ │positive  │ │very_pos│ │ │
│   │   │  │  -2      │ │  -1      │ │   0      │ │  +1      │ │  +2    │ │ │
│   │   │  └──────────┘ └──────────┘ └──────────┘ └──────────┘ └────────┘ │ │
│   │   │                                                             │     │ │
│   │   └─────────────────────────────────────────────────────────────┘     │ │
│   │          │                                                            │ │
│   │          ▼                                                            │ │
│   │   Output: sentiment = "negative", score = -1                          │ │
│   └───────────────────────────────────────────────────────────────────────┘ │
│                                                                             │
│   Downstream: → AFFECTIVE_MIRRORING_ENGINE (combined with emotions)         │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

### 2.2 Safety Gate Flow

#### F19: Crisis Detection & Safety Override Flow

```
┌─────────────────────────────────────────────────────────────────────────────┐
│               F19: CRISIS DETECTION & SAFETY OVERRIDE                       │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│   CRITICAL: This check happens FIRST, before ANY other routing              │
│   CRISIS band = IMMEDIATE safety protocol, bypasses everything              │
│                                                                             │
│   ┌───────────────────────────────────────────────────────────────────────┐ │
│   │             SAFETY GATE (Hard Stop)                                   │ │
│   │                                                                       │ │
│   │   ULTRABERT_SAFETY                                                    │ │
│   │          │                                                            │ │
│   │     safety_band                                                       │ │
│   │          │                                                            │ │
│   │          ▼                                                            │ │
│   │   ┌─────────────────┐                                                 │ │
│   │   │ CRISIS_DETECTOR │                                                 │ │
│   │   │                 │                                                 │ │
│   │   │ Is band CRISIS? │                                                 │ │
│   │   └────────┬────────┘                                                 │ │
│   │            │                                                          │ │
│   │      ┌─────┴─────┐                                                    │ │
│   │      │           │                                                    │ │
│   │      ▼           ▼                                                    │ │
│   │     YES          NO                                                   │ │
│   │      │           │                                                    │ │
│   │      │           └──────────────────────────────────────┐             │ │
│   │      │                                                  │             │ │
│   │      ▼                                                  ▼             │ │
│   │  ┌───────────────────┐                    ┌─────────────────────┐     │ │
│   │  │  SAFETY_OVERRIDE  │                    │ Continue to         │     │ │
│   │  │                   │                    │ COMPLEXITY_CLASSIFIER│     │ │
│   │  │  Bypasses ALL     │                    │ (normal routing)    │     │ │
│   │  │  routing logic    │                    └─────────────────────┘     │ │
│   │  └─────────┬─────────┘                                                │ │
│   │            │                                                          │ │
│   │       immediate                                                       │ │
│   │            │                                                          │ │
│   │            ▼                                                          │ │
│   │  ┌───────────────────┐  safety.crisis   ┌─────────────────────┐       │ │
│   │  │    TIER_CRISIS    │ ────.protocol───▶│   SAFETY_MAILBOX    │       │ │
│   │  │                   │                  │                     │       │ │
│   │  │ Safety Protocol   │                  │ WFQ Priority: URGENT│       │ │
│   │  │ (crisis response) │                  │ (highest priority)  │       │ │
│   │  └───────────────────┘                  └─────────────────────┘       │ │
│   └───────────────────────────────────────────────────────────────────────┘ │
│                                                                             │
│   Key: User safety is ALWAYS the highest priority - no exceptions           │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

### 2.3 Complexity Routing Flow

#### F20: Multi-Intent Scoring Flow

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                      F20: MULTI-INTENT SCORING FLOW                         │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│   Calculates intent complexity from UltraBERT multi-label output            │
│                                                                             │
│   ┌───────────────────────────────────────────────────────────────────────┐ │
│   │                                                                       │ │
│   │   ULTRABERT_INTENT                                                    │ │
│   │          │                                                            │ │
│   │    intents[] + scores{}                                               │ │
│   │          │                                                            │ │
│   │          ▼                                                            │ │
│   │   ┌─────────────────────────────────────────────────────────────┐     │ │
│   │   │              MULTI_INTENT_SCORER                            │     │ │
│   │   ├─────────────────────────────────────────────────────────────┤     │ │
│   │   │                                                             │     │ │
│   │   │  Scoring Formula:                                           │     │ │
│   │   │  intent_complexity = len(intents) + weighted_intent_types   │     │ │
│   │   │                                                             │     │ │
│   │   │  Rules:                                                     │     │ │
│   │   │  • 1 intent → LOW base                                      │     │ │
│   │   │  • 2 intents → MEDIUM base                                  │     │ │
│   │   │  • 3+ intents → HIGH base                                   │     │ │
│   │   │  • Certain intent combos (e.g., emotional + task) → bump    │     │ │
│   │   │                                                             │     │ │
│   │   └─────────────────────────────────────────────────────────────┘     │ │
│   │          │                                                            │ │
│   │     intent_complexity                                                 │ │
│   │          │                                                            │ │
│   │          ▼                                                            │ │
│   │   COMPLEXITY_CLASSIFIER                                               │ │
│   └───────────────────────────────────────────────────────────────────────┘ │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

#### F21: Cross-Domain Detection Flow

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                     F21: CROSS-DOMAIN DETECTION FLOW                        │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│   Multi-domain requests are inherently more complex                         │
│   Example: "Schedule my doctor and update my budget" → HEALTH + FINANCE     │
│                                                                             │
│   ┌───────────────────────────────────────────────────────────────────────┐ │
│   │                                                                       │ │
│   │   ULTRABERT_INGRESS                                                   │ │
│   │          │                                                            │ │
│   │     domains[]                                                         │ │
│   │          │                                                            │ │
│   │          ▼                                                            │ │
│   │   ┌─────────────────────────────────────────────────────────────┐     │ │
│   │   │             CROSS_DOMAIN_DETECTOR                           │     │ │
│   │   ├─────────────────────────────────────────────────────────────┤     │ │
│   │   │                                                             │     │ │
│   │   │  Check: len(domains) > 1 ?                                  │     │ │
│   │   │                                                             │     │ │
│   │   │  ┌─────────────┐    ┌─────────────┐    ┌─────────────┐      │     │ │
│   │   │  │ 1 domain    │    │ 2 domains   │    │ 3+ domains  │      │     │ │
│   │   │  │             │    │             │    │             │      │     │ │
│   │   │  │ No bump     │    │ +1 tier     │    │ +2 tiers    │      │     │ │
│   │   │  └─────────────┘    └─────────────┘    └─────────────┘      │     │ │
│   │   │                                                             │     │ │
│   │   └─────────────────────────────────────────────────────────────┘     │ │
│   │          │                                                            │ │
│   │     domain_complexity                                                 │ │
│   │          │                                                            │ │
│   │          ▼                                                            │ │
│   │   COMPLEXITY_CLASSIFIER                                               │ │
│   └───────────────────────────────────────────────────────────────────────┘ │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

#### F22: Complexity Classification Flow

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                    F22: COMPLEXITY CLASSIFICATION FLOW                      │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│   Multi-Factor Classification: intent + domain + safety + emotion           │
│                                                                             │
│   ┌───────────────────────────────────────────────────────────────────────┐ │
│   │                    COMPLEXITY_CLASSIFIER                              │ │
│   │                                                                       │ │
│   │   Inputs:                                                             │ │
│   │   ┌─────────────────┐  ┌─────────────────┐                            │ │
│   │   │intent_complexity│  │domain_complexity│                            │ │
│   │   │ (from F20)      │  │ (from F21)      │                            │ │
│   │   └────────┬────────┘  └────────┬────────┘                            │ │
│   │            │                    │                                     │ │
│   │   ┌────────┴────────┐  ┌────────┴────────┐                            │ │
│   │   │ safety_band     │  │emotion_intensity│                            │ │
│   │   │(ULTRABERT_SAFETY)  │(ULTRABERT_EMOT)│                            │ │
│   │   └────────┬────────┘  └────────┬────────┘                            │ │
│   │            │                    │                                     │ │
│   │            └────────────┬───────┘                                     │ │
│   │                         │                                             │ │
│   │                         ▼                                             │ │
│   │   ┌─────────────────────────────────────────────────────────────┐     │ │
│   │   │            COMPLEXITY DECISION MATRIX                       │     │ │
│   │   ├─────────────────────────────────────────────────────────────┤     │ │
│   │   │                                                             │     │ │
│   │   │  LOW:    single intent + single domain                      │     │ │
│   │   │          → TIER_LOW → Tool First → ~500 tokens              │     │ │
│   │   │                                                             │     │ │
│   │   │  MEDIUM: multi-intent OR multi-domain                       │     │ │
│   │   │          → TIER_MEDIUM → LLM Reasoning → 2K tokens          │     │ │
│   │   │                                                             │     │ │
│   │   │  HIGH:   complex + emotional (high intensity)               │     │ │
│   │   │          → TIER_HIGH → LLM Planning → 8K tokens             │     │ │
│   │   │                                                             │     │ │
│   │   │  CRISIS: safety_band = CRISIS (bypassed earlier)            │     │ │
│   │   │          → TIER_CRISIS → Safety Protocol                    │     │ │
│   │   │                                                             │     │ │
│   │   └─────────────────────────────────────────────────────────────┘     │ │
│   │                         │                                             │ │
│   │         ┌───────────────┼───────────────┐                             │ │
│   │         ▼               ▼               ▼                             │ │
│   │    TIER_LOW        TIER_MEDIUM      TIER_HIGH                         │ │
│   └───────────────────────────────────────────────────────────────────────┘ │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

### 2.4 Gap Detection & Clarification Flow

#### F23: Hypothesis Generation Flow

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                    F23: HYPOTHESIS GENERATION FLOW                          │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│   Receives explicit multi-intent from heads, generates hypotheses           │
│   for what the user might need                                              │
│                                                                             │
│   ┌───────────────────────────────────────────────────────────────────────┐ │
│   │                                                                       │ │
│   │   ULTRABERT_INTENT ─────┐                                             │ │
│   │   (intents[] explicit)  │                                             │ │
│   │                         │                                             │ │
│   │   ULTRABERT_INGRESS ────┼─────────────────┐                           │ │
│   │   (domains[] context)   │                 │                           │ │
│   │                         │                 │                           │ │
│   │                         ▼                 ▼                           │ │
│   │              ┌─────────────────────────────────────┐                  │ │
│   │              │       HYPOTHESIS_GENERATOR          │                  │ │
│   │              ├─────────────────────────────────────┤                  │ │
│   │              │                                     │                  │ │
│   │              │  For each intent in intents[]:      │                  │ │
│   │              │    - Generate hypothesis            │                  │ │
│   │              │    - Cross-reference with domains[] │                  │ │
│   │              │    - Identify required slots        │                  │ │
│   │              │                                     │                  │ │
│   │              │  Output: all_intent_requirements    │                  │ │
│   │              │                                     │                  │ │
│   │              └──────────────────┬──────────────────┘                  │ │
│   │                                 │                                     │ │
│   │                  all_intent_requirements                              │ │
│   │                                 │                                     │ │
│   │                                 ▼                                     │ │
│   │                   CONTRACT_SIGNAL_GAPS                                │ │
│   └───────────────────────────────────────────────────────────────────────┘ │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

#### F24: Contract & Signal Gap Detection Flow

```
┌─────────────────────────────────────────────────────────────────────────────┐
│               F24: CONTRACT & SIGNAL GAP DETECTION FLOW                     │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│   Union of ALL intent requirements - what's missing from user input?        │
│                                                                             │
│   ┌───────────────────────────────────────────────────────────────────────┐ │
│   │                                                                       │ │
│   │   HYPOTHESIS_GENERATOR                                                │ │
│   │          │                                                            │ │
│   │   all_intent_requirements                                             │ │
│   │          │                                                            │ │
│   │          ▼                                                            │ │
│   │   ┌─────────────────────────────────────────────────────────────┐     │ │
│   │   │             CONTRACT_SIGNAL_GAPS                            │     │ │
│   │   ├─────────────────────────────────────────────────────────────┤     │ │
│   │   │                                                             │     │ │
│   │   │  Check for missing signals:                                 │     │ │
│   │   │  • Required slots not filled                                │     │ │
│   │   │  • Ambiguous references                                     │     │ │
│   │   │  • Missing constraints                                      │     │ │
│   │   │                                                             │     │ │
│   │   └──────────────────┬──────────────────────────────────────────┘     │ │
│   │                      │                                                │ │
│   │                 signals                                               │ │
│   │                      │                                                │ │
│   │                      ▼                                                │ │
│   │   ┌─────────────────────────────────────────────────────────────┐     │ │
│   │   │               SIGNAL_LIBRARY                                │     │ │
│   │   ├─────────────────────────────────────────────────────────────┤     │ │
│   │   │                                                             │     │ │
│   │   │  Signal Types:                                              │     │ │
│   │   │  • Pronoun ambiguity ("he", "she", "they")                  │     │ │
│   │   │  • Conflicts (contradictory info)                           │     │ │
│   │   │  • Multi-entity ambiguity ("my doctor")                     │     │ │
│   │   │  • Time vagueness ("soon", "later")                         │     │ │
│   │   │                                                             │     │ │
│   │   └─────────────────────────────────────────────────────────────┘     │ │
│   │                      │                                                │ │
│   │             slot_fill_request                                         │ │
│   │                      │                                                │ │
│   │                      ▼                                                │ │
│   │               CONTEXT_INFERENCE                                       │ │
│   └───────────────────────────────────────────────────────────────────────┘ │
│                                                                             │
│   Also queries: CAPABILITY_REGISTRY (for capability requirements)           │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

#### F25: Context Inference Flow

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                     F25: CONTEXT INFERENCE FLOW                             │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│   SessionState fill + entity resolution - use what we already know          │
│                                                                             │
│   ┌───────────────────────────────────────────────────────────────────────┐ │
│   │                                                                       │ │
│   │   ULTRABERT_NER ────────┐                                             │ │
│   │   (entities)            │                                             │ │
│   │                         │                                             │ │
│   │   ULTRABERT_RELATIONS ──┼──────────┐                                  │ │
│   │   (relations)           │          │                                  │ │
│   │                         │          │                                  │ │
│   │   CONTRACT_SIGNAL_GAPS ─┼──────────┼──────┐                           │ │
│   │   (slot_fill_request)   │          │      │                           │ │
│   │                         ▼          ▼      ▼                           │ │
│   │              ┌─────────────────────────────────────┐                  │ │
│   │              │         CONTEXT_INFERENCE           │                  │ │
│   │              ├─────────────────────────────────────┤                  │ │
│   │              │                                     │                  │ │
│   │              │  1. Look up entities in SessionState│                  │ │
│   │              │     (BELIEFS_ACTIVE, HISTORY_ACTIVE)│                  │ │
│   │              │                                     │                  │ │
│   │              │  2. Resolve "my doctor" → Dr. Smith │                  │ │
│   │              │     using relation + entity data    │                  │ │
│   │              │                                     │                  │ │
│   │              │  3. Fill slots from known context   │                  │ │
│   │              │                                     │                  │ │
│   │              │  4. Track provenance (where data    │                  │ │
│   │              │     came from)                      │                  │ │
│   │              │                                     │                  │ │
│   │              └──────────────────┬──────────────────┘                  │ │
│   │                                 │                                     │ │
│   │                  filled_intent + provenance                           │ │
│   │                                 │                                     │ │
│   │                                 ▼                                     │ │
│   │                      TINY_SANITY_ARBITER                              │ │
│   └───────────────────────────────────────────────────────────────────────┘ │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

#### F26: Tiny Sanity Arbiter Validation Flow

```
┌─────────────────────────────────────────────────────────────────────────────┐
│               F26: TINY SANITY ARBITER VALIDATION FLOW                      │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│   Fast path validation using UltraBERT + cached checks                      │
│   Quick sanity check before proceeding                                      │
│                                                                             │
│   ┌───────────────────────────────────────────────────────────────────────┐ │
│   │                                                                       │ │
│   │   CONTEXT_INFERENCE                                                   │ │
│   │          │                                                            │ │
│   │   filled_intent + provenance                                          │ │
│   │          │                                                            │ │
│   │          ▼                                                            │ │
│   │   ┌─────────────────────────────────────────────────────────────┐     │ │
│   │   │         TINY_SANITY_ARBITER (Fast Path)                     │     │ │
│   │   ├─────────────────────────────────────────────────────────────┤     │ │
│   │   │                                                             │     │ │
│   │   │  Checks (all fast, <5ms total):                             │     │ │
│   │   │  • UltraBERT confidence thresholds                          │     │ │
│   │   │  • Cached validation rules                                  │     │ │
│   │   │  • Known conflict patterns                                  │     │ │
│   │   │  • Entity consistency                                       │     │ │
│   │   │                                                             │     │ │
│   │   │  Output:                                                    │     │ │
│   │   │  • verdict: PROCEED | CLARIFY | REJECT                      │     │ │
│   │   │  • flags: [warning_types]                                   │     │ │
│   │   │                                                             │     │ │
│   │   └──────────────────┬──────────────────────────────────────────┘     │ │
│   │                      │                                                │ │
│   │               verdict + flags                                         │ │
│   │                      │                                                │ │
│   │                      ▼                                                │ │
│   │              UNCERTAINTY_ESTIMATOR                                    │ │
│   └───────────────────────────────────────────────────────────────────────┘ │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

#### F27: Uncertainty Estimation Flow

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                   F27: UNCERTAINTY ESTIMATION FLOW                          │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│   Combines UltraBERT confidence with arbiter flags to decide: proceed       │
│   or clarify?                                                               │
│                                                                             │
│   ┌───────────────────────────────────────────────────────────────────────┐ │
│   │                                                                       │ │
│   │   TINY_SANITY_ARBITER ──────┐                                         │ │
│   │   (verdict + flags)         │                                         │ │
│   │                             │                                         │ │
│   │   ULTRABERT_INTENT ─────────┼─────────┐                               │ │
│   │   (confidence_score)        │         │                               │ │
│   │                             ▼         ▼                               │ │
│   │              ┌─────────────────────────────────────┐                  │ │
│   │              │       UNCERTAINTY_ESTIMATOR         │                  │ │
│   │              ├─────────────────────────────────────┤                  │ │
│   │              │                                     │                  │ │
│   │              │  Uncertainty Score Calculation:     │                  │ │
│   │              │  • Low confidence → high uncertainty│                  │ │
│   │              │  • Many flags → high uncertainty    │                  │ │
│   │              │  • Multiple intents → moderate      │                  │ │
│   │              │                                     │                  │ │
│   │              │  Threshold: uncertainty ≥ 0.2       │                  │ │
│   │              │  → triggers clarification           │                  │ │
│   │              │                                     │                  │ │
│   │              └──────────────────┬──────────────────┘                  │ │
│   │                                 │                                     │ │
│   │                        score + reasons                                │ │
│   │                                 │                                     │ │
│   │                                 ▼                                     │ │
│   │                ENTROPY_MIN_QUESTION_PLANNER                           │ │
│   └───────────────────────────────────────────────────────────────────────┘ │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

#### F28: Entropy-Minimizing Question Planning Flow

```
┌─────────────────────────────────────────────────────────────────────────────┐
│            F28: ENTROPY-MINIMIZING QUESTION PLANNING FLOW                   │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│   Progressive disclosure: Ask 1-2 high-information questions                │
│   Minimize user burden while maximizing clarity                             │
│                                                                             │
│   ┌───────────────────────────────────────────────────────────────────────┐ │
│   │                                                                       │ │
│   │   UNCERTAINTY_ESTIMATOR                                               │ │
│   │          │                                                            │ │
│   │   score + reasons (uncertainty ≥ 0.2)                                 │ │
│   │          │                                                            │ │
│   │          ▼                                                            │ │
│   │   ┌─────────────────────────────────────────────────────────────┐     │ │
│   │   │       ENTROPY_MIN_QUESTION_PLANNER                          │     │ │
│   │   ├─────────────────────────────────────────────────────────────┤     │ │
│   │   │                                                             │     │ │
│   │   │  Strategy: Progressive Disclosure                           │     │ │
│   │   │                                                             │     │ │
│   │   │  1. Rank gaps by information value                          │     │ │
│   │   │  2. Select 1-2 highest-value questions                      │     │ │
│   │   │  3. Phrase for natural conversation                         │     │ │
│   │   │                                                             │     │ │
│   │   │  Example:                                                   │     │ │
│   │   │  Input: "Remind me about my doctor"                         │     │ │
│   │   │  Gaps: [which_doctor?, what_time?, which_appointment?]      │     │ │
│   │   │  Best Q: "Which doctor - Dr. Smith or Dr. Jones?"           │     │ │
│   │   │                                                             │     │ │
│   │   └──────────────────┬──────────────────────────────────────────┘     │ │
│   │                      │                                                │ │
│   │               question_plan                                           │ │
│   │                      │                                                │ │
│   │                      ▼                                                │ │
│   │   ┌──────────────────────────────────────────────────────────────┐    │ │
│   │   │                    CLARIFYING                                │    │ │
│   │   │                         │                                    │    │ │
│   │   │             generate clarification                           │    │ │
│   │   │                         │                                    │    │ │
│   │   │                         ▼                                    │    │ │
│   │   │                   MODEL_GATEWAY                              │    │ │
│   │   │             (natural language question)                      │    │ │
│   │   └──────────────────────────────────────────────────────────────┘    │ │
│   └───────────────────────────────────────────────────────────────────────┘ │
│                                                                             │
│   Also updates: PENDING_CLARIFICATIONS in SessionState                      │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

### 2.5 UltraBERT → SessionState Update Flow

#### F29: Emotion → AFFECTIVE_NOW Update Flow

```
┌─────────────────────────────────────────────────────────────────────────────┐
│               F29: EMOTION → AFFECTIVE_NOW UPDATE FLOW                      │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│   Real-time emotional state tracking in HOT memory                          │
│                                                                             │
│   ┌───────────────────────────────────────────────────────────────────────┐ │
│   │                                                                       │ │
│   │   ULTRABERT_EMOTIONS                                                  │ │
│   │          │                                                            │ │
│   │   {emotion: "anxiety", intensity: 0.85}                               │ │
│   │          │                                                            │ │
│   │   update AFFECTIVE_NOW                                                │ │
│   │          │                                                            │ │
│   │          ▼                                                            │ │
│   │   ┌─────────────────────────────────────────────────────────────┐     │ │
│   │   │              AFFECTIVE_NOW (HOT CORE - 4KB)                 │     │ │
│   │   ├─────────────────────────────────────────────────────────────┤     │ │
│   │   │                                                             │     │ │
│   │   │  {                                                          │     │ │
│   │   │    "current_emotion": "anxiety",                            │     │ │
│   │   │    "intensity": 0.85,                                       │     │ │
│   │   │    "trajectory": "increasing",                              │     │ │
│   │   │    "last_updated": "2024-01-15T10:30:00Z"                   │     │ │
│   │   │  }                                                          │     │ │
│   │   │                                                             │     │ │
│   │   └─────────────────────────────────────────────────────────────┘     │ │
│   │                                                                       │ │
│   │   Used by:                                                            │ │
│   │   • AFFECTIVE_MIRRORING_ENGINE (tone adjustment)                      │ │
│   │   • COMPLEXITY_CLASSIFIER (HIGH tier if emotional)                    │ │
│   │   • FABRIC_POLICY_ENGINE (affective routing)                          │ │
│   └───────────────────────────────────────────────────────────────────────┘ │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

#### F30: NER → BELIEFS_ACTIVE Update Flow

```
┌─────────────────────────────────────────────────────────────────────────────┐
│               F30: NER → BELIEFS_ACTIVE UPDATE FLOW                         │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│   Extract entities, store as facts in HOT memory                            │
│                                                                             │
│   ┌───────────────────────────────────────────────────────────────────────┐ │
│   │                                                                       │ │
│   │   ULTRABERT_NER                                                       │ │
│   │          │                                                            │ │
│   │   entities = [                                                        │ │
│   │     {type: "PERSON", value: "Dr. Smith", span: [5,13]},               │ │
│   │     {type: "ORG", value: "Mayo Clinic", span: [17,28]},               │ │
│   │     {type: "TIME", value: "3pm", span: [32,35]}                       │ │
│   │   ]                                                                   │ │
│   │          │                                                            │ │
│   │   update BELIEFS_ACTIVE                                               │ │
│   │          │                                                            │ │
│   │          ▼                                                            │ │
│   │   ┌─────────────────────────────────────────────────────────────┐     │ │
│   │   │            BELIEFS_ACTIVE (HOT CORE - 8KB)                  │     │ │
│   │   ├─────────────────────────────────────────────────────────────┤     │ │
│   │   │                                                             │     │ │
│   │   │  Current turn facts:                                        │     │ │
│   │   │  • mentioned_person: "Dr. Smith"                            │     │ │
│   │   │  • mentioned_org: "Mayo Clinic"                             │     │ │
│   │   │  • mentioned_time: "3pm"                                    │     │ │
│   │   │  • turn_id: 42                                              │     │ │
│   │   │                                                             │     │ │
│   │   └─────────────────────────────────────────────────────────────┘     │ │
│   │                                                                       │ │
│   │   Used by: CONTEXT_INFERENCE for entity resolution                    │ │
│   └───────────────────────────────────────────────────────────────────────┘ │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

#### F31: Safety → CONTROL Update Flow

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                 F31: SAFETY → CONTROL UPDATE FLOW                           │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│   Safety band tracked in CONTROL for system-wide awareness                  │
│                                                                             │
│   ┌───────────────────────────────────────────────────────────────────────┐ │
│   │                                                                       │ │
│   │   ULTRABERT_SAFETY                                                    │ │
│   │          │                                                            │ │
│   │   safety_band = "AMBER"                                               │ │
│   │          │                                                            │ │
│   │   update CONTROL.safety_band                                          │ │
│   │          │                                                            │ │
│   │          ▼                                                            │ │
│   │   ┌─────────────────────────────────────────────────────────────┐     │ │
│   │   │                CONTROL (HOT CORE - 8KB)                     │     │ │
│   │   ├─────────────────────────────────────────────────────────────┤     │ │
│   │   │                                                             │     │ │
│   │   │  {                                                          │     │ │
│   │   │    "safety_band": "AMBER",                                  │     │ │
│   │   │    "active_leases": [...],                                  │     │ │
│   │   │    "turn_lock": {...},                                      │     │ │
│   │   │    "intents": {...},                                        │     │ │
│   │   │    "domains": [...]                                         │     │ │
│   │   │  }                                                          │     │ │
│   │   │                                                             │     │ │
│   │   └─────────────────────────────────────────────────────────────┘     │ │
│   │                                                                       │ │
│   │   System-wide: All components check CONTROL.safety_band               │ │
│   └───────────────────────────────────────────────────────────────────────┘ │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

#### F32: Intent/Ingress → CONTROL Update Flow

```
┌─────────────────────────────────────────────────────────────────────────────┐
│              F32: INTENT/INGRESS → CONTROL UPDATE FLOW                      │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│   Multi-label intents and domains stored in CONTROL                         │
│                                                                             │
│   ┌───────────────────────────────────────────────────────────────────────┐ │
│   │                                                                       │ │
│   │   ULTRABERT_INTENT ─────────────────┐                                 │ │
│   │   {primary, all[], scores{}}        │                                 │ │
│   │                                     │                                 │ │
│   │   ULTRABERT_INGRESS ────────────────┼───────┐                         │ │
│   │   domains[]                         │       │                         │ │
│   │                                     ▼       ▼                         │ │
│   │              ┌─────────────────────────────────────┐                  │ │
│   │              │         CONTROL (HOT CORE - 8KB)    │                  │ │
│   │              ├─────────────────────────────────────┤                  │ │
│   │              │                                     │                  │ │
│   │              │  "intents": {                       │                  │ │
│   │              │    "primary": "set_reminder",       │                  │ │
│   │              │    "all": ["set_reminder",          │                  │ │
│   │              │            "log_memory"],           │                  │ │
│   │              │    "scores": {                      │                  │ │
│   │              │      "set_reminder": 0.92,          │                  │ │
│   │              │      "log_memory": 0.78             │                  │ │
│   │              │    }                                │                  │ │
│   │              │  },                                 │                  │ │
│   │              │  "domains": ["HEALTH", "PERSONAL"]  │                  │ │
│   │              │                                     │                  │ │
│   │              └─────────────────────────────────────┘                  │ │
│   │                                                                       │ │
│   │   Used by: DISPATCHING for routing decisions                          │ │
│   │            CAPABILITY_FABRIC for provider selection                   │ │
│   └───────────────────────────────────────────────────────────────────────┘ │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## 3. TOOL EXECUTION FLOWS

### 3.1 Tool Execution & Result Pipeline

#### F33: Capability Fabric Tool Invocation Flow

```
┌─────────────────────────────────────────────────────────────────────────────┐
│               F33: CAPABILITY FABRIC TOOL INVOCATION FLOW                   │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│   Fabric resolves capability → provider → appropriate runner                │
│                                                                             │
│   ┌───────────────────────────────────────────────────────────────────────┐ │
│   │                                                                       │ │
│   │   TOOL_INVOKE_CAPABILITY (Concierge Tool)                             │ │
│   │          │                                                            │ │
│   │   Fabric Invocation                                                   │ │
│   │          │                                                            │ │
│   │          ▼                                                            │ │
│   │   ┌─────────────────────────────────────────────────────────────┐     │ │
│   │   │              CAPABILITY_FABRIC                              │     │ │
│   │   ├─────────────────────────────────────────────────────────────┤     │ │
│   │   │                                                             │     │ │
│   │   │  1. Resolve capability name → contract                      │     │ │
│   │   │  2. Find matching provider                                  │     │ │
│   │   │  3. Check QoS + affective routing                           │     │ │
│   │   │  4. Build context from SessionState                         │     │ │
│   │   │                                                             │     │ │
│   │   └──────────────────┬──────────────────────────────────────────┘     │ │
│   │                      │                                                │ │
│   │            invoke tool capability                                     │ │
│   │                      │                                                │ │
│   │                      ▼                                                │ │
│   │   ┌─────────────────────────────────────────────────────────────┐     │ │
│   │   │                TOOL_PROVIDERS                               │     │ │
│   │   ├─────────────────────────────────────────────────────────────┤     │ │
│   │   │                                                             │     │ │
│   │   │  Provider routes to appropriate runner:                     │     │ │
│   │   │  ┌───────────┐  ┌───────────┐  ┌───────────┐               │     │ │
│   │   │  │MCP_RUNNERS│  │K0_GENERIC │  │WASM_     │               │     │ │
│   │   │  │           │  │_CLIENT    │  │SANDBOX   │               │     │ │
│   │   │  │MCP tools  │  │K0 memory  │  │Isolated  │               │     │ │
│   │   │  └───────────┘  └───────────┘  └───────────┘               │     │ │
│   │   │                                                             │     │ │
│   │   └─────────────────────────────────────────────────────────────┘     │ │
│   └───────────────────────────────────────────────────────────────────────┘ │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

#### F34: MCP Tool Execution Flow

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                    F34: MCP TOOL EXECUTION FLOW                             │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│   MCP (Model Context Protocol) tools - local and remote servers             │
│                                                                             │
│   ┌───────────────────────────────────────────────────────────────────────┐ │
│   │                                                                       │ │
│   │   TOOL_PROVIDERS                                                      │ │
│   │          │                                                            │ │
│   │    MCP tool call                                                      │ │
│   │          │                                                            │ │
│   │          ▼                                                            │ │
│   │   ┌─────────────────────────────────────────────────────────────┐     │ │
│   │   │                   MCP_RUNNERS                               │     │ │
│   │   ├─────────────────────────────────────────────────────────────┤     │ │
│   │   │                                                             │     │ │
│   │   │  Executes tools from MCP Servers:                           │     │ │
│   │   │                                                             │     │ │
│   │   │  ┌──────────────────────┐  ┌──────────────────────┐         │     │ │
│   │   │  │ LOCAL_MCP_SERVERS    │  │ REMOTE_MCP_SERVERS   │         │     │ │
│   │   │  │                      │  │                      │         │     │ │
│   │   │  │ Device-Hosted        │  │ Company-Hosted       │         │     │ │
│   │   │  │ Personal Tools       │  │ External Systems     │         │     │ │
│   │   │  │ (calendar, notes,    │  │ (APIs, databases,    │         │     │ │
│   │   │  │  local files)        │  │  integrations)       │         │     │ │
│   │   │  └──────────────────────┘  └──────────────────────┘         │     │ │
│   │   │                                                             │     │ │
│   │   │  Via: K0_CONNECTOR_PROXY (auth, routing, caching)           │     │ │
│   │   │                                                             │     │ │
│   │   └──────────────────┬──────────────────────────────────────────┘     │ │
│   │                      │                                                │ │
│   │             tool_result JSON                                          │ │
│   │                      │                                                │ │
│   │                      ▼                                                │ │
│   │               TOOL_PROVIDERS                                          │ │
│   └───────────────────────────────────────────────────────────────────────┘ │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

#### F35: K0 Memory Operation Flow

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                     F35: K0 MEMORY OPERATION FLOW                           │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│   Memory operations via K0 - recall, write, consolidate                     │
│                                                                             │
│   ┌───────────────────────────────────────────────────────────────────────┐ │
│   │                                                                       │ │
│   │   TOOL_PROVIDERS                                                      │ │
│   │          │                                                            │ │
│   │    K0 memory operation                                                │ │
│   │          │                                                            │ │
│   │          ▼                                                            │ │
│   │   ┌─────────────────────────────────────────────────────────────┐     │ │
│   │   │               K0_GENERIC_CLIENT                             │     │ │
│   │   ├─────────────────────────────────────────────────────────────┤     │ │
│   │   │                                                             │     │ │
│   │   │  Only transport + auth (K0's internal concern)              │     │ │
│   │   │                                                             │     │ │
│   │   └──────────────────┬──────────────────────────────────────────┘     │ │
│   │                      │                                                │ │
│   │            generic transport                                          │ │
│   │                      │                                                │ │
│   │                      ▼                                                │ │
│   │   ┌─────────────────────────────────────────────────────────────┐     │ │
│   │   │             K0 INTERNAL (See k0_diagram.mmd)                │     │ │
│   │   ├─────────────────────────────────────────────────────────────┤     │ │
│   │   │                                                             │     │ │
│   │   │  K0 Pipelines:                                              │     │ │
│   │   │  • P01: Recall / Read                                       │     │ │
│   │   │  • P02: Write / Ingest                                      │     │ │
│   │   │  • P03: Memory Consolidation                                │     │ │
│   │   │  • P08: Embedding Management                                │     │ │
│   │   │  • P20: Procedure / Habits                                  │     │ │
│   │   │                                                             │     │ │
│   │   └──────────────────┬──────────────────────────────────────────┘     │ │
│   │                      │                                                │ │
│   │              K0 response                                              │ │
│   │                      │                                                │ │
│   │                      ▼                                                │ │
│   │               TOOL_PROVIDERS                                          │ │
│   └───────────────────────────────────────────────────────────────────────┘ │
│                                                                             │ │
└─────────────────────────────────────────────────────────────────────────────┘
```

#### F36: WASM Sandbox Execution Flow

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                   F36: WASM SANDBOX EXECUTION FLOW                          │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│   Isolated execution for untrusted or custom code                           │
│                                                                             │
│   ┌───────────────────────────────────────────────────────────────────────┐ │
│   │                                                                       │ │
│   │   TOOL_PROVIDERS                                                      │ │
│   │          │                                                            │ │
│   │    sandboxed execution                                                │ │
│   │          │                                                            │ │
│   │          ▼                                                            │ │
│   │   ┌─────────────────────────────────────────────────────────────┐     │ │
│   │   │                  WASM_SANDBOX                                │     │ │
│   │   ├─────────────────────────────────────────────────────────────┤     │ │
│   │   │                                                             │     │ │
│   │   │  Security Features:                                         │     │ │
│   │   │  • Memory isolation                                         │     │ │
│   │   │  • CPU time limits                                          │     │ │
│   │   │  • No network access (unless explicitly granted)            │     │ │
│   │   │  • Sandboxed filesystem                                     │     │ │
│   │   │                                                             │     │ │
│   │   │  Use Cases:                                                 │     │ │
│   │   │  • User-defined scripts                                     │     │ │
│   │   │  • Third-party plugins                                      │     │ │
│   │   │  • Untrusted transformations                                │     │ │
│   │   │                                                             │     │ │
│   │   └──────────────────┬──────────────────────────────────────────┘     │ │
│   │                      │                                                │ │
│   │             sandbox output                                            │ │
│   │                      │                                                │ │
│   │                      ▼                                                │ │
│   │               TOOL_PROVIDERS                                          │ │
│   └───────────────────────────────────────────────────────────────────────┘ │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

#### F37: Tool Result Return Flow

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                    F37: TOOL RESULT RETURN FLOW                             │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│   Results packaged and returned through Capability Fabric                   │
│                                                                             │
│   ┌───────────────────────────────────────────────────────────────────────┐ │
│   │                                                                       │ │
│   │   Runners (MCP/K0/WASM)                                               │ │
│   │          │                                                            │ │
│   │    tool_result / K0 response / sandbox output                         │ │
│   │          │                                                            │ │
│   │          ▼                                                            │ │
│   │   ┌─────────────────────────────────────────────────────────────┐     │ │
│   │   │                TOOL_PROVIDERS                               │     │ │
│   │   │                                                             │     │ │
│   │   │  Package result as CapabilityResult:                        │     │ │
│   │   │  {                                                          │     │ │
│   │   │    success: true/false,                                     │     │ │
│   │   │    data: <result_payload>,                                  │     │ │
│   │   │    error: <error_if_any>                                    │     │ │
│   │   │  }                                                          │     │ │
│   │   │                                                             │     │ │
│   │   └──────────────────┬──────────────────────────────────────────┘     │ │
│   │                      │                                                │ │
│   │      CapabilityResult{success, data, error}                           │ │
│   │                      │                                                │ │
│   │                      ▼                                                │ │
│   │   ┌─────────────────────────────────────────────────────────────┐     │ │
│   │   │              CAPABILITY_FABRIC                              │     │ │
│   │   │                                                             │     │ │
│   │   │  Emits: k1.capability.completed.v1 + result                 │     │ │
│   │   │                                                             │     │ │
│   │   └──────────────────┬──────────────────────────────────────────┘     │ │
│   │                      │                                                │ │
│   │         ┌────────────┴────────────┐                                   │ │
│   │         ▼                         ▼                                   │ │
│   │  LOW: tool_result       MEDIUM/HIGH: tool_result                      │ │
│   │         │                         │                                   │ │
│   │         ▼                         ▼                                   │ │
│   │   COMPANIONING           ORCHESTRATOR_ACTOR                           │ │
│   │   (direct path)          (aggregation path)                           │ │
│   └───────────────────────────────────────────────────────────────────────┘ │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

#### F38: Tool Result → LLM Context Staging Flow

```
┌─────────────────────────────────────────────────────────────────────────────┐
│             F38: TOOL RESULT → LLM CONTEXT STAGING FLOW                     │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│   Results staged in buffer, then included in LLM context                    │
│                                                                             │
│   ┌───────────────────────────────────────────────────────────────────────┐ │
│   │                                                                       │ │
│   │   COMPANIONING                                                        │ │
│   │          │                                                            │ │
│   │   stage tool_result for LLM                                           │ │
│   │          │                                                            │ │
│   │          ▼                                                            │ │
│   │   ┌─────────────────────────────────────────────────────────────┐     │ │
│   │   │              TOOL_RESULT_BUFFER                             │     │ │
│   │   ├─────────────────────────────────────────────────────────────┤     │ │
│   │   │                                                             │     │ │
│   │   │  Stages results for LLM context:                            │     │ │
│   │   │                                                             │     │ │
│   │   │  LOW tier:                                                  │     │ │
│   │   │  • Single tool_result[]                                     │     │ │
│   │   │  • ~500 token budget                                        │     │ │
│   │   │                                                             │     │ │
│   │   │  MEDIUM/HIGH tier:                                          │     │ │
│   │   │  • All tool_results[] from orchestrator                     │     │ │
│   │   │  • 2-8K token budget                                        │     │ │
│   │   │                                                             │     │ │
│   │   └──────────────────┬──────────────────────────────────────────┘     │ │
│   │                      │                                                │ │
│   │            (when DELIVERING state reached)                            │ │
│   │                      │                                                │ │
│   │         ┌────────────┴────────────┐                                   │ │
│   │         ▼                         ▼                                   │ │
│   │   LOW: tool_result[]      MEDIUM/HIGH: all tool_results[]             │ │
│   │         │                         │                                   │ │
│   │         └────────────┬────────────┘                                   │ │
│   │                      │                                                │ │
│   │                      ▼                                                │ │
│   │   ┌─────────────────────────────────────────────────────────────┐     │ │
│   │   │              MODEL_GATEWAY                                  │     │ │
│   │   │                                                             │     │ │
│   │   │  Generate response WITH tool results in context             │     │ │
│   │   │                                                             │     │ │
│   │   └──────────────────┬──────────────────────────────────────────┘     │ │
│   │                      │                                                │ │
│   │              final response                                           │ │
│   │                      │                                                │ │
│   │                      ▼                                                │ │
│   │               DELIVERING ───▶ clear buffer ───▶ LISTENING             │ │
│   └───────────────────────────────────────────────────────────────────────┘ │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

### 3.2 K0 Memory Recall Flow

#### F39: K0 Query Port Recall Flow

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                   F39: K0 QUERY PORT RECALL FLOW                            │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│   Structured recall from K0 memory via Query Port                           │
│                                                                             │
│   ┌───────────────────────────────────────────────────────────────────────┐ │
│   │                                                                       │ │
│   │   ACKING / CLARIFYING                                                 │ │
│   │          │                                                            │ │
│   │   invoke capability: k0.query_recall                                  │ │
│   │          │                                                            │ │
│   │          ▼                                                            │ │
│   │   ┌─────────────────────────────────────────────────────────────┐     │ │
│   │   │           TOOL_INVOKE_CAPABILITY                            │     │ │
│   │   │                     │                                       │     │ │
│   │   │                     ▼                                       │     │ │
│   │   │            K0_GENERIC_CLIENT                                │     │ │
│   │   │                     │                                       │     │ │
│   │   │            generic transport                                │     │ │
│   │   │                     │                                       │     │ │
│   │   │                     ▼                                       │     │ │
│   │   │               PORT_QRY (Query Port)                         │     │ │
│   │   │                     │                                       │     │ │
│   │   │            selector bundle                                  │     │ │
│   │   │                     │                                       │     │ │
│   │   │                     ▼                                       │     │ │
│   │   │               QUERY_AGG (Aggregator)                        │     │ │
│   │   │                     │                                       │     │ │
│   │   │      ┌──────────────┴──────────────┐                        │     │ │
│   │   │      ▼                             ▼                        │     │ │
│   │   │  WAL_DRIVER               VECTOR_DRIVER                     │     │ │
│   │   │  (episodic)               (semantic)                        │     │ │
│   │   │      │                             │                        │     │ │
│   │   │      └──────────────┬──────────────┘                        │     │ │
│   │   │                     ▼                                       │     │ │
│   │   │            TOOL_RECALL_MEMORY                               │     │ │
│   │   │                     │                                       │     │ │
│   │   │             recall bundle                                   │     │ │
│   │   │                     │                                       │     │ │
│   │   │                     ▼                                       │     │ │
│   │   │       CAPABILITY_CONTEXT_BUILDER                            │     │ │
│   │   └─────────────────────────────────────────────────────────────┘     │ │
│   └───────────────────────────────────────────────────────────────────────┘ │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

#### F40: WAL Driver Query Flow

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                      F40: WAL DRIVER QUERY FLOW                             │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│   Write-Ahead Log driver for episodic/sequential memory                     │
│                                                                             │
│   ┌───────────────────────────────────────────────────────────────────────┐ │
│   │                                                                       │ │
│   │   QUERY_AGG                                                           │ │
│   │          │                                                            │ │
│   │    multi-driver query                                                 │ │
│   │          │                                                            │ │
│   │          ▼                                                            │ │
│   │   ┌─────────────────────────────────────────────────────────────┐     │ │
│   │   │                   WAL_DRIVER                                │     │ │
│   │   ├─────────────────────────────────────────────────────────────┤     │ │
│   │   │                                                             │     │ │
│   │   │  Query Types:                                               │     │ │
│   │   │  • Recent turns (last N)                                    │     │ │
│   │   │  • Time-range queries                                       │     │ │
│   │   │  • Entity-filtered sequences                                │     │ │
│   │   │                                                             │     │ │
│   │   │  Storage: HOT_SQLITE (WAL mode, <10ms)                      │     │ │
│   │   │                                                             │     │ │
│   │   └──────────────────┬──────────────────────────────────────────┘     │ │
│   │                      │                                                │ │
│   │            episodic memories                                          │ │
│   │                      │                                                │ │
│   │                      ▼                                                │ │
│   │             TOOL_RECALL_MEMORY                                        │ │
│   └───────────────────────────────────────────────────────────────────────┘ │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

#### F41: Vector Semantic Search Flow

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                   F41: VECTOR SEMANTIC SEARCH FLOW                          │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│   Semantic similarity search via vector embeddings                          │
│                                                                             │
│   ┌───────────────────────────────────────────────────────────────────────┐ │
│   │                                                                       │ │
│   │   QUERY_AGG                                                           │ │
│   │          │                                                            │ │
│   │    semantic search                                                    │ │
│   │          │                                                            │ │
│   │          ▼                                                            │ │
│   │   ┌─────────────────────────────────────────────────────────────┐     │ │
│   │   │                  VECTOR_DRIVER                              │     │ │
│   │   ├─────────────────────────────────────────────────────────────┤     │ │
│   │   │                                                             │     │ │
│   │   │  Operations:                                                │     │ │
│   │   │  • Embed query via P08: Embedding Management                │     │ │
│   │   │  • K-NN search in vector store                              │     │ │
│   │   │  • Filter by metadata (time, domain, entity)                │     │ │
│   │   │                                                             │     │ │
│   │   │  Storage: COLD_DISK (Vector store, <100ms)                  │     │ │
│   │   │                                                             │     │ │
│   │   │  K0 Multi-Store Retrieval:                                  │     │ │
│   │   │  • FTS (Keyword) - exact matches                            │     │ │
│   │   │  • Vector (Semantic) - meaning-based                        │     │ │
│   │   │  • KG (Graph) - relationship traversal                      │     │ │
│   │   │  • Episodic (Sequences) - temporal patterns                 │     │ │
│   │   │                                                             │     │ │
│   │   └──────────────────┬──────────────────────────────────────────┘     │ │
│   │                      │                                                │ │
│   │            semantic matches                                           │ │
│   │                      │                                                │ │
│   │                      ▼                                                │ │
│   │             TOOL_RECALL_MEMORY                                        │ │
│   └───────────────────────────────────────────────────────────────────────┘ │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

#### F42: Context Budget Application Flow

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                 F42: CONTEXT BUDGET APPLICATION FLOW                        │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│   Apply token budget to recalled memories (128K limit)                      │
│                                                                             │
│   ┌───────────────────────────────────────────────────────────────────────┐ │
│   │                                                                       │ │
│   │   QUERY_AGG                                                           │ │
│   │          │                                                            │ │
│   │    return recall bundle                                               │ │
│   │          │                                                            │ │
│   │          ▼                                                            │ │
│   │   ┌─────────────────────────────────────────────────────────────┐     │ │
│   │   │                  CONTEXT_BUDGET                             │     │ │
│   │   ├─────────────────────────────────────────────────────────────┤     │ │
│   │   │                                                             │     │ │
│   │   │  Token Budget: 128K                                         │     │ │
│   │   │                                                             │     │ │
│   │   │  Strategy: recency + relevance                              │     │ │
│   │   │  • Recent items get priority                                │     │ │
│   │   │  • High-relevance items preserved                           │     │ │
│   │   │  • Low-relevance items truncated/dropped                    │     │ │
│   │   │                                                             │     │ │
│   │   │  Budget Allocation:                                         │     │ │
│   │   │  • Tool results: dynamic                                    │     │ │
│   │   │  • SessionState: ~48KB (HOT)                                │     │ │
│   │   │  • Recalled memories: remaining budget                      │     │ │
│   │   │                                                             │     │ │
│   │   └──────────────────┬──────────────────────────────────────────┘     │ │
│   │                      │                                                │ │
│   │          apply token budget                                           │ │
│   │                      │                                                │ │
│   │                      ▼                                                │ │
│   │   ┌─────────────────────────────────────────────────────────────┐     │ │
│   │   │          CAPABILITY_CONTEXT_BUILDER                         │     │ │
│   │   │                                                             │     │ │
│   │   │  Build context: SessionState → Fabric Context               │     │ │
│   │   │  Include: tool results + recalled memories + current state  │     │ │
│   │   │                                                             │     │ │
│   │   └─────────────────────────────────────────────────────────────┘     │ │
│   └───────────────────────────────────────────────────────────────────────┘ │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## 4. ORCHESTRATOR FLOWS

### 4.1 3-Phase Orchestration Flow

#### F43: Task Announcement & Bidding Flow

```
┌─────────────────────────────────────────────────────────────────────────────┐
│               F43: TASK ANNOUNCEMENT & BIDDING FLOW                         │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│   Contract Net Protocol - Phase 1: Negotiation                              │
│                                                                             │
│   ┌───────────────────────────────────────────────────────────────────────┐ │
│   │                                                                       │ │
│   │   ORCHESTRATOR_ACTOR                                                  │ │
│   │          │                                                            │ │
│   │   Capability Invocation                                               │ │
│   │          │                                                            │ │
│   │          ▼                                                            │ │
│   │   ┌─────────────────────────────────────────────────────────────┐     │ │
│   │   │          PHASE1_NEGOTIATION                                 │     │ │
│   │   │          Contract Net Protocol                              │     │ │
│   │   ├─────────────────────────────────────────────────────────────┤     │ │
│   │   │                                                             │     │ │
│   │   │  Step 1: Task Announcement                                  │     │ │
│   │   │  ┌─────────────────────────────────────────────────────┐    │     │ │
│   │   │  │         TASK_ANNOUNCEMENT                           │    │     │ │
│   │   │  │                                                     │    │     │ │
│   │   │  │  Broadcast requirements to potential agents:        │    │     │ │
│   │   │  │  • Task type                                        │    │     │ │
│   │   │  │  • Required capabilities                            │    │     │ │
│   │   │  │  • QoS constraints (latency, cost)                  │    │     │ │
│   │   │  │  • Context requirements                             │    │     │ │
│   │   │  │                                                     │    │     │ │
│   │   │  └──────────────────┬──────────────────────────────────┘    │     │ │
│   │   │                     │                                       │     │ │
│   │   │              Task Announced                                 │     │ │
│   │   │                     │                                       │     │ │
│   │   │                     ▼                                       │     │ │
│   │   │  Step 2: Proposal Bidding                                   │     │ │
│   │   │  ┌─────────────────────────────────────────────────────┐    │     │ │
│   │   │  │          PROPOSAL_BIDDING                           │    │     │ │
│   │   │  │                                                     │    │     │ │
│   │   │  │  Agents respond with proposals:                     │    │     │ │
│   │   │  │  • Can I do this? (capability match)                │    │     │ │
│   │   │  │  • At what cost?                                    │    │     │ │
│   │   │  │  • With what latency?                               │    │     │ │
│   │   │  │  • Confidence level                                 │    │     │ │
│   │   │  │                                                     │    │     │ │
│   │   │  └──────────────────┬──────────────────────────────────┘    │     │ │
│   │   │                     │                                       │     │ │
│   │   │           Proposals Received                                │     │ │
│   │   │                     │                                       │     │ │
│   │   │                     ▼                                       │     │ │
│   │   │           MULTI_CRITERIA_SCORING                            │     │ │
│   │   │                                                             │     │ │
│   │   └─────────────────────────────────────────────────────────────┘     │ │
│   └───────────────────────────────────────────────────────────────────────┘ │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

#### F44: Multi-Criteria Scoring & Selection Flow

```
┌─────────────────────────────────────────────────────────────────────────────┐
│             F44: MULTI-CRITERIA SCORING & SELECTION FLOW                    │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│   Contract Net Protocol - Phase 2: Selection                                │
│                                                                             │
│   ┌───────────────────────────────────────────────────────────────────────┐ │
│   │                                                                       │ │
│   │   PROPOSAL_BIDDING                                                    │ │
│   │          │                                                            │ │
│   │    Proposals Received                                                 │ │
│   │          │                                                            │ │
│   │          ▼                                                            │ │
│   │   ┌─────────────────────────────────────────────────────────────┐     │ │
│   │   │          PHASE2_SELECTION                                   │     │ │
│   │   │          Winner Determination                               │     │ │
│   │   ├─────────────────────────────────────────────────────────────┤     │ │
│   │   │                                                             │     │ │
│   │   │  ┌─────────────────────────────────────────────────────┐    │     │ │
│   │   │  │         MULTI_CRITERIA_SCORING                      │    │     │ │
│   │   │  │                                                     │    │     │ │
│   │   │  │  Scoring Dimensions:                                │    │     │ │
│   │   │  │  ┌──────────────┐ ┌──────────────┐ ┌──────────────┐ │    │     │ │
│   │   │  │  │ Capability   │ │ Latency      │ │ Cost         │ │    │     │ │
│   │   │  │  │ Match (40%)  │ │ Score (30%)  │ │ Score (30%)  │ │    │     │ │
│   │   │  │  └──────────────┘ └──────────────┘ └──────────────┘ │    │     │ │
│   │   │  │                                                     │    │     │ │
│   │   │  │  Additional factors:                                │    │     │ │
│   │   │  │  • Agent specialization                             │    │     │ │
│   │   │  │  • Current load/availability                        │    │     │ │
│   │   │  │  • Historical success rate                          │    │     │ │
│   │   │  │                                                     │    │     │ │
│   │   │  └──────────────────┬──────────────────────────────────┘    │     │ │
│   │   │                     │                                       │     │ │
│   │   │             Winner Selected                                 │     │ │
│   │   │                     │                                       │     │ │
│   │   │                     ▼                                       │     │ │
│   │   │              PARALLEL_DAG                                   │     │ │
│   │   │                                                             │     │ │
│   │   └─────────────────────────────────────────────────────────────┘     │ │
│   └───────────────────────────────────────────────────────────────────────┘ │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

#### F45: Parallel DAG Execution Flow

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                  F45: PARALLEL DAG EXECUTION FLOW                           │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│   Contract Net Protocol - Phase 3: Execution with DAG-based parallelism     │
│                                                                             │
│   ┌───────────────────────────────────────────────────────────────────────┐ │
│   │                                                                       │ │
│   │   MULTI_CRITERIA_SCORING                                              │ │
│   │          │                                                            │ │
│   │     Winner Selected                                                   │ │
│   │          │                                                            │ │
│   │          ▼                                                            │ │
│   │   ┌─────────────────────────────────────────────────────────────┐     │ │
│   │   │          PHASE3_EXECUTION                                   │     │ │
│   │   │          Task Fulfillment                                   │     │ │
│   │   ├─────────────────────────────────────────────────────────────┤     │ │
│   │   │                                                             │     │ │
│   │   │  ┌─────────────────────────────────────────────────────┐    │     │ │
│   │   │  │            PARALLEL_DAG                             │    │     │ │
│   │   │  │       Concurrent Task Execution                     │    │     │ │
│   │   │  │                                                     │    │     │ │
│   │   │  │  Example DAG:                                       │    │     │ │
│   │   │  │                                                     │    │     │ │
│   │   │  │       ┌──────┐         ┌──────┐                     │    │     │ │
│   │   │  │       │Task A│─────────│Task C│                     │    │     │ │
│   │   │  │       └──────┘    ┐    └──────┘                     │    │     │ │
│   │   │  │           │       │        │                        │    │     │ │
│   │   │  │           │       │        │                        │    │     │ │
│   │   │  │       ┌──────┐    │    ┌──────┐                     │    │     │ │
│   │   │  │       │Task B│────┘    │Task D│ (final)             │    │     │ │
│   │   │  │       └──────┘         └──────┘                     │    │     │ │
│   │   │  │                                                     │    │     │ │
│   │   │  │  A & B run in parallel, C waits for A,              │    │     │ │
│   │   │  │  D waits for B & C                                  │    │     │ │
│   │   │  │                                                     │    │     │ │
│   │   │  └──────────────────┬──────────────────────────────────┘    │     │ │
│   │   │                     │                                       │     │ │
│   │   │            Execution Started                                │     │ │
│   │   │                     │                                       │     │ │
│   │   │  ┌──────────────────┴──────────────────┐                    │     │ │
│   │   │  │            DAG_ENGINE               │                    │     │ │
│   │   │  │       Dependency Resolution         │                    │     │ │
│   │   │  │                                     │                    │     │ │
│   │   │  │  • Track task dependencies          │                    │     │ │
│   │   │  │  • Schedule parallel tasks          │                    │     │ │
│   │   │  │  • Handle task failures             │                    │     │ │
│   │   │  └──────────────────┬──────────────────┘                    │     │ │
│   │   │                     │                                       │     │ │
│   │   │                     ▼                                       │     │ │
│   │   │              SAGA_RECOVERY                                  │     │ │
│   │   │                                                             │     │ │
│   │   └─────────────────────────────────────────────────────────────┘     │ │
│   └───────────────────────────────────────────────────────────────────────┘ │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

#### F46: Saga Pattern Recovery Flow

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                   F46: SAGA PATTERN RECOVERY FLOW                           │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│   Compensating transactions for failure recovery                            │
│                                                                             │
│   ┌───────────────────────────────────────────────────────────────────────┐ │
│   │                                                                       │ │
│   │   PARALLEL_DAG                                                        │ │
│   │          │                                                            │ │
│   │    Execution Started                                                  │ │
│   │          │                                                            │ │
│   │          ▼                                                            │ │
│   │   ┌─────────────────────────────────────────────────────────────┐     │ │
│   │   │              SAGA_RECOVERY                                  │     │ │
│   │   │         Compensating Transactions                           │     │ │
│   │   ├─────────────────────────────────────────────────────────────┤     │ │
│   │   │                                                             │     │ │
│   │   │  Normal Flow (Success):                                     │     │ │
│   │   │  T1 → T2 → T3 → T4 → Complete                               │     │ │
│   │   │                                                             │     │ │
│   │   │  Failure at T3:                                             │     │ │
│   │   │  T1 → T2 → T3(FAIL) → C2 → C1 → Rollback Complete           │     │ │
│   │   │                                                             │     │ │
│   │   │  Where Cn = Compensating transaction for Tn                 │     │ │
│   │   │                                                             │     │ │
│   │   │  ┌─────────────────────────────────────────────────────┐    │     │ │
│   │   │  │ Saga State Machine:                                 │    │     │ │
│   │   │  │                                                     │    │     │ │
│   │   │  │   EXECUTING ──▶ SUCCESS                             │    │     │ │
│   │   │  │       │                                             │    │     │ │
│   │   │  │       ▼ (failure)                                   │    │     │ │
│   │   │  │   COMPENSATING ──▶ ROLLED_BACK                      │    │     │ │
│   │   │  │                                                     │    │     │ │
│   │   │  └─────────────────────────────────────────────────────┘    │     │ │
│   │   │                                                             │     │ │
│   │   │  Benefits:                                                  │     │ │
│   │   │  • No distributed locks needed                              │     │ │
│   │   │  • Eventual consistency                                     │     │ │
│   │   │  • Graceful degradation                                     │     │ │
│   │   │                                                             │     │ │
│   │   └─────────────────────────────────────────────────────────────┘     │ │
│   └───────────────────────────────────────────────────────────────────────┘ │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

### 4.2 Constraint Resolution Flow

#### F47: Constraint Manager Iteration Flow

```
┌─────────────────────────────────────────────────────────────────────────────┐
│               F47: CONSTRAINT MANAGER ITERATION FLOW                        │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│   Iterative validation with max 3 cycles before HIL fallback                │
│                                                                             │
│   ┌───────────────────────────────────────────────────────────────────────┐ │
│   │                                                                       │ │
│   │   ACKING                                                              │ │
│   │          │                                                            │ │
│   │   pre_execution_check                                                 │ │
│   │          │                                                            │ │
│   │          ▼                                                            │ │
│   │   ┌─────────────────────────────────────────────────────────────┐     │ │
│   │   │           CONSTRAINT_RESOLUTION_ENGINE                      │     │ │
│   │   │           Iterative Validation & HIL                        │     │ │
│   │   ├─────────────────────────────────────────────────────────────┤     │ │
│   │   │                                                             │     │ │
│   │   │  ┌─────────────────────────────────────────────────────┐    │     │ │
│   │   │  │          CONSTRAINT_MANAGER                         │    │     │ │
│   │   │  │         Oversees Iterative Flow                     │    │     │ │
│   │   │  │                                                     │    │     │ │
│   │   │  │   ┌─────────────────────────────────────────────┐   │    │     │ │
│   │   │  │   │      ITERATION_CONTROLLER                   │   │    │     │ │
│   │   │  │   │           Max 3 Cycles                      │   │    │     │ │
│   │   │  │   │                                             │   │    │     │ │
│   │   │  │   │   Cycle 1: Check constraints                │   │    │     │ │
│   │   │  │   │      │                                      │   │    │     │ │
│   │   │  │   │      ▼ (violations found)                   │   │    │     │ │
│   │   │  │   │   Cycle 2: Attempt resolution               │   │    │     │ │
│   │   │  │   │      │                                      │   │    │     │ │
│   │   │  │   │      ▼ (still violated)                     │   │    │     │ │
│   │   │  │   │   Cycle 3: Final attempt                    │   │    │     │ │
│   │   │  │   │      │                                      │   │    │     │ │
│   │   │  │   │      ▼ (still stuck)                        │   │    │     │ │
│   │   │  │   │   FALLBACK_TRIGGER → HIL                    │   │    │     │ │
│   │   │  │   │                                             │   │    │     │ │
│   │   │  │   └─────────────────────────────────────────────┘   │    │     │ │
│   │   │  │                                                     │    │     │ │
│   │   │  └──────────────────┬──────────────────────────────────┘    │     │ │
│   │   │                     │                                       │     │ │
│   │   │            gaps_found                                       │     │ │
│   │   │                     │                                       │     │ │
│   │   │                     ▼                                       │     │ │
│   │   │                  ACKING                                     │     │ │
│   │   │                                                             │     │ │
│   │   └─────────────────────────────────────────────────────────────┘     │ │
│   └───────────────────────────────────────────────────────────────────────┘ │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

#### F48: Solution Validation Flow (LLM + Rule-Based)

```
┌─────────────────────────────────────────────────────────────────────────────┐
│            F48: SOLUTION VALIDATION FLOW (LLM + Rule-Based)                 │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│   Hybrid validation: deterministic rules + LLM semantic checking            │
│                                                                             │
│   ┌───────────────────────────────────────────────────────────────────────┐ │
│   │                                                                       │ │
│   │   CONSTRAINT_MANAGER                                                  │ │
│   │          │                                                            │ │
│   │   ┌──────┴──────┐                                                     │ │
│   │   │             │                                                     │ │
│   │   ▼             ▼                                                     │ │
│   │   ┌─────────────────────────────────────────────────────────────┐     │ │
│   │   │              SOLUTION_VALIDATOR                             │     │ │
│   │   │              LLM + Rule-Based                               │     │ │
│   │   ├─────────────────────────────────────────────────────────────┤     │ │
│   │   │                                                             │     │ │
│   │   │  ┌─────────────────────┐  ┌─────────────────────────┐       │     │ │
│   │   │  │  RULE-BASED        │  │  LLM SEMANTIC           │       │     │ │
│   │   │  │  (Fast, ~1ms)      │  │  (Slower, ~100ms)       │       │     │ │
│   │   │  │                    │  │                         │       │     │ │
│   │   │  │  • Type checking   │  │  • Context coherence    │       │     │ │
│   │   │  │  • Range bounds    │  │  • Intent alignment     │       │     │ │
│   │   │  │  • Required fields │  │  • Ambiguity detection  │       │     │ │
│   │   │  │  • Format patterns │  │  • Conflict resolution  │       │     │ │
│   │   │  │                    │  │                         │       │     │ │
│   │   │  └─────────┬──────────┘  └───────────┬─────────────┘       │     │ │
│   │   │            │                         │                      │     │ │
│   │   │            └────────────┬────────────┘                      │     │ │
│   │   │                         │                                   │     │ │
│   │   │                         ▼                                   │     │ │
│   │   │                ┌─────────────────┐                          │     │ │
│   │   │                │ Combined Verdict │                          │     │ │
│   │   │                │                 │                          │     │ │
│   │   │                │ VALID / INVALID │                          │     │ │
│   │   │                │ + reasons       │                          │     │ │
│   │   │                └─────────────────┘                          │     │ │
│   │   │                                                             │     │ │
│   │   └─────────────────────────────────────────────────────────────┘     │ │
│   └───────────────────────────────────────────────────────────────────────┘ │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

#### F49: Constraint HIL Fallback Flow

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                 F49: CONSTRAINT HIL FALLBACK FLOW                           │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│   Human-in-the-Loop when automated resolution fails                         │
│                                                                             │
│   ┌───────────────────────────────────────────────────────────────────────┐ │
│   │                                                                       │ │
│   │   ITERATION_CONTROLLER (Cycle 3 exhausted)                            │ │
│   │          │                                                            │ │
│   │   still stuck                                                         │ │
│   │          │                                                            │ │
│   │          ▼                                                            │ │
│   │   ┌─────────────────────────────────────────────────────────────┐     │ │
│   │   │              FALLBACK_TRIGGER                               │     │ │
│   │   │              → HIL when stuck                               │     │ │
│   │   ├─────────────────────────────────────────────────────────────┤     │ │
│   │   │                                                             │     │ │
│   │   │  Triggers Human-in-the-Loop:                                │     │ │
│   │   │                                                             │     │ │
│   │   │  1. Package unresolved constraints                          │     │ │
│   │   │  2. Generate user-friendly explanation                      │     │ │
│   │   │  3. Present options to user                                 │     │ │
│   │   │  4. Await user decision                                     │     │ │
│   │   │                                                             │     │ │
│   │   │  Example:                                                   │     │ │
│   │   │  "I found two doctors named Smith. Did you mean:            │     │ │
│   │   │   A) Dr. John Smith (cardiologist)                          │     │ │
│   │   │   B) Dr. Jane Smith (dermatologist)"                        │     │ │
│   │   │                                                             │     │ │
│   │   └──────────────────┬──────────────────────────────────────────┘     │ │
│   │                      │                                                │ │
│   │             HIL request                                               │ │
│   │                      │                                                │ │
│   │                      ▼                                                │ │
│   │   ┌─────────────────────────────────────────────────────────────┐     │ │
│   │   │             PLANNER_HIL Integration                         │     │ │
│   │   │                                                             │     │ │
│   │   │  • REQUIREMENT_CLARIFICATION                                │     │ │
│   │   │  • PLAN_APPROVAL                                            │     │ │
│   │   │  • EXECUTION_MONITORING                                     │     │ │
│   │   │                                                             │     │ │
│   │   └─────────────────────────────────────────────────────────────┘     │ │
│   └───────────────────────────────────────────────────────────────────────┘ │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

### 4.3 Workflow System Flows

#### F50: Workflow Scheduling & Trigger Flow

```
┌─────────────────────────────────────────────────────────────────────────────┐
│               F50: WORKFLOW SCHEDULING & TRIGGER FLOW                       │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│   Time/Event/Proactive workflow triggers                                    │
│                                                                             │
│   ┌───────────────────────────────────────────────────────────────────────┐ │
│   │                                                                       │ │
│   │   ┌─────────────────────────────────────────────────────────────┐     │ │
│   │   │              WORKFLOW_REGISTRY                              │     │ │
│   │   │         Stores WorkflowSpec + TriggerSpec                   │     │ │
│   │   │                                                             │     │ │
│   │   │  WorkflowSpec:                                              │     │ │
│   │   │  • name: "morning_routine"                                  │     │ │
│   │   │  • steps: [check_weather, check_calendar, summarize]        │     │ │
│   │   │                                                             │     │ │
│   │   │  TriggerSpec:                                               │     │ │
│   │   │  • type: time | event | proactive                           │     │ │
│   │   │  • condition: "6:30 AM" | "location=home" | ...             │     │ │
│   │   │                                                             │     │ │
│   │   └──────────────────┬──────────────────────────────────────────┘     │ │
│   │                      │                                                │ │
│   │              workflow definitions                                     │ │
│   │                      │                                                │ │
│   │                      ▼                                                │ │
│   │   ┌─────────────────────────────────────────────────────────────┐     │ │
│   │   │              WORKFLOW_SCHEDULER                             │     │ │
│   │   │         Time/Event/Proactive Triggers                       │     │ │
│   │   ├─────────────────────────────────────────────────────────────┤     │ │
│   │   │                                                             │     │ │
│   │   │  Trigger Types:                                             │     │ │
│   │   │  ┌──────────────┐ ┌──────────────┐ ┌──────────────┐         │     │ │
│   │   │  │ TIME         │ │ EVENT        │ │ PROACTIVE    │         │     │ │
│   │   │  │              │ │              │ │              │         │     │ │
│   │   │  │ Cron-like    │ │ On event     │ │ AI-initiated │         │     │ │
│   │   │  │ scheduling   │ │ detection    │ │ (predictive) │         │     │ │
│   │   │  └──────────────┘ └──────────────┘ └──────────────┘         │     │ │
│   │   │                                                             │     │ │
│   │   └──────────────────┬──────────────────────────────────────────┘     │ │
│   │                      │                                                │ │
│   │             trigger fired                                             │ │
│   │                      │                                                │ │
│   │                      ▼                                                │ │
│   │             WORKFLOW_RUN_SUPERVISOR                                   │ │
│   └───────────────────────────────────────────────────────────────────────┘ │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

#### F51: Workflow Run Supervisor Flow

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                  F51: WORKFLOW RUN SUPERVISOR FLOW                          │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│   Leases + Guards + Lifecycle management                                    │
│                                                                             │
│   ┌───────────────────────────────────────────────────────────────────────┐ │
│   │                                                                       │ │
│   │   WORKFLOW_SCHEDULER                                                  │ │
│   │          │                                                            │ │
│   │    trigger fired                                                      │ │
│   │          │                                                            │ │
│   │          ▼                                                            │ │
│   │   ┌─────────────────────────────────────────────────────────────┐     │ │
│   │   │           WORKFLOW_RUN_SUPERVISOR                           │     │ │
│   │   │          Leases + Guards + Lifecycle                        │     │ │
│   │   ├─────────────────────────────────────────────────────────────┤     │ │
│   │   │                                                             │     │ │
│   │   │  1. Create Run Manifest:                                    │     │ │
│   │   │     ┌─────────────────────────────────────────────────┐     │     │ │
│   │   │     │           RUN_MANIFEST                          │     │     │ │
│   │   │     │                                                 │     │     │ │
│   │   │     │  • Pinned Version (immutable during run)        │     │     │ │
│   │   │     │  • Compiled Hash (integrity check)              │     │     │ │
│   │   │     │  • Run ID (unique identifier)                   │     │     │ │
│   │   │     │                                                 │     │     │ │
│   │   │     └─────────────────────────────────────────────────┘     │     │ │
│   │   │                                                             │     │ │
│   │   │  2. Acquire Leases (prevent concurrent runs)                │     │ │
│   │   │                                                             │     │ │
│   │   │  3. Set up Guards (timeout, resource limits)                │     │ │
│   │   │                                                             │     │ │
│   │   │  4. Execute Lifecycle:                                      │     │ │
│   │   │     STARTING → RUNNING → COMPLETING → COMPLETED             │     │ │
│   │   │                    ↓                                        │     │ │
│   │   │               FAILED (if error)                             │     │ │
│   │   │                                                             │     │ │
│   │   └──────────────────┬──────────────────────────────────────────┘     │ │
│   │                      │                                                │ │
│   │             compiled workflow                                         │ │
│   │                      │                                                │ │
│   │                      ▼                                                │ │
│   │             CAPABILITY_FABRIC (execution)                             │ │
│   └───────────────────────────────────────────────────────────────────────┘ │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

#### F52: Workflow Compiler → DAG Flow

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                  F52: WORKFLOW COMPILER → DAG FLOW                          │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│   Intent → Capability DAG compilation                                       │
│                                                                             │
│   ┌───────────────────────────────────────────────────────────────────────┐ │
│   │                                                                       │ │
│   │   User Intent / Workflow Definition                                   │ │
│   │          │                                                            │ │
│   │          ▼                                                            │ │
│   │   ┌─────────────────────────────────────────────────────────────┐     │ │
│   │   │              WORKFLOW_COMPILER                              │     │ │
│   │   │           Intent → Capability DAG                           │     │ │
│   │   ├─────────────────────────────────────────────────────────────┤     │ │
│   │   │                                                             │     │ │
│   │   │  Input: "When I say 'good morning', check weather,          │     │ │
│   │   │         show calendar, and play my morning playlist"        │     │ │
│   │   │                                                             │     │ │
│   │   │  Compilation Steps:                                         │     │ │
│   │   │  1. Parse intent into atomic operations                     │     │ │
│   │   │  2. Map operations to capabilities                          │     │ │
│   │   │  3. Resolve dependencies                                    │     │ │
│   │   │  4. Optimize for parallelism                                │     │ │
│   │   │                                                             │     │ │
│   │   │  Output: Capability DAG                                     │     │ │
│   │   │  ┌─────────────────────────────────────────────────────┐    │     │ │
│   │   │  │       ┌────────────┐                                │    │     │ │
│   │   │  │       │ get_weather│────┐                           │    │     │ │
│   │   │  │       └────────────┘    │                           │    │     │ │
│   │   │  │                         │   ┌────────────────┐      │    │     │ │
│   │   │  │       ┌────────────┐    ├──▶│ summarize_all  │      │    │     │ │
│   │   │  │       │get_calendar│────┤   └────────────────┘      │    │     │ │
│   │   │  │       └────────────┘    │                           │    │     │ │
│   │   │  │                         │                           │    │     │ │
│   │   │  │       ┌────────────┐────┘                           │    │     │ │
│   │   │  │       │play_music  │ (parallel, no deps)            │    │     │ │
│   │   │  │       └────────────┘                                │    │     │ │
│   │   │  └─────────────────────────────────────────────────────┘    │     │ │
│   │   │                                                             │     │ │
│   │   └──────────────────┬──────────────────────────────────────────┘     │ │
│   │                      │                                                │ │
│   │             Capability DAG                                            │ │
│   │                      │                                                │ │
│   │                      ▼                                                │ │
│   │             CAPABILITY_FABRIC (execution)                             │ │
│   └───────────────────────────────────────────────────────────────────────┘ │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

- [ ] **F52: Workflow Compiler → DAG Flow**

---

## 5. PLANNER FLOWS

### 5.1 4-Stage Planning Pipeline

#### F53: Stage 1 - Sketch Plan Flow

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                    F53: STAGE 1 - SKETCH PLAN FLOW                          │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│   LLM-Powered Plan Sketching - high-level outline                           │
│   ADR-0007: 4-Stage Planning Pipeline                                       │
│                                                                             │
│   ┌───────────────────────────────────────────────────────────────────────┐ │
│   │                                                                       │ │
│   │   ORCHESTRATOR_ACTOR                                                  │ │
│   │          │                                                            │ │
│   │   complex task (HIGH tier)                                            │ │
│   │          │                                                            │ │
│   │          ▼                                                            │ │
│   │   ┌─────────────────────────────────────────────────────────────┐     │ │
│   │   │              PLANNER_AGENT                                  │     │ │
│   │   │         LLM-Powered Planning                                │     │ │
│   │   │         4-Stage Pipeline                                    │     │ │
│   │   ├─────────────────────────────────────────────────────────────┤     │ │
│   │   │                                                             │     │ │
│   │   │  via PLANNER_MAILBOX (WFQ Priority: INTERACTIVE)            │     │ │
│   │   │                                                             │     │ │
│   │   └──────────────────┬──────────────────────────────────────────┘     │ │
│   │                      │                                                │ │
│   │                      ▼                                                │ │
│   │   ┌─────────────────────────────────────────────────────────────┐     │ │
│   │   │              STAGE1_SKETCH                                  │     │ │
│   │   │         LLM-Powered Plan Sketching                          │     │ │
│   │   ├─────────────────────────────────────────────────────────────┤     │ │
│   │   │                                                             │     │ │
│   │   │  Input:                                                     │     │ │
│   │   │  • User intent (from UltraBERT)                             │     │ │
│   │   │  • Context (SessionState snapshot)                          │     │ │
│   │   │  • Constraints (time, resources, safety)                    │     │ │
│   │   │                                                             │     │ │
│   │   │  LLM Task:                                                  │     │ │
│   │   │  "Break down this request into logical steps"               │     │ │
│   │   │                                                             │     │ │
│   │   │  Output: Plan Sketch                                        │     │ │
│   │   │  {                                                          │     │ │
│   │   │    "goal": "Schedule doctor and update budget",             │     │ │
│   │   │    "steps": [                                               │     │ │
│   │   │      {"id": 1, "action": "find_available_slots"},           │     │ │
│   │   │      {"id": 2, "action": "book_appointment"},               │     │ │
│   │   │      {"id": 3, "action": "update_budget"}                   │     │ │
│   │   │    ],                                                       │     │ │
│   │   │    "dependencies": [[1,2], [2,3]]                           │     │ │
│   │   │  }                                                          │     │ │
│   │   │                                                             │     │ │
│   │   └──────────────────┬──────────────────────────────────────────┘     │ │
│   │                      │                                                │ │
│   │              plan sketch                                              │ │
│   │                      │                                                │ │
│   │                      ▼                                                │ │
│   │               STAGE2_EXPAND                                           │ │
│   └───────────────────────────────────────────────────────────────────────┘ │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

#### F54: Stage 2 - Expand with Tools Flow

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                  F54: STAGE 2 - EXPAND WITH TOOLS FLOW                      │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│   Map sketch steps to specific tools and generate prompts                   │
│                                                                             │
│   ┌───────────────────────────────────────────────────────────────────────┐ │
│   │                                                                       │ │
│   │   STAGE1_SKETCH                                                       │ │
│   │          │                                                            │ │
│   │    plan sketch                                                        │ │
│   │          │                                                            │ │
│   │          ▼                                                            │ │
│   │   ┌─────────────────────────────────────────────────────────────┐     │ │
│   │   │              STAGE2_EXPAND                                  │     │ │
│   │   │         Tool Selection & Prompts                            │     │ │
│   │   ├─────────────────────────────────────────────────────────────┤     │ │
│   │   │                                                             │     │ │
│   │   │  For each step in sketch:                                   │     │ │
│   │   │                                                             │     │ │
│   │   │  1. Query CAPABILITY_REGISTRY                               │     │ │
│   │   │     "What tools can do 'find_available_slots'?"             │     │ │
│   │   │                                                             │     │ │
│   │   │  2. Select best tool (QoS + capability match)               │     │ │
│   │   │                                                             │     │ │
│   │   │  3. Generate tool invocation prompt                         │     │ │
│   │   │                                                             │     │ │
│   │   │  Output: Expanded Plan                                      │     │ │
│   │   │  {                                                          │     │ │
│   │   │    "steps": [                                               │     │ │
│   │   │      {                                                      │     │ │
│   │   │        "id": 1,                                             │     │ │
│   │   │        "tool": "calendar.query_availability",               │     │ │
│   │   │        "params": {"provider": "Dr. Smith", "days": 7},      │     │ │
│   │   │        "prompt": "Find next 7 days availability..."         │     │ │
│   │   │      },                                                     │     │ │
│   │   │      ...                                                    │     │ │
│   │   │    ]                                                        │     │ │
│   │   │  }                                                          │     │ │
│   │   │                                                             │     │ │
│   │   └──────────────────┬──────────────────────────────────────────┘     │ │
│   │                      │                                                │ │
│   │            expanded plan                                              │ │
│   │                      │                                                │ │
│   │                      ▼                                                │ │
│   │              STAGE3_VALIDATE                                          │ │
│   └───────────────────────────────────────────────────────────────────────┘ │
│                                                                             │
│   Queries: CAPABILITY_REGISTRY for tool discovery                           │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

#### F55: Stage 3 - Validation Flow

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                    F55: STAGE 3 - VALIDATION FLOW                           │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│   Rule-Based + Arbiter Validation before execution                          │
│                                                                             │
│   ┌───────────────────────────────────────────────────────────────────────┐ │
│   │                                                                       │ │
│   │   STAGE2_EXPAND                                                       │ │
│   │          │                                                            │ │
│   │    expanded plan                                                      │ │
│   │          │                                                            │ │
│   │          ▼                                                            │ │
│   │   ┌─────────────────────────────────────────────────────────────┐     │ │
│   │   │              STAGE3_VALIDATE                                │     │ │
│   │   │         Rule-Based + Arbiter Validation                     │     │ │
│   │   ├─────────────────────────────────────────────────────────────┤     │ │
│   │   │                                                             │     │ │
│   │   │  Validation Layers:                                         │     │ │
│   │   │                                                             │     │ │
│   │   │  ┌─────────────────────────────────────────────────────┐    │     │ │
│   │   │  │ RULE-BASED CHECKS (Fast, <5ms)                      │    │     │ │
│   │   │  │                                                     │    │     │ │
│   │   │  │ • Tool exists in registry                           │    │     │ │
│   │   │  │ • Parameters match schema                           │    │     │ │
│   │   │  │ • Dependencies are valid                            │    │     │ │
│   │   │  │ • No circular dependencies                          │    │     │ │
│   │   │  │ • Safety band allows operation                      │    │     │ │
│   │   │  └─────────────────────────────────────────────────────┘    │     │ │
│   │   │                      │                                      │     │ │
│   │   │                      ▼                                      │     │ │
│   │   │  ┌─────────────────────────────────────────────────────┐    │     │ │
│   │   │  │ ARBITER VALIDATION (LLM, ~100ms)                    │    │     │ │
│   │   │  │                                                     │    │     │ │
│   │   │  │ • Plan coherence check                              │    │     │ │
│   │   │  │ • Intent alignment verification                     │    │     │ │
│   │   │  │ • Edge case detection                               │    │     │ │
│   │   │  │ • User safety review                                │    │     │ │
│   │   │  └─────────────────────────────────────────────────────┘    │     │ │
│   │   │                                                             │     │ │
│   │   │  Output: Validation Result                                  │     │ │
│   │   │  { valid: true/false, issues: [], warnings: [] }            │     │ │
│   │   │                                                             │     │ │
│   │   └──────────────────┬──────────────────────────────────────────┘     │ │
│   │                      │                                                │ │
│   │         ┌────────────┴────────────┐                                   │ │
│   │         ▼                         ▼                                   │ │
│   │      VALID                     INVALID                                │ │
│   │         │                         │                                   │ │
│   │         ▼                         ▼                                   │ │
│   │   STAGE4_COMMIT            PLANNER_HIL                                │ │
│   │                        (clarification needed)                         │ │
│   └───────────────────────────────────────────────────────────────────────┘ │
│                                                                             │
│   Also receives: early_validation from ACKING (pre-flight check)            │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

#### F56: Stage 4 - Commit to K0 Flow

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                   F56: STAGE 4 - COMMIT TO K0 FLOW                          │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│   Plan Persistence to K0 WAL for durability and replay                      │
│                                                                             │
│   ┌───────────────────────────────────────────────────────────────────────┐ │
│   │                                                                       │ │
│   │   STAGE3_VALIDATE (valid=true)                                        │ │
│   │          │                                                            │ │
│   │    validated plan                                                     │ │
│   │          │                                                            │ │
│   │          ▼                                                            │ │
│   │   ┌─────────────────────────────────────────────────────────────┐     │ │
│   │   │              STAGE4_COMMIT                                  │     │ │
│   │   │         Plan Persistence to K0 WAL                          │     │ │
│   │   ├─────────────────────────────────────────────────────────────┤     │ │
│   │   │                                                             │     │ │
│   │   │  1. Assign Plan ID (unique, immutable)                      │     │ │
│   │   │                                                             │     │ │
│   │   │  2. Create Plan Record:                                     │     │ │
│   │   │     {                                                       │     │ │
│   │   │       "plan_id": "plan_2024_01_15_001",                     │     │ │
│   │   │       "user_intent": <original>,                            │     │ │
│   │   │       "steps": <expanded>,                                  │     │ │
│   │   │       "validation": <results>,                              │     │ │
│   │   │       "created_at": <timestamp>,                            │     │ │
│   │   │       "status": "COMMITTED"                                 │     │ │
│   │   │     }                                                       │     │ │
│   │   │                                                             │     │ │
│   │   │  3. Write to K0 WAL (durable)                               │     │ │
│   │   │                                                             │     │ │
│   │   └──────────────────┬──────────────────────────────────────────┘     │ │
│   │                      │                                                │ │
│   │            plan committed                                             │ │
│   │                      │                                                │ │
│   │                      ▼                                                │ │
│   │   ┌─────────────────────────────────────────────────────────────┐     │ │
│   │   │              K0_K1_BRIDGE                                   │     │ │
│   │   │                     │                                       │     │ │
│   │   │                     ▼                                       │     │ │
│   │   │              P02: Episodic Write                            │     │ │
│   │   │                     │                                       │     │ │
│   │   │              Plan stored in K0 WAL                          │     │ │
│   │   └─────────────────────────────────────────────────────────────┘     │ │
│   │                      │                                                │ │
│   │                      ▼                                                │ │
│   │         ORCHESTRATOR_ACTOR (begin execution)                          │ │
│   └───────────────────────────────────────────────────────────────────────┘ │
│                                                                             │
│   Benefits:                                                                 │
│   • Plan replay on failure                                                  │
│   • Audit trail for all plans                                               │
│   • Cross-session plan resumption                                           │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

### 5.2 Planner HIL Integration

#### F57: Requirement Clarification HIL Flow

```
┌─────────────────────────────────────────────────────────────────────────────┐
│              F57: REQUIREMENT CLARIFICATION HIL FLOW                        │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│   Human-in-the-Loop when plan requirements are ambiguous                    │
│                                                                             │
│   ┌───────────────────────────────────────────────────────────────────────┐ │
│   │                                                                       │ │
│   │   STAGE1_SKETCH or STAGE3_VALIDATE                                    │ │
│   │          │                                                            │ │
│   │   ambiguity detected / validation failed                              │ │
│   │          │                                                            │ │
│   │          ▼                                                            │ │
│   │   ┌─────────────────────────────────────────────────────────────┐     │ │
│   │   │           REQUIREMENT_CLARIFICATION                         │     │ │
│   │   │           (PLANNER_HIL)                                     │     │ │
│   │   ├─────────────────────────────────────────────────────────────┤     │ │
│   │   │                                                             │     │ │
│   │   │  Triggers:                                                  │     │ │
│   │   │  • Ambiguous scope ("schedule something")                   │     │ │
│   │   │  • Missing constraints ("when?", "with whom?")              │     │ │
│   │   │  • Conflicting requirements                                 │     │ │
│   │   │                                                             │     │ │
│   │   │  Process:                                                   │     │ │
│   │   │  1. Generate clarification questions                        │     │ │
│   │   │  2. Route to CLARIFYING state (via Concierge)               │     │ │
│   │   │  3. Present to user naturally                               │     │ │
│   │   │  4. Collect response                                        │     │ │
│   │   │  5. Update plan context                                     │     │ │
│   │   │  6. Resume pipeline                                         │     │ │
│   │   │                                                             │     │ │
│   │   │  Example:                                                   │     │ │
│   │   │  "You mentioned scheduling a meeting. Should I:             │     │ │
│   │   │   A) Find the next available slot?                          │     │ │
│   │   │   B) Look for a specific time you prefer?"                  │     │ │
│   │   │                                                             │     │ │
│   │   └──────────────────┬──────────────────────────────────────────┘     │ │
│   │                      │                                                │ │
│   │            clarification request                                      │ │
│   │                      │                                                │ │
│   │                      ▼                                                │ │
│   │   ┌─────────────────────────────────────────────────────────────┐     │ │
│   │   │  CONCIERGE_FSM → CLARIFYING → user → response               │     │ │
│   │   │         │                                                   │     │ │
│   │   │         ▼                                                   │     │ │
│   │   │  Resume: STAGE1_SKETCH (with clarified context)             │     │ │
│   │   └─────────────────────────────────────────────────────────────┘     │ │
│   └───────────────────────────────────────────────────────────────────────┘ │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

#### F58: Plan Approval HIL Flow

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                   F58: PLAN APPROVAL HIL FLOW                               │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│   User approval for high-impact or irreversible plans                       │
│                                                                             │
│   ┌───────────────────────────────────────────────────────────────────────┐ │
│   │                                                                       │ │
│   │   STAGE3_VALIDATE (valid but high-impact)                             │ │
│   │          │                                                            │ │
│   │   requires_approval = true                                            │ │
│   │          │                                                            │ │
│   │          ▼                                                            │ │
│   │   ┌─────────────────────────────────────────────────────────────┐     │ │
│   │   │              PLAN_APPROVAL                                  │     │ │
│   │   │              (PLANNER_HIL)                                  │     │ │
│   │   ├─────────────────────────────────────────────────────────────┤     │ │
│   │   │                                                             │     │ │
│   │   │  Triggers (require explicit approval):                      │     │ │
│   │   │  • Financial transactions above threshold                   │     │ │
│   │   │  • Sending messages to contacts                             │     │ │
│   │   │  • Deleting or modifying data                               │     │ │
│   │   │  • External API calls with side effects                     │     │ │
│   │   │                                                             │     │ │
│   │   │  Approval Request:                                          │     │ │
│   │   │  ┌─────────────────────────────────────────────────────┐    │     │ │
│   │   │  │ "I'm about to do the following:                     │    │     │ │
│   │   │  │                                                     │    │     │ │
│   │   │  │  1. Book appointment with Dr. Smith (Tue 3pm)       │    │     │ │
│   │   │  │  2. Add $150 to Health budget                       │    │     │ │
│   │   │  │  3. Send calendar invite to your email              │    │     │ │
│   │   │  │                                                     │    │     │ │
│   │   │  │ [Approve] [Modify] [Cancel]"                        │    │     │ │
│   │   │  └─────────────────────────────────────────────────────┘    │     │ │
│   │   │                                                             │     │ │
│   │   └──────────────────┬──────────────────────────────────────────┘     │ │
│   │                      │                                                │ │
│   │         ┌────────────┼────────────┐                                   │ │
│   │         ▼            ▼            ▼                                   │ │
│   │     APPROVED      MODIFY       CANCEL                                 │ │
│   │         │            │            │                                   │ │
│   │         ▼            ▼            ▼                                   │ │
│   │   STAGE4_COMMIT  STAGE1    LISTENING                                  │ │
│   │   (execute)      (re-plan) (abort)                                    │ │
│   └───────────────────────────────────────────────────────────────────────┘ │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

#### F59: Execution Monitoring HIL Flow

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                F59: EXECUTION MONITORING HIL FLOW                           │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│   Human oversight during plan execution for critical steps                  │
│                                                                             │
│   ┌───────────────────────────────────────────────────────────────────────┐ │
│   │                                                                       │ │
│   │   ORCHESTRATOR_ACTOR (executing plan)                                 │ │
│   │          │                                                            │ │
│   │   step marked: requires_monitoring = true                             │ │
│   │          │                                                            │ │
│   │          ▼                                                            │ │
│   │   ┌─────────────────────────────────────────────────────────────┐     │ │
│   │   │            EXECUTION_MONITORING                             │     │ │
│   │   │            (PLANNER_HIL)                                    │     │ │
│   │   ├─────────────────────────────────────────────────────────────┤     │ │
│   │   │                                                             │     │ │
│   │   │  Monitoring Modes:                                          │     │ │
│   │   │                                                             │     │ │
│   │   │  1. PROGRESS UPDATES (passive)                              │     │ │
│   │   │     "Step 2 of 4 complete: Appointment booked"              │     │ │
│   │   │                                                             │     │ │
│   │   │  2. CHECKPOINT CONFIRMATION (active)                        │     │ │
│   │   │     "Ready to proceed with payment. Continue?"              │     │ │
│   │   │                                                             │     │ │
│   │   │  3. ERROR INTERVENTION (reactive)                           │     │ │
│   │   │     "Step failed: Calendar unavailable.                     │     │ │
│   │   │      [Retry] [Skip] [Abort]"                                │     │ │
│   │   │                                                             │     │ │
│   │   │  Integration with FSM:                                      │     │ │
│   │   │  • PROGRESSING state streams updates                        │     │ │
│   │   │  • COMPANIONING keeps user informed                         │     │ │
│   │   │  • INTERRUPT_HANDLING for user interventions                │     │ │
│   │   │                                                             │     │ │
│   │   └──────────────────┬──────────────────────────────────────────┘     │ │
│   │                      │                                                │ │
│   │         ┌────────────┴────────────┐                                   │ │
│   │         ▼                         ▼                                   │ │
│   │   user: continue           user: intervene                            │ │
│   │         │                         │                                   │ │
│   │         ▼                         ▼                                   │ │
│   │   next step              INTERRUPT_HANDLING                           │ │
│   │                          (pause/modify/abort)                         │ │
│   └───────────────────────────────────────────────────────────────────────┘ │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## 6. SUB-AGENT FLOWS

### 6.1 Agent Lifecycle FSM Flow

#### F60: Agent Spawn via Fabric Flow

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                   F60: AGENT SPAWN VIA FABRIC FLOW                          │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│   Template-based agent creation via Capability Fabric                       │
│   ADR-0005: Agent Lifecycle FSM                                             │
│                                                                             │
│   ┌───────────────────────────────────────────────────────────────────────┐ │
│   │                                                                       │ │
│   │   ORCHESTRATOR_ACTOR or TOOL_SPAWN_VIA_FABRIC                         │ │
│   │          │                                                            │ │
│   │   Agent Spawning request                                              │ │
│   │          │                                                            │ │
│   │          ▼                                                            │ │
│   │   ┌─────────────────────────────────────────────────────────────┐     │ │
│   │   │              CAPABILITY_FABRIC                              │     │ │
│   │   │                     │                                       │     │ │
│   │   │            Spawn Agents                                     │     │ │
│   │   │                     │                                       │     │ │
│   │   │                     ▼                                       │     │ │
│   │   │              AGENT_PROVIDERS                                │     │ │
│   │   │         (58+ Agent Types as Capabilities)                   │     │ │
│   │   │                     │                                       │     │ │
│   │   │            Instantiate                                      │     │ │
│   │   │                     │                                       │     │ │
│   │   │                     ▼                                       │     │ │
│   │   │              AGENT_FACTORY                                  │     │ │
│   │   │         Creates from YAML templates                         │     │ │
│   │   └──────────────────┬──────────────────────────────────────────┘     │ │
│   │                      │                                                │ │
│   │             lookup template                                           │ │
│   │                      │                                                │ │
│   │                      ▼                                                │ │
│   │   ┌─────────────────────────────────────────────────────────────┐     │ │
│   │   │              AGENT_TEMPLATES                                │     │ │
│   │   │         (health_agent.yaml, finance_agent.yaml, ...)        │     │ │
│   │   ├─────────────────────────────────────────────────────────────┤     │ │
│   │   │                                                             │     │ │
│   │   │  Template Structure:                                        │     │ │
│   │   │  name: health_agent                                         │     │ │
│   │   │  capabilities:                                              │     │ │
│   │   │    - health.query_records                                   │     │ │
│   │   │    - health.schedule_appointment                            │     │ │
│   │   │  mailbox_priority: INTERACTIVE                              │     │ │
│   │   │  model: gpt-4o-mini                                         │     │ │
│   │   │  idle_ttl: 60s                                              │     │ │
│   │   │                                                             │     │ │
│   │   └──────────────────┬──────────────────────────────────────────┘     │ │
│   │                      │                                                │ │
│   │            create instance                                            │ │
│   │                      │                                                │ │
│   │                      ▼                                                │ │
│   │   ┌─────────────────────────────────────────────────────────────┐     │ │
│   │   │  DYNAMIC_INSTANCES → STATE_PENDING → Lifecycle FSM begins   │     │ │
│   │   └─────────────────────────────────────────────────────────────┘     │ │
│   └───────────────────────────────────────────────────────────────────────┘ │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

#### F61: PENDING → WARMING → ACTIVE Flow

```
┌─────────────────────────────────────────────────────────────────────────────┐
│               F61: PENDING → WARMING → ACTIVE FLOW                          │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│   Agent startup sequence with model preloading                              │
│                                                                             │
│   ┌───────────────────────────────────────────────────────────────────────┐ │
│   │                       AGENT LIFECYCLE FSM                             │ │
│   │                                                                       │ │
│   │   ┌─────────────────────────────────────────────────────────────┐     │ │
│   │   │              STATE_PENDING                                  │     │ │
│   │   │              Agent Created                                  │     │ │
│   │   ├─────────────────────────────────────────────────────────────┤     │ │
│   │   │                                                             │     │ │
│   │   │  • Agent instantiated from template                         │     │ │
│   │   │  • Configuration loaded                                     │     │ │
│   │   │  • Mailbox allocated                                        │     │ │
│   │   │  • Resources reserved (not initialized)                     │     │ │
│   │   │                                                             │     │ │
│   │   └──────────────────┬──────────────────────────────────────────┘     │ │
│   │                      │                                                │ │
│   │            Supervisor Hire                                            │ │
│   │                      │                                                │ │
│   │                      ▼                                                │ │
│   │   ┌─────────────────────────────────────────────────────────────┐     │ │
│   │   │              STATE_WARMING                                  │     │ │
│   │   │              Model Preloading                               │     │ │
│   │   ├─────────────────────────────────────────────────────────────┤     │ │
│   │   │                                                             │     │ │
│   │   │  • Load model weights (NPU→GPU→CPU→Remote cascade)          │     │ │
│   │   │  • Initialize inference session                             │     │ │
│   │   │  • Warm up cache                                            │     │ │
│   │   │  • Validate connectivity                                    │     │ │
│   │   │                                                             │     │ │
│   │   │  MODEL_INFERENCE cascade:                                   │     │ │
│   │   │  ┌─────┐   ┌─────┐   ┌─────┐   ┌────────┐                   │     │ │
│   │   │  │ NPU │ → │ GPU │ → │ CPU │ → │ Remote │                   │     │ │
│   │   │  └─────┘   └─────┘   └─────┘   └────────┘                   │     │ │
│   │   │  (try each, use first available)                            │     │ │
│   │   │                                                             │     │ │
│   │   └──────────────────┬──────────────────────────────────────────┘     │ │
│   │                      │                                                │ │
│   │            Model Ready                                                │ │
│   │                      │                                                │ │
│   │                      ▼                                                │ │
│   │   ┌─────────────────────────────────────────────────────────────┐     │ │
│   │   │              STATE_ACTIVE                                   │     │ │
│   │   │              Processing Messages                            │     │ │
│   │   ├─────────────────────────────────────────────────────────────┤     │ │
│   │   │                                                             │     │ │
│   │   │  • Accepting tasks from mailbox                             │     │ │
│   │   │  • Processing via model inference                           │     │ │
│   │   │  • Emitting deltas to DELTA_BUS                             │     │ │
│   │   │  • Responding to Orchestrator                               │     │ │
│   │   │                                                             │     │ │
│   │   └─────────────────────────────────────────────────────────────┘     │ │
│   └───────────────────────────────────────────────────────────────────────┘ │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

#### F62: ACTIVE → IDLE → ACTIVE Flow

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                  F62: ACTIVE → IDLE → ACTIVE FLOW                           │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│   Fast reactivation pool for efficient resource usage                       │
│                                                                             │
│   ┌───────────────────────────────────────────────────────────────────────┐ │
│   │                       AGENT LIFECYCLE FSM                             │ │
│   │                                                                       │ │
│   │   ┌─────────────────────────────────────────────────────────────┐     │ │
│   │   │              STATE_ACTIVE                                   │     │ │
│   │   │              Processing Messages                            │     │ │
│   │   │                                                             │     │ │
│   │   │  Agent processes tasks, no new work arrives...              │     │ │
│   │   │                                                             │     │ │
│   │   └──────────────────┬──────────────────────────────────────────┘     │ │
│   │                      │                                                │ │
│   │            60s Idle TTL (no messages)                                 │ │
│   │                      │                                                │ │
│   │                      ▼                                                │ │
│   │   ┌─────────────────────────────────────────────────────────────┐     │ │
│   │   │              STATE_IDLE                                     │     │ │
│   │   │              Fast Reactivation Pool                         │     │ │
│   │   ├─────────────────────────────────────────────────────────────┤     │ │
│   │   │                                                             │     │ │
│   │   │  Agent State:                                               │     │ │
│   │   │  • Model still loaded in memory                             │     │ │
│   │   │  • Mailbox still allocated                                  │     │ │
│   │   │  • Not actively processing                                  │     │ │
│   │   │  • Can reactivate in <10ms                                  │     │ │
│   │   │                                                             │     │ │
│   │   │  Resource Usage: LOW (no CPU, minimal memory)               │     │ │
│   │   │                                                             │     │ │
│   │   │  Pool Benefits:                                             │     │ │
│   │   │  • Skip WARMING phase on reactivation                       │     │ │
│   │   │  • Maintain hot cache                                       │     │ │
│   │   │  • Instant response to new tasks                            │     │ │
│   │   │                                                             │     │ │
│   │   └──────────────────┬──────────────────────────────────────────┘     │ │
│   │                      │                                                │ │
│   │            New Task arrives                                           │ │
│   │                      │                                                │ │
│   │                      ▼                                                │ │
│   │   ┌─────────────────────────────────────────────────────────────┐     │ │
│   │   │              STATE_ACTIVE                                   │     │ │
│   │   │              Processing Messages                            │     │ │
│   │   │                                                             │     │ │
│   │   │  Instant reactivation - no WARMING needed                   │     │ │
│   │   │  Resume processing immediately                              │     │ │
│   │   │                                                             │     │ │
│   │   └─────────────────────────────────────────────────────────────┘     │ │
│   └───────────────────────────────────────────────────────────────────────┘ │
│                                                                             │
│   Note: After extended IDLE period, may transition to DRAINING              │
│         to free resources completely                                        │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

#### F63: Agent Draining & Termination Flow

```
┌─────────────────────────────────────────────────────────────────────────────┐
│               F63: AGENT DRAINING & TERMINATION FLOW                        │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│   Graceful shutdown with resource cleanup                                   │
│                                                                             │
│   ┌───────────────────────────────────────────────────────────────────────┐ │
│   │                       AGENT LIFECYCLE FSM                             │ │
│   │                                                                       │ │
│   │   ┌─────────────────┐     ┌─────────────────┐                         │ │
│   │   │  STATE_ACTIVE   │     │  STATE_IDLE     │                         │ │
│   │   │                 │     │                 │                         │ │
│   │   │ Processing or   │     │ Waiting in pool │                         │ │
│   │   │ waiting         │     │                 │                         │ │
│   │   └────────┬────────┘     └────────┬────────┘                         │ │
│   │            │                       │                                  │ │
│   │    Supervisor Drain         Supervisor Drain                          │ │
│   │    (or resource pressure)   (or extended idle)                        │ │
│   │            │                       │                                  │ │
│   │            └───────────┬───────────┘                                  │ │
│   │                        │                                              │ │
│   │                        ▼                                              │ │
│   │   ┌─────────────────────────────────────────────────────────────┐     │ │
│   │   │              STATE_DRAINING                                 │     │ │
│   │   │              Graceful Shutdown                              │     │ │
│   │   ├─────────────────────────────────────────────────────────────┤     │ │
│   │   │                                                             │     │ │
│   │   │  Draining Process:                                          │     │ │
│   │   │  1. Stop accepting new tasks                                │     │ │
│   │   │  2. Complete in-flight tasks (with timeout)                 │     │ │
│   │   │  3. Flush pending deltas to DELTA_BUS                       │     │ │
│   │   │  4. Save any persistent state                               │     │ │
│   │   │  5. Release model resources                                 │     │ │
│   │   │                                                             │     │ │
│   │   │  Timeout: 30s max (force terminate if exceeded)             │     │ │
│   │   │                                                             │     │ │
│   │   └──────────────────┬──────────────────────────────────────────┘     │ │
│   │                      │                                                │ │
│   │            Tasks Complete                                             │ │
│   │                      │                                                │ │
│   │                      ▼                                                │ │
│   │   ┌─────────────────────────────────────────────────────────────┐     │ │
│   │   │              STATE_TERMINATED                               │     │ │
│   │   │              Clean Resource Disposal                        │     │ │
│   │   ├─────────────────────────────────────────────────────────────┤     │ │
│   │   │                                                             │     │ │
│   │   │  Final Cleanup:                                             │     │ │
│   │   │  • Deallocate mailbox                                       │     │ │
│   │   │  • Release model memory                                     │     │ │
│   │   │  • Remove from agent registry                               │     │ │
│   │   │  • Log termination event                                    │     │ │
│   │   │                                                             │     │ │
│   │   │  Agent is fully destroyed - requires re-spawn to use again  │     │ │
│   │   │                                                             │     │ │
│   │   └─────────────────────────────────────────────────────────────┘     │ │
│   └───────────────────────────────────────────────────────────────────────┘ │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

### 6.2 Sub-Agent Clarification Flow

#### F64: Sub-Agent Clarification Request Flow (via DeltaBus)

```
┌─────────────────────────────────────────────────────────────────────────────┐
│          F64: SUB-AGENT CLARIFICATION REQUEST FLOW (via DeltaBus)           │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│   Sub-agents CANNOT write to SessionState - emit to DeltaBus instead        │
│   Single Writer Pattern: Only Concierge writes to SessionState              │
│                                                                             │
│   ┌───────────────────────────────────────────────────────────────────────┐ │
│   │                                                                       │ │
│   │   L4_SUBAGENTS (any sub-agent)                                        │ │
│   │          │                                                            │ │
│   │   needs clarification from user                                       │ │
│   │   (e.g., "Which file format do you prefer?")                          │ │
│   │          │                                                            │ │
│   │          ▼                                                            │ │
│   │   ┌─────────────────────────────────────────────────────────────┐     │ │
│   │   │  Sub-Agent emits clarification_request delta                │     │ │
│   │   │                                                             │     │ │
│   │   │  {                                                          │     │ │
│   │   │    "type": "clarification_request",                         │     │ │
│   │   │    "agent_id": "health_agent_001",                          │     │ │
│   │   │    "question": "Which doctor did you mean?",                │     │ │
│   │   │    "options": ["Dr. Smith", "Dr. Jones"],                   │     │ │
│   │   │    "context": {...}                                         │     │ │
│   │   │  }                                                          │     │ │
│   │   │                                                             │     │ │
│   │   └──────────────────┬──────────────────────────────────────────┘     │ │
│   │                      │                                                │ │
│   │        clarification_request delta                                    │ │
│   │                      │                                                │ │
│   │                      ▼                                                │ │
│   │   ┌─────────────────────────────────────────────────────────────┐     │ │
│   │   │              DELTA_BUS                                      │     │ │
│   │   │         (Event Bus for all agent deltas)                    │     │ │
│   │   └──────────────────┬──────────────────────────────────────────┘     │ │
│   │                      │                                                │ │
│   │        clarification deltas                                           │ │
│   │                      │                                                │ │
│   │                      ▼                                                │ │
│   │   ┌─────────────────────────────────────────────────────────────┐     │ │
│   │   │            AGGREGATION_WINDOW                               │     │ │
│   │   │            500ms Batching                                   │     │ │
│   │   │                                                             │     │ │
│   │   │  Batches multiple deltas from different agents              │     │ │
│   │   │  into single coherent update                                │     │ │
│   │   │                                                             │     │ │
│   │   └──────────────────┬──────────────────────────────────────────┘     │ │
│   │                      │                                                │ │
│   │        clarification_request                                          │ │
│   │                      │                                                │ │
│   │                      ▼                                                │ │
│   │              CONCIERGE_FSM                                            │ │
│   │        (processes request - see F65)                                  │ │
│   └───────────────────────────────────────────────────────────────────────┘ │
│                                                                             │
│   Key: Sub-agents never directly access SessionState                        │
│        All writes go through Concierge (Single Writer)                      │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

#### F65: Concierge Pending Clarifications Write Flow (Single Writer)

```
┌─────────────────────────────────────────────────────────────────────────────┐
│       F65: CONCIERGE PENDING CLARIFICATIONS WRITE FLOW (Single Writer)      │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│   Concierge (only writer) receives delta, writes to PENDING_CLARIFICATIONS  │
│   Then routes to user for response                                          │
│                                                                             │
│   ┌───────────────────────────────────────────────────────────────────────┐ │
│   │                                                                       │ │
│   │   AGGREGATION_WINDOW                                                  │ │
│   │          │                                                            │ │
│   │   clarification_request (from sub-agent)                              │ │
│   │          │                                                            │ │
│   │          ▼                                                            │ │
│   │   ┌─────────────────────────────────────────────────────────────┐     │ │
│   │   │              CONCIERGE_FSM                                  │     │ │
│   │   │         (Single Writer for SessionState)                    │     │ │
│   │   ├─────────────────────────────────────────────────────────────┤     │ │
│   │   │                                                             │     │ │
│   │   │  1. Receive clarification request                           │     │ │
│   │   │  2. Validate request (is it reasonable?)                    │     │ │
│   │   │  3. Write to PENDING_CLARIFICATIONS                         │     │ │
│   │   │                                                             │     │ │
│   │   └──────────────────┬──────────────────────────────────────────┘     │ │
│   │                      │                                                │ │
│   │           write pending                                               │ │
│   │                      │                                                │ │
│   │                      ▼                                                │ │
│   │   ┌─────────────────────────────────────────────────────────────┐     │ │
│   │   │         PENDING_CLARIFICATIONS (HOT CORE - 2KB)             │     │ │
│   │   │         Sub-agent HIL requests                              │     │ │
│   │   ├─────────────────────────────────────────────────────────────┤     │ │
│   │   │                                                             │     │ │
│   │   │  {                                                          │     │ │
│   │   │    "pending": [                                             │     │ │
│   │   │      {                                                      │     │ │
│   │   │        "id": "clar_001",                                    │     │ │
│   │   │        "agent_id": "health_agent_001",                      │     │ │
│   │   │        "question": "Which doctor?",                         │     │ │
│   │   │        "options": ["Dr. Smith", "Dr. Jones"],               │     │ │
│   │   │        "created_at": "..."                                  │     │ │
│   │   │      }                                                      │     │ │
│   │   │    ]                                                        │     │ │
│   │   │  }                                                          │     │ │
│   │   │                                                             │     │ │
│   │   └──────────────────┬──────────────────────────────────────────┘     │ │
│   │                      │                                                │ │
│   │      interrupt for clarification                                      │ │
│   │                      │                                                │ │
│   │                      ▼                                                │ │
│   │   ┌─────────────────────────────────────────────────────────────┐     │ │
│   │   │            INTERRUPT_HANDLING                               │     │ │
│   │   │                     │                                       │     │ │
│   │   │            route to user                                    │     │ │
│   │   │                     │                                       │     │ │
│   │   │                     ▼                                       │     │ │
│   │   │              CLARIFYING                                     │     │ │
│   │   │        (present question to user)                           │     │ │
│   │   └─────────────────────────────────────────────────────────────┘     │ │
│   │                      │                                                │ │
│   │              user response                                            │ │
│   │                      │                                                │ │
│   │                      ▼                                                │ │
│   │   ACKING → resolve → route response back to waiting sub-agent         │ │
│   └───────────────────────────────────────────────────────────────────────┘ │
│                                                                             │
│   Single Writer Pattern Enforced:                                           │
│   • Sub-agents: emit deltas only                                            │
│   • DeltaBus: transport only                                                │
│   • Concierge: ONLY component that writes to SessionState                   │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## 7. SESSIONSTATE FLOWS

### 7.1 Single Writer Pattern

#### F66: Concierge → Single Writer → SessionState Flow

```
┌─────────────────────────────────────────────────────────────────────────────┐
│           F66: CONCIERGE → SINGLE WRITER → SESSIONSTATE FLOW                │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│   ADR-0018: Only Concierge writes to SessionState (Single Writer Pattern)   │
│   Prevents race conditions, ensures consistency                             │
│                                                                             │
│   ┌───────────────────────────────────────────────────────────────────────┐ │
│   │                                                                       │ │
│   │   CONCIERGE_FSM (any state transition)                                │ │
│   │          │                                                            │ │
│   │   state mutation needed                                               │ │
│   │   (e.g., update user_identity, add to history)                        │ │
│   │          │                                                            │ │
│   │          ▼                                                            │ │
│   │   ┌─────────────────────────────────────────────────────────────┐     │ │
│   │   │              SINGLE_WRITER                                  │     │ │
│   │   │         Mutation Serializer                                 │     │ │
│   │   ├─────────────────────────────────────────────────────────────┤     │ │
│   │   │                                                             │     │ │
│   │   │  Responsibilities:                                          │     │ │
│   │   │  • Queue incoming writes                                    │     │ │
│   │   │  • Serialize mutations (one at a time)                      │     │ │
│   │   │  • Enforce ordering guarantees                              │     │ │
│   │   │  • Coordinate with MutationGuard                            │     │ │
│   │   │                                                             │     │ │
│   │   │  Write Queue: FIFO, bounded                                 │     │ │
│   │   │                                                             │     │ │
│   │   └──────────────────┬──────────────────────────────────────────┘     │ │
│   │                      │                                                │ │
│   │           preflight check                                             │ │
│   │                      │                                                │ │
│   │                      ▼                                                │ │
│   │   ┌─────────────────────────────────────────────────────────────┐     │ │
│   │   │             MUTATION_GUARD                                  │     │ │
│   │   │         Budget & Eviction Check                             │     │ │
│   │   │                                                             │     │ │
│   │   │  Check: Will write exceed budget?                           │     │ │
│   │   │  If yes → trigger EVICTION_ENGINE first                     │     │ │
│   │   │  If no → proceed to write                                   │     │ │
│   │   │                                                             │     │ │
│   │   └──────────────────┬──────────────────────────────────────────┘     │ │
│   │                      │                                                │ │
│   │           approved write                                              │ │
│   │                      │                                                │ │
│   │                      ▼                                                │ │
│   │   ┌─────────────────────────────────────────────────────────────┐     │ │
│   │   │            SESSIONSTATE_STORE                               │     │ │
│   │   ├─────────────────────────────────────────────────────────────┤     │ │
│   │   │                                                             │     │ │
│   │   │   ┌─────────────┐  ┌─────────────┐  ┌─────────────┐         │     │ │
│   │   │   │  HOT_CORE   │  │  WARM_TIER  │  │ COLD_SHADOW │         │     │ │
│   │   │   │    48KB     │  │    48KB     │  │  (K0-backed)│         │     │ │
│   │   │   │ never evict │  │  evictable  │  │  infinite   │         │     │ │
│   │   │   └─────────────┘  └─────────────┘  └─────────────┘         │     │ │
│   │   │                                                             │     │ │
│   │   │   TOTAL HARD LIMIT: 96KB                                    │     │ │
│   │   │                                                             │     │ │
│   │   └─────────────────────────────────────────────────────────────┘     │ │
│   └───────────────────────────────────────────────────────────────────────┘ │
│                                                                             │
│   Key: Only Concierge reaches SINGLE_WRITER                                 │
│        Sub-agents emit to DeltaBus → Concierge → SINGLE_WRITER              │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

#### F67: Multi-Reader Access Flow

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                    F67: MULTI-READER ACCESS FLOW                            │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│   Single Writer, Multiple Readers - lock-free read access                   │
│                                                                             │
│   ┌───────────────────────────────────────────────────────────────────────┐ │
│   │                                                                       │ │
│   │                       SESSIONSTATE_STORE                              │ │
│   │                              │                                        │ │
│   │              ┌───────────────┼───────────────┐                        │ │
│   │              │               │               │                        │ │
│   │              ▼               ▼               ▼                        │ │
│   │   ┌─────────────────────────────────────────────────────────────┐     │ │
│   │   │                   READ ACCESS (Lock-Free)                   │     │ │
│   │   │                                                             │     │ │
│   │   │  ┌─────────────┐ ┌─────────────┐ ┌─────────────┐            │     │ │
│   │   │  │ CONCIERGE   │ │ ORCHESTRATOR│ │  PLANNER    │            │     │ │
│   │   │  │   (read)    │ │   (read)    │ │   (read)    │            │     │ │
│   │   │  └─────────────┘ └─────────────┘ └─────────────┘            │     │ │
│   │   │                                                             │     │ │
│   │   │  ┌─────────────┐ ┌─────────────┐ ┌─────────────┐            │     │ │
│   │   │  │ SUB-AGENTS  │ │  TOOL EXEC  │ │ ULTRABERT   │            │     │ │
│   │   │  │   (read)    │ │   (read)    │ │   (read)    │            │     │ │
│   │   │  └─────────────┘ └─────────────┘ └─────────────┘            │     │ │
│   │   │                                                             │     │ │
│   │   └─────────────────────────────────────────────────────────────┘     │ │
│   │                              │                                        │ │
│   │                              │                                        │ │
│   │                              ▼                                        │ │
│   │   ┌─────────────────────────────────────────────────────────────┐     │ │
│   │   │               WRITE ACCESS (Serialized)                     │     │ │
│   │   │                                                             │     │ │
│   │   │               ┌─────────────┐                               │     │ │
│   │   │               │ CONCIERGE   │  ← ONLY writer                │     │ │
│   │   │               │   (write)   │                               │     │ │
│   │   │               └──────┬──────┘                               │     │ │
│   │   │                      │                                      │     │ │
│   │   │                      ▼                                      │     │ │
│   │   │               SINGLE_WRITER                                 │     │ │
│   │   │                                                             │     │ │
│   │   └─────────────────────────────────────────────────────────────┘     │ │
│   └───────────────────────────────────────────────────────────────────────┘ │
│                                                                             │
│   Benefits:                                                                 │
│   • No read locks → high concurrency                                        │
│   • Eventual consistency for readers                                        │
│   • Writes serialized → strong consistency                                  │
│   • No writer starvation                                                    │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

### 7.2 Delta Aggregation Flow

#### F68: Agent Deltas → DeltaBus Flow

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                  F68: AGENT DELTAS → DELTABUS FLOW                          │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│   All agents emit deltas to DeltaBus - central event bus for state changes  │
│                                                                             │
│   ┌───────────────────────────────────────────────────────────────────────┐ │
│   │                                                                       │ │
│   │   L4_SUBAGENTS (multiple concurrent agents)                           │ │
│   │                                                                       │ │
│   │   ┌─────────┐ ┌─────────┐ ┌─────────┐ ┌─────────┐ ┌─────────┐         │ │
│   │   │ health_ │ │ finance_│ │ travel_ │ │ smart_  │ │ memory_ │         │ │
│   │   │ agent   │ │ agent   │ │ agent   │ │ home    │ │ writer  │         │ │
│   │   └────┬────┘ └────┬────┘ └────┬────┘ └────┬────┘ └────┬────┘         │ │
│   │        │           │           │           │           │              │ │
│   │    emit delta  emit delta  emit delta  emit delta  emit delta         │ │
│   │        │           │           │           │           │              │ │
│   │        │           │           │           │           │              │ │
│   │        └───────────┴─────┬─────┴───────────┴───────────┘              │ │
│   │                          │                                            │ │
│   │                          ▼                                            │ │
│   │   ┌─────────────────────────────────────────────────────────────┐     │ │
│   │   │                     DELTA_BUS                               │     │ │
│   │   │              Central Event Bus                              │     │ │
│   │   ├─────────────────────────────────────────────────────────────┤     │ │
│   │   │                                                             │     │ │
│   │   │  Delta Types:                                               │     │ │
│   │   │  • state_update: Agent state changes                        │     │ │
│   │   │  • clarification_request: Need user input                   │     │ │
│   │   │  • task_complete: Work finished                             │     │ │
│   │   │  • belief_update: User model changes                        │     │ │
│   │   │  • memory_episodic: Experience to remember                  │     │ │
│   │   │                                                             │     │ │
│   │   │  Ordering: Per-agent ordering guaranteed                    │     │ │
│   │   │  Delivery: At-least-once                                    │     │ │
│   │   │                                                             │     │ │
│   │   └──────────────────────────────────────────────────────────────┘    │ │
│   └───────────────────────────────────────────────────────────────────────┘ │
│                                                                             │
│   Key: DeltaBus decouples agents from SessionState                          │
│        Agents don't know about Single Writer pattern                        │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

#### F69: DeltaBus → Aggregation Window → Concierge Flow

```
┌─────────────────────────────────────────────────────────────────────────────┐
│          F69: DELTABUS → AGGREGATION WINDOW → CONCIERGE FLOW                │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│   500ms batching window for efficient state updates                         │
│                                                                             │
│   ┌───────────────────────────────────────────────────────────────────────┐ │
│   │                                                                       │ │
│   │   DELTA_BUS                                                           │ │
│   │          │                                                            │ │
│   │   stream of deltas (high frequency)                                   │ │
│   │          │                                                            │ │
│   │          ▼                                                            │ │
│   │   ┌─────────────────────────────────────────────────────────────┐     │ │
│   │   │            AGGREGATION_WINDOW                               │     │ │
│   │   │            500ms Batching                                   │     │ │
│   │   ├─────────────────────────────────────────────────────────────┤     │ │
│   │   │                                                             │     │ │
│   │   │  ┌─────────────────────────────────────────────────────┐    │     │ │
│   │   │  │  t=0ms    t=100ms   t=250ms   t=400ms   t=500ms     │    │     │ │
│   │   │  │    │         │         │         │         │        │    │     │ │
│   │   │  │    ▼         ▼         ▼         ▼         ▼        │    │     │ │
│   │   │  │  [δ1]     [δ2,δ3]    [δ4]      [δ5]    [FLUSH]      │    │     │ │
│   │   │  │                                                     │    │     │ │
│   │   │  │  Collect deltas for 500ms window                    │    │     │ │
│   │   │  └─────────────────────────────────────────────────────┘    │     │ │
│   │   │                                                             │     │ │
│   │   │  Aggregation Logic:                                         │     │ │
│   │   │  • Merge conflicting updates (last-write-wins)              │     │ │
│   │   │  • Collapse redundant updates                               │     │ │
│   │   │  • Sort by priority (clarifications first)                  │     │ │
│   │   │                                                             │     │ │
│   │   └──────────────────┬──────────────────────────────────────────┘     │ │
│   │                      │                                                │ │
│   │        aggregated batch (every 500ms)                                 │ │
│   │                      │                                                │ │
│   │                      ▼                                                │ │
│   │   ┌─────────────────────────────────────────────────────────────┐     │ │
│   │   │              CONCIERGE_FSM                                  │     │ │
│   │   │         Receives Aggregated Batch                           │     │ │
│   │   ├─────────────────────────────────────────────────────────────┤     │ │
│   │   │                                                             │     │ │
│   │   │  Processing:                                                │     │ │
│   │   │  1. Inspect batch for clarifications → CLARIFYING state     │     │ │
│   │   │  2. Apply state updates via SINGLE_WRITER                   │     │ │
│   │   │  3. Trigger downstream effects                              │     │ │
│   │   │                                                             │     │ │
│   │   └─────────────────────────────────────────────────────────────┘     │ │
│   └───────────────────────────────────────────────────────────────────────┘ │
│                                                                             │
│   Why 500ms?                                                                │
│   • Balances latency vs. efficiency                                         │
│   • Reduces write amplification                                             │
│   • Allows conflict resolution                                              │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

### 7.3 Memory Tiering Flow

#### F70: HOT → WARM Eviction Flow

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                    F70: HOT → WARM EVICTION FLOW                            │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│   ADR-0018: Tier-aware eviction when HOT approaches 48KB                    │
│                                                                             │
│   ┌───────────────────────────────────────────────────────────────────────┐ │
│   │                                                                       │ │
│   │   ┌─────────────────────────────────────────────────────────────┐     │ │
│   │   │                    HOT_CORE (48KB)                          │     │ │
│   │   │              Critical - Never Fully Evict                   │     │ │
│   │   ├─────────────────────────────────────────────────────────────┤     │ │
│   │   │                                                             │     │ │
│   │   │  Protected (never evict):         Evictable to WARM:        │     │ │
│   │   │  ┌──────────────────────┐        ┌──────────────────────┐   │     │ │
│   │   │  │ USER_IDENTITY (4KB)  │        │ HISTORY_ACTIVE (8KB) │   │     │ │
│   │   │  │ CURRENT_TOPIC (2KB)  │        │ CONTEXT_RECENT(6KB)  │   │     │ │
│   │   │  │ PENDING_CLARIF (2KB) │        │ BELIEFS_ACTIVE(4KB)  │   │     │ │
│   │   │  │ ACTIVE_TASKS (4KB)   │        │                      │   │     │ │
│   │   │  │ SAFETY_FLAGS (1KB)   │        │                      │   │     │ │
│   │   │  └──────────────────────┘        └──────────┬───────────┘   │     │ │
│   │   │                                             │               │     │ │
│   │   └─────────────────────────────────────────────┼───────────────┘     │ │
│   │                                                 │                     │ │
│   │           Eviction Trigger: HOT > 40KB          │                     │ │
│   │           (proactive eviction before limit)     │                     │ │
│   │                                                 │                     │ │
│   │                                                 ▼                     │ │
│   │   ┌─────────────────────────────────────────────────────────────┐     │ │
│   │   │                   EVICTION_ENGINE                           │     │ │
│   │   │              Tier-Aware, LRU-Based                          │     │ │
│   │   ├─────────────────────────────────────────────────────────────┤     │ │
│   │   │                                                             │     │ │
│   │   │  Eviction Order (oldest first):                             │     │ │
│   │   │  1. HISTORY_ACTIVE → HISTORY_RECENT                         │     │ │
│   │   │  2. BELIEFS_ACTIVE → BELIEFS_HISTORY                        │     │ │
│   │   │  3. CONTEXT_RECENT → CONTEXT_ARCHIVE                        │     │ │
│   │   │                                                             │     │ │
│   │   └──────────────────┬──────────────────────────────────────────┘     │ │
│   │                      │                                                │ │
│   │           move to WARM                                                │ │
│   │                      │                                                │ │
│   │                      ▼                                                │ │
│   │   ┌─────────────────────────────────────────────────────────────┐     │ │
│   │   │                    WARM_TIER (48KB)                         │     │ │
│   │   │              Recently Used - Evictable                      │     │ │
│   │   ├─────────────────────────────────────────────────────────────┤     │ │
│   │   │                                                             │     │ │
│   │   │  ┌──────────────────────┐ ┌──────────────────────┐          │     │ │
│   │   │  │ HISTORY_RECENT (12KB)│ │ CONTEXT_ARCHIVE(12KB)│          │     │ │
│   │   │  └──────────────────────┘ └──────────────────────┘          │     │ │
│   │   │  ┌──────────────────────┐ ┌──────────────────────┐          │     │ │
│   │   │  │ BELIEFS_HISTORY(8KB) │ │ TOOL_CACHE (8KB)     │          │     │ │
│   │   │  └──────────────────────┘ └──────────────────────┘          │     │ │
│   │   │                                                             │     │ │
│   │   └─────────────────────────────────────────────────────────────┘     │ │
│   └───────────────────────────────────────────────────────────────────────┘ │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

#### F71: WARM → COLD Archive Flow

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                    F71: WARM → COLD ARCHIVE FLOW                            │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│   When WARM approaches 48KB, archive oldest to COLD (K0-backed)             │
│                                                                             │
│   ┌───────────────────────────────────────────────────────────────────────┐ │
│   │                                                                       │ │
│   │   ┌─────────────────────────────────────────────────────────────┐     │ │
│   │   │                    WARM_TIER (48KB)                         │     │ │
│   │   │              Approaching Limit                              │     │ │
│   │   ├─────────────────────────────────────────────────────────────┤     │ │
│   │   │                                                             │     │ │
│   │   │  Archive candidates (oldest first):                         │     │ │
│   │   │  ┌──────────────────────┐                                   │     │ │
│   │   │  │ HISTORY_RECENT       │ → HISTORY_ARCHIVE                 │     │ │
│   │   │  │ (old entries)        │                                   │     │ │
│   │   │  └──────────────────────┘                                   │     │ │
│   │   │  ┌──────────────────────┐                                   │     │ │
│   │   │  │ BELIEFS_HISTORY      │ → BELIEFS_ARCHIVE                 │     │ │
│   │   │  │ (old entries)        │                                   │     │ │
│   │   │  └──────────────────────┘                                   │     │ │
│   │   │                                                             │     │ │
│   │   └──────────────────┬──────────────────────────────────────────┘     │ │
│   │                      │                                                │ │
│   │           archive to K0                                               │ │
│   │                      │                                                │ │
│   │                      ▼                                                │ │
│   │   ┌─────────────────────────────────────────────────────────────┐     │ │
│   │   │                   K0_STORAGE                                │     │ │
│   │   │              Long-Term Memory                               │     │ │
│   │   ├─────────────────────────────────────────────────────────────┤     │ │
│   │   │                                                             │     │ │
│   │   │  K0 pipelines for archival:                                 │     │ │
│   │   │  • P02: Episodic memories                                   │     │ │
│   │   │  • P03: Memory consolidation                                │     │ │
│   │   │  • P04: Belief updates                                      │     │ │
│   │   │                                                             │     │ │
│   │   └──────────────────┬──────────────────────────────────────────┘     │ │
│   │                      │                                                │ │
│   │           stored as COLD_SHADOW                                       │ │
│   │                      │                                                │ │
│   │                      ▼                                                │ │
│   │   ┌─────────────────────────────────────────────────────────────┐     │ │
│   │   │                   COLD_SHADOW                               │     │ │
│   │   │              K0-Backed Storage                              │     │ │
│   │   ├─────────────────────────────────────────────────────────────┤     │ │
│   │   │                                                             │     │ │
│   │   │  Properties:                                                │     │ │
│   │   │  • Unlimited capacity (K0 storage)                          │     │ │
│   │   │  • 50ms reconstruction SLA                                  │     │ │
│   │   │  • Compressed storage                                       │     │ │
│   │   │  • Index-only in SessionState                               │     │ │
│   │   │                                                             │     │ │
│   │   │  Sections:                                                  │     │ │
│   │   │  ┌──────────────────────┐ ┌──────────────────────┐          │     │ │
│   │   │  │ HISTORY_ARCHIVE     │ │ BELIEFS_ARCHIVE       │          │     │ │
│   │   │  │ (index pointers)    │ │ (index pointers)      │          │     │ │
│   │   │  └──────────────────────┘ └──────────────────────┘          │     │ │
│   │   │                                                             │     │ │
│   │   └─────────────────────────────────────────────────────────────┘     │ │
│   └───────────────────────────────────────────────────────────────────────┘ │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

#### F72: COLD → HOT Reconstruction Flow

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                   F72: COLD → HOT RECONSTRUCTION FLOW                       │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│   50ms SLA for reconstructing archived data when needed                     │
│                                                                             │
│   ┌───────────────────────────────────────────────────────────────────────┐ │
│   │                                                                       │ │
│   │   CONCIERGE_FSM or ORCHESTRATOR                                       │ │
│   │          │                                                            │ │
│   │   needs archived context                                              │ │
│   │   (e.g., "remember last week's conversation about...")                │ │
│   │          │                                                            │ │
│   │          ▼                                                            │ │
│   │   ┌─────────────────────────────────────────────────────────────┐     │ │
│   │   │            SESSIONSTATE_STORE                               │     │ │
│   │   │            Check HOT/WARM first                             │     │ │
│   │   ├─────────────────────────────────────────────────────────────┤     │ │
│   │   │                                                             │     │ │
│   │   │  Search Order:                                              │     │ │
│   │   │  1. HOT_CORE → found? return immediately                    │     │ │
│   │   │  2. WARM_TIER → found? return + promote to HOT              │     │ │
│   │   │  3. COLD_SHADOW → trigger reconstruction                    │     │ │
│   │   │                                                             │     │ │
│   │   └──────────────────┬──────────────────────────────────────────┘     │ │
│   │                      │                                                │ │
│   │           cache miss - need COLD                                      │ │
│   │                      │                                                │ │
│   │                      ▼                                                │ │
│   │   ┌─────────────────────────────────────────────────────────────┐     │ │
│   │   │             RECONSTRUCTION_SLA                              │     │ │
│   │   │             50ms Target                                     │     │ │
│   │   ├─────────────────────────────────────────────────────────────┤     │ │
│   │   │                                                             │     │ │
│   │   │  1. Lookup index pointer in COLD_SHADOW                     │     │ │
│   │   │  2. Fetch from K0 storage                                   │     │ │
│   │   │  3. Decompress if needed                                    │     │ │
│   │   │  4. Load into HOT_CORE (evicting if necessary)              │     │ │
│   │   │                                                             │     │ │
│   │   │  Timeline:                                                  │     │ │
│   │   │  ├─────────────────────────────────────────────┤            │     │ │
│   │   │  0ms        20ms        40ms        50ms                    │     │ │
│   │   │  │          │           │           │                       │     │ │
│   │   │  lookup     K0 fetch    decompress  ready                   │     │ │
│   │   │                                                             │     │ │
│   │   └──────────────────┬──────────────────────────────────────────┘     │ │
│   │                      │                                                │ │
│   │           reconstructed data                                          │ │
│   │                      │                                                │ │
│   │                      ▼                                                │ │
│   │   ┌─────────────────────────────────────────────────────────────┐     │ │
│   │   │                    HOT_CORE                                 │     │ │
│   │   │            Data Now Available                               │     │ │
│   │   │                                                             │     │ │
│   │   │  Promoted to HOT for fast subsequent access                 │     │ │
│   │   │  May trigger eviction of other HOT entries                  │     │ │
│   │   │                                                             │     │ │
│   │   └─────────────────────────────────────────────────────────────┘     │ │
│   └───────────────────────────────────────────────────────────────────────┘ │
│                                                                             │
│   Note: User experiences <50ms pause for archived context                   │
│         Indistinguishable from normal latency                               │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

### 7.4 Emergency Mode Flows

#### F73: Emergency Summarization Flow (≥95KB)

```
┌─────────────────────────────────────────────────────────────────────────────┐
│               F73: EMERGENCY SUMMARIZATION FLOW (≥95KB)                     │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│   When total SessionState ≥95KB, trigger emergency measures                 │
│                                                                             │
│   ┌───────────────────────────────────────────────────────────────────────┐ │
│   │                                                                       │ │
│   │   ┌─────────────────────────────────────────────────────────────┐     │ │
│   │   │                 SESSIONSTATE_STORE                          │     │ │
│   │   │                 Size: ≥95KB / 96KB                          │     │ │
│   │   │                 STATUS: EMERGENCY                           │     │ │
│   │   └──────────────────┬──────────────────────────────────────────┘     │ │
│   │                      │                                                │ │
│   │           threshold breach detected                                   │ │
│   │                      │                                                │ │
│   │                      ▼                                                │ │
│   │   ┌─────────────────────────────────────────────────────────────┐     │ │
│   │   │                 EMERGENCY_MODE                              │     │ │
│   │   │                 Activate                                    │     │ │
│   │   └──────────────────┬──────────────────────────────────────────┘     │ │
│   │                      │                                                │ │
│   │          ┌───────────┴───────────┬───────────────────┐                │ │
│   │          │                       │                   │                │ │
│   │          ▼                       ▼                   ▼                │ │
│   │   ┌─────────────┐    ┌──────────────────┐   ┌────────────────┐        │ │
│   │   │ EMERGENCY_  │    │ EMERGENCY_       │   │ EMERGENCY_     │        │ │
│   │   │ SUMMARIZE   │    │ READONLY         │   │ SHED           │        │ │
│   │   └──────┬──────┘    └──────────────────┘   └────────────────┘        │ │
│   │          │                                                            │ │
│   │          ▼                                                            │ │
│   │   ┌─────────────────────────────────────────────────────────────┐     │ │
│   │   │             EMERGENCY_SUMMARIZE                             │     │ │
│   │   │             Aggressive Compression                          │     │ │
│   │   ├─────────────────────────────────────────────────────────────┤     │ │
│   │   │                                                             │     │ │
│   │   │  Process:                                                   │     │ │
│   │   │  1. Identify compressible sections (history, context)       │     │ │
│   │   │  2. Generate summaries via Memory Writer agent              │     │ │
│   │   │  3. Replace verbose data with summaries                     │     │ │
│   │   │  4. Archive originals to COLD                               │     │ │
│   │   │                                                             │     │ │
│   │   │  Example:                                                   │     │ │
│   │   │  Before: 15 turn messages (12KB)                            │     │ │
│   │   │  After:  Summary "User discussed travel plans" (500B)       │     │ │
│   │   │          + COLD archive pointer                             │     │ │
│   │   │                                                             │     │ │
│   │   │  Target: Reduce to <90KB                                    │     │ │
│   │   │                                                             │     │ │
│   │   └─────────────────────────────────────────────────────────────┘     │ │
│   └───────────────────────────────────────────────────────────────────────┘ │
│                                                                             │
│   Note: Emergency summarization is lossy but preserves key information      │
│         Full history still available in COLD tier                           │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

#### F74: Emergency Read-Only Mode Flow

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                  F74: EMERGENCY READ-ONLY MODE FLOW                         │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│   When at 96KB hard limit, block new writes to prevent corruption           │
│                                                                             │
│   ┌───────────────────────────────────────────────────────────────────────┐ │
│   │                                                                       │ │
│   │   ┌─────────────────────────────────────────────────────────────┐     │ │
│   │   │                 SESSIONSTATE_STORE                          │     │ │
│   │   │                 Size: 96KB / 96KB (FULL)                    │     │ │
│   │   └─────────────────────────────────────────────────────────────┘     │ │
│   │                      │                                                │ │
│   │           hard limit reached                                          │ │
│   │                      │                                                │ │
│   │                      ▼                                                │ │
│   │   ┌─────────────────────────────────────────────────────────────┐     │ │
│   │   │             EMERGENCY_READONLY                              │     │ │
│   │   │             Block All Writes                                │     │ │
│   │   ├─────────────────────────────────────────────────────────────┤     │ │
│   │   │                                                             │     │ │
│   │   │  Write Behavior:                                            │     │ │
│   │   │  ┌──────────────────────────────────────────────────────┐   │     │ │
│   │   │  │                                                      │   │     │ │
│   │   │  │  CONCIERGE → SINGLE_WRITER → MUTATION_GUARD          │   │     │ │
│   │   │  │                                    │                 │   │     │ │
│   │   │  │                                    ▼                 │   │     │ │
│   │   │  │                              ╔═══════════╗           │   │     │ │
│   │   │  │                              ║  REJECT   ║           │   │     │ │
│   │   │  │                              ║  WRITE    ║           │   │     │ │
│   │   │  │                              ╚═══════════╝           │   │     │ │
│   │   │  │                                                      │   │     │ │
│   │   │  └──────────────────────────────────────────────────────┘   │     │ │
│   │   │                                                             │     │ │
│   │   │  Read Behavior: Normal (reads still work)                   │     │ │
│   │   │                                                             │     │ │
│   │   │  Recovery:                                                  │     │ │
│   │   │  • EMERGENCY_SUMMARIZE runs in background                   │     │ │
│   │   │  • Once < 90KB, writes resume                               │     │ │
│   │   │                                                             │     │ │
│   │   └─────────────────────────────────────────────────────────────┘     │ │
│   │                                                                       │ │
│   │   User Experience:                                                    │ │
│   │   • System still responds (from existing context)                     │ │
│   │   • New information may be lost temporarily                           │ │
│   │   • Background cleanup restores normal operation                      │ │
│   │                                                                       │ │
│   └───────────────────────────────────────────────────────────────────────┘ │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

#### F75: Emergency Priority Shedding Flow

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                  F75: EMERGENCY PRIORITY SHEDDING FLOW                      │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│   Drop low-priority work to free resources during emergency                 │
│                                                                             │
│   ┌───────────────────────────────────────────────────────────────────────┐ │
│   │                                                                       │ │
│   │   EMERGENCY_MODE active                                               │ │
│   │          │                                                            │ │
│   │          ▼                                                            │ │
│   │   ┌─────────────────────────────────────────────────────────────┐     │ │
│   │   │               EMERGENCY_SHED                                │     │ │
│   │   │               Priority Shedding                             │     │ │
│   │   ├─────────────────────────────────────────────────────────────┤     │ │
│   │   │                                                             │     │ │
│   │   │  Task Priority Levels (shed from bottom):                   │     │ │
│   │   │                                                             │     │ │
│   │   │  ┌──────────────────────────────────────────────────────┐   │     │ │
│   │   │  │ TIER_CRITICAL │ User safety, active response  │ KEEP │   │     │ │
│   │   │  ├───────────────┼───────────────────────────────┼──────┤   │     │ │
│   │   │  │ TIER_HIGH     │ Current task completion       │ KEEP │   │     │ │
│   │   │  ├───────────────┼───────────────────────────────┼──────┤   │     │ │
│   │   │  │ TIER_MEDIUM   │ Background processing         │ SHED │   │     │ │
│   │   │  ├───────────────┼───────────────────────────────┼──────┤   │     │ │
│   │   │  │ TIER_LOW      │ Proactive, predictive         │ SHED │   │     │ │
│   │   │  └──────────────────────────────────────────────────────┘   │     │ │
│   │   │                                                             │     │ │
│   │   └──────────────────┬──────────────────────────────────────────┘     │ │
│   │                      │                                                │ │
│   │           shed low priority                                           │ │
│   │                      │                                                │ │
│   │                      ▼                                                │ │
│   │   ┌─────────────────────────────────────────────────────────────┐     │ │
│   │   │                 AFFECTED SYSTEMS                            │     │ │
│   │   ├─────────────────────────────────────────────────────────────┤     │ │
│   │   │                                                             │     │ │
│   │   │  Shed (stopped/cancelled):                                  │     │ │
│   │   │  • Proactive agent spawning                                 │     │ │
│   │   │  • Speculative execution                                    │     │ │
│   │   │  • Background learning loops                                │     │ │
│   │   │  • Non-essential memory consolidation                       │     │ │
│   │   │                                                             │     │ │
│   │   │  Kept (continue running):                                   │     │ │
│   │   │  • Current user conversation                                │     │ │
│   │   │  • Active task execution                                    │     │ │
│   │   │  • Safety monitoring                                        │     │ │
│   │   │  • Emergency summarization                                  │     │ │
│   │   │                                                             │     │ │
│   │   └─────────────────────────────────────────────────────────────┘     │ │
│   └───────────────────────────────────────────────────────────────────────┘ │
│                                                                             │
│   Recovery: Once below 90KB, shed tasks can be rescheduled                  │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

### 7.5 Mutation Guard Flow

#### F76: Write Request → Mutation Guard Flow

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                F76: WRITE REQUEST → MUTATION GUARD FLOW                     │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│   Preflight check before any SessionState write                             │
│                                                                             │
│   ┌───────────────────────────────────────────────────────────────────────┐ │
│   │                                                                       │ │
│   │   SINGLE_WRITER                                                       │ │
│   │          │                                                            │ │
│   │   write request (section, data, size)                                 │ │
│   │          │                                                            │ │
│   │          ▼                                                            │ │
│   │   ┌─────────────────────────────────────────────────────────────┐     │ │
│   │   │                MUTATION_GUARD                               │     │ │
│   │   │                Preflight Checks                             │     │ │
│   │   ├─────────────────────────────────────────────────────────────┤     │ │
│   │   │                                                             │     │ │
│   │   │  Check 1: Budget Available?                                 │     │ │
│   │   │  ┌─────────────────────────────────────────────────────┐    │     │ │
│   │   │  │ current_size + write_size <= tier_limit?            │    │     │ │
│   │   │  │                                                     │    │     │ │
│   │   │  │ HOT:  current + write <= 48KB?                      │    │     │ │
│   │   │  │ WARM: current + write <= 48KB?                      │    │     │ │
│   │   │  │ TOTAL: current + write <= 96KB?                     │    │     │ │
│   │   │  └─────────────────────────────────────────────────────┘    │     │ │
│   │   │                                                             │     │ │
│   │   │  Check 2: Section Writable?                                 │     │ │
│   │   │  ┌─────────────────────────────────────────────────────┐    │     │ │
│   │   │  │ Is section in READONLY mode?                        │    │     │ │
│   │   │  │ Is emergency mode blocking writes?                  │    │     │ │
│   │   │  └─────────────────────────────────────────────────────┘    │     │ │
│   │   │                                                             │     │ │
│   │   │  Check 3: Valid Mutation?                                   │     │ │
│   │   │  ┌─────────────────────────────────────────────────────┐    │     │ │
│   │   │  │ Does mutation match section schema?                 │    │     │ │
│   │   │  │ Is data well-formed?                                │    │     │ │
│   │   │  └─────────────────────────────────────────────────────┘    │     │ │
│   │   │                                                             │     │ │
│   │   └──────────────────┬───────────────────────────────────────────┘    │ │
│   │                      │                                                │ │
│   │       ┌──────────────┴──────────────┐                                 │ │
│   │       │                             │                                 │ │
│   │       ▼                             ▼                                 │ │
│   │   ┌───────────┐             ┌───────────────┐                         │ │
│   │   │  APPROVE  │             │    REJECT     │                         │ │
│   │   │           │             │               │                         │ │
│   │   │ Proceed   │             │ If budget:    │                         │ │
│   │   │ to write  │             │ → Eviction    │                         │ │
│   │   │           │             │ If readonly:  │                         │ │
│   │   │           │             │ → Queue/Drop  │                         │ │
│   │   └───────────┘             └───────────────┘                         │ │
│   └───────────────────────────────────────────────────────────────────────┘ │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

#### F77: Eviction Engine Trigger Flow

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                  F77: EVICTION ENGINE TRIGGER FLOW                          │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│   MutationGuard triggers EvictionEngine when budget exceeded                │
│                                                                             │
│   ┌───────────────────────────────────────────────────────────────────────┐ │
│   │                                                                       │ │
│   │   MUTATION_GUARD                                                      │ │
│   │          │                                                            │ │
│   │   budget check failed                                                 │ │
│   │   (need space for incoming write)                                     │ │
│   │          │                                                            │ │
│   │          ▼                                                            │ │
│   │   ┌─────────────────────────────────────────────────────────────┐     │ │
│   │   │               EVICTION_ENGINE                               │     │ │
│   │   │               Tier-Aware Eviction                           │     │ │
│   │   ├─────────────────────────────────────────────────────────────┤     │ │
│   │   │                                                             │     │ │
│   │   │  Input: need_bytes = write_size - available_space           │     │ │
│   │   │                                                             │     │ │
│   │   │  Step 1: Identify eviction candidates                       │     │ │
│   │   │  ┌─────────────────────────────────────────────────────┐    │     │ │
│   │   │  │ HOT evictable:                                      │    │     │ │
│   │   │  │ • HISTORY_ACTIVE (oldest entries)                   │    │     │ │
│   │   │  │ • CONTEXT_RECENT (oldest entries)                   │    │     │ │
│   │   │  │ • BELIEFS_ACTIVE (stale entries)                    │    │     │ │
│   │   │  │                                                     │    │     │ │
│   │   │  │ HOT protected (never evict):                        │    │     │ │
│   │   │  │ • USER_IDENTITY                                     │    │     │ │
│   │   │  │ • CURRENT_TOPIC                                     │    │     │ │
│   │   │  │ • SAFETY_FLAGS                                      │    │     │ │
│   │   │  │ • ACTIVE_TASKS                                      │    │     │ │
│   │   │  └─────────────────────────────────────────────────────┘    │     │ │
│   │   │                                                             │     │ │
│   │   │  Step 2: Select by LRU + priority                           │     │ │
│   │   │  ┌─────────────────────────────────────────────────────┐    │     │ │
│   │   │  │ Sort candidates by:                                 │    │     │ │
│   │   │  │ 1. Last access time (oldest first)                  │    │     │ │
│   │   │  │ 2. Priority (low first)                             │    │     │ │
│   │   │  │ 3. Size (larger first for efficiency)               │    │     │ │
│   │   │  └─────────────────────────────────────────────────────┘    │     │ │
│   │   │                                                             │     │ │
│   │   │  Step 3: Cascade eviction                                   │     │ │
│   │   │                                                             │     │ │
│   │   └──────────────────┬──────────────────────────────────────────┘     │ │
│   │                      │                                                │ │
│   │           evict until need_bytes satisfied                            │ │
│   │                      │                                                │ │
│   │                      ▼                                                │ │
│   │   ┌─────────────────────────────────────────────────────────────┐     │ │
│   │   │               EVICTION CASCADE                              │     │ │
│   │   │                                                             │     │ │
│   │   │   HOT_CORE                WARM_TIER               COLD      │     │ │
│   │   │      │                        │                     │       │     │ │
│   │   │      │   evict oldest         │   evict oldest      │       │     │ │
│   │   │      ├───────────────────────►│ ──────────────────► │       │     │ │
│   │   │      │                        │                     │       │     │ │
│   │   │   HISTORY_ACTIVE ─────► HISTORY_RECENT ─────► HISTORY_ARCHIVE     │ │
│   │   │   BELIEFS_ACTIVE ─────► BELIEFS_HISTORY ────► BELIEFS_ARCHIVE     │ │
│   │   │                                                             │     │ │
│   │   └──────────────────┬──────────────────────────────────────────┘     │ │
│   │                      │                                                │ │
│   │           space freed                                                 │ │
│   │                      │                                                │ │
│   │                      ▼                                                │ │
│   │   MUTATION_GUARD → APPROVE → write proceeds                           │ │
│   └───────────────────────────────────────────────────────────────────────┘ │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## 8. K0 BRIDGE FLOWS

### 8.1 K0 Write Pipeline Flow

#### F78: Memory Writer Agents → K0 Flow

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                    F78: MEMORY WRITER AGENTS → K0 FLOW                      │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│   LLM-based agents observe conversations and prepare K0 command envelopes   │
│                                                                             │
│   ┌───────────────────────────────────────────────────────────────────────┐ │
│   │                                                                       │ │
│   │   DELTA_BUS                                                           │ │
│   │          │                                                            │ │
│   │   session deltas (from all agents)                                    │ │
│   │          │                                                            │ │
│   │          ▼                                                            │ │
│   │   ┌─────────────────────────────────────────────────────────────┐     │ │
│   │   │            MEMORY_WRITER_AGENTS                             │     │ │
│   │   │            LLM-Based Memory Writers                         │     │ │
│   │   ├─────────────────────────────────────────────────────────────┤     │ │
│   │   │                                                             │     │ │
│   │   │  Agent Types:                                               │     │ │
│   │   │  ┌─────────────────────────────────────────────────────┐    │     │ │
│   │   │  │ MemoryWriterAgent                                   │    │     │ │
│   │   │  │ • Observes LLM conversations                        │    │     │ │
│   │   │  │ • Extracts episodic memories                        │    │     │ │
│   │   │  │ • Prepares K0 command envelopes                     │    │     │ │
│   │   │  └─────────────────────────────────────────────────────┘    │     │ │
│   │   │  ┌─────────────────────────────────────────────────────┐    │     │ │
│   │   │  │ LearningExtractorAgent                              │    │     │ │
│   │   │  │ • Identifies learning patterns                      │    │     │ │
│   │   │  │ • Prepares advisory signals                         │    │     │ │
│   │   │  │ • Routes to P06 pipeline                            │    │     │ │
│   │   │  └─────────────────────────────────────────────────────┘    │     │ │
│   │   │                                                             │     │ │
│   │   └──────────────────┬──────────────────────────────────────────┘     │ │
│   │                      │                                                │ │
│   │           agent deltas (structured K0 commands)                       │ │
│   │                      │                                                │ │
│   │                      ▼                                                │ │
│   │   ┌─────────────────────────────────────────────────────────────┐     │ │
│   │   │            STATE_DELTA_EMITTER                              │     │ │
│   │   │            Batch Window: 250ms                              │     │ │
│   │   ├─────────────────────────────────────────────────────────────┤     │ │
│   │   │                                                             │     │ │
│   │   │  Output: K0 Command Envelopes (JSON)                        │     │ │
│   │   │  {                                                          │     │ │
│   │   │    "pipeline": "P02",                                       │     │ │
│   │   │    "operation": "episodic.write",                           │     │ │
│   │   │    "payload": {...},                                        │     │ │
│   │   │    "trace_id": "cog_xxx"                                    │     │ │
│   │   │  }                                                          │     │ │
│   │   │                                                             │     │ │
│   │   └──────────────────┬──────────────────────────────────────────┘     │ │
│   │                      │                                                │ │
│   │           to DELTA_AGGREGATOR (see F79)                               │ │
│   │                      │                                                │ │
│   │                      ▼                                                │ │
│   │                K0_K1_BRIDGE                                           │ │
│   └───────────────────────────────────────────────────────────────────────┘ │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

#### F79: Delta Aggregator → K0 Command Flow

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                  F79: DELTA AGGREGATOR → K0 COMMAND FLOW                    │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│   Time-window batching to reduce K0 write amplification                     │
│                                                                             │
│   ┌───────────────────────────────────────────────────────────────────────┐ │
│   │                                                                       │ │
│   │   MEMORY_WRITER_AGENTS                                                │ │
│   │          │                                                            │ │
│   │   agent deltas (high frequency)                                       │ │
│   │          │                                                            │ │
│   │          ▼                                                            │ │
│   │   ┌─────────────────────────────────────────────────────────────┐     │ │
│   │   │            DELTA_AGGREGATOR                                 │     │ │
│   │   │            Time-Window Batching                             │     │ │
│   │   ├─────────────────────────────────────────────────────────────┤     │ │
│   │   │                                                             │     │ │
│   │   │  Batching Logic:                                            │     │ │
│   │   │  ┌─────────────────────────────────────────────────────┐    │     │ │
│   │   │  │  t=0ms   t=50ms  t=100ms  t=200ms  t=250ms [FLUSH]  │    │     │ │
│   │   │  │    │       │        │        │        │             │    │     │ │
│   │   │  │    ▼       ▼        ▼        ▼        ▼             │    │     │ │
│   │   │  │  [δ1]    [δ2]     [δ3]     [δ4]   [batch]           │    │     │ │
│   │   │  └─────────────────────────────────────────────────────┘    │     │ │
│   │   │                                                             │     │ │
│   │   │  Aggregation:                                               │     │ │
│   │   │  • Merge duplicate writes to same key                       │     │ │
│   │   │  • Collapse sequential updates                              │     │ │
│   │   │  • Group by target pipeline (P02, P03, P04, P06)            │     │ │
│   │   │                                                             │     │ │
│   │   └──────────────────┬──────────────────────────────────────────┘     │ │
│   │                      │                                                │ │
│   │           batch to K0 (every 250ms)                                   │ │
│   │                      │                                                │ │
│   │                      ▼                                                │ │
│   │   ┌─────────────────────────────────────────────────────────────┐     │ │
│   │   │                    K0_CMD                                   │     │ │
│   │   │            Command Submission Port                          │     │ │
│   │   ├─────────────────────────────────────────────────────────────┤     │ │
│   │   │                                                             │     │ │
│   │   │  submit_command() → PORT_CMD → BUS_DISPATCH                 │     │ │
│   │   │                                                             │     │ │
│   │   └──────────────────┬──────────────────────────────────────────┘     │ │
│   │                      │                                                │ │
│   │           emits event that routes to pipeline                         │ │
│   │                      │                                                │ │
│   │                      ▼                                                │ │
│   │   ┌─────────────────────────────────────────────────────────────┐     │ │
│   │   │              PORT_CMD → BUS_DISPATCH                        │     │ │
│   │   │                     │                                       │     │ │
│   │   │            topic match                                      │     │ │
│   │   │                     │                                       │     │ │
│   │   │                     ▼                                       │     │ │
│   │   │              PIPELINE_ROUTER                                │     │ │
│   │   │        Routes to P02, P03, P04, P06 pipelines               │     │ │
│   │   └─────────────────────────────────────────────────────────────┘     │ │
│   └───────────────────────────────────────────────────────────────────────┘ │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

#### F80: K0 P02 Episodic Write Flow

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                    F80: K0 P02 EPISODIC WRITE FLOW                          │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│   P02 pipeline handles episodic memory writes                               │
│                                                                             │
│   ┌───────────────────────────────────────────────────────────────────────┐ │
│   │                                                                       │ │
│   │   PIPELINE_ROUTER                                                     │ │
│   │          │                                                            │ │
│   │   P02 trigger (episodic write command)                                │ │
│   │          │                                                            │ │
│   │          ▼                                                            │ │
│   │   ┌─────────────────────────────────────────────────────────────┐     │ │
│   │   │                PIPELINE_P02                                 │     │ │
│   │   │            Episodic Memory Pipeline                         │     │ │
│   │   ├─────────────────────────────────────────────────────────────┤     │ │
│   │   │                                                             │     │ │
│   │   │  P02 Operations:                                            │     │ │
│   │   │  1. Validate envelope schema                                │     │ │
│   │   │  2. Extract episodic content                                │     │ │
│   │   │  3. Compute embeddings (if needed)                          │     │ │
│   │   │  4. Write to WAL backend                                    │     │ │
│   │   │  5. Index in vector store                                   │     │ │
│   │   │                                                             │     │ │
│   │   │  Storage Backends:                                          │     │ │
│   │   │  ┌──────────────┐   ┌──────────────┐   ┌──────────────┐     │     │ │
│   │   │  │ WAL_BACKEND  │   │OBJECT_BACKEND│   │VECTOR_DRIVER │     │     │ │
│   │   │  │ (append-only)│   │ (blobs)      │   │ (embeddings) │     │     │ │
│   │   │  └──────────────┘   └──────────────┘   └──────────────┘     │     │ │
│   │   │                                                             │     │ │
│   │   └──────────────────┬──────────────────────────────────────────┘     │ │
│   │                      │                                                │ │
│   │           emit k0.episodic.written                                    │ │
│   │                      │                                                │ │
│   │                      ▼                                                │ │
│   │   ┌─────────────────────────────────────────────────────────────┐     │ │
│   │   │              BUS_DISPATCH                                   │     │ │
│   │   │                     │                                       │     │ │
│   │   │        event: k0.episodic.written.v1                        │     │ │
│   │   │                     │                                       │     │ │
│   │   │              ┌──────┴──────┐                                │     │ │
│   │   │              │             │                                │     │ │
│   │   │              ▼             ▼                                │     │ │
│   │   │        trigger P03    SSE to K1                             │     │ │
│   │   │     (consolidation)  (if subscribed)                        │     │ │
│   │   └─────────────────────────────────────────────────────────────┘     │ │
│   └───────────────────────────────────────────────────────────────────────┘ │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

#### F81: K0 P03 Consolidation Flow

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                    F81: K0 P03 CONSOLIDATION FLOW                           │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│   P03 pipeline consolidates memories (sleep-like processing)                │
│                                                                             │
│   ┌───────────────────────────────────────────────────────────────────────┐ │
│   │                                                                       │ │
│   │   BUS_DISPATCH                                                        │ │
│   │          │                                                            │ │
│   │   trigger P03 (from P02 completion or scheduled)                      │ │
│   │          │                                                            │ │
│   │          ▼                                                            │ │
│   │   ┌─────────────────────────────────────────────────────────────┐     │ │
│   │   │                PIPELINE_P03                                 │     │ │
│   │   │            Memory Consolidation Pipeline                    │     │ │
│   │   ├─────────────────────────────────────────────────────────────┤     │ │
│   │   │                                                             │     │ │
│   │   │  Consolidation Operations:                                  │     │ │
│   │   │  1. Gather related episodic memories                        │     │ │
│   │   │  2. Identify patterns and connections                       │     │ │
│   │   │  3. Update semantic indices                                 │     │ │
│   │   │  4. Compress redundant information                          │     │ │
│   │   │  5. Strengthen important memories                           │     │ │
│   │   │                                                             │     │ │
│   │   │  Consolidation Types:                                       │     │ │
│   │   │  ┌─────────────────────────────────────────────────────┐    │     │ │
│   │   │  │ • Episodic → Semantic (pattern extraction)          │    │     │ │
│   │   │  │ • Temporal clustering (related events)              │    │     │ │
│   │   │  │ • Belief reinforcement (repeated observations)      │    │     │ │
│   │   │  │ • Decay pruning (unused memories)                   │    │     │ │
│   │   │  └─────────────────────────────────────────────────────┘    │     │ │
│   │   │                                                             │     │ │
│   │   └──────────────────┬──────────────────────────────────────────┘     │ │
│   │                      │                                                │ │
│   │           emit k0.memory.consolidated                                 │ │
│   │                      │                                                │ │
│   │                      ▼                                                │ │
│   │   ┌─────────────────────────────────────────────────────────────┐     │ │
│   │   │              PORT_SSE                                       │     │ │
│   │   │                     │                                       │     │ │
│   │   │           SSE event stream                                  │     │ │
│   │   │                     │                                       │     │ │
│   │   │                     ▼                                       │     │ │
│   │   │              K0_SSE → K1 EVENT_BUS                          │     │ │
│   │   │        (notify K1 of consolidation complete)                │     │ │
│   │   └─────────────────────────────────────────────────────────────┘     │ │
│   └───────────────────────────────────────────────────────────────────────┘ │
│                                                                             │
│   Note: P03 runs asynchronously, not blocking conversation                  │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

### 8.2 K0 SSE Event Flow

#### F82: K0 SSE → K1 EventBus Flow

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                    F82: K0 SSE → K1 EVENTBUS FLOW                           │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│   Server-Sent Events from K0 to K1 for real-time notifications              │
│                                                                             │
│   ┌───────────────────────────────────────────────────────────────────────┐ │
│   │                                                                       │ │
│   │   ┌─────────────────────────────────────────────────────────────┐     │ │
│   │   │              K0_SSE_SERVER                                  │     │ │
│   │   │         Proactive Notification Source                       │     │ │
│   │   ├─────────────────────────────────────────────────────────────┤     │ │
│   │   │                                                             │     │ │
│   │   │  K0_SSE_ENDPOINT: /v1/k0/events/stream                      │     │ │
│   │   │                                                             │     │ │
│   │   │  SSE Event Types:                                           │     │ │
│   │   │  • k0.learning.advisory.validated.v1                        │     │ │
│   │   │  • k0.system.proactive.signal.v1                            │     │ │
│   │   │  • k0.episodic.written.v1                                   │     │ │
│   │   │  • k0.memory.consolidated.v1                                │     │ │
│   │   │                                                             │     │ │
│   │   │  SSE_CONNECTION_MGR: Per-Session Connections                │     │ │
│   │   │                                                             │     │ │
│   │   └──────────────────┬──────────────────────────────────────────┘     │ │
│   │                      │                                                │ │
│   │           SSE stream (persistent connection)                          │ │
│   │                      │                                                │ │
│   │                      ▼                                                │ │
│   │   ┌─────────────────────────────────────────────────────────────┐     │ │
│   │   │              K0_K1_BRIDGE                                   │     │ │
│   │   │         SSE Receiver                                        │     │ │
│   │   ├─────────────────────────────────────────────────────────────┤     │ │
│   │   │                                                             │     │ │
│   │   │  1. Receive SSE event                                       │     │ │
│   │   │  2. Parse event type and payload                            │     │ │
│   │   │  3. Map to K1 event topic                                   │     │ │
│   │   │  4. Publish to K1 EVENT_BUS                                 │     │ │
│   │   │                                                             │     │ │
│   │   └──────────────────┬──────────────────────────────────────────┘     │ │
│   │                      │                                                │ │
│   │           K1 event (translated)                                       │ │
│   │                      │                                                │ │
│   │                      ▼                                                │ │
│   │   ┌─────────────────────────────────────────────────────────────┐     │ │
│   │   │              K1 EVENT_BUS                                   │     │ │
│   │   │         Pub/Sub Topics                                      │     │ │
│   │   ├─────────────────────────────────────────────────────────────┤     │ │
│   │   │                                                             │     │ │
│   │   │  Topic Routing:                                             │     │ │
│   │   │  k0.learning.advisory → PROACTIVE_AGENT_SPAWNER             │     │ │
│   │   │  k0.system.proactive  → PROACTIVE_DECISION                  │     │ │
│   │   │  k0.memory.*          → CONCIERGE_FSM (context update)      │     │ │
│   │   │                                                             │     │ │
│   │   └─────────────────────────────────────────────────────────────┘     │ │
│   └───────────────────────────────────────────────────────────────────────┘ │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

#### F83: SSE Trigger → Proactive Decision Flow

```
┌─────────────────────────────────────────────────────────────────────────────┐
│              F83: SSE TRIGGER → PROACTIVE DECISION FLOW                     │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│   K0 SSE events trigger proactive decision-making in K1                     │
│                                                                             │
│   ┌───────────────────────────────────────────────────────────────────────┐ │
│   │                                                                       │ │
│   │   K0_SSE_ENDPOINT                                                     │ │
│   │          │                                                            │ │
│   │   k0.system.proactive.signal.v1                                       │ │
│   │          │                                                            │ │
│   │          ▼                                                            │ │
│   │   ┌─────────────────────────────────────────────────────────────┐     │ │
│   │   │              SSE_TRIGGER                                    │     │ │
│   │   │         From K0 P06 → K1                                    │     │ │
│   │   ├─────────────────────────────────────────────────────────────┤     │ │
│   │   │                                                             │     │ │
│   │   │  Trigger Types:                                             │     │ │
│   │   │  • Scheduled reminder due                                   │     │ │
│   │   │  • Learning advisory validated                              │     │ │
│   │   │  • Context change detected                                  │     │ │
│   │   │  • External event notification                              │     │ │
│   │   │                                                             │     │ │
│   │   └──────────────────┬──────────────────────────────────────────┘     │ │
│   │                      │                                                │ │
│   │           direct SSE                                                  │ │
│   │                      │                                                │ │
│   │                      ▼                                                │ │
│   │   ┌─────────────────────────────────────────────────────────────┐     │ │
│   │   │            PROACTIVE_DECISION                               │     │ │
│   │   │            LLM-Based Analysis                               │     │ │
│   │   ├─────────────────────────────────────────────────────────────┤     │ │
│   │   │                                                             │     │ │
│   │   │  Decision Process:                                          │     │ │
│   │   │  1. Receive SSE trigger payload                             │     │ │
│   │   │  2. Load current user context                               │     │ │
│   │   │  3. LLM analysis: "Should we act on this?"                  │     │ │
│   │   │  4. If yes → check budget gate                              │     │ │
│   │   │  5. If approved → spawn proactive agent                     │     │ │
│   │   │                                                             │     │ │
│   │   │  LLM Prompt Example:                                        │     │ │
│   │   │  "User mentioned dentist visit. A reminder was set.         │     │ │
│   │   │   It's now 1 hour before. Should I remind them?"            │     │ │
│   │   │                                                             │     │ │
│   │   └──────────────────┬──────────────────────────────────────────┘     │ │
│   │                      │                                                │ │
│   │           decision: proceed / skip                                    │ │
│   │                      │                                                │ │
│   │                      ▼                                                │ │
│   │              PROACTIVE_BUDGET_GATE (see F89)                          │ │
│   └───────────────────────────────────────────────────────────────────────┘ │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

### 8.3 Retention & Deletion Flow

#### F84: Session Checkpoint Flow

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                    F84: SESSION CHECKPOINT FLOW                             │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│   Save session state to K0 for persistence and recovery                     │
│                                                                             │
│   ┌───────────────────────────────────────────────────────────────────────┐ │
│   │                                                                       │ │
│   │   SESSIONSTATE_STORE                                                  │ │
│   │          │                                                            │ │
│   │   Session End (user closes, timeout, explicit save)                   │ │
│   │          │                                                            │ │
│   │          ▼                                                            │ │
│   │   ┌─────────────────────────────────────────────────────────────┐     │ │
│   │   │            SESSION CHECKPOINT PROCESS                       │     │ │
│   │   │                                                             │     │ │
│   │   │  1. Serialize HOT + WARM tiers                              │     │ │
│   │   │  2. Include COLD tier pointers                              │     │ │
│   │   │  3. Attach retention policy                                 │     │ │
│   │   │  4. Compute checksum                                        │     │ │
│   │   │                                                             │     │ │
│   │   │  Checkpoint Content:                                        │     │ │
│   │   │  ┌─────────────────────────────────────────────────────┐    │     │ │
│   │   │  │ • user_identity                                     │    │     │ │
│   │   │  │ • beliefs (active + history)                        │    │     │ │
│   │   │  │ • conversation_history                              │    │     │ │
│   │   │  │ • current_topic                                     │    │     │ │
│   │   │  │ • pending_tasks                                     │    │     │ │
│   │   │  │ • retention_policy: GREEN/RED/BLACK                 │    │     │ │
│   │   │  └─────────────────────────────────────────────────────┘    │     │ │
│   │   │                                                             │     │ │
│   │   └──────────────────┬──────────────────────────────────────────┘     │ │
│   │                      │                                                │ │
│   │           checkpoint                                                  │ │
│   │                      │                                                │ │
│   │                      ▼                                                │ │
│   │   ┌─────────────────────────────────────────────────────────────┐     │ │
│   │   │            K0_SESSION_CHECKPOINTS                           │     │ │
│   │   │            Persistent Storage                               │     │ │
│   │   ├─────────────────────────────────────────────────────────────┤     │ │
│   │   │                                                             │     │ │
│   │   │  Storage Details:                                           │     │ │
│   │   │  • Primary: WAL_BACKEND (ordered, recoverable)              │     │ │
│   │   │  • Backup: OBJECT_BACKEND (compressed blobs)                │     │ │
│   │   │                                                             │     │ │
│   │   │  Also stores:                                               │     │ │
│   │   │  ┌──────────────────────────────────────────────────────┐   │     │ │
│   │   │  │ K0_TURN_HISTORY: Individual turn records             │   │     │ │
│   │   │  │ K0_DELTA_BATCHING: Uncommitted deltas                │   │     │ │
│   │   │  └──────────────────────────────────────────────────────┘   │     │ │
│   │   │                                                             │     │ │
│   │   └─────────────────────────────────────────────────────────────┘     │ │
│   └───────────────────────────────────────────────────────────────────────┘ │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

#### F85: Retention Expiry → Automated Deletion Flow

```
┌─────────────────────────────────────────────────────────────────────────────┐
│            F85: RETENTION EXPIRY → AUTOMATED DELETION FLOW                  │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│   Policy-based automatic data retention and cleanup                         │
│                                                                             │
│   ┌───────────────────────────────────────────────────────────────────────┐ │
│   │                                                                       │ │
│   │   ┌─────────────────────────────────────────────────────────────┐     │ │
│   │   │            RETENTION_POLICIES                               │     │ │
│   │   │            Data Classification                              │     │ │
│   │   ├─────────────────────────────────────────────────────────────┤     │ │
│   │   │                                                             │     │ │
│   │   │  ┌────────────┬────────────────────────────────────────┐    │     │ │
│   │   │  │ GREEN      │ Standard retention (90 days)           │    │     │ │
│   │   │  │            │ General conversation data              │    │     │ │
│   │   │  ├────────────┼────────────────────────────────────────┤    │     │ │
│   │   │  │ RED        │ Extended retention (2 years)           │    │     │ │
│   │   │  │            │ Important memories, preferences        │    │     │ │
│   │   │  ├────────────┼────────────────────────────────────────┤    │     │ │
│   │   │  │ BLACK      │ Permanent retention (indefinite)       │    │     │ │
│   │   │  │            │ Critical user data, core identity      │    │     │ │
│   │   │  └────────────┴────────────────────────────────────────┘    │     │ │
│   │   │                                                             │     │ │
│   │   └──────────────────┬──────────────────────────────────────────┘     │ │
│   │                      │                                                │ │
│   │           retention expiry check (scheduled)                          │ │
│   │                      │                                                │ │
│   │                      ▼                                                │ │
│   │   ┌─────────────────────────────────────────────────────────────┐     │ │
│   │   │            AUTOMATED_DELETION                               │     │ │
│   │   │            Policy Enforcement                               │     │ │
│   │   ├─────────────────────────────────────────────────────────────┤     │ │
│   │   │                                                             │     │ │
│   │   │  Deletion Process:                                          │     │ │
│   │   │  1. Scan K0_SESSION_CHECKPOINTS for expired data            │     │ │
│   │   │  2. Check retention policy for each record                  │     │ │
│   │   │  3. If expired → mark for deletion                          │     │ │
│   │   │  4. Move to GRACE_PERIOD (30 days recoverable)              │     │ │
│   │   │  5. After grace → HARD_DELETE (permanent)                   │     │ │
│   │   │                                                             │     │ │
│   │   └──────────────────┬──────────────────────────────────────────┘     │ │
│   │                      │                                                │ │
│   │           ┌──────────┴──────────┐                                     │ │
│   │           │                     │                                     │ │
│   │           ▼                     ▼                                     │ │
│   │   K0_SESSION_CHECKPOINTS   K0_TURN_HISTORY                            │ │
│   │   (session data)           (turn records)                             │ │
│   │                                                                       │ │
│   │                      │                                                │ │
│   │                      ▼                                                │ │
│   │   ┌─────────────────────────────────────────────────────────────┐     │ │
│   │   │            DELETION_AUDIT                                   │     │ │
│   │   │            K0 Receipts Logging                              │     │ │
│   │   │                                                             │     │ │
│   │   │  Tracks: what, when, why deleted                            │     │ │
│   │   │  Metric: retention_deletions_total                          │     │ │
│   │   └─────────────────────────────────────────────────────────────┘     │ │
│   └───────────────────────────────────────────────────────────────────────┘ │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

#### F86: User Deletion → Soft Delete Flow

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                F86: USER DELETION → SOFT DELETE FLOW                        │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│   User-requested data deletion with recovery grace period                   │
│                                                                             │
│   ┌───────────────────────────────────────────────────────────────────────┐ │
│   │                                                                       │ │
│   │   USER (via UI or API)                                                │ │
│   │          │                                                            │ │
│   │   "Delete my data" request                                            │ │
│   │          │                                                            │ │
│   │          ▼                                                            │ │
│   │   ┌─────────────────────────────────────────────────────────────┐     │ │
│   │   │            USER_DELETION                                    │     │ │
│   │   │            Deletion Request Handler                         │     │ │
│   │   ├─────────────────────────────────────────────────────────────┤     │ │
│   │   │                                                             │     │ │
│   │   │  Scope Options:                                             │     │ │
│   │   │  • Delete specific session                                  │     │ │
│   │   │  • Delete date range                                        │     │ │
│   │   │  • Delete all data (account deletion)                       │     │ │
│   │   │                                                             │     │ │
│   │   │  Verification:                                              │     │ │
│   │   │  • Confirm user identity                                    │     │ │
│   │   │  • Log deletion request                                     │     │ │
│   │   │                                                             │     │ │
│   │   └──────────────────┬──────────────────────────────────────────┘     │ │
│   │                      │                                                │ │
│   │           soft delete (mark, don't destroy)                           │ │
│   │                      │                                                │ │
│   │           ┌──────────┴──────────┐                                     │ │
│   │           │                     │                                     │ │
│   │           ▼                     ▼                                     │ │
│   │   ┌─────────────────┐   ┌─────────────────┐                           │ │
│   │   │ K0_SESSION_     │   │ K0_TURN_        │                           │ │
│   │   │ CHECKPOINTS     │   │ HISTORY         │                           │ │
│   │   │                 │   │                 │                           │ │
│   │   │ status: DELETED │   │ status: DELETED │                           │ │
│   │   │ deleted_at: now │   │ deleted_at: now │                           │ │
│   │   └────────┬────────┘   └────────┬────────┘                           │ │
│   │            │                     │                                    │ │
│   │            └──────────┬──────────┘                                    │ │
│   │                       │                                               │ │
│   │                       ▼                                               │ │
│   │   ┌─────────────────────────────────────────────────────────────┐     │ │
│   │   │            GRACE_PERIOD                                     │     │ │
│   │   │            30 Days Recoverable                              │     │ │
│   │   ├─────────────────────────────────────────────────────────────┤     │ │
│   │   │                                                             │     │ │
│   │   │  During Grace Period:                                       │     │ │
│   │   │  • Data not visible to application                          │     │ │
│   │   │  • User can request recovery                                │     │ │
│   │   │  • After 30 days → permanent deletion                       │     │ │
│   │   │                                                             │     │ │
│   │   └─────────────────────────────────────────────────────────────┘     │ │
│   └───────────────────────────────────────────────────────────────────────┘ │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

#### F87: Grace Period Recovery Flow

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                   F87: GRACE PERIOD RECOVERY FLOW                           │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│   User can recover soft-deleted data within 30-day grace period             │
│                                                                             │
│   ┌───────────────────────────────────────────────────────────────────────┐ │
│   │                                                                       │ │
│   │   USER (via UI or API)                                                │ │
│   │          │                                                            │ │
│   │   "Recover my data" request (within 30 days)                          │ │
│   │          │                                                            │ │
│   │          ▼                                                            │ │
│   │   ┌─────────────────────────────────────────────────────────────┐     │ │
│   │   │            GRACE_PERIOD                                     │     │ │
│   │   │            Recovery Handler                                 │     │ │
│   │   ├─────────────────────────────────────────────────────────────┤     │ │
│   │   │                                                             │     │ │
│   │   │  Validation:                                                │     │ │
│   │   │  1. Verify user identity                                    │     │ │
│   │   │  2. Check grace period not expired                          │     │ │
│   │   │  3. Locate soft-deleted records                             │     │ │
│   │   │                                                             │     │ │
│   │   │  If within grace period:                                    │     │ │
│   │   │  ✓ Recover allowed                                          │     │ │
│   │   │                                                             │     │ │
│   │   │  If grace period expired:                                   │     │ │
│   │   │  ✗ Data permanently deleted - cannot recover                │     │ │
│   │   │                                                             │     │ │
│   │   └──────────────────┬──────────────────────────────────────────┘     │ │
│   │                      │                                                │ │
│   │           recovery (within grace period)                              │ │
│   │                      │                                                │ │
│   │           ┌──────────┴──────────┐                                     │ │
│   │           │                     │                                     │ │
│   │           ▼                     ▼                                     │ │
│   │   ┌─────────────────┐   ┌─────────────────┐                           │ │
│   │   │ K0_SESSION_     │   │ K0_TURN_        │                           │ │
│   │   │ CHECKPOINTS     │   │ HISTORY         │                           │ │
│   │   │                 │   │                 │                           │ │
│   │   │ status: ACTIVE  │   │ status: ACTIVE  │                           │ │
│   │   │ restored_at:now │   │ restored_at:now │                           │ │
│   │   └────────┬────────┘   └────────┬────────┘                           │ │
│   │            │                     │                                    │ │
│   │            └──────────┬──────────┘                                    │ │
│   │                       │                                               │ │
│   │                       ▼                                               │ │
│   │   ┌─────────────────────────────────────────────────────────────┐     │ │
│   │   │            DATA RESTORED                                    │     │ │
│   │   │                                                             │     │ │
│   │   │  • Data visible again to application                        │     │ │
│   │   │  • Retention timer reset                                    │     │ │
│   │   │  • Audit trail updated                                      │     │ │
│   │   │                                                             │     │ │
│   │   └─────────────────────────────────────────────────────────────┘     │ │
│   └───────────────────────────────────────────────────────────────────────┘ │
│                                                                             │
│   After 30 days: HARD_DELETE (permanent, irreversible)                      │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## 9. PROACTIVE AGENT FLOWS

### 9.1 Proactive Spawn Flow

#### F88: SSE Event → Proactive Decision Flow

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                F88: SSE EVENT → PROACTIVE DECISION FLOW                     │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│   K0 SSE events trigger proactive behavior evaluation                       │
│                                                                             │
│   ┌───────────────────────────────────────────────────────────────────────┐ │
│   │                                                                       │ │
│   │   K0_SSE_SERVER                                                       │ │
│   │          │                                                            │ │
│   │   SSE Event Types:                                                    │ │
│   │   • k0.learning.advisory.validated.v1                                 │ │
│   │   • k0.system.proactive.signal.v1                                     │ │
│   │          │                                                            │ │
│   │          ▼                                                            │ │
│   │   ┌─────────────────────────────────────────────────────────────┐     │ │
│   │   │              SSE_TRIGGER                                    │     │ │
│   │   │         From K0 P06 → K1                                    │     │ │
│   │   ├─────────────────────────────────────────────────────────────┤     │ │
│   │   │                                                             │     │ │
│   │   │  Event Payload:                                             │     │ │
│   │   │  {                                                          │     │ │
│   │   │    "event_type": "proactive.signal",                        │     │ │
│   │   │    "trigger": "reminder_due",                               │     │ │
│   │   │    "context": {                                             │     │ │
│   │   │      "reminder_id": "rem_123",                              │     │ │
│   │   │      "message": "Dentist appointment in 1 hour"             │     │ │
│   │   │    },                                                       │     │ │
│   │   │    "user_id": "user_456"                                    │     │ │
│   │   │  }                                                          │     │ │
│   │   │                                                             │     │ │
│   │   └──────────────────┬──────────────────────────────────────────┘     │ │
│   │                      │                                                │ │
│   │           direct SSE to decision engine                               │ │
│   │                      │                                                │ │
│   │                      ▼                                                │ │
│   │   ┌─────────────────────────────────────────────────────────────┐     │ │
│   │   │            PROACTIVE_DECISION                               │     │ │
│   │   │            LLM-Based Analysis                               │     │ │
│   │   ├─────────────────────────────────────────────────────────────┤     │ │
│   │   │                                                             │     │ │
│   │   │  Decision Process:                                          │     │ │
│   │   │  1. Load user context from SessionState                     │     │ │
│   │   │  2. Evaluate relevance and timing                           │     │ │
│   │   │  3. LLM decides: act now / defer / skip                     │     │ │
│   │   │                                                             │     │ │
│   │   │  Decision Factors:                                          │     │ │
│   │   │  • User's current activity (busy? idle?)                    │     │ │
│   │   │  • Time of day appropriateness                              │     │ │
│   │   │  • Recent interaction history                               │     │ │
│   │   │  • Proactive budget remaining                               │     │ │
│   │   │                                                             │     │ │
│   │   └──────────────────┬──────────────────────────────────────────┘     │ │
│   │                      │                                                │ │
│   │           decision: proceed / defer / skip                            │ │
│   │                      │                                                │ │
│   │                      ▼                                                │ │
│   │              PROACTIVE_BUDGET_GATE (see F89)                          │ │
│   └───────────────────────────────────────────────────────────────────────┘ │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

#### F89: Proactive Budget Gate Check Flow

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                F89: PROACTIVE BUDGET GATE CHECK FLOW                        │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│   Rate limiting for proactive actions to avoid overwhelming user            │
│                                                                             │
│   ┌───────────────────────────────────────────────────────────────────────┐ │
│   │                                                                       │ │
│   │   PROACTIVE_DECISION                                                  │ │
│   │          │                                                            │ │
│   │   decision: proceed                                                   │ │
│   │          │                                                            │ │
│   │          ▼                                                            │ │
│   │   ┌─────────────────────────────────────────────────────────────┐     │ │
│   │   │            PROACTIVE_BUDGET_GATE                            │     │ │
│   │   │            Check Tokens & Cooldown                          │     │ │
│   │   ├─────────────────────────────────────────────────────────────┤     │ │
│   │   │                                                             │     │ │
│   │   │  Budget Checks:                                             │     │ │
│   │   │                                                             │     │ │
│   │   │  1. Token Budget:                                           │     │ │
│   │   │     ┌─────────────────────────────────────────────────┐     │     │ │
│   │   │     │ Daily proactive token limit: 5,000 tokens       │     │     │ │
│   │   │     │ Current usage: 2,500 tokens                     │     │     │ │
│   │   │     │ This action cost: 500 tokens                    │     │     │ │
│   │   │     │ Result: 2,500 + 500 < 5,000 ✓ PASS              │     │     │ │
│   │   │     └─────────────────────────────────────────────────┘     │     │ │
│   │   │                                                             │     │ │
│   │   │  2. Cooldown Check:                                         │     │ │
│   │   │     ┌─────────────────────────────────────────────────┐     │     │ │
│   │   │     │ Min interval between proactive: 5 minutes       │     │     │ │
│   │   │     │ Last proactive: 10 minutes ago                  │     │     │ │
│   │   │     │ Result: 10 > 5 ✓ PASS                           │     │     │ │
│   │   │     └─────────────────────────────────────────────────┘     │     │ │
│   │   │                                                             │     │ │
│   │   │  3. User Preference Check:                                  │     │ │
│   │   │     ┌─────────────────────────────────────────────────┐     │     │ │
│   │   │     │ User setting: proactive_enabled = true          │     │     │ │
│   │   │     │ Do Not Disturb: false                           │     │     │ │
│   │   │     │ Result: ✓ PASS                                  │     │     │ │
│   │   │     └─────────────────────────────────────────────────┘     │     │ │
│   │   │                                                             │     │ │
│   │   └──────────────────┬──────────────────────────────────────────┘     │ │
│   │                      │                                                │ │
│   │       ┌──────────────┴──────────────┐                                 │ │
│   │       │                             │                                 │ │
│   │       ▼                             ▼                                 │ │
│   │   ┌───────────┐             ┌───────────────┐                         │ │
│   │   │  APPROVE  │             │    REJECT     │                         │ │
│   │   │           │             │               │                         │ │
│   │   │ Proceed   │             │ Log reason    │                         │ │
│   │   │ to spawn  │             │ Defer/Skip    │                         │ │
│   │   └───────────┘             └───────────────┘                         │ │
│   └───────────────────────────────────────────────────────────────────────┘ │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

#### F90: Proactive Agent Spawn via Fabric Flow

```
┌─────────────────────────────────────────────────────────────────────────────┐
│              F90: PROACTIVE AGENT SPAWN VIA FABRIC FLOW                     │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│   Spawn specialized proactive agents via Capability Fabric                  │
│                                                                             │
│   ┌───────────────────────────────────────────────────────────────────────┐ │
│   │                                                                       │ │
│   │   PROACTIVE_BUDGET_GATE                                               │ │
│   │          │                                                            │ │
│   │   APPROVED                                                            │ │
│   │          │                                                            │ │
│   │          ▼                                                            │ │
│   │   ┌─────────────────────────────────────────────────────────────┐     │ │
│   │   │            PROACTIVE_SPAWN                                  │     │ │
│   │   │            Via Capability Fabric                            │     │ │
│   │   ├─────────────────────────────────────────────────────────────┤     │ │
│   │   │                                                             │     │ │
│   │   │  Spawn Command:                                             │     │ │
│   │   │  {                                                          │     │ │
│   │   │    "capability": "agent.spawn",                             │     │ │
│   │   │    "agent_type": "context_updater",                         │     │ │
│   │   │    "context": {...proactive_payload...},                    │     │ │
│   │   │    "priority": "BACKGROUND"                                 │     │ │
│   │   │  }                                                          │     │ │
│   │   │                                                             │     │ │
│   │   └──────────────────┬──────────────────────────────────────────┘     │ │
│   │                      │                                                │ │
│   │           spawn via fabric                                            │ │
│   │                      │                                                │ │
│   │                      ▼                                                │ │
│   │   ┌─────────────────────────────────────────────────────────────┐     │ │
│   │   │            CAPABILITY_FABRIC                                │     │ │
│   │   │                     │                                       │     │ │
│   │   │            Spawn Agents                                     │     │ │
│   │   │                     │                                       │     │ │
│   │   │                     ▼                                       │     │ │
│   │   │            PROACTIVE_AGENTS                                 │     │ │
│   │   └──────────────────────────────────────────────────────────────┘    │ │
│   │                      │                                                │ │
│   │           agent types                                                 │ │
│   │                      │                                                │ │
│   │                      ▼                                                │ │
│   │   ┌─────────────────────────────────────────────────────────────┐     │ │
│   │   │            PROACTIVE_AGENT_TYPES                            │     │ │
│   │   ├─────────────────────────────────────────────────────────────┤     │ │
│   │   │                                                             │     │ │
│   │   │  ContextUpdaterAgent:                                       │     │ │
│   │   │  • Updates user context based on external events            │     │ │
│   │   │  • Refreshes stale information                              │     │ │
│   │   │                                                             │     │ │
│   │   │  LearningEnactorAgent:                                      │     │ │
│   │   │  • Applies validated learning advisories                    │     │ │
│   │   │  • Updates beliefs and preferences                          │     │ │
│   │   │                                                             │     │ │
│   │   │  ReminderAgent:                                             │     │ │
│   │   │  • Delivers scheduled reminders                             │     │ │
│   │   │  • Handles time-sensitive notifications                     │     │ │
│   │   │                                                             │     │ │
│   │   └──────────────────┬──────────────────────────────────────────┘     │ │
│   │                      │                                                │ │
│   │           proactive message to user                                   │ │
│   │                      │                                                │ │
│   │                      ▼                                                │ │
│   │              CONCIERGE_FSM (interrupt → user)                         │ │
│   └───────────────────────────────────────────────────────────────────────┘ │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

### 9.2 Learning Loop Flow

#### F91: Feedback Signal Collection Flow

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                F91: FEEDBACK SIGNAL COLLECTION FLOW                         │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│   Collect signals from agent execution for learning loop                    │
│                                                                             │
│   ┌───────────────────────────────────────────────────────────────────────┐ │
│   │                                                                       │ │
│   │   L4_SUBAGENTS (all sub-agents)                                       │ │
│   │                                                                       │ │
│   │   ┌─────────┐ ┌─────────┐ ┌─────────┐ ┌─────────┐                     │ │
│   │   │ health_ │ │ finance_│ │ travel_ │ │ smart_  │                     │ │
│   │   │ agent   │ │ agent   │ │ agent   │ │ home    │                     │ │
│   │   └────┬────┘ └────┬────┘ └────┬────┘ └────┬────┘                     │ │
│   │        │           │           │           │                          │ │
│   │    execution_results (success, failure, latency, user_reaction)       │ │
│   │        │           │           │           │                          │ │
│   │        └───────────┴─────┬─────┴───────────┘                          │ │
│   │                          │                                            │ │
│   │                          ▼                                            │ │
│   │   ┌─────────────────────────────────────────────────────────────┐     │ │
│   │   │            LEARNING_LOOP_FRAMEWORK                          │     │ │
│   │   │                     │                                       │     │ │
│   │   │            collect signals                                  │     │ │
│   │   │                     │                                       │     │ │
│   │   │                     ▼                                       │     │ │
│   │   │            FEEDBACK_SIGNAL_COLLECTOR                        │     │ │
│   │   └──────────────────────────────────────────────────────────────┘    │ │
│   │                          │                                            │ │
│   │                          ▼                                            │ │
│   │   ┌─────────────────────────────────────────────────────────────┐     │ │
│   │   │            FEEDBACK_SIGNAL_COLLECTOR                        │     │ │
│   │   │            Signal Aggregation                               │     │ │
│   │   ├─────────────────────────────────────────────────────────────┤     │ │
│   │   │                                                             │     │ │
│   │   │  Signal Types Collected:                                    │     │ │
│   │   │  ┌─────────────────────────────────────────────────────┐    │     │ │
│   │   │  │ • Task success/failure rates                        │    │     │ │
│   │   │  │ • User corrections (explicit feedback)              │    │     │ │
│   │   │  │ • User satisfaction signals (implicit)              │    │     │ │
│   │   │  │ • Execution latency patterns                        │    │     │ │
│   │   │  │ • Clarification frequency                           │    │     │ │
│   │   │  │ • Tool usage patterns                                │    │     │ │
│   │   │  └─────────────────────────────────────────────────────┘    │     │ │
│   │   │                                                             │     │ │
│   │   │  Aggregation Window: 1 hour                                 │     │ │
│   │   │                                                             │     │ │
│   │   └──────────────────┬──────────────────────────────────────────┘     │ │
│   │                      │                                                │ │
│   │           aggregated signals                                          │ │
│   │                      │                                                │ │
│   │                      ▼                                                │ │
│   │              DRIFT_DETECTOR (see F92)                                 │ │
│   └───────────────────────────────────────────────────────────────────────┘ │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

#### F92: Drift Detection Flow

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                    F92: DRIFT DETECTION FLOW                                │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│   Detect changes in user behavior or preferences                            │
│                                                                             │
│   ┌───────────────────────────────────────────────────────────────────────┐ │
│   │                                                                       │ │
│   │   FEEDBACK_SIGNAL_COLLECTOR                                           │ │
│   │          │                                                            │ │
│   │   aggregated signals                                                  │ │
│   │          │                                                            │ │
│   │          ▼                                                            │ │
│   │   ┌─────────────────────────────────────────────────────────────┐     │ │
│   │   │            DRIFT_DETECTOR                                   │     │ │
│   │   │            Behavioral Change Detection                      │     │ │
│   │   ├─────────────────────────────────────────────────────────────┤     │ │
│   │   │                                                             │     │ │
│   │   │  Detection Methods:                                         │     │ │
│   │   │                                                             │     │ │
│   │   │  1. Statistical Drift:                                      │     │ │
│   │   │     ┌─────────────────────────────────────────────────┐     │     │ │
│   │   │     │ Compare current metrics vs. baseline            │     │     │ │
│   │   │     │ Threshold: >2σ deviation triggers alert         │     │     │ │
│   │   │     └─────────────────────────────────────────────────┘     │     │ │
│   │   │                                                             │     │ │
│   │   │  2. Preference Drift:                                       │     │ │
│   │   │     ┌─────────────────────────────────────────────────┐     │     │ │
│   │   │     │ User consistently chooses different option      │     │     │ │
│   │   │     │ E.g., always picks "Dr. Jones" not "Dr. Smith"  │     │     │ │
│   │   │     └─────────────────────────────────────────────────┘     │     │ │
│   │   │                                                             │     │ │
│   │   │  3. Temporal Drift:                                         │     │ │
│   │   │     ┌─────────────────────────────────────────────────┐     │     │ │
│   │   │     │ Behavior changes based on time patterns         │     │     │ │
│   │   │     │ E.g., morning vs. evening preferences           │     │     │ │
│   │   │     └─────────────────────────────────────────────────┘     │     │ │
│   │   │                                                             │     │ │
│   │   │  4. Domain Drift:                                           │     │ │
│   │   │     ┌─────────────────────────────────────────────────┐     │     │ │
│   │   │     │ New interest areas emerging                     │     │     │ │
│   │   │     │ E.g., suddenly asking about gardening           │     │     │ │
│   │   │     └─────────────────────────────────────────────────┘     │     │ │
│   │   │                                                             │     │ │
│   │   └──────────────────┬──────────────────────────────────────────┘     │ │
│   │                      │                                                │ │
│   │           drift detected → emit advisory                              │ │
│   │                      │                                                │ │
│   │                      ▼                                                │ │
│   │              ADVISORY_EMITTER (see F93)                               │ │
│   └───────────────────────────────────────────────────────────────────────┘ │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

#### F93: Advisory Emission → K0 P06 Flow

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                F93: ADVISORY EMISSION → K0 P06 FLOW                         │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│   Send learning advisory to K0 for validation and persistence               │
│                                                                             │
│   ┌───────────────────────────────────────────────────────────────────────┐ │
│   │                                                                       │ │
│   │   DRIFT_DETECTOR                                                      │ │
│   │          │                                                            │ │
│   │   drift detected                                                      │ │
│   │          │                                                            │ │
│   │          ▼                                                            │ │
│   │   ┌─────────────────────────────────────────────────────────────┐     │ │
│   │   │            ADVISORY_EMITTER                                 │     │ │
│   │   │            → Sends to K0 P06                                │     │ │
│   │   ├─────────────────────────────────────────────────────────────┤     │ │
│   │   │                                                             │     │ │
│   │   │  Advisory Structure:                                        │     │ │
│   │   │  {                                                          │     │ │
│   │   │    "type": "learning_advisory",                             │     │ │
│   │   │    "drift_type": "preference_drift",                        │     │ │
│   │   │    "observation": {                                         │     │ │
│   │   │      "domain": "health.doctor_preference",                  │     │ │
│   │   │      "old_value": "Dr. Smith",                              │     │ │
│   │   │      "new_value": "Dr. Jones",                              │     │ │
│   │   │      "confidence": 0.85,                                    │     │ │
│   │   │      "evidence_count": 5                                    │     │ │
│   │   │    },                                                       │     │ │
│   │   │    "suggested_action": "update_belief"                      │     │ │
│   │   │  }                                                          │     │ │
│   │   │                                                             │     │ │
│   │   └──────────────────┬──────────────────────────────────────────┘     │ │
│   │                      │                                                │ │
│   │           to K0 P06                                                   │ │
│   │                      │                                                │ │
│   │                      ▼                                                │ │
│   │   ┌─────────────────────────────────────────────────────────────┐     │ │
│   │   │            K0_K1_BRIDGE                                     │     │ │
│   │   │                     │                                       │     │ │
│   │   │            route to P06 pipeline                            │     │ │
│   │   │                     │                                       │     │ │
│   │   │                     ▼                                       │     │ │
│   │   │            PIPELINE_P06 (Learning Advisory Pipeline)        │     │ │
│   │   └──────────────────────────────────────────────────────────────┘    │ │
│   │                          │                                            │ │
│   │                          ▼                                            │ │
│   │   ┌─────────────────────────────────────────────────────────────┐     │ │
│   │   │            K0 PIPELINE_P06                                  │     │ │
│   │   │            Learning Advisory Validation                     │     │ │
│   │   ├─────────────────────────────────────────────────────────────┤     │ │
│   │   │                                                             │     │ │
│   │   │  P06 Processing:                                            │     │ │
│   │   │  1. Validate advisory schema                                │     │ │
│   │   │  2. Check confidence threshold (>0.8)                       │     │ │
│   │   │  3. Verify evidence sufficiency                             │     │ │
│   │   │  4. Store validated advisory                                │     │ │
│   │   │  5. Emit SSE: k0.learning.advisory.validated.v1             │     │ │
│   │   │                                                             │     │ │
│   │   └──────────────────┬──────────────────────────────────────────┘     │ │
│   │                      │                                                │ │
│   │           SSE back to K1 (see F94)                                    │ │
│   │                      │                                                │ │
│   │                      ▼                                                │ │
│   │              K0_SSE → PROACTIVE_AGENT_SPAWNER                         │ │
│   └───────────────────────────────────────────────────────────────────────┘ │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

#### F94: K0 SSE → Proactive Agent Spawner Flow

```
┌─────────────────────────────────────────────────────────────────────────────┐
│              F94: K0 SSE → PROACTIVE AGENT SPAWNER FLOW                     │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│   Validated learning advisory triggers belief update agent                  │
│                                                                             │
│   ┌───────────────────────────────────────────────────────────────────────┐ │
│   │                                                                       │ │
│   │   K0_SSE                                                              │ │
│   │          │                                                            │ │
│   │   k0.learning.advisory.validated.v1                                   │ │
│   │          │                                                            │ │
│   │          ▼                                                            │ │
│   │   ┌─────────────────────────────────────────────────────────────┐     │ │
│   │   │            PROACTIVE_AGENT_SPAWNER                          │     │ │
│   │   │            ← Triggered by SSE from K0                       │     │ │
│   │   ├─────────────────────────────────────────────────────────────┤     │ │
│   │   │                                                             │     │ │
│   │   │  Receive validated advisory:                                │     │ │
│   │   │  {                                                          │     │ │
│   │   │    "advisory_id": "adv_789",                                │     │ │
│   │   │    "status": "validated",                                   │     │ │
│   │   │    "action": "update_belief",                               │     │ │
│   │   │    "target": "health.doctor_preference",                    │     │ │
│   │   │    "new_value": "Dr. Jones"                                 │     │ │
│   │   │  }                                                          │     │ │
│   │   │                                                             │     │ │
│   │   │  Spawner Logic:                                             │     │ │
│   │   │  1. Parse advisory action type                              │     │ │
│   │   │  2. Select appropriate agent type                           │     │ │
│   │   │  3. Request spawn via Capability Fabric                     │     │ │
│   │   │                                                             │     │ │
│   │   └──────────────────┬──────────────────────────────────────────┘     │ │
│   │                      │                                                │ │
│   │           spawn via fabric                                            │ │
│   │                      │                                                │ │
│   │                      ▼                                                │ │
│   │   ┌─────────────────────────────────────────────────────────────┐     │ │
│   │   │            CAPABILITY_FABRIC                                │     │ │
│   │   │                     │                                       │     │ │
│   │   │            spawn LearningEnactorAgent                       │     │ │
│   │   │                     │                                       │     │ │
│   │   │                     ▼                                       │     │ │
│   │   │            LearningEnactorAgent                             │     │ │
│   │   └──────────────────────────────────────────────────────────────┘    │ │
│   │                          │                                            │ │
│   │                          ▼                                            │ │
│   │   ┌─────────────────────────────────────────────────────────────┐     │ │
│   │   │            LearningEnactorAgent                             │     │ │
│   │   │            Apply Validated Learning                         │     │ │
│   │   ├─────────────────────────────────────────────────────────────┤     │ │
│   │   │                                                             │     │ │
│   │   │  Actions:                                                   │     │ │
│   │   │  1. Load current user beliefs from SessionState             │     │ │
│   │   │  2. Apply advisory update                                   │     │ │
│   │   │  3. Emit delta to DELTA_BUS (for Concierge to write)        │     │ │
│   │   │  4. Optionally notify user of learned preference            │     │ │
│   │   │                                                             │     │ │
│   │   │  Example Update:                                            │     │ │
│   │   │  BELIEFS_ACTIVE.health.doctor_preference = "Dr. Jones"      │     │ │
│   │   │                                                             │     │ │
│   │   └──────────────────┬──────────────────────────────────────────┘     │ │
│   │                      │                                                │ │
│   │           belief_update delta → DELTA_BUS                             │ │
│   │                      │                                                │ │
│   │                      ▼                                                │ │
│   │              CONCIERGE_FSM (Single Writer → SessionState)             │ │
│   └───────────────────────────────────────────────────────────────────────┘ │
│                                                                             │
│   Full Learning Loop Complete:                                              │ │
│   Agent execution → Feedback → Drift → Advisory → K0 → SSE → Update        │ │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## 10. CAPABILITY FABRIC FLOWS

### 10.1 Provider Resolution Flow

#### F95: Capability Resolver Selection Flow

```
┌─────────────────────────────────────────────────────────────────────────────┐
│               F95: CAPABILITY RESOLVER SELECTION FLOW                       │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│   Policy-driven selection of capability providers                           │
│                                                                             │
│   ┌───────────────────────────────────────────────────────────────────────┐ │
│   │                                                                       │ │
│   │   CAPABILITY REQUEST (from any component)                             │ │
│   │          │                                                            │ │
│   │   e.g., "calendar.create_event"                                       │ │
│   │          │                                                            │ │
│   │          ▼                                                            │ │
│   │   ┌─────────────────────────────────────────────────────────────┐     │ │
│   │   │            CAPABILITY_RESOLVER                              │     │ │
│   │   │            Provider Selection Engine                        │     │ │
│   │   ├─────────────────────────────────────────────────────────────┤     │ │
│   │   │                                                             │     │ │
│   │   │  Step 1: Query CAPABILITY_REGISTRY                          │     │ │
│   │   │  ┌─────────────────────────────────────────────────────┐    │     │ │
│   │   │  │ Matching providers for "calendar.create_event":     │    │     │ │
│   │   │  │ • google_calendar_provider (score: 0.95)            │    │     │ │
│   │   │  │ • outlook_calendar_provider (score: 0.90)           │    │     │ │
│   │   │  │ • local_calendar_mcp (score: 0.85)                  │    │     │ │
│   │   │  └─────────────────────────────────────────────────────┘    │     │ │
│   │   │                                                             │     │ │
│   │   │  Step 2: Apply Policy Filters                               │     │ │
│   │   │  ┌─────────────────────────────────────────────────────┐    │     │ │
│   │   │  │ AFFECTIVE_ROUTING: User stressed → prefer simple    │    │     │ │
│   │   │  │ COGNITIVE_LOAD_ROUTING: High load → filter complex  │    │     │ │
│   │   │  │ QOS_INTEGRATION: Budget check                       │    │     │ │
│   │   │  │ SECURITY_CONTEXT: Band access check                 │    │     │ │
│   │   │  └─────────────────────────────────────────────────────┘    │     │ │
│   │   │                                                             │     │ │
│   │   │  Step 3: Score and rank                                     │     │ │
│   │   │                                                             │     │ │
│   │   └──────────────────┬──────────────────────────────────────────┘     │ │
│   │                      │                                                │ │
│   │           selected provider                                           │ │
│   │                      │                                                │ │
│   │                      ▼                                                │ │
│   │   ┌─────────────────────────────────────────────────────────────┐     │ │
│   │   │            CAPABILITY_FABRIC                                │     │ │
│   │   │            Route to Selected Provider                       │     │ │
│   │   ├─────────────────────────────────────────────────────────────┤     │ │
│   │   │                                                             │     │ │
│   │   │  Provider Types:                                            │     │ │
│   │   │  ┌──────────────┐ ┌──────────────┐ ┌──────────────┐         │     │ │
│   │   │  │ AGENT_       │ │ TOOL_        │ │ WORKFLOW_    │         │     │ │
│   │   │  │ PROVIDERS    │ │ PROVIDERS    │ │ PROVIDERS    │         │     │ │
│   │   │  │ (58+ agents) │ │ (MCP, K0)    │ │ (DAGs)       │         │     │ │
│   │   │  └──────────────┘ └──────────────┘ └──────────────┘         │     │ │
│   │   │                                                             │     │ │
│   │   └─────────────────────────────────────────────────────────────┘     │ │
│   └───────────────────────────────────────────────────────────────────────┘ │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

#### F96: Provider Matcher → DAG Flow

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                  F96: PROVIDER MATCHER → DAG FLOW                           │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│   Complex tasks compiled into execution DAGs                                │
│                                                                             │
│   ┌───────────────────────────────────────────────────────────────────────┐ │
│   │                                                                       │ │
│   │   WORKFLOW_COMPILER                                                   │ │
│   │          │                                                            │ │
│   │   compile workflow to capability DAG                                  │ │
│   │          │                                                            │ │
│   │          ▼                                                            │ │
│   │   ┌─────────────────────────────────────────────────────────────┐     │ │
│   │   │            PROVIDER_MATCHER                                 │     │ │
│   │   │            Query Capabilities                               │     │ │
│   │   ├─────────────────────────────────────────────────────────────┤     │ │
│   │   │                                                             │     │ │
│   │   │  Input: Workflow steps requiring capabilities               │     │ │
│   │   │  ┌─────────────────────────────────────────────────────┐    │     │ │
│   │   │  │ Step 1: calendar.query_free_slots                   │    │     │ │
│   │   │  │ Step 2: llm.analyze_preferences                     │    │     │ │
│   │   │  │ Step 3: calendar.create_event                       │    │     │ │
│   │   │  │ Step 4: notification.send_confirmation              │    │     │ │
│   │   │  └─────────────────────────────────────────────────────┘    │     │ │
│   │   │                                                             │     │ │
│   │   │  Query CAPABILITY_TYPES for each step                       │     │ │
│   │   │                                                             │     │ │
│   │   └──────────────────┬──────────────────────────────────────────┘     │ │
│   │                      │                                                │ │
│   │           capability matches                                          │ │
│   │                      │                                                │ │
│   │                      ▼                                                │ │
│   │   ┌─────────────────────────────────────────────────────────────┐     │ │
│   │   │            DAG_ENGINE                                       │     │ │
│   │   │            Generate Execution DAG                           │     │ │
│   │   ├─────────────────────────────────────────────────────────────┤     │ │
│   │   │                                                             │     │ │
│   │   │  DAG Structure:                                             │     │ │
│   │   │                                                             │     │ │
│   │   │  ┌─────────────────┐                                        │     │ │
│   │   │  │ Step 1: query   │                                        │     │ │
│   │   │  │ free_slots      │                                        │     │ │
│   │   │  └────────┬────────┘                                        │     │ │
│   │   │           │                                                 │     │ │
│   │   │           ▼                                                 │     │ │
│   │   │  ┌─────────────────┐                                        │     │ │
│   │   │  │ Step 2: analyze │                                        │     │ │
│   │   │  │ preferences     │                                        │     │ │
│   │   │  └────────┬────────┘                                        │     │ │
│   │   │           │                                                 │     │ │
│   │   │           ▼                                                 │     │ │
│   │   │  ┌─────────────────┐                                        │     │ │
│   │   │  │ Step 3: create  │                                        │     │ │
│   │   │  │ event           │                                        │     │ │
│   │   │  └────────┬────────┘                                        │     │ │
│   │   │           │                                                 │     │ │
│   │   │           ▼                                                 │     │ │
│   │   │  ┌─────────────────┐                                        │     │ │
│   │   │  │ Step 4: send    │                                        │     │ │
│   │   │  │ confirmation    │                                        │     │ │
│   │   │  └─────────────────┘                                        │     │ │
│   │   │                                                             │     │ │
│   │   │  With dependencies, parallelization opportunities           │     │ │
│   │   │                                                             │     │ │
│   │   └──────────────────┬──────────────────────────────────────────┘     │ │
│   │                      │                                                │ │
│   │           execution DAG                                               │ │
│   │                      │                                                │ │
│   │                      ▼                                                │ │
│   │              WORKFLOW_RUN_SUPERVISOR (execute DAG)                    │ │
│   └───────────────────────────────────────────────────────────────────────┘ │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

### 10.2 Fabric Policy Engine Flow

#### F97: Affective Routing Flow (Emotion-Aware)

```
┌─────────────────────────────────────────────────────────────────────────────┐
│              F97: AFFECTIVE ROUTING FLOW (Emotion-Aware)                    │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│   User emotional state influences capability selection                      │
│                                                                             │
│   ┌───────────────────────────────────────────────────────────────────────┐ │
│   │                                                                       │ │
│   │   SESSIONSTATE_STORE                                                  │ │
│   │          │                                                            │ │
│   │   AFFECTIVE_NOW (current emotional state)                             │ │
│   │          │                                                            │ │
│   │          ▼                                                            │ │
│   │   ┌─────────────────────────────────────────────────────────────┐     │ │
│   │   │            AFFECTIVE_ROUTING                                │     │ │
│   │   │            Emotion-Aware Selection                          │     │ │
│   │   ├─────────────────────────────────────────────────────────────┤     │ │
│   │   │                                                             │     │ │
│   │   │  Emotional State Analysis:                                  │     │ │
│   │   │  ┌─────────────────────────────────────────────────────┐    │     │ │
│   │   │  │ current_emotion: "stressed"                         │    │     │ │
│   │   │  │ intensity: 0.7                                      │    │     │ │
│   │   │  │ trajectory: "increasing"                            │    │     │ │
│   │   │  └─────────────────────────────────────────────────────┘    │     │ │
│   │   │                                                             │     │ │
│   │   │  Routing Rules:                                             │     │ │
│   │   │  ┌─────────────────────────────────────────────────────┐    │     │ │
│   │   │  │ IF stressed:                                        │    │     │ │
│   │   │  │   • Prefer simpler tools (less choices)             │    │     │ │
│   │   │  │   • Avoid multi-step workflows                      │    │     │ │
│   │   │  │   • Prioritize familiar providers                   │    │     │ │
│   │   │  │                                                     │    │     │ │
│   │   │  │ IF happy/relaxed:                                   │    │     │ │
│   │   │  │   • Can suggest advanced features                   │    │     │ │
│   │   │  │   • Allow exploration of new providers              │    │     │ │
│   │   │  │                                                     │    │     │ │
│   │   │  │ IF frustrated:                                      │    │     │ │
│   │   │  │   • Use most reliable providers                     │    │     │ │
│   │   │  │   • Minimize failure risk                           │    │     │ │
│   │   │  └─────────────────────────────────────────────────────┘    │     │ │
│   │   │                                                             │     │ │
│   │   └──────────────────┬──────────────────────────────────────────┘     │ │
│   │                      │                                                │ │
│   │           emotion-aware selection criteria                            │ │
│   │                      │                                                │ │
│   │                      ▼                                                │ │
│   │              CAPABILITY_RESOLVER (apply as filter)                    │ │
│   └───────────────────────────────────────────────────────────────────────┘ │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

#### F98: Cognitive Load Routing Flow

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                F98: COGNITIVE LOAD ROUTING FLOW                             │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│   User cognitive load affects complexity of offered capabilities            │
│                                                                             │
│   ┌───────────────────────────────────────────────────────────────────────┐ │
│   │                                                                       │ │
│   │   SESSIONSTATE_STORE                                                  │ │
│   │          │                                                            │ │
│   │   CONTROL (cognitive load estimate)                                   │ │
│   │          │                                                            │ │
│   │          ▼                                                            │ │
│   │   ┌─────────────────────────────────────────────────────────────┐     │ │
│   │   │            COGNITIVE_LOAD_ROUTING                           │     │ │
│   │   │            Complexity-Aware Selection                       │     │ │
│   │   ├─────────────────────────────────────────────────────────────┤     │ │
│   │   │                                                             │     │ │
│   │   │  Cognitive Load Indicators:                                 │     │ │
│   │   │  ┌─────────────────────────────────────────────────────┐    │     │ │
│   │   │  │ • Multi-tasking detected (parallel topics)          │    │     │ │
│   │   │  │ • Complex task in progress                          │    │     │ │
│   │   │  │ • Time pressure signals                             │    │     │ │
│   │   │  │ • Confusion indicators (repeated clarifications)    │    │     │ │
│   │   │  │                                                     │    │     │ │
│   │   │  │ Load Level: HIGH (0.8)                              │    │     │ │
│   │   │  └─────────────────────────────────────────────────────┘    │     │ │
│   │   │                                                             │     │ │
│   │   │  Routing Adjustments:                                       │     │ │
│   │   │  ┌─────────────────────────────────────────────────────┐    │     │ │
│   │   │  │ LOW load (0.0-0.3):                                 │    │     │ │
│   │   │  │   • Full feature set available                      │    │     │ │
│   │   │  │   • Allow complex multi-step workflows              │    │     │ │
│   │   │  │                                                     │    │     │ │
│   │   │  │ MEDIUM load (0.3-0.6):                              │    │     │ │
│   │   │  │   • Prefer streamlined options                      │    │     │ │
│   │   │  │   • Suggest but don't require choices               │    │     │ │
│   │   │  │                                                     │    │     │ │
│   │   │  │ HIGH load (0.6-1.0):                                │    │     │ │
│   │   │  │   • Minimize user decisions                         │    │     │ │
│   │   │  │   • Use defaults aggressively                       │    │     │ │
│   │   │  │   • Single-action providers preferred               │    │     │ │
│   │   │  └─────────────────────────────────────────────────────┘    │     │ │
│   │   │                                                             │     │ │
│   │   └──────────────────┬──────────────────────────────────────────┘     │ │
│   │                      │                                                │ │
│   │           complexity-aware selection criteria                         │ │
│   │                      │                                                │ │
│   │                      ▼                                                │ │
│   │              CAPABILITY_RESOLVER (apply as filter)                    │ │
│   └───────────────────────────────────────────────────────────────────────┘ │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

#### F99: QoS Integration Flow (Token Budget)

```
┌─────────────────────────────────────────────────────────────────────────────┐
│               F99: QOS INTEGRATION FLOW (Token Budget)                      │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│   Token budget constraints affect provider selection                        │
│                                                                             │
│   ┌───────────────────────────────────────────────────────────────────────┐ │
│   │                                                                       │ │
│   │   SESSIONSTATE_STORE                                                  │ │
│   │          │                                                            │ │
│   │   CONTEXT_BUDGET (token allocation)                                   │ │
│   │          │                                                            │ │
│   │          ▼                                                            │ │
│   │   ┌─────────────────────────────────────────────────────────────┐     │ │
│   │   │            QOS_INTEGRATION                                  │     │ │
│   │   │            Budget-Aware Selection                           │     │ │
│   │   ├─────────────────────────────────────────────────────────────┤     │ │
│   │   │                                                             │     │ │
│   │   │  Token Budget Status:                                       │     │ │
│   │   │  ┌─────────────────────────────────────────────────────┐    │     │ │
│   │   │  │ Daily budget:     50,000 tokens                     │    │     │ │
│   │   │  │ Used today:       35,000 tokens                     │    │     │ │
│   │   │  │ Remaining:        15,000 tokens                     │    │     │ │
│   │   │  │ Current request:  ~2,000 tokens estimated           │    │     │ │
│   │   │  │ Status: WITHIN BUDGET ✓                             │    │     │ │
│   │   │  └─────────────────────────────────────────────────────┘    │     │ │
│   │   │                                                             │     │ │
│   │   │  QoS Routing Rules:                                         │     │ │
│   │   │  ┌─────────────────────────────────────────────────────┐    │     │ │
│   │   │  │ Budget > 50%:                                       │    │     │ │
│   │   │  │   • Full provider selection                         │    │     │ │
│   │   │  │   • Premium LLMs available                          │    │     │ │
│   │   │  │                                                     │    │     │ │
│   │   │  │ Budget 20-50%:                                      │    │     │ │
│   │   │  │   • Prefer cost-efficient providers                 │    │     │ │
│   │   │  │   • Use smaller models when possible                │    │     │ │
│   │   │  │                                                     │    │     │ │
│   │   │  │ Budget < 20%:                                       │    │     │ │
│   │   │  │   • Critical tasks only                             │    │     │ │
│   │   │  │   • Local providers preferred                       │    │     │ │
│   │   │  │   • May reject non-essential requests               │    │     │ │
│   │   │  └─────────────────────────────────────────────────────┘    │     │ │
│   │   │                                                             │     │ │
│   │   └──────────────────┬──────────────────────────────────────────┘     │ │
│   │                      │                                                │ │
│   │           budget-aware selection criteria                             │ │
│   │                      │                                                │ │
│   │                      ▼                                                │ │
│   │              CAPABILITY_RESOLVER (apply as filter)                    │ │
│   └───────────────────────────────────────────────────────────────────────┘ │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

#### F100: Security Context Flow (Band-Based Access)

```
┌─────────────────────────────────────────────────────────────────────────────┐
│             F100: SECURITY CONTEXT FLOW (Band-Based Access)                 │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│   UltraBERT safety band determines capability access level                  │
│                                                                             │
│   ┌───────────────────────────────────────────────────────────────────────┐ │
│   │                                                                       │ │
│   │   ULTRABERT_SAFETY                                                    │ │
│   │          │                                                            │ │
│   │   safety_band (from 12-head classification)                           │ │
│   │          │                                                            │ │
│   │          ▼                                                            │ │
│   │   ┌─────────────────────────────────────────────────────────────┐     │ │
│   │   │            SECURITY_CONTEXT                                 │     │ │
│   │   │            Band-Based Access Control                        │     │ │
│   │   ├─────────────────────────────────────────────────────────────┤     │ │
│   │   │                                                             │     │ │
│   │   │  Safety Band Levels:                                        │     │ │
│   │   │  ┌─────────────────────────────────────────────────────┐    │     │ │
│   │   │  │ BAND_GREEN (safe):                                  │    │     │ │
│   │   │  │   • Full capability access                          │    │     │ │
│   │   │  │   • All providers available                         │    │     │ │
│   │   │  │                                                     │    │     │ │
│   │   │  │ BAND_YELLOW (caution):                              │    │     │ │
│   │   │  │   • Enhanced logging enabled                        │    │     │ │
│   │   │  │   • Sensitive capabilities require confirmation     │    │     │ │
│   │   │  │   • Financial/health tools monitored                │    │     │ │
│   │   │  │                                                     │    │     │ │
│   │   │  │ BAND_RED (restricted):                              │    │     │ │
│   │   │  │   • Limited to safe capabilities only               │    │     │ │
│   │   │  │   • No external API calls                           │    │     │ │
│   │   │  │   • Human oversight required                        │    │     │ │
│   │   │  │                                                     │    │     │ │
│   │   │  │ BAND_CRISIS:                                        │    │     │ │
│   │   │  │   • Only safety protocols active                    │    │     │ │
│   │   │  │   • Route to SAFETY_MAILBOX immediately             │    │     │ │
│   │   │  └─────────────────────────────────────────────────────┘    │     │ │
│   │   │                                                             │     │ │
│   │   │  Capability Classification:                                 │     │ │
│   │   │  ┌────────────────┬────────────────────────────────────┐    │     │ │
│   │   │  │ Safe           │ weather.query, timer.set           │    │     │ │
│   │   │  │ Moderate       │ calendar.create, email.send        │    │     │ │
│   │   │  │ Sensitive      │ finance.transfer, health.records   │    │     │ │
│   │   │  │ Restricted     │ admin.delete, security.override    │    │     │ │
│   │   │  └────────────────┴────────────────────────────────────┘    │     │ │
│   │   │                                                             │     │ │
│   │   └──────────────────┬──────────────────────────────────────────┘     │ │
│   │                      │                                                │ │
│   │           band-based access criteria                                  │ │
│   │                      │                                                │ │
│   │                      ▼                                                │ │
│   │              CAPABILITY_RESOLVER (apply as filter)                    │ │
│   └───────────────────────────────────────────────────────────────────────┘ │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

### 10.3 MCP Discovery & Registration Flow

#### F101: Local MCP Server Discovery Flow

```
┌─────────────────────────────────────────────────────────────────────────────┐
│               F101: LOCAL MCP SERVER DISCOVERY FLOW                         │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│   Discover and register local MCP (Model Context Protocol) servers          │
│                                                                             │
│   ┌───────────────────────────────────────────────────────────────────────┐ │
│   │                                                                       │ │
│   │   ┌─────────────────────────────────────────────────────────────┐     │ │
│   │   │            MCP_TOOL_DISCOVERY                               │     │ │
│   │   │            Discovery Engine                                 │     │ │
│   │   ├─────────────────────────────────────────────────────────────┤     │ │
│   │   │                                                             │     │ │
│   │   │  Discovery Methods:                                         │     │ │
│   │   │  • Scan configured paths                                    │     │ │
│   │   │  • Check running processes                                  │     │ │
│   │   │  • Query mDNS/service discovery                             │     │ │
│   │   │  • Read config files                                        │     │ │
│   │   │                                                             │     │ │
│   │   └──────────────────┬──────────────────────────────────────────┘     │ │
│   │                      │                                                │ │
│   │           discover tools                                              │ │
│   │                      │                                                │ │
│   │                      ▼                                                │ │
│   │   ┌─────────────────────────────────────────────────────────────┐     │ │
│   │   │            LOCAL_MCP_SERVERS                                │     │ │
│   │   │            Local Tool Servers                               │     │ │
│   │   ├─────────────────────────────────────────────────────────────┤     │ │
│   │   │                                                             │     │ │
│   │   │  Discovered Servers:                                        │     │ │
│   │   │  ┌─────────────────────────────────────────────────────┐    │     │ │
│   │   │  │ local://filesystem-mcp (port 3001)                  │    │     │ │
│   │   │  │   └─ capabilities: file.read, file.write, file.list │    │     │ │
│   │   │  │                                                     │    │     │ │
│   │   │  │ local://calendar-mcp (port 3002)                    │    │     │ │
│   │   │  │   └─ capabilities: calendar.*, events.*             │    │     │ │
│   │   │  │                                                     │    │     │ │
│   │   │  │ local://browser-mcp (port 3003)                     │    │     │ │
│   │   │  │   └─ capabilities: browser.navigate, browser.scrape │    │     │ │
│   │   │  └─────────────────────────────────────────────────────┘    │     │ │
│   │   │                                                             │     │ │
│   │   └──────────────────┬──────────────────────────────────────────┘     │ │
│   │                      │                                                │ │
│   │           expose capabilities                                         │ │
│   │                      │                                                │ │
│   │                      ▼                                                │ │
│   │   ┌─────────────────────────────────────────────────────────────┐     │ │
│   │   │            MCP_CAPABILITY_REGISTRAR                         │     │ │
│   │   │            Register with Fabric                             │     │ │
│   │   ├─────────────────────────────────────────────────────────────┤     │ │
│   │   │                                                             │     │ │
│   │   │  Registration:                                              │     │ │
│   │   │  1. Validate MCP schema compliance                          │     │ │
│   │   │  2. Generate capability descriptors                         │     │ │
│   │   │  3. Register with CAPABILITY_REGISTRY                       │     │ │
│   │   │  4. Health check and monitoring setup                       │     │ │
│   │   │                                                             │     │ │
│   │   └──────────────────┬──────────────────────────────────────────┘     │ │
│   │                      │                                                │ │
│   │           register capabilities                                       │ │
│   │                      │                                                │ │
│   │                      ▼                                                │ │
│   │              CAPABILITY_REGISTRY (tools available)                    │ │
│   └───────────────────────────────────────────────────────────────────────┘ │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

#### F102: Remote MCP Server → K0 Proxy Flow

```
┌─────────────────────────────────────────────────────────────────────────────┐
│             F102: REMOTE MCP SERVER → K0 PROXY FLOW                         │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│   Remote MCP servers accessed via K0 connector proxy                        │
│                                                                             │
│   ┌───────────────────────────────────────────────────────────────────────┐ │
│   │                                                                       │ │
│   │   MCP_TOOL_DISCOVERY                                                  │ │
│   │          │                                                            │ │
│   │   discover remote tools                                               │ │
│   │          │                                                            │ │
│   │          ▼                                                            │ │
│   │   ┌─────────────────────────────────────────────────────────────┐     │ │
│   │   │            REMOTE_MCP_SERVERS                               │     │ │
│   │   │            Cloud-Based Tool Servers                         │     │ │
│   │   ├─────────────────────────────────────────────────────────────┤     │ │
│   │   │                                                             │     │ │
│   │   │  Remote Servers:                                            │     │ │
│   │   │  ┌─────────────────────────────────────────────────────┐    │     │ │
│   │   │  │ https://api.example.com/mcp/google-workspace        │    │     │ │
│   │   │  │ https://api.example.com/mcp/slack-integration       │    │     │ │
│   │   │  │ https://api.example.com/mcp/github-tools            │    │     │ │
│   │   │  └─────────────────────────────────────────────────────┘    │     │ │
│   │   │                                                             │     │ │
│   │   │  Security Concerns:                                         │     │ │
│   │   │  • Authentication required                                  │     │ │
│   │   │  • Rate limiting                                            │     │ │
│   │   │  • Data privacy                                             │     │ │
│   │   │                                                             │     │ │
│   │   └──────────────────┬──────────────────────────────────────────┘     │ │
│   │                      │                                                │ │
│   │           cloud routing                                               │ │
│   │                      │                                                │ │
│   │                      ▼                                                │ │
│   │   ┌─────────────────────────────────────────────────────────────┐     │ │
│   │   │            K0_CONNECTOR_PROXY                               │     │ │
│   │   │            Auth + Cache                                     │     │ │
│   │   ├─────────────────────────────────────────────────────────────┤     │ │
│   │   │                                                             │     │ │
│   │   │  Proxy Services:                                            │     │ │
│   │   │  ┌─────────────────────────────────────────────────────┐    │     │ │
│   │   │  │ Authentication:                                     │    │     │ │
│   │   │  │ • OAuth token management                            │    │     │ │
│   │   │  │ • API key storage (secure)                          │    │     │ │
│   │   │  │ • Token refresh handling                            │    │     │ │
│   │   │  │                                                     │    │     │ │
│   │   │  │ Caching:                                            │    │     │ │
│   │   │  │ • Response caching (configurable TTL)               │    │     │ │
│   │   │  │ • Schema caching                                    │    │     │ │
│   │   │  │                                                     │    │     │ │
│   │   │  │ Security:                                           │    │     │ │
│   │   │  │ • Request signing                                   │    │     │ │
│   │   │  │ • Audit logging                                     │    │     │ │
│   │   │  │ • Rate limit enforcement                            │    │     │ │
│   │   │  └─────────────────────────────────────────────────────┘    │     │ │
│   │   │                                                             │     │ │
│   │   └──────────────────┬──────────────────────────────────────────┘     │ │
│   │                      │                                                │ │
│   │           authenticated + cached                                      │ │
│   │                      │                                                │ │
│   │                      ▼                                                │ │
│   │              MCP_CAPABILITY_REGISTRAR                                 │ │
│   └───────────────────────────────────────────────────────────────────────┘ │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

#### F103: MCP Capability Registration Flow

```
┌─────────────────────────────────────────────────────────────────────────────┐
│              F103: MCP CAPABILITY REGISTRATION FLOW                         │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│   Final registration of MCP capabilities into Fabric                        │
│                                                                             │
│   ┌───────────────────────────────────────────────────────────────────────┐ │
│   │                                                                       │ │
│   │   LOCAL_MCP_SERVERS + K0_CONNECTOR_PROXY                              │ │
│   │          │                                                            │ │
│   │   expose capabilities                                                 │ │
│   │          │                                                            │ │
│   │          ▼                                                            │ │
│   │   ┌─────────────────────────────────────────────────────────────┐     │ │
│   │   │            MCP_CAPABILITY_REGISTRAR                         │     │ │
│   │   │            Registration Pipeline                            │     │ │
│   │   ├─────────────────────────────────────────────────────────────┤     │ │
│   │   │                                                             │     │ │
│   │   │  Registration Steps:                                        │     │ │
│   │   │                                                             │     │ │
│   │   │  Step 1: Schema Validation                                  │     │ │
│   │   │  ┌─────────────────────────────────────────────────────┐    │     │ │
│   │   │  │ • Validate MCP JSON Schema                          │    │     │ │
│   │   │  │ • Check tool definitions                            │    │     │ │
│   │   │  │ • Verify parameter types                            │    │     │ │
│   │   │  └─────────────────────────────────────────────────────┘    │     │ │
│   │   │                                                             │     │ │
│   │   │  Step 2: Capability Descriptor Generation                   │     │ │
│   │   │  ┌─────────────────────────────────────────────────────┐    │     │ │
│   │   │  │ {                                                   │    │     │ │
│   │   │  │   "capability_id": "mcp.calendar.create_event",     │    │     │ │
│   │   │  │   "provider": "local-calendar-mcp",                 │    │     │ │
│   │   │  │   "version": "1.2.0",                               │    │     │ │
│   │   │  │   "input_schema": {...},                            │    │     │ │
│   │   │  │   "output_schema": {...},                           │    │     │ │
│   │   │  │   "security_level": "moderate",                     │    │     │ │
│   │   │  │   "estimated_tokens": 500                           │    │     │ │
│   │   │  │ }                                                   │    │     │ │
│   │   │  └─────────────────────────────────────────────────────┘    │     │ │
│   │   │                                                             │     │ │
│   │   │  Step 3: Health Check Setup                                 │     │ │
│   │   │  ┌─────────────────────────────────────────────────────┐    │     │ │
│   │   │  │ • Periodic health pings                             │    │     │ │
│   │   │  │ • Latency monitoring                                │    │     │ │
│   │   │  │ • Availability tracking                             │    │     │ │
│   │   │  └─────────────────────────────────────────────────────┘    │     │ │
│   │   │                                                             │     │ │
│   │   └──────────────────┬──────────────────────────────────────────┘     │ │
│   │                      │                                                │ │
│   │           register capabilities                                       │ │
│   │                      │                                                │ │
│   │                      ▼                                                │ │
│   │   ┌─────────────────────────────────────────────────────────────┐     │ │
│   │   │            CAPABILITY_REGISTRY                              │     │ │
│   │   │            Central Registry                                 │     │ │
│   │   ├─────────────────────────────────────────────────────────────┤     │ │
│   │   │                                                             │     │ │
│   │   │  Registry Contents:                                         │     │ │
│   │   │  ┌─────────────────────────────────────────────────────┐    │     │ │
│   │   │  │ CAPABILITY_TYPES:                                   │    │     │ │
│   │   │  │ • agent.* (58+ agent capabilities)                  │    │     │ │
│   │   │  │ • tool.* (MCP + K0 tools)                           │    │     │ │
│   │   │  │ • workflow.* (DAG-based workflows)                  │    │     │ │
│   │   │  │ • llm.* (model access)                              │    │     │ │
│   │   │  └─────────────────────────────────────────────────────┘    │     │ │
│   │   │                                                             │     │ │
│   │   └──────────────────┬──────────────────────────────────────────┘     │ │
│   │                      │                                                │ │
│   │           create providers                                            │ │
│   │                      │                                                │ │
│   │                      ▼                                                │ │
│   │   ┌─────────────────────────────────────────────────────────────┐     │ │
│   │   │            MCP_PROVIDER_FACTORY                             │     │ │
│   │   │            Create Providers                                 │     │ │
│   │   │                     │                                       │     │ │
│   │   │                     ▼                                       │     │ │
│   │   │            TOOL_PROVIDERS (ready for use)                   │     │ │
│   │   └─────────────────────────────────────────────────────────────┘     │ │
│   └───────────────────────────────────────────────────────────────────────┘ │
│                                                                             │
│   Result: MCP tools available via CAPABILITY_FABRIC                         │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## 11. MODEL GATEWAY FLOWS

### 11.1 LLM Access Flow

- [x] **F104: Model Router Load Balancing Flow**
- [x] **F105: Model Cache Hit/Miss Flow**
- [x] **F106: LLM Provider Routing Flow** (OpenAI, Anthropic, etc.)

### 11.2 LLM Consumer Flows

- [x] **F107: Concierge LLM Inference Flow**
- [x] **F108: Planner LLM Inference Flow**
- [x] **F109: Memory Writer LLM Inference Flow**
- [x] **F110: Solution Validator LLM Flow**
- [x] **F111: Proactive Decision LLM Flow**

---

### F104: Model Router Load Balancing Flow

**Trigger:** Any LLM consumer requests inference
**Outcome:** Request routed to optimal provider with load balancing and fallback

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                   F104: MODEL ROUTER LOAD BALANCING FLOW                    │
│                                                                             │
│   LLM Consumers: CONCIERGE_FSM, PLANNER_AGENT, DYNAMIC_AGENTS,              │
│                  MEMORY_WRITER_AGENTS, PROACTIVE_DECISION, SOLUTION_VALIDATOR│
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│   ┌─────────────────────────────────────────────────────────────────────┐   │
│   │                        LLM CONSUMERS                                │   │
│   │  ┌──────────────┐  ┌──────────────┐  ┌──────────────────────────┐  │   │
│   │  │CONCIERGE_FSM │  │PLANNER_AGENT │  │MEMORY_WRITER_AGENTS      │  │   │
│   │  │"LLM Inference"│  │"LLM Inference"│  │"LLM Inference"          │  │   │
│   │  └──────┬───────┘  └──────┬───────┘  └────────────┬─────────────┘  │   │
│   │         │                 │                        │                │   │
│   │  ┌──────┴──────┐  ┌───────┴───────┐  ┌────────────┴────────────┐   │   │
│   │  │DYNAMIC_     │  │PROACTIVE_     │  │SOLUTION_VALIDATOR       │   │   │
│   │  │  AGENTS     │  │  DECISION     │  │"LLM Validation"         │   │   │
│   │  │"LLM Calls"  │  │"LLM Analysis" │  │                         │   │   │
│   │  └──────┬──────┘  └───────┬───────┘  └────────────┬────────────┘   │   │
│   │         │                 │                        │                │   │
│   │         └─────────────────┼────────────────────────┘                │   │
│   │                           │                                         │   │
│   │                           ▼                                         │   │
│   └─────────────────────────────────────────────────────────────────────┘   │
│                               │                                             │
│                               │ inference request                           │
│                               ▼                                             │
│   ┌─────────────────────────────────────────────────────────────────────┐   │
│   │                       MODEL_GATEWAY                                 │   │
│   │  ┌───────────────────────────────────────────────────────────────┐  │   │
│   │  │                      MODEL_ROUTER                             │  │   │
│   │  │               "Load Balancing & Fallback"                     │  │   │
│   │  │                                                               │  │   │
│   │  │  ┌─────────────────────────────────────────────────────────┐  │  │   │
│   │  │  │              Load Balancing Algorithm                   │  │  │   │
│   │  │  │                                                         │  │  │   │
│   │  │  │  1. Evaluate Provider Health                            │  │  │   │
│   │  │  │     - OpenAI: latency, error_rate, availability         │  │  │   │
│   │  │  │     - Anthropic: latency, error_rate, availability      │  │  │   │
│   │  │  │     - Others: latency, error_rate, availability         │  │  │   │
│   │  │  │                                                         │  │  │   │
│   │  │  │  2. Apply Request Characteristics                       │  │  │   │
│   │  │  │     - Token count → provider token limits               │  │  │   │
│   │  │  │     - Model preference → available models               │  │  │   │
│   │  │  │     - Cost tier → pricing constraints                   │  │  │   │
│   │  │  │                                                         │  │  │   │
│   │  │  │  3. Weighted Round Robin Selection                      │  │  │   │
│   │  │  │     weight = health_score * capability_match * cost     │  │  │   │
│   │  │  └─────────────────────────────────────────────────────────┘  │  │   │
│   │  │                           │                                   │  │   │
│   │  │                           ▼                                   │  │   │
│   │  │  ┌─────────────────────────────────────────────────────────┐  │  │   │
│   │  │  │                Fallback Chain                           │  │  │   │
│   │  │  │                                                         │  │  │   │
│   │  │  │  Primary: HUB_OPENAI (GPT-4, GPT-3.5-turbo)             │  │  │   │
│   │  │  │      │                                                  │  │  │   │
│   │  │  │      │ on failure (timeout, rate_limit, error)         │  │  │   │
│   │  │  │      ▼                                                  │  │  │   │
│   │  │  │  Secondary: HUB_ANTHROPIC (Claude-3, Claude-2)          │  │  │   │
│   │  │  │      │                                                  │  │  │   │
│   │  │  │      │ on failure                                       │  │  │   │
│   │  │  │      ▼                                                  │  │  │   │
│   │  │  │  Tertiary: HUB_OTHERS (Google, Meta, etc.)              │  │  │   │
│   │  │  │                                                         │  │  │   │
│   │  │  └─────────────────────────────────────────────────────────┘  │  │   │
│   │  └───────────────────────────────────────────────────────────────┘  │   │
│   │                              │                                      │   │
│   │                              │ routed request                       │   │
│   │                              ▼                                      │   │
│   │  ┌───────────────────────────────────────────────────────────────┐  │   │
│   │  │                      MODEL_METRICS                            │  │   │
│   │  │               "Usage & Performance Tracking"                  │  │   │
│   │  │                                                               │  │   │
│   │  │  Metrics Tracked:                                             │  │   │
│   │  │  - tokens_used (prompt + completion)                          │  │   │
│   │  │  - latency_ms (p50, p95, p99)                                 │  │   │
│   │  │  - error_count by type                                        │  │   │
│   │  │  - cost_usd per request                                       │  │   │
│   │  │  - provider_health_score                                      │  │   │
│   │  └───────────────────────────────────────────────────────────────┘  │   │
│   └─────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
│   Result: Request routed with load balancing, fallback ready               │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

### F105: Model Cache Hit/Miss Flow

**Trigger:** MODEL_ROUTER receives inference request
**Outcome:** Cache hit returns immediately, cache miss routes to HUB_ROUTER

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                       F105: MODEL CACHE HIT/MISS FLOW                       │
│                                                                             │
│   Cache Strategy: Semantic hash of (prompt, model, temperature, params)     │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│   ┌─────────────────────────────────────────────────────────────────────┐   │
│   │                      MODEL_ROUTER                                   │   │
│   │                                                                     │   │
│   │   Incoming Request:                                                 │   │
│   │   {                                                                 │   │
│   │     "model": "gpt-4",                                               │   │
│   │     "messages": [...],                                              │   │
│   │     "temperature": 0.7,                                             │   │
│   │     "max_tokens": 2000                                              │   │
│   │   }                                                                 │   │
│   │                              │                                      │   │
│   │                              │ "check cache"                        │   │
│   │                              ▼                                      │   │
│   └─────────────────────────────────────────────────────────────────────┘   │
│                                  │                                          │
│                                  ▼                                          │
│   ┌─────────────────────────────────────────────────────────────────────┐   │
│   │                       MODEL_CACHE                                   │   │
│   │                    "Response Caching"                               │   │
│   │                                                                     │   │
│   │  ┌───────────────────────────────────────────────────────────────┐  │   │
│   │  │                    Cache Key Generation                       │  │   │
│   │  │                                                               │  │   │
│   │  │  cache_key = sha256(                                          │  │   │
│   │  │    model +                                                    │  │   │
│   │  │    canonical(messages) +  // normalized, trimmed              │  │   │
│   │  │    str(temperature) +     // determinism factor               │  │   │
│   │  │    str(max_tokens)        // output limit                     │  │   │
│   │  │  )                                                            │  │   │
│   │  └───────────────────────────────────────────────────────────────┘  │   │
│   │                              │                                      │   │
│   │                              ▼                                      │   │
│   │  ┌───────────────────────────────────────────────────────────────┐  │   │
│   │  │                     Cache Lookup                              │  │   │
│   │  │                                                               │  │   │
│   │  │         ┌─────────────────┬─────────────────┐                 │  │   │
│   │  │         │                 │                 │                 │  │   │
│   │  │         ▼                 ▼                 │                 │  │   │
│   │  │   ┌──────────┐     ┌──────────┐            │                 │  │   │
│   │  │   │   HIT    │     │   MISS   │            │                 │  │   │
│   │  │   │          │     │          │            │                 │  │   │
│   │  │   │ TTL OK?  │     │ Not in   │            │                 │  │   │
│   │  │   │ temp=0?  │     │ cache    │            │                 │  │   │
│   │  │   └────┬─────┘     └────┬─────┘            │                 │  │   │
│   │  │        │                │                  │                 │  │   │
│   │  │        ▼                ▼                  │                 │  │   │
│   │  │   "cache hit"      "cache miss"            │                 │  │   │
│   │  └───────────────────────────────────────────────────────────────┘  │   │
│   │        │                   │                                        │   │
│   └────────┼───────────────────┼────────────────────────────────────────┘   │
│            │                   │                                            │
│            ▼                   ▼                                            │
│   ┌─────────────────┐   ┌───────────────────────────────────────────────┐   │
│   │  CACHE HIT PATH │   │              CACHE MISS PATH                  │   │
│   │                 │   │                                               │   │
│   │  Return cached  │   │  ┌─────────────────────────────────────────┐  │   │
│   │  response to    │   │  │             HUB_ROUTER                  │  │   │
│   │  MODEL_ROUTER   │   │  │                                         │  │   │
│   │                 │   │  │  Route to selected provider:            │  │   │
│   │  latency: <1ms  │   │  │  - HUB_OPENAI → GPT-4, GPT-3.5          │  │   │
│   │                 │   │  │  - HUB_ANTHROPIC → Claude-3, Claude-2   │  │   │
│   │                 │   │  │  - HUB_OTHERS → Google, Meta, etc.      │  │   │
│   │                 │   │  │                                         │  │   │
│   │                 │   │  └────────────────┬────────────────────────┘  │   │
│   │                 │   │                   │                           │   │
│   │                 │   │                   │ "response"                │   │
│   │                 │   │                   ▼                           │   │
│   │                 │   │  ┌─────────────────────────────────────────┐  │   │
│   │                 │   │  │         Store in Cache                  │  │   │
│   │                 │   │  │                                         │  │   │
│   │                 │   │  │  If temperature == 0 (deterministic):   │  │   │
│   │                 │   │  │    TTL = 24 hours                       │  │   │
│   │                 │   │  │  Else:                                  │  │   │
│   │                 │   │  │    TTL = 1 hour (or no cache)           │  │   │
│   │                 │   │  └─────────────────────────────────────────┘  │   │
│   │                 │   │                   │                           │   │
│   └────────┬────────┘   └───────────────────┼───────────────────────────┘   │
│            │                                │                               │
│            └────────────────┬───────────────┘                               │
│                             │                                               │
│                             ▼                                               │
│   ┌─────────────────────────────────────────────────────────────────────┐   │
│   │                      MODEL_ROUTER                                   │   │
│   │                                                                     │   │
│   │  Response returned to LLM consumer                                  │   │
│   │                                                                     │   │
│   │  ┌───────────────────────────────────────────────────────────────┐  │   │
│   │  │                   MODEL_METRICS                               │  │   │
│   │  │                                                               │  │   │
│   │  │  Track: cache_hit_rate, cache_miss_rate, cache_latency_saved  │  │   │
│   │  └───────────────────────────────────────────────────────────────┘  │   │
│   └─────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
│   Result: Deterministic requests cached, reducing latency and cost          │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

### F106: LLM Provider Routing Flow

**Trigger:** MODEL_CACHE miss → HUB_ROUTER receives request
**Outcome:** Request routed to appropriate LLM provider (OpenAI, Anthropic, etc.)

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                      F106: LLM PROVIDER ROUTING FLOW                        │
│                                                                             │
│   Providers: HUB_OPENAI, HUB_ANTHROPIC, HUB_OTHERS (Google, Meta, etc.)     │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│   ┌─────────────────────────────────────────────────────────────────────┐   │
│   │                        HUB_ROUTER                                   │   │
│   │                                                                     │   │
│   │  Incoming from MODEL_CACHE (miss) or MODEL_ROUTER (fallback)        │   │
│   │                                                                     │   │
│   │  ┌───────────────────────────────────────────────────────────────┐  │   │
│   │  │                  Provider Selection Matrix                    │  │   │
│   │  │                                                               │  │   │
│   │  │  Model Request         →  Provider Routing                    │  │   │
│   │  │  ─────────────────────────────────────────────                │  │   │
│   │  │  gpt-4, gpt-4-turbo    →  HUB_OPENAI                          │  │   │
│   │  │  gpt-3.5-turbo         →  HUB_OPENAI                          │  │   │
│   │  │  claude-3-opus         →  HUB_ANTHROPIC                       │  │   │
│   │  │  claude-3-sonnet       →  HUB_ANTHROPIC                       │  │   │
│   │  │  claude-2.1            →  HUB_ANTHROPIC                       │  │   │
│   │  │  gemini-pro            →  HUB_OTHERS (Google)                 │  │   │
│   │  │  llama-2-70b           →  HUB_OTHERS (Meta)                   │  │   │
│   │  │  mixtral-8x7b          →  HUB_OTHERS (Mistral)                │  │   │
│   │  └───────────────────────────────────────────────────────────────┘  │   │
│   │                              │                                      │   │
│   └──────────────────────────────┼──────────────────────────────────────┘   │
│                                  │                                          │
│         ┌────────────────────────┼────────────────────────┐                 │
│         │                        │                        │                 │
│         ▼                        ▼                        ▼                 │
│   ┌───────────────┐       ┌───────────────┐       ┌───────────────┐         │
│   │  HUB_OPENAI   │       │ HUB_ANTHROPIC │       │  HUB_OTHERS   │         │
│   │               │       │               │       │               │         │
│   │ ┌───────────┐ │       │ ┌───────────┐ │       │ ┌───────────┐ │         │
│   │ │  GPT-4    │ │       │ │ Claude-3  │ │       │ │Google     │ │         │
│   │ │  GPT-4T   │ │       │ │  Opus     │ │       │ │ Gemini-Pro│ │         │
│   │ │  GPT-3.5  │ │       │ │  Sonnet   │ │       │ │Meta       │ │         │
│   │ │           │ │       │ │  Haiku    │ │       │ │ Llama-2   │ │         │
│   │ │           │ │       │ │ Claude-2  │ │       │ │Mistral    │ │         │
│   │ │           │ │       │ │           │ │       │ │ Mixtral   │ │         │
│   │ └───────────┘ │       │ └───────────┘ │       │ └───────────┘ │         │
│   │               │       │               │       │               │         │
│   │ API Config:   │       │ API Config:   │       │ API Config:   │         │
│   │ - api_key     │       │ - api_key     │       │ - api_keys[]  │         │
│   │ - org_id      │       │ - version     │       │ - endpoints[] │         │
│   │ - base_url    │       │ - max_tokens  │       │ - auth_types[]│         │
│   │               │       │               │       │               │         │
│   │ Rate Limits:  │       │ Rate Limits:  │       │ Rate Limits:  │         │
│   │ - 10K TPM     │       │ - 100K TPM    │       │ - varies      │         │
│   │ - 500 RPM     │       │ - 1K RPM      │       │ - per provider│         │
│   └───────┬───────┘       └───────┬───────┘       └───────┬───────┘         │
│           │                       │                       │                 │
│           │                       │                       │                 │
│           └───────────────────────┼───────────────────────┘                 │
│                                   │                                         │
│                                   │ "response"                              │
│                                   ▼                                         │
│   ┌─────────────────────────────────────────────────────────────────────┐   │
│   │                        HUB_ROUTER                                   │   │
│   │                                                                     │   │
│   │  Response Processing:                                               │   │
│   │  ┌───────────────────────────────────────────────────────────────┐  │   │
│   │  │  1. Validate response structure                               │  │   │
│   │  │  2. Extract token usage (prompt + completion)                 │  │   │
│   │  │  3. Calculate cost                                            │  │   │
│   │  │  4. Update provider health metrics                            │  │   │
│   │  │  5. Handle streaming if requested                             │  │   │
│   │  └───────────────────────────────────────────────────────────────┘  │   │
│   │                              │                                      │   │
│   │                              │ "response"                           │   │
│   │                              ▼                                      │   │
│   └─────────────────────────────────────────────────────────────────────┘   │
│                                  │                                          │
│                                  ▼                                          │
│   ┌─────────────────────────────────────────────────────────────────────┐   │
│   │                       MODEL_ROUTER                                  │   │
│   │                                                                     │   │
│   │  Return response to original LLM consumer                           │   │
│   └─────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
│   Result: LLM request completed via appropriate provider                    │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

### F107: Concierge LLM Inference Flow

**Trigger:** CONCIERGE_FSM needs LLM for response generation
**Outcome:** Concierge receives LLM response for user-facing output

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                    F107: CONCIERGE LLM INFERENCE FLOW                       │
│                                                                             │
│   Context: DELIVERING state generates final response with tool results      │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│   ┌─────────────────────────────────────────────────────────────────────┐   │
│   │                      CONCIERGE_FSM                                  │   │
│   │                "FSM-Driven Conversation Conductor"                  │   │
│   │                                                                     │   │
│   │   Current State: DELIVERING                                         │   │
│   │                                                                     │   │
│   │   ┌───────────────────────────────────────────────────────────────┐ │   │
│   │   │              Build LLM Context                                │ │   │
│   │   │                                                               │ │   │
│   │   │  From TOOL_RESULT_BUFFER:                                     │ │   │
│   │   │    - LOW tier: tool_result[] (~500 tokens)                    │ │   │
│   │   │    - MEDIUM/HIGH tier: all tool_results[] (2-8K tokens)       │ │   │
│   │   │                                                               │ │   │
│   │   │  From SessionState:                                           │ │   │
│   │   │    - CONVERSATION_HISTORY (recent turns)                      │ │   │
│   │   │    - AFFECTIVE_NOW (current emotion)                          │ │   │
│   │   │    - PERSONA hints (style adjustments)                        │ │   │
│   │   │                                                               │ │   │
│   │   │  From CONCIERGE_STYLE + CONCIERGE_PERSONA:                    │ │   │
│   │   │    - Tone adjustments from EMOTIONAL_MIRRORING                │ │   │
│   │   │    - Persona hints from user preferences                      │ │   │
│   │   └───────────────────────────────────────────────────────────────┘ │   │
│   │                              │                                      │   │
│   │                              │ "LLM Inference" request              │   │
│   │                              ▼                                      │   │
│   └─────────────────────────────────────────────────────────────────────┘   │
│                                  │                                          │
│                                  ▼                                          │
│   ┌─────────────────────────────────────────────────────────────────────┐   │
│   │                       MODEL_GATEWAY                                 │   │
│   │                                                                     │   │
│   │   Request:                                                          │   │
│   │   {                                                                 │   │
│   │     "consumer": "CONCIERGE_FSM",                                    │   │
│   │     "priority": "REALTIME",  // WFQ priority                        │   │
│   │     "model": "gpt-4",                                               │   │
│   │     "messages": [                                                   │   │
│   │       {"role": "system", "content": "<persona + style>"},           │   │
│   │       {"role": "user", "content": "<user input>"},                  │   │
│   │       {"role": "assistant", "content": "<tool results>"}            │   │
│   │     ],                                                              │   │
│   │     "temperature": 0.7,                                             │   │
│   │     "stream": true  // for PROGRESSING state updates                │   │
│   │   }                                                                 │   │
│   │                              │                                      │   │
│   │                              ▼                                      │   │
│   │   MODEL_ROUTER → MODEL_CACHE → HUB_ROUTER → Provider                │   │
│   │                              │                                      │   │
│   │                              │ streaming response                   │   │
│   │                              ▼                                      │   │
│   └─────────────────────────────────────────────────────────────────────┘   │
│                                  │                                          │
│                                  │ response (streaming)                     │
│                                  ▼                                          │
│   ┌─────────────────────────────────────────────────────────────────────┐   │
│   │                      CONCIERGE_FSM                                  │   │
│   │                                                                     │   │
│   │   ┌───────────────────────────────────────────────────────────────┐ │   │
│   │   │              Process LLM Response                             │ │   │
│   │   │                                                               │ │   │
│   │   │  If streaming:                                                │ │   │
│   │   │    Stream chunks to PROGRESSING → user                        │ │   │
│   │   │                                                               │ │   │
│   │   │  Final response:                                              │ │   │
│   │   │    - DELIVERING → user with "Next Steps" suggestions          │ │   │
│   │   │    - Clear TOOL_RESULT_BUFFER                                 │ │   │
│   │   │    - Transition: DELIVERING → LISTENING                       │ │   │
│   │   │    - Emit: "user.ack"                                         │ │   │
│   │   └───────────────────────────────────────────────────────────────┘ │   │
│   │                                                                     │   │
│   └─────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
│   Result: User receives natural language response with tool results         │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

### F108: Planner LLM Inference Flow

**Trigger:** PLANNER_AGENT Stage 1 (Sketch) or Stage 2 (Expand)
**Outcome:** LLM generates plan sketch or expanded plan with tools

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                      F108: PLANNER LLM INFERENCE FLOW                       │
│                                                                             │
│   Context: 4-Stage Planning Pipeline for HIGH complexity tasks              │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│   ┌─────────────────────────────────────────────────────────────────────┐   │
│   │                       PLANNER_AGENT                                 │   │
│   │                "LLM-Powered Planning (4-Stage Pipeline)"            │   │
│   │                                                                     │   │
│   │   From ORCHESTRATOR_ACTOR: "HIGH: needs planning"                   │   │
│   │                                                                     │   │
│   │   ┌───────────────────────────────────────────────────────────────┐ │   │
│   │   │                    STAGE1_SKETCH                              │ │   │
│   │   │              "LLM-Powered Plan Sketching"                     │ │   │
│   │   │                                                               │ │   │
│   │   │   Build Planning Prompt:                                      │ │   │
│   │   │   - User goal/task description                                │ │   │
│   │   │   - Available capabilities (from CAPABILITY_REGISTRY)         │ │   │
│   │   │   - Constraints (time, budget, permissions)                   │ │   │
│   │   │   - Past similar plans (from K0 recall)                       │ │   │
│   │   │                                                               │ │   │
│   │   │   Expected Output:                                            │ │   │
│   │   │   - High-level step sequence                                  │ │   │
│   │   │   - Estimated complexity per step                             │ │   │
│   │   │   - Dependency graph (DAG structure)                          │ │   │
│   │   └───────────────────────────────────────────────────────────────┘ │   │
│   │                              │                                      │   │
│   │                              │ "LLM Inference" request              │   │
│   │                              ▼                                      │   │
│   └─────────────────────────────────────────────────────────────────────┘   │
│                                  │                                          │
│                                  ▼                                          │
│   ┌─────────────────────────────────────────────────────────────────────┐   │
│   │                       MODEL_GATEWAY                                 │   │
│   │                                                                     │   │
│   │   Request:                                                          │   │
│   │   {                                                                 │   │
│   │     "consumer": "PLANNER_AGENT",                                    │   │
│   │     "priority": "INTERACTIVE",  // WFQ priority                     │   │
│   │     "model": "gpt-4",  // high-capability for planning              │   │
│   │     "messages": [                                                   │   │
│   │       {"role": "system", "content": "<planner system prompt>"},     │   │
│   │       {"role": "user", "content": "<task + capabilities>"}          │   │
│   │     ],                                                              │   │
│   │     "temperature": 0.3,  // lower for structured output             │   │
│   │     "response_format": {"type": "json_object"}                      │   │
│   │   }                                                                 │   │
│   │                              │                                      │   │
│   │                              ▼                                      │   │
│   │   MODEL_ROUTER → MODEL_CACHE → HUB_ROUTER → Provider                │   │
│   │                              │                                      │   │
│   └─────────────────────────────────────────────────────────────────────┘   │
│                                  │                                          │
│                                  │ rough plan (JSON)                        │
│                                  ▼                                          │
│   ┌─────────────────────────────────────────────────────────────────────┐   │
│   │                       PLANNER_AGENT                                 │   │
│   │                                                                     │   │
│   │   ┌───────────────────────────────────────────────────────────────┐ │   │
│   │   │                    STAGE2_EXPAND                              │ │   │
│   │   │            "Tool Selection & Prompt Expansion"                │ │   │
│   │   │                                                               │ │   │
│   │   │   Input: rough plan from Stage 1                              │ │   │
│   │   │                                                               │ │   │
│   │   │   Second LLM Call:                                            │ │   │
│   │   │   - Expand each step with specific tool invocations           │ │   │
│   │   │   - Generate prompts for each tool                            │ │   │
│   │   │   - Add error handling branches                               │ │   │
│   │   │   - Estimate token costs                                      │ │   │
│   │   │                                                               │ │   │
│   │   │   Output: expanded plan → STAGE3_VALIDATE                     │ │   │
│   │   └───────────────────────────────────────────────────────────────┘ │   │
│   │                              │                                      │   │
│   │                              │ "expanded plan with tools"           │   │
│   │                              ▼                                      │   │
│   │   ┌───────────────────────────────────────────────────────────────┐ │   │
│   │   │  STAGE3_VALIDATE → STAGE4_COMMIT → ORCHESTRATOR_ACTOR         │ │   │
│   │   │                                                               │ │   │
│   │   │  Also: STAGE4_COMMIT → K0_K1_BRIDGE (persist plan to K0 WAL)  │ │   │
│   │   └───────────────────────────────────────────────────────────────┘ │   │
│   │                                                                     │   │
│   └─────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
│   Result: Validated, committed plan ready for execution                     │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

### F109: Memory Writer LLM Inference Flow

**Trigger:** MEMORY_WRITER_AGENTS need to summarize/consolidate memories
**Outcome:** LLM-generated memory summaries written to K0

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                   F109: MEMORY WRITER LLM INFERENCE FLOW                    │
│                                                                             │
│   Context: Memory consolidation and summarization for K0 persistence        │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│   ┌─────────────────────────────────────────────────────────────────────┐   │
│   │                    MEMORY_WRITER_AGENTS                             │   │
│   │                                                                     │   │
│   │   Triggered by:                                                     │   │
│   │   - Session end (checkpoint)                                        │   │
│   │   - Memory threshold (too many episodic memories)                   │   │
│   │   - Scheduled consolidation (K0 P03 request)                        │   │
│   │                                                                     │   │
│   │   ┌───────────────────────────────────────────────────────────────┐ │   │
│   │   │              Memory Consolidation Task                        │ │   │
│   │   │                                                               │ │   │
│   │   │   Input Data:                                                 │ │   │
│   │   │   - Recent conversation turns (from CONVERSATION_HISTORY)     │ │   │
│   │   │   - Emotional trajectory (from AFFECTIVE_NOW history)         │ │   │
│   │   │   - Key decisions/outcomes (from tool results)                │ │   │
│   │   │   - User preferences observed                                 │ │   │
│   │   │                                                               │ │   │
│   │   │   Consolidation Goal:                                         │ │   │
│   │   │   - Summarize N episodic memories → 1 semantic memory         │ │   │
│   │   │   - Extract key facts (NER, relations)                        │ │   │
│   │   │   - Preserve emotional significance                           │ │   │
│   │   └───────────────────────────────────────────────────────────────┘ │   │
│   │                              │                                      │   │
│   │                              │ "LLM Inference" request              │   │
│   │                              ▼                                      │   │
│   └─────────────────────────────────────────────────────────────────────┘   │
│                                  │                                          │
│                                  ▼                                          │
│   ┌─────────────────────────────────────────────────────────────────────┐   │
│   │                       MODEL_GATEWAY                                 │   │
│   │                                                                     │   │
│   │   Request:                                                          │   │
│   │   {                                                                 │   │
│   │     "consumer": "MEMORY_WRITER_AGENTS",                             │   │
│   │     "priority": "BACKGROUND",  // WFQ priority (non-urgent)         │   │
│   │     "model": "gpt-3.5-turbo",  // cost-effective for summarization  │   │
│   │     "messages": [                                                   │   │
│   │       {"role": "system", "content": "<memory writer prompt>"},      │   │
│   │       {"role": "user", "content": "<episodic memories to consolidate>"}│   │
│   │     ],                                                              │   │
│   │     "temperature": 0.2,  // low for factual accuracy                │   │
│   │     "response_format": {"type": "json_object"}                      │   │
│   │   }                                                                 │   │
│   │                              │                                      │   │
│   │                              ▼                                      │   │
│   │   MODEL_ROUTER → MODEL_CACHE → HUB_ROUTER → Provider                │   │
│   │                              │                                      │   │
│   └─────────────────────────────────────────────────────────────────────┘   │
│                                  │                                          │
│                                  │ consolidated memory (JSON)               │
│                                  ▼                                          │
│   ┌─────────────────────────────────────────────────────────────────────┐   │
│   │                    MEMORY_WRITER_AGENTS                             │   │
│   │                                                                     │   │
│   │   ┌───────────────────────────────────────────────────────────────┐ │   │
│   │   │              Process LLM Output                               │ │   │
│   │   │                                                               │ │   │
│   │   │   Output Format:                                              │ │   │
│   │   │   {                                                           │ │   │
│   │   │     "summary": "User discussed health goals...",              │ │   │
│   │   │     "key_facts": ["prefers morning workouts", ...],           │ │   │
│   │   │     "emotional_markers": ["positive about progress"],         │ │   │
│   │   │     "relationships": [{"entity": "gym", "relation": "..."}]   │ │   │
│   │   │   }                                                           │ │   │
│   │   └───────────────────────────────────────────────────────────────┘ │   │
│   │                              │                                      │   │
│   │                              │ emit delta to DELTA_BUS              │   │
│   │                              ▼                                      │   │
│   └─────────────────────────────────────────────────────────────────────┘   │
│                                  │                                          │
│                                  ▼                                          │
│   ┌─────────────────────────────────────────────────────────────────────┐   │
│   │                      DELTA_AGGREGATOR                               │   │
│   │                              │                                      │   │
│   │                              ▼                                      │   │
│   │                      K0_K1_BRIDGE                                   │   │
│   │                              │                                      │   │
│   │                              ▼                                      │   │
│   │                   PORT_CMD → PIPELINE_P02                           │   │
│   │                  (Episodic Write to K0)                             │   │
│   └─────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
│   Result: Consolidated memory persisted to K0 for long-term recall          │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

### F110: Solution Validator LLM Flow

**Trigger:** STAGE3_VALIDATE needs LLM to validate plan correctness
**Outcome:** Plan validated or rejected with feedback

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                     F110: SOLUTION VALIDATOR LLM FLOW                       │
│                                                                             │
│   Context: Planner Stage 3 - Rule-Based + LLM Arbiter Validation            │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│   ┌─────────────────────────────────────────────────────────────────────┐   │
│   │                      STAGE3_VALIDATE                                │   │
│   │                "Rule-Based + Arbiter Validation"                    │   │
│   │                                                                     │   │
│   │   Input: Expanded plan from STAGE2_EXPAND                           │   │
│   │                                                                     │   │
│   │   ┌───────────────────────────────────────────────────────────────┐ │   │
│   │   │              Rule-Based Checks (Fast)                         │ │   │
│   │   │                                                               │ │   │
│   │   │   1. Schema validation (JSON structure)                       │ │   │
│   │   │   2. Capability existence check (all tools available)         │ │   │
│   │   │   3. Permission check (security context allows)               │ │   │
│   │   │   4. Budget check (token cost within limits)                  │ │   │
│   │   │   5. Dependency graph validation (no cycles)                  │ │   │
│   │   └───────────────────────────────────────────────────────────────┘ │   │
│   │                              │                                      │   │
│   │                              │ if rules pass → LLM validation       │   │
│   │                              ▼                                      │   │
│   └─────────────────────────────────────────────────────────────────────┘   │
│                                  │                                          │
│                                  ▼                                          │
│   ┌─────────────────────────────────────────────────────────────────────┐   │
│   │                     SOLUTION_VALIDATOR                              │   │
│   │                    "TINY_SANITY_ARBITER"                            │   │
│   │                                                                     │   │
│   │   ┌───────────────────────────────────────────────────────────────┐ │   │
│   │   │              Build Validation Prompt                          │ │   │
│   │   │                                                               │ │   │
│   │   │   Inputs:                                                     │ │   │
│   │   │   - Original user request                                     │ │   │
│   │   │   - Generated plan (steps, tools, dependencies)               │ │   │
│   │   │   - Constraints (from CONSTRAINT_MANAGER)                     │ │   │
│   │   │   - Past similar plans and outcomes (from K0)                 │ │   │
│   │   │                                                               │ │   │
│   │   │   Validation Questions:                                       │ │   │
│   │   │   - Does plan achieve user's stated goal?                     │ │   │
│   │   │   - Are steps in logical order?                               │ │   │
│   │   │   - Are there missing edge cases?                             │ │   │
│   │   │   - Is the plan efficient (no redundant steps)?               │ │   │
│   │   └───────────────────────────────────────────────────────────────┘ │   │
│   │                              │                                      │   │
│   │                              │ "LLM Validation" request             │   │
│   │                              ▼                                      │   │
│   └─────────────────────────────────────────────────────────────────────┘   │
│                                  │                                          │
│                                  ▼                                          │
│   ┌─────────────────────────────────────────────────────────────────────┐   │
│   │                       MODEL_GATEWAY                                 │   │
│   │                                                                     │   │
│   │   Request:                                                          │   │
│   │   {                                                                 │   │
│   │     "consumer": "SOLUTION_VALIDATOR",                               │   │
│   │     "priority": "INTERACTIVE",                                      │   │
│   │     "model": "gpt-4",  // high-capability for reasoning             │   │
│   │     "messages": [                                                   │   │
│   │       {"role": "system", "content": "<validator system prompt>"},   │   │
│   │       {"role": "user", "content": "<plan + goal + constraints>"}    │   │
│   │     ],                                                              │   │
│   │     "temperature": 0.1,  // very low for consistent judgment        │   │
│   │     "response_format": {"type": "json_object"}                      │   │
│   │   }                                                                 │   │
│   │                              │                                      │   │
│   └─────────────────────────────────────────────────────────────────────┘   │
│                                  │                                          │
│                                  │ validation result                        │
│                                  ▼                                          │
│   ┌─────────────────────────────────────────────────────────────────────┐   │
│   │                     SOLUTION_VALIDATOR                              │   │
│   │                                                                     │   │
│   │   ┌───────────────────────────────────────────────────────────────┐ │   │
│   │   │              Process Validation Result                        │ │   │
│   │   │                                                               │ │   │
│   │   │   Output Format:                                              │ │   │
│   │   │   {                                                           │ │   │
│   │   │     "valid": true/false,                                      │ │   │
│   │   │     "confidence": 0.95,                                       │ │   │
│   │   │     "issues": ["step 3 may fail if...", ...],                 │ │   │
│   │   │     "suggestions": ["add error handling for...", ...]         │ │   │
│   │   │   }                                                           │ │   │
│   │   │                                                               │ │   │
│   │   │   If valid=true → STAGE4_COMMIT                               │ │   │
│   │   │   If valid=false → back to STAGE2_EXPAND with feedback        │ │   │
│   │   │   If needs_approval → PLAN_APPROVAL (HIL)                     │ │   │
│   │   └───────────────────────────────────────────────────────────────┘ │   │
│   │                                                                     │   │
│   └─────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
│   Result: Plan validated or iteratively improved until valid                │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

### F111: Proactive Decision LLM Flow

**Trigger:** K0 SSE event triggers PROACTIVE_DECISION analysis
**Outcome:** LLM decides whether to spawn proactive agent

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                    F111: PROACTIVE DECISION LLM FLOW                        │
│                                                                             │
│   Context: K0 SSE triggers proactive analysis for autonomous actions        │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│   ┌─────────────────────────────────────────────────────────────────────┐   │
│   │                     K0_SSE_ENDPOINT                                 │   │
│   │                                                                     │   │
│   │   SSE Event: "learning.advisory.validated"                          │   │
│   │   or: "schedule.trigger.due"                                        │   │
│   │   or: "memory.pattern.detected"                                     │   │
│   │                              │                                      │   │
│   │                              │ "Direct SSE"                         │   │
│   │                              ▼                                      │   │
│   └─────────────────────────────────────────────────────────────────────┘   │
│                                  │                                          │
│                                  ▼                                          │
│   ┌─────────────────────────────────────────────────────────────────────┐   │
│   │                     PROACTIVE_DECISION                              │   │
│   │                                                                     │   │
│   │   ┌───────────────────────────────────────────────────────────────┐ │   │
│   │   │              Build Decision Context                           │ │   │
│   │   │                                                               │ │   │
│   │   │   From SSE Event:                                             │ │   │
│   │   │   - Event type and payload                                    │ │   │
│   │   │   - Source pipeline (P06, P20, etc.)                          │ │   │
│   │   │                                                               │ │   │
│   │   │   From SessionState (if active session):                      │ │   │
│   │   │   - Current user context                                      │ │   │
│   │   │   - Conversation state                                        │ │   │
│   │   │   - User preferences                                          │ │   │
│   │   │                                                               │ │   │
│   │   │   From K0 (historical):                                       │ │   │
│   │   │   - User patterns and habits                                  │ │   │
│   │   │   - Past proactive action outcomes                            │ │   │
│   │   │   - User feedback on similar proactive actions                │ │   │
│   │   └───────────────────────────────────────────────────────────────┘ │   │
│   │                              │                                      │   │
│   │                              │ "LLM Analysis" request               │   │
│   │                              ▼                                      │   │
│   └─────────────────────────────────────────────────────────────────────┘   │
│                                  │                                          │
│                                  ▼                                          │
│   ┌─────────────────────────────────────────────────────────────────────┐   │
│   │                       MODEL_GATEWAY                                 │   │
│   │                                                                     │   │
│   │   Request:                                                          │   │
│   │   {                                                                 │   │
│   │     "consumer": "PROACTIVE_DECISION",                               │   │
│   │     "priority": "BACKGROUND",  // non-blocking                      │   │
│   │     "model": "gpt-3.5-turbo",  // cost-effective for decision       │   │
│   │     "messages": [                                                   │   │
│   │       {"role": "system", "content": "<proactive decision prompt>"},│   │
│   │       {"role": "user", "content": "<event + context + history>"}   │   │
│   │     ],                                                              │   │
│   │     "temperature": 0.3,                                             │   │
│   │     "response_format": {"type": "json_object"}                      │   │
│   │   }                                                                 │   │
│   │                              │                                      │   │
│   └─────────────────────────────────────────────────────────────────────┘   │
│                                  │                                          │
│                                  │ decision result                          │
│                                  ▼                                          │
│   ┌─────────────────────────────────────────────────────────────────────┐   │
│   │                     PROACTIVE_DECISION                              │   │
│   │                                                                     │   │
│   │   ┌───────────────────────────────────────────────────────────────┐ │   │
│   │   │              Process Decision Result                          │ │   │
│   │   │                                                               │ │   │
│   │   │   Output Format:                                              │ │   │
│   │   │   {                                                           │ │   │
│   │   │     "should_act": true/false,                                 │ │   │
│   │   │     "action_type": "reminder|suggestion|alert|...",           │ │   │
│   │   │     "urgency": "low|medium|high",                             │ │   │
│   │   │     "message": "Based on your patterns, you might want...",   │ │   │
│   │   │     "agent_template": "health_agent.yaml",                    │ │   │
│   │   │     "reasoning": "User typically exercises at this time..."   │ │   │
│   │   │   }                                                           │ │   │
│   │   └───────────────────────────────────────────────────────────────┘ │   │
│   │                              │                                      │   │
│   │                              │ if should_act=true                   │   │
│   │                              ▼                                      │   │
│   └─────────────────────────────────────────────────────────────────────┘   │
│                                  │                                          │
│                                  ▼                                          │
│   ┌─────────────────────────────────────────────────────────────────────┐   │
│   │                  PROACTIVE_AGENT_SPAWNER                            │   │
│   │                              │                                      │   │
│   │                              │ "spawn via fabric"                   │   │
│   │                              ▼                                      │   │
│   │                      CAPABILITY_FABRIC                              │   │
│   │                              │                                      │   │
│   │                              ▼                                      │   │
│   │                      AGENT_PROVIDERS                                │   │
│   │                  (spawn proactive agent)                            │   │
│   └─────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
│   Result: Proactive agent spawned if LLM determines action is warranted     │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## 12. EXPERIENCE LAYER FLOWS (Periodic - Every 20-30 Turns)

### 12.1 Emotional Processing Flow

- [x] **F112: Emotional Trajectory Analysis Flow** (turn % 25)
- [x] **F113: Emotional Mirroring → Style Adjustment Flow**
- [x] **F114: Persona Hints Update Flow**

### 12.2 Narrative Weaving Flow

- [x] **F115: Narrative Thread Analysis Flow** (turn % 20)
- [x] **F116: Thread → Narrative Engine Flow**
- [x] **F117: Narrative Arc Update Flow**

### 12.3 Anticipatory Response Flow

- [x] **F118: User Needs Prediction Flow** (turn % 30)
- [x] **F119: Context Prefetch Flow**

---

### F112: Emotional Trajectory Analysis Flow

**Trigger:** turn_count % 25 == 0 (every 25 turns)
**Outcome:** Long-term emotional patterns analyzed for conversation adaptation

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                  F112: EMOTIONAL TRAJECTORY ANALYSIS FLOW                   │
│                                                                             │
│   Trigger: DELIVERING state, turn_count % 25 == 0                           │
│   Purpose: Analyze long-term emotional patterns, not every-turn reactions   │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│   ┌─────────────────────────────────────────────────────────────────────┐   │
│   │                       DELIVERING                                    │   │
│   │                  (CONCIERGE_FSM State)                              │   │
│   │                                                                     │   │
│   │   turn_count = 25, 50, 75, 100, ...                                 │   │
│   │                                                                     │   │
│   │   ┌───────────────────────────────────────────────────────────────┐ │   │
│   │   │              Check Trigger Condition                          │ │   │
│   │   │                                                               │ │   │
│   │   │   if (turn_count % 25 == 0):                                  │ │   │
│   │   │       trigger EMOTIONAL_PROCESSING                            │ │   │
│   │   │                                                               │ │   │
│   │   │   Note: This is periodic, NOT every turn                      │ │   │
│   │   │   Rationale: Emotional patterns emerge over time              │ │   │
│   │   └───────────────────────────────────────────────────────────────┘ │   │
│   │                              │                                      │   │
│   │                              │ "turn_count % 25 == 0"               │   │
│   │                              ▼                                      │   │
│   └─────────────────────────────────────────────────────────────────────┘   │
│                                  │                                          │
│                                  ▼                                          │
│   ┌─────────────────────────────────────────────────────────────────────┐   │
│   │                    EMOTIONAL_PROCESSING                             │   │
│   │                "Analyze emotional trajectory"                       │   │
│   │                                                                     │   │
│   │   ┌───────────────────────────────────────────────────────────────┐ │   │
│   │   │              Gather Emotional History                         │ │   │
│   │   │                                                               │ │   │
│   │   │   From SessionState:                                          │ │   │
│   │   │   ┌─────────────────────────────────────────────────────────┐ │ │   │
│   │   │   │  AFFECTIVE_NOW (last 25 turns)                          │ │ │   │
│   │   │   │                                                         │ │ │   │
│   │   │   │  Turn 1:  valence=0.6, arousal=0.4, emotion="curious"   │ │ │   │
│   │   │   │  Turn 5:  valence=0.3, arousal=0.7, emotion="frustrated"│ │ │   │
│   │   │   │  Turn 10: valence=0.5, arousal=0.5, emotion="neutral"   │ │ │   │
│   │   │   │  Turn 15: valence=0.8, arousal=0.6, emotion="happy"     │ │ │   │
│   │   │   │  Turn 20: valence=0.7, arousal=0.4, emotion="satisfied" │ │ │   │
│   │   │   │  Turn 25: valence=0.9, arousal=0.5, emotion="grateful"  │ │ │   │
│   │   │   └─────────────────────────────────────────────────────────┘ │ │   │
│   │   │                                                               │ │   │
│   │   │   From K0 (long-term):                                        │ │   │
│   │   │   - Historical emotional patterns for this user               │ │   │
│   │   │   - Typical emotional baselines                               │ │   │
│   │   │   - Past session emotional arcs                               │ │   │
│   │   └───────────────────────────────────────────────────────────────┘ │   │
│   │                              │                                      │   │
│   │   ┌───────────────────────────────────────────────────────────────┐ │   │
│   │   │              Compute Trajectory                               │ │   │
│   │   │                                                               │ │   │
│   │   │   Metrics Calculated:                                         │ │   │
│   │   │                                                               │ │   │
│   │   │   1. Trend Direction:                                         │ │   │
│   │   │      valence_trend = slope(valence over 25 turns)             │ │   │
│   │   │      → IMPROVING / STABLE / DECLINING                         │ │   │
│   │   │                                                               │ │   │
│   │   │   2. Volatility:                                              │ │   │
│   │   │      volatility = std_dev(valence)                            │ │   │
│   │   │      → HIGH_VARIANCE / STABLE                                 │ │   │
│   │   │                                                               │ │   │
│   │   │   3. Dominant Emotion:                                        │ │   │
│   │   │      mode(emotions) → most frequent emotion                   │ │   │
│   │   │                                                               │ │   │
│   │   │   4. Arousal Pattern:                                         │ │   │
│   │   │      arousal_avg → ENGAGED / CALM / DISENGAGED                │ │   │
│   │   └───────────────────────────────────────────────────────────────┘ │   │
│   │                              │                                      │   │
│   │                              │ "emotional trajectory"               │   │
│   │                              ▼                                      │   │
│   └─────────────────────────────────────────────────────────────────────┘   │
│                                  │                                          │
│                                  ▼                                          │
│   ┌─────────────────────────────────────────────────────────────────────┐   │
│   │                    EMOTIONAL_MIRRORING                              │   │
│   │               "Adjust conversational tone"                          │   │
│   │                                                                     │   │
│   │   Receives trajectory analysis → generates tone adjustments         │   │
│   │                                                                     │   │
│   │   (See F113 for details)                                            │   │
│   └─────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
│   Result: Emotional trajectory computed for tone/persona adaptation         │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

### F113: Emotional Mirroring → Style Adjustment Flow

**Trigger:** EMOTIONAL_PROCESSING outputs trajectory
**Outcome:** CONCIERGE_STYLE updated with tone adjustments

```
┌─────────────────────────────────────────────────────────────────────────────┐
│               F113: EMOTIONAL MIRRORING → STYLE ADJUSTMENT FLOW             │
│                                                                             │
│   Purpose: Adapt conversational tone based on emotional trajectory          │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│   ┌─────────────────────────────────────────────────────────────────────┐   │
│   │                    EMOTIONAL_PROCESSING                             │   │
│   │                                                                     │   │
│   │   Trajectory Output:                                                │   │
│   │   {                                                                 │   │
│   │     "trend": "IMPROVING",                                           │   │
│   │     "volatility": "STABLE",                                         │   │
│   │     "dominant_emotion": "curious",                                  │   │
│   │     "arousal_pattern": "ENGAGED",                                   │   │
│   │     "valence_avg": 0.7                                              │   │
│   │   }                                                                 │   │
│   │                              │                                      │   │
│   │                              │ "emotional trajectory"               │   │
│   │                              ▼                                      │   │
│   └─────────────────────────────────────────────────────────────────────┘   │
│                                  │                                          │
│                                  ▼                                          │
│   ┌─────────────────────────────────────────────────────────────────────┐   │
│   │                    EMOTIONAL_MIRRORING                              │   │
│   │               "Adjust conversational tone"                          │   │
│   │                                                                     │   │
│   │   ┌───────────────────────────────────────────────────────────────┐ │   │
│   │   │              Mirroring Strategy Matrix                        │ │   │
│   │   │                                                               │ │   │
│   │   │   Trajectory       →  Tone Adjustment                         │ │   │
│   │   │   ────────────────────────────────────────────────            │ │   │
│   │   │   IMPROVING        →  Match positive energy                   │ │   │
│   │   │                       Celebrate progress                      │ │   │
│   │   │                       Encourage momentum                      │ │   │
│   │   │                                                               │ │   │
│   │   │   DECLINING        →  Increase empathy                        │ │   │
│   │   │                       Offer support                           │ │   │
│   │   │                       Reduce task pressure                    │ │   │
│   │   │                                                               │ │   │
│   │   │   HIGH_VARIANCE    →  Stabilize tone                          │ │   │
│   │   │                       Consistent warmth                       │ │   │
│   │   │                       Predictable responses                   │ │   │
│   │   │                                                               │ │   │
│   │   │   DISENGAGED       →  Re-engage with interest                 │ │   │
│   │   │                       Ask engaging questions                  │ │   │
│   │   │                       Offer novelty                           │ │   │
│   │   └───────────────────────────────────────────────────────────────┘ │   │
│   │                              │                                      │   │
│   │                              │ "tone adjustments"                   │   │
│   │                              ▼                                      │   │
│   └─────────────────────────────────────────────────────────────────────┘   │
│                                  │                                          │
│         ┌────────────────────────┴────────────────────────┐                 │
│         │                                                 │                 │
│         ▼                                                 ▼                 │
│   ┌───────────────────────────────┐   ┌───────────────────────────────────┐ │
│   │       CONCIERGE_STYLE         │   │       CONCIERGE_PERSONA           │ │
│   │     "Style Adaptation"        │   │      "Persona Engine"             │ │
│   │                               │   │                                   │ │
│   │  Updated Style Parameters:    │   │  Updated Persona Hints:           │ │
│   │  ┌─────────────────────────┐  │   │  ┌─────────────────────────────┐  │ │
│   │  │ warmth_level: 0.8      │  │   │  │ empathy_mode: "supportive"  │  │ │
│   │  │ formality: 0.3         │  │   │  │ energy_level: "matching"    │  │ │
│   │  │ enthusiasm: 0.7        │  │   │  │ humor_allowed: true         │  │ │
│   │  │ brevity: 0.5           │  │   │  │ directness: 0.6             │  │ │
│   │  │ emoji_usage: "moderate"│  │   │  │ topic_steering: "gentle"    │  │ │
│   │  └─────────────────────────┘  │   │  └─────────────────────────────┘  │ │
│   │                               │   │                                   │ │
│   └───────────────────────────────┘   └───────────────────────────────────┘ │
│                                                                             │
│   ┌─────────────────────────────────────────────────────────────────────┐   │
│   │                      CONCIERGE_FSM                                  │   │
│   │                                                                     │   │
│   │   Next LLM call (DELIVERING) will include:                          │   │
│   │   - Updated CONCIERGE_STYLE in system prompt                        │   │
│   │   - Updated CONCIERGE_PERSONA hints                                 │   │
│   │   - Tone adapted to emotional trajectory                            │   │
│   └─────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
│   Result: Concierge tone adapts to user's emotional journey                 │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

### F114: Persona Hints Update Flow

**Trigger:** EMOTIONAL_MIRRORING computes persona adjustments
**Outcome:** CONCIERGE_PERSONA updated with long-term preference hints

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                     F114: PERSONA HINTS UPDATE FLOW                         │
│                                                                             │
│   Purpose: Update persona based on observed user preferences over time      │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│   ┌─────────────────────────────────────────────────────────────────────┐   │
│   │                    EMOTIONAL_MIRRORING                              │   │
│   │                                                                     │   │
│   │   Computed Persona Adjustments:                                     │   │
│   │   {                                                                 │   │
│   │     "preferred_style": "casual",                                    │   │
│   │     "response_length": "concise",                                   │   │
│   │     "explanation_depth": "detailed_when_asked",                     │   │
│   │     "humor_receptivity": 0.7,                                       │   │
│   │     "formality_preference": 0.3                                     │   │
│   │   }                                                                 │   │
│   │                              │                                      │   │
│   │                              │ "update persona hints"               │   │
│   │                              ▼                                      │   │
│   └─────────────────────────────────────────────────────────────────────┘   │
│                                  │                                          │
│                                  ▼                                          │
│   ┌─────────────────────────────────────────────────────────────────────┐   │
│   │                     CONCIERGE_PERSONA                               │   │
│   │                      "Persona Engine"                               │   │
│   │                                                                     │   │
│   │   ┌───────────────────────────────────────────────────────────────┐ │   │
│   │   │              Persona Hint Categories                          │ │   │
│   │   │                                                               │ │   │
│   │   │   Communication Style:                                        │ │   │
│   │   │   ┌─────────────────────────────────────────────────────────┐ │ │   │
│   │   │   │ - Verbosity: concise | moderate | verbose               │ │ │   │
│   │   │   │ - Formality: casual | professional | adaptive           │ │ │   │
│   │   │   │ - Tone: warm | neutral | enthusiastic                   │ │ │   │
│   │   │   │ - Humor: none | light | frequent                        │ │ │   │
│   │   │   └─────────────────────────────────────────────────────────┘ │ │   │
│   │   │                                                               │ │   │
│   │   │   Interaction Preferences:                                    │ │   │
│   │   │   ┌─────────────────────────────────────────────────────────┐ │ │   │
│   │   │   │ - Proactivity: passive | balanced | proactive           │ │ │   │
│   │   │   │ - Explanation: brief | on_request | always_detailed     │ │ │   │
│   │   │   │ - Confirmation: minimal | moderate | thorough           │ │ │   │
│   │   │   │ - Suggestions: few | moderate | many                    │ │ │   │
│   │   │   └─────────────────────────────────────────────────────────┘ │ │   │
│   │   │                                                               │ │   │
│   │   │   Emotional Responsiveness:                                   │ │   │
│   │   │   ┌─────────────────────────────────────────────────────────┐ │ │   │
│   │   │   │ - Empathy_level: low | medium | high                    │ │ │   │
│   │   │   │ - Mirroring_intensity: subtle | moderate | strong       │ │ │   │
│   │   │   │ - Support_style: practical | emotional | balanced       │ │ │   │
│   │   │   └─────────────────────────────────────────────────────────┘ │ │   │
│   │   └───────────────────────────────────────────────────────────────┘ │   │
│   │                              │                                      │   │
│   │                              │ merge with existing persona          │   │
│   │                              ▼                                      │   │
│   │   ┌───────────────────────────────────────────────────────────────┐ │   │
│   │   │              Persona Persistence                              │ │   │
│   │   │                                                               │ │   │
│   │   │   Session-level: SessionState.PERSONA                         │ │   │
│   │   │   Long-term: K0 via DELTA_BUS → K0_K1_BRIDGE                  │ │   │
│   │   │                                                               │ │   │
│   │   │   Merge Strategy:                                             │ │   │
│   │   │   - New hints weighted higher for recent sessions             │ │   │
│   │   │   - Long-term patterns weighted for stability                 │ │   │
│   │   │   - User explicit preferences always override                 │ │   │
│   │   └───────────────────────────────────────────────────────────────┘ │   │
│   └─────────────────────────────────────────────────────────────────────┘   │
│                                  │                                          │
│                                  │ (optional) persist to K0                 │
│                                  ▼                                          │
│   ┌─────────────────────────────────────────────────────────────────────┐   │
│   │                        DELTA_BUS                                    │   │
│   │                           │                                         │   │
│   │                           ▼                                         │   │
│   │                    DELTA_AGGREGATOR                                 │   │
│   │                           │                                         │   │
│   │                           ▼                                         │   │
│   │                      K0_K1_BRIDGE                                   │   │
│   │                           │                                         │   │
│   │                           ▼                                         │   │
│   │                 PORT_CMD → PIPELINE_P02                             │   │
│   │               (Persist persona to K0)                               │   │
│   └─────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
│   Result: Persona evolves based on long-term emotional patterns             │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

### F115: Narrative Thread Analysis Flow

**Trigger:** turn_count % 20 == 0 (every 20 turns)
**Outcome:** Conversation threads identified and tracked

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                   F115: NARRATIVE THREAD ANALYSIS FLOW                      │
│                                                                             │
│   Trigger: DELIVERING state, turn_count % 20 == 0                           │
│   Purpose: Identify and maintain conversation threads across turns          │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│   ┌─────────────────────────────────────────────────────────────────────┐   │
│   │                       DELIVERING                                    │   │
│   │                  (CONCIERGE_FSM State)                              │   │
│   │                                                                     │   │
│   │   turn_count = 20, 40, 60, 80, ...                                  │   │
│   │                                                                     │   │
│   │   ┌───────────────────────────────────────────────────────────────┐ │   │
│   │   │              Check Trigger Condition                          │ │   │
│   │   │                                                               │ │   │
│   │   │   if (turn_count % 20 == 0):                                  │ │   │
│   │   │       trigger NARRATIVE_WEAVING                               │ │   │
│   │   │                                                               │ │   │
│   │   │   Note: More frequent than emotional (every 20 vs 25)         │ │   │
│   │   │   Rationale: Threads change faster than emotional patterns    │ │   │
│   │   └───────────────────────────────────────────────────────────────┘ │   │
│   │                              │                                      │   │
│   │                              │ "turn_count % 20 == 0"               │   │
│   │                              ▼                                      │   │
│   └─────────────────────────────────────────────────────────────────────┘   │
│                                  │                                          │
│                                  ▼                                          │
│   ┌─────────────────────────────────────────────────────────────────────┐   │
│   │                     NARRATIVE_WEAVING                               │   │
│   │              "Maintain conversation threads"                        │   │
│   │                                                                     │   │
│   │   ┌───────────────────────────────────────────────────────────────┐ │   │
│   │   │              Extract Threads from History                     │ │   │
│   │   │                                                               │ │   │
│   │   │   From CONVERSATION_HISTORY (last 20 turns):                  │ │   │
│   │   │                                                               │ │   │
│   │   │   Turn 1-5:   Topic="meal planning" → Thread A                │ │   │
│   │   │   Turn 6-8:   Topic="grocery budget" → Thread B               │ │   │
│   │   │   Turn 9-12:  Topic="meal planning" → Thread A (resumed)      │ │   │
│   │   │   Turn 13-15: Topic="diet restrictions" → Thread C            │ │   │
│   │   │   Turn 16-20: Topic="weekly menu" → Thread A (continued)      │ │   │
│   │   │                                                               │ │   │
│   │   │   Thread Detection:                                           │ │   │
│   │   │   - Topic clustering (semantic similarity)                    │ │   │
│   │   │   - Entity continuity (same subjects)                         │ │   │
│   │   │   - Goal persistence (unfinished tasks)                       │ │   │
│   │   └───────────────────────────────────────────────────────────────┘ │   │
│   │                              │                                      │   │
│   │   ┌───────────────────────────────────────────────────────────────┐ │   │
│   │   │              Thread Analysis Output                           │ │   │
│   │   │                                                               │ │   │
│   │   │   Active Threads:                                             │ │   │
│   │   │   ┌─────────────────────────────────────────────────────────┐ │ │   │
│   │   │   │ Thread A: "Meal Planning"                               │ │ │   │
│   │   │   │   - Status: ACTIVE                                      │ │ │   │
│   │   │   │   - Turns: [1-5, 9-12, 16-20]                           │ │ │   │
│   │   │   │   - Entities: [recipes, ingredients, schedule]          │ │ │   │
│   │   │   │   - Open goals: [finalize_menu, create_list]            │ │ │   │
│   │   │   │                                                         │ │ │   │
│   │   │   │ Thread B: "Grocery Budget"                              │ │ │   │
│   │   │   │   - Status: PAUSED                                      │ │ │   │
│   │   │   │   - Turns: [6-8]                                        │ │ │   │
│   │   │   │   - Entities: [budget, prices, stores]                  │ │ │   │
│   │   │   │   - Open goals: [set_weekly_budget]                     │ │ │   │
│   │   │   │                                                         │ │ │   │
│   │   │   │ Thread C: "Diet Restrictions"                           │ │ │   │
│   │   │   │   - Status: RESOLVED                                    │ │ │   │
│   │   │   │   - Turns: [13-15]                                      │ │ │   │
│   │   │   │   - Outcome: noted_allergies                            │ │ │   │
│   │   │   └─────────────────────────────────────────────────────────┘ │ │   │
│   │   └───────────────────────────────────────────────────────────────┘ │   │
│   │                              │                                      │   │
│   │                              │ "active threads"                     │   │
│   │                              ▼                                      │   │
│   └─────────────────────────────────────────────────────────────────────┘   │
│                                  │                                          │
│                                  ▼                                          │
│   ┌─────────────────────────────────────────────────────────────────────┐   │
│   │              CONVERSATIONAL_NARRATIVE_ENGINE                        │   │
│   │                                                                     │   │
│   │   (See F116 for thread → engine flow)                               │   │
│   └─────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
│   Result: Conversation threads identified with status and open goals        │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

### F116: Thread → Narrative Engine Flow

**Trigger:** NARRATIVE_WEAVING outputs active threads
**Outcome:** CONVERSATIONAL_NARRATIVE_ENGINE updates thread state

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                   F116: THREAD → NARRATIVE ENGINE FLOW                      │
│                                                                             │
│   Purpose: Feed thread analysis to narrative engine for coherence           │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│   ┌─────────────────────────────────────────────────────────────────────┐   │
│   │                     NARRATIVE_WEAVING                               │   │
│   │                                                                     │   │
│   │   Active Threads Output:                                            │   │
│   │   [                                                                 │   │
│   │     {thread_id: "A", topic: "Meal Planning", status: "ACTIVE"},     │   │
│   │     {thread_id: "B", topic: "Grocery Budget", status: "PAUSED"}     │   │
│   │   ]                                                                 │   │
│   │                              │                                      │   │
│   │                              │ "active threads"                     │   │
│   │                              ▼                                      │   │
│   └─────────────────────────────────────────────────────────────────────┘   │
│                                  │                                          │
│                                  ▼                                          │
│   ┌─────────────────────────────────────────────────────────────────────┐   │
│   │              CONVERSATIONAL_NARRATIVE_ENGINE                        │   │
│   │                                                                     │   │
│   │   ┌───────────────────────────────────────────────────────────────┐ │   │
│   │   │              Thread Management                                │ │   │
│   │   │                                                               │ │   │
│   │   │   Operations:                                                 │ │   │
│   │   │                                                               │ │   │
│   │   │   1. Update Thread States                                     │ │   │
│   │   │      - Merge new thread info with existing                    │ │   │
│   │   │      - Update status (ACTIVE, PAUSED, RESOLVED)               │ │   │
│   │   │      - Track open goals per thread                            │ │   │
│   │   │                                                               │ │   │
│   │   │   2. Calculate Thread Priority                                │ │   │
│   │   │      priority = recency * importance * user_engagement        │ │   │
│   │   │                                                               │ │   │
│   │   │   3. Generate Thread Resumption Hints                         │ │   │
│   │   │      - "Earlier you mentioned budget concerns..."             │ │   │
│   │   │      - "Should we return to the meal planning?"               │ │   │
│   │   │                                                               │ │   │
│   │   │   4. Detect Thread Conflicts                                  │ │   │
│   │   │      - Contradictory goals across threads                     │ │   │
│   │   │      - Resource conflicts (time, budget)                      │ │   │
│   │   └───────────────────────────────────────────────────────────────┘ │   │
│   │                              │                                      │   │
│   │                              │ "Update Threads"                     │   │
│   │                              ▼                                      │   │
│   └─────────────────────────────────────────────────────────────────────┘   │
│                                  │                                          │
│         ┌────────────────────────┴────────────────────────┐                 │
│         │                                                 │                 │
│         ▼                                                 ▼                 │
│   ┌───────────────────────────────┐   ┌───────────────────────────────────┐ │
│   │     CONVERSATION_THREADS      │   │     SessionState Updates          │ │
│   │                               │   │                                   │ │
│   │  In-memory thread state:      │   │  NARRATIVE_ACTIVE:                │ │
│   │  ┌─────────────────────────┐  │   │  ┌─────────────────────────────┐  │ │
│   │  │ thread_A: {             │  │   │  │ primary_thread: "A"         │  │ │
│   │  │   turns: [...],         │  │   │  │ paused_threads: ["B"]       │  │ │
│   │  │   entities: [...],      │  │   │  │ thread_count: 2             │  │ │
│   │  │   goals: [...]          │  │   │  │ resumption_hint: "..."      │  │ │
│   │  │ },                      │  │   │  └─────────────────────────────┘  │ │
│   │  │ thread_B: {...}         │  │   │                                   │ │
│   │  └─────────────────────────┘  │   │                                   │ │
│   └───────────────────────────────┘   └───────────────────────────────────┘ │
│                                                                             │
│   ┌─────────────────────────────────────────────────────────────────────┐   │
│   │                      CONCIERGE_FSM                                  │   │
│   │                                                                     │   │
│   │   Narrative context available for:                                  │   │
│   │   - COMPANIONING: Reference active threads in updates               │   │
│   │   - DELIVERING: Suggest thread resumption in "Next Steps"           │   │
│   │   - CLARIFYING: Understand context from thread history              │   │
│   └─────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
│   Result: Narrative engine maintains coherent multi-thread conversation     │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

### F117: Narrative Arc Update Flow

**Trigger:** CONVERSATIONAL_NARRATIVE_ENGINE processes threads
**Outcome:** NARRATIVE_ARC updated with conversation progression

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                      F117: NARRATIVE ARC UPDATE FLOW                        │
│                                                                             │
│   Purpose: Track overall conversation progression and story arc             │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│   ┌─────────────────────────────────────────────────────────────────────┐   │
│   │              CONVERSATIONAL_NARRATIVE_ENGINE                        │   │
│   │                                                                     │   │
│   │   Thread Processing Complete                                        │   │
│   │                              │                                      │   │
│   │                              │ "Update Arc"                         │   │
│   │                              ▼                                      │   │
│   └─────────────────────────────────────────────────────────────────────┘   │
│                                  │                                          │
│                                  ▼                                          │
│   ┌─────────────────────────────────────────────────────────────────────┐   │
│   │                       NARRATIVE_ARC                                 │   │
│   │                                                                     │   │
│   │   ┌───────────────────────────────────────────────────────────────┐ │   │
│   │   │              Arc Structure (Story Model)                      │ │   │
│   │   │                                                               │ │   │
│   │   │   Session Arc:                                                │ │   │
│   │   │   ┌─────────────────────────────────────────────────────────┐ │ │   │
│   │   │   │                                                         │ │ │   │
│   │   │   │   EXPOSITION    RISING ACTION    CLIMAX    RESOLUTION   │ │ │   │
│   │   │   │       │              │             │           │        │ │ │   │
│   │   │   │   [turns 1-10]  [turns 11-40]  [turns 41-60] [ongoing]  │ │ │   │
│   │   │   │       │              │             │           │        │ │ │   │
│   │   │   │   "User intro"  "Working on"   "Key moment" "Wrapping"  │ │ │   │
│   │   │   │   "Goals set"   "tasks/issues" "Decision"   "up/closure"│ │ │   │
│   │   │   │                                                         │ │ │   │
│   │   │   │   Current Position: ████████░░░░░░ (RISING ACTION)      │ │ │   │
│   │   │   │                                                         │ │ │   │
│   │   │   └─────────────────────────────────────────────────────────┘ │ │   │
│   │   │                                                               │ │   │
│   │   │   Arc Metrics:                                                │ │   │
│   │   │   ┌─────────────────────────────────────────────────────────┐ │ │   │
│   │   │   │ - progress: 0.45 (45% through expected session)         │ │ │   │
│   │   │   │ - tension_level: 0.6 (moderate complexity)              │ │ │   │
│   │   │   │ - resolution_count: 2 (threads resolved)                │ │ │   │
│   │   │   │ - open_threads: 2 (threads still active)                │ │ │   │
│   │   │   │ - momentum: INCREASING (user engagement up)             │ │ │   │
│   │   │   └─────────────────────────────────────────────────────────┘ │ │   │
│   │   │                                                               │ │   │
│   │   │   Arc Transitions:                                            │ │   │
│   │   │   ┌─────────────────────────────────────────────────────────┐ │ │   │
│   │   │   │ If all_threads_resolved && user_satisfied:              │ │ │   │
│   │   │   │   → Transition to RESOLUTION phase                      │ │ │   │
│   │   │   │   → Prepare session summary                             │ │ │   │
│   │   │   │   → Suggest follow-up actions                           │ │ │   │
│   │   │   │                                                         │ │ │   │
│   │   │   │ If new_major_thread_introduced:                         │ │ │   │
│   │   │   │   → Reset to RISING ACTION                              │ │ │   │
│   │   │   │   → Acknowledge topic shift                             │ │ │   │
│   │   │   └─────────────────────────────────────────────────────────┘ │ │   │
│   │   └───────────────────────────────────────────────────────────────┘ │   │
│   │                                                                     │   │
│   └─────────────────────────────────────────────────────────────────────┘   │
│                                  │                                          │
│                                  │ arc state update                         │
│                                  ▼                                          │
│   ┌─────────────────────────────────────────────────────────────────────┐   │
│   │                      SessionState                                   │   │
│   │                                                                     │   │
│   │   NARRATIVE_ACTIVE updated with arc position                        │   │
│   │                                                                     │   │
│   │   Used by CONCIERGE_FSM for:                                        │   │
│   │   - Pacing responses (slower in resolution)                         │   │
│   │   - Closure prompts (when arc suggests ending)                      │   │
│   │   - Energy matching (higher in rising action)                       │   │
│   └─────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
│   Result: Conversation has coherent narrative structure                     │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

### F118: User Needs Prediction Flow

**Trigger:** turn_count % 30 == 0 (every 30 turns)
**Outcome:** Predicted user needs for anticipatory responses

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                    F118: USER NEEDS PREDICTION FLOW                         │
│                                                                             │
│   Trigger: DELIVERING state, turn_count % 30 == 0                           │
│   Purpose: Predict what user will need next before they ask                 │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│   ┌─────────────────────────────────────────────────────────────────────┐   │
│   │                       DELIVERING                                    │   │
│   │                  (CONCIERGE_FSM State)                              │   │
│   │                                                                     │   │
│   │   turn_count = 30, 60, 90, 120, ...                                 │   │
│   │                                                                     │   │
│   │   ┌───────────────────────────────────────────────────────────────┐ │   │
│   │   │              Check Trigger Condition                          │ │   │
│   │   │                                                               │ │   │
│   │   │   if (turn_count % 30 == 0):                                  │ │   │
│   │   │       trigger ANTICIPATORY_RESPONSE                           │ │   │
│   │   │                                                               │ │   │
│   │   │   Note: Least frequent (every 30 turns)                       │ │   │
│   │   │   Rationale: Predictions are costly, need enough data         │ │   │
│   │   └───────────────────────────────────────────────────────────────┘ │   │
│   │                              │                                      │   │
│   │                              │ "turn_count % 30 == 0"               │   │
│   │                              ▼                                      │   │
│   └─────────────────────────────────────────────────────────────────────┘   │
│                                  │                                          │
│                                  ▼                                          │
│   ┌─────────────────────────────────────────────────────────────────────┐   │
│   │                   ANTICIPATORY_RESPONSE                             │   │
│   │                   "Predict user needs"                              │   │
│   │                                                                     │   │
│   │   ┌───────────────────────────────────────────────────────────────┐ │   │
│   │   │              Gather Prediction Context                        │ │   │
│   │   │                                                               │ │   │
│   │   │   From Current Session:                                       │ │   │
│   │   │   - Active threads and their goals                            │ │   │
│   │   │   - Recent tool invocations                                   │ │   │
│   │   │   - User's expressed frustrations/satisfactions               │ │   │
│   │   │   - Current task progress                                     │ │   │
│   │   │                                                               │ │   │
│   │   │   From K0 (Historical Patterns):                              │ │   │
│   │   │   - What user typically asks after similar contexts           │ │   │
│   │   │   - Sequence patterns (A → B → C typical flow)                │ │   │
│   │   │   - Time-of-day preferences                                   │ │   │
│   │   │   - Domain expertise level                                    │ │   │
│   │   └───────────────────────────────────────────────────────────────┘ │   │
│   │                              │                                      │   │
│   │   ┌───────────────────────────────────────────────────────────────┐ │   │
│   │   │              Prediction Engine                                │ │   │
│   │   │                                                               │ │   │
│   │   │   Prediction Categories:                                      │ │   │
│   │   │                                                               │ │   │
│   │   │   1. Next Action Prediction                                   │ │   │
│   │   │      - P(user_asks_X | context) for top-N actions             │ │   │
│   │   │      - Example: "User will likely ask for grocery list"       │ │   │
│   │   │                                                               │ │   │
│   │   │   2. Information Need Prediction                              │ │   │
│   │   │      - What info user will need to complete goal              │ │   │
│   │   │      - Example: "Will need store locations"                   │ │   │
│   │   │                                                               │ │   │
│   │   │   3. Clarification Prediction                                 │ │   │
│   │   │      - Ambiguities user hasn't noticed yet                    │ │   │
│   │   │      - Example: "Budget not specified for groceries"          │ │   │
│   │   │                                                               │ │   │
│   │   │   4. Emotional Need Prediction                                │ │   │
│   │   │      - Support user may need based on trajectory              │ │   │
│   │   │      - Example: "May need encouragement soon"                 │ │   │
│   │   └───────────────────────────────────────────────────────────────┘ │   │
│   │                              │                                      │   │
│   │                              │ "predicted needs"                    │   │
│   │                              ▼                                      │   │
│   └─────────────────────────────────────────────────────────────────────┘   │
│                                  │                                          │
│                                  ▼                                          │
│   ┌─────────────────────────────────────────────────────────────────────┐   │
│   │            CONVERSATIONAL_ANTICIPATION_ENGINE                       │   │
│   │                                                                     │   │
│   │   Predictions Output:                                               │   │
│   │   {                                                                 │   │
│   │     "likely_next_requests": [                                       │   │
│   │       {"action": "create_grocery_list", "confidence": 0.85},        │   │
│   │       {"action": "find_nearby_stores", "confidence": 0.60}          │   │
│   │     ],                                                              │   │
│   │     "prefetch_suggestions": [                                       │   │
│   │       "k0.query_recall: grocery preferences",                       │   │
│   │       "capability: store_locator"                                   │   │
│   │     ],                                                              │   │
│   │     "proactive_hints": [                                            │   │
│   │       "Would you like me to also find nearby stores?"               │   │
│   │     ]                                                               │   │
│   │   }                                                                 │   │
│   └─────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
│   Result: System anticipates user needs before they ask                     │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

### F119: Context Prefetch Flow

**Trigger:** ANTICIPATORY_RESPONSE generates predictions
**Outcome:** Relevant context pre-fetched via CAPABILITY_FABRIC

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                      F119: CONTEXT PREFETCH FLOW                            │
│                                                                             │
│   Purpose: Pre-fetch context for predicted needs to reduce latency          │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│   ┌─────────────────────────────────────────────────────────────────────┐   │
│   │                   ANTICIPATORY_RESPONSE                             │   │
│   │                                                                     │   │
│   │   Predicted Needs:                                                  │   │
│   │   {                                                                 │   │
│   │     "likely_next_requests": [                                       │   │
│   │       {"action": "create_grocery_list", "confidence": 0.85}         │   │
│   │     ],                                                              │   │
│   │     "prefetch_suggestions": [                                       │   │
│   │       "k0.query_recall: grocery preferences",                       │   │
│   │       "k0.query_recall: dietary restrictions"                       │   │
│   │     ]                                                               │   │
│   │   }                                                                 │   │
│   │                              │                                      │   │
│   │                              │ "prefetch context"                   │   │
│   │                              ▼                                      │   │
│   └─────────────────────────────────────────────────────────────────────┘   │
│                                  │                                          │
│                                  ▼                                          │
│   ┌─────────────────────────────────────────────────────────────────────┐   │
│   │                     CAPABILITY_FABRIC                               │   │
│   │                                                                     │   │
│   │   ┌───────────────────────────────────────────────────────────────┐ │   │
│   │   │              Prefetch Strategy                                │ │   │
│   │   │                                                               │ │   │
│   │   │   1. Evaluate Prefetch Cost/Benefit                           │ │   │
│   │   │      - confidence > 0.7 → prefetch                            │ │   │
│   │   │      - estimated_latency_saved vs prefetch_cost               │ │   │
│   │   │                                                               │ │   │
│   │   │   2. Priority Ordering                                        │ │   │
│   │   │      - Higher confidence → higher priority                    │ │   │
│   │   │      - Lower latency items first                              │ │   │
│   │   │                                                               │ │   │
│   │   │   3. Background Execution                                     │ │   │
│   │   │      - Non-blocking prefetch                                  │ │   │
│   │   │      - Cancel if user request changes                         │ │   │
│   │   └───────────────────────────────────────────────────────────────┘ │   │
│   │                              │                                      │   │
│   │                              │ invoke capabilities (background)     │   │
│   │                              ▼                                      │   │
│   └─────────────────────────────────────────────────────────────────────┘   │
│                                  │                                          │
│         ┌────────────────────────┴────────────────────────┐                 │
│         │                                                 │                 │
│         ▼                                                 ▼                 │
│   ┌───────────────────────────────┐   ┌───────────────────────────────────┐ │
│   │     K0_GENERIC_CLIENT         │   │     TOOL_PROVIDERS                │ │
│   │                               │   │                                   │ │
│   │  Prefetch K0 Recalls:         │   │  Prefetch Tool Warm-up:           │ │
│   │  ┌─────────────────────────┐  │   │  ┌─────────────────────────────┐  │ │
│   │  │ - grocery_preferences   │  │   │  │ - store_locator: warm cache │  │ │
│   │  │ - dietary_restrictions  │  │   │  │ - recipe_search: preload    │  │ │
│   │  │ - past_grocery_lists    │  │   │  │ - price_check: connect      │  │ │
│   │  └─────────────────────────┘  │   │  └─────────────────────────────┘  │ │
│   │           │                   │   │           │                       │ │
│   │           ▼                   │   │           ▼                       │ │
│   │  PORT_QRY → QUERY_AGG         │   │  MCP_RUNNERS (warm)               │ │
│   │           │                   │   │                                   │ │
│   │           ▼                   │   │                                   │ │
│   │  Results cached in            │   │                                   │ │
│   │  TOOL_RESULT_BUFFER           │   │                                   │ │
│   └───────────────────────────────┘   └───────────────────────────────────┘ │
│                                                                             │
│   ┌─────────────────────────────────────────────────────────────────────┐   │
│   │                    PREFETCH CACHE                                   │   │
│   │                                                                     │   │
│   │   Cached Prefetch Results:                                          │   │
│   │   ┌───────────────────────────────────────────────────────────────┐ │   │
│   │   │ prefetch_id: "anticipate_30"                                  │ │   │
│   │   │ results: {                                                    │ │   │
│   │   │   "grocery_preferences": ["organic", "local", "budget:$150"], │ │   │
│   │   │   "dietary_restrictions": ["gluten-free", "no nuts"],         │ │   │
│   │   │   "warm_tools": ["store_locator", "recipe_search"]            │ │   │
│   │   │ }                                                             │ │   │
│   │   │ ttl: 5 minutes (expires if not used)                          │ │   │
│   │   │ invalidate_on: ["user_intent_change", "topic_shift"]          │ │   │
│   │   └───────────────────────────────────────────────────────────────┘ │   │
│   │                                                                     │   │
│   │   When User Actually Asks:                                          │   │
│   │   - If prefetch hit: latency reduced by 200-500ms                   │   │
│   │   - If prefetch miss: normal execution (no penalty)                 │   │
│   └─────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
│   Result: Predicted context ready, reducing response latency                │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## 13. RHYTHM & EMPATHY FLOWS

### 13.1 Conversational Rhythm Flow

- [x] **F120: Rhythm Patterns → Conversation Beat Flow**
- [x] **F121: Dynamic Timing Adjustment Flow**
- [x] **F122: Pacing → Concierge FSM Flow**

### 13.2 Theory of Mind Flow

- [x] **F123: ToM Engine → Mental Model Update Flow**
- [x] **F124: Mental Model Management → Cognitive Load Flow**
- [x] **F125: Capacity Estimate → Concierge Flow**

### 13.3 Predictive Completion Flow

- [x] **F126: Predictions → Anticipation Engine Flow**
- [x] **F127: Anticipation → Speculative Execution Flow**

---

### F120: Rhythm Patterns → Conversation Beat Flow

**Trigger:** Every conversation turn (real-time)
**Outcome:** Response timing calibrated to conversation rhythm

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                F120: RHYTHM PATTERNS → CONVERSATION BEAT FLOW               │
│                                                                             │
│   Layer: L1_RHYTHM (Real-time, every turn)                                  │
│   Purpose: Calibrate response timing for natural conversation flow          │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│   ┌─────────────────────────────────────────────────────────────────────┐   │
│   │                        L1_RHYTHM                                    │   │
│   │              "Rhythm Controller (Real-time)"                        │   │
│   │                                                                     │   │
│   │   ┌───────────────────────────────────────────────────────────────┐ │   │
│   │   │                   RHYTHM_PATTERNS                             │ │   │
│   │   │                                                               │ │   │
│   │   │   Defined Patterns:                                           │ │   │
│   │   │   ┌─────────────────────────────────────────────────────────┐ │ │   │
│   │   │   │                                                         │ │ │   │
│   │   │   │   QUICK_EXCHANGE:                                       │ │ │   │
│   │   │   │     Response Time: 200-500ms                            │ │ │   │
│   │   │   │     Context: Simple questions, acknowledgments          │ │ │   │
│   │   │   │     Example: "Yes", "Got it", "Sure"                    │ │ │   │
│   │   │   │                                                         │ │ │   │
│   │   │   │   THOUGHTFUL_DISCUSSION:                                │ │ │   │
│   │   │   │     Response Time: 1-2 seconds                          │ │ │   │
│   │   │   │     Context: Complex questions, explanations            │ │ │   │
│   │   │   │     Example: Analysis, recommendations, plans           │ │ │   │
│   │   │   │                                                         │ │ │   │
│   │   │   │   DEEP_ANALYSIS:                                        │ │ │   │
│   │   │   │     Response Time: 2-5 seconds                          │ │ │   │
│   │   │   │     Context: Multi-step reasoning, research             │ │ │   │
│   │   │   │     Example: Complex planning, data analysis            │ │ │   │
│   │   │   │                                                         │ │ │   │
│   │   │   │   EXTENDED_WORK:                                        │ │ │   │
│   │   │   │     Response Time: 5+ seconds (with progress updates)   │ │ │   │
│   │   │   │     Context: Tool execution, external calls             │ │ │   │
│   │   │   │     Example: File operations, API calls                 │ │ │   │
│   │   │   │                                                         │ │ │   │
│   │   │   └─────────────────────────────────────────────────────────┘ │ │   │
│   │   │                                                               │ │   │
│   │   └───────────────────────────────────────────────────────────────┘ │   │
│   │                              │                                      │   │
│   │                              │ pattern selection                    │   │
│   │                              ▼                                      │   │
│   └─────────────────────────────────────────────────────────────────────┘   │
│                                  │                                          │
│                                  ▼                                          │
│   ┌─────────────────────────────────────────────────────────────────────┐   │
│   │                    CONVERSATION_BEAT                                │   │
│   │                                                                     │   │
│   │   ┌───────────────────────────────────────────────────────────────┐ │   │
│   │   │              Beat Detection & Application                     │ │   │
│   │   │                                                               │ │   │
│   │   │   Inputs:                                                     │ │   │
│   │   │   - Current task complexity (from ULTRABERT_INGRESS)          │ │   │
│   │   │   - User's typing speed (if available)                        │ │   │
│   │   │   - Historical response times for this user                   │ │   │
│   │   │   - Current emotional state (from AFFECTIVE_NOW)              │ │   │
│   │   │                                                               │ │   │
│   │   │   Beat Calculation:                                           │ │   │
│   │   │   ┌─────────────────────────────────────────────────────────┐ │ │   │
│   │   │   │                                                         │ │ │   │
│   │   │   │   if task_complexity == LOW:                            │ │ │   │
│   │   │   │       target_beat = QUICK_EXCHANGE (200-500ms)          │ │ │   │
│   │   │   │   elif task_complexity == MEDIUM:                       │ │ │   │
│   │   │   │       target_beat = THOUGHTFUL_DISCUSSION (1-2s)        │ │ │   │
│   │   │   │   elif task_complexity == HIGH:                         │ │ │   │
│   │   │   │       target_beat = DEEP_ANALYSIS (2-5s)                │ │ │   │
│   │   │   │       + periodic progress via PROGRESSING state         │ │ │   │
│   │   │   │                                                         │ │ │   │
│   │   │   │   # Adjust for user preferences                         │ │ │   │
│   │   │   │   if user_prefers_fast:                                 │ │ │   │
│   │   │   │       target_beat *= 0.8  # 20% faster                  │ │ │   │
│   │   │   │   if user_seems_anxious:                                │ │ │   │
│   │   │   │       target_beat *= 0.9  # slightly faster             │ │ │   │
│   │   │   │                                                         │ │ │   │
│   │   │   └─────────────────────────────────────────────────────────┘ │ │   │
│   │   │                                                               │ │   │
│   │   │   Output:                                                     │ │   │
│   │   │   {                                                           │ │   │
│   │   │     "target_response_time_ms": 1200,                          │ │   │
│   │   │     "pattern": "THOUGHTFUL_DISCUSSION",                       │ │   │
│   │   │     "allow_early_response": true,                             │ │   │
│   │   │     "progress_interval_ms": null                              │ │   │
│   │   │   }                                                           │ │   │
│   │   └───────────────────────────────────────────────────────────────┘ │   │
│   │                                                                     │   │
│   └─────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
│   Result: Response timing target set for natural conversation flow          │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

### F121: Dynamic Timing Adjustment Flow

**Trigger:** User behavior observed (typing speed, response patterns)
**Outcome:** RHYTHM_PATTERNS dynamically adjusted for user

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                  F121: DYNAMIC TIMING ADJUSTMENT FLOW                       │
│                                                                             │
│   Purpose: Adapt response timing based on real-time user behavior           │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│   ┌─────────────────────────────────────────────────────────────────────┐   │
│   │                    User Behavior Signals                            │   │
│   │                                                                     │   │
│   │   ┌─────────────────────────────────────────────────────────────┐   │   │
│   │   │              Observable Signals                             │   │   │
│   │   │                                                             │   │   │
│   │   │   1. Typing Speed (if available via client):                │   │   │
│   │   │      - Fast typing → user is fluent, can handle faster      │   │   │
│   │   │      - Slow typing → user is thinking, slow down            │   │   │
│   │   │                                                             │   │   │
│   │   │   2. Response Time (user → system):                         │   │   │
│   │   │      - Quick responses → engaged, wants fast interaction    │   │   │
│   │   │      - Slow responses → distracted or thinking              │   │   │
│   │   │                                                             │   │   │
│   │   │   3. Topic Complexity (from ULTRABERT):                     │   │   │
│   │   │      - Simple topics → expect quick responses               │   │   │
│   │   │      - Complex topics → expect thoughtful responses         │   │   │
│   │   │                                                             │   │   │
│   │   │   4. Message Length:                                        │   │   │
│   │   │      - Short messages → user wants brevity                  │   │   │
│   │   │      - Long messages → user is detailed, can handle more    │   │   │
│   │   └─────────────────────────────────────────────────────────────┘   │   │
│   │                              │                                      │   │
│   └──────────────────────────────┼──────────────────────────────────────┘   │
│                                  │                                          │
│                                  ▼                                          │
│   ┌─────────────────────────────────────────────────────────────────────┐   │
│   │                    DYNAMIC_ADJUSTMENT                               │   │
│   │                                                                     │   │
│   │   ┌───────────────────────────────────────────────────────────────┐ │   │
│   │   │              Adjustment Computation                           │ │   │
│   │   │                                                               │ │   │
│   │   │   Inputs:                                                     │ │   │
│   │   │   ┌─────────────────────────────────────────────────────────┐ │ │   │
│   │   │   │ User Typing Speed → Response Timing                     │ │ │   │
│   │   │   │   fast_typer → faster responses (+20%)                  │ │ │   │
│   │   │   │   slow_typer → maintain or slow (-10%)                  │ │ │   │
│   │   │   │                                                         │ │ │   │
│   │   │   │ Topic Complexity → Pacing                               │ │ │   │
│   │   │   │   complex_topic → slower, more thoughtful               │ │ │   │
│   │   │   │   simple_topic → faster, more direct                    │ │ │   │
│   │   │   │                                                         │ │ │   │
│   │   │   │ Emotional State → Timing Modulation                     │ │ │   │
│   │   │   │   anxious → faster to reassure                          │ │ │   │
│   │   │   │   calm → standard timing                                │ │ │   │
│   │   │   │   frustrated → faster initial ack, then thorough        │ │ │   │
│   │   │   └─────────────────────────────────────────────────────────┘ │ │   │
│   │   │                                                               │ │   │
│   │   │   Adjustment Formula:                                         │ │   │
│   │   │   ┌─────────────────────────────────────────────────────────┐ │ │   │
│   │   │   │                                                         │ │ │   │
│   │   │   │   adjustment_factor = (                                 │ │ │   │
│   │   │   │     typing_speed_factor *                               │ │ │   │
│   │   │   │     complexity_factor *                                 │ │ │   │
│   │   │   │     emotional_factor                                    │ │ │   │
│   │   │   │   )                                                     │ │ │   │
│   │   │   │                                                         │ │ │   │
│   │   │   │   adjusted_timing = base_timing * adjustment_factor     │ │ │   │
│   │   │   │                                                         │ │ │   │
│   │   │   │   # Clamp to reasonable bounds                          │ │ │   │
│   │   │   │   adjusted_timing = clamp(adjusted_timing, 100ms, 10s)  │ │ │   │
│   │   │   │                                                         │ │ │   │
│   │   │   └─────────────────────────────────────────────────────────┘ │ │   │
│   │   └───────────────────────────────────────────────────────────────┘ │   │
│   │                              │                                      │   │
│   │                              │ adjusted rhythm parameters           │   │
│   │                              ▼                                      │   │
│   └─────────────────────────────────────────────────────────────────────┘   │
│                                  │                                          │
│                                  ▼                                          │
│   ┌─────────────────────────────────────────────────────────────────────┐   │
│   │                    RHYTHM_PATTERNS (Updated)                        │   │
│   │                                                                     │   │
│   │   Session-Adjusted Patterns:                                        │   │
│   │   ┌───────────────────────────────────────────────────────────────┐ │   │
│   │   │ QUICK_EXCHANGE: 160-400ms (was 200-500ms, user is fast)      │ │   │
│   │   │ THOUGHTFUL: 800ms-1.6s (was 1-2s, user prefers faster)       │ │   │
│   │   │ DEEP_ANALYSIS: 1.6-4s (was 2-5s, adjusted)                   │ │   │
│   │   └───────────────────────────────────────────────────────────────┘ │   │
│   │                                                                     │   │
│   └─────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
│   Result: Response timing personalized to user's interaction style          │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

### F122: Pacing → Concierge FSM Flow

**Trigger:** CONVERSATION_BEAT outputs timing target
**Outcome:** CONCIERGE_FSM applies pacing to response delivery

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                    F122: PACING → CONCIERGE FSM FLOW                        │
│                                                                             │
│   Purpose: Apply computed rhythm to actual response delivery                │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│   ┌─────────────────────────────────────────────────────────────────────┐   │
│   │                    CONVERSATION_BEAT                                │   │
│   │                                                                     │   │
│   │   Timing Target:                                                    │   │
│   │   {                                                                 │   │
│   │     "target_response_time_ms": 1200,                                │   │
│   │     "pattern": "THOUGHTFUL_DISCUSSION",                             │   │
│   │     "progress_interval_ms": null,                                   │   │
│   │     "min_delay_ms": 300  // minimum "thinking" time                 │   │
│   │   }                                                                 │   │
│   │                              │                                      │   │
│   │                              │ pacing parameters                    │   │
│   │                              ▼                                      │   │
│   └─────────────────────────────────────────────────────────────────────┘   │
│                                  │                                          │
│                                  ▼                                          │
│   ┌─────────────────────────────────────────────────────────────────────┐   │
│   │                      CONCIERGE_FSM                                  │   │
│   │                                                                     │   │
│   │   ┌───────────────────────────────────────────────────────────────┐ │   │
│   │   │              Pacing Application by State                      │ │   │
│   │   │                                                               │ │   │
│   │   │   ACKING State:                                               │ │   │
│   │   │   ┌─────────────────────────────────────────────────────────┐ │ │   │
│   │   │   │ - If pattern == QUICK_EXCHANGE:                         │ │ │   │
│   │   │   │     Skip explicit ack, go straight to response          │ │ │   │
│   │   │   │ - If pattern == THOUGHTFUL_DISCUSSION:                  │ │ │   │
│   │   │   │     Brief ack ("Let me think about that...")            │ │ │   │
│   │   │   │ - If pattern == DEEP_ANALYSIS:                          │ │ │   │
│   │   │   │     Explicit ack with estimated time                    │ │ │   │
│   │   │   └─────────────────────────────────────────────────────────┘ │ │   │
│   │   │                                                               │ │   │
│   │   │   PROGRESSING State:                                          │ │   │
│   │   │   ┌─────────────────────────────────────────────────────────┐ │ │   │
│   │   │   │ - If elapsed > target && not done:                      │ │ │   │
│   │   │   │     Send progress update (streaming)                    │ │ │   │
│   │   │   │ - Progress interval from CONVERSATION_BEAT              │ │ │   │
│   │   │   │ - "Still working on it... found 3 options so far"       │ │ │   │
│   │   │   └─────────────────────────────────────────────────────────┘ │ │   │
│   │   │                                                               │ │   │
│   │   │   DELIVERING State:                                           │ │   │
│   │   │   ┌─────────────────────────────────────────────────────────┐ │ │   │
│   │   │   │ - Apply min_delay if response ready too fast            │ │ │   │
│   │   │   │ - Avoid "instant" responses that feel robotic           │ │ │   │
│   │   │   │                                                         │ │ │   │
│   │   │   │ actual_delay = max(                                     │ │ │   │
│   │   │   │   min_delay_ms,                                         │ │ │   │
│   │   │   │   processing_time                                       │ │ │   │
│   │   │   │ )                                                       │ │ │   │
│   │   │   │                                                         │ │ │   │
│   │   │   │ - Streaming: pace token output for readability          │ │ │   │
│   │   │   │   tokens_per_second = user_reading_speed * 0.8          │ │ │   │
│   │   │   └─────────────────────────────────────────────────────────┘ │ │   │
│   │   │                                                               │ │   │
│   │   └───────────────────────────────────────────────────────────────┘ │   │
│   │                                                                     │   │
│   │   ┌───────────────────────────────────────────────────────────────┐ │   │
│   │   │              Pacing Examples                                  │ │   │
│   │   │                                                               │ │   │
│   │   │   User: "What's the weather?"                                 │ │   │
│   │   │   Pattern: QUICK_EXCHANGE                                     │ │   │
│   │   │   Response: Immediate (no artificial delay)                   │ │   │
│   │   │                                                               │ │   │
│   │   │   User: "Help me plan my vacation"                            │ │   │
│   │   │   Pattern: THOUGHTFUL_DISCUSSION                              │ │   │
│   │   │   Response: 300ms delay + "I'd love to help..." + content     │ │   │
│   │   │                                                               │ │   │
│   │   │   User: "Analyze my spending patterns"                        │ │   │
│   │   │   Pattern: DEEP_ANALYSIS                                      │ │   │
│   │   │   Response: Ack → Progress updates → Final response           │ │   │
│   │   │                                                               │ │   │
│   │   └───────────────────────────────────────────────────────────────┘ │   │
│   │                                                                     │   │
│   └─────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
│   Result: Responses delivered with natural, context-appropriate pacing      │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

### F123: ToM Engine → Mental Model Update Flow

**Trigger:** User interaction provides new mental model data
**Outcome:** THEORY_OF_MIND_ENGINE updates user's mental model

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                 F123: ToM ENGINE → MENTAL MODEL UPDATE FLOW                 │
│                                                                             │
│   Layer: L3_5_EMPATHY (Cognitive Empathy Core)                              │
│   Purpose: Build and maintain model of user's knowledge, beliefs, goals     │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│   ┌─────────────────────────────────────────────────────────────────────┐   │
│   │                    User Interaction Signals                         │   │
│   │                                                                     │   │
│   │   From Conversation:                                                │   │
│   │   - Questions asked → knowledge gaps                                │   │
│   │   - Statements made → beliefs/facts known                           │   │
│   │   - Requests made → current goals                                   │   │
│   │   - Confusion signals → understanding limits                        │   │
│   │   - Expertise demonstrated → skill level                            │   │
│   │                              │                                      │   │
│   │                              │ interaction signals                  │   │
│   │                              ▼                                      │   │
│   └─────────────────────────────────────────────────────────────────────┘   │
│                                  │                                          │
│                                  ▼                                          │
│   ┌─────────────────────────────────────────────────────────────────────┐   │
│   │                  THEORY_OF_MIND_ENGINE                              │   │
│   │                   "User Mental Model"                               │   │
│   │                                                                     │   │
│   │   ┌───────────────────────────────────────────────────────────────┐ │   │
│   │   │              Mental Model Components                          │ │   │
│   │   │                                                               │ │   │
│   │   │   1. Knowledge Model (What user knows):                       │ │   │
│   │   │   ┌─────────────────────────────────────────────────────────┐ │ │   │
│   │   │   │ - Domain expertise: {finance: 0.7, cooking: 0.9}        │ │ │   │
│   │   │   │ - Technical level: {coding: 0.3, general_tech: 0.6}     │ │ │   │
│   │   │   │ - Known facts: [has_kids, lives_in_seattle, ...]        │ │ │   │
│   │   │   │ - Knowledge gaps: [crypto, tax_rules, ...]              │ │ │   │
│   │   │   └─────────────────────────────────────────────────────────┘ │ │   │
│   │   │                                                               │ │   │
│   │   │   2. Belief Model (What user believes):                       │ │   │
│   │   │   ┌─────────────────────────────────────────────────────────┐ │ │   │
│   │   │   │ - Values: [health_conscious, budget_minded, ...]        │ │ │   │
│   │   │   │ - Preferences: [prefers_organic, dislikes_waiting]      │ │ │   │
│   │   │   │ - Assumptions: [thinks_AI_is_helpful, ...]              │ │ │   │
│   │   │   └─────────────────────────────────────────────────────────┘ │ │   │
│   │   │                                                               │ │   │
│   │   │   3. Goal Model (What user wants):                            │ │   │
│   │   │   ┌─────────────────────────────────────────────────────────┐ │ │   │
│   │   │   │ - Immediate: [plan_dinner, find_recipe]                 │ │ │   │
│   │   │   │ - Session: [meal_prep_for_week]                         │ │ │   │
│   │   │   │ - Long-term: [eat_healthier, save_money]                │ │ │   │
│   │   │   └─────────────────────────────────────────────────────────┘ │ │   │
│   │   │                                                               │ │   │
│   │   │   4. Attention Model (What user is focused on):               │ │   │
│   │   │   ┌─────────────────────────────────────────────────────────┐ │ │   │
│   │   │   │ - Current focus: "dinner_options"                       │ │ │   │
│   │   │   │ - Attention span: MODERATE (based on response times)    │ │ │   │
│   │   │   │ - Distraction level: LOW                                │ │ │   │
│   │   │   └─────────────────────────────────────────────────────────┘ │ │   │
│   │   └───────────────────────────────────────────────────────────────┘ │   │
│   │                              │                                      │   │
│   │                              │ "update mental model"                │   │
│   │                              ▼                                      │   │
│   └─────────────────────────────────────────────────────────────────────┘   │
│                                  │                                          │
│                                  ▼                                          │
│   ┌─────────────────────────────────────────────────────────────────────┐   │
│   │                       MENTAL_MODEL                                  │   │
│   │                 (In SessionState.BELIEFS)                           │   │
│   │                                                                     │   │
│   │   Updated Mental Model:                                             │   │
│   │   {                                                                 │   │
│   │     "knowledge": {...},                                             │   │
│   │     "beliefs": {...},                                               │   │
│   │     "goals": {...},                                                 │   │
│   │     "attention": {...},                                             │   │
│   │     "last_updated": "turn_42",                                      │   │
│   │     "confidence": 0.75                                              │   │
│   │   }                                                                 │   │
│   │                                                                     │   │
│   │   Used by:                                                          │   │
│   │   - CONCIERGE_FSM: Adjust explanation depth                         │   │
│   │   - CAPABILITY_FABRIC: Route to appropriate tools                   │   │
│   │   - ANTICIPATORY_RESPONSE: Predict needs                            │   │
│   └─────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
│   Result: System maintains accurate model of user's mental state            │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

### F124: Mental Model Management → Cognitive Load Flow

**Trigger:** MENTAL_MODEL_MANAGEMENT detects cognitive load signals
**Outcome:** Response complexity adjusted for user's capacity

```
┌─────────────────────────────────────────────────────────────────────────────┐
│             F124: MENTAL MODEL MANAGEMENT → COGNITIVE LOAD FLOW             │
│                                                                             │
│   Purpose: Estimate user's cognitive capacity and adjust response complexity│
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│   ┌─────────────────────────────────────────────────────────────────────┐   │
│   │                  MENTAL_MODEL_MANAGEMENT                            │   │
│   │              "Cognitive Load Management"                            │   │
│   │                                                                     │   │
│   │   ┌───────────────────────────────────────────────────────────────┐ │   │
│   │   │              Cognitive Load Signals                           │ │   │
│   │   │                                                               │ │   │
│   │   │   Signs of HIGH Cognitive Load:                               │ │   │
│   │   │   ┌─────────────────────────────────────────────────────────┐ │ │   │
│   │   │   │ - Short, fragmented responses                           │ │ │   │
│   │   │   │ - Repeated questions (didn't absorb answer)             │ │ │   │
│   │   │   │ - Confusion markers ("I don't understand", "what?")     │ │ │   │
│   │   │   │ - Topic jumping (overwhelmed, avoiding)                 │ │ │   │
│   │   │   │ - Long response times (processing slowly)               │ │ │   │
│   │   │   │ - Time of day (late night = lower capacity)             │ │ │   │
│   │   │   └─────────────────────────────────────────────────────────┘ │ │   │
│   │   │                                                               │ │   │
│   │   │   Signs of LOW Cognitive Load:                                │ │   │
│   │   │   ┌─────────────────────────────────────────────────────────┐ │ │   │
│   │   │   │ - Detailed, coherent messages                           │ │ │   │
│   │   │   │ - Asking follow-up questions (engaged)                  │ │ │   │
│   │   │   │ - Building on previous context                          │ │ │   │
│   │   │   │ - Quick, accurate responses                             │ │ │   │
│   │   │   └─────────────────────────────────────────────────────────┘ │ │   │
│   │   └───────────────────────────────────────────────────────────────┘ │   │
│   │                              │                                      │   │
│   │   ┌───────────────────────────────────────────────────────────────┐ │   │
│   │   │              Cognitive Load Estimation                        │ │   │
│   │   │                                                               │ │   │
│   │   │   Formula:                                                    │ │   │
│   │   │   ┌─────────────────────────────────────────────────────────┐ │ │   │
│   │   │   │                                                         │ │ │   │
│   │   │   │   cognitive_load = (                                    │ │ │   │
│   │   │   │     task_complexity * 0.4 +                             │ │ │   │
│   │   │   │     active_threads_count * 0.2 +                        │ │ │   │
│   │   │   │     confusion_signals * 0.3 +                           │ │ │   │
│   │   │   │     fatigue_indicators * 0.1                            │ │ │   │
│   │   │   │   )                                                     │ │ │   │
│   │   │   │                                                         │ │ │   │
│   │   │   │   cognitive_capacity = 1.0 - cognitive_load             │ │ │   │
│   │   │   │                                                         │ │ │   │
│   │   │   │   Levels:                                               │ │ │   │
│   │   │   │   - capacity > 0.7: HIGH (can handle complexity)        │ │ │   │
│   │   │   │   - capacity 0.4-0.7: MODERATE (simplify somewhat)      │ │ │   │
│   │   │   │   - capacity < 0.4: LOW (simplify significantly)        │ │ │   │
│   │   │   │                                                         │ │ │   │
│   │   │   └─────────────────────────────────────────────────────────┘ │ │   │
│   │   └───────────────────────────────────────────────────────────────┘ │   │
│   │                              │                                      │   │
│   │                              │ cognitive_capacity estimate          │   │
│   │                              ▼                                      │   │
│   └─────────────────────────────────────────────────────────────────────┘   │
│                                  │                                          │
│                                  ▼                                          │
│   ┌─────────────────────────────────────────────────────────────────────┐   │
│   │                    Response Adaptation                              │   │
│   │                                                                     │   │
│   │   Based on Cognitive Capacity:                                      │   │
│   │   ┌───────────────────────────────────────────────────────────────┐ │   │
│   │   │                                                               │ │   │
│   │   │   HIGH Capacity (> 0.7):                                      │ │   │
│   │   │   - Full detail in responses                                  │ │   │
│   │   │   - Multiple options presented                                │ │   │
│   │   │   - Technical terms OK                                        │ │   │
│   │   │   - Longer explanations acceptable                            │ │   │
│   │   │                                                               │ │   │
│   │   │   MODERATE Capacity (0.4-0.7):                                │ │   │
│   │   │   - Summarize first, details on request                       │ │   │
│   │   │   - 2-3 options maximum                                       │ │   │
│   │   │   - Plain language preferred                                  │ │   │
│   │   │   - Bullet points over paragraphs                             │ │   │
│   │   │                                                               │ │   │
│   │   │   LOW Capacity (< 0.4):                                       │ │   │
│   │   │   - One thing at a time                                       │ │   │
│   │   │   - Binary choices (yes/no, A or B)                           │ │   │
│   │   │   - Very simple language                                      │ │   │
│   │   │   - Offer to pause/resume later                               │ │   │
│   │   │                                                               │ │   │
│   │   └───────────────────────────────────────────────────────────────┘ │   │
│   │                                                                     │   │
│   └─────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
│   Result: Response complexity matched to user's current capacity            │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

### F125: Capacity Estimate → Concierge Flow

**Trigger:** Cognitive capacity estimate available
**Outcome:** CONCIERGE_FSM adjusts response generation

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                  F125: CAPACITY ESTIMATE → CONCIERGE FLOW                   │
│                                                                             │
│   Purpose: Apply cognitive capacity to actual response generation           │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│   ┌─────────────────────────────────────────────────────────────────────┐   │
│   │                  MENTAL_MODEL_MANAGEMENT                            │   │
│   │                                                                     │   │
│   │   Capacity Estimate:                                                │   │
│   │   {                                                                 │   │
│   │     "cognitive_capacity": 0.55,                                     │   │
│   │     "level": "MODERATE",                                            │   │
│   │     "signals": ["confusion_once", "moderate_response_time"],        │   │
│   │     "recommendation": "simplify_somewhat"                           │   │
│   │   }                                                                 │   │
│   │                              │                                      │   │
│   │                              │ capacity estimate                    │   │
│   │                              ▼                                      │   │
│   └─────────────────────────────────────────────────────────────────────┘   │
│                                  │                                          │
│                                  ▼                                          │
│   ┌─────────────────────────────────────────────────────────────────────┐   │
│   │                      CONCIERGE_FSM                                  │   │
│   │                                                                     │   │
│   │   ┌───────────────────────────────────────────────────────────────┐ │   │
│   │   │              Apply Capacity to States                         │ │   │
│   │   │                                                               │ │   │
│   │   │   ACKING (Intent Classification):                             │ │   │
│   │   │   ┌─────────────────────────────────────────────────────────┐ │ │   │
│   │   │   │ If capacity == LOW:                                     │ │ │   │
│   │   │   │   - Confirm understanding more explicitly               │ │ │   │
│   │   │   │   - "Just to make sure I understand..."                 │ │ │   │
│   │   │   └─────────────────────────────────────────────────────────┘ │ │   │
│   │   │                                                               │ │   │
│   │   │   CLARIFYING (Questions):                                     │ │   │
│   │   │   ┌─────────────────────────────────────────────────────────┐ │ │   │
│   │   │   │ If capacity == LOW:                                     │ │ │   │
│   │   │   │   - One question at a time                              │ │ │   │
│   │   │   │   - Simple yes/no when possible                         │ │ │   │
│   │   │   │ If capacity == HIGH:                                    │ │ │   │
│   │   │   │   - Can ask compound questions                          │ │ │   │
│   │   │   │   - More efficient information gathering                │ │ │   │
│   │   │   └─────────────────────────────────────────────────────────┘ │ │   │
│   │   │                                                               │ │   │
│   │   │   DELIVERING (Final Response):                                │ │   │
│   │   │   ┌─────────────────────────────────────────────────────────┐ │ │   │
│   │   │   │ Adjust LLM prompt based on capacity:                    │ │ │   │
│   │   │   │                                                         │ │ │   │
│   │   │   │ system_prompt += f"""                                   │ │ │   │
│   │   │   │ User cognitive capacity: {capacity_level}               │ │ │   │
│   │   │   │ Response guidelines:                                    │ │ │   │
│   │   │   │ - Complexity: {complexity_guideline}                    │ │ │   │
│   │   │   │ - Options: {max_options}                                │ │ │   │
│   │   │   │ - Language: {language_level}                            │ │ │   │
│   │   │   │ - Format: {preferred_format}                            │ │ │   │
│   │   │   │ """                                                     │ │ │   │
│   │   │   └─────────────────────────────────────────────────────────┘ │ │   │
│   │   │                                                               │ │   │
│   │   └───────────────────────────────────────────────────────────────┘ │   │
│   │                              │                                      │   │
│   │                              │ capacity-adjusted LLM call           │   │
│   │                              ▼                                      │   │
│   │   ┌───────────────────────────────────────────────────────────────┐ │   │
│   │   │                    MODEL_GATEWAY                              │ │   │
│   │   │                                                               │ │   │
│   │   │  LLM generates response appropriate to user's capacity        │ │   │
│   │   │                                                               │ │   │
│   │   │  Example for MODERATE capacity:                               │ │   │
│   │   │  ┌─────────────────────────────────────────────────────────┐  │ │   │
│   │   │  │ "Here are 2 good dinner options:                        │  │ │   │
│   │   │  │  1. Pasta (quick, 20 min)                               │  │ │   │
│   │   │  │  2. Stir fry (healthy, 30 min)                          │  │ │   │
│   │   │  │                                                         │  │ │   │
│   │   │  │  Which sounds better?"                                  │  │ │   │
│   │   │  │                                                         │  │ │   │
│   │   │  │  (Not: "Here are 7 options with detailed nutritional   │  │ │   │
│   │   │  │   breakdowns and cooking complexity ratings...")        │  │ │   │
│   │   │  └─────────────────────────────────────────────────────────┘  │ │   │
│   │   └───────────────────────────────────────────────────────────────┘ │   │
│   │                                                                     │   │
│   └─────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
│   Result: Responses calibrated to user's cognitive capacity                 │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

### F126: Predictions → Anticipation Engine Flow

**Trigger:** PREDICTIVE_COMPLETION generates predictions
**Outcome:** CONVERSATIONAL_ANTICIPATION_ENGINE processes predictions

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                F126: PREDICTIONS → ANTICIPATION ENGINE FLOW                 │
│                                                                             │
│   Purpose: Convert predictions into actionable anticipation strategies      │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│   ┌─────────────────────────────────────────────────────────────────────┐   │
│   │                    PREDICTIVE_COMPLETION                            │   │
│   │              "Anticipatory Response System"                         │   │
│   │                                                                     │   │
│   │   ┌───────────────────────────────────────────────────────────────┐ │   │
│   │   │              Prediction Generation                            │ │   │
│   │   │                                                               │ │   │
│   │   │   Inputs:                                                     │ │   │
│   │   │   - Current conversation context                              │ │   │
│   │   │   - User's mental model (from ToM Engine)                     │ │   │
│   │   │   - Historical patterns (from K0)                             │ │   │
│   │   │   - Active narrative threads                                  │ │   │
│   │   │                                                               │ │   │
│   │   │   Prediction Types:                                           │ │   │
│   │   │   ┌─────────────────────────────────────────────────────────┐ │ │   │
│   │   │   │                                                         │ │ │   │
│   │   │   │   1. Next Query Prediction                              │ │ │   │
│   │   │   │      "User will likely ask about recipes next"          │ │ │   │
│   │   │   │      confidence: 0.82                                   │ │ │   │
│   │   │   │                                                         │ │ │   │
│   │   │   │   2. Clarification Need Prediction                      │ │ │   │
│   │   │   │      "User may be confused about portion sizes"         │ │ │   │
│   │   │   │      confidence: 0.65                                   │ │ │   │
│   │   │   │                                                         │ │ │   │
│   │   │   │   3. Tool Need Prediction                               │ │ │   │
│   │   │   │      "Will need recipe_search capability"               │ │ │   │
│   │   │   │      confidence: 0.78                                   │ │ │   │
│   │   │   │                                                         │ │ │   │
│   │   │   │   4. Completion Prediction                              │ │ │   │
│   │   │   │      "User typing: 'Can you also...' → wants related"   │ │ │   │
│   │   │   │      confidence: 0.70                                   │ │ │   │
│   │   │   │                                                         │ │ │   │
│   │   │   └─────────────────────────────────────────────────────────┘ │ │   │
│   │   └───────────────────────────────────────────────────────────────┘ │   │
│   │                              │                                      │   │
│   │                              │ predictions array                    │   │
│   │                              ▼                                      │   │
│   └─────────────────────────────────────────────────────────────────────┘   │
│                                  │                                          │
│                                  ▼                                          │
│   ┌─────────────────────────────────────────────────────────────────────┐   │
│   │            CONVERSATIONAL_ANTICIPATION_ENGINE                       │   │
│   │                                                                     │   │
│   │   ┌───────────────────────────────────────────────────────────────┐ │   │
│   │   │              Prediction Processing                            │ │   │
│   │   │                                                               │ │   │
│   │   │   1. Filter by Confidence Threshold                           │ │   │
│   │   │      Keep predictions with confidence > 0.6                   │ │   │
│   │   │                                                               │ │   │
│   │   │   2. Rank by Actionability                                    │ │   │
│   │   │      - Prefetchable > non-prefetchable                        │ │   │
│   │   │      - Low-cost > high-cost                                   │ │   │
│   │   │      - High-confidence > low-confidence                       │ │   │
│   │   │                                                               │ │   │
│   │   │   3. Generate Anticipation Actions                            │ │   │
│   │   │      ┌─────────────────────────────────────────────────────┐  │ │   │
│   │   │      │ Action: PREFETCH                                    │  │ │   │
│   │   │      │   target: "k0.query_recall(recipes)"                │  │ │   │
│   │   │      │   trigger_confidence: 0.82                          │  │ │   │
│   │   │      │                                                     │  │ │   │
│   │   │      │ Action: WARM_CAPABILITY                             │  │ │   │
│   │   │      │   target: "recipe_search"                           │  │ │   │
│   │   │      │   trigger_confidence: 0.78                          │  │ │   │
│   │   │      │                                                     │  │ │   │
│   │   │      │ Action: PREPARE_CLARIFICATION                       │  │ │   │
│   │   │      │   topic: "portion_sizes"                            │  │ │   │
│   │   │      │   trigger_confidence: 0.65                          │  │ │   │
│   │   │      └─────────────────────────────────────────────────────┘  │ │   │
│   │   └───────────────────────────────────────────────────────────────┘ │   │
│   │                              │                                      │   │
│   │                              │ anticipation actions                 │   │
│   │                              ▼                                      │   │
│   │   ┌───────────────────────────────────────────────────────────────┐ │   │
│   │   │              Output: Anticipation Queue                       │ │   │
│   │   │                                                               │ │   │
│   │   │   [                                                           │ │   │
│   │   │     {action: "PREFETCH", target: "...", execute: true},       │ │   │
│   │   │     {action: "WARM_CAPABILITY", target: "...", execute: true},│ │   │
│   │   │     {action: "SUGGEST", hint: "...", execute: false}          │ │   │
│   │   │   ]                                                           │ │   │
│   │   └───────────────────────────────────────────────────────────────┘ │   │
│   │                                                                     │   │
│   └─────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
│   Result: Actionable anticipation queue ready for execution                 │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

### F127: Anticipation → Speculative Execution Flow

**Trigger:** CONVERSATIONAL_ANTICIPATION_ENGINE outputs action queue
**Outcome:** High-confidence predictions speculatively executed

```
┌─────────────────────────────────────────────────────────────────────────────┐
│               F127: ANTICIPATION → SPECULATIVE EXECUTION FLOW               │
│                                                                             │
│   Purpose: Execute high-confidence predictions before user asks             │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│   ┌─────────────────────────────────────────────────────────────────────┐   │
│   │            CONVERSATIONAL_ANTICIPATION_ENGINE                       │   │
│   │                                                                     │   │
│   │   Anticipation Queue:                                               │   │
│   │   [                                                                 │   │
│   │     {action: "PREFETCH", target: "recipes", confidence: 0.82},      │   │
│   │     {action: "WARM_CAPABILITY", target: "recipe_search", conf: 0.78}│   │
│   │   ]                                                                 │   │
│   │                              │                                      │   │
│   │                              │ anticipation actions                 │   │
│   │                              ▼                                      │   │
│   └─────────────────────────────────────────────────────────────────────┘   │
│                                  │                                          │
│                                  ▼                                          │
│   ┌─────────────────────────────────────────────────────────────────────┐   │
│   │                    SPECULATIVE EXECUTOR                             │   │
│   │                                                                     │   │
│   │   ┌───────────────────────────────────────────────────────────────┐ │   │
│   │   │              Execution Decision                               │ │   │
│   │   │                                                               │ │   │
│   │   │   Execute Speculatively If:                                   │ │   │
│   │   │   ┌─────────────────────────────────────────────────────────┐ │ │   │
│   │   │   │ 1. confidence > SPECULATION_THRESHOLD (0.75)            │ │ │   │
│   │   │   │ 2. cost < MAX_SPECULATIVE_COST (low latency, no $)      │ │ │   │
│   │   │   │ 3. side_effects == none (read-only operations)          │ │ │   │
│   │   │   │ 4. user_not_typing (avoid invalidation)                 │ │ │   │
│   │   │   └─────────────────────────────────────────────────────────┘ │ │   │
│   │   │                                                               │ │   │
│   │   │   Do NOT Execute If:                                          │ │   │
│   │   │   ┌─────────────────────────────────────────────────────────┐ │ │   │
│   │   │   │ - Action has side effects (writes, API calls with cost) │ │ │   │
│   │   │   │ - User is actively typing (prediction may be wrong)     │ │ │   │
│   │   │   │ - Confidence below threshold                            │ │ │   │
│   │   │   │ - Resource budget exhausted                             │ │ │   │
│   │   │   └─────────────────────────────────────────────────────────┘ │ │   │
│   │   └───────────────────────────────────────────────────────────────┘ │   │
│   │                              │                                      │   │
│   │                              │ filtered actions                     │   │
│   │                              ▼                                      │   │
│   └─────────────────────────────────────────────────────────────────────┘   │
│                                  │                                          │
│         ┌────────────────────────┴────────────────────────┐                 │
│         │                                                 │                 │
│         ▼                                                 ▼                 │
│   ┌───────────────────────────────┐   ┌───────────────────────────────────┐ │
│   │     PREFETCH Execution        │   │   WARM_CAPABILITY Execution       │ │
│   │                               │   │                                   │ │
│   │  Via K0_GENERIC_CLIENT:       │   │  Via CAPABILITY_FABRIC:           │ │
│   │  ┌─────────────────────────┐  │   │  ┌─────────────────────────────┐  │ │
│   │  │ query_recall("recipes") │  │   │  │ warm_capability(            │  │ │
│   │  │                         │  │   │  │   "recipe_search",          │  │ │
│   │  │ Results cached in       │  │   │  │   preload_model=true        │  │ │
│   │  │ SPECULATIVE_CACHE       │  │   │  │ )                           │  │ │
│   │  │                         │  │   │  │                             │  │ │
│   │  │ TTL: 60 seconds         │  │   │  │ Tool ready for instant use  │  │ │
│   │  └─────────────────────────┘  │   │  └─────────────────────────────┘  │ │
│   │                               │   │                                   │ │
│   └───────────────────────────────┘   └───────────────────────────────────┘ │
│                                                                             │
│   ┌─────────────────────────────────────────────────────────────────────┐   │
│   │                    SPECULATIVE_CACHE                                │   │
│   │                                                                     │   │
│   │   Cache State:                                                      │   │
│   │   ┌───────────────────────────────────────────────────────────────┐ │   │
│   │   │ speculative_results: {                                        │ │   │
│   │   │   "recipes": {                                                │ │   │
│   │   │     data: [...recipe results...],                             │ │   │
│   │   │     fetched_at: "2024-01-15T10:30:00Z",                       │ │   │
│   │   │     ttl: 60s,                                                 │ │   │
│   │   │     prediction_confidence: 0.82                               │ │   │
│   │   │   }                                                           │ │   │
│   │   │ },                                                            │ │   │
│   │   │ warmed_capabilities: ["recipe_search"]                        │ │   │
│   │   └───────────────────────────────────────────────────────────────┘ │   │
│   │                                                                     │   │
│   │   When User Actually Asks:                                          │   │
│   │   ┌───────────────────────────────────────────────────────────────┐ │   │
│   │   │ if request matches speculative_cache:                         │ │   │
│   │   │   return cached_result  // ~0ms latency                       │ │   │
│   │   │   metrics.speculative_hit += 1                                │ │   │
│   │   │ else:                                                         │ │   │
│   │   │   execute_normally()                                          │ │   │
│   │   │   invalidate_speculative_cache()                              │ │   │
│   │   │   metrics.speculative_miss += 1                               │ │   │
│   │   └───────────────────────────────────────────────────────────────┘ │   │
│   │                                                                     │   │
│   │   Invalidation Triggers:                                            │   │
│   │   - User types different request                                    │   │
│   │   - TTL expires                                                     │   │
│   │   - Topic shifts detected                                           │   │
│   │   - Context changes significantly                                   │   │
│   └─────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
│   Result: High-confidence predictions pre-executed, reducing latency        │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## 14. MODULE LOADER FLOWS

### 14.1 Module Discovery & Registration Flow

- [x] **F128: Module Scanner Discovery Flow**
- [x] **F129: Tool Registry Registration Flow**
- [x] **F130: Prompt Registry Registration Flow**
- [x] **F131: Agent Registry → Factory Flow**

---

### F128: Module Scanner Discovery Flow

**Trigger:** K1 kernel startup or hot reload event
**Outcome:** All modules in k1/modules/* discovered and validated

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                     F128: MODULE SCANNER DISCOVERY FLOW                     │
│                                                                             │
│   Location: k1/kernel/loader.py                                             │
│   Purpose: Discover and validate all modules in the modules directory       │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│   ┌─────────────────────────────────────────────────────────────────────┐   │
│   │                    K1 Kernel Startup                                │   │
│   │                                                                     │   │
│   │   Trigger Events:                                                   │   │
│   │   - Initial kernel boot                                             │   │
│   │   - HOT_RELOAD_ENGINE file change event (dev mode)                  │   │
│   │   - Manual reload command                                           │   │
│   │                              │                                      │   │
│   │                              │ start discovery                      │   │
│   │                              ▼                                      │   │
│   └─────────────────────────────────────────────────────────────────────┘   │
│                                  │                                          │
│                                  ▼                                          │
│   ┌─────────────────────────────────────────────────────────────────────┐   │
│   │                      MODULE_SCANNER                                 │   │
│   │            "Discovers k1/modules/*/module.yaml"                     │   │
│   │                                                                     │   │
│   │   ┌───────────────────────────────────────────────────────────────┐ │   │
│   │   │              Discovery Process                                │ │   │
│   │   │                                                               │ │   │
│   │   │   Step 1: Scan Directory                                      │ │   │
│   │   │   ┌─────────────────────────────────────────────────────────┐ │ │   │
│   │   │   │ k1/modules/                                             │ │ │   │
│   │   │   │ ├── health/                                             │ │ │   │
│   │   │   │ │   ├── module.yaml      ← discovered                   │ │ │   │
│   │   │   │ │   ├── tools/                                          │ │ │   │
│   │   │   │ │   │   └── contract.yaml                               │ │ │   │
│   │   │   │ │   └── prompts/                                        │ │ │   │
│   │   │   │ │       └── *.md                                        │ │ │   │
│   │   │   │ ├── finance/                                            │ │ │   │
│   │   │   │ │   ├── module.yaml      ← discovered                   │ │ │   │
│   │   │   │ │   ├── tools/                                          │ │ │   │
│   │   │   │ │   └── prompts/                                        │ │ │   │
│   │   │   │ └── stress_table/                                       │ │ │   │
│   │   │   │     └── module.yaml      ← discovered                   │ │ │   │
│   │   │   └─────────────────────────────────────────────────────────┘ │ │   │
│   │   │                                                               │ │   │
│   │   │   Step 2: Parse module.yaml                                   │ │   │
│   │   │   ┌─────────────────────────────────────────────────────────┐ │ │   │
│   │   │   │ # health/module.yaml                                    │ │ │   │
│   │   │   │ name: health                                            │ │ │   │
│   │   │   │ version: 1.0.0                                          │ │ │   │
│   │   │   │ description: Health and wellness module                 │ │ │   │
│   │   │   │ tools:                                                  │ │ │   │
│   │   │   │   - tools/contract.yaml                                 │ │ │   │
│   │   │   │ prompts:                                                │ │ │   │
│   │   │   │   - prompts/*.md                                        │ │ │   │
│   │   │   │ agents:                                                 │ │ │   │
│   │   │   │   - agents/health_agent.yaml                            │ │ │   │
│   │   │   └─────────────────────────────────────────────────────────┘ │ │   │
│   │   │                                                               │ │   │
│   │   │   Step 3: Validate Module Structure                           │ │   │
│   │   │   ┌─────────────────────────────────────────────────────────┐ │ │   │
│   │   │   │ Checks:                                                 │ │ │   │
│   │   │   │ - module.yaml exists and is valid YAML                  │ │ │   │
│   │   │   │ - Required fields present (name, version)               │ │ │   │
│   │   │   │ - Referenced files exist                                │ │ │   │
│   │   │   │ - No circular dependencies                              │ │ │   │
│   │   │   │ - Version compatibility with K1 kernel                  │ │ │   │
│   │   │   └─────────────────────────────────────────────────────────┘ │ │   │
│   │   └───────────────────────────────────────────────────────────────┘ │   │
│   │                              │                                      │   │
│   │                              │ "discovers"                          │   │
│   │                              ▼                                      │   │
│   └─────────────────────────────────────────────────────────────────────┘   │
│                                  │                                          │
│                                  ▼                                          │
│   ┌─────────────────────────────────────────────────────────────────────┐   │
│   │                       MODULES_DIR                                   │   │
│   │                     "k1/modules/"                                   │   │
│   │                                                                     │   │
│   │   Discovered Modules:                                               │   │
│   │   ┌───────────────────────────────────────────────────────────────┐ │   │
│   │   │                                                               │ │   │
│   │   │   HEALTH_MODULE:                                              │ │   │
│   │   │     path: k1/modules/health/                                  │ │   │
│   │   │     status: VALID                                             │ │   │
│   │   │     tools: 3, prompts: 5, agents: 1                           │ │   │
│   │   │                                                               │ │   │
│   │   │   FINANCE_MODULE:                                             │ │   │
│   │   │     path: k1/modules/finance/                                 │ │   │
│   │   │     status: VALID                                             │ │   │
│   │   │     tools: 4, prompts: 3, agents: 1                           │ │   │
│   │   │                                                               │ │   │
│   │   │   STRESS_MODULE:                                              │ │   │
│   │   │     path: k1/modules/stress_table/                            │ │   │
│   │   │     status: VALID                                             │ │   │
│   │   │     tools: 2, prompts: 2, agents: 0                           │ │   │
│   │   │                                                               │ │   │
│   │   └───────────────────────────────────────────────────────────────┘ │   │
│   │                                                                     │   │
│   │   Next: Register with appropriate registries                        │   │
│   │   (See F129, F130, F131)                                            │   │
│   └─────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
│   Result: All valid modules discovered and ready for registration           │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

### F129: Tool Registry Registration Flow

**Trigger:** MODULE_SCANNER discovers module with tools/contract.yaml
**Outcome:** Tools registered in TOOL_REGISTRY, exposed to CAPABILITY_REGISTRY

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                   F129: TOOL REGISTRY REGISTRATION FLOW                     │
│                                                                             │
│   Purpose: Auto-register tools from contract.yaml into capability system    │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│   ┌─────────────────────────────────────────────────────────────────────┐   │
│   │                      MODULE_SCANNER                                 │   │
│   │                                                                     │   │
│   │   For each discovered module with tools:                            │   │
│   │   ┌───────────────────────────────────────────────────────────────┐ │   │
│   │   │ health/tools/contract.yaml                                    │ │   │
│   │   │ finance/tools/contract.yaml                                   │ │   │
│   │   │ stress_table/tools/contract.yaml                              │ │   │
│   │   └───────────────────────────────────────────────────────────────┘ │   │
│   │                              │                                      │   │
│   │                              │ "registers"                          │   │
│   │                              ▼                                      │   │
│   └─────────────────────────────────────────────────────────────────────┘   │
│                                  │                                          │
│                                  ▼                                          │
│   ┌─────────────────────────────────────────────────────────────────────┐   │
│   │                       TOOL_REGISTRY                                 │   │
│   │             "Auto-registers from contract.yaml"                     │   │
│   │                                                                     │   │
│   │   ┌───────────────────────────────────────────────────────────────┐ │   │
│   │   │              Parse contract.yaml                              │ │   │
│   │   │                                                               │ │   │
│   │   │   # health/tools/contract.yaml                                │ │   │
│   │   │   ┌─────────────────────────────────────────────────────────┐ │ │   │
│   │   │   │ tools:                                                  │ │ │   │
│   │   │   │   - name: health.track_workout                          │ │ │   │
│   │   │   │     description: Track a workout session                │ │ │   │
│   │   │   │     inputs:                                             │ │ │   │
│   │   │   │       - name: workout_type                              │ │ │   │
│   │   │   │         type: string                                    │ │ │   │
│   │   │   │         required: true                                  │ │ │   │
│   │   │   │       - name: duration_minutes                          │ │ │   │
│   │   │   │         type: integer                                   │ │ │   │
│   │   │   │     outputs:                                            │ │ │   │
│   │   │   │       - name: workout_id                                │ │ │   │
│   │   │   │         type: string                                    │ │ │   │
│   │   │   │     mcp_server: health_mcp                              │ │ │   │
│   │   │   │     security_band: GREEN                                │ │ │   │
│   │   │   │                                                         │ │ │   │
│   │   │   │   - name: health.get_vitals                             │ │ │   │
│   │   │   │     description: Retrieve current vitals                │ │ │   │
│   │   │   │     ...                                                 │ │ │   │
│   │   │   └─────────────────────────────────────────────────────────┘ │ │   │
│   │   └───────────────────────────────────────────────────────────────┘ │   │
│   │                              │                                      │   │
│   │   ┌───────────────────────────────────────────────────────────────┐ │   │
│   │   │              Build Tool Registry Entry                        │ │   │
│   │   │                                                               │ │   │
│   │   │   For each tool in contract.yaml:                             │ │   │
│   │   │   ┌─────────────────────────────────────────────────────────┐ │ │   │
│   │   │   │ tool_entry = {                                          │ │ │   │
│   │   │   │   "id": "health.track_workout",                         │ │ │   │
│   │   │   │   "module": "health",                                   │ │ │   │
│   │   │   │   "description": "Track a workout session",             │ │ │   │
│   │   │   │   "inputs_schema": {...},                               │ │ │   │
│   │   │   │   "outputs_schema": {...},                              │ │ │   │
│   │   │   │   "mcp_server": "health_mcp",                           │ │ │   │
│   │   │   │   "security_band": "GREEN",                             │ │ │   │
│   │   │   │   "version": "1.0.0",                                   │ │ │   │
│   │   │   │   "registered_at": "2024-01-15T10:30:00Z"               │ │ │   │
│   │   │   │ }                                                       │ │ │   │
│   │   │   └─────────────────────────────────────────────────────────┘ │ │   │
│   │   └───────────────────────────────────────────────────────────────┘ │   │
│   │                              │                                      │   │
│   │                              │ "exposes"                            │   │
│   │                              ▼                                      │   │
│   └─────────────────────────────────────────────────────────────────────┘   │
│                                  │                                          │
│                                  ▼                                          │
│   ┌─────────────────────────────────────────────────────────────────────┐   │
│   │                    CAPABILITY_REGISTRY                              │   │
│   │                                                                     │   │
│   │   Tools exposed as capabilities:                                    │   │
│   │   ┌───────────────────────────────────────────────────────────────┐ │   │
│   │   │                                                               │ │   │
│   │   │   TOOL_CAPABILITIES:                                          │ │   │
│   │   │   ┌─────────────────────────────────────────────────────────┐ │ │   │
│   │   │   │ - health.track_workout                                  │ │ │   │
│   │   │   │ - health.get_vitals                                     │ │ │   │
│   │   │   │ - health.log_meal                                       │ │ │   │
│   │   │   │ - finance.check_balance                                 │ │ │   │
│   │   │   │ - finance.track_expense                                 │ │ │   │
│   │   │   │ - stress_table.get_stress_level                         │ │ │   │
│   │   │   └─────────────────────────────────────────────────────────┘ │ │   │
│   │   │                                                               │ │   │
│   │   │   Now available to:                                           │ │   │
│   │   │   - CAPABILITY_FABRIC (for invocation)                        │ │   │
│   │   │   - PLANNER_AGENT (for plan generation)                       │ │   │
│   │   │   - TOOL_DISCOVER_CAPABILITIES (for discovery)                │ │   │
│   │   │                                                               │ │   │
│   │   └───────────────────────────────────────────────────────────────┘ │   │
│   └─────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
│   Result: Tools available for invocation via Capability Fabric              │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

### F130: Prompt Registry Registration Flow

**Trigger:** MODULE_SCANNER discovers module with prompts/*.md
**Outcome:** Prompts registered in PROMPT_REGISTRY for LLM context

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                   F130: PROMPT REGISTRY REGISTRATION FLOW                   │
│                                                                             │
│   Purpose: Register markdown prompt assets for module-specific LLM context  │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│   ┌─────────────────────────────────────────────────────────────────────┐   │
│   │                      MODULE_SCANNER                                 │   │
│   │                                                                     │   │
│   │   For each discovered module with prompts:                          │   │
│   │   ┌───────────────────────────────────────────────────────────────┐ │   │
│   │   │ health/prompts/                                               │ │   │
│   │   │ ├── system_prompt.md                                          │ │   │
│   │   │ ├── workout_guidance.md                                       │ │   │
│   │   │ ├── nutrition_advice.md                                       │ │   │
│   │   │ └── motivation.md                                             │ │   │
│   │   └───────────────────────────────────────────────────────────────┘ │   │
│   │                              │                                      │   │
│   │                              │ "registers prompts"                  │   │
│   │                              ▼                                      │   │
│   └─────────────────────────────────────────────────────────────────────┘   │
│                                  │                                          │
│                                  ▼                                          │
│   ┌─────────────────────────────────────────────────────────────────────┐   │
│   │                      PROMPT_REGISTRY                                │   │
│   │               "Markdown prompt assets"                              │   │
│   │                                                                     │   │
│   │   ┌───────────────────────────────────────────────────────────────┐ │   │
│   │   │              Parse and Index Prompts                          │ │   │
│   │   │                                                               │ │   │
│   │   │   For each .md file:                                          │ │   │
│   │   │   ┌─────────────────────────────────────────────────────────┐ │ │   │
│   │   │   │ # health/prompts/system_prompt.md                       │ │ │   │
│   │   │   │                                                         │ │ │   │
│   │   │   │ ---                                                     │ │ │   │
│   │   │   │ id: health.system_prompt                                │ │ │   │
│   │   │   │ type: system                                            │ │ │   │
│   │   │   │ version: 1.0.0                                          │ │ │   │
│   │   │   │ ---                                                     │ │ │   │
│   │   │   │                                                         │ │ │   │
│   │   │   │ You are a health and wellness assistant...              │ │ │   │
│   │   │   │ Your role is to help users track their fitness...       │ │ │   │
│   │   │   │                                                         │ │ │   │
│   │   │   │ ## Guidelines                                           │ │ │   │
│   │   │   │ - Be encouraging but realistic                          │ │ │   │
│   │   │   │ - Never provide medical advice                          │ │ │   │
│   │   │   │ - Reference user's past data when relevant              │ │ │   │
│   │   │   └─────────────────────────────────────────────────────────┘ │ │   │
│   │   └───────────────────────────────────────────────────────────────┘ │   │
│   │                              │                                      │   │
│   │   ┌───────────────────────────────────────────────────────────────┐ │   │
│   │   │              Build Prompt Registry Entry                      │ │   │
│   │   │                                                               │ │   │
│   │   │   prompt_entry = {                                            │ │   │
│   │   │     "id": "health.system_prompt",                             │ │   │
│   │   │     "module": "health",                                       │ │   │
│   │   │     "type": "system",                                         │ │   │
│   │   │     "content": "You are a health and wellness...",            │ │   │
│   │   │     "version": "1.0.0",                                       │ │   │
│   │   │     "variables": [],  // {{user_name}}, {{history}}           │ │   │
│   │   │     "file_path": "health/prompts/system_prompt.md"            │ │   │
│   │   │   }                                                           │ │   │
│   │   └───────────────────────────────────────────────────────────────┘ │   │
│   │                              │                                      │   │
│   │   ┌───────────────────────────────────────────────────────────────┐ │   │
│   │   │              Registry Contents                                │ │   │
│   │   │                                                               │ │   │
│   │   │   Registered Prompts:                                         │ │   │
│   │   │   ┌─────────────────────────────────────────────────────────┐ │ │   │
│   │   │   │ health.system_prompt      (type: system)                │ │ │   │
│   │   │   │ health.workout_guidance   (type: context)               │ │ │   │
│   │   │   │ health.nutrition_advice   (type: context)               │ │ │   │
│   │   │   │ health.motivation         (type: inject)                │ │ │   │
│   │   │   │ finance.system_prompt     (type: system)                │ │ │   │
│   │   │   │ finance.budget_guidance   (type: context)               │ │ │   │
│   │   │   └─────────────────────────────────────────────────────────┘ │ │   │
│   │   │                                                               │ │   │
│   │   │   Prompt Types:                                               │ │   │
│   │   │   - system: Base system prompt for agents                     │ │   │
│   │   │   - context: Injected when topic matches                      │ │   │
│   │   │   - inject: Dynamically added based on conditions             │ │   │
│   │   └───────────────────────────────────────────────────────────────┘ │   │
│   │                                                                     │   │
│   └─────────────────────────────────────────────────────────────────────┘   │
│                                  │                                          │
│                                  │ prompts available to                     │
│                                  ▼                                          │
│   ┌─────────────────────────────────────────────────────────────────────┐   │
│   │                    LLM Context Consumers                            │   │
│   │                                                                     │   │
│   │   - CONCIERGE_FSM: Module-specific system prompts                   │   │
│   │   - DYNAMIC_AGENTS: Agent-specific prompts                          │   │
│   │   - PLANNER_AGENT: Domain context for planning                      │   │
│   │   - MEMORY_WRITER_AGENTS: Summarization prompts                     │   │
│   │                                                                     │   │
│   └─────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
│   Result: Prompts indexed and available for LLM context injection           │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

### F131: Agent Registry → Factory Flow

**Trigger:** MODULE_SCANNER discovers module with agents/*.yaml
**Outcome:** Agent templates registered, AGENT_FACTORY can spawn instances

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                    F131: AGENT REGISTRY → FACTORY FLOW                      │
│                                                                             │
│   Purpose: Register agent templates and enable on-demand spawning           │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│   ┌─────────────────────────────────────────────────────────────────────┐   │
│   │                      MODULE_SCANNER                                 │   │
│   │                                                                     │   │
│   │   For each discovered module with agents:                           │   │
│   │   ┌───────────────────────────────────────────────────────────────┐ │   │
│   │   │ health/agents/health_agent.yaml                               │ │   │
│   │   │ finance/agents/finance_agent.yaml                             │ │   │
│   │   └───────────────────────────────────────────────────────────────┘ │   │
│   │                              │                                      │   │
│   │                              │ "registers agent templates"          │   │
│   │                              ▼                                      │   │
│   └─────────────────────────────────────────────────────────────────────┘   │
│                                  │                                          │
│                                  ▼                                          │
│   ┌─────────────────────────────────────────────────────────────────────┐   │
│   │                      AGENT_REGISTRY                                 │   │
│   │               "YAML agent templates"                                │   │
│   │                                                                     │   │
│   │   ┌───────────────────────────────────────────────────────────────┐ │   │
│   │   │              Parse Agent Template                             │ │   │
│   │   │                                                               │ │   │
│   │   │   # health/agents/health_agent.yaml                           │ │   │
│   │   │   ┌─────────────────────────────────────────────────────────┐ │ │   │
│   │   │   │ name: health_agent                                      │ │ │   │
│   │   │   │ version: 1.0.0                                          │ │ │   │
│   │   │   │ description: Health domain specialist agent             │ │ │   │
│   │   │   │                                                         │ │ │   │
│   │   │   │ capabilities:                                           │ │ │   │
│   │   │   │   - health.track_workout                                │ │ │   │
│   │   │   │   - health.get_vitals                                   │ │ │   │
│   │   │   │   - health.log_meal                                     │ │ │   │
│   │   │   │                                                         │ │ │   │
│   │   │   │ prompts:                                                │ │ │   │
│   │   │   │   system: health.system_prompt                          │ │ │   │
│   │   │   │   context:                                              │ │ │   │
│   │   │   │     - health.workout_guidance                           │ │ │   │
│   │   │   │     - health.nutrition_advice                           │ │ │   │
│   │   │   │                                                         │ │ │   │
│   │   │   │ lifecycle:                                              │ │ │   │
│   │   │   │   idle_ttl_seconds: 60                                  │ │ │   │
│   │   │   │   max_concurrent: 3                                     │ │ │   │
│   │   │   │   priority: INTERACTIVE                                 │ │ │   │
│   │   │   │                                                         │ │ │   │
│   │   │   │ model:                                                  │ │ │   │
│   │   │   │   preferred: gpt-4                                      │ │ │   │
│   │   │   │   fallback: gpt-3.5-turbo                               │ │ │   │
│   │   │   │   temperature: 0.7                                      │ │ │   │
│   │   │   └─────────────────────────────────────────────────────────┘ │ │   │
│   │   └───────────────────────────────────────────────────────────────┘ │   │
│   │                              │                                      │   │
│   │   ┌───────────────────────────────────────────────────────────────┐ │   │
│   │   │              Template Registry                                │ │   │
│   │   │                                                               │ │   │
│   │   │   AGENT_TEMPLATES:                                            │ │   │
│   │   │   ┌─────────────────────────────────────────────────────────┐ │ │   │
│   │   │   │ health_agent:                                           │ │ │   │
│   │   │   │   module: health                                        │ │ │   │
│   │   │   │   capabilities: [3 tools]                               │ │ │   │
│   │   │   │   prompts: system + 2 context                           │ │ │   │
│   │   │   │   status: READY                                         │ │ │   │
│   │   │   │                                                         │ │ │   │
│   │   │   │ finance_agent:                                          │ │ │   │
│   │   │   │   module: finance                                       │ │ │   │
│   │   │   │   capabilities: [4 tools]                               │ │ │   │
│   │   │   │   prompts: system + 1 context                           │ │ │   │
│   │   │   │   status: READY                                         │ │ │   │
│   │   │   └─────────────────────────────────────────────────────────┘ │ │   │
│   │   └───────────────────────────────────────────────────────────────┘ │   │
│   │                              │                                      │   │
│   │                              │ "templates"                          │   │
│   │                              ▼                                      │   │
│   └─────────────────────────────────────────────────────────────────────┘   │
│                                  │                                          │
│                                  ▼                                          │
│   ┌─────────────────────────────────────────────────────────────────────┐   │
│   │                       AGENT_FACTORY                                 │   │
│   │             "Creates from YAML templates"                           │   │
│   │                                                                     │   │
│   │   ┌───────────────────────────────────────────────────────────────┐ │   │
│   │   │              Factory Operations                               │ │   │
│   │   │                                                               │ │   │
│   │   │   spawn(template_name, context):                              │ │   │
│   │   │   ┌─────────────────────────────────────────────────────────┐ │ │   │
│   │   │   │ 1. Load template from AGENT_REGISTRY                    │ │ │   │
│   │   │   │ 2. Resolve prompts from PROMPT_REGISTRY                 │ │ │   │
│   │   │   │ 3. Verify capabilities in CAPABILITY_REGISTRY           │ │ │   │
│   │   │   │ 4. Create agent instance with:                          │ │ │   │
│   │   │   │    - Unique agent_id                                    │ │ │   │
│   │   │   │    - Private mailbox (MPSC queue)                       │ │ │   │
│   │   │   │    - Resolved prompts                                   │ │ │   │
│   │   │   │    - Capability bindings                                │ │ │   │
│   │   │   │ 5. Register in DYNAMIC_INSTANCES                        │ │ │   │
│   │   │   │ 6. Start lifecycle FSM (PENDING → WARMING → ACTIVE)     │ │ │   │
│   │   │   └─────────────────────────────────────────────────────────┘ │ │   │
│   │   └───────────────────────────────────────────────────────────────┘ │   │
│   │                              │                                      │   │
│   │                              │ "spawns"                             │   │
│   │                              ▼                                      │   │
│   └─────────────────────────────────────────────────────────────────────┘   │
│                                  │                                          │
│                                  ▼                                          │
│   ┌─────────────────────────────────────────────────────────────────────┐   │
│   │                     DYNAMIC_INSTANCES                               │   │
│   │               "Created on-demand via Fabric"                        │   │
│   │                                                                     │   │
│   │   Active Agents:                                                    │   │
│   │   ┌───────────────────────────────────────────────────────────────┐ │   │
│   │   │ agent_id: "health_agent_abc123"                               │ │   │
│   │   │   template: health_agent                                      │ │   │
│   │   │   state: ACTIVE                                               │ │   │
│   │   │   spawned_at: "2024-01-15T10:35:00Z"                          │ │   │
│   │   │   idle_since: null                                            │ │   │
│   │   │   tasks_completed: 3                                          │ │   │
│   │   └───────────────────────────────────────────────────────────────┘ │   │
│   │                                                                     │   │
│   │   Lifecycle: PENDING → WARMING → ACTIVE → IDLE → DRAINING → TERM    │   │
│   │                                                                     │   │
│   └─────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
│   Result: Agent templates ready, Factory can spawn instances on demand      │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## 15. EVENT BUS & COORDINATION FLOWS

### 15.1 Event Bus Routing Flow

- [x] **F132: Capability Invoked Event Flow**
- [x] **F133: Capability Completed Event Flow**
- [x] **F134: Affect Analyzed Event Flow**
- [x] **F135: Constraint Progress Event Flow**

### 15.2 WFQ Scheduling Flow

- [x] **F136: Priority-Based Event Bus Delivery Flow**
- [x] **F137: Priority-Based Mailbox Router Flow**

---

### F132: Capability Invoked Event Flow

**Trigger:** CAPABILITY_FABRIC invokes a capability
**Outcome:** k1.capability.invoked.v1 event published and routed

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                    F132: CAPABILITY INVOKED EVENT FLOW                      │
│                                                                             │
│   Event: k1.capability.invoked.v1                                           │
│   Purpose: Notify interested parties when capability execution starts       │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│   ┌─────────────────────────────────────────────────────────────────────┐   │
│   │                     CAPABILITY_FABRIC                               │   │
│   │                                                                     │   │
│   │   Capability Invocation:                                            │   │
│   │   ┌───────────────────────────────────────────────────────────────┐ │   │
│   │   │ capability: "health.track_workout"                            │ │   │
│   │   │ inputs: {workout_type: "running", duration: 30}               │ │   │
│   │   │ invoker: "CONCIERGE_FSM"                                      │ │   │
│   │   │ trace_id: "cog_abc123"                                        │ │   │
│   │   └───────────────────────────────────────────────────────────────┘ │   │
│   │                              │                                      │   │
│   │                              │ "k1.capability.invoked.v1"           │   │
│   │                              ▼                                      │   │
│   └─────────────────────────────────────────────────────────────────────┘   │
│                                  │                                          │
│                                  ▼                                          │
│   ┌─────────────────────────────────────────────────────────────────────┐   │
│   │                        EVENT_BUS                                    │   │
│   │                  "K1 Event Bus (Pub/Sub Topics)"                    │   │
│   │                                                                     │   │
│   │   ┌───────────────────────────────────────────────────────────────┐ │   │
│   │   │              Event Structure                                  │ │   │
│   │   │                                                               │ │   │
│   │   │   {                                                           │ │   │
│   │   │     "topic": "k1.capability.invoked.v1",                      │ │   │
│   │   │     "timestamp": "2024-01-15T10:30:00.123Z",                  │ │   │
│   │   │     "trace_id": "cog_abc123",                                 │ │   │
│   │   │     "payload": {                                              │ │   │
│   │   │       "capability_id": "health.track_workout",                │ │   │
│   │   │       "invocation_id": "inv_xyz789",                          │ │   │
│   │   │       "invoker": "CONCIERGE_FSM",                             │ │   │
│   │   │       "inputs": {...},                                        │ │   │
│   │   │       "priority": "INTERACTIVE"                               │ │   │
│   │   │     }                                                         │ │   │
│   │   │   }                                                           │ │   │
│   │   └───────────────────────────────────────────────────────────────┘ │   │
│   │                              │                                      │   │
│   │                              │ "Route capability events"            │   │
│   │                              ▼                                      │   │
│   └─────────────────────────────────────────────────────────────────────┘   │
│                                  │                                          │
│         ┌────────────────────────┼────────────────────────┐                 │
│         │                        │                        │                 │
│         ▼                        ▼                        ▼                 │
│   ┌───────────────┐       ┌───────────────┐       ┌───────────────┐         │
│   │ FABRIC_MAILBOX│       │CONCIERGE_     │       │DISTRIBUTED_   │         │
│   │               │       │   MAILBOX     │       │   TRACING     │         │
│   │ Subscriber:   │       │               │       │               │         │
│   │ CAPABILITY_   │       │ Subscriber:   │       │ Subscriber:   │         │
│   │ FABRIC        │       │ CONCIERGE_FSM │       │ Observability │         │
│   │               │       │               │       │               │         │
│   │ Purpose:      │       │ Purpose:      │       │ Purpose:      │         │
│   │ Track active  │       │ Update UI     │       │ Trace span    │         │
│   │ invocations   │       │ "Working..."  │       │ recording     │         │
│   └───────────────┘       └───────────────┘       └───────────────┘         │
│                                                                             │
│   ┌─────────────────────────────────────────────────────────────────────┐   │
│   │                    TOPIC_PATTERNS                                   │   │
│   │                                                                     │   │
│   │   k1.capability.invoked.v1 → Subscribers:                           │   │
│   │   - FABRIC_MAILBOX (internal tracking)                              │   │
│   │   - CONCIERGE_MAILBOX (UI updates)                                  │   │
│   │   - DISTRIBUTED_TRACING (span creation)                             │   │
│   │   - METRICS_AGGREGATOR (latency tracking)                           │   │
│   └─────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
│   Result: All subscribers notified of capability invocation start           │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

### F133: Capability Completed Event Flow

**Trigger:** CAPABILITY_FABRIC completes capability execution
**Outcome:** k1.capability.completed.v1 event with result published

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                   F133: CAPABILITY COMPLETED EVENT FLOW                     │
│                                                                             │
│   Event: k1.capability.completed.v1                                         │
│   Purpose: Notify when capability execution completes with result           │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│   ┌─────────────────────────────────────────────────────────────────────┐   │
│   │                     CAPABILITY_FABRIC                               │   │
│   │                                                                     │   │
│   │   Capability Execution Complete:                                    │   │
│   │   ┌───────────────────────────────────────────────────────────────┐ │   │
│   │   │ capability: "health.track_workout"                            │ │   │
│   │   │ invocation_id: "inv_xyz789"                                   │ │   │
│   │   │ status: "SUCCESS"                                             │ │   │
│   │   │ result: {workout_id: "wrk_456", calories_burned: 320}         │ │   │
│   │   │ duration_ms: 245                                              │ │   │
│   │   └───────────────────────────────────────────────────────────────┘ │   │
│   │                              │                                      │   │
│   │                              │ "k1.capability.completed.v1 + result"│   │
│   │                              ▼                                      │   │
│   └─────────────────────────────────────────────────────────────────────┘   │
│                                  │                                          │
│                                  ▼                                          │
│   ┌─────────────────────────────────────────────────────────────────────┐   │
│   │                        EVENT_BUS                                    │   │
│   │                                                                     │   │
│   │   ┌───────────────────────────────────────────────────────────────┐ │   │
│   │   │              Event Structure                                  │ │   │
│   │   │                                                               │ │   │
│   │   │   {                                                           │ │   │
│   │   │     "topic": "k1.capability.completed.v1",                    │ │   │
│   │   │     "timestamp": "2024-01-15T10:30:00.368Z",                  │ │   │
│   │   │     "trace_id": "cog_abc123",                                 │ │   │
│   │   │     "payload": {                                              │ │   │
│   │   │       "capability_id": "health.track_workout",                │ │   │
│   │   │       "invocation_id": "inv_xyz789",                          │ │   │
│   │   │       "status": "SUCCESS",  // or "FAILURE", "TIMEOUT"        │ │   │
│   │   │       "result": {                                             │ │   │
│   │   │         "workout_id": "wrk_456",                              │ │   │
│   │   │         "calories_burned": 320                                │ │   │
│   │   │       },                                                      │ │   │
│   │   │       "error": null,  // populated on failure                 │ │   │
│   │   │       "duration_ms": 245                                      │ │   │
│   │   │     }                                                         │ │   │
│   │   │   }                                                           │ │   │
│   │   └───────────────────────────────────────────────────────────────┘ │   │
│   │                              │                                      │   │
│   │                              │ "Notify completion"                  │   │
│   │                              ▼                                      │   │
│   └─────────────────────────────────────────────────────────────────────┘   │
│                                  │                                          │
│         ┌────────────────────────┼────────────────────────┐                 │
│         │                        │                        │                 │
│         ▼                        ▼                        ▼                 │
│   ┌───────────────┐       ┌───────────────┐       ┌───────────────┐         │
│   │CONCIERGE_     │       │TOOL_RESULT_   │       │ORCHESTRATOR_  │         │
│   │   MAILBOX     │       │   BUFFER      │       │   ACTOR       │         │
│   │               │       │               │       │               │         │
│   │ Action:       │       │ Action:       │       │ Action:       │         │
│   │ Trigger       │       │ Stage result  │       │ Update DAG    │         │
│   │ DELIVERING    │       │ for LLM       │       │ execution     │         │
│   │ state         │       │ context       │       │ state         │         │
│   └───────────────┘       └───────────────┘       └───────────────┘         │
│                                                                             │
│   ┌─────────────────────────────────────────────────────────────────────┐   │
│   │                   Result Flow to User                               │   │
│   │                                                                     │   │
│   │   EVENT_BUS → CONCIERGE_MAILBOX → CONCIERGE_FSM                     │   │
│   │                                        │                            │   │
│   │                                        ▼                            │   │
│   │                               TOOL_RESULT_BUFFER                    │   │
│   │                                        │                            │   │
│   │                                        ▼                            │   │
│   │                               DELIVERING state                      │   │
│   │                                        │                            │   │
│   │                                        ▼                            │   │
│   │                               MODEL_GATEWAY (LLM)                   │   │
│   │                                        │                            │   │
│   │                                        ▼                            │   │
│   │                               User Response                         │   │
│   └─────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
│   Result: Capability result delivered to all interested parties             │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

### F134: Affect Analyzed Event Flow

**Trigger:** ULTRABERT_EMOTIONS completes affect analysis
**Outcome:** k1.affect.analyzed.v1 event updates AFFECTIVE_CONTEXT

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                     F134: AFFECT ANALYZED EVENT FLOW                        │
│                                                                             │
│   Event: k1.affect.analyzed.v1                                              │
│   Purpose: Propagate emotional analysis to routing and personalization      │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│   ┌─────────────────────────────────────────────────────────────────────┐   │
│   │                    ULTRABERT_EMOTIONS                               │   │
│   │                                                                     │   │
│   │   Affect Analysis Result:                                           │   │
│   │   ┌───────────────────────────────────────────────────────────────┐ │   │
│   │   │ input: "I'm so frustrated with this diet thing"               │ │   │
│   │   │                                                               │ │   │
│   │   │ analysis: {                                                   │ │   │
│   │   │   "valence": 0.25,        // negative                         │ │   │
│   │   │   "arousal": 0.75,        // high activation                  │ │   │
│   │   │   "primary_emotion": "frustration",                           │ │   │
│   │   │   "secondary_emotions": ["disappointment", "impatience"],     │ │   │
│   │   │   "confidence": 0.89                                          │ │   │
│   │   │ }                                                             │ │   │
│   │   └───────────────────────────────────────────────────────────────┘ │   │
│   │                              │                                      │   │
│   │                              │ "k1.affect.analyzed.v1"              │   │
│   │                              ▼                                      │   │
│   └─────────────────────────────────────────────────────────────────────┘   │
│                                  │                                          │
│                                  ▼                                          │
│   ┌─────────────────────────────────────────────────────────────────────┐   │
│   │                        EVENT_BUS                                    │   │
│   │                                                                     │   │
│   │   ┌───────────────────────────────────────────────────────────────┐ │   │
│   │   │              Event Structure                                  │ │   │
│   │   │                                                               │ │   │
│   │   │   {                                                           │ │   │
│   │   │     "topic": "k1.affect.analyzed.v1",                         │ │   │
│   │   │     "timestamp": "2024-01-15T10:30:00.045Z",                  │ │   │
│   │   │     "trace_id": "cog_abc123",                                 │ │   │
│   │   │     "payload": {                                              │ │   │
│   │   │       "turn_id": 42,                                          │ │   │
│   │   │       "valence": 0.25,                                        │ │   │
│   │   │       "arousal": 0.75,                                        │ │   │
│   │   │       "primary_emotion": "frustration",                       │ │   │
│   │   │       "secondary_emotions": ["disappointment", "impatience"], │ │   │
│   │   │       "confidence": 0.89                                      │ │   │
│   │   │     }                                                         │ │   │
│   │   │   }                                                           │ │   │
│   │   └───────────────────────────────────────────────────────────────┘ │   │
│   │                              │                                      │   │
│   │                              │ "Update affective_context"           │   │
│   │                              ▼                                      │   │
│   └─────────────────────────────────────────────────────────────────────┘   │
│                                  │                                          │
│         ┌────────────────────────┼────────────────────────┐                 │
│         │                        │                        │                 │
│         ▼                        ▼                        ▼                 │
│   ┌───────────────┐       ┌───────────────┐       ┌───────────────┐         │
│   │AFFECTIVE_     │       │AFFECTIVE_     │       │EMOTIONAL_     │         │
│   │   CONTEXT     │       │   ROUTING     │       │   MIRRORING   │         │
│   │               │       │               │       │               │         │
│   │ SessionState  │       │ FABRIC_POLICY │       │ CONCIERGE     │         │
│   │ Update:       │       │               │       │               │         │
│   │ ┌───────────┐ │       │ Routing       │       │ Adjust tone   │         │
│   │ │valence:   │ │       │ adjustment:   │       │ for response: │         │
│   │ │  0.25     │ │       │ - Prefer      │       │ - Empathetic  │         │
│   │ │arousal:   │ │       │   supportive  │       │ - Validating  │         │
│   │ │  0.75     │ │       │   providers   │       │ - Calming     │         │
│   │ │emotion:   │ │       │ - Reduce      │       │               │         │
│   │ │frustration│ │       │   complexity  │       │               │         │
│   │ └───────────┘ │       └───────────────┘       └───────────────┘         │
│   └───────────────┘                                                         │
│                                                                             │
│   ┌─────────────────────────────────────────────────────────────────────┐   │
│   │                    Downstream Effects                               │   │
│   │                                                                     │   │
│   │   1. AFFECTIVE_CONTEXT → Stored in SessionState (HOT tier)          │   │
│   │   2. AFFECTIVE_ROUTING → Fabric selects empathetic providers        │   │
│   │   3. EMOTIONAL_MIRRORING → Concierge adjusts response tone          │   │
│   │   4. COGNITIVE_LOAD_ROUTING → Reduces complexity for stressed user  │   │
│   │   5. EXPERIENCE_LAYER → Contributes to emotional trajectory         │   │
│   │                                                                     │   │
│   └─────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
│   Result: Emotional state propagated for empathetic response generation     │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

### F135: Constraint Progress Event Flow

**Trigger:** CONSTRAINT_MANAGER makes progress on constraint resolution
**Outcome:** k1.constraint.progress.v1 event triggers UI update

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                   F135: CONSTRAINT PROGRESS EVENT FLOW                      │
│                                                                             │
│   Event: k1.constraint.progress.v1                                          │
│   Purpose: Keep user informed of multi-step constraint resolution progress  │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│   ┌─────────────────────────────────────────────────────────────────────┐   │
│   │                    CONSTRAINT_MANAGER                               │   │
│   │                                                                     │   │
│   │   Constraint Resolution Progress:                                   │   │
│   │   ┌───────────────────────────────────────────────────────────────┐ │   │
│   │   │ constraint_set: "vacation_planning"                           │ │   │
│   │   │ total_constraints: 5                                          │ │   │
│   │   │ resolved: 3                                                   │ │   │
│   │   │ pending: 2                                                    │ │   │
│   │   │                                                               │ │   │
│   │   │ current_constraint: "budget_under_$2000"                      │ │   │
│   │   │ status: "EVALUATING"                                          │ │   │
│   │   │ iteration: 2 of 5 max                                         │ │   │
│   │   └───────────────────────────────────────────────────────────────┘ │   │
│   │                              │                                      │   │
│   │                              │ "k1.constraint.progress.v1"          │   │
│   │                              ▼                                      │   │
│   └─────────────────────────────────────────────────────────────────────┘   │
│                                  │                                          │
│                                  ▼                                          │
│   ┌─────────────────────────────────────────────────────────────────────┐   │
│   │                        EVENT_BUS                                    │   │
│   │                                                                     │   │
│   │   ┌───────────────────────────────────────────────────────────────┐ │   │
│   │   │              Event Structure                                  │ │   │
│   │   │                                                               │ │   │
│   │   │   {                                                           │ │   │
│   │   │     "topic": "k1.constraint.progress.v1",                     │ │   │
│   │   │     "timestamp": "2024-01-15T10:30:05.000Z",                  │ │   │
│   │   │     "trace_id": "cog_abc123",                                 │ │   │
│   │   │     "payload": {                                              │ │   │
│   │   │       "constraint_set_id": "cs_vacation_123",                 │ │   │
│   │   │       "progress": {                                           │ │   │
│   │   │         "total": 5,                                           │ │   │
│   │   │         "resolved": 3,                                        │ │   │
│   │   │         "pending": 2,                                         │ │   │
│   │   │         "percentage": 60                                      │ │   │
│   │   │       },                                                      │ │   │
│   │   │       "current": {                                            │ │   │
│   │   │         "constraint": "budget_under_$2000",                   │ │   │
│   │   │         "status": "EVALUATING",                               │ │   │
│   │   │         "iteration": 2                                        │ │   │
│   │   │       },                                                      │ │   │
│   │   │       "human_message": "Checking budget options... (3/5 done)"│ │   │
│   │   │     }                                                         │ │   │
│   │   │   }                                                           │ │   │
│   │   └───────────────────────────────────────────────────────────────┘ │   │
│   │                              │                                      │   │
│   │                              │ "Progress Updates"                   │   │
│   │                              ▼                                      │   │
│   └─────────────────────────────────────────────────────────────────────┘   │
│                                  │                                          │
│                                  ▼                                          │
│   ┌─────────────────────────────────────────────────────────────────────┐   │
│   │                    CONCIERGE_MAILBOX                                │   │
│   │                                                                     │   │
│   │   ┌───────────────────────────────────────────────────────────────┐ │   │
│   │   │              Progress Update Processing                       │ │   │
│   │   │                                                               │ │   │
│   │   │   1. Receive k1.constraint.progress.v1                        │ │   │
│   │   │   2. Route to CONCIERGE_FSM                                   │ │   │
│   │   │   3. Trigger PROGRESSING state if not already                 │ │   │
│   │   │   4. Generate user-friendly progress message                  │ │   │
│   │   └───────────────────────────────────────────────────────────────┘ │   │
│   │                              │                                      │   │
│   │                              ▼                                      │   │
│   │   ┌───────────────────────────────────────────────────────────────┐ │   │
│   │   │                    CONCIERGE_FSM                              │ │   │
│   │   │                                                               │ │   │
│   │   │   Current State: COMPANIONING or PROGRESSING                  │ │   │
│   │   │                                                               │ │   │
│   │   │   Action: Stream progress to user                             │ │   │
│   │   │   ┌─────────────────────────────────────────────────────────┐ │ │   │
│   │   │   │ "Making progress on your vacation plan...               │ │ │   │
│   │   │   │  [████████████░░░░░░░░] 60%                              │ │ │   │
│   │   │   │  Currently: Checking budget options"                    │ │ │   │
│   │   │   └─────────────────────────────────────────────────────────┘ │ │   │
│   │   └───────────────────────────────────────────────────────────────┘ │   │
│   │                                                                     │   │
│   └─────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
│   Result: User sees real-time progress on complex constraint resolution     │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

### F136: Priority-Based Event Bus Delivery Flow

**Trigger:** Event published to EVENT_BUS
**Outcome:** WFQ_SCHEDULER ensures priority-based delivery

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                F136: PRIORITY-BASED EVENT BUS DELIVERY FLOW                 │
│                                                                             │
│   Component: WFQ_SCHEDULER (Weighted Fair Queuing)                          │
│   Purpose: Ensure high-priority events processed before low-priority        │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│   ┌─────────────────────────────────────────────────────────────────────┐   │
│   │                    Incoming Events                                  │   │
│   │                                                                     │   │
│   │   Multiple events arriving simultaneously:                          │   │
│   │   ┌───────────────────────────────────────────────────────────────┐ │   │
│   │   │ Event A: k1.affect.analyzed.v1        (URGENT, weight=4)      │ │   │
│   │   │ Event B: k1.capability.completed.v1   (REALTIME, weight=3)    │ │   │
│   │   │ Event C: k1.fabric.learning.signal.v1 (BACKGROUND, weight=1)  │ │   │
│   │   │ Event D: k1.constraint.progress.v1    (INTERACTIVE, weight=2) │ │   │
│   │   └───────────────────────────────────────────────────────────────┘ │   │
│   │                              │                                      │   │
│   │                              │ all events                           │   │
│   │                              ▼                                      │   │
│   └─────────────────────────────────────────────────────────────────────┘   │
│                                  │                                          │
│                                  ▼                                          │
│   ┌─────────────────────────────────────────────────────────────────────┐   │
│   │                      WFQ_SCHEDULER                                  │   │
│   │       "URGENT=4, REALTIME=3, INTERACTIVE=2, BACKGROUND=1"           │   │
│   │                                                                     │   │
│   │   ┌───────────────────────────────────────────────────────────────┐ │   │
│   │   │              Priority Queues                                  │ │   │
│   │   │                                                               │ │   │
│   │   │   ┌─────────────────────────────────────────────────────────┐ │ │   │
│   │   │   │ URGENT (weight=4):                                      │ │ │   │
│   │   │   │   - Safety events                                       │ │ │   │
│   │   │   │   - Crisis detection                                    │ │ │   │
│   │   │   │   - Affect analysis (emotional state)                   │ │ │   │
│   │   │   │   → Processed 4x as often as BACKGROUND                 │ │ │   │
│   │   │   └─────────────────────────────────────────────────────────┘ │ │   │
│   │   │   ┌─────────────────────────────────────────────────────────┐ │ │   │
│   │   │   │ REALTIME (weight=3):                                    │ │ │   │
│   │   │   │   - Capability completions                              │ │ │   │
│   │   │   │   - User input events                                   │ │ │   │
│   │   │   │   - Concierge state transitions                         │ │ │   │
│   │   │   │   → Processed 3x as often as BACKGROUND                 │ │ │   │
│   │   │   └─────────────────────────────────────────────────────────┘ │ │   │
│   │   │   ┌─────────────────────────────────────────────────────────┐ │ │   │
│   │   │   │ INTERACTIVE (weight=2):                                 │ │ │   │
│   │   │   │   - Progress updates                                    │ │ │   │
│   │   │   │   - Planner events                                      │ │ │   │
│   │   │   │   - Sub-agent coordination                              │ │ │   │
│   │   │   │   → Processed 2x as often as BACKGROUND                 │ │ │   │
│   │   │   └─────────────────────────────────────────────────────────┘ │ │   │
│   │   │   ┌─────────────────────────────────────────────────────────┐ │ │   │
│   │   │   │ BACKGROUND (weight=1):                                  │ │ │   │
│   │   │   │   - Learning signals                                    │ │ │   │
│   │   │   │   - Metrics aggregation                                 │ │ │   │
│   │   │   │   - Memory consolidation                                │ │ │   │
│   │   │   │   → Baseline processing rate                            │ │ │   │
│   │   │   └─────────────────────────────────────────────────────────┘ │ │   │
│   │   └───────────────────────────────────────────────────────────────┘ │   │
│   │                              │                                      │   │
│   │   ┌───────────────────────────────────────────────────────────────┐ │   │
│   │   │              WFQ Algorithm                                    │ │   │
│   │   │                                                               │ │   │
│   │   │   Processing Order (weighted round-robin):                    │ │   │
│   │   │                                                               │ │   │
│   │   │   Round 1: [URGENT, URGENT, URGENT, URGENT,                   │ │   │
│   │   │            REALTIME, REALTIME, REALTIME,                      │ │   │
│   │   │            INTERACTIVE, INTERACTIVE,                          │ │   │
│   │   │            BACKGROUND]                                        │ │   │
│   │   │                                                               │ │   │
│   │   │   Actual Processing:                                          │ │   │
│   │   │   1. Event A (URGENT)     ← first                             │ │   │
│   │   │   2. Event B (REALTIME)                                       │ │   │
│   │   │   3. Event D (INTERACTIVE)                                    │ │   │
│   │   │   4. Event C (BACKGROUND) ← last                              │ │   │
│   │   │                                                               │ │   │
│   │   └───────────────────────────────────────────────────────────────┘ │   │
│   │                              │                                      │   │
│   │                              │ "Priority-based Delivery"            │   │
│   │                              ▼                                      │   │
│   └─────────────────────────────────────────────────────────────────────┘   │
│                                  │                                          │
│                                  ▼                                          │
│   ┌─────────────────────────────────────────────────────────────────────┐   │
│   │                        EVENT_BUS                                    │   │
│   │                                                                     │   │
│   │   Events delivered in priority order to subscribers                 │   │
│   │                                                                     │   │
│   │   Latency Targets (ADR-0028):                                       │   │
│   │   - URGENT: <5ms delivery                                           │   │
│   │   - REALTIME: <10ms delivery                                        │   │
│   │   - INTERACTIVE: <50ms delivery                                     │   │
│   │   - BACKGROUND: <500ms delivery (best effort)                       │   │
│   │                                                                     │   │
│   └─────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
│   Result: Critical events processed first, background tasks don't starve    │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

### F137: Priority-Based Mailbox Router Flow

**Trigger:** Event needs delivery to specific actor mailbox
**Outcome:** MAILBOX_ROUTER delivers with priority ordering

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                F137: PRIORITY-BASED MAILBOX ROUTER FLOW                     │
│                                                                             │
│   Component: MAILBOX_ROUTER + WFQ_SCHEDULER                                 │
│   Purpose: Route events to actor mailboxes with priority preservation       │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│   ┌─────────────────────────────────────────────────────────────────────┐   │
│   │                      WFQ_SCHEDULER                                  │   │
│   │                                                                     │   │
│   │   Prioritized events ready for mailbox delivery:                    │   │
│   │   ┌───────────────────────────────────────────────────────────────┐ │   │
│   │   │ 1. k1.affect.analyzed.v1 → CONCIERGE_MAILBOX (URGENT)         │ │   │
│   │   │ 2. k1.capability.completed.v1 → CONCIERGE_MAILBOX (REALTIME)  │ │   │
│   │   │ 3. k1.constraint.progress.v1 → CONCIERGE_MAILBOX (INTERACTIVE)│ │   │
│   │   │ 4. k1.fabric.learning.signal.v1 → LEARNING_MAILBOX (BACKGROUND)│ │   │
│   │   └───────────────────────────────────────────────────────────────┘ │   │
│   │                              │                                      │   │
│   │                              │ "Priority-based Delivery"            │   │
│   │                              ▼                                      │   │
│   └─────────────────────────────────────────────────────────────────────┘   │
│                                  │                                          │
│                                  ▼                                          │
│   ┌─────────────────────────────────────────────────────────────────────┐   │
│   │                      MAILBOX_ROUTER                                 │   │
│   │               "Direct Mailbox Router (Actor ID → Mailbox)"          │   │
│   │                                                                     │   │
│   │   ┌───────────────────────────────────────────────────────────────┐ │   │
│   │   │              Mailbox Registry                                 │ │   │
│   │   │                                                               │ │   │
│   │   │   Actor Mailboxes (MPSC Queues):                              │ │   │
│   │   │   ┌─────────────────────────────────────────────────────────┐ │ │   │
│   │   │   │ CONCIERGE_MAILBOX:                                      │ │ │   │
│   │   │   │   actor_id: "concierge_main"                            │ │ │   │
│   │   │   │   priority: REALTIME                                    │ │ │   │
│   │   │   │   queue_depth: 100                                      │ │ │   │
│   │   │   │   subscriptions: [k1.capability.*, k1.affect.*, ...]    │ │ │   │
│   │   │   │                                                         │ │ │   │
│   │   │   │ ORCHESTRATOR_MAILBOX:                                   │ │ │   │
│   │   │   │   actor_id: "orchestrator_main"                         │ │ │   │
│   │   │   │   priority: REALTIME                                    │ │ │   │
│   │   │   │   queue_depth: 50                                       │ │ │   │
│   │   │   │                                                         │ │ │   │
│   │   │   │ PLANNER_MAILBOX:                                        │ │ │   │
│   │   │   │   actor_id: "planner_main"                              │ │ │   │
│   │   │   │   priority: INTERACTIVE                                 │ │ │   │
│   │   │   │   queue_depth: 20                                       │ │ │   │
│   │   │   │                                                         │ │ │   │
│   │   │   │ FABRIC_MAILBOX:                                         │ │ │   │
│   │   │   │   actor_id: "fabric_main"                               │ │ │   │
│   │   │   │   priority: REALTIME                                    │ │ │   │
│   │   │   │   queue_depth: 200                                      │ │ │   │
│   │   │   │                                                         │ │ │   │
│   │   │   │ CUSTOM_MAILBOXES[]:                                     │ │ │   │
│   │   │   │   Dynamic agent mailboxes (spawned on demand)           │ │ │   │
│   │   │   └─────────────────────────────────────────────────────────┘ │ │   │
│   │   └───────────────────────────────────────────────────────────────┘ │   │
│   │                              │                                      │   │
│   │   ┌───────────────────────────────────────────────────────────────┐ │   │
│   │   │              Routing Logic                                    │ │   │
│   │   │                                                               │ │   │
│   │   │   route(event):                                               │ │   │
│   │   │   ┌─────────────────────────────────────────────────────────┐ │ │   │
│   │   │   │ 1. Lookup subscribers for event.topic                   │ │ │   │
│   │   │   │                                                         │ │ │   │
│   │   │   │ 2. For each subscriber:                                 │ │ │   │
│   │   │   │    a. Get mailbox by actor_id                           │ │ │   │
│   │   │   │    b. Check mailbox capacity (queue_depth)              │ │ │   │
│   │   │   │    c. If full: apply backpressure strategy              │ │ │   │
│   │   │   │       - URGENT: always accept (bump oldest BACKGROUND)  │ │ │   │
│   │   │   │       - REALTIME: accept, warn if near full             │ │ │   │
│   │   │   │       - INTERACTIVE: drop if full, log warning          │ │ │   │
│   │   │   │       - BACKGROUND: drop silently if full               │ │ │   │
│   │   │   │                                                         │ │ │   │
│   │   │   │ 3. Enqueue with priority ordering within mailbox        │ │ │   │
│   │   │   └─────────────────────────────────────────────────────────┘ │ │   │
│   │   └───────────────────────────────────────────────────────────────┘ │   │
│   │                              │                                      │   │
│   └──────────────────────────────┼──────────────────────────────────────┘   │
│                                  │                                          │
│         ┌────────────────────────┼────────────────────────────────────┐     │
│         │                        │                        │           │     │
│         ▼                        ▼                        ▼           ▼     │
│   ┌───────────┐           ┌───────────┐           ┌───────────┐ ┌─────────┐ │
│   │CONCIERGE_ │           │ORCHESTRATOR│          │PLANNER_   │ │FABRIC_  │ │
│   │ MAILBOX   │           │ _MAILBOX  │           │ MAILBOX   │ │MAILBOX  │ │
│   │           │           │           │           │           │ │         │ │
│   │ Priority  │           │ Priority  │           │ Priority  │ │Priority │ │
│   │ Queue:    │           │ Queue:    │           │ Queue:    │ │Queue:   │ │
│   │ ┌───────┐ │           │ ┌───────┐ │           │ ┌───────┐ │ │┌───────┐│ │
│   │ │URGENT │ │           │ │URGENT │ │           │ │URGENT │ │ ││URGENT ││ │
│   │ │───────│ │           │ │───────│ │           │ │───────│ │ ││───────││ │
│   │ │REALTIME│ │           │ │REALTIME│ │           │ │REALTIME│ │ ││REALTIME││ │
│   │ │───────│ │           │ │───────│ │           │ │───────│ │ ││───────││ │
│   │ │INTER. │ │           │ │INTER. │ │           │ │INTER. │ │ ││INTER. ││ │
│   │ │───────│ │           │ │───────│ │           │ │───────│ │ ││───────││ │
│   │ │BACKGND│ │           │ │BACKGND│ │           │ │BACKGND│ │ ││BACKGND││ │
│   │ └───────┘ │           │ └───────┘ │           │ └───────┘ │ │└───────┘│ │
│   └───────────┘           └───────────┘           └───────────┘ └─────────┘ │
│                                                                             │
│   Result: Events delivered to correct mailboxes with priority preservation  │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## 16. HIL FEEDBACK FLOWS

### 16.1 User Loop Flows

- [x] **F138: Concierge ↔ User Bidirectional Flow**
- [x] **F139: Planner ↔ User Bidirectional Flow**
- [x] **F140: Sub-Agents ↔ User Bidirectional Flow**
- [x] **F141: Orchestrator ↔ User Bidirectional Flow**

---

### F138: Concierge ↔ User Bidirectional Flow

**Trigger:** User sends message OR Concierge needs clarification
**Outcome:** Conversational feedback loop for natural dialog

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                 F138: CONCIERGE ↔ USER BIDIRECTIONAL FLOW                   │
│                                                                             │
│   Component: CONCIERGE_USER_LOOP                                            │
│   Purpose: Conversational feedback for natural, empathetic dialog           │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│   ┌─────────────────────────────────────────────────────────────────────┐   │
│   │                         USER                                        │   │
│   │                                                                     │   │
│   │   User Actions:                                                     │   │
│   │   - Send message                                                    │   │
│   │   - Provide correction ("No, I meant...")                           │   │
│   │   - Give feedback ("That's not what I wanted")                      │   │
│   │   - Request clarification ("What do you mean by...")                │   │
│   │   - Express preference ("I prefer the first option")                │   │
│   │                              │                                      │   │
│   │                              ▼                                      │   │
│   └─────────────────────────────────────────────────────────────────────┘   │
│                                  │                                          │
│                                  │ user input                               │
│                                  ▼                                          │
│   ┌─────────────────────────────────────────────────────────────────────┐   │
│   │                   CONCIERGE_USER_LOOP                               │   │
│   │           "Concierge ↔ User Conversational Feedback"                │   │
│   │                                                                     │   │
│   │   ┌───────────────────────────────────────────────────────────────┐ │   │
│   │   │              Feedback Classification                          │ │   │
│   │   │                                                               │ │   │
│   │   │   Input Analysis:                                             │ │   │
│   │   │   ┌─────────────────────────────────────────────────────────┐ │ │   │
│   │   │   │ 1. NEW_TOPIC: User starts fresh conversation            │ │ │   │
│   │   │   │    → Route to CONCIERGE_FSM LISTENING state             │ │ │   │
│   │   │   │                                                         │ │ │   │
│   │   │   │ 2. CORRECTION: User corrects misunderstanding           │ │ │   │
│   │   │   │    → Update BELIEFS_ACTIVE, re-process                  │ │ │   │
│   │   │   │                                                         │ │ │   │
│   │   │   │ 3. FEEDBACK: Positive/negative on response              │ │ │   │
│   │   │   │    → Signal to LEARNING_LOOP, adjust approach           │ │ │   │
│   │   │   │                                                         │ │ │   │
│   │   │   │ 4. CLARIFICATION_REQUEST: User needs explanation        │ │ │   │
│   │   │   │    → Generate explanation, defer current task           │ │ │   │
│   │   │   │                                                         │ │ │   │
│   │   │   │ 5. CLARIFICATION_RESPONSE: User answers our question    │ │ │   │
│   │   │   │    → Update CLARIFICATIONS, resume task                 │ │ │   │
│   │   │   │                                                         │ │ │   │
│   │   │   │ 6. PREFERENCE: User expresses choice                    │ │ │   │
│   │   │   │    → Update PERSONA hints, store preference             │ │ │   │
│   │   │   └─────────────────────────────────────────────────────────┘ │ │   │
│   │   └───────────────────────────────────────────────────────────────┘ │   │
│   │                              │                                      │   │
│   │                              │ "Bidirectional Flow"                 │   │
│   │                              ▼                                      │   │
│   └─────────────────────────────────────────────────────────────────────┘   │
│                                  │                                          │
│                                  ▼                                          │
│   ┌─────────────────────────────────────────────────────────────────────┐   │
│   │                       CONCIERGE_FSM                                 │   │
│   │                                                                     │   │
│   │   ┌───────────────────────────────────────────────────────────────┐ │   │
│   │   │              Feedback Processing                              │ │   │
│   │   │                                                               │ │   │
│   │   │   CORRECTION Handling:                                        │ │   │
│   │   │   ┌─────────────────────────────────────────────────────────┐ │ │   │
│   │   │   │ 1. Acknowledge: "I understand, you meant..."            │ │ │   │
│   │   │   │ 2. Update BELIEFS_ACTIVE with correction                │ │ │   │
│   │   │   │ 3. Invalidate affected TOOL_RESULT_BUFFER entries       │ │ │   │
│   │   │   │ 4. Re-enter PLANNING if plan was based on old belief    │ │ │   │
│   │   │   │ 5. Generate corrected response                          │ │ │   │
│   │   │   └─────────────────────────────────────────────────────────┘ │ │   │
│   │   │                                                               │ │   │
│   │   │   CLARIFICATION_REQUEST Handling:                             │ │   │
│   │   │   ┌─────────────────────────────────────────────────────────┐ │ │   │
│   │   │   │ 1. Detect gap in understanding                          │ │ │   │
│   │   │   │ 2. Add to CLARIFICATIONS (4KB) in SessionState          │ │ │   │
│   │   │   │ 3. Generate clarifying question                         │ │ │   │
│   │   │   │ 4. Enter COMPANIONING with clarification mode           │ │ │   │
│   │   │   │ 5. Wait for user response                               │ │   │
│   │   │   └─────────────────────────────────────────────────────────┘ │ │   │
│   │   └───────────────────────────────────────────────────────────────┘ │   │
│   │                              │                                      │   │
│   │                              ▼                                      │   │
│   │   ┌───────────────────────────────────────────────────────────────┐ │   │
│   │   │              Response Generation                              │ │   │
│   │   │                                                               │ │   │
│   │   │   Concierge → User:                                           │ │   │
│   │   │   - Acknowledgment of feedback                                │ │   │
│   │   │   - Clarifying questions when needed                          │ │   │
│   │   │   - Progress updates during execution                         │ │   │
│   │   │   - Emotionally-attuned responses (via AFFECTIVE_CONTEXT)     │ │   │
│   │   │   - Option presentations when multiple paths exist            │ │   │
│   │   └───────────────────────────────────────────────────────────────┘ │   │
│   └─────────────────────────────────────────────────────────────────────┘   │
│                                  │                                          │
│                                  │ all feedback through                     │
│                                  ▼                                          │
│   ┌─────────────────────────────────────────────────────────────────────┐   │
│   │                      FEEDBACK_ROUTING                               │   │
│   │            "All Feedback through Event Bus"                         │   │
│   │                                                                     │   │
│   │   Events emitted:                                                   │   │
│   │   - k1.hil.correction.received.v1                                   │   │
│   │   - k1.hil.clarification.requested.v1                               │   │
│   │   - k1.hil.preference.captured.v1                                   │   │
│   │   - k1.hil.feedback.positive.v1 / k1.hil.feedback.negative.v1       │   │
│   │                              │                                      │   │
│   │                              ▼                                      │   │
│   │                          EVENT_BUS                                  │   │
│   └─────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
│   Result: Seamless conversational loop with correction and clarification    │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

### F139: Planner ↔ User Bidirectional Flow

**Trigger:** PLANNER_AGENT needs requirement clarification or plan approval
**Outcome:** User provides missing requirements or approves/modifies plan

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                  F139: PLANNER ↔ USER BIDIRECTIONAL FLOW                    │
│                                                                             │
│   Component: PLANNER_USER_LOOP + PLANNER_HIL                                │
│   Purpose: Requirement clarification and plan approval                      │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│   ┌─────────────────────────────────────────────────────────────────────┐   │
│   │                       PLANNER_AGENT                                 │   │
│   │                                                                     │   │
│   │   Planning encounters uncertainty:                                  │   │
│   │   ┌───────────────────────────────────────────────────────────────┐ │   │
│   │   │ Task: "Book a vacation"                                       │ │   │
│   │   │                                                               │ │   │
│   │   │ Missing Information:                                          │ │   │
│   │   │ - Destination?                                                │ │   │
│   │   │ - Budget range?                                               │ │   │
│   │   │ - Travel dates?                                               │ │   │
│   │   │ - Number of travelers?                                        │ │   │
│   │   └───────────────────────────────────────────────────────────────┘ │   │
│   │                              │                                      │   │
│   │                              │ need clarification                   │   │
│   │                              ▼                                      │   │
│   └─────────────────────────────────────────────────────────────────────┘   │
│                                  │                                          │
│                                  ▼                                          │
│   ┌─────────────────────────────────────────────────────────────────────┐   │
│   │                      PLANNER_HIL                                    │   │
│   │                  "Human-in-the-Loop"                                │   │
│   │                                                                     │   │
│   │   ┌───────────────────────────────────────────────────────────────┐ │   │
│   │   │              REQUIREMENT_CLARIFICATION                        │ │   │
│   │   │                                                               │ │   │
│   │   │   When triggered:                                             │ │   │
│   │   │   - Essential parameter missing for plan generation           │ │   │
│   │   │   - Ambiguous user intent detected                            │ │   │
│   │   │   - Multiple valid interpretations possible                   │ │   │
│   │   │                                                               │ │   │
│   │   │   Question Generation:                                        │ │   │
│   │   │   ┌─────────────────────────────────────────────────────────┐ │ │   │
│   │   │   │ Prioritize by:                                          │ │ │   │
│   │   │   │ 1. Impact on plan structure                             │ │ │   │
│   │   │   │ 2. Cannot be inferred from context                      │ │ │   │
│   │   │   │ 3. User likely has strong preference                    │ │ │   │
│   │   │   │                                                         │ │ │   │
│   │   │   │ Generated: "Where would you like to go, and what's      │ │ │   │
│   │   │   │            your approximate budget?"                    │ │ │   │
│   │   │   └─────────────────────────────────────────────────────────┘ │ │   │
│   │   └───────────────────────────────────────────────────────────────┘ │   │
│   │                              │                                      │   │
│   │   ┌───────────────────────────────────────────────────────────────┐ │   │
│   │   │              PLAN_APPROVAL                                    │ │   │
│   │   │                                                               │ │   │
│   │   │   When triggered:                                             │ │   │
│   │   │   - Complex multi-step plan generated                         │ │   │
│   │   │   - High-impact actions (financial, irreversible)             │ │   │
│   │   │   - User preference for explicit approval                     │ │   │
│   │   │                                                               │ │   │
│   │   │   Approval Request:                                           │ │   │
│   │   │   ┌─────────────────────────────────────────────────────────┐ │ │   │
│   │   │   │ "Here's my plan for your Hawaii vacation:               │ │ │   │
│   │   │   │                                                         │ │ │   │
│   │   │   │  1. Search flights (AA, United) for dates               │ │ │   │
│   │   │   │  2. Find hotels in Maui within budget                   │ │ │   │
│   │   │   │  3. Check car rental availability                       │ │ │   │
│   │   │   │  4. Look up activities (snorkeling, hiking)             │ │ │   │
│   │   │   │                                                         │ │ │   │
│   │   │   │ Should I proceed, or would you like to modify this?"    │ │ │   │
│   │   │   └─────────────────────────────────────────────────────────┘ │ │   │
│   │   └───────────────────────────────────────────────────────────────┘ │   │
│   │                              │                                      │   │
│   │   ┌───────────────────────────────────────────────────────────────┐ │   │
│   │   │              EXECUTION_MONITORING                             │ │   │
│   │   │                                                               │ │   │
│   │   │   During plan execution:                                      │ │   │
│   │   │   - Progress updates via CONSTRAINT_PROGRESS events           │ │   │
│   │   │   - User can pause ("Wait, hold on")                          │ │   │
│   │   │   - User can modify ("Actually, skip the car rental")         │ │   │
│   │   │   - User can abort ("Cancel all this")                        │ │   │
│   │   └───────────────────────────────────────────────────────────────┘ │   │
│   │                              │                                      │   │
│   │                              │ "Bidirectional Flow"                 │   │
│   │                              ▼                                      │   │
│   └─────────────────────────────────────────────────────────────────────┘   │
│                                  │                                          │
│                                  ▼                                          │
│   ┌─────────────────────────────────────────────────────────────────────┐   │
│   │                    PLANNER_USER_LOOP                                │   │
│   │           "Planner ↔ User Requirement Clarification"                │   │
│   │                                                                     │   │
│   │   ┌───────────────────────────────────────────────────────────────┐ │   │
│   │   │              Loop States                                      │ │   │
│   │   │                                                               │ │   │
│   │   │   AWAITING_REQUIREMENTS:                                      │ │   │
│   │   │   → Asked clarifying question                                 │ │   │
│   │   │   → Waiting for user response                                 │ │   │
│   │   │   → Timeout: 5 minutes, then gentle reminder                  │ │   │
│   │   │                                                               │ │   │
│   │   │   AWAITING_APPROVAL:                                          │ │   │
│   │   │   → Presented plan for approval                               │ │   │
│   │   │   → Options: approve / modify / cancel                        │ │   │
│   │   │   → Default: proceed after user confirmation                  │ │   │
│   │   │                                                               │ │   │
│   │   │   EXECUTING_WITH_MONITORING:                                  │ │   │
│   │   │   → Plan executing                                            │ │   │
│   │   │   → User can intervene at any point                           │ │   │
│   │   │   → Progress updates via CONCIERGE_FSM                        │ │   │
│   │   └───────────────────────────────────────────────────────────────┘ │   │
│   │                                                                     │   │
│   └─────────────────────────────────────────────────────────────────────┘   │
│                                  │                                          │
│                       ┌──────────┴──────────┐                               │
│                       ▼                     ▼                               │
│   ┌─────────────────────────┐   ┌─────────────────────────┐                 │
│   │   User Response:        │   │   User Response:        │                 │
│   │   CLARIFICATION         │   │   APPROVAL              │                 │
│   │                         │   │                         │                 │
│   │   "Hawaii, around       │   │   "Yes, go ahead" or    │                 │
│   │    $3000 for 2 people"  │   │   "Skip step 3"         │                 │
│   │           │             │   │           │             │                 │
│   │           ▼             │   │           ▼             │                 │
│   │   Update BELIEFS_ACTIVE │   │   Update DAG_ENGINE     │                 │
│   │   Resume planning       │   │   Execute/modify plan   │                 │
│   └─────────────────────────┘   └─────────────────────────┘                 │
│                                                                             │
│   Result: Plans built collaboratively with user input and approval          │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

### F140: Sub-Agents ↔ User Bidirectional Flow

**Trigger:** Sub-agent needs domain-specific clarification or progress update
**Outcome:** User provides input, sub-agent continues or adjusts

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                 F140: SUB-AGENTS ↔ USER BIDIRECTIONAL FLOW                  │
│                                                                             │
│   Component: SUBAGENTS_USER_LOOP                                            │
│   Purpose: Progress updates and domain-specific clarifications              │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│   ┌─────────────────────────────────────────────────────────────────────┐   │
│   │                    L4_SUBAGENTS (Dynamic Instances)                 │   │
│   │                                                                     │   │
│   │   Active Sub-Agents:                                                │   │
│   │   ┌───────────────────────────────────────────────────────────────┐ │   │
│   │   │                                                               │ │   │
│   │   │ health_agent_abc123:                                          │ │   │
│   │   │   Task: "Log today's meals"                                   │ │   │
│   │   │   Status: ACTIVE                                              │ │   │
│   │   │   Needs: Meal details from user                               │ │   │
│   │   │                                                               │ │   │
│   │   │ finance_agent_xyz789:                                         │ │   │
│   │   │   Task: "Analyze spending patterns"                           │ │   │
│   │   │   Status: ACTIVE                                              │ │   │
│   │   │   Progress: 60% complete                                      │ │   │
│   │   │                                                               │ │   │
│   │   └───────────────────────────────────────────────────────────────┘ │   │
│   │                              │                                      │   │
│   │                              │ needs user input                     │   │
│   │                              ▼                                      │   │
│   └─────────────────────────────────────────────────────────────────────┘   │
│                                  │                                          │
│                                  ▼                                          │
│   ┌─────────────────────────────────────────────────────────────────────┐   │
│   │                    SUBAGENTS_USER_LOOP                              │   │
│   │             "Sub-Agents ↔ User Progress Updates"                    │   │
│   │                                                                     │   │
│   │   ┌───────────────────────────────────────────────────────────────┐ │   │
│   │   │              HIL Request Types                                │ │   │
│   │   │                                                               │ │   │
│   │   │   1. DOMAIN_CLARIFICATION:                                    │ │   │
│   │   │   ┌─────────────────────────────────────────────────────────┐ │ │   │
│   │   │   │ health_agent: "What did you have for lunch today?       │ │ │   │
│   │   │   │  I see you logged breakfast as oatmeal."                │ │ │   │
│   │   │   │                                                         │ │ │   │
│   │   │   │ → Stored in PENDING_CLARIFICATIONS (2KB)                │ │ │   │
│   │   │   │ → Sub-agent HIL requests tracked per session            │ │ │   │
│   │   │   └─────────────────────────────────────────────────────────┘ │ │   │
│   │   │                                                               │ │   │
│   │   │   2. PROGRESS_UPDATE:                                         │ │   │
│   │   │   ┌─────────────────────────────────────────────────────────┐ │ │   │
│   │   │   │ finance_agent: "I've analyzed 3 months of spending.     │ │ │   │
│   │   │   │  Working on categorization now... (60%)"                │ │ │   │
│   │   │   │                                                         │ │ │   │
│   │   │   │ → Routed through CONCIERGE_FSM PROGRESSING state        │ │ │   │
│   │   │   │ → User sees progress, can intervene if needed           │ │ │   │
│   │   │   └─────────────────────────────────────────────────────────┘ │ │   │
│   │   │                                                               │ │   │
│   │   │   3. PREFERENCE_QUERY:                                        │ │   │
│   │   │   ┌─────────────────────────────────────────────────────────┐ │ │   │
│   │   │   │ health_agent: "I found two workout plans matching your  │ │ │   │
│   │   │   │  goals. Do you prefer morning or evening sessions?"     │ │ │   │
│   │   │   │                                                         │ │ │   │
│   │   │   │ → Options presented to user                             │ │ │   │
│   │   │   │ → Choice stored in PERSONA hints for future             │ │ │   │
│   │   │   └─────────────────────────────────────────────────────────┘ │ │   │
│   │   │                                                               │ │   │
│   │   │   4. ERROR_RECOVERY:                                          │ │   │
│   │   │   ┌─────────────────────────────────────────────────────────┐ │ │   │
│   │   │   │ finance_agent: "I couldn't connect to your bank.        │ │ │   │
│   │   │   │  Would you like to try again or use manual entry?"      │ │ │   │
│   │   │   │                                                         │ │ │   │
│   │   │   │ → SAGA_RECOVERY pattern for compensating actions        │ │ │   │
│   │   │   │ → User chooses recovery path                            │ │ │   │
│   │   │   └─────────────────────────────────────────────────────────┘ │ │   │
│   │   └───────────────────────────────────────────────────────────────┘ │   │
│   │                              │                                      │   │
│   │                              │ "Bidirectional Flow"                 │   │
│   │                              ▼                                      │   │
│   └─────────────────────────────────────────────────────────────────────┘   │
│                                  │                                          │
│                                  ▼                                          │
│   ┌─────────────────────────────────────────────────────────────────────┐   │
│   │                      Message Flow                                   │   │
│   │                                                                     │   │
│   │   Sub-Agent → User:                                                 │   │
│   │   ┌───────────────────────────────────────────────────────────────┐ │   │
│   │   │ SUB_AGENT_MAILBOX → CONCIERGE_MAILBOX → CONCIERGE_FSM → User  │ │   │
│   │   │                                                               │ │   │
│   │   │ Sub-agent messages always mediated by Concierge:              │ │   │
│   │   │ - Concierge adds empathetic framing                           │ │   │
│   │   │ - Concierge may batch multiple sub-agent messages             │ │   │
│   │   │ - Concierge ensures consistent voice                          │ │   │
│   │   └───────────────────────────────────────────────────────────────┘ │   │
│   │                                                                     │   │
│   │   User → Sub-Agent:                                                 │   │
│   │   ┌───────────────────────────────────────────────────────────────┐ │   │
│   │   │ User → CONCIERGE_FSM → ORCHESTRATOR → SUB_AGENT_MAILBOX       │ │   │
│   │   │                                                               │ │   │
│   │   │ User responses routed to correct sub-agent:                   │ │   │
│   │   │ - Orchestrator tracks which agent is awaiting response        │ │   │
│   │   │ - Response matched to PENDING_CLARIFICATIONS entry            │ │   │
│   │   │ - Sub-agent resumes execution with new information            │ │   │
│   │   └───────────────────────────────────────────────────────────────┘ │   │
│   └─────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
│   Result: Sub-agents can request user input without breaking conversation   │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

### F141: Orchestrator ↔ User Bidirectional Flow

**Trigger:** ORCHESTRATOR needs resource allocation decision or intervention
**Outcome:** User provides guidance on priorities or resource allocation

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                F141: ORCHESTRATOR ↔ USER BIDIRECTIONAL FLOW                 │
│                                                                             │
│   Component: ORCHESTRATOR_USER_LOOP                                         │
│   Purpose: Resource allocation decisions and priority interventions         │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│   ┌─────────────────────────────────────────────────────────────────────┐   │
│   │                    ORCHESTRATOR_ACTOR                               │   │
│   │                                                                     │   │
│   │   Resource Conflict Detected:                                       │   │
│   │   ┌───────────────────────────────────────────────────────────────┐ │   │
│   │   │ Scenario: Multiple high-priority tasks competing              │ │   │
│   │   │                                                               │ │   │
│   │   │ Task A: "Book vacation flights" (User Priority: HIGH)         │ │   │
│   │   │   - Requires: LLM tokens, travel API                          │ │   │
│   │   │   - Estimated: 30 seconds                                     │ │   │
│   │   │                                                               │ │   │
│   │   │ Task B: "Analyze spending report" (User Priority: HIGH)       │ │   │
│   │   │   - Requires: LLM tokens, bank API                            │ │   │
│   │   │   - Estimated: 2 minutes                                      │ │   │
│   │   │                                                               │ │   │
│   │   │ Constraint: Cannot run both simultaneously (token budget)     │ │   │
│   │   └───────────────────────────────────────────────────────────────┘ │   │
│   │                              │                                      │   │
│   │                              │ needs user prioritization            │   │
│   │                              ▼                                      │   │
│   └─────────────────────────────────────────────────────────────────────┘   │
│                                  │                                          │
│                                  ▼                                          │
│   ┌─────────────────────────────────────────────────────────────────────┐   │
│   │                   ORCHESTRATOR_USER_LOOP                            │   │
│   │            "Orchestrator ↔ User Resource Allocation"                │   │
│   │                                                                     │   │
│   │   ┌───────────────────────────────────────────────────────────────┐ │   │
│   │   │              Intervention Types                               │ │   │
│   │   │                                                               │ │   │
│   │   │   1. PRIORITY_CONFLICT:                                       │ │   │
│   │   │   ┌─────────────────────────────────────────────────────────┐ │ │   │
│   │   │   │ "I have two tasks ready. Which should I do first:       │ │ │   │
│   │   │   │  A) Book your vacation flights (quick, ~30s)            │ │ │   │
│   │   │   │  B) Analyze spending report (detailed, ~2min)           │ │ │   │
│   │   │   │                                                         │ │ │   │
│   │   │   │ Or I can do A first, then B in background?"             │ │ │   │
│   │   │   └─────────────────────────────────────────────────────────┘ │ │   │
│   │   │                                                               │ │   │
│   │   │   2. RESOURCE_EXHAUSTION:                                     │ │   │
│   │   │   ┌─────────────────────────────────────────────────────────┐ │ │   │
│   │   │   │ "I'm running low on API quota for this session.         │ │ │   │
│   │   │   │  Would you like me to:                                  │ │ │   │
│   │   │   │  A) Continue with reduced quality (faster model)        │ │ │   │
│   │   │   │  B) Pause non-critical tasks                            │ │ │   │
│   │   │   │  C) Complete current task and stop?"                    │ │ │   │
│   │   │   └─────────────────────────────────────────────────────────┘ │ │   │
│   │   │                                                               │ │   │
│   │   │   3. LONG_RUNNING_TASK:                                       │ │   │
│   │   │   ┌─────────────────────────────────────────────────────────┐ │ │   │
│   │   │   │ "The spending analysis is taking longer than expected.  │ │ │   │
│   │   │   │  (Currently 3 minutes, estimated 2 more)                │ │ │   │
│   │   │   │                                                         │ │ │   │
│   │   │   │  Should I:                                              │ │ │   │
│   │   │   │  A) Keep going                                          │ │ │   │
│   │   │   │  B) Stop and show partial results                       │ │ │   │
│   │   │   │  C) Run in background, notify when done?"               │ │ │   │
│   │   │   └─────────────────────────────────────────────────────────┘ │ │   │
│   │   │                                                               │ │   │
│   │   │   4. FALLBACK_TRIGGER (from CONSTRAINT_RESOLUTION_ENGINE):    │ │   │
│   │   │   ┌─────────────────────────────────────────────────────────┐ │ │   │
│   │   │   │ "I've tried 3 times to find flights under your budget   │ │ │   │
│   │   │   │  but all options are over by $200.                      │ │ │   │
│   │   │   │                                                         │ │ │   │
│   │   │   │  Would you like to:                                     │ │ │   │
│   │   │   │  A) Increase budget to $2200                            │ │ │   │
│   │   │   │  B) Try different dates                                 │ │ │   │
│   │   │   │  C) Try alternative destinations?"                      │ │ │   │
│   │   │   └─────────────────────────────────────────────────────────┘ │ │   │
│   │   └───────────────────────────────────────────────────────────────┘ │   │
│   │                              │                                      │   │
│   │                              │ "Bidirectional Flow"                 │   │
│   │                              ▼                                      │   │
│   └─────────────────────────────────────────────────────────────────────┘   │
│                                  │                                          │
│                                  ▼                                          │
│   ┌─────────────────────────────────────────────────────────────────────┐   │
│   │                    User Decision Processing                         │   │
│   │                                                                     │   │
│   │   ┌───────────────────────────────────────────────────────────────┐ │   │
│   │   │              Decision Flow                                    │ │   │
│   │   │                                                               │ │   │
│   │   │   User: "Do the flights first"                                │ │   │
│   │   │            │                                                  │ │   │
│   │   │            ▼                                                  │ │   │
│   │   │   CONCIERGE_FSM classifies as ORCHESTRATOR_DECISION           │ │   │
│   │   │            │                                                  │ │   │
│   │   │            ▼                                                  │ │   │
│   │   │   ORCHESTRATOR_ACTOR receives priority update                 │ │   │
│   │   │            │                                                  │ │   │
│   │   │            ▼                                                  │ │   │
│   │   │   ┌─────────────────────────────────────────────────────────┐ │ │   │
│   │   │   │ Update DAG_ENGINE execution order:                      │ │ │   │
│   │   │   │ - Task A priority: URGENT                               │ │ │   │
│   │   │   │ - Task B priority: INTERACTIVE (deferred)               │ │ │   │
│   │   │   │                                                         │ │ │   │
│   │   │   │ Resume execution with new priorities                    │ │ │   │
│   │   │   └─────────────────────────────────────────────────────────┘ │ │   │
│   │   └───────────────────────────────────────────────────────────────┘ │   │
│   │                                                                     │   │
│   │   Events emitted via FEEDBACK_ROUTING → EVENT_BUS:                  │   │
│   │   - k1.orchestrator.priority.updated.v1                             │   │
│   │   - k1.orchestrator.resource.allocated.v1                           │   │
│   │   - k1.orchestrator.task.deferred.v1                                │   │
│   │                                                                     │   │
│   └─────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
│   Result: User controls resource allocation for competing priorities        │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## 17. OBSERVABILITY FLOWS

### 17.1 Tracing & Metrics Flow

- [x] **F142: Distributed Tracing → Cognitive Trace ID Flow**
- [x] **F143: Metrics Aggregator → SessionState Flow**
- [x] **F144: Health Check Orchestrator Flow**

---

### F142: Distributed Tracing → Cognitive Trace ID Flow

**Trigger:** Any K1 component performs an action
**Outcome:** Action recorded with cognitive trace ID for end-to-end causality

```
┌─────────────────────────────────────────────────────────────────────────────┐
│              F142: DISTRIBUTED TRACING → COGNITIVE TRACE ID FLOW            │
│                                                                             │
│   Component: DISTRIBUTED_TRACING + COGNITIVE_TRACE_ID                       │
│   Purpose: Unified causality tracking across all K1 components              │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│   ┌─────────────────────────────────────────────────────────────────────┐   │
│   │                    User Message Arrives                             │   │
│   │                                                                     │   │
│   │   Input: "Book a flight to Hawaii next week"                        │   │
│   │                              │                                      │   │
│   │                              │ generate trace ID                    │   │
│   │                              ▼                                      │   │
│   └─────────────────────────────────────────────────────────────────────┘   │
│                                  │                                          │
│                                  ▼                                          │
│   ┌─────────────────────────────────────────────────────────────────────┐   │
│   │                    COGNITIVE_TRACE_ID                               │   │
│   │               "Unifies Causality"                                   │   │
│   │                                                                     │   │
│   │   ┌───────────────────────────────────────────────────────────────┐ │   │
│   │   │              Trace ID Structure                               │ │   │
│   │   │                                                               │ │   │
│   │   │   Format: cog_{session}_{turn}_{timestamp}                    │ │   │
│   │   │   Example: cog_abc123_42_1705312200123                        │ │   │
│   │   │                                                               │ │   │
│   │   │   Components:                                                 │ │   │
│   │   │   - session: User session identifier                          │ │   │
│   │   │   - turn: Conversation turn number                            │ │   │
│   │   │   - timestamp: Microsecond precision                          │ │   │
│   │   │                                                               │ │   │
│   │   │   Properties:                                                 │ │   │
│   │   │   - Globally unique across all K1 instances                   │ │   │
│   │   │   - Propagates through all downstream calls                   │ │   │
│   │   │   - Links K1 traces to K0 traces via bridge                   │ │   │
│   │   └───────────────────────────────────────────────────────────────┘ │   │
│   │                              │                                      │   │
│   │                              │ trace ID propagates                  │   │
│   │                              ▼                                      │   │
│   └─────────────────────────────────────────────────────────────────────┘   │
│                                  │                                          │
│                                  ▼                                          │
│   ┌─────────────────────────────────────────────────────────────────────┐   │
│   │                    DISTRIBUTED_TRACING                              │   │
│   │               "Cognitive Trace ID"                                  │   │
│   │                                                                     │   │
│   │   ┌───────────────────────────────────────────────────────────────┐ │   │
│   │   │              Span Hierarchy                                   │ │   │
│   │   │                                                               │ │   │
│   │   │   trace_id: cog_abc123_42_1705312200123                       │ │   │
│   │   │   │                                                           │ │   │
│   │   │   ├─ span: CONCIERGE_FSM.LISTENING                            │ │   │
│   │   │   │  └─ duration: 2ms                                         │ │   │
│   │   │   │                                                           │ │   │
│   │   │   ├─ span: ULTRABERT_CLASSIFIER                               │ │   │
│   │   │   │  ├─ ROUTER_HEAD: intent=book_travel                       │ │   │
│   │   │   │  ├─ EMOTION_HEAD: valence=0.7                             │ │   │
│   │   │   │  └─ duration: 15ms                                        │ │   │
│   │   │   │                                                           │ │   │
│   │   │   ├─ span: CONCIERGE_FSM.PLANNING                             │ │   │
│   │   │   │  └─ duration: 5ms                                         │ │   │
│   │   │   │                                                           │ │   │
│   │   │   ├─ span: PLANNER_AGENT.generate_plan                        │ │   │
│   │   │   │  ├─ MODEL_GATEWAY call (gpt-4)                            │ │   │
│   │   │   │  │  └─ duration: 850ms                                    │ │   │
│   │   │   │  └─ duration: 900ms                                       │ │   │
│   │   │   │                                                           │ │   │
│   │   │   ├─ span: ORCHESTRATOR.execute_dag                           │ │   │
│   │   │   │  │                                                        │ │   │
│   │   │   │  ├─ span: CAPABILITY_FABRIC.invoke                        │ │   │
│   │   │   │  │  ├─ capability: travel.search_flights                  │ │   │
│   │   │   │  │  ├─ K0 MCP call (external)                             │ │   │
│   │   │   │  │  └─ duration: 2500ms                                   │ │   │
│   │   │   │  │                                                        │ │   │
│   │   │   │  └─ duration: 2600ms                                      │ │   │
│   │   │   │                                                           │ │   │
│   │   │   ├─ span: CONCIERGE_FSM.DELIVERING                           │ │   │
│   │   │   │  ├─ MODEL_GATEWAY call (gpt-4)                            │ │   │
│   │   │   │  └─ duration: 600ms                                       │ │   │
│   │   │   │                                                           │ │   │
│   │   │   └─ total_duration: 4072ms                                   │ │   │
│   │   └───────────────────────────────────────────────────────────────┘ │   │
│   │                              │                                      │   │
│   │                              │ "Trace Collection"                   │   │
│   │                              ▼                                      │   │
│   └─────────────────────────────────────────────────────────────────────┘   │
│                                  │                                          │
│                                  ▼                                          │
│   ┌─────────────────────────────────────────────────────────────────────┐   │
│   │                    Trace Storage & Export                           │   │
│   │                                                                     │   │
│   │   Storage:                                                          │   │
│   │   ┌───────────────────────────────────────────────────────────────┐ │   │
│   │   │ - TELEMETRY (8KB) in SessionState WARM tier                   │ │   │
│   │   │ - Recent traces kept for debugging                            │ │   │
│   │   │ - Lossy compression for older traces                          │ │   │
│   │   └───────────────────────────────────────────────────────────────┘ │   │
│   │                                                                     │   │
│   │   Export Formats:                                                   │   │
│   │   ┌───────────────────────────────────────────────────────────────┐ │   │
│   │   │ - OpenTelemetry (OTLP) for external observability             │ │   │
│   │   │ - Jaeger for distributed trace visualization                  │ │   │
│   │   │ - Custom K1 format for internal debugging                     │ │   │
│   │   └───────────────────────────────────────────────────────────────┘ │   │
│   │                                                                     │   │
│   │   Correlation:                                                      │   │
│   │   ┌───────────────────────────────────────────────────────────────┐ │   │
│   │   │ K1 trace_id ←→ K0 trace_id via K0_K1_BRIDGE                   │ │   │
│   │   │ Enables end-to-end debugging across systems                   │ │   │
│   │   └───────────────────────────────────────────────────────────────┘ │   │
│   │                                                                     │   │
│   └─────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
│   Result: Full causality chain from user input to response, all components  │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

### F143: Metrics Aggregator → SessionState Flow

**Trigger:** K1 components emit performance metrics
**Outcome:** Metrics aggregated and stored in SessionState TELEMETRY

```
┌─────────────────────────────────────────────────────────────────────────────┐
│               F143: METRICS AGGREGATOR → SESSIONSTATE FLOW                  │
│                                                                             │
│   Component: METRICS_AGGREGATOR                                             │
│   Purpose: Collect, aggregate, and store performance metrics                │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│   ┌─────────────────────────────────────────────────────────────────────┐   │
│   │                    Metric Sources                                   │   │
│   │                                                                     │   │
│   │   ┌─────────────────┐ ┌─────────────────┐ ┌─────────────────┐       │   │
│   │   │ CONCIERGE_FSM   │ │ MODEL_GATEWAY   │ │ CAPABILITY_     │       │   │
│   │   │                 │ │                 │ │ FABRIC          │       │   │
│   │   │ Metrics:        │ │ Metrics:        │ │ Metrics:        │       │   │
│   │   │ - state_dur_ms  │ │ - llm_latency   │ │ - invoke_dur_ms │       │   │
│   │   │ - turns_count   │ │ - token_count   │ │ - success_rate  │       │   │
│   │   │ - error_count   │ │ - cache_hits    │ │ - provider_lat  │       │   │
│   │   └────────┬────────┘ └────────┬────────┘ └────────┬────────┘       │   │
│   │            │                   │                   │                │   │
│   │            └───────────────────┼───────────────────┘                │   │
│   │                                │                                    │   │
│   │   ┌─────────────────┐ ┌───────┴───────┐ ┌─────────────────┐         │   │
│   │   │ ORCHESTRATOR    │ │ ULTRABERT     │ │ K0_K1_BRIDGE    │         │   │
│   │   │                 │ │               │ │                 │         │   │
│   │   │ Metrics:        │ │ Metrics:      │ │ Metrics:        │         │   │
│   │   │ - dag_exec_ms   │ │ - infer_ms    │ │ - sse_events    │         │   │
│   │   │ - active_agents │ │ - batch_size  │ │ - mcp_calls     │         │   │
│   │   │ - queue_depth   │ │ - accuracy    │ │ - bridge_lat_ms │         │   │
│   │   └────────┬────────┘ └───────┬───────┘ └────────┬────────┘         │   │
│   │            │                  │                  │                  │   │
│   │            └──────────────────┼──────────────────┘                  │   │
│   │                               │                                     │   │
│   │                               │ all metrics                         │   │
│   │                               ▼                                     │   │
│   └───────────────────────────────────────────────────────────────────────┘ │
│                                   │                                         │
│                                   ▼                                         │
│   ┌─────────────────────────────────────────────────────────────────────┐   │
│   │                    METRICS_AGGREGATOR                               │   │
│   │            "Performance & Usage"                                    │   │
│   │                                                                     │   │
│   │   ┌───────────────────────────────────────────────────────────────┐ │   │
│   │   │              Aggregation Pipeline                             │ │   │
│   │   │                                                               │ │   │
│   │   │   1. COLLECT: Receive metrics from all components             │ │   │
│   │   │   ┌─────────────────────────────────────────────────────────┐ │ │   │
│   │   │   │ - Metrics pushed via EVENT_BUS                          │ │ │   │
│   │   │   │ - Buffered in 100ms windows                             │ │ │   │
│   │   │   │ - Tagged with trace_id and timestamp                    │ │ │   │
│   │   │   └─────────────────────────────────────────────────────────┘ │ │   │
│   │   │                                                               │ │   │
│   │   │   2. AGGREGATE: Compute rollups                               │ │   │
│   │   │   ┌─────────────────────────────────────────────────────────┐ │ │   │
│   │   │   │ Per-Turn Aggregates:                                    │ │ │   │
│   │   │   │ - total_latency_ms: sum(all component latencies)        │ │ │   │
│   │   │   │ - llm_tokens_used: sum(input + output tokens)           │ │ │   │
│   │   │   │ - capability_invocations: count                         │ │ │   │
│   │   │   │ - error_count: count(failures)                          │ │ │   │
│   │   │   │                                                         │ │ │   │
│   │   │   │ Rolling Averages (last 10 turns):                       │ │ │   │
│   │   │   │ - avg_turn_latency_ms                                   │ │ │   │
│   │   │   │ - avg_llm_latency_ms                                    │ │ │   │
│   │   │   │ - cache_hit_rate                                        │ │ │   │
│   │   │   │ - ultrabert_accuracy                                    │ │ │   │
│   │   │   └─────────────────────────────────────────────────────────┘ │ │   │
│   │   │                                                               │ │   │
│   │   │   3. COMPRESS: Lossy compression for older data               │ │   │
│   │   │   ┌─────────────────────────────────────────────────────────┐ │ │   │
│   │   │   │ Recent (last 10 turns): Full fidelity                   │ │ │   │
│   │   │   │ Older (10-40 turns): Percentiles only (p50, p95, p99)   │ │ │   │
│   │   │   │ Session-level: Summary statistics only                  │ │ │   │
│   │   │   └─────────────────────────────────────────────────────────┘ │ │   │
│   │   └───────────────────────────────────────────────────────────────┘ │   │
│   │                              │                                      │   │
│   │                              │ "Aggregate Metrics"                  │   │
│   │                              ▼                                      │   │
│   └─────────────────────────────────────────────────────────────────────┘   │
│                                  │                                          │
│                                  ▼                                          │
│   ┌─────────────────────────────────────────────────────────────────────┐   │
│   │                    SESSIONSTATE_STORE                               │   │
│   │                                                                     │   │
│   │   ┌───────────────────────────────────────────────────────────────┐ │   │
│   │   │              TELEMETRY (8KB, WARM tier)                       │ │   │
│   │   │                                                               │ │   │
│   │   │   {                                                           │ │   │
│   │   │     "session_metrics": {                                      │ │   │
│   │   │       "total_turns": 42,                                      │ │   │
│   │   │       "total_llm_tokens": 15420,                              │ │   │
│   │   │       "total_capability_calls": 28,                           │ │   │
│   │   │       "total_errors": 2,                                      │ │   │
│   │   │       "session_duration_ms": 1850000                          │ │   │
│   │   │     },                                                        │ │   │
│   │   │     "rolling_averages": {                                     │ │   │
│   │   │       "avg_turn_latency_ms": 2150,                            │ │   │
│   │   │       "avg_llm_latency_ms": 850,                              │ │   │
│   │   │       "avg_ultrabert_ms": 15,                                 │ │   │
│   │   │       "cache_hit_rate": 0.42                                  │ │   │
│   │   │     },                                                        │ │   │
│   │   │     "recent_turns": [                                         │ │   │
│   │   │       {"turn": 42, "latency_ms": 2400, "tokens": 380},        │ │   │
│   │   │       {"turn": 41, "latency_ms": 1800, "tokens": 290},        │ │   │
│   │   │       ...                                                     │ │   │
│   │   │     ],                                                        │ │   │
│   │   │     "component_health": {                                     │ │   │
│   │   │       "CONCIERGE_FSM": "healthy",                             │ │   │
│   │   │       "MODEL_GATEWAY": "healthy",                             │ │   │
│   │   │       "CAPABILITY_FABRIC": "degraded"  // high latency        │ │   │
│   │   │     }                                                         │ │   │
│   │   │   }                                                           │ │   │
│   │   └───────────────────────────────────────────────────────────────┘ │   │
│   │                                                                     │   │
│   │   Uses:                                                             │   │
│   │   - Performance debugging                                           │   │
│   │   - Adaptive behavior (reduce complexity if slow)                   │   │
│   │   - User-facing latency explanations                                │   │
│   │   - K0 advisory signals for system optimization                     │   │
│   │                                                                     │   │
│   └─────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
│   Result: Session performance metrics stored and available for analysis     │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

### F144: Health Check Orchestrator Flow

**Trigger:** Periodic health check or degradation detected
**Outcome:** Provider health status updated, routing adjusted

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                   F144: HEALTH CHECK ORCHESTRATOR FLOW                      │
│                                                                             │
│   Component: HEALTH_CHECK_ORCHESTRATOR                                      │
│   Purpose: Monitor fabric provider health and trigger routing adjustments   │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│   ┌─────────────────────────────────────────────────────────────────────┐   │
│   │                    Health Check Triggers                            │   │
│   │                                                                     │   │
│   │   1. PERIODIC: Every 30 seconds (configurable)                      │   │
│   │   2. ON_FAILURE: When capability invocation fails                   │   │
│   │   3. ON_DEGRADATION: When latency exceeds threshold                 │   │
│   │   4. ON_STARTUP: Initial provider discovery                         │   │
│   │                              │                                      │   │
│   │                              │ trigger health checks                │   │
│   │                              ▼                                      │   │
│   └─────────────────────────────────────────────────────────────────────┘   │
│                                  │                                          │
│                                  ▼                                          │
│   ┌─────────────────────────────────────────────────────────────────────┐   │
│   │                 HEALTH_CHECK_ORCHESTRATOR                           │   │
│   │           "Fabric Provider Health"                                  │   │
│   │                                                                     │   │
│   │   ┌───────────────────────────────────────────────────────────────┐ │   │
│   │   │              Health Check Process                             │ │   │
│   │   │                                                               │ │   │
│   │   │   For each registered provider in CAPABILITY_FABRIC:          │ │   │
│   │   │   ┌─────────────────────────────────────────────────────────┐ │ │   │
│   │   │   │                                                         │ │ │   │
│   │   │   │   1. CONNECTIVITY CHECK:                                │ │ │   │
│   │   │   │      - Ping MCP server endpoint                         │ │ │   │
│   │   │   │      - Timeout: 5 seconds                               │ │ │   │
│   │   │   │      - Pass/Fail                                        │ │ │   │
│   │   │   │                                                         │ │ │   │
│   │   │   │   2. CAPABILITY CHECK:                                  │ │ │   │
│   │   │   │      - Verify capabilities still advertised             │ │ │   │
│   │   │   │      - Check capability versions match                  │ │ │   │
│   │   │   │      - Detect new/removed capabilities                  │ │ │   │
│   │   │   │                                                         │ │ │   │
│   │   │   │   3. LATENCY CHECK:                                     │ │ │   │
│   │   │   │      - Measure round-trip time                          │ │ │   │
│   │   │   │      - Compare to historical baseline                   │ │ │   │
│   │   │   │      - Flag if >2x baseline                             │ │ │   │
│   │   │   │                                                         │ │ │   │
│   │   │   │   4. RESOURCE CHECK:                                    │ │ │   │
│   │   │   │      - Query provider rate limits (if supported)        │ │ │   │
│   │   │   │      - Check quota remaining                            │ │ │   │
│   │   │   │      - Estimate time to quota reset                     │ │ │   │
│   │   │   │                                                         │ │ │   │
│   │   │   └─────────────────────────────────────────────────────────┘ │ │   │
│   │   └───────────────────────────────────────────────────────────────┘ │   │
│   │                              │                                      │   │
│   │   ┌───────────────────────────────────────────────────────────────┐ │   │
│   │   │              Health Status Matrix                             │ │   │
│   │   │                                                               │ │   │
│   │   │   Provider Health States:                                     │ │   │
│   │   │   ┌─────────────────────────────────────────────────────────┐ │ │   │
│   │   │   │ HEALTHY:                                                │ │ │   │
│   │   │   │   - All checks pass                                     │ │ │   │
│   │   │   │   - Latency within baseline                             │ │ │   │
│   │   │   │   - Full routing weight                                 │ │ │   │
│   │   │   │                                                         │ │ │   │
│   │   │   │ DEGRADED:                                               │ │ │   │
│   │   │   │   - Connectivity OK, but high latency                   │ │ │   │
│   │   │   │   - Or quota near exhaustion                            │ │ │   │
│   │   │   │   - Reduced routing weight (50%)                        │ │ │   │
│   │   │   │                                                         │ │ │   │
│   │   │   │ UNHEALTHY:                                              │ │ │   │
│   │   │   │   - Connectivity failed                                 │ │ │   │
│   │   │   │   - Or repeated errors                                  │ │ │   │
│   │   │   │   - Routing weight: 0 (failover to backup)              │ │ │   │
│   │   │   │                                                         │ │ │   │
│   │   │   │ RECOVERING:                                             │ │ │   │
│   │   │   │   - Previously unhealthy, now passing checks            │ │ │   │
│   │   │   │   - Gradual routing weight increase                     │ │ │   │
│   │   │   │   - Full weight after 3 consecutive healthy checks      │ │ │   │
│   │   │   └─────────────────────────────────────────────────────────┘ │ │   │
│   │   └───────────────────────────────────────────────────────────────┘ │   │
│   │                              │                                      │   │
│   │                              │ "Health Checks"                      │   │
│   │                              ▼                                      │   │
│   └─────────────────────────────────────────────────────────────────────┘   │
│                                  │                                          │
│                                  ▼                                          │
│   ┌─────────────────────────────────────────────────────────────────────┐   │
│   │                     CAPABILITY_FABRIC                               │   │
│   │                                                                     │   │
│   │   ┌───────────────────────────────────────────────────────────────┐ │   │
│   │   │              Provider Registry Update                         │ │   │
│   │   │                                                               │ │   │
│   │   │   PROVIDER_REGISTRY:                                          │ │   │
│   │   │   ┌─────────────────────────────────────────────────────────┐ │ │   │
│   │   │   │                                                         │ │ │   │
│   │   │   │ travel_mcp:                                             │ │ │   │
│   │   │   │   status: HEALTHY                                       │ │ │   │
│   │   │   │   latency_ms: 120                                       │ │ │   │
│   │   │   │   routing_weight: 1.0                                   │ │ │   │
│   │   │   │   last_check: "2024-01-15T10:30:00Z"                    │ │ │   │
│   │   │   │                                                         │ │ │   │
│   │   │   │ finance_mcp:                                            │ │ │   │
│   │   │   │   status: DEGRADED                                      │ │ │   │
│   │   │   │   latency_ms: 850  (baseline: 200)                      │ │ │   │
│   │   │   │   routing_weight: 0.5                                   │ │ │   │
│   │   │   │   last_check: "2024-01-15T10:30:00Z"                    │ │ │   │
│   │   │   │                                                         │ │ │   │
│   │   │   │ calendar_mcp:                                           │ │ │   │
│   │   │   │   status: UNHEALTHY                                     │ │ │   │
│   │   │   │   error: "Connection refused"                           │ │ │   │
│   │   │   │   routing_weight: 0.0                                   │ │ │   │
│   │   │   │   failover_to: calendar_mcp_backup                      │ │ │   │
│   │   │   │   last_check: "2024-01-15T10:30:00Z"                    │ │ │   │
│   │   │   │                                                         │ │ │   │
│   │   │   └─────────────────────────────────────────────────────────┘ │ │   │
│   │   │                                                               │ │   │
│   │   │   Routing Adjustments:                                        │ │   │
│   │   │   - PROVIDER_SELECTOR uses updated weights                    │ │   │
│   │   │   - Degraded providers get fewer requests                     │ │   │
│   │   │   - Unhealthy providers bypassed entirely                     │ │   │
│   │   │   - Failover chains activated automatically                   │ │   │
│   │   │                                                               │ │   │
│   │   └───────────────────────────────────────────────────────────────┘ │   │
│   │                                                                     │   │
│   └─────────────────────────────────────────────────────────────────────┘   │
│                                  │                                          │
│                                  │ health events                            │
│                                  ▼                                          │
│   ┌─────────────────────────────────────────────────────────────────────┐   │
│   │                        EVENT_BUS                                    │   │
│   │                                                                     │   │
│   │   Events emitted:                                                   │   │
│   │   - k1.fabric.provider.healthy.v1                                   │   │
│   │   - k1.fabric.provider.degraded.v1                                  │   │
│   │   - k1.fabric.provider.unhealthy.v1                                 │   │
│   │   - k1.fabric.provider.recovered.v1                                 │   │
│   │                                                                     │   │
│   │   Subscribers:                                                      │   │
│   │   - METRICS_AGGREGATOR (track health over time)                     │   │
│   │   - CONCIERGE_FSM (user-facing explanations if degraded)            │   │
│   │   - LEARNING_LOOP (adjust usage patterns)                           │   │
│   │                                                                     │   │
│   └─────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
│   Result: Automatic health monitoring with graceful degradation             │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## FLOW SUMMARY

| Category | Count |
|----------|-------|
| Core Conversation | 10 |
| UltraBERT Classification | 22 |
| Tool Execution | 10 |
| Orchestrator | 10 |
| Planner | 7 |
| Sub-Agent | 6 |
| SessionState | 12 |
| K0 Bridge | 10 |
| Proactive Agent | 7 |
| Capability Fabric | 9 |
| Model Gateway | 8 |
| Experience Layer | 8 |
| Rhythm & Empathy | 8 |
| Module Loader | 4 |
| Event Bus & Coordination | 6 |
| HIL Feedback | 4 |
| Observability | 3 |
| LLM Control Plane | 10 |
| **TOTAL** | **154** |

---

## 18. LLM CONTROL PLANE FLOWS

### 18.1 Prompt Management Flows

- [x] **F145: Prompt Resolution → Template Lookup Flow**
- [x] **F146: Prompt Variable Injection Flow**
- [x] **F147: Prompt Compilation → Model Gateway Flow**
- [x] **F148: Dynamic Agent Prompt Registration Flow**

### 18.2 Output Validation Flows

- [x] **F149: LLM Output → 3-Tier Validation Pipeline Flow**
- [x] **F150: Schema Registry → Agent Schema Lookup Flow**
- [x] **F151: Hallucination Detection → SessionState Cross-Reference Flow**
- [x] **F152: Validation Fallback → Retry/Repair/Reject Flow**
- [x] **F153: Dynamic Agent Schema Registration Flow**
- [x] **F154: Core vs Generic Payload Schema Selection Flow**

---

### F145: Prompt Resolution → Template Lookup Flow

**Trigger:** LLM consumer requests a prompt by ID (e.g., `concierge.response`)
**Outcome:** Correct prompt template retrieved from file-based store

```
┌─────────────────────────────────────────────────────────────────────────────┐
│               F145: PROMPT RESOLUTION → TEMPLATE LOOKUP FLOW                │
│                                                                             │
│   Component: PROMPT_RESOLVER + PROMPT_TEMPLATE_STORE                        │
│   Purpose: Map consumer prompt request to file-based template               │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│   ┌─────────────────────────────────────────────────────────────────────┐   │
│   │                    LLM Consumer Request                             │   │
│   │                                                                     │   │
│   │   Examples:                                                         │   │
│   │   - CONCIERGE_FSM: "concierge.response"                             │   │
│   │   - PLANNER_AGENT: "planner.sketch"                                 │   │
│   │   - MEMORY_WRITER: "memory.extract"                                 │   │
│   │   - DYNAMIC_AGENT: "agent.health.analyze"                           │   │
│   │                              │                                      │   │
│   │                              │ prompt_id                            │   │
│   │                              ▼                                      │   │
│   └─────────────────────────────────────────────────────────────────────┘   │
│                                  │                                          │
│                                  ▼                                          │
│   ┌─────────────────────────────────────────────────────────────────────┐   │
│   │                    PROMPT_RESOLVER                                  │   │
│   │               "Consumer → Template Lookup"                          │   │
│   │                                                                     │   │
│   │   ┌───────────────────────────────────────────────────────────────┐ │   │
│   │   │              Resolution Algorithm                             │ │   │
│   │   │                                                               │ │   │
│   │   │   Input: prompt_id = "concierge.response"                     │ │   │
│   │   │                                                               │ │   │
│   │   │   1. Parse prompt_id:                                         │ │   │
│   │   │      namespace = "concierge"                                  │ │   │
│   │   │      template = "response"                                    │ │   │
│   │   │                                                               │ │   │
│   │   │   2. Resolve file path:                                       │ │   │
│   │   │      k1/prompts/core/{namespace}/{template}.md                │ │   │
│   │   │      → k1/prompts/core/concierge/response.md                  │ │   │
│   │   │                                                               │ │   │
│   │   │   3. For dynamic agents:                                      │ │   │
│   │   │      prompt_id = "agent.health.analyze"                       │ │   │
│   │   │      → k1/prompts/agents/health/analyze.md                    │ │   │
│   │   │                                                               │ │   │
│   │   │   4. Check cache (MODULE_CACHE):                              │ │   │
│   │   │      - If cached & not stale: return cached                   │ │   │
│   │   │      - If not cached: load from disk                          │ │   │
│   │   │                                                               │ │   │
│   │   └───────────────────────────────────────────────────────────────┘ │   │
│   │                              │                                      │   │
│   │                              │ file_path                            │   │
│   │                              ▼                                      │   │
│   └─────────────────────────────────────────────────────────────────────┘   │
│                                  │                                          │
│                                  ▼                                          │
│   ┌─────────────────────────────────────────────────────────────────────┐   │
│   │                    PROMPT_TEMPLATE_STORE                            │   │
│   │               "File-Based Template Storage"                         │   │
│   │                                                                     │   │
│   │   Directory Structure:                                              │   │
│   │   ┌───────────────────────────────────────────────────────────────┐ │   │
│   │   │                                                               │ │   │
│   │   │   k1/prompts/                                                 │ │   │
│   │   │   ├── core/                      # Core system prompts        │ │   │
│   │   │   │   ├── concierge/                                          │ │   │
│   │   │   │   │   ├── response.md        # Main response generation   │ │   │
│   │   │   │   │   ├── clarification.md   # Clarification questions    │ │   │
│   │   │   │   │   ├── empathy.md         # Empathetic framing         │ │   │
│   │   │   │   │   └── preliminary_ack.md # Quick acknowledgment       │ │   │
│   │   │   │   ├── planner/                                            │ │   │
│   │   │   │   │   ├── sketch.md          # Initial plan outline       │ │   │
│   │   │   │   │   ├── expand.md          # Plan expansion             │ │   │
│   │   │   │   │   └── validate.md        # Plan validation            │ │   │
│   │   │   │   ├── memory_writer/                                      │ │   │
│   │   │   │   │   ├── extract.md         # Fact extraction            │ │   │
│   │   │   │   │   └── consolidate.md     # Memory consolidation       │ │   │
│   │   │   │   └── validator/                                          │ │   │
│   │   │   │       └── check.md           # Solution validation        │ │   │
│   │   │   │                                                           │ │   │
│   │   │   └── agents/                    # Agent-specific prompts     │ │   │
│   │   │       ├── health/                                             │ │   │
│   │   │       │   ├── analyze.md                                      │ │   │
│   │   │       │   └── recommend.md                                    │ │   │
│   │   │       ├── finance/                                            │ │   │
│   │   │       │   ├── analyze.md                                      │ │   │
│   │   │       │   └── budget.md                                       │ │   │
│   │   │       └── {dynamic_agent}/       # Runtime-registered         │ │   │
│   │   │           └── *.md                                            │ │   │
│   │   │                                                               │ │   │
│   │   └───────────────────────────────────────────────────────────────┘ │   │
│   │                                                                     │   │
│   │   Template Format (Markdown with YAML frontmatter):                 │   │
│   │   ┌───────────────────────────────────────────────────────────────┐ │   │
│   │   │   ---                                                         │ │   │
│   │   │   id: concierge.response                                      │ │   │
│   │   │   version: 2.1.0                                              │ │   │
│   │   │   output_schema: concierge_payload                            │ │   │
│   │   │   max_tokens: 500                                             │ │   │
│   │   │   variables:                                                  │ │   │
│   │   │     - name: user_name                                         │ │   │
│   │   │       source: sessionstate.persona.name                       │ │   │
│   │   │     - name: emotion                                           │ │   │
│   │   │       source: sessionstate.affective_now.primary              │ │   │
│   │   │     - name: tool_results                                      │ │   │
│   │   │       source: tool_result_buffer                              │ │   │
│   │   │   ---                                                         │ │   │
│   │   │                                                               │ │   │
│   │   │   You are a helpful family assistant.                         │ │   │
│   │   │   User: {{user_name}}                                         │ │   │
│   │   │   Current emotion: {{emotion}}                                │ │   │
│   │   │                                                               │ │   │
│   │   │   Tool results: {{tool_results}}                              │ │   │
│   │   │                                                               │ │   │
│   │   │   Respond in JSON format:                                     │ │   │
│   │   │   {                                                           │ │   │
│   │   │     "response_text": "...",                                   │ │   │
│   │   │     "tone": "warm|neutral|professional",                      │ │   │
│   │   │     "next_actions": [...]                                     │ │   │
│   │   │   }                                                           │ │   │
│   │   │                                                               │ │   │
│   │   └───────────────────────────────────────────────────────────────┘ │   │
│   │                                                                     │   │
│   └─────────────────────────────────────────────────────────────────────┘   │
│                                  │                                          │
│                                  │ raw_template + metadata                  │
│                                  ▼                                          │
│   ┌─────────────────────────────────────────────────────────────────────┐   │
│   │                    PROMPT_VERSION_CONTROLLER                        │   │
│   │                                                                     │   │
│   │   Version Resolution:                                               │   │
│   │   - Check if A/B test active for this prompt                        │   │
│   │   - Select version based on session_id hash                         │   │
│   │   - Log version selection for metrics                               │   │
│   │                                                                     │   │
│   └─────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
│   Result: Versioned template ready for variable injection                   │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

### F146: Prompt Variable Injection Flow

**Trigger:** Template loaded, needs variables from SessionState
**Outcome:** Template variables replaced with actual values

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                  F146: PROMPT VARIABLE INJECTION FLOW                       │
│                                                                             │
│   Component: PROMPT_VARIABLE_INJECTOR                                       │
│   Purpose: Inject SessionState values into prompt template variables        │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│   ┌─────────────────────────────────────────────────────────────────────┐   │
│   │                    Template with Variables                          │   │
│   │                                                                     │   │
│   │   variables:                                                        │   │
│   │     - name: user_name                                               │   │
│   │       source: sessionstate.persona.name                             │   │
│   │     - name: emotion                                                 │   │
│   │       source: sessionstate.affective_now.primary                    │   │
│   │     - name: tool_results                                            │   │
│   │       source: tool_result_buffer                                    │   │
│   │     - name: history                                                 │   │
│   │       source: sessionstate.history_active                           │   │
│   │       transform: last_5_turns                                       │   │
│   │                              │                                      │   │
│   │                              │ variable_specs                       │   │
│   │                              ▼                                      │   │
│   └─────────────────────────────────────────────────────────────────────┘   │
│                                  │                                          │
│                                  ▼                                          │
│   ┌─────────────────────────────────────────────────────────────────────┐   │
│   │                    PROMPT_VARIABLE_INJECTOR                         │   │
│   │               "SessionState → Template Vars"                        │   │
│   │                                                                     │   │
│   │   ┌───────────────────────────────────────────────────────────────┐ │   │
│   │   │              Variable Resolution Pipeline                     │ │   │
│   │   │                                                               │ │   │
│   │   │   For each variable in template:                              │ │   │
│   │   │                                                               │ │   │
│   │   │   1. PARSE SOURCE PATH:                                       │ │   │
│   │   │      "sessionstate.persona.name"                              │ │   │
│   │   │      → store="sessionstate", path="persona.name"              │ │   │
│   │   │                                                               │ │   │
│   │   │   2. FETCH VALUE:                                             │ │   │
│   │   │      SessionState.read("persona.name")                        │ │   │
│   │   │      → "Alex"                                                 │ │   │
│   │   │                                                               │ │   │
│   │   │   3. APPLY TRANSFORM (if specified):                          │ │   │
│   │   │      transform: last_5_turns                                  │ │   │
│   │   │      → extract last 5 entries from history array              │ │   │
│   │   │                                                               │ │   │
│   │   │   4. FORMAT FOR PROMPT:                                       │ │   │
│   │   │      - Strings: as-is                                         │ │   │
│   │   │      - Arrays: JSON serialize                                 │ │   │
│   │   │      - Objects: JSON serialize                                │ │   │
│   │   │      - Numbers: string convert                                │ │   │
│   │   │                                                               │ │   │
│   │   │   5. TOKEN BUDGET CHECK:                                      │ │   │
│   │   │      If variable would exceed CONTEXT_BUDGET:                 │ │   │
│   │   │      → Truncate with "[...truncated]"                         │ │   │
│   │   │      → Or summarize if transformer available                  │ │   │
│   │   │                                                               │ │   │
│   │   └───────────────────────────────────────────────────────────────┘ │   │
│   │                              │                                      │   │
│   │   ┌───────────────────────────────────────────────────────────────┐ │   │
│   │   │              Source Types                                     │ │   │
│   │   │                                                               │ │   │
│   │   │   sessionstate.*     → Read from SessionState store           │ │   │
│   │   │   tool_result_buffer → Current turn's tool results            │ │   │
│   │   │   ultrabert.*        → UltraBERT classification results       │ │   │
│   │   │   context.*          → Request context (turn_id, etc.)        │ │   │
│   │   │   k0.*               → K0 memory query results                │ │   │
│   │   │                                                               │ │   │
│   │   └───────────────────────────────────────────────────────────────┘ │   │
│   │                              │                                      │   │
│   │                              │ variable_values{}                    │   │
│   │                              ▼                                      │   │
│   └─────────────────────────────────────────────────────────────────────┘   │
│                                  │                                          │
│                                  ▼                                          │
│   ┌─────────────────────────────────────────────────────────────────────┐   │
│   │                    SESSIONSTATE_STORE                               │   │
│   │                                                                     │   │
│   │   Multi-Reader Access (ADR-0017):                                   │   │
│   │   - PROMPT_VARIABLE_INJECTOR reads from HOT + WARM tiers            │   │
│   │   - <1ms read latency                                               │   │
│   │   - No write permissions (Single Writer = Concierge only)           │   │
│   │                                                                     │   │
│   └─────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
│   Result: All template variables resolved to concrete values                │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

### F147: Prompt Compilation → Model Gateway Flow

**Trigger:** Template + variables ready
**Outcome:** Final compiled prompt sent to MODEL_ROUTER

```
┌─────────────────────────────────────────────────────────────────────────────┐
│              F147: PROMPT COMPILATION → MODEL GATEWAY FLOW                  │
│                                                                             │
│   Component: PROMPT_COMPILER → MODEL_ROUTER                                 │
│   Purpose: Assemble final prompt and route to LLM provider                  │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│   ┌─────────────────────────────────────────────────────────────────────┐   │
│   │                    PROMPT_COMPILER                                  │   │
│   │               "Template + Context → Final Prompt"                   │   │
│   │                                                                     │   │
│   │   ┌───────────────────────────────────────────────────────────────┐ │   │
│   │   │              Compilation Steps                                │ │   │
│   │   │                                                               │ │   │
│   │   │   Input:                                                      │ │   │
│   │   │   - template: "You are a helpful... {{user_name}}..."         │ │   │
│   │   │   - variables: {user_name: "Alex", emotion: "anxious", ...}   │ │   │
│   │   │   - metadata: {output_schema: "concierge_payload", ...}       │ │   │
│   │   │                                                               │ │   │
│   │   │   1. VARIABLE SUBSTITUTION:                                   │ │   │
│   │   │      Replace {{variable}} with values                         │ │   │
│   │   │      "You are a helpful... Alex..."                           │ │   │
│   │   │                                                               │ │   │
│   │   │   2. SYSTEM PROMPT INJECTION:                                 │ │   │
│   │   │      Prepend global system instructions                       │ │   │
│   │   │      (safety, format, persona base)                           │ │   │
│   │   │                                                               │ │   │
│   │   │   3. OUTPUT SCHEMA HINT:                                      │ │   │
│   │   │      Append: "Respond in JSON matching schema: ..."           │ │   │
│   │   │      Include required fields from output_schema               │ │   │
│   │   │                                                               │ │   │
│   │   │   4. TOKEN COUNT:                                             │ │   │
│   │   │      Count tokens in compiled prompt                          │ │   │
│   │   │      Verify within max_tokens from metadata                   │ │   │
│   │   │                                                               │ │   │
│   │   └───────────────────────────────────────────────────────────────┘ │   │
│   │                              │                                      │   │
│   │                              │ compiled_prompt + request_metadata   │   │
│   │                              ▼                                      │   │
│   └─────────────────────────────────────────────────────────────────────┘   │
│                                  │                                          │
│                                  ▼                                          │
│   ┌─────────────────────────────────────────────────────────────────────┐   │
│   │                    MODEL_ROUTER                                     │   │
│   │               "Load Balancing & Fallback"                           │   │
│   │                                                                     │   │
│   │   Request Structure (FlatBuffers):                                  │   │
│   │   ┌───────────────────────────────────────────────────────────────┐ │   │
│   │   │                                                               │ │   │
│   │   │   table LLMRequest {                                          │ │   │
│   │   │     request_id: string;                                       │ │   │
│   │   │     consumer_id: string;    // "concierge", "planner", etc.   │ │   │
│   │   │     prompt_id: string;      // "concierge.response"           │ │   │
│   │   │     prompt_version: string; // "2.1.0"                        │ │   │
│   │   │     compiled_prompt: string;                                  │ │   │
│   │   │     output_schema_id: string;                                 │ │   │
│   │   │     max_tokens: int32;                                        │ │   │
│   │   │     temperature: float;                                       │ │   │
│   │   │     trace_id: string;       // Cognitive Trace ID             │ │   │
│   │   │   }                                                           │ │   │
│   │   │                                                               │ │   │
│   │   └───────────────────────────────────────────────────────────────┘ │   │
│   │                              │                                      │   │
│   │   ┌───────────────────────────────────────────────────────────────┐ │   │
│   │   │              Routing Decision                                 │ │   │
│   │   │                                                               │ │   │
│   │   │   1. Check MODEL_CACHE for semantic match                     │ │   │
│   │   │      → If hit: return cached response                         │ │   │
│   │   │                                                               │ │   │
│   │   │   2. Select provider via HUB_ROUTER:                          │ │   │
│   │   │      - Check provider health                                  │ │   │
│   │   │      - Apply load balancing                                   │ │   │
│   │   │      - Consider cost/latency tradeoffs                        │ │   │
│   │   │                                                               │ │   │
│   │   │   3. Track in MODEL_METRICS:                                  │ │   │
│   │   │      - Token usage                                            │ │   │
│   │   │      - Latency                                                │ │   │
│   │   │      - Provider selection                                     │ │   │
│   │   │                                                               │ │   │
│   │   └───────────────────────────────────────────────────────────────┘ │   │
│   │                              │                                      │   │
│   │                              │ routed to provider                   │   │
│   │                              ▼                                      │   │
│   └─────────────────────────────────────────────────────────────────────┘   │
│                                  │                                          │
│                                  ▼                                          │
│   ┌─────────────────────────────────────────────────────────────────────┐   │
│   │                    HUB_ROUTER → LLM_PROVIDERS                       │   │
│   │                                                                     │   │
│   │   Provider Selection:                                               │   │
│   │   - HUB_OPENAI: GPT-4, GPT-3.5-turbo                                │   │
│   │   - HUB_ANTHROPIC: Claude models                                    │   │
│   │   - HUB_OTHERS: Google, Meta, local models                          │   │
│   │                                                                     │   │
│   └─────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
│   Result: LLM request sent to provider, response awaited                    │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

### F148: Dynamic Agent Prompt Registration Flow

**Trigger:** AGENT_FACTORY spawns new dynamic agent instance
**Outcome:** Agent's prompts registered in PROMPT_TEMPLATE_STORE

```
┌─────────────────────────────────────────────────────────────────────────────┐
│             F148: DYNAMIC AGENT PROMPT REGISTRATION FLOW                    │
│                                                                             │
│   Component: AGENT_FACTORY → PROMPT_TEMPLATE_STORE                          │
│   Purpose: Register agent-specific prompts at spawn time                    │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│   ┌─────────────────────────────────────────────────────────────────────┐   │
│   │                    CAPABILITY_FABRIC                                │   │
│   │                                                                     │   │
│   │   Spawn Request:                                                    │   │
│   │   {                                                                 │   │
│   │     capability: "agent.spawn.health",                               │   │
│   │     template: "health_agent",                                       │   │
│   │     instance_id: "health_abc123"                                    │   │
│   │   }                                                                 │   │
│   │                              │                                      │   │
│   │                              │ spawn_request                        │   │
│   │                              ▼                                      │   │
│   └─────────────────────────────────────────────────────────────────────┘   │
│                                  │                                          │
│                                  ▼                                          │
│   ┌─────────────────────────────────────────────────────────────────────┐   │
│   │                    AGENT_FACTORY                                    │   │
│   │               "Creates from YAML templates"                         │   │
│   │                                                                     │   │
│   │   ┌───────────────────────────────────────────────────────────────┐ │   │
│   │   │              Agent Template (YAML)                            │ │   │
│   │   │                                                               │ │   │
│   │   │   # k1/contracts/agents/health_agent.yaml                     │ │   │
│   │   │   id: health_agent                                            │ │   │
│   │   │   version: 1.2.0                                              │ │   │
│   │   │   capabilities:                                               │ │   │
│   │   │     - health.analyze                                          │ │   │
│   │   │     - health.recommend                                        │ │   │
│   │   │   prompts:                                                    │ │   │
│   │   │     analyze: agent.health.analyze                             │ │   │
│   │   │     recommend: agent.health.recommend                         │ │   │
│   │   │   output_schema: health_payload                               │ │   │
│   │   │   prompt_dir: k1/prompts/agents/health/                       │ │   │
│   │   │                                                               │ │   │
│   │   └───────────────────────────────────────────────────────────────┘ │   │
│   │                              │                                      │   │
│   │                              │ template.prompt_dir                  │   │
│   │                              ▼                                      │   │
│   └─────────────────────────────────────────────────────────────────────┘   │
│                                  │                                          │
│                                  ▼                                          │
│   ┌─────────────────────────────────────────────────────────────────────┐   │
│   │                    Registration Process                             │   │
│   │                                                                     │   │
│   │   1. LOAD AGENT PROMPTS:                                            │   │
│   │      Read all *.md files from template.prompt_dir                   │   │
│   │      k1/prompts/agents/health/*.md                                  │   │
│   │                                                                     │   │
│   │   2. REGISTER IN PROMPT_REGISTRY:                                   │   │
│   │      For each prompt file:                                          │   │
│   │      - Parse YAML frontmatter                                       │   │
│   │      - Register with namespace: "agent.{template_id}"               │   │
│   │      - Store in MODULE_CACHE for fast access                        │   │
│   │                                                                     │   │
│   │   3. REGISTER SCHEMA:                                               │   │
│   │      Load template.output_schema                                    │   │
│   │      → health_payload.fbs                                           │   │
│   │      Register in SCHEMA_REGISTRY                                    │   │
│   │                                                                     │   │
│   │   4. LINK INSTANCE:                                                 │   │
│   │      Map instance_id → template prompts/schema                      │   │
│   │      health_abc123 → {prompts: [...], schema: health_payload}       │   │
│   │                                                                     │   │
│   └─────────────────────────────────────────────────────────────────────┘   │
│                                  │                                          │
│                                  │ registration_complete                    │
│                                  ▼                                          │
│   ┌─────────────────────────────────────────────────────────────────────┐   │
│   │                    DYNAMIC_INSTANCES                                │   │
│   │                                                                     │   │
│   │   Instance ready with:                                              │   │
│   │   - Prompts: agent.health.analyze, agent.health.recommend           │   │
│   │   - Schema: health_payload                                          │   │
│   │   - Can now call MODEL_GATEWAY via PROMPT_RESOLVER                  │   │
│   │                                                                     │   │
│   └─────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
│   Result: Dynamic agent has prompts + schema registered at spawn time       │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

### F149: LLM Output → 3-Tier Validation Pipeline Flow

**Trigger:** LLM provider returns raw response
**Outcome:** Response validated through 3 tiers, returned to consumer or fallback triggered

```
┌─────────────────────────────────────────────────────────────────────────────┐
│            F149: LLM OUTPUT → 3-TIER VALIDATION PIPELINE FLOW               │
│                                                                             │
│   Component: OUTPUT_VALIDATOR + VALIDATION_PIPELINE                         │
│   Purpose: Ensure LLM outputs conform to expected structure and semantics   │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│   ┌─────────────────────────────────────────────────────────────────────┐   │
│   │                    HUB_ROUTER                                       │   │
│   │                                                                     │   │
│   │   Raw LLM Response:                                                 │   │
│   │   {                                                                 │   │
│   │     "response_text": "I've set a reminder for 5pm.",                │   │
│   │     "tone": "warm",                                                 │   │
│   │     "next_actions": ["check_calendar", "confirm_with_user"]         │   │
│   │   }                                                                 │   │
│   │                              │                                      │   │
│   │                              │ raw_response + request_metadata      │   │
│   │                              ▼                                      │   │
│   └─────────────────────────────────────────────────────────────────────┘   │
│                                  │                                          │
│                                  ▼                                          │
│   ┌─────────────────────────────────────────────────────────────────────┐   │
│   │                    OUTPUT_VALIDATOR                                 │   │
│   │               "Orchestrates 3-Tier Validation"                      │   │
│   │                                                                     │   │
│   │   ┌───────────────────────────────────────────────────────────────┐ │   │
│   │   │              Validation Context                               │ │   │
│   │   │                                                               │ │   │
│   │   │   From request_metadata:                                      │ │   │
│   │   │   - consumer_id: "concierge"                                  │ │   │
│   │   │   - output_schema_id: "concierge_payload"                     │ │   │
│   │   │   - prompt_id: "concierge.response"                           │ │   │
│   │   │   - trace_id: "cog_abc123_42_..."                             │ │   │
│   │   │                                                               │ │   │
│   │   │   Lookup schema from SCHEMA_REGISTRY                          │ │   │
│   │   │                                                               │ │   │
│   │   └───────────────────────────────────────────────────────────────┘ │   │
│   │                              │                                      │   │
│   │                              │ route to T1                          │   │
│   │                              ▼                                      │   │
│   └─────────────────────────────────────────────────────────────────────┘   │
│                                  │                                          │
│   ═══════════════════════════════════════════════════════════════════════   │
│                         TIER 1: STRUCTURAL (HARD)                           │
│   ═══════════════════════════════════════════════════════════════════════   │
│                                  │                                          │
│                                  ▼                                          │
│   ┌─────────────────────────────────────────────────────────────────────┐   │
│   │                    TIER1_STRUCTURAL                                 │   │
│   │               "FlatBuffer Parse (HARD)"                             │   │
│   │                                                                     │   │
│   │   Validation Steps:                                                 │   │
│   │   ┌───────────────────────────────────────────────────────────────┐ │   │
│   │   │                                                               │ │   │
│   │   │   1. JSON PARSE:                                              │ │   │
│   │   │      Try to parse raw response as JSON                        │ │   │
│   │   │      → If fail: REJECT (not recoverable)                      │ │   │
│   │   │                                                               │ │   │
│   │   │   2. FLATBUFFER SERIALIZE:                                    │ │   │
│   │   │      Convert JSON to FlatBuffer using CoreOutputSchema        │ │   │
│   │   │      → If fail: REJECT (structural mismatch)                  │ │   │
│   │   │                                                               │ │   │
│   │   │   3. CORE FIELDS CHECK:                                       │ │   │
│   │   │      Verify all LLMOutput base fields present                 │ │   │
│   │   │      (output_id, status, confidence, payload)                 │ │   │
│   │   │                                                               │ │   │
│   │   └───────────────────────────────────────────────────────────────┘ │   │
│   │                              │                                      │   │
│   │              ┌───────────────┴───────────────┐                      │   │
│   │              │                               │                      │   │
│   │              ▼                               ▼                      │   │
│   │         T1_PASS                         T1_FAIL                     │   │
│   │              │                               │                      │   │
│   │              │                               │ → VALIDATION_FALLBACK│   │
│   │              ▼                               │    (immediate REJECT)│   │
│   │         Continue to T2                       │                      │   │
│   │                                                                     │   │
│   └─────────────────────────────────────────────────────────────────────┘   │
│                                  │                                          │
│   ═══════════════════════════════════════════════════════════════════════   │
│                         TIER 2: SCHEMA (RETRY)                              │
│   ═══════════════════════════════════════════════════════════════════════   │
│                                  │                                          │
│                                  ▼                                          │
│   ┌─────────────────────────────────────────────────────────────────────┐   │
│   │                    TIER2_SCHEMA                                     │   │
│   │               "Required Fields + Types (RETRY)"                     │   │
│   │                                                                     │   │
│   │   Validation Steps:                                                 │   │
│   │   ┌───────────────────────────────────────────────────────────────┐ │   │
│   │   │                                                               │ │   │
│   │   │   1. LOOKUP PAYLOAD SCHEMA:                                   │ │   │
│   │   │      output_schema_id = "concierge_payload"                   │ │   │
│   │   │      → Load from SCHEMA_REGISTRY                              │ │   │
│   │   │                                                               │ │   │
│   │   │   2. REQUIRED FIELDS:                                         │ │   │
│   │   │      Check all required fields present                        │ │   │
│   │   │      concierge_payload requires:                              │ │   │
│   │   │        - response_text: string (required)                     │ │   │
│   │   │        - tone: enum (required)                                │ │   │
│   │   │        - next_actions: [string] (optional)                    │ │   │
│   │   │                                                               │ │   │
│   │   │   3. TYPE VALIDATION:                                         │ │   │
│   │   │      Verify field types match schema                          │ │   │
│   │   │      - response_text must be string                           │ │   │
│   │   │      - tone must be enum value                                │ │   │
│   │   │      - next_actions must be array of strings                  │ │   │
│   │   │                                                               │ │   │
│   │   │   4. ENUM VALIDATION:                                         │ │   │
│   │   │      tone in ["warm", "neutral", "professional", "empathetic"]│ │   │
│   │   │                                                               │ │   │
│   │   └───────────────────────────────────────────────────────────────┘ │   │
│   │                              │                                      │   │
│   │              ┌───────────────┴───────────────┐                      │   │
│   │              │                               │                      │   │
│   │              ▼                               ▼                      │   │
│   │         T2_PASS                         T2_FAIL                     │   │
│   │              │                               │                      │   │
│   │              │                               │ → VALIDATION_FALLBACK│   │
│   │              ▼                               │    (RETRY up to 2x)  │   │
│   │         Continue to T3                       │                      │   │
│   │                                                                     │   │
│   └─────────────────────────────────────────────────────────────────────┘   │
│                                  │                                          │
│   ═══════════════════════════════════════════════════════════════════════   │
│                         TIER 3: SEMANTIC (REPAIR)                           │
│   ═══════════════════════════════════════════════════════════════════════   │
│                                  │                                          │
│                                  ▼                                          │
│   ┌─────────────────────────────────────────────────────────────────────┐   │
│   │                    TIER3_SEMANTIC                                   │   │
│   │               "Business Rules + Hallucination (REPAIR)"             │   │
│   │                                                                     │   │
│   │   Validation Steps:                                                 │   │
│   │   ┌───────────────────────────────────────────────────────────────┐ │   │
│   │   │                                                               │ │   │
│   │   │   1. HALLUCINATION CHECK:                                     │ │   │
│   │   │      → Delegate to HALLUCINATION_DETECTOR                     │ │   │
│   │   │      Cross-reference facts with SessionState                  │ │   │
│   │   │                                                               │ │   │
│   │   │   2. BUSINESS RULES:                                          │ │   │
│   │   │      - response_text length: 10-2000 chars                    │ │   │
│   │   │      - next_actions: max 5 items                              │ │   │
│   │   │      - No PII in response unless explicitly allowed           │ │   │
│   │   │      - Tone matches emotional context                         │ │   │
│   │   │                                                               │ │   │
│   │   │   3. CONSISTENCY CHECK:                                       │ │   │
│   │   │      - Response consistent with tool_results                  │ │   │
│   │   │      - No contradictions with recent conversation             │ │   │
│   │   │                                                               │ │   │
│   │   └───────────────────────────────────────────────────────────────┘ │   │
│   │                              │                                      │   │
│   │              ┌───────────────┴───────────────┐                      │   │
│   │              │                               │                      │   │
│   │              ▼                               ▼                      │   │
│   │         T3_PASS                         T3_FAIL                     │   │
│   │              │                               │                      │   │
│   │              │                               │ → VALIDATION_FALLBACK│   │
│   │              ▼                               │    (REPAIR or WARN)  │   │
│   │         VALIDATED                            │                      │   │
│   │                                                                     │   │
│   └─────────────────────────────────────────────────────────────────────┘   │
│                                  │                                          │
│                                  ▼                                          │
│   ┌─────────────────────────────────────────────────────────────────────┐   │
│   │                    OUTPUT_VALIDATOR                                 │   │
│   │               "Return Validated Response"                           │   │
│   │                                                                     │   │
│   │   Wrap in FlatBuffer envelope:                                      │   │
│   │   ┌───────────────────────────────────────────────────────────────┐ │   │
│   │   │                                                               │ │   │
│   │   │   table ValidatedLLMOutput {                                  │ │   │
│   │   │     output_id: string;                                        │ │   │
│   │   │     agent_id: string;                                         │ │   │
│   │   │     timestamp_ms: int64;                                      │ │   │
│   │   │     status: SUCCESS;                                          │ │   │
│   │   │     confidence: 0.95;                                         │ │   │
│   │   │     validation_tier_reached: T3;                              │ │   │
│   │   │     hallucination_score: 0.02;                                │ │   │
│   │   │     payload: ConciergePayload { ... };                        │ │   │
│   │   │   }                                                           │ │   │
│   │   │                                                               │ │   │
│   │   └───────────────────────────────────────────────────────────────┘ │   │
│   │                                                                     │   │
│   └─────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
│   Result: Validated response returned to consumer via MODEL_ROUTER          │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

### F150: Schema Registry → Agent Schema Lookup Flow

**Trigger:** OUTPUT_VALIDATOR needs schema for validation
**Outcome:** Correct FlatBuffer schema retrieved for agent type

```
┌─────────────────────────────────────────────────────────────────────────────┐
│             F150: SCHEMA REGISTRY → AGENT SCHEMA LOOKUP FLOW                │
│                                                                             │
│   Component: SCHEMA_REGISTRY                                                │
│   Purpose: Map consumer/agent to correct FlatBuffer output schema           │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│   ┌─────────────────────────────────────────────────────────────────────┐   │
│   │                    OUTPUT_VALIDATOR                                 │   │
│   │                                                                     │   │
│   │   Request: lookup_schema(output_schema_id="concierge_payload")      │   │
│   │                              │                                      │   │
│   │                              │ schema_id                            │   │
│   │                              ▼                                      │   │
│   └─────────────────────────────────────────────────────────────────────┘   │
│                                  │                                          │
│                                  ▼                                          │
│   ┌─────────────────────────────────────────────────────────────────────┐   │
│   │                    SCHEMA_REGISTRY                                  │   │
│   │               "FlatBuffers Output Schemas"                          │   │
│   │                                                                     │   │
│   │   Schema Hierarchy:                                                 │   │
│   │   ┌───────────────────────────────────────────────────────────────┐ │   │
│   │   │                                                               │ │   │
│   │   │   CORE SCHEMAS (always loaded):                               │ │   │
│   │   │   ┌─────────────────────────────────────────────────────────┐ │ │   │
│   │   │   │                                                         │ │ │   │
│   │   │   │   llm_output (base)                                     │ │ │   │
│   │   │   │   ├── concierge_payload                                 │ │ │   │
│   │   │   │   ├── planner_payload                                   │ │ │   │
│   │   │   │   ├── memory_payload                                    │ │ │   │
│   │   │   │   ├── validator_payload                                 │ │ │   │
│   │   │   │   └── generic_payload (fallback)                        │ │ │   │
│   │   │   │                                                         │ │ │   │
│   │   │   └─────────────────────────────────────────────────────────┘ │ │   │
│   │   │                                                               │ │   │
│   │   │   AGENT SCHEMAS (loaded at spawn):                            │ │   │
│   │   │   ┌─────────────────────────────────────────────────────────┐ │ │   │
│   │   │   │                                                         │ │ │   │
│   │   │   │   health_payload (extends generic_payload)              │ │ │   │
│   │   │   │     - health_score: float                               │ │ │   │
│   │   │   │     - recommendations: [string]                         │ │ │   │
│   │   │   │     - metrics: HealthMetrics                            │ │ │   │
│   │   │   │                                                         │ │ │   │
│   │   │   │   finance_payload (extends generic_payload)             │ │ │   │
│   │   │   │     - budget_status: BudgetStatus                       │ │ │   │
│   │   │   │     - transactions: [Transaction]                       │ │ │   │
│   │   │   │     - insights: [string]                                │ │ │   │
│   │   │   │                                                         │ │ │   │
│   │   │   │   {dynamic}_payload (runtime registered)                │ │ │   │
│   │   │   │     - Uses generic_payload structure                    │ │ │   │
│   │   │   │     - key_values: [KeyValue]                            │ │ │   │
│   │   │   │     - schema_ref: string (for custom validation)        │ │ │   │
│   │   │   │                                                         │ │ │   │
│   │   │   └─────────────────────────────────────────────────────────┘ │ │   │
│   │   │                                                               │ │   │
│   │   └───────────────────────────────────────────────────────────────┘ │   │
│   │                              │                                      │   │
│   │   ┌───────────────────────────────────────────────────────────────┐ │   │
│   │   │              Lookup Algorithm                                 │ │   │
│   │   │                                                               │ │   │
│   │   │   1. Check exact match:                                       │ │   │
│   │   │      "concierge_payload" → FOUND in core schemas              │ │   │
│   │   │                                                               │ │   │
│   │   │   2. Check agent-specific:                                    │ │   │
│   │   │      "health_payload" → FOUND in agent schemas                │ │   │
│   │   │                                                               │ │   │
│   │   │   3. Fallback to generic:                                     │ │   │
│   │   │      "unknown_payload" → Use generic_payload                  │ │   │
│   │   │      (allows dynamic agents to work without custom schema)    │ │   │
│   │   │                                                               │ │   │
│   │   └───────────────────────────────────────────────────────────────┘ │   │
│   │                              │                                      │   │
│   │                              │ compiled_schema                      │   │
│   │                              ▼                                      │   │
│   └─────────────────────────────────────────────────────────────────────┘   │
│                                  │                                          │
│                                  ▼                                          │
│   ┌─────────────────────────────────────────────────────────────────────┐   │
│   │                    Schema File Structure                            │   │
│   │                                                                     │   │
│   │   k1/schemas/                                                       │   │
│   │   ├── core/                                                         │   │
│   │   │   ├── llm_output.fbs           # Base output schema             │   │
│   │   │   ├── concierge_payload.fbs    # Concierge-specific             │   │
│   │   │   ├── planner_payload.fbs      # Planner-specific               │   │
│   │   │   ├── memory_payload.fbs       # Memory writer-specific         │   │
│   │   │   └── generic_payload.fbs      # Fallback for dynamic agents    │   │
│   │   │                                                                 │   │
│   │   └── agents/                                                       │   │
│   │       ├── health/                                                   │   │
│   │       │   └── health_payload.fbs                                    │   │
│   │       ├── finance/                                                  │   │
│   │       │   └── finance_payload.fbs                                   │   │
│   │       └── {dynamic}/               # Runtime-added                  │   │
│   │           └── payload.fbs                                           │   │
│   │                                                                     │   │
│   └─────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
│   Result: Correct FlatBuffer schema for validation                          │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

### F151: Hallucination Detection → SessionState Cross-Reference Flow

**Trigger:** TIER3_SEMANTIC validation invokes hallucination check
**Outcome:** Facts in LLM response cross-referenced with SessionState

```
┌─────────────────────────────────────────────────────────────────────────────┐
│       F151: HALLUCINATION DETECTION → SESSIONSTATE CROSS-REFERENCE FLOW     │
│                                                                             │
│   Component: HALLUCINATION_DETECTOR                                         │
│   Purpose: Detect factual claims not supported by SessionState              │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│   ┌─────────────────────────────────────────────────────────────────────┐   │
│   │                    TIER3_SEMANTIC                                   │   │
│   │                                                                     │   │
│   │   LLM Response to check:                                            │   │
│   │   {                                                                 │   │
│   │     "response_text": "I've scheduled your dentist appointment       │   │
│   │                       for tomorrow at 3pm with Dr. Smith."          │   │
│   │   }                                                                 │   │
│   │                              │                                      │   │
│   │                              │ response + context                   │   │
│   │                              ▼                                      │   │
│   └─────────────────────────────────────────────────────────────────────┘   │
│                                  │                                          │
│                                  ▼                                          │
│   ┌─────────────────────────────────────────────────────────────────────┐   │
│   │                    HALLUCINATION_DETECTOR                           │   │
│   │               "Cross-ref SessionState"                              │   │
│   │                                                                     │   │
│   │   ┌───────────────────────────────────────────────────────────────┐ │   │
│   │   │              Detection Pipeline                               │ │   │
│   │   │                                                               │ │   │
│   │   │   1. EXTRACT CLAIMS:                                          │ │   │
│   │   │      Parse response for factual claims:                       │ │   │
│   │   │      - "dentist appointment" (event type)                     │ │   │
│   │   │      - "tomorrow at 3pm" (time claim)                         │ │   │
│   │   │      - "Dr. Smith" (entity claim)                             │ │   │
│   │   │                                                               │ │   │
│   │   │   2. QUERY SESSIONSTATE:                                      │ │   │
│   │   │      For each claim, check:                                   │ │   │
│   │   │      ┌─────────────────────────────────────────────────────┐  │ │   │
│   │   │      │                                                     │  │ │   │
│   │   │      │ BELIEFS_ACTIVE:                                     │  │ │   │
│   │   │      │   scheduled_event: {                                │  │ │   │
│   │   │      │     type: "dentist",                                │  │ │   │
│   │   │      │     time: "2024-01-16T15:00",                       │  │ │   │
│   │   │      │     provider: "Dr. Smith"                           │  │ │   │
│   │   │      │   }                                                 │  │ │   │
│   │   │      │   → MATCHES: event, time, provider ✓                │  │ │   │
│   │   │      │                                                     │  │ │   │
│   │   │      │ TOOL_RESULT_BUFFER:                                 │  │ │   │
│   │   │      │   calendar.schedule result confirms booking         │  │ │   │
│   │   │      │   → MATCHES: action was performed ✓                 │  │ │   │
│   │   │      │                                                     │  │ │   │
│   │   │      └─────────────────────────────────────────────────────┘  │ │   │
│   │   │                                                               │ │   │
│   │   │   3. SCORE HALLUCINATION:                                     │ │   │
│   │   │      claims_verified / total_claims                           │ │   │
│   │   │      3/3 = 1.0 → hallucination_score = 0.0 (none)             │ │   │
│   │   │                                                               │ │   │
│   │   │   4. FLAG UNVERIFIED:                                         │ │   │
│   │   │      If claim not found in SessionState:                      │ │   │
│   │   │      - Mark as POTENTIAL_HALLUCINATION                        │ │   │
│   │   │      - Check K0 (if claim might be historical)                │ │   │
│   │   │      - If still unverified: hallucination detected            │ │   │
│   │   │                                                               │ │   │
│   │   └───────────────────────────────────────────────────────────────┘ │   │
│   │                              │                                      │   │
│   │   ┌───────────────────────────────────────────────────────────────┐ │   │
│   │   │              Hallucination Categories                         │ │   │
│   │   │                                                               │ │   │
│   │   │   FACTUAL: Claims about events/data not in context            │ │   │
│   │   │   ENTITY: References to people/places not mentioned           │ │   │
│   │   │   TEMPORAL: Wrong dates/times                                 │ │   │
│   │   │   ATTRIBUTION: Incorrect source of information                │ │   │
│   │   │   CAPABILITY: Claims about actions not performed              │ │   │
│   │   │                                                               │ │   │
│   │   └───────────────────────────────────────────────────────────────┘ │   │
│   │                              │                                      │   │
│   │                              │ hallucination_score + details        │   │
│   │                              ▼                                      │   │
│   └─────────────────────────────────────────────────────────────────────┘   │
│                                  │                                          │
│                                  ▼                                          │
│   ┌─────────────────────────────────────────────────────────────────────┐   │
│   │                    Hallucination Response                           │   │
│   │                                                                     │   │
│   │   Score Thresholds:                                                 │   │
│   │   ┌───────────────────────────────────────────────────────────────┐ │   │
│   │   │                                                               │ │   │
│   │   │   0.0 - 0.1: CLEAN       → Pass validation                    │ │   │
│   │   │   0.1 - 0.3: LOW         → Warn, pass with flag               │ │   │
│   │   │   0.3 - 0.5: MODERATE    → Attempt REPAIR                     │ │   │
│   │   │   0.5 - 1.0: HIGH        → Trigger VALIDATION_FALLBACK        │ │   │
│   │   │                                                               │ │   │
│   │   └───────────────────────────────────────────────────────────────┘ │   │
│   │                                                                     │   │
│   └─────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
│   Result: Hallucination score returned to TIER3_SEMANTIC                    │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

### F152: Validation Fallback → Retry/Repair/Reject Flow

**Trigger:** Any validation tier fails
**Outcome:** Appropriate fallback action taken based on failure tier

```
┌─────────────────────────────────────────────────────────────────────────────┐
│            F152: VALIDATION FALLBACK → RETRY/REPAIR/REJECT FLOW             │
│                                                                             │
│   Component: VALIDATION_FALLBACK                                            │
│   Purpose: Handle validation failures with tiered recovery strategies       │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│   ┌─────────────────────────────────────────────────────────────────────┐   │
│   │                    Validation Failure                               │   │
│   │                                                                     │   │
│   │   Failure Context:                                                  │   │
│   │   {                                                                 │   │
│   │     tier: "T2" | "T3",                                              │   │
│   │     failure_reason: "missing_field" | "hallucination" | ...,        │   │
│   │     retry_count: 0,                                                 │   │
│   │     original_request: LLMRequest,                                   │   │
│   │     failed_response: raw_output                                     │   │
│   │   }                                                                 │   │
│   │                              │                                      │   │
│   │                              │ failure_context                      │   │
│   │                              ▼                                      │   │
│   └─────────────────────────────────────────────────────────────────────┘   │
│                                  │                                          │
│                                  ▼                                          │
│   ┌─────────────────────────────────────────────────────────────────────┐   │
│   │                    VALIDATION_FALLBACK                              │   │
│   │               "Retry → Repair → Reject"                             │   │
│   │                                                                     │   │
│   │   ┌───────────────────────────────────────────────────────────────┐ │   │
│   │   │              Strategy Selection                               │ │   │
│   │   │                                                               │ │   │
│   │   │   T1 (Structural) Failure:                                    │ │   │
│   │   │   ┌─────────────────────────────────────────────────────────┐ │ │   │
│   │   │   │ Action: IMMEDIATE REJECT                                │ │ │   │
│   │   │   │ Reason: LLM didn't return valid JSON/structure          │ │ │   │
│   │   │   │ Recovery: Not possible without re-prompt                │ │ │   │
│   │   │   │                                                         │ │ │   │
│   │   │   │ Response to consumer:                                   │ │ │   │
│   │   │   │ {                                                       │ │ │   │
│   │   │   │   status: ERROR,                                        │ │ │   │
│   │   │   │   error_code: "STRUCTURAL_VALIDATION_FAILED",           │ │ │   │
│   │   │   │   fallback_response: generic_error_message              │ │ │   │
│   │   │   │ }                                                       │ │ │   │
│   │   │   └─────────────────────────────────────────────────────────┘ │ │   │
│   │   │                                                               │ │   │
│   │   │   T2 (Schema) Failure:                                        │ │   │
│   │   │   ┌─────────────────────────────────────────────────────────┐ │ │   │
│   │   │   │ Action: RETRY (max 2 attempts)                          │ │ │   │
│   │   │   │ Reason: Missing/wrong fields, recoverable               │ │ │   │
│   │   │   │                                                         │ │ │   │
│   │   │   │ Retry Strategy:                                         │ │ │   │
│   │   │   │ 1. Append schema hint to prompt:                        │ │ │   │
│   │   │   │    "Your response was missing 'tone' field.             │ │ │   │
│   │   │   │     Required format: {response_text, tone, ...}"        │ │ │   │
│   │   │   │                                                         │ │ │   │
│   │   │   │ 2. Increase temperature slightly (creativity)           │ │ │   │
│   │   │   │                                                         │ │ │   │
│   │   │   │ 3. Re-submit to PROMPT_COMPILER                         │ │ │   │
│   │   │   │                                                         │ │ │   │
│   │   │   │ If retry_count >= 2: → REJECT                           │ │ │   │
│   │   │   └─────────────────────────────────────────────────────────┘ │ │   │
│   │   │                                                               │ │   │
│   │   │   T3 (Semantic) Failure:                                      │ │   │
│   │   │   ┌─────────────────────────────────────────────────────────┐ │ │   │
│   │   │   │ Action: REPAIR or WARN                                  │ │ │   │
│   │   │   │ Reason: Hallucination, rule violation, repairable       │ │ │   │
│   │   │   │                                                         │ │ │   │
│   │   │   │ Repair Strategies:                                      │ │ │   │
│   │   │   │                                                         │ │ │   │
│   │   │   │ HALLUCINATION (score 0.3-0.5):                          │ │ │   │
│   │   │   │   → Remove unverified claims from response              │ │ │   │
│   │   │   │   → Add disclaimer: "Based on available information..." │ │ │   │
│   │   │   │                                                         │ │ │   │
│   │   │   │ RULE_VIOLATION:                                         │ │ │   │
│   │   │   │   → Truncate if too long                                │ │ │   │
│   │   │   │   → Redact PII if detected                              │ │ │   │
│   │   │   │   → Adjust tone if mismatch                             │ │ │   │
│   │   │   │                                                         │ │ │   │
│   │   │   │ INCONSISTENCY:                                          │ │ │   │
│   │   │   │   → Flag for manual review                              │ │ │   │
│   │   │   │   → Pass with warning metadata                          │ │ │   │
│   │   │   │                                                         │ │ │   │
│   │   │   │ If repair fails or score > 0.5: → RETRY (once)          │ │ │   │
│   │   │   └─────────────────────────────────────────────────────────┘ │ │   │
│   │   │                                                               │ │   │
│   │   └───────────────────────────────────────────────────────────────┘ │   │
│   │                              │                                      │   │
│   │              ┌───────────────┼───────────────┐                      │   │
│   │              │               │               │                      │   │
│   │              ▼               ▼               ▼                      │   │
│   │          RETRY           REPAIR          REJECT                     │   │
│   │              │               │               │                      │   │
│   │              ▼               ▼               ▼                      │   │
│   │    PROMPT_COMPILER    OUTPUT_VALIDATOR  MODEL_METRICS              │   │
│   │    (with hints)       (modified resp)   (log failure)              │   │
│   │                                                                     │   │
│   └─────────────────────────────────────────────────────────────────────┘   │
│                                  │                                          │
│   ┌─────────────────────────────────────────────────────────────────────┐   │
│   │                    Metrics & Observability                          │   │
│   │                                                                     │   │
│   │   Events emitted:                                                   │   │
│   │   - k1.llm.validation.retry.v1                                      │   │
│   │   - k1.llm.validation.repair.v1                                     │   │
│   │   - k1.llm.validation.reject.v1                                     │   │
│   │                                                                     │   │
│   │   Metrics tracked:                                                  │   │
│   │   - validation_failures_by_tier (counter)                           │   │
│   │   - validation_retry_success_rate (gauge)                           │   │
│   │   - hallucination_scores (histogram)                                │   │
│   │                                                                     │   │
│   └─────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
│   Result: Failed response handled appropriately per failure type            │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

### F153: Dynamic Agent Schema Registration Flow

**Trigger:** AGENT_FACTORY spawns agent with custom output schema
**Outcome:** Agent's FlatBuffer schema compiled and registered

```
┌─────────────────────────────────────────────────────────────────────────────┐
│             F153: DYNAMIC AGENT SCHEMA REGISTRATION FLOW                    │
│                                                                             │
│   Component: SCHEMA_COMPILER → SCHEMA_REGISTRY                              │
│   Purpose: Register agent-specific output schemas at spawn time             │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│   ┌─────────────────────────────────────────────────────────────────────┐   │
│   │                    AGENT_FACTORY                                    │   │
│   │                                                                     │   │
│   │   Agent Template:                                                   │   │
│   │   # k1/contracts/agents/health_agent.yaml                           │   │
│   │   output_schema: health_payload                                     │   │
│   │   schema_path: k1/schemas/agents/health/health_payload.fbs          │   │
│   │                              │                                      │   │
│   │                              │ schema_reference                     │   │
│   │                              ▼                                      │   │
│   └─────────────────────────────────────────────────────────────────────┘   │
│                                  │                                          │
│                                  ▼                                          │
│   ┌─────────────────────────────────────────────────────────────────────┐   │
│   │                    SCHEMA_COMPILER                                  │   │
│   │               "Agent Template → FlatBuffer Schema"                  │   │
│   │                                                                     │   │
│   │   ┌───────────────────────────────────────────────────────────────┐ │   │
│   │   │              Compilation Process                              │ │   │
│   │   │                                                               │ │   │
│   │   │   1. LOAD SCHEMA FILE:                                        │ │   │
│   │   │      Read k1/schemas/agents/health/health_payload.fbs         │ │   │
│   │   │                                                               │ │   │
│   │   │   2. PARSE FLATBUFFER IDL:                                    │ │   │
│   │   │      ┌─────────────────────────────────────────────────────┐  │ │   │
│   │   │      │ // health_payload.fbs                               │  │ │   │
│   │   │      │ include "core/llm_output.fbs";                      │  │ │   │
│   │   │      │                                                     │  │ │   │
│   │   │      │ namespace k1.agents.health;                         │  │ │   │
│   │   │      │                                                     │  │ │   │
│   │   │      │ table HealthMetrics {                               │  │ │   │
│   │   │      │   steps: int32;                                     │  │ │   │
│   │   │      │   calories: int32;                                  │  │ │   │
│   │   │      │   sleep_hours: float;                               │  │ │   │
│   │   │      │ }                                                   │  │ │   │
│   │   │      │                                                     │  │ │   │
│   │   │      │ table HealthPayload {                               │  │ │   │
│   │   │      │   health_score: float;        // 0.0-1.0            │  │ │   │
│   │   │      │   recommendations: [string];                        │  │ │   │
│   │   │      │   metrics: HealthMetrics;                           │  │ │   │
│   │   │      │   analysis_summary: string;                         │  │ │   │
│   │   │      │ }                                                   │  │ │   │
│   │   │      │                                                     │  │ │   │
│   │   │      │ root_type HealthPayload;                            │  │ │   │
│   │   │      └─────────────────────────────────────────────────────┘  │ │   │
│   │   │                                                               │ │   │
│   │   │   3. VALIDATE INHERITANCE:                                    │ │   │
│   │   │      Ensure schema includes llm_output.fbs base               │ │   │
│   │   │      Check all required base fields present                   │ │   │
│   │   │                                                               │ │   │
│   │   │   4. COMPILE TO BINARY:                                       │ │   │
│   │   │      flatc --binary health_payload.fbs                        │ │   │
│   │   │      → Generate compiled schema for fast validation           │ │   │
│   │   │                                                               │ │   │
│   │   └───────────────────────────────────────────────────────────────┘ │   │
│   │                              │                                      │   │
│   │                              │ compiled_schema                      │   │
│   │                              ▼                                      │   │
│   └─────────────────────────────────────────────────────────────────────┘   │
│                                  │                                          │
│                                  ▼                                          │
│   ┌─────────────────────────────────────────────────────────────────────┐   │
│   │                    SCHEMA_REGISTRY                                  │   │
│   │                                                                     │   │
│   │   Registration:                                                     │   │
│   │   ┌───────────────────────────────────────────────────────────────┐ │   │
│   │   │                                                               │ │   │
│   │   │   schema_registry.register(                                   │ │   │
│   │   │     id = "health_payload",                                    │ │   │
│   │   │     version = "1.2.0",                                        │ │   │
│   │   │     compiled = <binary>,                                      │ │   │
│   │   │     source_path = "k1/schemas/agents/health/...",             │ │   │
│   │   │     extends = "generic_payload",                              │ │   │
│   │   │     agent_templates = ["health_agent"]                        │ │   │
│   │   │   )                                                           │ │   │
│   │   │                                                               │ │   │
│   │   └───────────────────────────────────────────────────────────────┘ │   │
│   │                                                                     │   │
│   │   For truly dynamic agents (no pre-defined schema):                 │   │
│   │   ┌───────────────────────────────────────────────────────────────┐ │   │
│   │   │                                                               │ │   │
│   │   │   Uses GENERIC_PAYLOAD_SCHEMA with runtime validation:        │ │   │
│   │   │                                                               │ │   │
│   │   │   table GenericPayload {                                      │ │   │
│   │   │     key_values: [KeyValue];  // Flexible structure            │ │   │
│   │   │     raw_json: string;        // Unparsed JSON fallback        │ │   │
│   │   │     schema_ref: string;      // Optional custom validator     │ │   │
│   │   │   }                                                           │ │   │
│   │   │                                                               │ │   │
│   │   │   This allows ANY dynamic agent to work without               │ │   │
│   │   │   pre-registered schema, with graceful degradation            │ │   │
│   │   │                                                               │ │   │
│   │   └───────────────────────────────────────────────────────────────┘ │   │
│   │                                                                     │   │
│   └─────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
│   Result: Agent schema registered, ready for output validation              │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

### F154: Core vs Generic Payload Schema Selection Flow

**Trigger:** OUTPUT_VALIDATOR needs to determine which schema to apply
**Outcome:** Correct schema selected based on consumer type

```
┌─────────────────────────────────────────────────────────────────────────────┐
│          F154: CORE VS GENERIC PAYLOAD SCHEMA SELECTION FLOW                │
│                                                                             │
│   Component: OUTPUT_VALIDATOR + SCHEMA_REGISTRY                             │
│   Purpose: Select appropriate schema for core vs dynamic agents             │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│   ┌─────────────────────────────────────────────────────────────────────┐   │
│   │                    OUTPUT_VALIDATOR                                 │   │
│   │                                                                     │   │
│   │   Request Context:                                                  │   │
│   │   {                                                                 │   │
│   │     consumer_id: "health_abc123",  // or "concierge"                │   │
│   │     output_schema_id: "health_payload",  // or "concierge_payload"  │   │
│   │   }                                                                 │   │
│   │                              │                                      │   │
│   │                              │ schema_lookup_request                │   │
│   │                              ▼                                      │   │
│   └─────────────────────────────────────────────────────────────────────┘   │
│                                  │                                          │
│                                  ▼                                          │
│   ┌─────────────────────────────────────────────────────────────────────┐   │
│   │                    SCHEMA_REGISTRY                                  │   │
│   │               "Schema Selection Logic"                              │   │
│   │                                                                     │   │
│   │   ┌───────────────────────────────────────────────────────────────┐ │   │
│   │   │              Selection Algorithm                              │ │   │
│   │   │                                                               │ │   │
│   │   │   Step 1: CHECK CORE SCHEMAS                                  │ │   │
│   │   │   ┌─────────────────────────────────────────────────────────┐ │ │   │
│   │   │   │                                                         │ │ │   │
│   │   │   │   Core Consumer IDs:                                    │ │ │   │
│   │   │   │   - "concierge" → concierge_payload                     │ │ │   │
│   │   │   │   - "planner" → planner_payload                         │ │ │   │
│   │   │   │   - "memory_writer" → memory_payload                    │ │ │   │
│   │   │   │   - "validator" → validator_payload                     │ │ │   │
│   │   │   │   - "proactive" → proactive_payload                     │ │ │   │
│   │   │   │                                                         │ │ │   │
│   │   │   │   If consumer_id in core_consumers:                     │ │ │   │
│   │   │   │     → Return core schema (strict validation)            │ │ │   │
│   │   │   │                                                         │ │ │   │
│   │   │   └─────────────────────────────────────────────────────────┘ │ │   │
│   │   │                                                               │ │   │
│   │   │   Step 2: CHECK AGENT-SPECIFIC SCHEMAS                        │ │   │
│   │   │   ┌─────────────────────────────────────────────────────────┐ │ │   │
│   │   │   │                                                         │ │ │   │
│   │   │   │   If output_schema_id registered in agent schemas:      │ │ │   │
│   │   │   │     "health_payload" → found in registry                │ │ │   │
│   │   │   │     → Return agent-specific schema                      │ │ │   │
│   │   │   │                                                         │ │ │   │
│   │   │   │   Agent schemas inherit from generic_payload            │ │ │   │
│   │   │   │   and add domain-specific fields                        │ │ │   │
│   │   │   │                                                         │ │ │   │
│   │   │   └─────────────────────────────────────────────────────────┘ │ │   │
│   │   │                                                               │ │   │
│   │   │   Step 3: FALLBACK TO GENERIC                                 │ │   │
│   │   │   ┌─────────────────────────────────────────────────────────┐ │ │   │
│   │   │   │                                                         │ │ │   │
│   │   │   │   If schema_id not found:                               │ │ │   │
│   │   │   │     "unknown_agent_payload" → not registered            │ │ │   │
│   │   │   │     → Return generic_payload                            │ │ │   │
│   │   │   │                                                         │ │ │   │
│   │   │   │   Generic schema accepts:                               │ │ │   │
│   │   │   │   - key_values: [KeyValue]                              │ │ │   │
│   │   │   │   - raw_json: string                                    │ │ │   │
│   │   │   │   - schema_ref: string (for future validation)          │ │ │   │
│   │   │   │                                                         │ │ │   │
│   │   │   │   This ensures NEW agents can work immediately          │ │ │   │
│   │   │   │   even without pre-registered schemas                   │ │ │   │
│   │   │   │                                                         │ │ │   │
│   │   │   └─────────────────────────────────────────────────────────┘ │ │   │
│   │   │                                                               │ │   │
│   │   └───────────────────────────────────────────────────────────────┘ │   │
│   │                              │                                      │   │
│   │   ┌───────────────────────────────────────────────────────────────┐ │   │
│   │   │              Validation Strictness by Schema Type             │ │   │
│   │   │                                                               │ │   │
│   │   │   CORE SCHEMAS (strict):                                      │ │   │
│   │   │   - All fields validated                                      │ │   │
│   │   │   - T2 failure → RETRY                                        │ │   │
│   │   │   - T3 hallucination > 0.3 → REPAIR                           │ │   │
│   │   │                                                               │ │   │
│   │   │   AGENT SCHEMAS (moderate):                                   │ │   │
│   │   │   - Required fields validated                                 │ │   │
│   │   │   - Optional fields accepted if present                       │ │   │
│   │   │   - T2 failure → RETRY once                                   │ │   │
│   │   │                                                               │ │   │
│   │   │   GENERIC SCHEMA (permissive):                                │ │   │
│   │   │   - Basic structure only                                      │ │   │
│   │   │   - T2 failure → WARN but pass                                │ │   │
│   │   │   - raw_json accepted as fallback                             │ │   │
│   │   │                                                               │ │   │
│   │   └───────────────────────────────────────────────────────────────┘ │   │
│   │                              │                                      │   │
│   │                              │ selected_schema + strictness_level   │   │
│   │                              ▼                                      │   │
│   └─────────────────────────────────────────────────────────────────────┘   │
│                                  │                                          │
│                                  ▼                                          │
│   ┌─────────────────────────────────────────────────────────────────────┐   │
│   │                    TIER2_SCHEMA                                     │   │
│   │                                                                     │   │
│   │   Apply validation with selected schema and strictness level        │   │
│   │                                                                     │   │
│   └─────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
│   Result: Correct schema applied with appropriate strictness                │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## NOTES

<!-- Add clarification questions or notes here -->
