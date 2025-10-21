# K1 Intelligence Module - Comprehensive Dependency Map

**Status:** 🚧 SKELETON (Awaiting ADR Logic Population)
**Last Updated:** 2025-10-17
**Author:** K1 Architecture Team
**Next Phase:** Populate ADR/sub-ADR logic into each layer + External Systems Integration

---

## Table of Contents

1. [Architecture Overview](#architecture-overview)
2. [Layer 1: Input Processing](#layer-1-input-processing)
3. [Layer 2: Orchestration](#layer-2-orchestration)
4. [Layer 3: Execution](#layer-3-execution)
5. [Layer 4: Runtime Core](#layer-4-runtime-core)
6. [Layer 5: Infrastructure](#layer-5-infrastructure)
7. [Inter-Layer Dependencies](#inter-layer-dependencies)
8. [External Systems & Kernel Bridges](#external-systems--kernel-bridges)
9. [Performance Critical Paths](#performance-critical-paths)
10. [Future Population Roadmap](#future-population-roadmap)

---

## Architecture Overview

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                        USER INTERACTION LAYER                               │
│  (Voice, Text, Video, Sensors)                                              │
└──────────────────────────┬──────────────────────────────────────────────────┘
                           │
                           │ Input Stream
                           ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│  LAYER 1: INPUT PROCESSING (4 Modules)                                      │
│  Purpose: Multi-modal input perception & intent routing                     │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │ • stream_switch (VAD, ASR, vision, sensor)                          │   │
│  │ • operators (stream transformations)                                │   │
│  │ • intent_router (3-tier: regex → SLM → LLM)                        │   │
│  │ • meta_policy (proactivity, clarification)                         │   │
│  │                                                                     │   │
│  │ Imports: Layer 5 only (event_bus)                                  │   │
│  │ Exports: IntentDetected, UserInput events → Layer 5 bus            │   │
│  └─────────────────────────────────────────────────────────────────────┘   │
└──────────────────────────┬──────────────────────────────────────────────────┘
                           │
                           │ Events (L5 Event Bus)
                           ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│  LAYER 2: ORCHESTRATION (3 Modules)                                         │
│  Purpose: Multi-agent coordination & plan generation                        │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │ • planner (4-stage: sketch → expand → validate → commit)           │   │
│  │ • orchestrator (3-phase: negotiation → selection → execution)      │   │
│  │ • protocol_monitor (MPST/Scribble validation)                      │   │
│  │                                                                     │   │
│  │ Imports: Layers 1, 3, 4, 5 (full visibility)                      │   │
│  │ Exports: Plan definitions, Agent hire requests → Layer 3           │   │
│  └─────────────────────────────────────────────────────────────────────┘   │
└──────────────────────────┬──────────────────────────────────────────────────┘
                           │
                           │ Plan Execution + Agent Hire
                           ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│  LAYER 3: EXECUTION (22 Modules)                                            │
│  Purpose: Agent lifecycle, AI integration (Model Hub), tool execution       │
│  ┌──────────────────────────────────────────────────────────────────────┐  │
│  │ AGENT LIFECYCLE (6 modules):                                        │  │
│  │ • registry, hire_fire, supervisor, personality, mailbox, roster    │  │
│  │                                                                     │  │
│  │ MODEL HUB - AI INTEGRATION (7 modules):                            │  │
│  │ • router, placement_planner, adapters, kv_cache_broker            │  │
│  │ • prompt_library, fallback_cascade, safety_filter                 │  │
│  │ [ONLY 4 AI AGENTS use Model Hub: Concierge, Planner, Researcher]  │  │
│  │                                                                     │  │
│  │ TOOL EXECUTION (5 modules):                                        │  │
│  │ • runner, sandbox, registry, adapters, control                    │  │
│  │                                                                     │  │
│  │ DIALOGUE MANAGEMENT (4 modules):                                   │  │
│  │ • scoreboard, state_tracker, turn_manager, repair                 │  │
│  │                                                                     │  │
│  │ Imports: Layers 4, 5 (runtime + infrastructure)                   │  │
│  │ Exports: Agent status, tool results → Layer 4 (state)             │  │
│  └──────────────────────────────────────────────────────────────────────┘  │
└──────────────────────────┬──────────────────────────────────────────────────┘
                           │
                           │ State Updates, Learning Signals
                           ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│  LAYER 4: RUNTIME CORE (8 Modules)                                          │
│  Purpose: State management, flow execution, adaptive learning               │
│  ┌──────────────────────────────────────────────────────────────────────┐  │
│  │ RUNTIME (4 modules):                                                │  │
│  │ • leases (capability/lease management)                              │  │
│  │ • mailbox (per-agent MPSC queues)                                   │  │
│  │ • session_state (6-section in-memory state)                         │  │
│  │ • flow_engine (deterministic DSL executor)                          │  │
│  │                                                                     │  │
│  │ LEARNING (4 modules):                                              │  │
│  │ • learning_loop (feedback integration, drift detection)             │  │
│  │ • feedback_collector (explicit/implicit/behavioral signals)        │  │
│  │ • drift_detector (performance degradation detection)                │  │
│  │ • model_updater (weight/ranking updates)                            │  │
│  │                                                                     │  │
│  │ Imports: Layer 5 (infrastructure + config)                         │  │
│  │ Exports: Updated weights, config changes → Layer 5                 │  │
│  └──────────────────────────────────────────────────────────────────────┘  │
└──────────────────────────┬──────────────────────────────────────────────────┘
                           │
                           │ Config Updates, Metrics, Logs
                           ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│  LAYER 5: INFRASTRUCTURE (19 Modules)                                       │
│  Purpose: Scheduling, observability, configuration, resource management    │
│  ┌──────────────────────────────────────────────────────────────────────┐  │
│  │ INFRASTRUCTURE (7 modules):                                          │  │
│  │ • scheduler (WFQ task scheduling, 4-tier priority)                  │  │
│  │ • backpressure (flow control, cascade)                              │  │
│  │ • thermal (NPU/GPU/CPU temp, placement decisions)                   │  │
│  │ • budgets (token, dollar, compute ms, latency)                      │  │
│  │ • cache (KV cache 128MB, prompt cache 64MB)                         │  │
│  │ • rate_limiting (token bucket per-intent)                           │  │
│  │ • storage_connector (persistence abstraction)                       │  │
│  │                                                                     │  │
│  │ SAFETY & POLICY (3 modules):                                        │  │
│  │ • policy (bands.yml, caps.yml, budgets.yml enforcement)            │  │
│  │ • pii_detector (regex, redaction markers)                           │  │
│  │ • arbiter (RED band human-in-loop decisions)                        │  │
│  │                                                                     │  │
│  │ OBSERVABILITY (4 modules):                                          │  │
│  │ • tracing (cognitive_trace_id propagation, OpenTelemetry)          │  │
│  │ • metrics (Prometheus RED: counters, gauges, histograms)            │  │
│  │ • receipts (model, tool, protocol, state receipts)                  │  │
│  │ • perf_harness (synthetic load, benchmarks)                         │  │
│  │                                                                     │  │
│  │ CONFIGURATION (3 modules):                                          │  │
│  │ • global (agents.yml, models.yml, tools.yml, scheduler.yml)         │  │
│  │ • schemas (Pydantic schemas, FlatBuffers definitions)               │  │
│  │ • config_manager (hot reload, SSE listener, merger, validator)      │  │
│  │                                                                     │  │
│  │ CONNECTORS (2 modules):                                             │  │
│  │ • k0_bridge (K0 kernel communication, batching, compression)        │  │
│  │ • model_hub_client (internal Model Hub interface)                   │  │
│  │                                                                     │  │
│  │ Imports: NONE from other layers (foundation)                        │  │
│  │ Exports: All layers can import Layer 5                              │  │
│  └──────────────────────────────────────────────────────────────────────┘  │
└──────────────────────────┬──────────────────────────────────────────────────┘
                           │
                           │ K0 Bridge (Batching, Compression)
                           ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                        K0 KERNEL (External)                                 │
│  Purpose: Persistent storage, distributed coordination, K0 specifics       │
│  • State persistence (session recovery, audit logs)                         │
│  • Distributed coordination (multi-instance K1 sessions)                    │
│  • K0-specific bridging logic                                              │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## Layer 1: Input Processing

### Module Inventory

| Module | File Path | Status | Dependencies | Exports | ADR Reference |
|--------|-----------|--------|--------------|---------|---|
| stream_switch | `k1/input/stream_switch/` | 🚧 SKELETON | Layer 5 (event_bus) | InputStreamEvent | ADR-0056, ADR-0057 |
| operators | `k1/input/operators/` | 🚧 SKELETON | Layer 5 (metrics, logging) | StreamTransformedEvent | ADR-0056a, ADR-0056b |
| intent_router | `k1/input/intent_router/` | 🚧 SKELETON | Layer 5 (event_bus) | IntentDetectedEvent | ADR-0058, ADR-0058a |
| meta_policy | `k1/input/meta_policy/` | 🚧 SKELETON | Layer 5 (event_bus, policy) | ProactivityEvent, ClarificationEvent | ADR-0057c, ADR-0058b |

### Dependency Details

**stream_switch:**
- ✅ Imports: `k1.infrastructure.event_bus` (L5)
- ✅ Exports: `InputStreamEvent` → Layer 5 event bus (pub/sub via ADR-0004a)
- **ADRs:**
  - ADR-0056 (Voice pipeline implementation - 5-stage architecture)
  - ADR-0056a (ASR ingress - 20ms frames, 80ms ring buffer)
  - ADR-0057 (Voice-specific backpressure - frame dropping at 80% capacity)
- **Sub-modules:** VAD detection (Voice Activity Detection), frame buffering (ring buffer), stream routing
- **Performance Budget:** <5ms per stream event (from ADR-0024)
- **External Connections:**
  - ASR API: Google Cloud Speech, Azure Speech, OpenAI Whisper
  - VAD: Silero VAD, WebRTC VAD
  - Sensor APIs: IoT platforms, MQTT brokers
- **Layer Boundary:** L1 → L5 only ✅ (no L2/L3/L4 imports)

**operators:**
- ✅ Imports: `k1.infrastructure.metrics` (L5), `k1.infrastructure.logging` (L5)
- ✅ Exports: `StreamTransformedEvent` → event_bus (L5 pub/sub)
- **ADRs:**
  - ADR-0056a (ASR ingress - Whisper model, partial/final transcripts)
  - ADR-0056b (Intent bridge - preprocessing, disfluency removal)
  - ADR-0056d (TTS synthesis - VITS model, 16kHz PCM, SSML generator)
  - ADR-0056e (Audio output - codec selection, device capability negotiation)
- **Sub-modules:**
  - ASR transformer: Whisper streaming with partial results
  - TTS transformer: VITS synthesis with prosody controls
  - Vision transformer: MediaPipe, OpenCV for gesture/face detection
  - Sensor transformer: IMU, GPS, environmental data processing
- **Performance Budget:** <5ms per transformation (from ADR-0024)
- **Research:** Google Duplex (20ms frames), Amazon Alexa (2s silence), Apple Siri (partial results)
- **Layer Boundary:** L1 → L5 only ✅

**intent_router:**
- ✅ Imports: `k1.infrastructure.event_bus` (L5)
- ✅ Exports: `IntentDetectedEvent` → Layer 5 event bus (orchestrator subscribes on L2)
- **ADRs:**
  - ADR-0058 (Intent classification integration - voice path)
  - ADR-0058a (Confidence thresholds - 0.8 minimum threshold)
  - ADR-0058b (Safety hooks - privacy band validation, refusal carry-over)
  - ADR-0056b (Intent bridge - disfluency removal, phonetic matching)
- **3-Tier Classification Pipeline:**
  1. **Tier 1 (T1):** Regex patterns <1ms (fast exact matches)
  2. **Tier 2 (T2):** SLM (Small Language Model) 2-3ms (fuzzy matches)
  3. **Tier 3 (T3):** LLM <50ms (async fallback, NOT on hot path)
- **Voice-Specific Enhancements:**
  - ASR confidence integration (30% weight)
  - Phonetic fuzzy matching (homophones like "book a flight" vs "book a kite")
  - Disfluency removal (um, uh, stutters)
  - Multi-turn repair (clarification cascades for low confidence <0.8)
- **Performance Budget:** <50ms P95 total classification (from ADR-0024)
- **Safety:** Privacy band checks, refusal carry-over, cost confirmation for HIGH-risk actions
- **Layer Boundary:** L1 → L5 only ✅ (event_bus publishes to L2 orchestrator)

**meta_policy:**
- ✅ Imports: `k1.infrastructure.event_bus` (L5), `k1.infrastructure.policy` (L5)
- ✅ Exports: `ProactivityEvent`, `ClarificationEvent` → event_bus (L5 pub/sub)
- **ADRs:**
  - ADR-0057c (Barge-in preemption - detect intent switch, interrupt TTS <120ms)
  - ADR-0058b (Safety hooks - privacy band checks, clarification gates)
  - ADR-0057 (Voice-specific backpressure - guide when to degrade quality vs interrupt)
- **Sub-modules:**
  - **Proactivity scorer:** Determines when K1 should interrupt with suggestions/context
    - Based on: session history, task complexity, confidence levels
    - Timing: Proactive help ≤2s decision window
  - **Clarification trigger:** Detects missing context → `ClarificationEvent`
    - Low ASR confidence (<0.7) → ask user to repeat
    - Missing mandatory parameters → ask for details
    - Ambiguous reference resolution ("call John" → "which John?")
  - **Barge-in detector:** Detects new voice input during TTS
    - Integrates with ADR-0057c (preemption protocol)
    - Cancels current TTS, restarts pipeline (<120ms latency)
  - **Context analyzer:** Tracks conversation state
    - Belief tracking (user model, history)
    - Turn boundaries (explicit vs implicit)
- **Performance Budget:** <10ms decision latency (from ADR-0024)
- **Safety:** All policy checks validated against ADR-0032 bands (GREEN/AMBER/RED)
- **Layer Boundary:** L1 → L5 only ✅ (uses policy + event_bus from infrastructure)

### Layer 1 Inter-Module Communication

**Sequential Data Flow:**
```
Audio Input (Voice/Text/Sensors)
    │
    ▼
[stream_switch] - VAD + frame buffering
    │ InputStreamEvent
    ▼ (event_bus publish)
[operators] - ASR, TTS, vision transformations
    │ StreamTransformedEvent
    ▼ (event_bus publish)
[intent_router] - 3-tier classification (regex → SLM → LLM)
    │ IntentDetectedEvent
    ▼ (event_bus publish)
[meta_policy] - proactivity + clarification + barge-in
    │ ProactivityEvent, ClarificationEvent
    ▼ (event_bus publish)
event_bus (Layer 5 foundation)
    │
    ├─→ Layer 2 (orchestrator subscribes) → coordinates response
    └─→ Layer 4 (learning loop subscribes) → feedback signal collection
```

**Event Bus Communication (ADR-0004a):**
- ✅ L1 publishes: `InputStreamEvent`, `StreamTransformedEvent`, `IntentDetectedEvent`, `ProactivityEvent`, `ClarificationEvent`
- ✅ L2 subscribes: orchestrator waits for `IntentDetectedEvent` to trigger 3-phase coordination (ADR-0006)
- ✅ L4 subscribes: learning loop aggregates signals for drift detection (ADR-0059)
- ✅ Performance: Event delivery <10ms (ADR-0004a contract)
- ✅ No direct L1→L2/L3/L4 imports (strict layering via ADR-0004b)

**Layer 1 Batch Summary (BATCH 1 ✅ COMPLETED):**
- ✅ All 4 modules have ADR references (stream_switch, operators, intent_router, meta_policy)
- ✅ Primary ADRs: ADR-0056 (voice pipeline), ADR-0057 (voice backpressure), ADR-0058 (intent classification)
- ✅ Sub-ADRs: ADR-0056a, 0056b, 0056d, 0056e, 0057c, 0058a, 0058b (7 sub-ADRs)
- ✅ Performance budgets: <5ms stream, <50ms intent classification, <10ms meta-policy (ADR-0024)
- ✅ Layer boundary: L1 → L5 only (ADR-0004b validated)
- ✅ Event bus communication: 5 events published to L5 (ADR-0004a compliant)
- ✅ External systems: ASR APIs (Google/Azure/Whisper), VAD (Silero/WebRTC), TTS (VITS/ElevenLabs)
- ✅ Research citations: Google Duplex, Amazon Alexa, Apple Siri patterns documented

---

## Layer 2: Orchestration

### Module Inventory

| Module | File Path | Status | Dependencies | Exports | ADR Reference |
|--------|-----------|--------|--------------|---------|---|
| planner | `k1/orchestration/planner/` | ✅ SPECIFIED | Layers 1, 3, 4, 5 | FlowDef (validated plans) | ADR-0007, 0007a-0007d, 0001b, 0010, 0011, 0017 |
| orchestrator | `k1/orchestration/orchestrator/` | ✅ SPECIFIED | Layers 1, 3, 4, 5 | Agent hire requests, DAG execution | ADR-0006, 0006a-0006e, 0002, 0008, 0010, 0024 |
| protocol_monitor | `k1/orchestration/protocol_monitor/` | ✅ SPECIFIED | Layers 4, 5 | Protocol validation alerts | ADR-0003, 0003a-0003d, 0002, 0010 |

### Dependency Details

**planner (4-Stage AI Agent Planning Pipeline - ADR-0007)**

*One of 4 AI agents (uses Model Hub for Stage 1 LLM inference)*

**Imports:**
- ✅ `k1.infrastructure.event_bus` (L5) - receives planning requests
- ✅ `k1.runtime.session_state` (L4) - reads user context, beliefs for Stage 1 prompt
- ✅ `k1.execution.model_hub` (L3) - LLM inference in Stage 1 (Sketch)
- ✅ `k1.infrastructure.config` (L5) - tool registry (Stage 2), validation rules (Stage 3)
- ✅ `k1.infrastructure.metrics` (L5) - emit latency metrics per stage
- ✅ `k1.runtime.leases` (L4) - capability verification (Stage 3)
- ✅ ADR-0004b validates: L2 has full visibility (1, 3, 4, 5) ✅

**Exports:**
- ✅ `FlowDef` → `k1.runtime.session_state.current_flow` (L4) - validated plan stored
- ✅ `PLAN_COMMITTED` event → L5 event_bus (audit trail)
- ✅ `PLAN_VALIDATION_ERROR` event → L5 event_bus (observable failures)

**4-Stage Pipeline (Hybrid AI + Deterministic):**

1. **Stage 1: Sketch (LLM, Creative, 150-500ms) - ADR-0007a:**
   - **Trigger:** Receive `PlanRequest` from orchestrator (via mailbox)
   - **LLM Inference:** Call Model Hub with prompt template (plan_generation.jinja2)
   - **Prompt Engineering:**
     - System prompt: Role definition, constraints, output format
     - Few-shot examples: 5-10 examples for JSON structure learning
     - Tool listing: Available tools filtered by agent capabilities
     - Context summary: SessionState beliefs (user preferences, history)
     - Temperature: 0.3 for consistency
     - Response format: JSON schema with intent, steps, complexity
     - Max tokens: 800 (response)
   - **Output:** `PlanSketch` with {intent, steps[], complexity}
   - **Performance Budget:** 150-500ms P95 (includes LLM TTFT + E2E)
   - **Error Handling:** Retry with stricter constraints (temperature 0.0, max 2 retries)
   - **Research:** OpenAI Structured Outputs (2024), Chain-of-Thought (Wei 2022)

2. **Stage 2: Expand (Deterministic, Fast Lookup, <1ms) - ADR-0007b:**
   - **Input:** `PlanSketch` from Stage 1
   - **Registry Lookups:** Tool schemas + prompt templates
     - Tool Registry O(1) lookup: 50+ tools with schemas (schema_in, schema_out, latency_hint_ms, cost_hint_usd, band_required, caps_required)
     - Prompt Registry matching: Step description → PromptTemplate (fuzzy keyword matching)
   - **Metadata Enrichment:** Add to each step:
     - Tool schema (input/output structure)
     - Latency hints (P95 expected execution time)
     - Cost hints (LLM tokens + tool cost estimate)
     - Band required (GREEN/AMBER/RED privacy)
     - Capabilities required (for capability-based security)
   - **Unknown Tool Handling:** Log warning, continue expansion (Tier 1 validation will catch)
   - **Output:** `ExpandedPlan` with full metadata
   - **Performance Budget:** <1ms P95 (pure O(1) dictionary lookups)
   - **Metrics:** expansion_latency_ms, unknown_tools_total, prompt_match_success_rate
   - **Research:** Registry pattern (Gamma 1994), JSON Schema validation (2020)

3. **Stage 3: Validate (Two-Tier: Rules + Arbiter, <1ms or 50-100ms) - ADR-0007c:**

   **Tier 1 (Rule-Based, <1ms, Always Run):** 6 deterministic checks
   1. **Structural validation:** Plan has 1+ steps, step count ≤ 10, unique/sequential step IDs
   2. **Dependency validation:** No circular dependencies (DAG cycle detection via Kahn's algorithm O(V+E))
   3. **Capability validation:** Agent has required tools/caps (set intersection against agent.capabilities)
   4. **Budget validation:** Total latency ≤ session budget, total cost ≤ session budget
   5. **Band validation:** Highest step band ≤ session band (GREEN/AMBER/RED enforcement)
   6. **Schema validation:** Step inputs match tool schema_in (JSON Schema validation)

   **Tier 2 (LLM Arbiter, 50-100ms, AMBER/RED Only):** Safety-critical validation
   - **Invocation Condition:** Only for AMBER/RED band plans (child space, user age < 18, HIGH-risk actions)
   - **Agent:** Safety Watch agent (AI agent #4, uses Model Hub)
   - **Validation:** LLM-based safety check with Constitutional AI principles
   - **Arbiter Decision:** {safe: true/false, reason: string}
   - **Fallback:** Rejection not retriable (arbiter is authoritative)
   - **Performance Budget:** 50-100ms P95 (gpt-4o-mini or distilled model)
   - **Target:** >95% error detection rate (Tier 1), <15% arbiter invocation rate

   - **Output:** `ValidatedPlan` or `ValidationError`
   - **Research:** STRIPS planning (Fikes 1971), DAG cycle detection (Kahn 1962), Constitutional AI (Anthropic 2022)

4. **Stage 4: Commit (Deterministic, Persistence, <10ms) - ADR-0007d:**
   - **Input:** `ValidatedPlan` from Stage 3
   - **FlowDef Serialization:** Convert to FlatBuffers binary (low memory, fast)
   - **Schema:** FlatBuffers `flow_def.fbs` with:
     - flow_id, intent, steps[], complexity
     - Aggregate metadata: total_latency_hint_ms, total_cost_hint_usd, highest_band_required
     - Audit metadata: session_id, trace_id, space, created_at
     - Validation metadata: validation_errors[], arbiter_invoked, arbiter_reason
   - **K0 WAL Write:** Persist to K0 Write-Ahead Log (PLAN_COMMITTED topic) for durability
   - **SessionState Update:** Set current_flow field (marks plan as active)
   - **STATE_DELTA Emission:** Publish state change event (null → flow_id)
   - **Idempotency:** Use idempotency key (plan_hash + session_id) to prevent duplicate commits on retry
   - **Output:** Committed `FlowDef` ready for execution by orchestrator
   - **Performance Budget:** <10ms P95 (FlatBuffers serialize + K0 write)
   - **100% Durability:** All plans persisted to K0 WAL (no data loss on crash)
   - **Audit Trail:** All commits logged with trace_id for compliance

**Performance Budgets (from ADR-0024):**
- Stage 1 (Sketch): 150-500ms (LLM inference, TTFT dominant)
- Stage 2 (Expand): <1ms (deterministic lookups)
- Stage 3-Tier1 (Rules): <1ms (deterministic checks)
- Stage 3-Tier2 (Arbiter): 50-100ms (only for AMBER/RED, ~15% invocation)
- Stage 4 (Commit): <10ms (serialization + persistence)
- **Total E2E P95:** <2.5s (within E2E budget from ADR-0024)
- **Max plan complexity:** 12 steps per plan
- **Fallback retries:** 2 max (avoid latency spiral)

**Lifecycle (ADR-0005 Agent Lifecycle FSM):**
- WARMING state: Load Model Hub prompts (10ms) into memory
- ACTIVE state: LLM reasoning loop for sketch generation (Stage 1)
- Resource footprint: 150MB (model weights + KV cache)
- Location: Layer 2 (`k1/orchestration/planner/`) - Core kernel

**Safety Integration (ADR-0010, ADR-0032):**
- Planner validates capability constraints (Stage 3 Tier 1)
- Arbiter performs privacy band validation (Stage 3 Tier 2)
- All plans tagged with privacy band for downstream enforcement
- References: ADR-0010 (Capability-Based Security), ADR-0032 (Privacy Bands)

**Related ADRs:**
- ADR-0007 (Main 4-stage pipeline spec)
- ADR-0007a (Stage 1 prompt engineering)
- ADR-0007b (Stage 2 registry integration)
- ADR-0007c (Stage 3 validation 2-tier)
- ADR-0007d (Stage 4 K0 WAL integration)
- ADR-0001b (Model Hub architecture)
- ADR-0005 (Agent lifecycle FSM)
- ADR-0010 (Capability security)
- ADR-0011 (FlatBuffers serialization)
- ADR-0017 (SessionState design)
- ADR-0024 (Performance budgets)

---

**orchestrator (3-Phase Coordination Contract Net Protocol - ADR-0006)**

*Pure Actor: NO LLM calls, deterministic logic, coordinates 4 AI agents + 54 pure actors*

**Imports:**
- ✅ `k1.infrastructure.event_bus` (L5) - receives intent events from L1
- ✅ `k1.execution.registry` (L3) - agent capabilities, current load
- ✅ `k1.execution.hire_fire` (L3) - hire/release agents
- ✅ `k1.execution.mailbox` (L4) - send agent messages
- ✅ `k1.runtime.session_state` (L4) - read user context, plan
- ✅ `k1.infrastructure.metrics` (L5) - emit orchestration latency per phase
- ✅ `k1.infrastructure.thermal` (L5) - agent thermal status
- ✅ ADR-0004b validates: L2 has full visibility ✅

**Exports:**
- ✅ `HireRequest` → Layer 3 agent.registry (via mailbox/event_bus)
- ✅ `TaskAnnouncement` → Layer 3 agents (broadcast via event_bus or direct mailbox)
- ✅ Orchestration phase metrics → Layer 5 observability

**3-Phase Contract Net Coordination (Smith 1980):**

1. **Phase 1: Negotiation (Broadcast + Bidding, <50ms P95) - ADR-0006a:**
   - **Trigger:** Receive `IntentDetected` event from Layer 1 (via event_bus)
   - **Broadcast:** Send `TaskAnnouncement` to all ACTIVE agents (parallel, non-blocking)
   - **Proposal Collection:** Agents evaluate task → send `Proposal` with confidence/latency/cost estimates
   - **Bidding Window:** 50ms deadline (non-blocking MPSC mailbox, lock-free)
   - **Fallback Strategy (4-Tier):**
     1. **Hire Agent:** Select best proposal if ≥1 proposal received
     2. **Simplify Task:** If no proposals, decompose task → retry with simpler sub-tasks
     3. **Wait-Retry:** If still no proposals, wait 100ms → retry negotiation
     4. **Degrade Capabilities:** If still failing, reduce required capabilities → accept lower-quality agent
   - **Performance Budget:** <50ms P95 (deadline for proposal collection)
   - **Parallelism:** All agents evaluate concurrently (no bottleneck)
   - **Research:** Contract Net Protocol (Smith 1980), non-blocking queues (MPSC)

2. **Phase 2: Selection (Weighted Scoring, <5ms P95) - ADR-0006b:**
   - **Input:** Proposals from Phase 1 (confidence, latency, cost, parallelism, track_record, load)
   - **Scoring Formula (6-Factor Weighted):**
     ```
     score = (
       w_confidence * confidence +        # 10.0 weight
       w_latency * latency_score +        # 8.0 weight
       w_cost * cost_score +              # -5.0 weight (penalty)
       w_parallelism * parallel_bonus +   # 3.0 weight
       w_track_record * success_rate +    # 2.0 weight
       penalty_busy * load_penalty        # -4.0 weight
     )
     ```
   - **Normalization:** All factors scaled to 0-1 range (fair comparison)
   - **Tie-Breaking (4 Strategies):**
     1. `prefer_resident` - Choose agent already in memory
     2. `prefer_fast` - Choose agent with lowest latency
     3. `prefer_cheap` - Choose agent with lowest cost
     4. `random` - Fallback randomization
   - **Winner Selection:** Highest score wins (deterministic, reproducible)
   - **Explainability:** Log score breakdown per proposal for debugging
   - **Performance Budget:** <5ms P95 (O(N) scoring for N proposals, ~1ms per proposal)
   - **Determinism:** Same proposals → same winner (reproducibility)
   - **Research:** Multi-attribute decision making (MADM), Weighted Sum Model (WSM)

3. **Phase 3: Execution (DAG Parallel Waves, <2000ms P95) - ADR-0006c, ADR-0006d:**
   - **Input:** Plan from planner (validated FlowDef) + selected agent from Phase 2
   - **DAG Model:** Steps (nodes) + dependencies (edges)
   - **Wave Computation (Kahn's Algorithm 1962):**
     1. Compute in-degree for each step
     2. Identify steps with no dependencies → Wave 1
     3. Mark completed → decrement in-degrees
     4. Repeat → Waves 2, 3, ...
     5. Result: Independent steps grouped into parallel waves
   - **Parallel Execution:**
     ```
     Wave 1 (no deps) → asyncio.gather + semaphore (max 3 concurrent)
         ↓ (barrier: await all)
     Wave 2 (depends on Wave 1) → asyncio.gather
         ↓ (barrier: await all)
     ...
     Wave N → Final result
     ```
   - **Dependency Resolution:** Variable substitution {step.output} → step inputs
   - **Expected Speedup:** 2-3× faster than sequential (for multi-step plans)
   - **Straggler Handling:** Detect slow tasks, log warnings

   **Error Recovery (Saga Pattern - ADR-0006d, ADR-0008):**
   - Track compensation actions per step
   - On failure: Reverse-order compensation (LIFO stack unwinding)
   - Example:
     ```
     Step 1 ✅ (cancel_search compensation)
     Step 2 ✅ (cancel_reservation compensation)
     Step 3 ❌ FAILS
     Compensation: Step 2 → cancel_reservation, Step 1 → cancel_search
     ```
   - Best-effort recovery (continue even if one compensation fails)
   - Garcia-Molina & Salem 1987

   **Multi-Agent Coordination (Q2 2025 Post-MVP - ADR-0006e):**
   - Future optimization: Multiple agents execute different waves concurrently (specialization)
   - Currently: Single agent executes all waves sequentially

   - **Performance Budget:** <2000ms P95 (task-dependent execution latency)
   - **Total Orchestration Overhead:** Phase 1 + Phase 2 = <50ms + <5ms = <55ms
   - **Execution Latency:** Variable (task-dependent, agent-dependent)
   - **Total E2E (Intent → Result):** <2000ms P95 (includes all 3 phases)

**Deterministic Properties (Pure Actor):**
- ✅ No LLM calls (all phases deterministic logic)
- ✅ No Model Hub access (orchestrator does not reason with LLMs)
- ✅ Coordinates AI agents (planner, researcher, etc.) but doesn't use them internally
- ✅ Reproducible (same proposals → same execution)

**Related ADRs:**
- ADR-0006 (Main 3-phase spec)
- ADR-0006a (Phase 1 negotiation)
- ADR-0006b (Phase 2 scoring)
- ADR-0006c (Phase 3 DAG execution)
- ADR-0006d (Saga pattern integration)
- ADR-0006e (Multi-agent coordination - post-MVP)
- ADR-0002 (Actor model foundation)
- ADR-0002b (Supervisor pattern)
- ADR-0008 (Saga pattern references)
- ADR-0010 (Capability constraints)
- ADR-0024 (Performance budgets)

---

**protocol_monitor (MPST Protocol Validation - ADR-0003)**

*Pure Actor: Deterministic FSM validation, intercepts ALL Actor messages*

**Imports:**
- ✅ `k1.runtime.session_state` (L4) - session_id for FSM instance lookup
- ✅ `k1.infrastructure.metrics` (L5) - emit validation latency metrics
- ✅ `k1.infrastructure.logging` (L5) - audit trail for violations
- ✅ `k1.runtime.leases` (L4) - role attestation HMAC verification
- ✅ ADR-0004b validates: L2 has visibility to 4, 5 ✅

**Exports:**
- ✅ Protocol validation alerts → L5 observability (violations)
- ✅ Metrics: protocol_validation_latency_ms, protocol_violations_total
- ✅ DLQ messages → L5 for manual investigation

**Protocol Definition Language (PDL) - YAML Custom DSL (NOT Scribble) - ADR-0003a:**
- **Rationale:** Custom YAML DSL over Scribble for team readability (9/10 fit vs 4/10 Scribble)
- **Conversation-Native Primitives:** Clarification, barge-in, grounding as first-class
- **Compiler:** PDL → FlatBuffers FSM pre-compiled at startup (<100ms per protocol)
- **Deadlock Detection:** Static analysis at compile-time via Tarjan's algorithm
- **Timeout Policies:** Progress guarantees via auto-transition on expiry

**6 Core Protocols (27 States, 45 Transitions Total) - ADR-0003b:**

1. **Agent Hire Protocol** (6 states, 8 transitions):
   - Flow: start → negotiation → selection → hired/rejected/timeout
   - Timeout policy: 500ms negotiation window (message receipt deadline)
   - Violation: Message received outside window → block/warn

2. **Task Execution Protocol** (5 states, 10 transitions):
   - Flow: start → assigned → planning → approved → executing/rejected/timeout
   - LLM Awareness: Planner LLM timeout (5000ms internal) ≠ protocol timeout (500ms message receipt)
   - Violation: Executor sends result before approval → block

3. **Clarification Protocol** (4 states, 6 transitions):
   - Flow: start → clarification_needed → user_responded → resume/abort
   - Nested: Can interrupt task execution protocol
   - Violation: Multiple clarifications without user response → timeout

4. **Barge-In Protocol** (3 states, 5 transitions):
   - Flow: start → listening → interrupted/timeout
   - Interrupt: Pause current TTS/execution, receive new input
   - Violation: Barge-in during critical state (safety operations) → block

5. **Tool Call Protocol** (4 states, 7 transitions):
   - Flow: start → tool_requested → tool_validated → executed/rejected/timeout
   - Capability check: Tool requires capabilities → verified (ADR-0003d)
   - Violation: Agent calls tool without capability → block

6. **Saga Rollback Protocol** (5 states, 9 transitions):
   - Flow: start → compensating → compensating_step_n → rollback_complete/failed/timeout
   - LIFO order: Compensation in reverse step order
   - Violation: Out-of-order compensation → abort rollback

**Runtime Implementation (Pure Actor) - ADR-0003c:**

- **FSM Registry (Startup):**
  - Load 6 PDL protocols from FlatBuffers (pre-compiled binary)
  - Parse FSM tables: states, transitions, timeouts, guards, violations
  - Build O(1) lookup: state_id → State, transition_id → Transition
  - Validate: Reachability, acyclic (Tarjan's algorithm), deadlock-free
  - Metrics: k1_protocol_compilation_time_ms (histogram)

- **Session FSM Tracker (Runtime Per-Session):**
  - Hash table: session_id → FSMInstance
  - FSMInstance: {protocol_name, current_state, start_time, transition_log}
  - Concurrent access: RwLock (readers: validation, writer: state transition)
  - Metrics: k1_protocol_sessions_active (gauge)

- **Receive-Side Validation Hook (Mailbox Path):**
  1. Message arrives at mailbox (Actor message, NOT LLM call)
  2. Extract: session_id, sender_role, message_type
  3. Lookup: FSMInstance for session_id
  4. Validate: current_state + message_type → valid transition?
  5. Decision: PASS (deliver) or BLOCK (violation)
  6. Metrics: k1_protocol_validation_latency_ms (histogram)
  7. **Budget:** <5ms P95 (must not block mailbox delivery)

- **Violation Handler (6 Actions):**
  1. **BLOCK** (default): Drop message, log, metric `k1_protocol_violations_total[violation_type]`
  2. **WARN**: Deliver message, log warning, metric (rare, debug-only)
  3. **DLQ**: Send to Dead Letter Queue, log, metric (manual investigation)
  4. **REPAIR**: Auto-fix message (if possible), deliver, log (e.g., add missing field)
  5. **FALLBACK**: Trigger fallback state transition, deliver (e.g., timeout → error state)
  6. **ABORT**: Terminate protocol, cleanup FSM, log (unrecoverable error)

- **Timeout Enforcement (Progress Guarantees):**
  - Track state entry time
  - Auto-transition on timeout expiry (move to terminal state or fallback)
  - Metrics: `k1_protocol_timeouts_total[protocol_name, state]`

- **Protocol Composition (Multi-Protocol Support):**
  - Pause/resume: Clarification pauses task, resumes after
  - Interrupt/abort: Barge-in aborts task execution
  - Nested: Protocols stack (main + nested)

**Role Attestation & Capability Verification (ADR-0003d):**

- **Message Envelope Security:**
  - Every Actor message: {sender_role, sender_lease_id, signature}
  - Signature: HMAC-SHA256(message_type + session_id + payload, lease_secret)
  - Constant-time comparison (prevent timing attacks)

- **2-Phase Verification:**
  1. **Phase 1: Role Verification (<500μs):**
     - Lookup agent lease (O(1) hash table)
     - Validate: lease exists, not expired, matches sender_agent_id
     - Verify HMAC-SHA256 signature
  2. **Phase 2: Protocol FSM (<2ms):**
     - Validate current_state + message_type → valid transition
  3. **Total Overhead:** <3ms P95 (within <5ms mailbox budget)

- **Security Properties:**
  - No role spoofing (agents cannot impersonate other roles)
  - No privilege escalation (agents cannot send outside capabilities)
  - Least privilege (agents have minimal capabilities)
  - Lease expiry enforcement (zombie agents rejected)

**Performance Targets (from ADR-0024):**
- FSM state lookup: <1ms P95 (hash table O(1) access)
- Message validation: <2ms P95 (pre-compiled FSM)
- Mailbox hook overhead: <5ms P95 (must not block delivery)
- Role attestation: <3ms P95 total (HMAC + FSM)
- Protocol compilation: <100ms per protocol (startup only)

**Research Foundation:**
- MPST (Honda et al. 2008) - Multiparty session types, deadlock freedom
- Scribble (Yoshida et al. 2013) - MPST runtime monitors
- Custom PDL: YAML-based for readability + team adoption

**Related ADRs:**
- ADR-0003 (Main MPST spec, custom PDL rationale)
- ADR-0003a (PDL specification, YAML schema)
- ADR-0003b (6 protocols in PDL YAML)
- ADR-0003c (Runtime implementation)
- ADR-0003d (Role attestation, capability verification)
- ADR-0002 (Actor model foundation)
- ADR-0008 (Saga pattern - rollback protocol)
- ADR-0010 (Capability-based security)

### Layer 2 Inter-Module Communication

```
Layer 1 Events (event_bus, L5)
    │
    ├─→ IntentDetectedEvent
    │   │
    │   ▼
    │ orchestrator (Phase 1 Negotiation)
    │   │ TaskAnnouncement (broadcast)
    │   ▼
    │ protocol_monitor (Agent Hire Protocol validation) ◄─── ADR-0003b#1
    │   │ HireRequest → approved
    │   │
    │   ▼
    │ orchestrator (Phase 2 Selection)
    │   │ Weighted scoring (6-factor)
    │   │
    │   ▼
    │ orchestrator (Phase 3 Execution)
    │   │ DAG waves + dependency resolution
    │   │
    │   ├─→ planner (if plan not cached)
    │   │   ├─ Stage 1: Sketch (LLM)
    │   │   ├─ Stage 2: Expand (registry lookup)
    │   │   ├─ Stage 3: Validate (rules + arbiter)
    │   │   └─ Stage 4: Commit (K0 WAL)
    │   │
    │   └─→ Layer 3 (agent execution)
    │       │
    │       └─→ protocol_monitor (Task Execution Protocol) ◄─── ADR-0003b#2
    │           │ TaskAnnouncement → Planning → Approved → Executing
    │
    ▼
protocol_monitor (All 6 protocols)
    │ Validates per-message via FSM
    │ ├─ Agent Hire (ADR-0003b#1)
    │ ├─ Task Execution (ADR-0003b#2)
    │ ├─ Clarification (ADR-0003b#3)
    │ ├─ Barge-In (ADR-0003b#4)
    │ ├─ Tool Call (ADR-0003b#5)
    │ └─ Saga Rollback (ADR-0003b#6)
    │
    ├─→ metrics (L5) - validation latency, violations
    └─→ logging (L5) - audit trail
```

### Layer 2 Batch Summary (BATCH 2 ✅)

- ✅ All 3 modules specified with ADR logic: planner (4-stage), orchestrator (3-phase), protocol_monitor (6 protocols)
- ✅ Primary ADRs: ADR-0006 (orchestration), ADR-0007 (planning), ADR-0003 (protocol validation)
- ✅ Sub-ADRs (13 total): 0006a-0006e (5), 0007a-0007d (4), 0003a-0003d (4)
- ✅ Performance budgets linked: <80ms orchestration overhead, <2.5s planner total, <2ms protocol validation (ADR-0024)
- ✅ Layer boundary: L2 has full visibility (1, 3, 4, 5) per ADR-0004b ✅
- ✅ Event bus communication: IntentDetectedEvent → orchestrator → planner/Layer3 (ADR-0004a)
- ✅ Research citations: Contract Net (Smith 1980), MPST (Honda 2008), Saga (Garcia-Molina 1987), DAG (Kahn 1962)
- ✅ AI agent integration: Planner uses Model Hub (1 of 4 AI agents), orchestrator is pure actor (deterministic)
- ✅ Protocol validation: 27 states, 45 transitions across 6 protocols, custom PDL YAML (not Scribble)
- ✅ Role attestation: HMAC-SHA256 signature verification for all Actor messages (ADR-0003d)
- ✅ Cross-module flow: Orchestrator → Planner → Layer 3 (agent hire + execution)

---

## Layer 3: Execution

### Module Inventory (22 Modules)

#### 3a: Agent Lifecycle (6 modules) ✅ BATCH 3 COMPLETE

| Module | File Path | Status | Dependencies | ADR Reference |
|--------|-----------|--------|--------------|---|
| registry | `k1/execution/agents/registry/` | ✅ POPULATED | `k1.infrastructure.config` (L5) | ADR-0004 (52-module arch), ADR-0005 (Lifecycle FSM) |
| hire_fire | `k1/execution/agents/hire_fire/` | ✅ POPULATED | `k1.runtime.session_state` (L4), `k1.infrastructure.metrics` (L5) | ADR-0005 (6-state FSM: PENDING→WARMING→ACTIVE→IDLE→DRAINING→TERMINATED) |
| supervisor | `k1/execution/agents/supervisor/` | ✅ POPULATED | `k1.runtime.session_state` (L4), `k1.infrastructure.metrics` (L5) | ADR-0002b (Supervisor monitoring), ADR-0005c (Lifecycle supervision) |
| personality | `k1/execution/agents/personality/` | ✅ POPULATED | `k1.infrastructure.config` (L5) | ADR-0005e (Personality adaptation), ADR-0067 (Delight factors), ADR-0069 (Affect) |
| mailbox | `k1/execution/agents/mailbox/` | ✅ POPULATED | `k1.infrastructure.metrics` (L5) | ADR-0002a (Mailbox MPSC queue), pattern: Actor Model (Hewitt 1973) |
| active_roster | `k1/execution/agents/active_roster/` | ✅ POPULATED | `k1.infrastructure.metrics` (L5), `k1.runtime.session_state` (L4) | ADR-0005b (State transitions), ADR-0005d (Supervisor monitoring) |

**Agent Lifecycle Context (ADR-0005 + sub-ADRs 0005a-0005e):**

The 6-state FSM applies to **ALL 58 K1 agents** (4 AI agents + 54 pure actors):
- **AI Agents (4):** Concierge (L1), Planner (L2), Researcher (L3), Safety Watch (L3) — Use Model Hub for LLM reasoning
- **Pure Actors (54):** Orchestrator, Supervisor, Router, SessionState, etc. — Deterministic logic only

**1. registry (Agent Templates & Specs)**

```
PURPOSE: Central repository for agent specifications, templates, configurations

IMPORTS:
  → k1.infrastructure.config (L5) - Config file loading

EXPORTS:
  → Agent specs (templates, capabilities, resource limits)
  → Agent factory for hire_fire module

LOGIC (from ADR-0005, ADR-0004):
  1. Load agent specs from YAML configs (Layer 5)
  2. Store: {agent_id, agent_type (AI/pure), capabilities, personality, warmup_config}
  3. For AI agents: Load Model Hub config (which LLM, prompt templates)
  4. For pure actors: Load config templates (state machines, rule engines)
  5. Registry lookup: O(1) hash table by agent_type or agent_id
  6. Template instantiation: Clone spec → create new agent instance

ADR REFERENCES:
  - ADR-0005 (6-state FSM definition for all agents)
  - ADR-0004 (58-module architecture context)
  - ADR-0005e (Personality traits per agent)

PERFORMANCE:
  - Registry lookup: <1ms (O(1) hash table)
  - Template instantiation: <10ms

OBSERVABILITY:
  - gauge: k1_agent_registry_entries{agent_type} (AI vs pure count)
  - histogram: k1_agent_instantiation_ms
```

**2. hire_fire (Agent Lifecycle Transitions)**

```
PURPOSE: Execute state transitions in 6-state FSM

IMPORTS:
  → k1.runtime.session_state (L4) - Agent state persistence
  → k1.infrastructure.metrics (L5) - Emit transition metrics

EXPORTS:
  → State transition events
  → Agent lifecycle notifications

LOGIC (from ADR-0005: PENDING→WARMING→ACTIVE→IDLE→DRAINING→TERMINATED):

STATE TRANSITIONS:
  1. PENDING → WARMING: Orchestrator hires agent
     - Entry action: Start resource initialization
     - Budget: <200ms (pure actors), <600ms total hire → ACTIVE
     - Supervisor monitors: Warmup timeout enforced (5s max)

  2. WARMING → ACTIVE: Resources initialized, ready for tasks
     - AI agents: Model loaded, KV cache allocated, warmup inference complete (240ms avg)
     - Pure actors: Config loaded, mailbox initialized (20ms avg)
     - Entry action: Supervisor registration, mailbox ready
     - Exit guard: All resources must be initialized

  3. ACTIVE → IDLE: No tasks for idle_timeout (60s default)
     - Entry guard: Mailbox quiescent (200ms no messages)
     - Entry action: Release non-essential memory, keep model loaded
     - TTL countdown: 5 minutes in IDLE before auto-drain
     - Supervisor monitors: Reactivation speed <50ms

  4. IDLE → ACTIVE: New task assigned
     - Entry action: Resume message processing
     - Reactivation latency: <50ms (model already loaded)

  5. ACTIVE/IDLE → DRAINING: TTL expired, memory pressure, or FIRE message
     - Entry action: Reject new tasks, finish current work
     - MPST enforcement: Orchestrator stops sending `Assign` messages
     - Budget: <10s max draining duration
     - Action: Flush state to K0, revoke capabilities

  6. DRAINING → TERMINATED: Graceful shutdown complete
     - Entry action: Release all resources, close mailbox, delete from roster
     - Blacklist check: >3 crashes in 10min → blacklist 1 hour
     - Capabilities revoked: Prevent leaked handle abuse (revocation-on-crash)

ADR REFERENCES:
  - ADR-0005 (6-state FSM master definition)
  - ADR-0005a (AI agent WARMING: <250ms laptop, <500ms phone)
  - ADR-0005b (IDLE pooling: <50ms reactivation)
  - ADR-0005c (DRAINING graceful shutdown: <10s)
  - ADR-0005d (Supervisor monitoring & crash recovery)

PERFORMANCE TARGETS (from ADR-0024):
  - Transition overhead: <5ms per transition
  - WARMING: 240ms AI agents, 20ms pure actors
  - IDLE→ACTIVE reactivation: <50ms
  - DRAINING: <10s max (configurable)

OBSERVABILITY:
  - counter: k1_agent_transitions_total{from_state, to_state}
  - histogram: k1_agent_warmup_duration_ms{agent_type}
  - histogram: k1_agent_reactivation_ms
  - gauge: k1_agents_by_state{state} (PENDING/WARMING/ACTIVE/IDLE/DRAINING/TERMINATED)
```

**3. supervisor (Health Monitoring & Crash Recovery)**

```
PURPOSE: Monitor agent health, detect crashes, enforce blacklist

IMPORTS:
  → k1.runtime.session_state (L4) - Agent state tracking
  → k1.infrastructure.metrics (L5) - Emit health metrics

EXPORTS:
  → Health checks, escalations, crash notifications
  → Blacklist decisions

LOGIC (from ADR-0002b Supervisor, ADR-0005d Blacklist):

HEALTH MONITORING:
  1. Periodic health check: Every 1000ms (1 Hz, configurable)
     - Send heartbeat message to agent mailbox
     - Expect response within timeout window
  2. Crash detection: No response → agent declared dead
     - Record crash: timestamp, agent_id, error_context
     - Transition: ACTIVE → TERMINATED (emergency)
  3. Supervisor escalation chain:
     - Crash level 0-2: Log, recover, notify orchestrator
     - Crash level 3: Blacklist agent for 1 hour (3 crashes in 10min)
     - Crash level 4+: Escalate to session (multiple agent failures → session pause)

BLACKLIST POLICY:
  - Trigger: 3 crashes in 10-minute window
  - Duration: 1 hour
  - Effect: Agent cannot be hired (orchestrator receives rejection bid)
  - Rationale: Prevent thrashing (repeated hire/crash cycles)

LEASE REVOCATION (ADR-0005d Crash Recovery):
  - On TERMINATED (crash or graceful): Revoke all capabilities/leases
  - Add revocation-on-crash flag: Tool/model tokens/handles non-reusable post-crash
  - Defense: Prevents leaked handle exploitation

ADR REFERENCES:
  - ADR-0002b (Supervisor role, crash detection, one-for-one strategy)
  - ADR-0005d (Agent blacklist & recovery)
  - ADR-0010d (Capability revocation)

PERFORMANCE TARGETS (from ADR-0024):
  - Health check latency: <100ms per check (async)
  - Crash detection: <1.2s (1s interval + timeout window)
  - Supervisor overhead: <0.1% CPU (configurable check frequency)

OBSERVABILITY:
  - counter: k1_agent_crashes_total{agent_id, reason}
  - counter: k1_agent_blacklist_total{agent_id, reason}
  - gauge: k1_supervisor_health_checks_pending
  - histogram: k1_supervisor_heartbeat_response_ms
```

**4. personality (Agent Persona & Adaptation)**

```
PURPOSE: Manage agent personality traits, tone, adaptation to user preferences

IMPORTS:
  → k1.infrastructure.config (L5) - Personality templates

EXPORTS:
  → Persona prompts (for AI agents)
  → Tone/style settings (for all agents)

LOGIC (from ADR-0005e Personality, ADR-0067 Delight):

AI AGENT PERSONALITIES:
  1. Concierge: Professional, helpful, multilingual, culturally aware
  2. Planner: Efficient, detailed, safety-conscious (safety-first planning)
  3. Researcher: Thorough, evidence-based, precise citations
  4. Safety Watch: Cautious, privacy-aware, consistent with policies

PERSONA PROMPTS (stored in Model Hub per ADR-0030):
  - Each AI agent has persona prompt template: `system_prompt.jinja2`
  - Template includes: role, tone, capabilities, constraints, safety rules
  - Examples:
    * Concierge: "You are a professional concierge assistant..."
    * Planner: "You are a task planning expert. Prioritize safety and correctness..."
    * Safety Watch: "You are a content safety filter. Flag PII, toxic content, policy violations..."

TONE ADAPTATION (User Preference Learning):
  - Learn user tone preference: formal vs casual, brief vs detailed
  - Store in SessionState (user_profile band: GREEN)
  - Apply at runtime: Adjust prompt temperature/parameters

ADR REFERENCES:
  - ADR-0005e (Personality & capability system)
  - ADR-0067 (Delight factors - user satisfaction)
  - ADR-0069 (Affect modulation - emotional tone)

OBSERVABILITY:
  - gauge: k1_personality_profiles_loaded{agent_type}
  - counter: k1_personality_adaptations_applied{user_id}
```

**5. mailbox (MPSC Message Queue)**

```
PURPOSE: Actor Model message passing (lock-free MPSC queue)

IMPORTS:
  → k1.infrastructure.metrics (L5) - Queue metrics

EXPORTS:
  → Message delivery, mailbox status

LOGIC (from ADR-0002a Mailbox MPSC, Actor Model Hewitt 1973):

ARCHITECTURE:
  1. **Lock-Free MPSC Queue** (Multi-Producer Single-Consumer):
     - Senders enqueue messages without lock (atomic CAS operations)
     - Receiver dequeues in order (FIFO)
     - No blocking, no shared memory (no race conditions)
  2. Per-agent mailbox: ONE mailbox per agent (100+ agents in session)
  3. Message immutability: FlatBuffers serialization (no copies)
  4. Priority levels: URGENT (heartbeat, barge-in) > NORMAL (tasks) > LOW (metrics)

IMPLEMENTATION:
  - Data structure: Crossbeam MPSC (Rust) or similar atomic queue
  - Polling: Agent mailbox.receive_next() blocks on empty, timeout-based
  - Backpressure: If mailbox >1000 messages, reject new messages (ADR-0026)
  - Quiescence detection: Mailbox empty + no arrivals for 200ms = idle

ADR REFERENCES:
  - ADR-0002a (Mailbox MPSC implementation)
  - ADR-0002 (Actor Model foundation)

PERFORMANCE TARGETS (from ADR-0024):
  - Enqueue latency: <1ms P95 (lock-free atomic)
  - Dequeue latency: <0.5ms P95 (FIFO order)
  - Backpressure: Reject if >1000 pending (configurable)

OBSERVABILITY:
  - histogram: k1_mailbox_enqueue_latency_us{agent_id}
  - gauge: k1_mailbox_depth{agent_id} (pending messages)
  - counter: k1_mailbox_backpressure_rejections_total{agent_id}
```

**6. active_roster (Agent Status Tracking)**

```
PURPOSE: Track which agents are currently active in session

IMPORTS:
  → k1.runtime.session_state (L4) - Session context
  → k1.infrastructure.metrics (L5) - Roster metrics

EXPORTS:
  → Active agent list, state queries

LOGIC (from ADR-0005b State Transitions):

ROSTER STRUCTURE:
  - Hash table: agent_id → {state, state_since_time, resource_usage, lease}
  - Per-session roster: MAX 3 agents (configurable space policy)
  - Lookup: O(1) hash table
  - State snapshot: Quick query of all agents in ACTIVE/IDLE/DRAINING

TRANSITIONS TRACKED:
  1. Add agent: hire_fire → PENDING → WARMING → ACTIVE
  2. Idle agent: active_roster updates idle_timestamp, enables ACTIVE → IDLE
  3. Fire agent: active_roster marks for draining, monitors drain completion
  4. Remove agent: TERMINATED → delete from roster

RESOURCE LIMITS:
  - Per-agent: 150MB (AI agents) to <10MB (pure actors)
  - Per-session: 500MB total K1 memory (ADR-0024)
  - Enforce: If heap >80%, supervisor drains IDLE agents by RSS

ADR REFERENCES:
  - ADR-0005b (Agent state transitions, lifecycle management)
  - ADR-0005d (Supervisor monitoring of roster)

OBSERVABILITY:
  - gauge: k1_active_agents_total{session_id, agent_type}
  - gauge: k1_agents_by_state{state} (PENDING/WARMING/ACTIVE/IDLE/DRAINING)
  - histogram: k1_agent_lifetime_duration_ms (total time from hire to fire)
```

**3a Summary: Agent Lifecycle Flow**

```
Orchestrator.hire_agent(agent_id) [Contract Net Protocol - ADR-0006a]
    ↓
hire_fire.transition(PENDING → WARMING)
    ├─→ registry.get_agent_spec(agent_id)
    ├─→ For AI agents: Load model (Model Hub), prompt, KV cache
    ├─→ For pure actors: Load config
    └─→ Supervisor registers: health_check_enabled
    ↓ (Awaits resource initialization)
hire_fire.transition(WARMING → ACTIVE)
    ├─→ mailbox.ready()  (MPSC queue ready)
    ├─→ personality.apply() (tone, persona)
    └─→ active_roster.add(agent_id, state=ACTIVE)
    ↓ (Agent now processes tasks)
Agent.process_messages() [Actor message loop]
    ├─→ mailbox.receive_next() [MPSC dequeue, <0.5ms]
    ├─→ message_handler(message_type)
    ├─→ Model Hub calls (if AI agent) or pure logic
    └─→ Response / state_delta emission
    ↓ (After idle_timeout or completion)
hire_fire.transition(ACTIVE → IDLE)
    ├─→ mailbox.quiescent_check(200ms) [Guard]
    ├─→ personality.adapt_to_user() [Optional]
    └─→ active_roster.mark_idle()
    ↓ (On TTL expiry or memory pressure)
hire_fire.transition(IDLE → DRAINING)
    ├─→ mailbox.reject_new_tasks() [MPST enforced]
    ├─→ Finish current task
    ├─→ k1.runtime.session_state.flush() [K0 WAL idempotent]
    └─→ supervisor.request_termination()
    ↓
hire_fire.transition(DRAINING → TERMINATED)
    ├─→ registry.unload_spec(agent_id)
    ├─→ mailbox.close()
    ├─→ active_roster.remove(agent_id)
    ├─→ supervisor.check_blacklist() [>3 crashes in 10min]
    └─→ Capability revocation: revocation-on-crash tokens non-reusable

CRASH PATH:
Supervisor.health_check_failed() [Agent not responding to heartbeat]
    ↓
hire_fire.transition(any_state → TERMINATED) [Emergency]
    ├─→ Reason: crash
    ├─→ supervisor.record_crash()
    ├─→ supervisor.escalate_if_repeated()
    └─→ If >3 crashes: agent_id added to blacklist (1 hour)
```

#### 3b: Model Hub (7 modules - AI Integration Infrastructure)

| Module | File Path | Status | Serves AI Agents | ADR Reference |
|--------|-----------|--------|------------------|---|
| router | `k1/execution/model_hub/router.py` | ✅ POPULATED | Concierge, Planner, Researcher, Safety Watch | ADR-0001b, ADR-0027 |
| placement_planner | `k1/execution/model_hub/placement_planner.py` | ✅ POPULATED | All LLM calls (4 agents) | ADR-0027, ADR-0027a-0027d |
| adapters | `k1/execution/model_hub/adapters/` | ✅ POPULATED | OpenAI, Anthropic, Google, vLLM, Ollama, Azure | ADR-0001b |
| kv_cache_broker | `k1/execution/model_hub/kv_cache_broker.py` | ✅ POPULATED | Shared cache for multi-turn conversations | ADR-0025, ADR-0025a-0025e |
| prompt_library | `k1/execution/model_hub/prompt_library/` | ✅ POPULATED | 4 AI agents with versioned templates | ADR-0001b |
| fallback_cascade | `k1/execution/model_hub/fallback_cascade.py` | ✅ POPULATED | Provider failover with cost awareness | ADR-0027b-c |
| safety_filter | `k1/execution/model_hub/safety_filter.py` | ✅ POPULATED | Safety Watch agent + 3-tier moderation | ADR-0032, ADR-0035 |

**Architecture: 4 AI Agents + 6 LLM Providers + 4-Tier Placement Cascade**

```
4 AI Agents (serve different purposes, different LLM budgets):
  1. Concierge Agent (L1 NLU):      50ms budget   sync   openai|anthropic|vllm
  2. Planner Agent (L2 planning):  5000ms budget   async  openai|anthropic|vllm
  3. Researcher Agent (L3 synth):  3000ms budget   async  anthropic|openai|vllm
  4. Safety Watch Agent (L3 mod):   100ms budget   sync   openai|anthropic|vllm

6 LLM Providers (cost, latency, quality tiers):
  1. OpenAI (GPT-4, GPT-3.5)       - remote API, $0.015+/1K tokens, 250-500ms
  2. Anthropic (Claude 3)           - remote API, $0.003+/1K tokens, 250-500ms
  3. Google (Gemini)                - remote API, $0.0001+/1K tokens, 250-500ms
  4. vLLM (local GPU)               - local, free, 50ms, quantized models
  5. Ollama (local CPU)             - local, free, 120ms, small models
  6. Azure (enterprise)             - remote API, $0.001+/1K tokens (negotiated)

4-Tier Placement Cascade (from ADR-0027):
  Tier 1: NPU (30ms, 10W, on-device, privacy-respecting)
  Tier 2: GPU (50ms, 12W, on-device, high perf)
  Tier 3: CPU (120ms, 15W, on-device, fallback)
  Tier 4: Remote (250-500ms, 5W idle, unlimited quality)
```

**1. router (Provider Routing Decisions)**

```
PURPOSE: Select best LLM provider for each agent call

IMPORTS:
  → k1.execution.model_hub.placement_planner (hardware availability)
  → k1.execution.model_hub.adapters (provider clients)
  → k1.execution.model_hub.fallback_cascade (fallback decisions)
  → k1.infrastructure.config (L5 - provider config, API keys)
  → k1.infrastructure.metrics (L5 - track provider calls)

EXPORTS:
  → LLM call routed to selected provider
  → Decision metadata (why this provider was selected)

LOGIC (from ADR-0001b, ADR-0027):

ROUTING DECISION TREE:
  1. Determine task type from agent_id + intent
     - Concierge NLU: Fast classification (<50ms) → prefer local (vLLM) or cheap (Google)
     - Planner reasoning: Complex 5000ms budget → prefer best quality (GPT-4 or Claude Opus)
     - Researcher synthesis: 3000ms budget + long context → prefer Claude (200K context)
     - Safety Watch: Fast classification (<100ms) → prefer GPT-3.5 (cheap + fast)

  2. Check placement availability (ADR-0027a thermal cascade):
     - Device thermal state: COOL/WARM/HOT/CRITICAL (from ADR-0026)
     - NPU available? → Place there first (privacy + speed)
     - GPU available? → If NPU unavailable
     - CPU available? → If GPU unavailable
     - Force remote? → If local unavailable or RED band (privacy)

  3. Apply privacy band constraints:
     - GREEN (public): Any placement OK → prioritize cost (Google Gemini cheapest)
     - AMBER (semi-private): Local preferred, remote with PII masking
     - RED (sensitive): Local only → model Hub blocks remote

  4. Select provider from available tiers:
     - Local tier: vLLM (GPU) or Ollama (CPU) available → use (free, <150ms)
     - Cost tier: If local unavailable, route to cheapest provider (Google < Anthropic < OpenAI)
     - Quality tier: If local + cost tiers unable, route to best (GPT-4 Turbo, Claude Opus)
     - Enterprise tier: Azure if org policy requires

  5. Check circuit breaker state (ADR-0027b failover):
     - Provider open circuit? (>5 failures in 60s) → skip, try next tier
     - Provider degraded? (latency >2s) → mark for fallback_cascade
     - Provider quota exceeded? → try next provider

  6. Route to selected provider adapter
     - Call adapter.send_request(messages, max_tokens, timeout)
     - Timeout: 10s max per LLM call (from ADR-0001b)

ADR REFERENCES:
  - ADR-0001b (Model Hub architecture, 4 AI agents, 6 providers)
  - ADR-0027 (Model placement cascade, NPU→GPU→CPU→Remote)
  - ADR-0027a (Placement algorithm, thermal awareness)
  - ADR-0027b (Automatic failover <100ms migration)

PERFORMANCE TARGETS (from ADR-0024):
  - Routing decision latency: <5ms (simple decision tree)
  - Concierge sync call: <50ms (routing + inference)
  - Planner async call: <5000ms (routing + reasoning)

OBSERVABILITY:
  - counter: k1_model_router_decisions_total{agent_id, provider, reason}
  - histogram: k1_model_router_latency_ms{agent_id}
  - gauge: k1_model_provider_circuit_breaker{provider, state}
```

**2. placement_planner (Hardware Placement Decisions)**

```
PURPOSE: Decide WHERE to run inference (NPU/GPU/CPU/Remote)

IMPORTS:
  → k1.infrastructure.thermal (L5 - thermal state, ADR-0026)
  → k1.infrastructure.budgets (L5 - resource constraints, ADR-0024)
  → k1.infrastructure.config (L5 - hardware manifest)

EXPORTS:
  → Placement decision (NPU|GPU|CPU|Remote)
  → Fallback chain if placement fails

LOGIC (from ADR-0027, ADR-0027a Placement Algorithm):

HARDWARE AVAILABILITY CHECKS:
  1. NPU (Neural Processing Unit - Apple ANE, NVIDIA Tensor):
     - Driver available: Check `/dev/qaic*` (Linux) or system APIs
     - Thermal state: Must be COOL or WARM (ADR-0026c thermal cascade)
     - Memory available: >100MB for quantized models
     - Not blacklisted: No recent crashes (supervisor tracking)
     - Privacy OK: Can place model (RED stays local only)

  2. GPU (CUDA/ROCm/Metal):
     - Runtime available: CUDA, OpenCL, Metal runtime loaded
     - Thermal state: Not CRITICAL (allow HOT state with throttling)
     - Memory available: >500MB for LLaMA-7B
     - Not blacklisted: No recent OOM failures

  3. CPU (Universal fallback):
     - Always available (can run quantized models)
     - Memory available: >300MB even under pressure
     - Throttle if thermal EMERGENCY (slow 120ms inference)

  4. Remote (Cloud LLM APIs):
     - Network available: Active connection to provider
     - Circuit breaker not open: Provider not rate-limited or failing
     - Cost within budget: Session $0.10/turn limit (ADR-0027c)
     - Privacy allowed: GREEN/AMBER only (RED blocks remote)

PLACEMENT CASCADE (priority order):
  if thermal_state in [COOL, WARM]:
    cascade = [NPU, GPU, CPU, Remote]
  elif thermal_state == HOT:
    cascade = [GPU, CPU, Remote]  # Skip NPU to save power
  elif thermal_state == CRITICAL:
    cascade = [CPU, Remote]       # Skip NPU + GPU
  else:  # EMERGENCY
    cascade = [Remote]            # Local disabled

  for placement in cascade:
    if is_available(placement) and respects_privacy_band():
      return placement
  return Remote  # Ultimate fallback

LATENCY & POWER CHARACTERISTICS (from ADR-0027):
  - NPU: 30ms latency, 5-8W power (BEST for privacy + speed)
  - GPU: 50ms latency, 15-25W power (good for high throughput)
  - CPU: 120ms latency, 3-10W power (universal fallback)
  - Remote: 250-500ms latency, 5W idle (unlimited quality)

ADR REFERENCES:
  - ADR-0027 (Model placement cascade master decision)
  - ADR-0027a (Placement algorithm NPU→GPU→CPU→Remote)
  - ADR-0027b (Automatic failover <100ms migration)
  - ADR-0027c (Cost-aware fallback $0.10/session budget)
  - ADR-0027d (Remote resilience 3 retries, 10s timeout)
  - ADR-0026c (Thermal state integration)

PERFORMANCE TARGETS (from ADR-0024):
  - Placement decision: <5ms (simple algorithm)
  - Fallback decision: <10ms (max 2 retries per tier)

OBSERVABILITY:
  - counter: k1_model_placement_decisions_total{device_type, reason}
  - histogram: k1_model_placement_latency_ms
  - gauge: k1_model_device_available{device_type}
```

**3. adapters (Multi-Provider LLM Interface)**

```
PURPOSE: Provide unified interface for 6 LLM providers

IMPORTS:
  → k1.infrastructure.config (L5 - API keys, model names)
  → k1.infrastructure.metrics (L5 - usage metrics)

EXPORTS:
  → Unified LLM interface: call(messages, max_tokens) → response
  → Token usage tracking
  → Error handling + timeouts

LOGIC (from ADR-0001b Provider Adapters):

ADAPTER ARCHITECTURE (6 providers):

1. **OpenAI Adapter (GPT-4 Turbo, GPT-3.5):**
   - Models: gpt-4-turbo (128K context), gpt-3.5-turbo (16K context)
   - Cost: $0.01/1K input, $0.03/1K output
   - Latency: 250-500ms TTFT
   - Implementation: OpenAI SDK + aiohttp (async)
   - Circuit breaker: 5 failures → open 60s (ADR-0009)
   - Timeout: 10s max per call
   - Error handling: Rate limit (429), API errors, timeouts

2. **Anthropic Adapter (Claude 3 Opus/Sonnet/Haiku):**
   - Models: claude-3-opus (200K context), claude-3-sonnet, claude-3-haiku
   - Cost: Opus $0.015/1K input, $0.075/1K output
   - Latency: 250-500ms TTFT
   - Implementation: Anthropic SDK + async
   - Circuit breaker: 5 failures → open 60s
   - Timeout: 10s max per call
   - Strengths: Long context (200K), constitutional AI (safety)

3. **Google Gemini Adapter:**
   - Models: gemini-pro (32K context), gemini-1.5 (1M context coming)
   - Cost: $0.0001/1K input (CHEAPEST), $0.0005/1K output
   - Latency: 250-500ms TTFT
   - Implementation: Google Generative AI SDK
   - Circuit breaker: 5 failures → open 60s
   - Timeout: 10s max per call
   - Strengths: Cost, multimodal support

4. **vLLM Adapter (local GPU inference):**
   - Models: LLaMA 3.1 8B, Mistral 7B, Gemma 2 9B
   - Cost: FREE (on-device)
   - Latency: 50ms TTFT (GPU), 120ms (CPU quantized)
   - Implementation: vLLM HTTP server (localhost:8000)
   - Circuit breaker: OOM failures → fallback to CPU
   - Timeout: 2s max per call (local)
   - Privacy: Full on-device, no data egress

5. **Ollama Adapter (local CPU inference):**
   - Models: LLaMA 2 7B, Mistral 7B quantized INT4
   - Cost: FREE (on-device)
   - Latency: 120ms TTFT (even on slow CPU)
   - Implementation: Ollama HTTP API (localhost:11434)
   - Circuit breaker: Memory pressure → skip
   - Timeout: 5s max per call (slower)
   - Privacy: Full on-device, no data egress

6. **Azure Adapter (enterprise):**
   - Models: GPT-4, GPT-3.5 (via Azure OpenAI)
   - Cost: Custom pricing (enterprise negotiated)
   - Latency: 250-500ms TTFT
   - Implementation: Azure OpenAI SDK
   - Circuit breaker: 5 failures → open 60s
   - Timeout: 10s max per call
   - Strengths: Enterprise compliance, SOC 2

UNIFIED INTERFACE (all adapters):
  async def call(messages, max_tokens, timeout=10.0):
    """Call LLM, return {content, usage, finish_reason, model}"""
    # Implementation per provider
    response = await provider_sdk.create(...)
    return {
      "content": response.choices[0].message.content,
      "usage": {"prompt_tokens": X, "completion_tokens": Y},
      "finish_reason": "stop|length|tool_use",
      "model": response.model
    }

ERROR HANDLING:
  - Timeout (10s): Raise ModelTimeoutError → trigger fallback_cascade
  - Rate limit (429): Raise ModelRateLimitError → back off + fallback
  - API error (5xx): Raise ModelProviderError → open circuit breaker
  - Insufficient quota: Raise ModelQuotaError → use backup provider

ADR REFERENCES:
  - ADR-0001b (Model Hub architecture, provider adapters)
  - ADR-0009 (Circuit breaker pattern, failure thresholds)

PERFORMANCE TARGETS (from ADR-0024):
  - Adapter call latency: 250-500ms remote, 30-120ms local
  - Provider failover: <100ms (ADR-0027b)

OBSERVABILITY:
  - counter: k1_model_adapter_requests_total{provider, model}
  - histogram: k1_model_adapter_latency_ms{provider}
  - counter: k1_model_adapter_errors_total{provider, reason}
  - gauge: k1_model_adapter_circuit_breaker{provider, state}
```

**4. kv_cache_broker (Shared KV Cache Management)**

```
PURPOSE: Manage shared KV cache (512MB global budget) across all sessions

IMPORTS:
  → k1.infrastructure.cache (L5 - cache allocator)
  → k1.infrastructure.metrics (L5 - cache metrics)

EXPORTS:
  → KV cache allocation/deallocation
  → Cache hit/miss tracking

LOGIC (from ADR-0025 Global KV Cache Manager, ADR-0025a Allocator):

GLOBAL BUDGET: 512MB device-wide (from ADR-0024 constraints)

ALLOCATION POLICY (LRU/LFU hybrid):
  - Per-session min: 32MB guaranteed for active sessions
  - Per-session max: 256MB cap (prevent monopolization)
  - Total limit: 512MB device-wide
  - Eviction trigger: 90% full (460MB) → start evicting

EVICTION STRATEGY (60% LRU + 40% LFU):
  - LRU weight: 60% → prioritize recency (user's active conversations)
  - LFU weight: 40% → prioritize frequency (important long-running sessions)
  - Protected sessions: Active conversation + Safety Watch never evicted
  - Cascade on memory pressure: Evict inactive sessions first

CACHE WARMING (on session resume):
  - Prefetch recent turns (last 5 messages)
  - Precompute attention KV for resume latency <50ms
  - Compress inactive caches with zstd (70% size reduction)

COMPRESSION (under memory pressure):
  - Trigger: 85% full (435MB)
  - Algorithm: zstd compression level 3
  - Compression ratio: 70% size (256MB → 77MB)
  - Decompression latency: <15ms per access

ADR REFERENCES:
  - ADR-0025 (KV cache management 512MB global budget)
  - ADR-0025a (Global KV cache allocator per-session limits)
  - ADR-0025b-e (Eviction, cache warming, compression details)

PERFORMANCE TARGETS (from ADR-0024):
  - Cache lookup: <1ms (hash table)
  - Cache allocation: <2ms
  - Eviction decision: <5ms (LRU/LFU scoring)
  - Cache hit rate: >75% target (79% in production)

OBSERVABILITY:
  - gauge: k1_kv_cache_allocated_mb (current usage)
  - gauge: k1_kv_cache_available_mb (free budget)
  - counter: k1_kv_cache_hits_total{session_id}
  - counter: k1_kv_cache_misses_total{session_id}
  - histogram: k1_kv_cache_hit_rate_percent
```

**5. prompt_library (Agent-Specific Prompt Templates)**

```
PURPOSE: Store versioned prompt templates (system messages) for 4 AI agents

IMPORTS:
  → k1.infrastructure.storage_connector (L5 - template loading)
  → k1.infrastructure.config (L5 - template catalog)

EXPORTS:
  → Rendered prompt templates (Jinja2 with context variables)
  → Template versioning + evolution tracking

LOGIC (from ADR-0001b Prompt Library):

TEMPLATE STRUCTURE:

1. **Agent Persona Prompts** (system messages):
   - concierge/system_prompt_v1.0.0.jinja2 (friendly assistant)
   - planner/plan_generation_v1.0.0.jinja2 (strategic planner)
   - researcher/research_strategy_v1.0.0.jinja2 (academic researcher)
   - safety_watch/content_filtering_v1.0.0.jinja2 (safety guardian)

2. **Task-Specific Prompts**:
   - task_decomposition.jinja2 (planning tasks)
   - tool_call_formatting.jinja2 (MCP tool invocation)
   - memory_synthesis.jinja2 (K0 context integration)

3. **Template Variables** (injected at runtime):
   - {{ user_profile.name }} - User identity
   - {{ family_members }} - Family context
   - {{ recent_memories }} - Last 5 K0 memories
   - {{ available_tools }} - MCP tools available
   - {{ context_window_tokens }} - Remaining budget

4. **Versioning** (semantic versioning):
   - v1.0.0: Initial release
   - v1.1.0: Bug fixes to prompts
   - v2.0.0: Major persona overhaul
   - Active version configurable per agent

RENDERING PROCESS:
  1. Load template: prompt_library.get("concierge", version="v1.0.0")
  2. Inject variables: template.render(user_profile=..., recent_memories=...)
  3. Return: {system_prompt, token_budget_remaining}

ADR REFERENCES:
  - ADR-0001b (Model Hub architecture, Prompt Library component)

PERFORMANCE TARGETS (from ADR-0024):
  - Template load: <5ms (cached in memory)
  - Template render: <10ms (Jinja2 compilation)
  - Total prompt prep: <20ms

OBSERVABILITY:
  - counter: k1_prompt_renders_total{agent_id, template_version}
  - histogram: k1_prompt_render_latency_ms
```

**6. fallback_cascade (Provider Failover with Cost Awareness)**

```
PURPOSE: Handle provider failures with graceful degradation + cost optimization

IMPORTS:
  → k1.execution.model_hub.adapters (provider clients)
  → k1.execution.model_hub.placement_planner (hardware fallback)
  → k1.infrastructure.budgets (L5 - cost limits)

EXPORTS:
  → Fallback provider selection
  → Graceful degradation (template-based response if all fail)

LOGIC (from ADR-0027b Automatic Failover, ADR-0027c Cost-Aware Fallback):

FAILOVER SEQUENCE (per agent):

1. **Concierge Agent** (50ms budget, fast NLU):
   Primary: vLLM (local GPU, free, 50ms)
   Backup1: Ollama (local CPU, free, 120ms)
   Backup2: Google Gemini (cheapest, $0.0001/1K, 250-500ms)
   Backup3: Anthropic Haiku (cheap + capable, $0.00025/1K, 250-500ms)
   Fallback: Template-based response ("Please rephrase")

2. **Planner Agent** (5000ms budget, complex reasoning):
   Primary: GPT-4 Turbo (best quality, $0.015/1K, 250-500ms)
   Backup1: Claude 3 Opus (high quality, $0.015/1K, 250-500ms)
   Backup2: vLLM (local fallback, free, 50ms - lower quality)
   Fallback: Template-based plan ("Standard approach")

3. **Researcher Agent** (3000ms budget, long context):
   Primary: Claude 3 Opus (200K context, $0.015/1K, 250-500ms)
   Backup1: GPT-4 Turbo (128K context, $0.01/1K, 250-500ms)
   Backup2: Gemini 1.5 (1M context, $0.0001/1K, 250-500ms)
   Fallback: Template-based summary ("Summary unavailable")

4. **Safety Watch Agent** (100ms budget, classification):
   Primary: GPT-3.5 Turbo (fast + cheap, $0.0005/1K, 250-500ms)
   Backup1: Claude 3 Haiku (fast + cheap, $0.00025/1K, 250-500ms)
   Backup2: Gemini Nano (ultra-fast, $0.0001/1K, 250-500ms)
   Fallback: Block by default (conservative safety)

COST-AWARE ROUTING:
  - Per-session budget: $0.10/turn (ADR-0027c)
  - Track cost per call: tokens * cost_per_token
  - If cumulative >$0.08 on previous call: Use cheaper provider
  - If budget exhausted: Block remote, use local only

CIRCUIT BREAKER INTEGRATION (ADR-0009):
  - Per provider: Open if >5 failures in 60s window
  - Open duration: 30-60s (exponential backoff)
  - Half-open check: Probe with small request
  - Closed: Normal operation

ERROR RECOVERY (retry logic):
  - Max retries per tier: 2 (prevent cascade loops)
  - Total timeout per call: 5s (max 2s per retry)
  - Exponential backoff: 100ms, 200ms between retries

GRACEFUL DEGRADATION (all providers fail):
  - Return template-based response (neutral, safe default)
  - Log incident: send to observability backend + alert
  - Metrics: increment k1_fallback_cascade_exhausted_total

ADR REFERENCES:
  - ADR-0027b (Automatic failover <100ms migration)
  - ADR-0027c (Cost-aware fallback $0.10/session budget)
  - ADR-0027d (Remote resilience 3 retries, 10s timeout)
  - ADR-0009 (Circuit breaker pattern)

PERFORMANCE TARGETS (from ADR-0024):
  - Failover decision: <10ms
  - Max cascade time: 5s (2 retries + fallback)

OBSERVABILITY:
  - counter: k1_fallback_cascade_triggered_total{agent_id, reason}
  - counter: k1_fallback_cascade_exhausted_total
  - counter: k1_fallback_cost_limits_hit_total
  - histogram: k1_fallback_cascade_latency_ms
```

**7. safety_filter (3-Tier Content Moderation)**

```
PURPOSE: Safety checks on LLM input/output, PII detection

IMPORTS:
  → k1.infrastructure.safety.pii_detector (L5 - PII detection)
  → k1.infrastructure.policy (L5 - safety policy)
  → k1.infrastructure.metrics (L5 - safety metrics)

EXPORTS:
  → Pre-filter check (input validation)
  → Post-filter check (output validation)
  → Redaction/blocking decisions

LOGIC (from ADR-0032 Band-Based Egress, ADR-0035 PII Detection):

3-TIER MODERATION (ADR-0033 sandbox strategy):

1. **Tier 1: Pre-Filter (Input Validation)**
   - Prompt injection detection: Check for adversarial patterns
   - PII detection: Scan input for sensitive data (SSN, phone, address, etc)
   - Privacy band enforcement: RED → block remote APIs, AMBER/GREEN → allow
   - Action: Redact PII, block injections, allow safe input

2. **Tier 2: Post-Filter (Output Validation)**
   - PII in output: Detect SSN, phone, address in LLM response
   - Harmful content: Check for violent, hateful, illegal content
   - Privacy band enforcement: RED output must not contain PII
   - Action: Redact PII, block harmful content, return template response

3. **Tier 3: Safety Watch Agent** (Deep analysis on escalation)
   - Triggered when Tier 1 or Tier 2 flags high-risk content
   - Runs Safety Watch agent (GPT-3.5 + safety persona)
   - Complex reasoning: Is this truly harmful? (>2 false positives)
   - Action: Escalate to HITL, block content, or allow

PII DETECTION METHODS (ADR-0035):
  - Regex patterns: SSN (XXX-XX-XXXX), phone (555-1234), credit card
  - ML-based NER: Named entity recognition for person names, locations
  - Heuristic: Email + password combinations, "confirm password" patterns
  - Encrypted vault: Store redacted PII in secure storage (encryption key in L5)

PRIVACY BAND ENFORCEMENT:
  - RED (medical, financial):
    * Pre: Block PII input
    * Post: Block any PII in output
    * Remote: Blocked entirely (local only)
  - AMBER (preferences, habits):
    * Pre: Warn on PII input
    * Post: Redact PII in output
    * Remote: Allowed with PII masking
  - GREEN (public):
    * Pre: No restrictions
    * Post: No restrictions
    * Remote: Allowed freely

ADR REFERENCES:
  - ADR-0032 (Band-based egress rules, privacy enforcement)
  - ADR-0032a (Network egress control, iptables)
  - ADR-0035 (PII detection and redaction)
  - ADR-0035a (Regex pattern library)
  - ADR-0035b (ML-based NER)
  - ADR-0033 (Three-tier sandbox strategy)

PERFORMANCE TARGETS (from ADR-0024):
  - Pre-filter latency: <10ms
  - Post-filter latency: <10ms
  - Safety Watch decision: <100ms (on tier 3 escalation)

OBSERVABILITY:
  - counter: k1_safety_filter_blocks_total{tier, reason}
  - counter: k1_safety_filter_redactions_total
  - counter: k1_safety_filter_escalations_total
  - histogram: k1_safety_filter_latency_ms
```

**Model Hub Dependency Graph**

```
orchestrator (L2) [via hire_fire agent dispatch]
    ↓
agent (AI: Concierge|Planner|Researcher|Safety Watch)
    ├─→ router (decide provider based on budget + thermal)
    │      ├─→ placement_planner (NPU→GPU→CPU→Remote)
    │      ├─→ adapters (provider circuit breakers)
    │      └─→ fallback_cascade (if provider fails)
    ├─→ prompt_library (load system message template)
    ├─→ adapters.call(provider_id, messages)
    │      └─→ [OpenAI|Anthropic|Google|vLLM|Ollama|Azure]
    ├─→ kv_cache_broker (cache KV for next turn)
    └─→ safety_filter (pre-filter input, post-filter output)
         ├─→ PII detection (ADR-0035)
         └─→ Band-based privacy (ADR-0032)

EXECUTION FLOW (Concierge call):
  1. Agent receives intent_classification task (50ms budget)
  2. router: COOL thermal → try vLLM (local GPU, free)
  3. placement_planner: NPU available + RED band → local only
  4. prompt_library: Load concierge system prompt v1.0.0
  5. safety_filter: Pre-filter user input (PII check)
  6. adapters.vllm.call(messages) → 50ms latency
  7. safety_filter: Post-filter output (PII redaction)
  8. kv_cache_broker: Store KV cache for multi-turn
  9. Return: {classification, confidence, trace_id}
```

#### 3c: Tool Execution (5 modules - MCP+Sandbox 2-Layer Architecture)

| Module | File Path | Status | Serves | ADR Reference |
|--------|-----------|--------|--------|---|
| runner | `k1/execution/tools/runner.py` | ✅ POPULATED | Tool invocation orchestrator | ADR-0034, ADR-0014 |
| sandbox | `k1/execution/tools/sandbox/` | ✅ POPULATED | MCP+WASM+Process+Container isolation | ADR-0033, ADR-0033a-d |
| registry | `k1/execution/tools/registry.py` | ✅ POPULATED | Tool catalog + capability enforcement | ADR-0013, ADR-0010 |
| adapters | `k1/execution/tools/adapters/` | ✅ POPULATED | MCP JSON-RPC, REST, CLI protocol adapters | ADR-0034, ADR-0034a-d |
| control | `k1/execution/tools/control.py` | ✅ POPULATED | Timeout, resource limits, cost budgets | ADR-0014, ADR-0031 |

**Architecture: 100 Tools × 2-Layer Execution**

```
2-Layer Tool Execution Architecture (ADR-0033, ADR-0034):

Layer 1 - Protocol (HOW tools communicate):
  • MCP Protocol (80% tools): JSON-RPC 2.0 over stdio/HTTP (Anthropic 2024, 608 tools)
  • Direct API (20% tools): REST APIs, CLI binaries, legacy integrations

Layer 2 - Sandbox (WHERE/HOW code runs securely):
  • WASM Sandbox (15% tools): Wasmtime + WASI, max isolation for untrusted code
  • Process Sandbox (80% tools): OS process isolation with egress controls (ADR-0032)
  • Container Sandbox (5% tools): gVisor/Firecracker for high-risk operations

2D Matrix (100% coverage):
  ┌──────────────┬──────────────┬──────────────┬──────────────┐
  │ Protocol ↓ / │ WASM (15%)   │ Process(80%) │ Container(5%)│
  │ Sandbox →    │              │              │              │
  ├──────────────┼──────────────┼──────────────┼──────────────┤
  │ MCP (80%)    │ 10%: Plugin  │ 70%: Standard│ <1%: High    │
  │              │  as WASM MCP │ MCP server   │ risk MCP     │
  ├──────────────┼──────────────┼──────────────┼──────────────┤
  │ Direct (20%) │ 5%: Standalone│ 15%: CLI    │ <1%: High    │
  │              │  WASM module │ binary      │ risk API     │
  └──────────────┴──────────────┴──────────────┴──────────────┘

Security Guarantees: All sandboxes enforce timeout, egress control, resource limits
```

**1. runner (Tool Invocation Orchestrator)**

```
PURPOSE: Execute tool calls with orchestration, timeouts, and error handling

IMPORTS:
  → k1.execution.tools.registry (tool specs, capabilities)
  → k1.execution.tools.adapters (protocol adapters: MCP, REST, CLI)
  → k1.execution.tools.sandbox (execution environments)
  → k1.execution.tools.control (timeout, resource, cost limits)
  → k1.infrastructure.policy (L5 - capability enforcement)
  → k1.infrastructure.metrics (L5 - tool metrics)

EXPORTS:
  → Tool execution results (output, usage, error)
  → Tool call receipts → K0

LOGIC (from ADR-0034 MCP Protocol, ADR-0014 Timeout Management):

TOOL EXECUTION FLOW:
  1. Receive tool call request (agent → runner)
  2. registry.get_tool_spec(tool_id) → {name, protocol, sandbox, capabilities}
  3. Check capability: Does caller possess permission to invoke?
     - Via ADR-0010: Caller must have capability token for this tool
     - ADR-0010c: Validate token signature + constraint (max_cost, max_invocations)
  4. Check timeout budget: Convert tool budget to wall-clock timeout
     - Standard tool: <5s timeout
     - Long-running tool (video): <300s timeout
     - Quick tool (calculator): <0.5s timeout
  5. adapters.route(protocol, tool_spec) → adapter instance
  6. sandbox.execute(adapter, tool_spec, arguments, timeout) → result
  7. control.enforce_limits(result) → Check cost, resource usage
  8. Return result to caller

TOOL REGISTRY LOOKUP (ADR-0013):
  - By tool_id: "weather_api", "book_reservation", "send_email"
  - By capability: "execute_booking", "read_calendar", "send_message"
  - By sandbox: "MCP+Process", "Direct+WASM", "MCP+Container"

CAPABILITY ENFORCEMENT (ADR-0010):
  - Caller must possess unforgeable capability token
  - Token signed with HMAC-SHA256, includes constraints
  - Validate: signature, expiration, max_cost, max_invocations, privacy_band
  - <1ms validation (HMAC check + constraint checks)

ADR REFERENCES:
  - ADR-0034 (MCP protocol for tool integration)
  - ADR-0014 (Tool timeout management)
  - ADR-0010 (Capability-based security, token validation)
  - ADR-0013 (Dynamic tool loading, registry)
  - ADR-0033 (3-tier sandbox strategy)

PERFORMANCE TARGETS (from ADR-0024):
  - Tool lookup: <1ms (hash table O(1))
  - Capability validation: <1ms (HMAC signature + constraint check)
  - Tool execution: Tool-dependent (0.5s-300s range)
  - Error handling: <10ms (exception → response)

OBSERVABILITY:
  - counter: k1_tool_executions_total{tool_id, status}
  - histogram: k1_tool_execution_latency_ms{tool_id}
  - counter: k1_tool_capability_denials_total{reason}
  - gauge: k1_tool_concurrent_executions{tool_id}
```

**2. sandbox (3-Tier Execution Environment - ADR-0033)**

```
PURPOSE: Provide graduated execution isolation (WASM/Process/Container)

IMPORTS:
  → k1.infrastructure.metrics (L5)
  → k1.infrastructure.policy (L5 - egress controls, ADR-0032)

EXPORTS:
  → Sandboxed execution environments for tools
  → Execution results with resource tracking

LOGIC (from ADR-0033 Three-Tier Sandbox Strategy):

3-TIER ARCHITECTURE:

TIER 1: WASM Sandbox (15% of tools)
  - Purpose: Maximum isolation for untrusted code (user plugins, 3rd party submissions)
  - Implementation: Wasmtime runtime + WASI (WebAssembly System Interface)
  - Security: Capability-based I/O (no native syscalls without permission)
  - Performance: 10x slower than native (acceptable for untrusted code)
  - Examples: User-submitted plugin, experimental feature, third-party module
  - Constraints:
    * Memory: 64MB per module (enforced by WASI)
    * CPU: 5s timeout (configurable)
    * I/O: Only via WASI filesystem/network (whitelisted)
  - Flow:
    1. Load WASM module from registry
    2. Initialize Wasmtime runtime with resource limits
    3. Call exported function: invoke(args_json)
    4. Capture output, enforce timeout
    5. Return result or timeout error

TIER 2: Process Sandbox (80% of tools)
  - Purpose: Standard OS process isolation with egress controls
  - Implementation: POSIX process + chroot + seccomp + cgroups (ADR-0032)
  - Security: Network/filesystem/resource restricted per ADR-0032 band rules
  - Performance: <100ms launch overhead, native speed execution
  - Examples: Weather API (MCP+Process), ffmpeg CLI, system utilities
  - Egress Controls (from ADR-0032):
    * Network: iptables rules per privacy band (RED: no remote, AMBER: masked PII, GREEN: allowed)
    * Filesystem: chroot to /var/tool_id (isolated filesystem)
    * Syscalls: seccomp filter (whitelist safe syscalls, block dangerous ones)
    * Resources: cgroups v2 (CPU, memory, I/O limits)
  - Flow:
    1. Fork child process
    2. Apply chroot, seccomp, cgroups limits
    3. Execute tool (MCP server, native binary, or CLI)
    4. Monitor via process metrics
    5. Enforce timeout with SIGKILL
    6. Collect output, cleanup

TIER 3: Container Sandbox (5% of tools)
  - Purpose: Hardware-level isolation for extremely high-risk operations
  - Implementation: gVisor (user-space kernel) or Firecracker (microVM)
  - Security: Kernel isolation, extreme defense-in-depth
  - Performance: gVisor ~100ms overhead, Firecracker 125ms boot + execution
  - Use case: RED band tools, malware analysis, hostile code
  - Examples: High-risk tool execution, regulatory-required isolation
  - Flow (Firecracker):
    1. Launch microVM (~125ms startup)
    2. Execute tool inside microVM
    3. Collect results, shutdown microVM

SANDBOX SELECTION LOGIC:
  if trust_level == "untrusted":
    → WASM Sandbox (maximum isolation)
  elif privacy_band == "RED":
    → WASM or Container (local-only enforcement)
  elif tool_complexity == "high" && failure_risk == "high":
    → Container Sandbox (hardware isolation)
  else:
    → Process Sandbox (standard for 80% of tools)

ADR REFERENCES:
  - ADR-0033 (3-tier sandbox strategy)
  - ADR-0033a (MCP protocol integration)
  - ADR-0033b (WASM sandbox implementation)
  - ADR-0033c (Process sandbox implementation)
  - ADR-0032 (Band-based egress controls)

PERFORMANCE TARGETS:
  - WASM spawn: <5ms, execution: 10x slower than native
  - Process spawn: <100ms, execution: native speed
  - Container spawn: 100-500ms (gVisor-100ms, Firecracker-125ms+)

OBSERVABILITY:
  - gauge: k1_sandbox_active_executions{type}
  - histogram: k1_sandbox_spawn_latency_ms{type}
  - counter: k1_sandbox_failures_total{type, reason}
```

**3. registry (Tool Catalog + Capability Management)**

```
PURPOSE: Store tool specifications, manage capabilities, enforce access control

IMPORTS:
  → k1.infrastructure.config (L5 - tool definitions)
  → k1.infrastructure.metrics (L5)

EXPORTS:
  → Tool specifications and capabilities
  → Capability enforcement decisions

LOGIC (from ADR-0013 Dynamic Tool Loading, ADR-0010 Capabilities):

TOOL REGISTRY STRUCTURE:
  - Registry: tool_id → {name, protocol, sandbox, capabilities, timeout_s}
  - Examples:
    * "weather_api": {protocol: "MCP", sandbox: "Process", timeout: 5s}
    * "book_reservation": {protocol: "MCP", sandbox: "Process", timeout: 10s, capability: "execute_booking"}
    * "user_plugin": {protocol: "Direct", sandbox: "WASM", timeout: 5s}

CAPABILITY MODEL (ADR-0010):
  - Tool requires capability token from caller
  - Capability token structure:
    {
      "subject": "agent:planner_001",
      "resource": "tool:book_reservation",
      "rights": ["execute"],
      "constraints": {
        "max_cost_usd": 100.0,
        "max_invocations": 10,
        "requires_approval": true,
        "privacy_band": "AMBER"
      },
      "expiration": "2025-10-20T10:00:00Z",
      "signature": "HMAC-SHA256(token_content, secret_key)"
    }

REGISTRATION FLOW (ADR-0013a Runtime Registration):
  1. Tool provider submits tool specification (name, protocol, sandbox, capabilities)
  2. registry.register(tool_spec) → store in registry
  3. Version tracking: tool_v1.0.0, tool_v1.1.0, tool_v2.0.0
  4. Capability assignment: Who can invoke this tool? (agents, roles)

LOOKUP OPERATIONS:
  - By ID: registry.get("weather_api") → Tool spec
  - By capability: registry.find_by_capability("execute_booking") → [Tool A, Tool B]
  - By sandbox: registry.find_by_sandbox("WASM") → [Plugin1, Plugin2]

ADR REFERENCES:
  - ADR-0013 (Dynamic tool loading and versioning)
  - ADR-0010 (Capability-based security)

PERFORMANCE:
  - Lookup: O(1) hash table <1ms
  - Registration: <5ms

OBSERVABILITY:
  - gauge: k1_tool_registry_entries_total{protocol, sandbox}
```

**4. adapters (Protocol Adapters - MCP, REST, CLI)**

```
PURPOSE: Unified interface for tool communication protocols

IMPORTS:
  → k1.infrastructure.config (L5 - API credentials, endpoints)
  → k1.infrastructure.metrics (L5)

EXPORTS:
  → Unified tool call interface across protocols

LOGIC (from ADR-0034 MCP Protocol):

PROTOCOL ADAPTER TYPES:

1. **MCP Adapter (80% of tools)**
   - Protocol: JSON-RPC 2.0 over stdio or HTTP
   - Standard: Anthropic 2024 (adopted by Claude, ChatGPT, Copilot)
   - 608 tools compatible via MCP
   - Implementation:
     * stdio mode: Start MCP server process, communicate via stdin/stdout pipes
     * HTTP mode: Connect to MCP server HTTP endpoint
   - Message format: {"jsonrpc": "2.0", "id": 1, "method": "invoke", "params": {...}}
   - Error handling: JSON-RPC error response {"code": -32600, "message": "..."}

2. **REST Adapter (15% of tools)**
   - Protocol: HTTP/HTTPS with JSON payload
   - Examples: Weather API (HTTP GET), Booking service (HTTP POST)
   - Implementation: aiohttp client with retry + timeout

3. **CLI Adapter (5% of tools)**
   - Protocol: Command-line execution (stdin/stdout)
   - Examples: ffmpeg, imagemagick, system utilities
   - Implementation: subprocess with stdio pipes

UNIFIED INTERFACE (all adapters):
  async def invoke(self, tool_spec, arguments, timeout_s) → {output, usage, error}
  - tool_spec: Tool definition from registry
  - arguments: Tool invocation parameters (JSON)
  - timeout_s: Wall-clock timeout in seconds
  - Returns: {output, usage (if MCP), error (if failed)}

ERROR HANDLING:
  - Timeout: Raise ToolTimeoutError after timeout_s elapsed
  - Network error: Raise ToolNetworkError + retry up to 3 times
  - Invalid input: Raise ToolValidationError with details
  - Tool error: Return error response from tool (don't raise)

ADR REFERENCES:
  - ADR-0034 (MCP protocol for tool sandboxing)
  - ADR-0034a (JSON-RPC 2.0 specification)
  - ADR-0034b-d (MCP process lifecycle, circuit breaker, error handling)

OBSERVABILITY:
  - counter: k1_tool_adapter_requests_total{protocol, tool_id}
  - histogram: k1_tool_adapter_latency_ms{protocol}
```

**5. control (Timeout, Resource, and Cost Limits)**

```
PURPOSE: Enforce execution constraints (timeout, resource usage, cost budgets)

IMPORTS:
  → k1.infrastructure.budgets (L5 - cost limits, resource constraints)
  → k1.infrastructure.metrics (L5)

EXPORTS:
  → Enforcement of timeout, resource, cost limits
  → Budget deductions on tool execution

LOGIC (from ADR-0014 Timeout Management, ADR-0031 Cost Tracking):

TIMEOUT ENFORCEMENT (ADR-0014):
  - Per-tool timeout: Configured in tool spec (calculator: 0.5s, video: 300s)
  - Mechanism: Set timer, enforce SIGKILL or container termination
  - Measurement: Wall-clock time from invoke to result
  - P95 compliance: 95% of tools complete within their timeout budget

RESOURCE LIMITS (ADR-0024):
  - Memory per tool: <512MB (enforced via cgroups)
  - CPU per tool: <2 cores (enforced via cgroups)
  - File descriptors: <100 (enforced via ulimit)
  - Network connections: <10 concurrent (enforced via iptables)

COST TRACKING (ADR-0031):
  - Per-tool: Track cost per invocation (API call cost)
  - Per-session: Accumulate cost across all tool calls
  - Budget: $0.10-1.00 per session (configurable)
  - Enforcement: Reject tool calls that would exceed budget

ADR REFERENCES:
  - ADR-0014 (Tool timeout management with P95 targets)
  - ADR-0031 (Cost tracking per-session)
  - ADR-0024 (Performance budgets and resource limits)

OBSERVABILITY:
  - histogram: k1_tool_execution_duration_ms
  - counter: k1_tool_timeouts_total
  - gauge: k1_tool_session_cost_usd
```

---

#### 3d: Dialogue Management (4 modules - Conversation State & Turn Management)

| Module | File Path | Status | Purpose | ADR Reference |
|--------|-----------|--------|---------|---|
| scoreboard | `k1/execution/dialogue/scoreboard.py` | ✅ POPULATED | Message queue + coalescing | ADR-0053, ADR-0053a-c |
| state_tracker | `k1/execution/dialogue/state_tracker.py` | ✅ POPULATED | Conversation state mutations | ADR-0054, ADR-0054a-c |
| turn_manager | `k1/execution/dialogue/turn_manager.py` | ✅ POPULATED | Turn transitions + barge-in | ADR-0054, ADR-0057, ADR-0057a-c |
| repair | `k1/execution/dialogue/repair.py` | ✅ POPULATED | Error recovery + clarification | ADR-0008, ADR-0008a-d |

**Architecture: Turn-Based Dialogue with Message Coalescing & Error Recovery**

```
Conversation Flow (Implicit + Explicit Turn Boundaries):

USER TURN:
  Message 1: "Book a flight" → [Queued for coalescing]
  Message 2: "to New York" → [2s window, coalescing]
  Message 3: "tomorrow" → [Coalesce triggered]
  [2s pause] → Turn boundary (implicit)
  ↓
SYSTEM TURN:
  Intent: BOOK_FLIGHT (to="New York", date="tomorrow")
  Agent: Planner → Generate plan → Execute
  [If error] → Repair (clarify intent, retry)
  [If success] → Confirmation message
  ↓
[Session state committed]
  Conversation turn recorded in SessionState (ADR-0017)
```

**1. scoreboard (Message Queue & Coalescing)**

```
PURPOSE: Coalesce rapid user messages into complete utterances before processing

IMPORTS:
  → k1.infrastructure.event_bus (L5 - message ingress)
  → k1.infrastructure.metrics (L5)

EXPORTS:
  → Coalesced messages ready for intent classification
  → Rapid message batching signals

LOGIC (from ADR-0053 Message Queue & Coalescing):

MESSAGE COALESCING (ADR-0053a Coalesce Window):
  - Window: 2 seconds (user stops typing)
  - Limit: 5 messages per coalesce (prevent hoarding)
  - Trigger: Window expiry OR 5 messages received
  - Example:
    t=0.0s: "What's the"          → Queued
    t=0.5s: "weather in"          → Queued (2 messages)
    t=1.0s: "Seattle?"            → Queued (3 messages)
    t=1.2s: "today?"              → Queued (4 messages)
    t=3.2s: [2s silent] → Coalesce triggered
    Output: "What's the weather in Seattle today?"

RATE LIMITING (ADR-0053b Rate Limits & Bursts):
  - Baseline: 5 messages per second
  - Burst: Allow 3 messages before rate limit (for rapid corrections)
  - Enforcement: Reject messages >3 per 100ms (DDoS protection)
  - Privacy: RED band messages bypass coalescing (immediate processing)

CANCELLATION PATH (ADR-0053c Cancel Path P95):
  - User can interrupt mid-coalesce (e.g., click "Stop" button)
  - Cancellation completes <120ms P95
  - Mechanism: Cancel entire pending coalesce window, discard queued messages

ADR REFERENCES:
  - ADR-0053 (Message queue & coalescing architecture)
  - ADR-0053a (Coalesce window limits 2s, 5 messages)
  - ADR-0053b (Rate limits 5 msg/sec, 3-message burst)
  - ADR-0053c (Cancel path <120ms P95)

OBSERVABILITY:
  - histogram: k1_coalesce_window_size{messages}
  - histogram: k1_coalesce_duration_ms
  - counter: k1_rate_limit_rejections_total
```

**2. state_tracker (Conversation State Mutations)**

```
PURPOSE: Track dialogue state transitions and conversation history

IMPORTS:
  → k1.runtime.session_state (L4 - session context)
  → k1.infrastructure.metrics (L5)

EXPORTS:
  → Dialogue state mutations
  → Turn completion events

LOGIC (from ADR-0054 Turn Boundary Management):

TURN TYPES (ADR-0054a & 0054b):

1. **Implicit Turn** (ADR-0054a Implicit Pause ≥2s):
   - Trigger: 2+ seconds of silence (no messages from user)
   - Detection: scoreboard sends "coalesce_triggered" event
   - Action: Mark USER_TURN as complete, transition to SYSTEM_TURN
   - Example: User types "What's the weather" then stops for 2s

2. **Explicit Turn** (ADR-0054b Explicit Submit & UX):
   - Trigger: User clicks "Send" button or presses Enter
   - Detection: UI sends "explicit_submit" message
   - Action: Immediately complete USER_TURN, ignore remaining coalesce window
   - Example: User types partial query and clicks "Send"

MPST TURN TRANSITIONS (ADR-0054c MPST Coordination):
  - Protocol state machine: USER_TURN ↔ SYSTEM_TURN
  - Transition guard: Turn boundary event (implicit or explicit)
  - Validation: Protocol monitor (ADR-0003) ensures valid transitions
  - State: Record turn_id, turn_timestamp, intent_classified

CONVERSATION HISTORY:
  - Append to SessionState.scoreboard (ADR-0017b)
  - Each turn: {user_message, intent, agent_response, timestamp, trace_id}
  - TTL: Keep last 20 turns (configurable window)

ADR REFERENCES:
  - ADR-0054 (Turn boundary management)
  - ADR-0054a (Implicit pause ≥2s detection)
  - ADR-0054b (Explicit submit UX contracts)
  - ADR-0054c (MPST turn transitions protocol)

OBSERVABILITY:
  - counter: k1_turns_total{type} (implicit vs explicit)
  - histogram: k1_turn_duration_seconds
```

**3. turn_manager (Turn Transitions & Barge-In Handling)**

```
PURPOSE: Manage turn transitions and voice interruption (barge-in)

IMPORTS:
  → k1.infrastructure.event_bus (L5 - barge-in signals)
  → k1.infrastructure.metrics (L5)
  → k1.infrastructure.policy (L5 - voice quality)

EXPORTS:
  → Turn transition events
  → Barge-in preemption signals

LOGIC (from ADR-0057 Voice-Specific Backpressure):

BARGE-IN SUPPORT (ADR-0057a ASR Frame Drop, ADR-0057c Barge-in Preemption):
  - Definition: User interrupts system while it's responding
  - Flow:
    1. System generating response (TTS playing)
    2. User starts speaking (ASR detects voice activity)
    3. turn_manager receives barge-in signal
    4. Action: Stop TTS, flush pending output, start new USER_TURN
    5. Result: User can interrupt without waiting for full response

PREEMPTION LOGIC (ADR-0057c):
  - Detect: Voice activity detection (VAD) during SYSTEM_TURN
  - Decision: Is this a valid barge-in? (confidence >0.8)
  - Action: Preempt system response, transition to new USER_TURN
  - Latency: <120ms preemption (perceived interruption latency)

VOICE QUALITY ADAPTATION (ADR-0057b TTS Degradation Ladder):
  - If network is congested: Degrade TTS quality (compressed audio)
  - Degrade ladder: Full → Medium → Low quality
  - Trigger: When backpressure signal received from infrastructure

ADR REFERENCES:
  - ADR-0057 (Voice-specific backpressure)
  - ADR-0057a (ASR frame drop under load)
  - ADR-0057b (TTS degradation ladder)
  - ADR-0057c (Barge-in preemption <120ms)

OBSERVABILITY:
  - counter: k1_barge_in_events_total
  - histogram: k1_barge_in_preemption_latency_ms
```

**4. repair (Error Recovery & Clarification)**

```
PURPOSE: Handle dialogue failures, repair broken states, request clarification

IMPORTS:
  → k1.execution.orchestrator (L2 - saga coordinator)
  → k1.runtime.session_state (L4 - conversation history)
  → k1.infrastructure.metrics (L5)

EXPORTS:
  → Clarification requests to user
  → Repair actions (retry, escalate, fallback)
  → Compensation execution (Saga pattern, ADR-0008)

LOGIC (from ADR-0008 Saga Pattern Error Recovery):

FAILURE SCENARIOS & RECOVERY:

Scenario 1: Intent Classification Fails
  - Error: Confidence <0.4, ambiguous intent
  - Recovery: request_clarification("What did you mean by X?")
  - Re-classify: User clarification → higher confidence
  - If still failing: Escalate to HITL (human agent)

Scenario 2: Plan Execution Fails
  - Error: Tool call failed (e.g., booking API timeout)
  - Recovery: Saga pattern (ADR-0008a Compensating Transactions)
    1. Already executed: Step 1 (search) ✅
    2. Already executed: Step 2 (book) ✅
    3. Failed: Step 3 (confirm) ❌
    4. Action: Run compensations (LIFO reverse order)
       - Compensation 2: Cancel booking (delete_reservation API)
       - Compensation 1: Clear search cache
  - Result: Consistent state, error to user

Scenario 3: Safety Violation
  - Error: Content filtered by Safety Watch agent
  - Recovery: Rephrase request or escalate to user
  - Example: "Delete all user data" → Denied → "Can't fulfill that request"

COMPENSATION SEQUENCES (ADR-0008a):
  - Each step defines compensation action (reverse operation)
  - Compensation runs in LIFO order (last step first)
  - Each compensation is best-effort (may fail, continue anyway)
  - All attempts logged to K0 receipts (ADR-0020)

CLARIFICATION PROMPTS:
  - Stored as templates in prompt_library (Model Hub)
  - Customized per intent type
  - Examples:
    * Ambiguous intent: "Did you mean X or Y?"
    * Missing parameter: "For how many people?"
    * Confirmation needed: "Proceed with booking?"

ADR REFERENCES:
  - ADR-0008 (Saga pattern error recovery master)
  - ADR-0008a (Compensating transaction design)
  - ADR-0008b (Forward vs backward recovery)
  - ADR-0008c (Distributed state management)
  - ADR-0008d (Timeout/deadlock handling)

PERFORMANCE TARGETS (from ADR-0024):
  - Clarification latency: <1000ms (user-facing, acceptable)
  - Compensation execution: <5s per step (best-effort recovery)
  - Saga rollback: <10s total (all compensations complete)

OBSERVABILITY:
  - counter: k1_repair_clarifications_total{reason}
  - counter: k1_repair_compensations_total{outcome}
  - histogram: k1_repair_latency_ms
```

---

**Batch 5 Tool Execution & Dialogue Summary**

Tool Execution (5 modules) implements **2-layer architecture**:
- **Layer 1 Protocol:** MCP (80%), Direct API (20%)
- **Layer 2 Sandbox:** WASM (15%), Process (80%), Container (5%)
- **2D Matrix:** 100% tool coverage with optimal protocol + sandbox per tool
- **Security:** Capability tokens, timeout enforcement, resource limits (ADR-0010, ADR-0014)

Dialogue Management (4 modules) implements **turn-based conversation flow**:
- **Message Coalescing:** 2s window, 5-message limit (ADR-0053)
- **Turn Boundaries:** Implicit (2s pause) + Explicit (Send button) (ADR-0054)
- **Barge-In Support:** Voice interruption with <120ms preemption (ADR-0057)
- **Error Recovery:** Saga pattern with compensating transactions (ADR-0008)

### Layer 3 Dependency Graph

```
orchestrator (L2) ─→ hire_fire
                        │
                        ├─→ registry (agent specs)
                        ├─→ personality (persona adaptation)
                        └─→ active_roster (tracking)
                             │
                             ▼
                        supervisor (health monitoring)
                             │
                             ├─→ mailbox (MPSC queues)
                             └─→ Layer 4 (session_state)
                                  │
                                  └─→ model_hub/router (4 AI agents)
                                      │
                                      ├─→ placement_planner (NPU/GPU/CPU)
                                      ├─→ adapters (OpenAI, Anthropic, etc)
                                      ├─→ kv_cache_broker (cache management)
                                      ├─→ prompt_library (templates)
                                      ├─→ fallback_cascade (routing)
                                      └─→ safety_filter (Safety Watch)
                                  │
                                  └─→ tools/runner (tool execution)
                                      │
                                      ├─→ sandbox (MCP/WASM/Process)
                                      ├─→ registry (tool catalog)
                                      ├─→ adapters (protocol adapters)
                                      └─→ control (runtime management)
                                  │
                                  └─→ dialogue/* (conversation management)
```

---

## Layer 4: Runtime Core

### Module Inventory (8 modules)

#### 4a: Runtime (4 modules)

| Module | File Path | Status | Dependencies | ADR Reference |
|--------|-----------|--------|--------------|---|
| leases | `k1/runtime/leases/` | ✅ POPULATED | Layer 5 (policy) | ADR-0010 (Capability Security) |
| mailbox | `k1/runtime/mailbox/` | ✅ POPULATED | Layer 5 (metrics) | ADR-0002a (MPSC Queues) |
| session_state | `k1/runtime/session_state/` | ✅ POPULATED | Layer 5 (metrics, storage) | ADR-0017 (6-section design) |
| flow_engine | `k1/runtime/flow_engine/` | ✅ POPULATED | Layers 3, 5 (execution, storage) | ADR-0062 (DSL Executor) |

##### 4a.1: leases (Capability Token Lifecycle)

**PURPOSE:** Manage agent capability tokens with per-agent leases, delegation chains, and revocation.

**IMPORTS:**
- `k1.infrastructure.policy` (L5) - Policy definitions, constraints validation
- `k1.infrastructure.metrics` (L5) - Lease metrics (acquires, releases, timeouts)

**EXPORTS:**
- `acquire_lease(agent_id, capabilities, ttl_ms)` → Lease token (HMAC-SHA256 signed)
- `validate_lease(token)` → LeaseValidation (valid=bool, agent_id, capabilities, constraints)
- `release_lease(token)` → Success/failure
- `revoke_capability(agent_id, capability)` → All leases invalidated

**LOGIC:**

1. **Lease Acquisition** (<1ms latency):
   - Agent requests lease for specific capabilities (e.g., ["TOOL_CALL", "MODEL_ACCESS"])
   - leases module generates HMAC-SHA256 token: `token = HMAC(secret_key, agent_id + capabilities + ttl_ms + nonce)`
   - Token includes: agent_id, capabilities list, constraints (max_cost, max_invocations, privacy_band), expiration_ms
   - Token stored in in-memory HashMap: `active_leases[token] = LeaseRecord(...)`
   - Metrics: `capability_lease_acquires_total{capability}` counter incremented
   - Return token to agent

2. **Lease Validation** (<1ms latency):
   - Agent presents token for operation (e.g., "call tool X")
   - leases module verifies HMAC signature (prevents tampering)
   - Checks expiration_ms > now() (not expired)
   - Checks requested operation in capabilities list (e.g., operation="TOOL_CALL", token has "TOOL_CALL")
   - Checks constraints: cost_used < max_cost, invocations_used < max_invocations
   - Returns LeaseValidation(valid=true, agent_id, remaining_cost, remaining_invocations)

3. **Lease Release** (<200μs latency):
   - Agent calls `release_lease(token)` on completion
   - Removes from `active_leases` HashMap
   - Updates cost/invocation counters
   - Metrics: `capability_lease_releases_total{capability}` counter incremented
   - Returns success

4. **Lease Timeout** (detected every 1s scan):
   - Periodic background task checks all leases in `active_leases`
   - If lease.expiration_ms < now(): automatically revoked
   - Supervisor notified if critical capability (MODEL_ACCESS, TOOL_CALL)
   - Metrics: `capability_lease_timeouts_total{capability}` counter incremented

5. **Capability Revocation** (on-demand):
   - Admin/arbiter calls `revoke_capability(agent_id, capability)`
   - Iterates all leases for that agent, removes capability from list
   - If leases list becomes empty, lease auto-revoked
   - Metrics: `capability_revocations_total{capability}` counter incremented

**ADR REFERENCES:**
- ADR-0010 (Capability-Based Security) - Token model, delegation chains - 1513 lines
- ADR-0010a (Capability Token Design) - HMAC-SHA256, signature format
- ADR-0010b (Delegation Chains) - Transitive capability delegation
- ADR-0010c (Revocation Audit Trail) - Immutable revocation log

**PERFORMANCE TARGETS (P95):**
- Lease acquire: <1ms (HMAC signature generation)
- Lease validate: <1ms (signature verification + HashMap lookup)
- Lease release: <200μs (HashMap removal)
- Timeout scan: <5ms for 100 active leases

##### 4a.2: mailbox (Per-Agent MPSC Queues)

**PURPOSE:** Lock-free MPSC (Multi-Producer Single-Consumer) queues for all 58 agents with priority scheduling, backpressure, and fairness.

**IMPORTS:**
- `k1.infrastructure.metrics` (L5) - Queue depth, latency, drop metrics

**EXPORTS:**
- `enqueue(agent_id, message, priority)` → Success/backpressure signal
- `dequeue(agent_id)` → Message or None
- `get_queue_depth(agent_id)` → Depth counter

**LOGIC:**

1. **Queue Structure** (ADR-0002a):
   - 4-tier priority queues per agent:
     - Priority 0 (URGENT, 16 slots): Barge-in, agent crash notifications
     - Priority 1 (REALTIME, 32 slots): User messages, tool results
     - Priority 2 (INTERACTIVE, 64 slots): Agent coordination, negotiation
     - Priority 3 (BACKGROUND, 128 slots): Metrics, logging, housekeeping
   - Total capacity per agent: 240 messages
   - High watermark: 50 messages (trigger backpressure)
   - Low watermark: 25 messages (resume after backpressure)

2. **Weighted Fair Queueing (WFQ)** (prevent starvation):
   - Virtual time formula: `vt = message_size / priority_weight`
   - Weights: URGENT=4, REALTIME=3, INTERACTIVE=2, BACKGROUND=1
   - Dequeue priority: highest virtual time first
   - Aging mechanism: BACKGROUND messages promoted after 5s idle (virtual time advances)
   - Example: After 5s, BACKGROUND message vt=1.0 becomes vt=1000.0 (promoted)

3. **Backpressure Management**:
   - If queue depth > high watermark (50):
     - BACKGROUND messages dropped (oldest first)
     - INTERACTIVE messages blocked (sender waits)
     - REALTIME/URGENT messages always accepted (critical path)
   - Alert supervisor if high watermark exceeded 3x in 60s
   - Metrics: `agent_queue_backpressure_events_total{agent_id}` counter incremented

4. **Dead Letter Queue (DLQ)**:
   - Dropped messages moved to DLQ (max 100 messages, 5-minute retention)
   - Accessible via observability API: `GET /metrics/dlq?agent_id=agent_123`
   - Example usage: Debugging dropped telemetry messages

5. **Message TTL Enforcement**:
   - Each message has TTL (default: 30s)
   - On dequeue: if message.created_ms + ttl_ms < now(): discard (don't process)
   - Metrics: `agent_queue_message_ttl_expirations_total{agent_id}` counter incremented

**ADR REFERENCES:**
- ADR-0002a (Mailbox MPSC Queue Implementation) - Lock-free ring buffers - 715 lines
- ADR-0002a specifics: 4-tier priority queues, WFQ scheduler, backpressure watermarks
- ADR-0005 (Agent Lifecycle FSM) - Agents process messages in ACTIVE state
- ADR-0028 (WFQ Scheduler) - Weighted fair queueing algorithm

**PERFORMANCE TARGETS (P95):**
- Enqueue: <0.5ms (lock-free atomic operations)
- Dequeue: <0.5ms (O(1) priority selection via WFQ virtual time)
- Backpressure detection: <1ms (watermark check)

##### 4a.3: session_state (6-Section SessionState Design)

**PURPOSE:** In-memory working state with 6 clear sections, fast serialization, LRU eviction, and schema validation.

**IMPORTS:**
- `k1.infrastructure.metrics` (L5) - State size, eviction metrics
- `k1.infrastructure.storage_connector` (L5) - K0 WAL persistence

**EXPORTS:**
- `get_beliefs()`, `set_beliefs(beliefs)` → User facts, preferences
- `get_scoreboard()`, `set_scoreboard(scoreboard)` → Common ground
- `get_control()`, `set_control(control)` → Agent leases, flow state
- `serialize()` → FlatBuffers binary (delta encoding, <1ms)
- `deserialize(bytes)` → SessionState from binary

**LOGIC:**

1. **6-Section Architecture** (ADR-0017, 1137 lines):

   **Section 1: Beliefs (10-20KB, LRU eviction)**
   - Stores user facts: name, location, preferences, history
   - Data model: Dict[str, Fact] where Fact={value, confidence 0-1, source, timestamps}
   - Example facts: `{"user_name": Fact("Alice", 0.95, "user_stated"), "location": Fact("SF", 0.8, "inferred")}`
   - Eviction: When size > 20KB, evict least recently accessed facts (LRU)
   - Serialization: FlatBuffers `BeliefsSection` table with 300-600 facts

   **Section 2: Scoreboard (4-8KB, high priority LRU)**
   - Stores common ground: referents, QUD (Questions Under Discussion), context
   - Data model: Dict[str, Referent] where Referent={type, description, salience}
   - Example referents: `{"restaurant_search": Referent("search", "Italian restaurants near Union Square", 0.9)}`
   - QUD stack: Up to 3 open questions being discussed
   - Eviction: Medium priority (keep active referents, evict cold ones)
   - Serialization: FlatBuffers `ScoreboardSection` table

   **Section 3: Control (8-12KB, NEVER evict, critical)**
   - Stores active agent leases, flow state, turn lock
   - Data model: Dict[str, AgentLease] + FlowState object
   - Agent leases: agent_id → {state, lease_expires_ms, capabilities}
   - Flow state: {current_phase (negotiation/selection/execution), turn_id, timeout_ms}
   - Turn lock: Boolean flag prevents concurrent turns
   - Eviction: NEVER (if evicted during turn, orchestrator crashes)
   - Serialization: FlatBuffers `ControlSection` table

   **Section 4: Persona (2-4KB, static, low eviction priority)**
   - Stores personality model, tone settings, style preferences
   - Data model: personality_config={tone: "formal"/"casual"/"warm", response_length: "brief"/"medium"/"verbose"}
   - Example: `{"tone": "warm", "response_length": "medium", "emoji_usage": "occasional"}`
   - Rarely changes, low eviction priority
   - Serialization: FlatBuffers `PersonaSection` table

   **Section 5: Multimodal (4-8KB, medium priority LRU)**
   - Stores audio/vision state, streaming buffers, recent inputs
   - Data model: audio_state={samplerate, channels, duration_ms}, vision_frames={latest_frame_id, detected_objects}
   - Example: `{"audio": {...}, "vision": {...}, "recent_inputs": [...]}`
   - Eviction: Medium priority (keep recent, evict old video frames)
   - Serialization: FlatBuffers `MultimodalSection` + blob pointers to storage

   **Section 6: Meta (2-4KB, observability, first to evict)**
   - Stores metadata: trace_id, session_id, start_time, turn_count, performance metrics
   - Data model: {trace_id, session_id, started_at_ms, turn_count, last_turn_latency_ms}
   - Example: `{"trace_id": "abc123", "turn_count": 42, "last_turn_latency_ms": 850}`
   - Eviction: Lowest priority (observability only, first to evict under pressure)
   - Serialization: FlatBuffers `MetaSection` table

2. **Size Management & Eviction** (ADR-0018, 3-tier):
   - Soft limit: 64KB (target)
   - Hard limit: 128KB (warning)
   - OOM limit: 256KB (aggressive eviction)
   - Eviction priority: Meta (first) → Persona → Multimodal → Scoreboard → Beliefs (last) → Control (never)
   - When size > soft limit: LRU eviction within each section (remove least accessed items)
   - Metrics: `session_state_size_bytes{section}` gauge, `evictions_total{section}` counter

3. **Serialization** (ADR-0019, delta encoding):
   - FlatBuffers zero-copy format (6 schemas, one per section)
   - Delta encoding: only changed sections serialized
   - Example: If only beliefs changed, only serialize BeliefsSection (skip other 5)
   - Performance: <1ms P95 for full serialize, <200μs for delta
   - Compression: Zstd compression (optional, for K0 WAL)

4. **K0 Persistence** (checkpointing):
   - Serialize session_state to K0 WAL:
     - On turn completion (every 2-5 seconds)
     - On major state changes (persona update, new referent)
     - On session end (graceful shutdown)
   - Durable recovery: Session can resume from checkpoint (survive crash)
   - Lifecycle: 30-day retention in K0 (archived to S3 after)

5. **Memory Layout** (cache-friendly):
   - All 6 sections in single FlatBuffers root (no pointer chasing)
   - Beliefs HashMap uses Python dict (fast, cache-friendly)
   - Scoreboard HashMap similar (O(1) lookup)
   - Control section as flat struct (no indirection)
   - Multimodal section has blob pointers (external storage)
   - Example layout:
     ```
     [Root FlatBuffers Buffer]
     ├─ Beliefs offset (points to beliefs_table)
     │   └─ [Beliefs table]
     │       ├─ Fact 1, Fact 2, ... Fact N (flat array)
     ├─ Scoreboard offset (points to scoreboard_table)
     ├─ Control offset
     ├─ Persona offset
     ├─ Multimodal offset
     └─ Meta offset
     ```

**ADR REFERENCES:**
- ADR-0017 (SessionState 6-Section Design) - 1137 lines, decision matrix vs alternatives
- ADR-0017a (Beliefs Section) - User facts, confidence, LRU - 872 lines
- ADR-0017b (Scoreboard Section) - Common ground, QUD - ~850 lines
- ADR-0017c (Control Section) - Agent leases, flow state - 566 lines
- ADR-0017d (Persona Section) - Personality model, tone - ~500 lines
- ADR-0017e (Multimodal Section) - Audio/vision state - ~600 lines
- ADR-0017f (Meta Section) - Telemetry, metadata - ~500 lines
- ADR-0018 (3-Tier Eviction Strategy) - Soft/hard/OOM cascades
- ADR-0019 (FlatBuffers SessionState Serialization) - Delta encoding, zero-copy
- ADR-0020 (Multi-Tier Storage) - L1 (RAM) / L2 (SSD K0) / L3 (S3)

**PERFORMANCE TARGETS (P95):**
- Read any section: <100μs (O(1) HashMap lookup + FlatBuffers traversal)
- Write any section: <500μs (update + delta tracking)
- Serialize full: <1ms (FlatBuffers zero-copy)
- Serialize delta: <200μs (only changed sections)
- Deserialize: <1ms (FlatBuffers zero-copy deserialization)
- Eviction check: <5ms for full sweep

**MEMORY TARGETS:**
- Typical size: 30-56KB (well under 64KB soft limit)
- Size budget: 64KB soft, 128KB hard, 256KB OOM
- Per-session overhead: ~100 concurrent sessions × 50KB ≈ 5MB (very efficient)

##### 4a.4: flow_engine (Deterministic DSL Executor)

**PURPOSE:** Execute deterministic task flows (orchestration DSLs) with timeouts, error recovery, and state persistence.

**IMPORTS:**
- `k1.runtime.session_state` (L4) - Read/write state during flow
- `k1.execution.*` (L3) - Tool runners, model hub, agent orchestration
- `k1.infrastructure.storage_connector` (L5) - Persist flow checkpoints

**EXPORTS:**
- `execute(flow_dsl)` → FlowResult (status, output, latency_ms)
- `pause(flow_id)` → Checkpoint saved
- `resume(flow_id, session_state)` → Continue from checkpoint
- `abort(flow_id, reason)` → Cleanup and terminate

**LOGIC:**

1. **DSL Syntax** (7 core commands):

   ```
   // Example flow: Search restaurants and get details
   flow: search_and_details

     // 1. Await: Wait for condition
     await user_input received

     // 2. Decide: Conditional branching
     if user_message contains "restaurant"
       // 3. Call: Invoke tool or agent
       restaurant_results = call tool:search_restaurants
         query: user_message
         location: session_state.beliefs.location
         max_results: 5
     else
       reject "Please specify 'restaurant'"
       return error

     // 4. Yield: Return result (turn end)
     yield restaurant_results

     // 5. Persist: Save state checkpoint
     persist session_state.scoreboard

     // 6. Fork/Join: Parallel execution
     fork:
       details_1 = call tool:get_restaurant_details(restaurant_results[0])
       details_2 = call tool:get_restaurant_details(restaurant_results[1])
     join all

     // 7. Abort: Error recovery
     on error:
       abort reason="tool_timeout" after 30s
       cleanup:
         - cancel pending tool calls
         - restore session_state to checkpoint
   ```

2. **Execution Model**:
   - Single-threaded, cooperative multitasking
   - Timeout enforcement: Each command has max_duration_ms (default 30s)
   - State persistence: Checkpoint after Persist commands
   - Error handling: Abort block catches exceptions, executes cleanup

3. **Command Semantics**:

   **Await(condition)**: Block until condition true, timeout after 30s
   - Conditions: `user_input received`, `agent_response ready`, `tool_call succeeded`
   - Implementation: Wait on event or timer

   **Decide(condition, then_flow, else_flow)**: Conditional branching
   - Condition: `user_message contains "keyword"`, `session_state.beliefs.preference == value`
   - Example: `if user asks for reservation then call booking_agent else return search results`

   **Call(target, params)**: Invoke tool or agent
   - Targets: `tool:search_restaurants`, `agent:Planner`, `model:GPT-4`
   - Params: Pass input (query, filters, context)
   - Returns: Result with status (success/failure/timeout)
   - Timeout: 30s default (configurable per call)

   **Yield(output)**: Return from flow (turn end)
   - Output: Result to return to user
   - Side effect: Ends turn, initiates backpressure handling
   - Persist: Automatically checkpoints before yield

   **Persist(state_path)**: Save checkpoint
   - State path: `session_state`, `session_state.beliefs`, `session_state.scoreboard`
   - Implementation: Serialize selected sections to K0 WAL
   - Purpose: Enable resumption if crash occurs mid-turn

   **Fork/Join**: Parallel execution
   - `fork`: Start multiple parallel Call blocks
   - `join all`: Wait for all to complete (or timeout)
   - `join any`: Return on first completion
   - Example: Fetch details for 3 restaurants in parallel

   **Abort(reason, cleanup)**: Error recovery
   - Triggered by: timeout, exception, explicit abort
   - Cleanup: Cancel pending calls, restore checkpoint, log error
   - Example: If tool_call timeout >5s, abort and return "Service unavailable"

4. **State Machine**:
   ```
   IDLE → PAUSED (await condition)
        → EXECUTING (running commands)
        → YIELDING (return to user, checkpoint)
        → COMPLETED (success)
        → ERROR (exception caught, cleanup)
        → ABORTED (abort command)
   ```

5. **Timeout Enforcement**:
   - Each Call command: default 30s timeout (configurable)
   - Fork/Join timeout: max of all parallel calls + join overhead
   - Overall flow timeout: 60s (prevent stuck turns)
   - If timeout exceeded: Exception caught by Abort block

6. **Checkpointing & Recovery**:
   - Checkpoint format: Serialized session_state + flow_execution_context (which command, local variables)
   - Restore: Load checkpoint + resume at next command
   - Example: Turn 5 paused after restaurant search, turn 6 resumes with results ready

**ADR REFERENCES:**
- ADR-0062 (Deterministic DSL Executor) - Flow semantics, timeout enforcement
- ADR-0006 (Orchestrator 3-Phase Coordination) - flow_engine integrates with orchestration
- ADR-0008 (Saga Pattern Error Recovery) - Abort block uses saga compensations
- ADR-0014 (Tool Timeout Management) - Call command timeout enforcement

**PERFORMANCE TARGETS (P95):**
- Command execution: <100ms per command (most commands are awaits or decisions)
- Fork/Join: <500ms for parallel calls (3 tools parallel, each 150ms)
- Checkpoint save: <100ms (serialization + K0 write)
- Checkpoint restore: <50ms (load from memory, no deserialization needed)

---

#### 4b: Learning (4 modules - Adaptive Learning Loop)

| Module | File Path | Status | Dependencies | ADR Reference |
|--------|-----------|--------|--------------|---|
| learning_loop | `k1/learning/learning_loop/` | ✅ POPULATED | Layers 3, 5 | ADR-0059 (Learning Loop) |
| feedback_collector | `k1/learning/feedback_collector/` | ✅ POPULATED | Layer 5 | ADR-0059a (Feedback Signals) |
| drift_detector | `k1/learning/drift_detector/` | ✅ POPULATED | Layer 5 | ADR-0059b (Drift Detection) |
| model_updater | `k1/learning/model_updater/` | ✅ POPULATED | Layer 5 | ADR-0059c (Weight Updates) |

##### 4b.1: learning_loop (K1 Advisory-Only, K0 Persistence)

**PURPOSE:** Collect feedback, detect patterns, emit advisory recommendations (NOT directly modify state).

**IMPORTS:**
- `k1.infrastructure.metrics` (L5) - Performance metrics, signal counts
- `k1.infrastructure.config_manager` (L5) - Config hot-reload, parameter updates
- `k1.infrastructure.event_bus` (L5) - Subscribe to feedback events

**EXPORTS:**
- `process_feedback(feedback, session)` → Advisory (ADAPT or ROLLBACK recommendation)
- `emit_advisory(advisory)` → K0 P06 Gateway → K0 persistence

**LOGIC:**

1. **K0/K1 Boundary** (CRITICAL - ADR-0059):
   - ✅ K1 collects feedback signals (explicit, implicit, behavioral)
   - ✅ K1 analyzes patterns and suggests adaptations
   - ✅ K1 monitors for drift and emits rollback advisories
   - ❌ K1 NEVER persists learned state directly
   - ❌ K1 NEVER writes to SessionState
   - ❌ K1 NEVER modifies K0 databases
   - **K0 P06 FeedbackIntegration is authoritative** for persistence

2. **Advisory Generation Pipeline**:
   ```
   Feedback Input
        ↓
   feedback_collector (classify signal)
        ↓
   analyze_for_adaptation (pattern matching)
        ↓
   drift_detector (check for anomalies)
        ↓
   advisory_emitter (ADAPT or ROLLBACK)
        ↓
   K0 P06 Gateway (submit for validation + persistence)
        ↓
   K0 P06 Validation (safety, policy checks)
        ↓
   K0 Persistence + Receipt
   ```

3. **Advisory Types**:
   - **ADAPT Advisory**: Recommendation to update parameter (e.g., increase confidence threshold from 0.80 to 0.82)
   - **ROLLBACK Advisory**: Recommendation to revert parameter to prior value (detected drift)

4. **Processing Flow** (<100ms P95):
   - Receive feedback event (user thumbs-up, task completion, dwell time)
   - Classify signal type (explicit/implicit/behavioral)
   - Aggregate with recent signals (sliding window 1 hour)
   - Detect patterns (e.g., "3 thumbs-ups, user spent 2min reading response")
   - Propose adaptation (increase verbosity, save user preferences)
   - Check for drift (is parameter going too far?)
   - Emit advisory to K0 P06 gateway
   - Metrics: `learning_advisory_emitted_total{type}` counter

5. **K0 P06 Gateway Communication**:
   - Serialize advisory as protobuf/JSON
   - Send to K0 P06 over port boundary (P06 port)
   - Wait for receipt (or timeout after 5s)
   - If accepted: log success, update metrics
   - If rejected: log reason, don't retry
   - Research: Feedback loop design patterns (Russell & Norvig 2020)

**ADR REFERENCES:**
- ADR-0059 (Learning Loop Architecture) - 510 lines - K0/K1 boundary, K1 advisory-only model
- ADR-0001f (K0/K1 Boundary Enforcement) - K1 advisory signals, K0 persistence authority
- ADR-0017 (SessionState) - Beliefs section contains user preferences
- ADR-0038 (Receipt System) - Immutable receipts for all K0 operations
- ADR-0007 (Planner Pipeline) - Parameters adapted by learning loop

**PERFORMANCE TARGETS (P95):**
- Signal processing: <50ms
- Pattern analysis: <30ms
- Drift check: <20ms
- Advisory emission: <100ms total

##### 4b.2: feedback_collector (Signal Aggregation & Classification)

**PURPOSE:** Collect diverse feedback signals with 3-tier weighting and aggregate into recommendations.

**IMPORTS:**
- `k1.infrastructure.event_bus` (L5) - Subscribe to feedback events
- `k1.infrastructure.metrics` (L5) - Signal counts, classification metrics

**EXPORTS:**
- `collect(feedback, session)` → FeedbackSignal (with type, weight, polarity, context)
- `aggregate_signals(signals, window_ms)` → AggregatedSignal (weighted score)

**LOGIC:**

1. **3-Tier Signal Taxonomy** (ADR-0059a, 530 lines):

   **Tier 1: Explicit Signals (Weight: 1.0 - High Confidence)**
   - THUMBS_UP (+1.0): User 👍 button, explicit approval
   - THUMBS_DOWN (-1.0): User 👎 button, explicit rejection
   - STAR_RATING (0.0-1.0): 1-5 stars mapped to polarity
   - EXPLICIT_CORRECTION (-0.8): "No, I meant X"
   - FEATURE_REQUEST (+0.5): "Can you also do Y?"
   - REPORT_ERROR (-1.0): "That's wrong"
   - Example: Thumbs up weighted 1.0 × polarity +1.0 = +1.0 impact

   **Tier 2: Implicit Signals (Weight: 0.5 - Medium Confidence)**
   - CLARIFICATION_NEEDED (-0.6): Had to ask for clarification
   - TASK_COMPLETION (+0.8): Task completed successfully
   - REPEATED_QUERY (-0.5): Asked same thing twice
   - REFORMULATION (-0.4): Rephrased question
   - FOLLOW_UP (+0.3): Asked related question
   - TOOL_CALL_SUCCESS (+0.7): Tool execution succeeded
   - TOOL_CALL_FAILURE (-0.7): Tool execution failed
   - Example: Task completion weighted 0.5 × polarity +0.8 = +0.4 impact

   **Tier 3: Behavioral Signals (Weight: 0.2 - Low Confidence)**
   - INTERRUPTION (-0.4): User barge-in during response
   - QUICK_EXIT (-0.5): Session ended <10s
   - DWELL_TIME (0.0-1.0): Time spent on response (more = better)
   - SCROLL_DEPTH (0.0-1.0): Fraction of response read
   - COPY_TEXT (+0.6): User copied response to clipboard
   - SHARE_RESPONSE (+0.8): User shared with others
   - VOICE_TONE (0.0-1.0): Frustration/satisfaction detected by prosody analysis
   - Example: Copy-text weighted 0.2 × polarity +0.6 = +0.12 impact

2. **Signal Weighting Formula**:
   ```
   effective_score = weight × polarity
   
   where:
   - weight ∈ {1.0, 0.5, 0.2}  [Explicit, Implicit, Behavioral]
   - polarity ∈ [-1.0, +1.0]   [Negative to Positive]
   
   Total impact = sum of all signals in window
   ```
   Example aggregation (1-hour window):
   ```
   Thumbs up:          1.0 × (+1.0) = +1.00
   Task completion:    0.5 × (+0.8) = +0.40
   Copy text:          0.2 × (+0.6) = +0.12
   Dwell time (50%):   0.2 × (+0.5) = +0.10
   Quick exit:         0.2 × (-0.5) = -0.10
   ────────────────────────────────
   Total impact:                      +1.52 (positive feedback)
   ```

3. **Signal Collection** (<10ms per signal):
   - Event arrives from Layer 5 event bus (user clicked 👍)
   - Classify signal type using decision tree (Tier 1 vs 2 vs 3)
   - Calculate polarity (explicit: fixed, variable: extracted from payload)
   - Capture context: session_id, timestamp, turn_number, intent
   - Store in sliding window (1-hour window, max 1000 signals)
   - Metrics: `feedback_signal_collected_total{tier, type}` counter

4. **Signal Aggregation** (<30ms for 100 signals):
   - Aggregate signals in time window (default: 1 hour)
   - Sum weighted impacts across all signal types
   - Separate by dimension (e.g., "verbosity", "tone", "tool quality")
   - Example dimensions:
     - Verbosity dimension: Thumbs up on short answer = -0.8 (prefer brief)
     - Tone dimension: Positive feedback on formal response = +0.6 (prefer formal)
     - Tool accuracy: Tool failures = -0.7 (fix tools)
   - Return aggregated score per dimension

5. **Conflict Resolution**:
   - If thumbs up + quick exit: Resolve as mixed signal (context-dependent)
   - Explicit > Implicit > Behavioral (higher tiers override lower)
   - Recent signals > old signals (weighted recency, exponential decay)
   - Same-user signals vs cross-user (weighted by frequency)
   - Example: Thumbs up (explicit) overrides quick exit (behavioral)

**ADR REFERENCES:**
- ADR-0059a (Feedback Signal Taxonomy) - 530 lines - 3-tier signals with weights
- ADR-0059 (Learning Loop) - Integration with advisory generation
- ADR-0038 (Receipt System) - Signal logging + audit trail

**PERFORMANCE TARGETS (P95):**
- Signal collect: <10ms (decision tree classification)
- Signal aggregate: <30ms (100 signals, weighted sum)
- Conflict resolution: <5ms (max-tier selection)

##### 4b.3: drift_detector (Anomaly Detection & Safety)

**PURPOSE:** Detect when learning has gone wrong (drift detection, preventing adverse adaptations).

**IMPORTS:**
- `k1.infrastructure.metrics` (L5) - Parameter history, performance metrics
- `k1.infrastructure.config_manager` (L5) - Current parameter values

**EXPORTS:**
- `check_for_drift(parameter, new_value, session_id)` → DriftStatus (is_drift: bool, severity, reason)
- `emit_rollback_advisory()` → Advisory (type=ROLLBACK)

**LOGIC:**

1. **Multi-Layer Drift Detection** (ADR-0059b, 596 lines):

   **Layer 1: Statistical Drift** (<30ms):
   - Z-Score calculation: How many standard deviations from mean?
   - Max Z-Score threshold: 3.0 (99.7% confidence level)
   - Rate of change: Daily <20%, Weekly <40%
   - Trigger: If z_score > 3.0 or daily_change > 20%, emit drift advisory
   - Example: Confidence threshold changes from 0.80 → 0.50 (25% daily change) = DRIFT

   **Layer 2: Behavioral Drift** (<20ms):
   - User satisfaction trending down: Last 10 sessions have >50% negative feedback
   - Parameter causing worse results: Correlation analysis (parameter value vs task success)
   - Repeated clarifications: More "Say that again?" after adaptation
   - Trigger: If negative feedback increases after parameter change, emit ROLLBACK
   - Example: Changed verbosity to high, got 3 quick exits in a row = DRIFT

   **Layer 3: Safety Drift** (<10ms):
   - Parameter approaching safety boundary (e.g., confidence threshold → 0.0)
   - Conflicting with policy constraints (e.g., RED band privacy mode)
   - Estimated impact analysis: Will this break existing functionality?
   - Trigger: If approaching safety boundary, emit CRITICAL drift
   - Example: Confidence threshold → 0.30, approaching 0.0 boundary = CRITICAL DRIFT

2. **Drift Status Decision**:
   ```
   If Layer 1 (statistical): return DriftStatus(is_drift=True, severity="HIGH", reason="statistical")
   Else if Layer 2 (behavioral): return DriftStatus(is_drift=True, severity="MEDIUM", reason="behavioral")
   Else if Layer 3 (safety): return DriftStatus(is_drift=True, severity="CRITICAL", reason="safety")
   Else: return DriftStatus(is_drift=False)
   ```

3. **Drift Severity Levels**:
   - **CRITICAL**: Parameter approaches safety boundary (e.g., confidence < 0.10)
     - Action: Immediate ROLLBACK advisory (no human approval needed)
   - **HIGH**: Statistical anomaly (>3 sigma, >20% daily change)
     - Action: Emit ROLLBACK advisory, flag for review
   - **MEDIUM**: Behavioral pattern detected (negative feedback increasing)
     - Action: Emit ROLLBACK advisory, observe for confirmation
   - **LOW**: Parameter at edge but within bounds
     - Action: Log and monitor, don't emit advisory yet

4. **Parameter History Tracking**:
   - Keep per-parameter history: value, timestamp, source (user input, learning)
   - Sliding window: 30-day history for trend analysis
   - Baseline: Initial parameter value (starting point)
   - Thresholds: Min/max safe ranges per parameter
   - Example parameter tracking:
     ```
     confidence_threshold:
       - initial: 0.80
       - day 1: 0.80 (no change)
       - day 3: 0.78 (user feedback: accept lower confidence)
       - day 5: 0.75 (learning adapted)
       - day 7: 0.60 (DRIFT DETECTED: 20% daily change)
       - day 10: 0.40 (CRITICAL DRIFT: approaching 0.0 boundary)
     ```

5. **Rollback Mechanism**:
   - If drift detected: Emit ROLLBACK advisory to learning_loop
   - learning_loop sends advisory to K0 P06
   - K0 P06 executes rollback (restore parameter to prior value)
   - Metrics: `drift_detections_total{severity, reason}` counter

**ADR REFERENCES:**
- ADR-0059b (Drift Detection & Safeguards) - 596 lines - Multi-layer detection, thresholds
- ADR-0059 (Learning Loop) - Rollback advisory coordination
- ADR-0029 (Observability & Metrics) - Performance metric access for behavioral detection
- ADR-0031 (Config Hot-Reload) - Parameter value history

**PERFORMANCE TARGETS (P95):**
- Statistical check: <30ms (z-score, rate-of-change calculation)
- Behavioral check: <20ms (feedback trend analysis)
- Safety check: <10ms (boundary comparison)
- Total drift check: <60ms

##### 4b.4: model_updater (Weight Update & Config Deployment)

**PURPOSE:** Apply learning recommendations via config hot-reload (K0 executes, K1 advises).

**IMPORTS:**
- `k1.infrastructure.config_manager` (L5) - Config versions, hot-reload triggers
- `k1.infrastructure.metrics` (L5) - Updated metrics after parameter change

**EXPORTS:**
- `apply_update(advisory)` → Update confirmation (K0-executed)
- `verify_update(parameter, new_value)` → Success/failure status

**LOGIC:**

1. **Update Types** (ADR-0059c):

   **Type 1: Ranking Updates** (e.g., model routing)
   - Parameter: `model_router.weights[OpenAI] = 0.6` (was 0.5)
   - Effect: Route 60% of requests to OpenAI instead of 50%
   - K0 Trigger: Config hot-reload, no restart needed
   - Performance: <100ms deployment

   **Type 2: Planner Parameter Updates** (e.g., search depth)
   - Parameter: `planner.search_depth = 3` (was 2)
   - Effect: Consider more solution branches during planning
   - K0 Trigger: Config hot-reload on orchestrator instances
   - Performance: <100ms deployment

   **Type 3: Threshold Updates** (e.g., confidence, cost limits)
   - Parameter: `intent_classifier.confidence_threshold = 0.82` (was 0.80)
   - Effect: Require higher confidence before accepting intent
   - K0 Trigger: Config hot-reload on intent classifier agent
   - Performance: <50ms deployment

   **Type 4: Persona Adaptations** (e.g., response tone)
   - Parameter: `response_generator.tone = "formal"` (was "casual")
   - Effect: Generate more formal responses
   - K0 Trigger: Config hot-reload on response generator
   - Performance: <200ms deployment

2. **Update Application Flow** (<500ms P95):
   - Advisory received from learning_loop (e.g., "increase verbosity")
   - Classify update type (ranking, planner, threshold, persona)
   - Create config patch (old_value, new_value, timestamp, reason)
   - Send to K0 P06 for validation (safety check)
   - K0 approves/rejects (policy compliance check)
   - If approved: Deploy via config hot-reload
   - If rejected: Log reason, emit advisory error
   - Metrics: `config_updates_total{type, status}` counter

3. **Hot-Reload Mechanism** (from ADR-0031):
   - Config manager broadcasts event: `ConfigUpdated(parameter, value, timestamp)`
   - All components subscribed to config changes receive event
   - Components verify update is valid for their context
   - Components apply update (no restart)
   - Performance: <100ms for all subscribers to apply
   - Rollback available: Previous config version stored, can revert <50ms

4. **Update Verification** (<100ms):
   - After deployment: Verify parameter took effect
   - Sample metrics: Did model router actually use new weights?
   - Performance check: Did update improve latency/accuracy?
   - If verification fails: Auto-rollback to prior value
   - Metrics: `config_update_verification_total{status}` counter

5. **Gradual Rollout** (optional, for major changes):
   - Instead of 100% → 0%, apply update gradually (e.g., 10% → 20% → 50% → 100%)
   - Monitor metrics at each step
   - Rollback if degradation detected
   - Example: Increase new model weight from 5% to 50% over 1 hour

6. **Version Management**:
   - Each config version has: timestamp, reason, parameters_changed, applied_by (K0 P06)
   - Version history: Last 100 versions retained (30-day retention)
   - Rollback: Select prior version, re-deploy
   - Audit trail: Immutable log of all updates (via receipts)

**ADR REFERENCES:**
- ADR-0059c (Weight Updates & Config Deployment) - 530 lines - Update types, hot-reload
- ADR-0031 (Config Hot-Reload) - Config versioning, deployment mechanism
- ADR-0001 (K0 Memory Microkernel) - K0 P06 FeedbackIntegration persistence
- ADR-0059 (Learning Loop) - Advisory-to-update flow

**PERFORMANCE TARGETS (P95):**
- Update application: <500ms (config hot-reload + verification)
- Rollback: <100ms (restore prior config version)
- Verification: <100ms (sample metrics, check parameter effect)

---

**Learning Loop Cross-Module Coordination**:
```
feedback_collector
    ↓ (FeedbackSignal)
learning_loop
    ├─→ analyze_for_adaptation
    └─→ drift_detector (check for anomalies)
         ├─→ Statistical layer (<30ms)
         ├─→ Behavioral layer (<20ms)
         └─→ Safety layer (<10ms)
              ↓ (DriftStatus)
         ├─ If no drift: Emit ADAPT advisory
         └─ If drift: Emit ROLLBACK advisory
              ↓ (Advisory)
         K0 P06 Gateway
              ├─→ Validation (safety, policy)
              └─→ Persistence (receipt, audit trail)
                   ↓ (K0 executes)
         model_updater
              ├─→ Apply update (config hot-reload)
              └─→ Verify update (metrics check)
```

**K0/K1 Boundary Enforcement**:
- ✅ K1 (advisory): Collect signals, detect drift, propose updates
- ✅ K0 (authoritative): Validate, persist, execute, audit
- Never crossing: K1 stays advisory-only, K0 controls state

### Layer 4 Inter-Module Communication

```
Layer 3 (execution results)
    │
    ├─→ session_state (state updates)
    │    │
    │    ├─→ flow_engine (continue execution)
    │    └─→ learning_loop (feedback collection)
    │         │
    │         ├─→ feedback_collector (aggregate signals)
    │         ├─→ drift_detector (detect degradation)
    │         └─→ model_updater (update weights)
    │              │
    │              └─→ config_manager (L5) → hot reload
    │
    └─→ Layer 5 (metrics, logging, persistence)
```

---

## Layer 5: Infrastructure

### Module Inventory (19 modules)

#### 5a: Infrastructure (7 modules - Layer 5 Foundation)

| Module | File Path | Status | Exports | ADR Reference |
|--------|-----------|--------|---------|---|
| scheduler | `k1/infrastructure/scheduler/` | ✅ POPULATED | Task scheduling decisions | ADR-0028 (WFQ Scheduler) |
| backpressure | `k1/infrastructure/backpressure/` | ✅ POPULATED | Backpressure signals (3-tier) | ADR-0061 (3-Tier Cascade) |
| thermal | `k1/infrastructure/thermal/` | ✅ POPULATED | Placement decisions (thermal state) | ADR-0026 (Thermal Hysteresis) |
| budgets | `k1/infrastructure/budgets/` | ✅ POPULATED | Budget enforcement decisions | ADR-0024 (Performance Budgets) |
| cache | `k1/infrastructure/cache/` | ✅ POPULATED | Managed cache state | ADR-0025 (KV Cache Management) |
| rate_limiting | `k1/infrastructure/rate_limiting/` | ✅ POPULATED | Rate limit enforcement | ADR-TBD (Per-Intent Rate Limits) |
| storage_connector | `k1/infrastructure/storage_connector/` | ✅ POPULATED | Persistence abstraction | ADR-0020 (Multi-Tier Storage) |

##### 5a.1: scheduler (4-Tier WFQ with Anti-Starvation)

**PURPOSE:** Weighted Fair Queuing scheduler with 4 priority tiers, preemption, and anti-starvation guarantees.

**EXPORTS:**
- `schedule_task(task, priority)` → Task scheduled/deferred
- `preempt_lower_priority(urgent_task)` → Immediate execution
- `get_scheduling_decision()` → Next task to execute

**LOGIC:**

1. **4 Priority Classes** (ADR-0028, 1523 lines):

   **TIER 0: URGENT (≤50ms budget, weight=10×)**
   - Examples: Barge-in, cancel command, emergency stop
   - Preempts: All lower tiers
   - Capacity: 16 slots in urgent queue
   - Latency guarantee: 30ms P95 (50ms budget with 20ms margin)

   **TIER 1: REALTIME (≤150ms budget, weight=5×)**
   - Examples: Voice turns, model inference, tool calls, user input
   - Preempts: INTERACTIVE, BACKGROUND
   - Capacity: 32 slots
   - Latency guarantee: 120ms P95 (150ms budget with 30ms margin)

   **TIER 2: INTERACTIVE (≤300ms budget, weight=3×)**
   - Examples: UI clicks, text input, config reload, agent coordination
   - Preempts: BACKGROUND only
   - Capacity: 64 slots
   - Latency guarantee: 250ms P95 (300ms budget with 50ms margin)

   **TIER 3: BACKGROUND (≤5000ms budget, weight=1×)**
   - Examples: Learning loop, sync to K0, cache cleanup, metrics aggregation
   - Preempts: None (lowest priority)
   - Capacity: 128 slots
   - Latency guarantee: 4000ms P95 (5000ms budget with 1000ms margin)

2. **Virtual Time Fairness** (ADR-0028a):
   - Track virtual time per priority queue: `vt = accumulated_runtime / weight`
   - At each scheduling decision: Pick queue with lowest virtual time (fairest)
   - Example: After 5s of running
     ```
     URGENT:       vt = 2000ms / 10 = 200ms
     REALTIME:     vt = 1800ms / 5 = 360ms
     INTERACTIVE:  vt = 900ms / 3 = 300ms
     BACKGROUND:   vt = 500ms / 1 = 500ms
     
     Next scheduled: URGENT (lowest vt), maintains fairness
     ```

3. **Preemption Mechanism** (<5ms overhead):
   - Only URGENT tasks trigger preemption
   - When URGENT arrives: Pause current task (if not URGENT)
   - Save preempted task context (register state, local variables)
   - Execute URGENT task (typically 10-30ms)
   - Resume preempted task after 10ms delay (task switch overhead)
   - Performance: Preemption overhead <1% of turn latency

4. **Anti-Starvation Guarantee** (ADR-0028c):
   - BACKGROUND tasks guaranteed to run every 500ms
   - If BACKGROUND starved >500ms: Force-schedule next BACKGROUND task
   - Mechanism: Track time since last BACKGROUND execution
   - Alert if BACKGROUND starved >1s (investigate bottleneck)
   - Metrics: `scheduler_task_starvation_time_ms{priority}` histogram

5. **Deadline Tracking** (<1ms overhead):
   - Each task has deadline (based on priority): 50ms, 150ms, 300ms, 5000ms
   - Track elapsed time per task
   - If approaching deadline: Promote priority or fail with timeout
   - Example: REALTIME task at 140ms, 10ms left, preempt INTERACTIVE to complete

6. **CPU Yield Mechanism** (Cooperative scheduling):
   - CPU-bound tasks yield periodically (every 10ms)
   - Yield triggers scheduler to pick next task
   - Prevents any single task monopolizing CPU
   - Performance: <0.5ms yield overhead per 10ms time slice

**ADR REFERENCES:**
- ADR-0028 (Weighted Fair Queuing Scheduler) - 1523 lines - 4-tier priority, preemption, anti-starvation
- ADR-0028a (WFQ Algorithm Virtual Time) - Virtual time fairness tracking
- ADR-0028b (Priority Classes & Preemption) - URGENT preemption rules
- ADR-0028c (Starvation Prevention 500ms Max Wait) - Anti-starvation guarantee
- ADR-0024 (Performance Budgets) - Latency SLOs per tier

**PERFORMANCE TARGETS (P95):**
- Schedule decision: <2ms (heap-based O(log n))
- Preemption overhead: <5ms
- Fairness check: <1ms
- Deadline check: <1ms
- Total scheduler overhead: <1% of turn latency

##### 5a.2: backpressure (3-Tier Cascade with Voice-Specific Handling)

**PURPOSE:** Progressive backpressure cascade with per-stream watermarks, voice-specific degradation, and global resource protection.

**EXPORTS:**
- `check_backpressure(stream_id)` → BackpressureStatus (NORMAL/WARN/DEGRADE/REJECT)
- `apply_degradation(action, target)` → Applied or deferred
- `get_queue_depth()` → Utilization metrics

**LOGIC:**

1. **3-Tier Backpressure Cascade** (ADR-0061, 1013 lines):

   **Tier 1: Per-Stream Watermarks** (<5ms check):
   - Stream types: `audio_frames`, `agent_mailbox`, `k0_outbox`, `sse_subscribers`
   - Monitor queue depth per stream independently
   - Stream-specific overflow policies:
     - audio_frames: Drop oldest frame (audio tolerable)
     - agent_mailbox: Block sender (control messages are critical)
     - k0_outbox: Merge deltas (compress state updates)
     - sse_subscribers: Disconnect slow clients (prevent hogging)

   **Tier 2: Voice Pipeline Stages** (<10ms check):
   - 5 voice processing stages: ASR input → Intent queue → Tool executor → TTS queue → Audio output
   - Stage-specific degradation actions:
     ```
     ASR input queue (50%):    Downsample audio 16kHz→8kHz
     ASR input queue (80%):    Drop partial frames
     Intent queue (75%):       Shed ephemeral tools (non-critical)
     TTS queue (80%):          Degrade TTS quality (fast mode)
     Audio output (95%):       Fast-forward playback (skip silence)
     ```

   **Tier 3: Global Resource Limits** (<3ms check):
   - Total memory limit: 512MB for all queues combined
   - Total queue items limit: 5000 items across all streams
   - Sustained overload detection: >10s continuous backpressure triggers alert
   - Action: Force-shed BACKGROUND tasks, alert operators

2. **Watermark Levels** (ADR-0061a):
   - **Green (0-50%)**: Normal operation, no action
   - **Yellow (50-75%)**: Warnings emitted, metrics alert
   - **Orange (75-90%)**: Degradation actions activated
     - Drop oldest BACKGROUND messages
     - Reduce cache hit timeout (faster misses)
     - Shed non-essential async tasks
   - **Red (90-95%)**: Aggressive shedding
     - Drop all non-CRITICAL messages
     - Emergency garbage collection
     - Close idle connections
   - **Critical (95%+)**: Reject new requests
     - Block all new sessions except CRITICAL
     - Force-migrate non-critical tasks to async queue
     - Invoke emergency shutdown procedures

3. **Per-Stream Overflow Actions** (ADR-0061a):
   ```
   Per-Stream Backpressure Logic:
   
   If queue_depth > high_watermark (50 messages):
     case stream_type:
       "audio_frames":      Drop oldest frame  (audio loss tolerable)
       "agent_mailbox":     Block sender      (control critical)
       "k0_outbox":         Merge deltas      (compress updates)
       "sse_subscribers":   Disconnect slow   (prevent hogging)
   
   If queue_depth > critical (95 messages):
     All streams: Force FIFO drain (drop oldest regardless)
   ```

4. **Voice-Specific Degradation Ladder** (ADR-0057 integration):
   - When voice pipeline stages overloaded: Graceful degradation
   - Example sequence under sustained load:
     ```
     T+0s:   Normal voice processing (16kHz ASR, normal TTS)
     T+5s:   ASR input 60%: Downsample to 8kHz (still intelligible)
     T+10s:  Intent queue 75%: Drop non-critical tools (e.g., weather forecast)
     T+15s:  TTS queue 80%: Switch to fast mode (slight speed increase)
     T+20s:  Audio output 95%: Skip silence during TTS playback
     
     Result: User still hears response but slightly lower quality
     vs Binary failure at 100% (no response at all)
     ```

5. **Priority-Based Bypass** (ADR-0061c):
   - RED band operations BYPASS backpressure limits:
     - Arbiter approval decisions
     - Safety policy enforcement
     - Emergency shutdown commands
   - Rationale: Safety/privacy never blocked by resource pressure

6. **Observability & Alerts** (ADR-0061b):
   - Metrics: `queue_depth_items{stream_type}` gauge
   - Metrics: `backpressure_actions_total{action_type}` counter
   - Alerts: At yellow (75%), orange (90%), red (95%) watermarks
   - Grafana dashboard: Real-time queue visualization

**ADR REFERENCES:**
- ADR-0061 (3-Tier Backpressure Cascade) - 1013 lines - Per-stream, voice-specific, global tiers
- ADR-0061a (Watermark Thresholds) - Green/Yellow/Orange/Red/Critical definitions
- ADR-0061b (RED Metrics & Alerts) - Observability + alerting
- ADR-0061c (Privacy Band Overrides) - RED band bypass rules
- ADR-0057 (Voice-Specific Backpressure) - ASR/TTS degradation ladder

**PERFORMANCE TARGETS (P95):**
- Backpressure check: <5ms (per-stream watermarks)
- Degradation action: <10ms (drop frame, merge delta)
- Global check: <3ms (total memory, item count)
- Total backpressure overhead: <2% of turn latency

##### 5a.3: thermal (Hysteresis Matrix with 5°C Buffer)

**PURPOSE:** NPU/GPU/CPU temperature monitoring with hysteresis-based thermal placement decisions.

**EXPORTS:**
- `get_thermal_state()` → State (COOL/WARM/HOT/CRITICAL)
- `get_placement_decision(task)` → Target (NPU/GPU/CPU/Remote)
- `thermal_alert(severity)` → Alert to operators

**LOGIC:**

1. **Thermal State Machine** (ADR-0026, with hysteresis):
   - **COOL State** (≤40°C): All hardware available
     - Model hub prefers NPU (fastest, lowest power)
     - Cache operations prefer GPU memory
   - **WARM State** (40°C-50°C, but don't downgrade until 50°C-5°C=45°C):
     - NPU available but not preferred (reducing load)
     - GPU memory limited to 80% utilization
   - **HOT State** (50°C-60°C, upgrade until 60°C-5°C=55°C):
     - NPU disabled, switch to GPU+CPU
     - GPU limited to 60% utilization
     - Cache operations demoted to CPU memory
   - **CRITICAL State** (>60°C):
     - All accelerators disabled
     - CPU-only execution (slowest, but thermal-safe)
     - Non-critical tasks deferred to cool down

2. **Hysteresis Logic** (5°C buffer prevents oscillation):
   - **Upgrade threshold**: 40°C (enter WARM)
   - **Downgrade threshold**: 40°C - 5°C = 35°C (back to COOL)
   - **Rationale**: Without hysteresis, temps would oscillate between 40-42°C, causing thrashing
   - Example:
     ```
     T=0s:   Temp=38°C (COOL state)
     T+1s:   Temp=41°C (trigger WARM state) → Switch GPU→CPU
     T+2s:   Temp=38°C (would go back COOL, but hysteresis blocks it)
     T+3s:   Temp=36°C (now 36 < 35°C threshold, return to COOL)
     
     vs without hysteresis (thrashing):
     T+1s:   Temp=41°C → WARM
     T+2s:   Temp=38°C → COOL
     T+3s:   Temp=41°C → WARM  (oscillating!)
     ```

3. **Placement Decisions** (Model hub uses thermal state):
   - **COOL**: Route to NPU (10ms per token, lowest latency)
   - **WARM**: Route to GPU (15ms per token, moderate)
   - **HOT**: Route to CPU (50ms per token, slow)
   - **CRITICAL**: Queue and defer (wait for cool-down)
   - Metrics: `thermal_placement_decisions_total{target}` counter

4. **Temperature Monitoring** (<1ms per check):
   - Poll hardware temp sensors every 5s
   - Average over 1-minute window (smooth spikes)
   - Alert if sustained >60°C for >30s
   - Track peak temps for capacity planning

5. **Thermal Throttling** (Graceful degradation):
   - If CRITICAL: Reduce model batch size (1 token at a time instead of 4)
   - If HOT: Reduce model parallelism (serial processing)
   - Goal: Continue operation, just slower, until cool-down

**ADR REFERENCES:**
- ADR-0026 (Thermal Management with Hysteresis Matrix) - 5°C buffer explicit
- ADR-0026a (Temperature Monitoring) - Sensor integration
- ADR-0026b (Hysteresis Logic) - Prevent oscillation
- ADR-0026c (Placement Decisions) - NPU/GPU/CPU selection
- ADR-0027 (Model Placement Cascade) - Integration with model_hub

**PERFORMANCE TARGETS (P95):**
- Temperature check: <1ms per read
- Placement decision: <100μs (state lookup)
- Thermal alert: <50ms propagation

##### 5a.4: budgets (Hierarchical Resource Limits)

**PURPOSE:** Multi-dimension budget enforcement (tokens, dollars, compute, latency) with per-session and per-user limits.

**EXPORTS:**
- `check_budget(dimension, amount)` → Allowed/Denied + remaining
- `consume_budget(dimension, amount)` → Consumed (or blocked if over limit)
- `reset_budget(period)` → Daily/hourly reset

**LOGIC:**

1. **Budget Dimensions** (ADR-0024, hierarchical):

   **Dimension 1: Token Budget** (Model input/output tokens):
   - Global limit: 10M tokens/day (all sessions)
   - Per-session limit: 100K tokens/session
   - Per-user limit: 1M tokens/day
   - Per-request limit: 4K tokens max (OpenAI context limit)
   - Enforcement: REJECT request if over limit

   **Dimension 2: Dollar Budget** (API call costs):
   - Global limit: $100/day (model API costs)
   - Per-session limit: $1/session (cost cap per conversation)
   - Per-user limit: $10/day (user spending limit)
   - Per-request limit: $0.10 max per request
   - Enforcement: Fall back to cheap model if limit approached

   **Dimension 3: Compute Budget** (CPU/GPU time):
   - Global limit: 1000 CPU-seconds/day
   - Per-session limit: 10 CPU-seconds/session
   - Per-agent limit: 1 CPU-second per agent action
   - Enforcement: TIMEOUT after limit exceeded

   **Dimension 4: Latency Budget** (Response time SLOs):
   - TTFT (Time To First Token): <150ms P95
   - E2E Turn: <2000ms P95
   - Intent Classification: <50ms P95
   - Tool Call: <3000ms P95
   - Enforcement: Return cached result or approximate answer if budget exceeded

2. **Budget Hierarchy** (Parent-child structure):
   ```
   Global Budget (daily)
       ├─→ Per-User Budget (daily)
       │   ├─→ Per-Session Budget (lifetime)
       │   └─→ Per-Request Budget (single request)
       └─→ Per-Dimension Budget (tokens, $, compute, latency)
   ```

3. **Budget Tracking** (<5ms overhead):
   - Track consumed vs. limit per dimension
   - Atomically deduct on each operation
   - Alert at 80% utilization
   - Block at 100% utilization
   - Metrics: `budget_consumed_total{dimension}` counter, `budget_remaining_bytes{dimension}` gauge

4. **Reset Policies**:
   - Token budget: Daily reset (UTC midnight)
   - Dollar budget: Monthly reset (1st of month)
   - Session budget: Never reset (lifetime cap)
   - Request budget: Per-request fresh

5. **Escalation Path** (When over budget):
   - First: Warn user ("Approaching token limit")
   - Second: Use cheaper model (GPT-3.5 instead of GPT-4)
   - Third: Return shorter response
   - Final: Reject request with explanation

**ADR REFERENCES:**
- ADR-0024 (Performance Budgets & SLOs) - Latency targets
- ADR-0024a (TTFT Budget <150ms)
- ADR-0024b (E2E Turn Budget <2000ms)
- ADR-0031 (Cost Tracking Hierarchical) - Token, dollar, compute budgets
- ADR-0031a (Hierarchical Budgets) - Global/per-user/per-session structure
- ADR-0031b (Per-Session Budgets) - Session-level enforcement

**PERFORMANCE TARGETS (P95):**
- Budget check: <1ms (O(1) lookup)
- Budget consume: <2ms (atomic deduct)
- Remaining calc: <1ms (subtraction)

##### 5a.5: cache (128MB KV + 64MB Prompt with LRU-LFU Hybrid)

**PURPOSE:** Shared model KV cache (128MB) and prompt template cache (64MB) with LRU-LFU hybrid eviction.

**EXPORTS:**
- `get_kv_cache_hit(session_id, model_id)` → CacheEntry or None
- `put_kv_cache(session_id, model_id, kv_state)` → Stored
- `get_prompt_cache(intent, tone)` → Template or None

**LOGIC:**

1. **Cache Architecture**:

   **KV Cache (128MB)**:
   - Stores model key-value attention states
   - Shared across all sessions
   - Per-entry metadata: session_id, model_id, timestamp, hit_count
   - Example: After running GPT-4 inference, cache 8KB of KV state for next turn
   - Hit rate target: 70% (saves 7 out of 10 model calls)

   **Prompt Cache (64MB)**:
   - Stores frequently used prompt templates
   - Examples: "You are a helpful assistant", system prompts for Planner
   - Per-entry metadata: intent, tone, timestamp, hit_count
   - Hit rate target: 85% (saves 85% of prompt token cost)

2. **LRU-LFU Hybrid Eviction** (ADR-0025, eviction strategy):
   - **LRU (Least Recently Used)**: Prioritize recency (last_access_time)
   - **LFU (Least Frequently Used)**: Prioritize popularity (hit_count)
   - **Hybrid formula**: `score = 0.6 × recency + 0.4 × frequency`
   - Eviction: Drop lowest score when cache full
   - Example:
     ```
     Entry A: Last accessed 10s ago, 100 hits, score = 0.6×(1-10/(10+20)) + 0.4×(100/200) = 0.4
     Entry B: Last accessed 1s ago, 10 hits, score = 0.6×(1-1/(10+20)) + 0.4×(10/200) = 0.56
     
     Evict Entry A (lower score), keep Entry B (more recent)
     ```

3. **3-Tier Eviction** (ADR-0018 integration):
   - **Soft (50% used, 64MB)**: Normal, no eviction
   - **Hard (75% used, 96MB)**: Aggressive LRU eviction
   - **OOM (90% used, 115MB)**: Emergency eviction, clear all LFU entries

4. **Compression** (Zstd):
   - Compress KV entries if >1KB
   - Compression ratio ~3:1 typical
   - Decompression <1ms per entry
   - Trade-off: CPU time for memory savings

5. **Per-Session Isolation**:
   - Each session can cache up to 5MB (KV cache quota)
   - Prevents single session monopolizing cache
   - Metrics: `cache_hit_rate{type}` gauge, `cache_evictions_total{tier}` counter

**ADR REFERENCES:**
- ADR-0025 (KV Cache Management 128MB) - LRU-LFU hybrid eviction
- ADR-0025a (Eviction Strategy LRU-LFU) - Hybrid scoring
- ADR-0025b (Compression with Zstd) - Memory savings
- ADR-0025c (Memory Tiering) - L1 (RAM) vs L2 (SSD) cache
- ADR-0019 (FlatBuffers Serialization) - KV state format

**PERFORMANCE TARGETS (P95):**
- Cache lookup: <100μs (hash table O(1))
- Cache insert: <500μs (compression + eviction check)
- Eviction: <5ms (LRU-LFU score calculation, removal)
- Hit rate: 70% KV, 85% prompt cache

##### 5a.6: rate_limiting (Token Bucket per-Intent with Drift Detection)

**PURPOSE:** Per-intent rate limiting with token bucket algorithm and adaptive drift detection.

**EXPORTS:**
- `check_rate_limit(intent, user_id)` → Allowed/Denied
- `consume_token(intent, amount)` → Tokens consumed or deferred
- `get_available_tokens(intent)` → Current available tokens

**LOGIC:**

1. **Token Bucket Algorithm**:
   - Per-intent bucket with token capacity (e.g., 10 tokens max)
   - Tokens refill at rate (e.g., 1 token per second = 60 tokens/min)
   - On request: Check if ≥1 token available
   - If yes: Consume token, allow request
   - If no: Defer request (queue or reject)
   - Burst allowance: Up to N tokens can accumulate

2. **Per-Intent Limits** (ADR-TBD - Rate Limiting):
   - search_restaurants: 10 requests/min (burst: 20)
   - book_hotel: 5 requests/min (burst: 10)
   - check_weather: 30 requests/min (burst: 60)
   - Default: 5 requests/min, burst 10

3. **Gradual Backoff** (Not sudden drop):
   - If approaching limit (80% utilized): Start queuing requests (FIFO)
   - Queue retention: 30s timeout
   - If queue fills: Reject new requests with "Queue full" message
   - Instead of: Immediate reject with "Rate limit exceeded"
   - User experience: Slight delay, not error

4. **Drift Detection** (ADR-0059 integration):
   - Detect unusual patterns (sudden spike in requests for one intent)
   - Example: Normal "check_weather" = 1 req/min, suddenly 10 req/min
   - Alert: Possible abuse or user frustration (repeated retries)
   - Action: Investigate or temporarily increase limit

**ADR REFERENCES:**
- ADR-TBD (Per-Intent Rate Limiting)
- ADR-0028 (Scheduler) - BACKGROUND rate limiting
- ADR-0061 (Backpressure) - Queue management integration

**PERFORMANCE TARGETS (P95):**
- Rate limit check: <100μs (O(1) token bucket)
- Token consumption: <100μs (atomic decrement)

##### 5a.7: storage_connector (Persistence Abstraction Layer)

**PURPOSE:** Abstract persistence layer supporting multi-tier storage (L1 RAM, L2 SSD K0 WAL, L3 S3 archive).

**EXPORTS:**
- `read(key, tier)` → Data (from L1, L2, or L3 based on tier)
- `write(key, data, tier)` → Stored
- `sync_to_tier(key, src_tier, dst_tier)` → Migrated
- `delete(key)` → Deleted from all tiers

**LOGIC:**

1. **3-Tier Storage Architecture** (ADR-0020):

   **Tier L1: RAM (Hot, <1ms latency)**
   - Current session state, active models, recent cache
   - Capacity: ~100MB per K1 instance
   - Retention: Session lifetime only (lost on crash)
   - Use case: Active state, performance-critical

   **Tier L2: SSD K0 WAL (Warm, <10ms latency)**
   - SessionState checkpoints, operation receipts, learning advisories
   - Capacity: 10GB K0 persistent storage
   - Retention: 30 days (rotating log)
   - Use case: Durable recovery, compliance audit
   - Format: WAL (Write-Ahead Log) entries, append-only

   **Tier L3: S3 (Cold, <100ms latency)**
   - Archived sessions, historical data, analysis datasets
   - Capacity: Unlimited (S3 scale)
   - Retention: 1 year (configurable)
   - Use case: Long-term analytics, compliance archive
   - Format: Compressed + partitioned by date

2. **Data Lifecycle**:
   ```
   Write to L1 (RAM)
       ↓ (sync interval, 5s or session end)
   Write to L2 (K0 WAL)
       ↓ (after 24 hours or 1MB accumulated)
   Move to L3 (S3 archive)
       ↓ (after 30 days)
   Delete from L2
   ```

3. **Migration Strategy**:
   - L1 → L2: Synchronous on session end, async every 5s (batch operations)
   - L2 → L3: Scheduled batch job (daily at 2am UTC)
   - L3 → L1: On-demand read (user requests old session) with caching

4. **Read Path** (<5ms average):
   - Try L1 first (fast path, usually hits)
   - Fall back to L2 (durable recovery)
   - Fall back to L3 (archive retrieval, slower)
   - Cache read result in L1 for future access

5. **Write Path** (<1ms L1, <10ms L2):
   - Write to L1 immediately (return success)
   - Queue L2 sync (background thread)
   - Periodic flush to K0 WAL (via k0_bridge)

**ADR REFERENCES:**
- ADR-0020 (Multi-Tier Storage L1/L2/L3) - RAM/SSD/S3 architecture
- ADR-0020a (L1 RAM Tier) - Hot data
- ADR-0020b (L2 SSD K0 WAL) - Warm, durable
- ADR-0020c (L3 S3 Cold Archive) - Cold, long-term
- ADR-0019 (FlatBuffers Serialization) - Storage format

**PERFORMANCE TARGETS (P95):**
- L1 read: <1ms (in-memory)
- L2 write: <10ms (SSD K0 WAL)
- L3 archive: <100ms (S3)
- Migration: <50ms per batch

#### 5b: Safety & Policy (3 modules - Layer 5 Safety Foundation)

| Module | File Path | Status | Exports | ADR Reference |
|--------|-----------|--------|---------|---|
| policy | `k1/safety/policy/` | ✅ POPULATED | Band-based egress rules | ADR-0032 (Band-Based Egress) |
| pii_detector | `k1/safety/pii_detector/` | ✅ POPULATED | PII redaction markers + vault | ADR-0035 (PII Detection) |
| arbiter | `k1/safety/arbiter/` | ✅ POPULATED | RED band approval decisions | ADR-0052 (Enhanced HITL) |

##### 5b.1: policy (4-Tier Band-Based Egress with iptables/chroot/seccomp/cgroups)

**PURPOSE:** Enforce privacy band network and filesystem access policies (GREEN/AMBER/RED/BLACK) at OS level via multi-layer egress controls.

**EXPORTS:**
- `get_egress_policy(band)` → Egress rules (network, filesystem, syscall, resource)
- `enforce_egress(tool_pid, band)` → Applied iptables/chroot/seccomp/cgroups
- `log_violation(violation_event)` → Audit trail to K0

**LOGIC:**

1. **4 Privacy Bands** (ADR-0032, 1848 lines):

   **GREEN Band** (Unrestricted):
   - Network: Internet access allowed (all domains whitelisted)
   - Filesystem: /opt/tools/green/* (read-write)
   - Syscalls: All allowed (no seccomp filtering)
   - Resources: CPU 50%, memory 512MB
   - Example tools: weather_api, news_feed, public_search
   - Enforcement: None (minimal overhead)

   **AMBER Band** (Restricted, monitoring required):
   - Network: Whitelist only (e.g., api.weather.com, api.maps.google.com)
   - Filesystem: /opt/tools/amber/* (read-write), read-only /opt/shared/configs
   - Syscalls: Allowed except spawn (no fork/execve)
   - Resources: CPU 20%, memory 256MB
   - Example tools: email_sender, calendar_updater, notification_service
   - Enforcement: iptables, chroot jail (read-only mounts for configs)
   - PII Handling: All output redacted (via pii_detector)

   **RED Band** (Highest sensitivity, human approval):
   - Network: LOCAL ONLY (127.0.0.1, no remote)
   - Filesystem: /opt/tools/red/* (read-write), NO system access
   - Syscalls: Minimal (no fork, no mount, no ptrace)
   - Resources: CPU 5%, memory 64MB
   - Example tools: financial_transfer, health_record_access, legal_document_sign
   - Enforcement: iptables (drop all remote), chroot strict jail, seccomp-bpf kill
   - Access Control: Requires arbiter approval before execution
   - Audit: 100% operation logging to K0 ToolReceipt

   **BLACK Band** (Disabled):
   - No tools execute in BLACK band
   - Used for dangerous operations (kernel manipulation, system takeover)
   - Example: format_disk, enable_sudo, install_malware (never allowed)

2. **Multi-Layer Egress Enforcement** (ADR-0032, 4-tier OS-level):

   **Layer 1: Network Egress (iptables)**
   ```
   GREEN band:   Allow all (0.0.0.0/0)
   AMBER band:   Whitelist only (api.weather.com, api.maps.google.com)
   RED band:     LOCAL only (127.0.0.1/32)
   
   Implementation (per-tool):
   iptables -A OUTPUT --pid-owner $TOOL_PID -d 10.0.0.0/8 -j DROP
   iptables -A OUTPUT --pid-owner $TOOL_PID -d 192.168.0.0/16 -j DROP
   iptables -A OUTPUT --pid-owner $TOOL_PID -d 0.0.0.0/8 -j DROP
   (drop private IPs, allow public IPs for GREEN/AMBER)
   ```

   **Layer 2: Filesystem Egress (chroot + mount)**
   ```
   GREEN band:   /opt/tools/green/* (read-write)
   AMBER band:   /opt/tools/amber/* (read-write), /opt/shared/configs (read-only)
   RED band:     /opt/tools/red/* (read-write only), system paths read-only
   
   Implementation (chroot jail):
   chroot /opt/tools/amber /bin/sh -c "run_tool"
   (tool sees /opt/tools/amber as root /, cannot access /etc/passwd)
   ```

   **Layer 3: Syscall Egress (seccomp-bpf)**
   ```
   GREEN band:   All syscalls allowed
   AMBER band:   Deny fork, execve, mount, ptrace
   RED band:     Deny fork, execve, mount, ptrace, socket (LOCAL socket only)
   
   Implementation (seccomp filter):
   seccomp -m allow -s fork -s execve -s mount -s ptrace
   (if tool calls fork: SECCOMP_RET_KILL, process killed)
   
   Performance: <100ns per syscall (kernel-enforced, 0 overhead)
   ```

   **Layer 4: Resource Egress (cgroups)**
   ```
   GREEN band:   CPU 50%, memory 512MB, 256 file descriptors
   AMBER band:   CPU 20%, memory 256MB, 128 file descriptors
   RED band:     CPU 5%, memory 64MB, 32 file descriptors
   
   Implementation (cgroups v2):
   echo "500000" > /sys/fs/cgroup/k1-amber/cpu.max (50% CPU)
   echo "268435456" > /sys/fs/cgroup/k1-amber/memory.max (256MB)
   (if tool exceeds: kernel OOM killer terminates process)
   ```

3. **Violation Logging** (ADR-0032d):
   - Detect: iptables DROP (network), seccomp KILL (syscall), cgroups OOM (resource)
   - Log event: violation_event(tool_id, band, violation_type, target, timestamp)
   - Store: K0 ToolReceipt with audit trail (WHO, WHAT, WHEN, WHY)
   - Alert: Operator notification for RED band violations
   - Example:
     ```
     Violation: tool_id=weather_api, band=AMBER, type=NETWORK_DENY
     Target: attacker.com (not whitelisted)
     Timestamp: 2025-10-17 14:23:45 UTC
     Action: Connection blocked, violation logged
     ```

4. **Performance Impact** (ADR-0032a):
   - Firewall setup: <10ms per tool launch
   - Runtime overhead: 0% (kernel-enforced, no user-space checks)
   - Cleanup: Automatic on tool termination (iptables rules expire)
   - Scaling: Tested with 100 concurrent tools (no degradation)

5. **Compatibility** (ADR-0032a, ADR-0032b, ADR-0032c):
   - Linux: iptables, chroot, seccomp-bpf, cgroups (production)
   - macOS: pfctl firewall, sandbox-exec, resource limits (supported)
   - Windows: Windows Firewall API, AppContainer, job objects (future)

**ADR REFERENCES:**
- ADR-0032 (Band-Based Egress Rules) - 1848 lines - 4-layer OS enforcement
- ADR-0032a (Network Egress Control iptables) - Private IP blocking
- ADR-0032b (Filesystem Egress Control chroot + seccomp) - Jail isolation
- ADR-0032c (Resource Egress Control cgroups) - CPU/memory limits
- ADR-0032d (Egress Violation Logging Audit Trail) - Compliance audit
- ADR-0010 (Capability-Based Security) - Fine-grained access control

**PERFORMANCE TARGETS (P95):**
- Egress policy lookup: <100μs (hash map)
- Firewall setup: <10ms per tool
- Runtime overhead: 0% (kernel-enforced)
- Violation detection: <10ms (kernel event)

##### 5b.2: pii_detector (Hybrid Regex + BERT-NER with AES-256-GCM Vault)

**PURPOSE:** Detect and redact personally identifiable information (PII) using hybrid regex + ML-based NER with encrypted vault storage.

**EXPORTS:**
- `detect_pii(text)` → List of (pii_type, span, confidence, redacted_text)
- `redact_pii(text, pii_list)` → Text with placeholders ([SSN], [CREDIT_CARD], etc.)
- `vault_pii(pii_value, pii_type)` → Encrypted vault ID
- `get_vault_item(vault_id)` → Decrypted PII (requires HSM/KMS key)

**LOGIC:**

1. **3-Tier PII Detection Cascade** (ADR-0035, 1627 lines):

   **Tier 1: Regex Patterns** (<1ms, 85% recall):
   ```
   PII Type              Pattern                    Recall  False Positive Rate
   ─────────────────────────────────────────────────────────────────────────
   SSN                   \d{3}-\d{2}-\d{4}          95%     0%
   Credit Card           \d{4}[-\s]?\d{4}[-\s]?\d{4}[-\s]?\d{4}  90%  0.1%
   Phone Number          \+?1?\s?(\d{3})[-.\s]?(\d{3})[-.\s]?(\d{4})  90%  0.5%
   Email                 [a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}  99%  0%
   Date of Birth         (0[1-9]|1[0-2])[/-](0[1-9]|[12]\d|3[01])[/-](\d{4})  80%  2%
   Medical Record ID     [A-Z]{2}\d{6}[A-Z]  85%  1%
   Insurance ID          [A-Z]{2}\d{8}  80%  5%
   Passport Number       [A-Z0-9]{8,9}  70%  10%
   Driver License        [A-Z]{1,2}\d{4,8}  65%  15%
   Address (Pattern)     \d+\s+[A-Za-z\s]+,\s+[A-Za-z]{2}\s+\d{5}  60%  20%
   Zip Code              ^\d{5}(-\d{4})?$  50%  30%
   Bank Account          \d{8,17}  40%  50%
   HIPAA PHI             (medical|health|patient|hospital|diagnosis)  30%  40%
   ```
   - Performance: <1ms for 500 character text
   - Output: List of matches with exact span positions

   **Tier 2: BERT-NER Model** (5-50ms, +10% recall, <1% false positive):
   - Model: bert-base-cased + spaCy NER fine-tuned on PII
   - Input: Remaining text after regex filtering
   - Output: Named entity predictions (PERSON, LOCATION, ORGANIZATION, MEDICAL)
   - Mapping:
     ```
     PERSON → potential name, address, phone (unstructured)
     LOCATION → potential address, travel destination
     ORGANIZATION → company name, medical provider
     MEDICAL → disease, medication, procedure, symptoms
     ```
   - Example:
     ```
     Text: "John Doe at Mount Sinai Hospital was diagnosed with diabetes"
     Regex: (none matched)
     NER: PERSON="John Doe", LOCATION="Mount Sinai Hospital", MEDICAL="diabetes"
     Redactions: [NAME], [HOSPITAL], [DIAGNOSIS]
     ```

   **Tier 3: Confidence Scoring** (0.0-1.0):
   - Regex confidence: High (0.95-1.0, precise patterns)
   - NER confidence: Model score (0.7-0.95, contextual)
   - Thresholds:
     - Confidence >0.85: Redact immediately
     - Confidence 0.70-0.85: Redact with audit note
     - Confidence <0.70: Flag for manual review (don't auto-redact)

2. **Redaction Strategy** (ADR-0035a):
   ```
   PII Type               Placeholder
   ─────────────────────────────────────
   SSN                    [SSN]
   Credit Card            [CREDIT_CARD]
   Phone                  [PHONE]
   Email                  [EMAIL]
   Date of Birth          [DOB]
   Name                   [NAME]
   Address                [ADDRESS]
   Medical Condition      [DIAGNOSIS]
   Insurance ID           [INSURANCE_ID]
   
   Example:
   Original: "John Doe's SSN is 123-45-6789, call 555-1234"
   Redacted: "[NAME]'s SSN is [SSN], call [PHONE]"
   Vault IDs: pii_001, pii_002, pii_003 (encrypted)
   ```

3. **Encryption Vault** (ADR-0035c, AES-256-GCM):
   - Storage: K0 pii_vault table
   - Encryption: AES-256-GCM with:
     - Key: HSM or AWS KMS (never in K1 memory)
     - Nonce: Random 96-bit per PII value
     - Additional Auth Data (AAD): user_id + pii_type
   - Example:
     ```
     Input: pii_value="123-45-6789", pii_type="SSN", user_id="user_001"
     Encrypted: aes_256_gcm(key, nonce, pii_value, aad=user_id)
     Vault entry: {
       vault_id: "pii_001",
       ciphertext: 0xABCD...,
       nonce: 0x1234...,
       pii_type: "SSN",
       user_id: "user_001",
       created_at: "2025-10-17T14:23:45Z",
       access_log: [...]
     }
     ```

4. **Redaction Locations** (Defense in depth):
   - **SessionState:** Redact before storing (no plaintext in memory)
   - **LLM Prompts:** Redact before sending to OpenAI/Anthropic
   - **Observability Logs:** Redact in OpenTelemetry and Grafana
   - **K0 Receipts:** Redact in audit trail (compliance)
   - Example flow:
     ```
     User Input: "My SSN is 123-45-6789"
     ↓ (pii_detector)
     Detect: SSN=[SSN], vault_id=pii_001
     ↓ (redact)
     Redacted: "My SSN is [SSN]"
     ↓ (store SessionState)
     beliefs["user_input"] = "My SSN is [SSN]"
     ↓ (send LLM)
     prompt = "User said: My SSN is [SSN]"
     ↓ (log)
     logger.info("User input", message="My SSN is [SSN]")
     ```

5. **Privacy Bands Integration** (ADR-0035 + ADR-0032):
   - GREEN: No redaction required (no PII concern)
   - AMBER: Redaction required + PII audit logging
   - RED: Redaction required + restricted vault access (only arbiter can access)

6. **Performance** (ADR-0035, <5ms overhead):
   - Regex detection: <1ms (compiled regex cache)
   - NER model: <5ms (BERT inference on CPU or GPU)
   - Redaction: <1ms (string replacement)
   - Vault encryption: <1ms (AES-256-GCM with hardware acceleration)
   - Total: <5ms overhead per request

**ADR REFERENCES:**
- ADR-0035 (PII Detection & Redaction) - 1627 lines - Hybrid regex + NER
- ADR-0035a (Regex Pattern Library) - 12 PII types with patterns
- ADR-0035b (ML-based NER) - BERT-NER model, spaCy integration
- ADR-0035c (Encrypted Vault Key Management) - AES-256-GCM encryption, HSM keys
- ADR-0035d (Audit Trail GDPR Compliance) - Redaction event logging
- ADR-0032 (Band-Based Egress) - Privacy band integration

**PERFORMANCE TARGETS (P95):**
- Regex detection: <1ms (12 patterns cached)
- NER detection: <5ms (BERT inference)
- Redaction: <1ms (string replacement)
- Vault encrypt: <1ms (hardware acceleration)
- Total overhead: <5ms per request
- Detection recall: 95% (catch 95% of PII)
- False positive rate: <1% (don't redact legitimate text)

##### 5b.3: arbiter (RED Band Human-in-the-Loop with 4 Enhanced Protocols)

**PURPOSE:** Enable human-in-the-loop approval workflows for RED band operations via 4 enhanced HITL protocol extensions.

**EXPORTS:**
- `request_approval(operation, approval_type, timeout)` → Approval/Rejection
- `get_approval_status(request_id)` → Status (PENDING/APPROVED/REJECTED/EXPIRED)
- `confirm_phrase(user_phrase, required_phrase)` → Phrase validation
- `escalate(request_id, reason)` → Escalated to admin/operator

**LOGIC:**

1. **4 Enhanced HITL Protocols** (ADR-0052, 1052 lines):

   **Protocol 1: Step-by-Step Approval** (ADR-0052a):
   - Multi-step tasks with per-step approval (e.g., production deployment, data migration)
   - Each step requires: Description, Risk Level (LOW/MEDIUM/HIGH), Estimated Duration
   - User actions: Approve, Skip, Rollback (undo previous steps)
   - State persistence: Checkpointed to K0 (resume if interrupted)
   - Rollback: Saga pattern rollback for completed steps
   - Example (Production Deployment):
     ```
     [Step 1/4] Run integration tests (LOW risk, 5min)
       [Approve] [Skip] [Cancel]
     ↓ User: [Approve]
     ✅ Tests passed (5m 23s)
     
     [Step 2/4] Create backup snapshot (LOW risk, 2min)
       [Approve] [Skip] [Cancel]
     ↓ User: [Approve]
     ✅ Backup created (2m 11s)
     
     [Step 3/4] Deploy to prod-01 (MEDIUM risk, 3min)
       [Approve] [Skip] [Cancel]
     ↓ User: [No] (changes mind)
     
     ❓ Rollback options:
       A) Rollback backup snapshot (undo step 2)
       B) Keep backup, abort deployment
       C) Cancel entire workflow
     ```

   **Protocol 2: RED Band Approval (ADR-0052b):**
   - Explicit confirmation phrases for high-risk operations
   - Examples: "CONFIRM WIRE $50000", "DELETE 1.2M RECORDS", "ENABLE SUDO"
   - Anti-typo: User must type EXACTLY (case-sensitive, full string)
   - Anti-social-engineering: Message includes details (amount, target, records)
   - Two-person rule (optional): Require 2nd operator approval for very high risk
   - Timeout: 30s countdown (no approval → auto-reject)
   - Example (Financial Wire):
     ```
     � HIGH RISK OPERATION: FINANCIAL WIRE TRANSFER
     Amount: $50,000.00 (10× usual limit)
     To: John Doe (****-5432)
     
     ⚠️ Wire transfers cannot be reversed
     
     To proceed, type EXACTLY:
     'CONFIRM WIRE $50000 TO 9876-5432'
     
     Time remaining: 30 seconds [████░░░░░░]
     (Type 'cancel' to abort): ___
     ```

   **Protocol 3: Nested Clarifications (ADR-0052c):**
   - Clarification chains (hotel booking: "Which city?" → "Which dates?" → "Budget?")
   - History tracking: Display previous questions and answers
   - "Go back" functionality: Return to any prior step
   - Hard limit: Max 3 nesting levels (prevent infinite loops)
   - Context preservation: Pass context between steps
   - Example (Hotel Booking Chain):
     ```
     [Q1] Which city would you like to visit?
     User: "New York"
     
     [Q2] Check-in and check-out dates?
     User: "Next weekend (Dec 16-17)"
     Previous: ← [Q1: New York]
     
     [Q3] Budget per night?
     User: "Under $200"
     Previous: ← [Q2: Dec 16-17] ← [Q1: New York]
     
     [Q4] Preferred area in NYC?
     - Manhattan (10 hotels, $180-$200)
     - Brooklyn (25 hotels, $120-$150)
     User: [selects Manhattan]
     Previous: ← [Q3: <$200] ← [Q2: Dec 16-17] ← [Q1: New York]
     
     [Go Back] [Continue]
     ```

   **Protocol 4: Proactive Risk Confirmation (ADR-0052d):**
   - Agent-initiated safety checks triggered by anomaly detection
   - Triggers: Unusual transaction amount, access to sensitive data, unusual time
   - Example: "This transaction ($5000) is 10× your usual limit. Continue?"
   - Escalation: If anomaly score >0.8 → require explicit confirmation (not just "Yes")
   - Impact: Prevents accidental operations
   - Example (Transaction Anomaly):
     ```
     ⚠️ UNUSUAL TRANSACTION DETECTED
     
     Amount: $5,000 (10× your average $500)
     Time: 3:47 AM (unusual time)
     Frequency: 3rd transaction in 1 hour (unusual frequency)
     
     Anomaly Score: 0.92 (HIGH RISK)
     
     Continue transaction? [Yes/No]
     
     (For anomaly scores >0.8, will require confirmation phrase)
     ```

2. **Approval Workflow State Machine** (ADR-0052a, ADR-0052b):
   ```
   PENDING
     ↓ (user approves)
   APPROVED → Execute operation → Operation complete
     ↓ (user rejects)
   REJECTED → Operation aborted → Notification sent
     ↓ (timeout)
   EXPIRED (30s) → Operation auto-rejected → Notification sent
     ↓ (escalate)
   ESCALATED → Operator/admin review → Notification sent
   ```

3. **Approval Request Structure**:
   ```python
   ApprovalRequest {
     request_id: UUID,
     operation: OperationType (STEP_BY_STEP, RED_BAND_APPROVAL, NESTED_CLARIFICATION, PROACTIVE_CONFIRM),
     user_id: str,
     context: {
       step: int (if step-by-step),
       risk_level: str (LOW/MEDIUM/HIGH),
       description: str,
       confirmation_phrase: str (if RED band),
       timeout_seconds: int (default 30)
     },
     created_at: datetime,
     expires_at: datetime,
     response: {
       approved: bool,
       response_text: str (user's response),
       responded_at: datetime,
       response_time_seconds: float
     }
   }
   ```

4. **Two-Person Rule** (ADR-0052b, optional for very high risk):
   - Configure per-operation: "wire_transfer" requires 2 approvers
   - Require approval from 2 different users (not same user twice)
   - Timeout: 60s total (each approver has 30s)
   - Example:
     ```
     Approval 1/2:
       Operator: Alice
       Status: ✅ APPROVED
     
     Approval 2/2:
       Operator: Bob (pending...)
       Time remaining: 25 seconds
     ```

5. **Audit Trail** (ADR-0052c, 100% compliance logging):
   - Log every approval request/response
   - Store in K0 ToolReceipt with:
     - request_id, user_id, operation, response, timestamp, response_time
     - Confirmation phrase (encrypted if RED band)
     - Anomaly score (if proactive confirm)
   - Compliance: GDPR audit trail (who approved what, when)

6. **Integration with Planner** (ADR-0052 + ADR-0007):
   - Planner 4-stage pipeline pauses after Validate stage
   - Waiting for approval triggers Clarification protocol
   - Step-by-step approval integrates with Saga rollback
   - Example flow:
     ```
     Planner:
       Stage 1: Sketch (LLM) → production deployment plan
       Stage 2: Expand (deterministic) → 4 detailed steps
       Stage 3: Validate (rules + arbiter) → HIGH RISK, needs approval
       ↓
     Arbiter:
       Request approval (step-by-step, 4 steps)
       User approves steps 1-2, rejects step 3
       ↓
     Saga:
       Rollback step 2 (backup snapshot)
       Keep step 1 (tests completed)
       Notify user: "Deployment aborted, backup kept"
     ```

**ADR REFERENCES:**
- ADR-0052 (Enhanced HITL Protocols) - 1052 lines - 4 HITL extensions
- ADR-0052a (Step-by-Step Approval Protocol) - Multi-step workflows with rollback
- ADR-0052b (RED Band Approval Two-Person Rule) - Confirmation phrases, two-person
- ADR-0052c (Nested Clarification Chains History) - History tracking, "go back"
- ADR-0052d (Proactive Risk Confirmation) - Anomaly-triggered approvals
- ADR-0007 (4-Stage Planning Pipeline) - Planner integration
- ADR-0008 (Saga Pattern Error Recovery) - Rollback for step-by-step
- ADR-0040 (WebSocket Real-Time Chat) - Message delivery for HITL

**PERFORMANCE TARGETS (P95):**
- Approval request creation: <10ms (K0 write)
- Nested clarification overhead: <50ms per level (max 3 levels)
- Confirmation phrase validation: <100ms (string matching)
- State persistence: <10ms to K0 checkpoint
- Total arbiter overhead: <50ms per approval
- Timeout enforcement: <1s (30s default countdown)

#### 5c: Observability (4 modules)

| Module | File Path | Status | Imports | ADR Reference |
|--------|-----------|--------|---------|---|
| tracing | `k1/infrastructure/observability/tracing/` | 🚧 SKELETON | None (L5) | TBD |
| metrics | `k1/infrastructure/observability/metrics/` | 🚧 SKELETON | None (L5) | TBD |
| receipts | `k1/infrastructure/observability/receipts/` | 🚧 SKELETON | None (L5) | TBD |
| perf_harness | `k1/infrastructure/observability/perf_harness/` | 🚧 SKELETON | None (L5) | TBD |

#### 5d: Configuration (3 modules)

| Module | File Path | Status | Imports | ADR Reference |
|--------|-----------|--------|---------|---|
| global | `k1/infrastructure/config/global/` | 🚧 SKELETON | None (L5) | TBD |
| schemas | `k1/infrastructure/config/schemas/` | 🚧 SKELETON | None (L5) | TBD |
| config_manager | `k1/infrastructure/config/config_manager/` | 🚧 SKELETON | None (L5) | TBD |

#### 5e: Connectors (2 modules)

| Module | File Path | Status | Imports | ADR Reference |
|--------|-----------|--------|---------|---|
| k0_bridge | `k1/infrastructure/connectors/k0_bridge/` | 🚧 SKELETON | None (L5) | ADR-0001a (K0 Bridge) |
| model_hub_client | `k1/infrastructure/connectors/model_hub_client/` | 🚧 SKELETON | None (L5) | TBD |

#### 5f: Event Bus (Foundation - ADR-0004a)

**event_bus** - Central pub/sub for cross-layer communication
- ✅ Status: Referenced in ADR-0004a (completed)
- ✅ Topics: `IntentDetected`, `UserInput`, `VoiceCommand`, `BargeIn`
- ✅ Performance: <10ms end-to-end (publish <2ms + delivery <5ms)

### Layer 5 Dependency Graph

```
Layer 5 (Foundation - ALL MODULES)
│
├─→ event_bus ←──────────────────────────────────────────────────┐
│   (Layer 1 publishes, Layer 2 subscribes, etc)                 │
│                                                                  │
├─→ config_manager ←───────────────────────────────────────────┐  │
│   (hot reload, SSE listener, version management)             │  │
│   ├─→ global (agents.yml, models.yml, tools.yml)             │  │
│   ├─→ schemas (Pydantic + FlatBuffers definitions)           │  │
│   └─→ Layer 4 (learning_loop sends weight updates)           │  │
│                                                                │  │
├─→ metrics (Prometheus RED method)                             │  │
│   ├─→ counters (events_total, transitions_total)            │  │
│   ├─→ gauges (active_agents, cache_utilization)             │  │
│   └─→ histograms (latency_ms, memory_bytes)                 │  │
│                                                                │  │
├─→ tracing (OpenTelemetry + cognitive_trace_id)               │  │
│   ├─→ Span propagation (all layers)                          │  │
│   └─→ Exporters (Jaeger, Datadog, etc)                       │  │
│                                                                │  │
├─→ policy (bands.yml, caps.yml, budgets.yml)                  │  │
│   ├─→ Green band (unrestricted)                              │  │
│   ├─→ Amber band (restricted, monitoring)                    │  │
│   └─→ Red band (requires arbiter approval)                   │  │
│                                                                │  │
├─→ scheduler (WFQ - Weighted Fair Queuing)                    │  │
│   ├─→ 4-tier priority: CRITICAL, HIGH, NORMAL, LOW          │  │
│   ├─→ Anti-starvation rules                                  │  │
│   └─→ Backpressure cascade (blocks lower priority)           │  │
│                                                                │  │
├─→ thermal (NPU/GPU/CPU placement + heat management)          │  │
│   ├─→ Temperature monitoring                                 │  │
│   ├─→ Placement decisions (cooling decisions)                │  │
│   └─→ Hysteresis (prevent thrashing)                         │  │
│                                                                │  │
├─→ backpressure (cascade, watermarks)                         │  │
│   ├─→ Per-stream watermarks (speech, vision, etc)           │  │
│   ├─→ Voice-specific actions (pause, resume, skip)          │  │
│   └─→ Cascade to upper layers                                │  │
│                                                                │  │
├─→ cache (KV cache 128MB, prompt cache 64MB)                  │  │
│   ├─→ Model KV cache (shared across sessions)               │  │
│   ├─→ Prompt cache (frequently used prompts)                │  │
│   └─→ Eviction: LRU with 3-tier bands                       │  │
│                                                                │  │
├─→ budgets (resource limits enforcement)                      │  │
│   ├─→ Tokens (model input/output)                            │  │
│   ├─→ Dollars (API call costs)                               │  │
│   ├─→ Compute ms (CPU/GPU time)                              │  │
│   └─→ Latency (response time)                                │  │
│                                                                │  │
├─→ rate_limiting (token bucket per-intent)                    │  │
│   ├─→ Per-user limits                                        │  │
│   ├─→ Drift detection (unusual patterns)                     │  │
│   └─→ Gradual backoff (not sudden drop)                      │  │
│                                                                │  │
├─→ pii_detector (3-tier: regex, ONNX, LLM)                   │  │
│   ├─→ Regex patterns <1ms                                    │  │
│   ├─→ ONNX models 2-3ms                                      │  │
│   └─→ LLM fallback <50ms                                     │  │
│                                                                │  │
├─→ receipts (aggregation + audit)                             │  │
│   ├─→ Model receipts (LLM calls, costs)                      │  │
│   ├─→ Tool receipts (execution, errors)                      │  │
│   ├─→ Protocol receipts (MPST violations)                    │  │
│   └─→ State receipts (persistence, recovery)                 │  │
│                                                                │  │
├─→ k0_bridge (K0 kernel communication)                        │  │
│   ├─→ Batching (250ms or 64KB)                               │  │
│   ├─→ Compression (zstd)                                     │  │
│   ├─→ Ports: P01-P20 (specialized port specs)               │  │
│   └─→ Protocols: State, config, audit                        │  │
│                                                                │  │
└─→ storage_connector (persistence abstraction)                 │  │
    ├─→ Session recovery (resumable sessions)                  │  │
    ├─→ Audit logs (compliance, debugging)                     │  │
    └─→ K0 bridge (batched writes)                             │  │
         │                                                       │
         └──→ K0 Kernel (External) ────────────────────────────┘
```

---

## Inter-Layer Dependencies

### Allowed Imports (Layer Dependencies)

```
┌──────────────────────────────────────────────┐
│ STRICT LAYERING RULES                        │
│ Enforced by import-linter (ADR-0004b)       │
└──────────────────────────────────────────────┘

Layer 1 (Input):
  ✅ Can import: Layer 5
  ❌ Cannot import: Layers 2, 3, 4

Layer 2 (Orchestration):
  ✅ Can import: Layers 1, 3, 4, 5
  ❌ Cannot import: None (full visibility)

Layer 3 (Execution):
  ✅ Can import: Layers 4, 5
  ❌ Cannot import: Layers 1, 2

Layer 4 (Runtime):
  ✅ Can import: Layer 5
  ❌ Cannot import: Layers 1, 2, 3

Layer 5 (Infrastructure):
  ✅ Can import: None (foundation layer)
  ❌ Cannot import: Layers 1, 2, 3, 4
```

### Cross-Layer Communication Pattern (ADR-0004a: Event Bus)

```
Layer 1 → Layer 5 (event_bus) → Layer 2

Example Flow:
  1. intent_router (L1) detects intent
  2. Publishes IntentDetected event → event_bus (L5)
  3. orchestrator (L2) subscribes to event
  4. Receives event, triggers orchestration

Benefits:
  ✅ No direct L1 → L2 import (preserves layering)
  ✅ Async delivery (non-blocking)
  ✅ Decoupled (L1 doesn't know about L2)
  ✅ Extensible (multiple L2 subscribers possible)
```

---

## External Systems & Kernel Bridges

### External Systems (Non-K1)

```
┌─────────────────────────────────────────────────────────────┐
│           EXTERNAL SYSTEMS (Outside K1 Kernel)              │
└─────────────────────────────────────────────────────────────┘

VOICE & AUDIO:
  ├─→ Speech-to-Text (ASR): Google Cloud Speech, Azure, OpenAI Whisper
  ├─→ Text-to-Speech (TTS): Google Cloud TTS, AWS Polly, ElevenLabs
  ├─→ Voice Activity Detection (VAD): Silero VAD, WebRTC VAD
  └─→ Barge-In Detection: Custom models, WebRTC

VISION & SENSORS:
  ├─→ Computer Vision: OpenCV, MediaPipe, TensorFlow
  ├─→ Video Processing: FFmpeg, Gstreamer
  ├─→ Sensor APIs: IoT platforms, MQTT brokers
  └─→ Gesture Recognition: MediaPipe Pose, OpenPose

LLM PROVIDERS:
  ├─→ OpenAI (GPT-4, GPT-3.5, embeddings)
  ├─→ Anthropic (Claude models)
  ├─→ Google (Gemini, PaLM)
  ├─→ Microsoft (Azure OpenAI)
  ├─→ Open-source: vLLM, Ollama (local)
  └─→ Specialized: Llama, Mistral, Phi

EXTERNAL TOOLS & SERVICES:
  ├─→ Weather API: OpenWeatherMap, WeatherAPI
  ├─→ Search: Google Search API, Bing Search
  ├─→ Calendar: Google Calendar, Microsoft 365
  ├─→ Email: Gmail API, Outlook API
  ├─→ Databases: PostgreSQL, MongoDB, Elasticsearch
  ├─→ CMS: Notion, Confluence, SharePoint
  └─→ Custom APIs: REST/GraphQL/SOAP endpoints

OBSERVABILITY BACKENDS:
  ├─→ Metrics: Prometheus, Datadog, New Relic
  ├─→ Tracing: Jaeger, Zipkin, Datadog
  ├─→ Logging: ELK Stack, Splunk, Datadog
  └─→ Alerting: PagerDuty, Opsgenie, AlertManager

STORAGE & PERSISTENCE:
  ├─→ Databases: PostgreSQL, DynamoDB, Firestore
  ├─→ Object Storage: S3, GCS, Azure Blob
  ├─→ Cache: Redis, Memcached, DynamoDB DAX
  └─→ Distributed Store: etcd, Consul

KUBERNETES & ORCHESTRATION:
  ├─→ K8s: Pod, deployment, service management
  ├─→ Container Runtime: Docker, containerd
  ├─→ Networking: Ingress, service mesh (Istio)
  └─→ Resource Management: CPU, memory, GPU quotas
```

### K0 Kernel Bridge (ADR-0001a: K0-K1 Integration)

```
┌─────────────────────────────────────────────────────────────┐
│     K1 INTELLIGENCE MODULE (This Architecture)              │
└──────────────────────────┬──────────────────────────────────┘
                           │
                           │ k0_bridge (L5 connector)
                           │ - Batching (250ms / 64KB)
                           │ - Compression (zstd)
                           │ - Ports: P01-P20
                           ▼
┌─────────────────────────────────────────────────────────────┐
│            K0 KERNEL (Persistent Layer)                     │
├─────────────────────────────────────────────────────────────┤
│                                                              │
│  • State Persistence: Store session recovery data          │
│  • Distributed Coordination: Multi-instance K1 sessions    │
│  • Audit Logs: Compliance, debugging, forensics           │
│  • Model Management: Model versioning, rollback            │
│  • Configuration Storage: agents.yml, models.yml backup    │
│                                                              │
│  Interfaces:                                               │
│  ├─→ State API (read/write session state)                 │
│  ├─→ Config API (read/write configuration)                │
│  ├─→ Audit API (append-only audit logs)                   │
│  ├─→ Model API (model metadata, versioning)               │
│  └─→ Discovery API (find K1 instances, load balance)      │
│                                                              │
└──────────────────────────┬──────────────────────────────────┘
                           │
                           │ K0-specific protocols
                           ▼
        ┌──────────────────────────────────────┐
        │  K0 Persistent Storage (External)    │
        │  - PostgreSQL, DynamoDB, or custom   │
        │  - All K1 session data backed up     │
        └──────────────────────────────────────┘
```

### Kernel Connection Points

**Layer 5 ↔ External Systems:**

```
┌─────────────────────────────────────────────┐
│  Layer 1 (Input Processing)                │
└────────────────┬────────────────────────────┘
                 │
                 ├─→ [External] ASR API (speech → text)
                 ├─→ [External] VAD (voice activity)
                 ├─→ [External] Vision API (image processing)
                 └─→ [External] Sensor integrations

┌─────────────────────────────────────────────┐
│  Layer 3 (Execution - Model Hub)            │
└────────────────┬────────────────────────────┘
                 │
                 ├─→ [External] OpenAI API (LLM calls)
                 ├─→ [External] Anthropic API
                 ├─→ [External] Google Gemini API
                 ├─→ [External] Local vLLM (on-device)
                 └─→ [External] Ollama (open-source)

┌─────────────────────────────────────────────┐
│  Layer 3 (Execution - Tool Runner)          │
└────────────────┬────────────────────────────┘
                 │
                 ├─→ [External] Tool APIs (weather, calendar, search)
                 ├─→ [External] Databases (read/write data)
                 ├─→ [External] CMS systems (Notion, Confluence)
                 └─→ [External] Custom REST/GraphQL endpoints

┌─────────────────────────────────────────────┐
│  Layer 5 (Infrastructure - Observability)   │
└────────────────┬────────────────────────────┘
                 │
                 ├─→ [External] Prometheus (metrics scrape)
                 ├─→ [External] Jaeger (trace export)
                 ├─→ [External] ELK Stack (log aggregation)
                 └─→ [External] Datadog/New Relic (unified platform)

┌─────────────────────────────────────────────┐
│  Layer 5 (Infrastructure - Persistence)     │
└────────────────┬────────────────────────────┘
                 │
                 ├─→ [External] PostgreSQL (relational)
                 ├─→ [External] Redis (cache)
                 ├─→ [External] S3 (object storage)
                 └─→ [K0 Bridge] K0 Kernel (state sync)

┌─────────────────────────────────────────────┐
│  Layer 1 (Output - TTS)                     │
└────────────────┬────────────────────────────┘
                 │
                 ├─→ [External] Google TTS API
                 ├─→ [External] AWS Polly
                 ├─→ [External] ElevenLabs
                 └─→ [External] Local TTS (Piper, VITS)
```

---

## Performance Critical Paths

### Path 1: User Input → Intent Detection (Layer 1)

**Budget:** <150ms P95

```
1. User speaks → stream_switch (VAD detection)      [<5ms]
2. ASR → text conversion                             [<50ms]
3. intent_router (T1: regex → T2: SLM → T3: LLM)   [<50ms]
4. Publish IntentDetected event → event_bus (L5)    [<2ms]
──────────────────────────────────────────────────
Total: <150ms P95 ✅
```

**Critical Components:**
- ❌ No LLM call on hot path (T3 is async fallback)
- ❌ No network latency (local ASR/VAD preferred)
- ✅ Event publish non-blocking (Layer 1 continues)

---

### Path 2: Intent → Orchestration → Plan (Layers 1-2)

**Budget:** <250ms P95 orchestration + <5000ms plan generation

```
1. orchestrator receives IntentDetected event (L5)    [<1ms]
2. Phase 1: Negotiation (broadcast to agents)         [<50ms]
3. Phase 2: Selection (score & select best agent)     [<50ms]
4. Phase 3: Execution start                           [<50ms]
5. planner.generate_plan() (4-stage pipeline)         [<5000ms]
   - Stage 1: Sketch (LLM call via Model Hub)        [<3000ms]
   - Stage 2: Expand (deterministic)                 [<500ms]
   - Stage 3: Validate (rules + arbiter)             [<1000ms]
   - Stage 4: Commit (persist plan)                  [<500ms]
──────────────────────────────────────────────────
Orchestration: <250ms P95 ✅
Plan generation: <5000ms P95 ✅ (includes LLM)
```

**Critical Components:**
- ❌ LLM called in Stage 1 (can be slow)
- ✅ Validation (Stage 3) blocks unsafe plans
- ✅ Async execution (orchestrator doesn't wait)

---

### Path 3: Agent Hire → Warming → Active (Layer 3)

**Budget:** <600ms P95

```
1. orchestrator.hire_agent() → hire_fire module       [<10ms]
2. Agent transitions: PENDING → WARMING               [<200ms]
   - Load model (if using LLM)
   - Initialize agent state
3. Agent becomes ACTIVE                               [<390ms]
──────────────────────────────────────────────────
Total: <600ms P95 ✅
```

**Critical Components:**
- ✅ Model loading happens in WARMING (non-blocking to caller)
- ✅ Supervisor monitors health (1Hz checks)
- ✅ Mailbox ready for messages

---

### Path 4: User Turn End-to-End (All Layers)

**Budget:** <2000ms P95

```
1. Layer 1: Input processing + intent detection       [<150ms]
2. Layer 2: Orchestration + planning                  [<5250ms potentially]
3. Layer 3: Agent hire + execution                    [<600ms]
4. Layer 4: State management + response generation    [<100ms]
5. Layer 1: TTS output                                [<50ms]
──────────────────────────────────────────────────
Theoretical max: ~6150ms

OPTIMIZATIONS:
- Run steps in parallel where possible
- Stream output (don't wait for entire response)
- Cache common responses
- Use local models (avoid network latency)

Target: <2000ms P95 ✅ (with optimizations)
```

---

## Future Population Roadmap

### Phase 1: Core Layer Logic Population (Weeks 1-4)

**Goal:** Populate each layer with accurate ADR decision logic mapping

```
Layer 1 (Input Processing) - 4 Modules:
  ✅ ADR-0004 (52-module architecture) - reference
  ✅ ADR-0004a (Layer 1-2 event bus) - references L5 pub/sub backbone
  ⏳ ADR-0056, 0056a-0056e (Voice pipeline implementation) - ASR, intent bridge, TTS
  ⏳ ADR-0058, 0058a-0058b (Intent classification voice) - voice intent detection
  ⏳ ADR-0068, 0068a-0068c (Voice quality measurement) - ASR WER evaluation
  ⏳ ADR-0071, 0071a-0071c (Multilingual & code-switching) - language support

  **References from L5 (consumed, not owned):**
  → ADR-0032, 0032a-0032d (Band-based egress) - applies security policy at ingress
  → ADR-0035, 0035a-0035d (PII detection) - applies detection at input stream
  → ADR-0057, 0057a-0057c (Voice backpressure) - applies pressure at voice input

Layer 2 (Orchestration) - 3 Modules:
  ✅ ADR-0004 (52-module architecture) - reference
  ⏳ ADR-0003, 0003a-0003d (MPST protocol validation & monitoring) - protocol safety enforcement
  ⏳ ADR-0006, 0006a-0006e (3-phase orchestration with Contract Net) - negotiation→selection→execution
  ⏳ ADR-0007, 0007a-0007d (4-stage planning pipeline) - sketch→expand→validate→commit
  ⏳ ADR-0008, 0008a-0008d (Saga pattern error recovery) - distributed transaction semantics
  ⏳ ADR-0009, 0009a-0009c (Circuit breaker pattern) - cascading failure prevention
  ⏳ ADR-0049 (Fast/Smart lane router policy) - CRITICAL: request routing + admission control
  ⏳ ADR-0052, 0052a-0052d (Enhanced HITL protocols) - human-in-the-loop with approvals
  ⏳ ADR-0054, 0054a-0054c (Turn boundary management) - explicit/implicit turn handling
  ⏳ ADR-0055, 0055a-0055c (Context switch detection) - intent drift detection
  ⏳ ADR-0066, 0066a-0066c (Developer testing & simulation harness) - testing infrastructure
  ⏳ ADR-0070, 0070a-0070c (Observability evaluation infrastructure) - quality metrics

  **References from L5 (consumed, not owned):**
  → ADR-0045, 0045a-0045d (Agent SSE coordination) - uses L5 event bus
  → ADR-0048 (K1 internal event bus) - uses L5 pub/sub infrastructure

  **Phase Exit Criteria:**
  ⏳ ADR-0006, 0007 implemented + tested
  ⏳ ADR-0049 lane router operational
  ⏳ ADR-0003 protocol monitor validates all 6 protocols

Layer 3 (Execution) - 22 Modules:

  Agent Lifecycle (6 modules):
    ⏳ ADR-0002, 0002a-0002d (Actor model + mailbox, supervisor, router, observability) - actor infrastructure
    ⏳ ADR-0005, 0005a-0005e (Agent lifecycle FSM + state details) - PENDING→WARMING→ACTIVE→IDLE→DRAINING→TERMINATED

  Model Hub - LLM Integration (7 modules):
    ✅ ADR-0001b (Model Hub architecture) - multi-LLM integration layer
    ✅ ADR-0027, 0027a-0027d (Model placement cascade) - NPU/GPU/CPU/Remote placement with failover
    ✅ ADR-0025, 0025a-0025e (KV cache management 512MB) - shared attention cache management
    ✅ ADR-0032, 0032a-0032d (Band-based egress) - privacy enforcement on LLM outputs
    ✅ ADR-0035, 0035a-0035d (PII detection) - pre/post-filter safety

    **Implements Policy from L4 (applies, not owns):**
    → ADR-0060, 0060a-0060b (Adaptive KV cache management) - L4 Learning OWNS policy, L3 Model Hub implements

  Tool Execution (5 modules):
    ⏳ ADR-0010, 0010a-0010d (Capability-based security) - least-privilege access control
    ⏳ ADR-0033, 0033a-0033d (Three-tier sandbox strategy) - Protocol × Sandbox × Band layers
    ⏳ ADR-0034, 0034a-0034d (MCP protocol for tool sandboxing) - JSON-RPC 2.0 implementation
    ⏳ ADR-0012, 0012a-0012c (Tool discovery, validation, execution) - MCP tool runtime
    ⏳ ADR-0013, 0013a-0013d (Dynamic tool loading) - runtime tool registration
    ⏳ ADR-0014, 0014a-0014c (Tool timeout management) - execution constraints
    ⏳ ADR-0015, 0015a-0015c (Streaming tool execution) - incremental results
    ⏳ ADR-0018, 0018a-0018c (Model provider abstraction) - unified LLM interface
    ⏳ ADR-0019, 0019a-0019c (Model failover & fallback) - provider resilience
    ⏳ ADR-0020, 0020a-0020c (Prompt template management) - structured prompts
    ⏳ ADR-0021, 0021a-0021c (Response streaming) - incremental token delivery
    ⏳ ADR-0024, 0024a-0024c (Context window optimization) - token budget management
    ⏳ ADR-0046, 0046a-0046d (MCP gateway architecture) - tool protocol gateway
    ⏳ ADR-0062, 0062a-0062d (Streaming execution) - progressive output delivery
    ⏳ [TBD: Prompt/Secret Management] - L5 Safety OWNS policy, L3 Execution applies

  **References from L5 (consumed, not owned):**
  → ADR-0029, 0029a-0029c (OpenTelemetry tracing) - applies tracing to tool/model calls
  → ADR-0030, 0030a-0030c (Prometheus metrics) - emits execution metrics
  → ADR-0032, 0032a-0032d (Band-based egress) - applies security policy to outputs

  **Phase Exit Criteria:**
  ⏳ MCP gateway (ADR-0046) operational with 5+ tool providers
  ⏳ Model Hub (ADR-0018, 0019) supports 3+ LLM providers with failover
  ⏳ Tool execution metrics feeding L4 Learning Loop

  Dialogue Management (4 modules):
    ⏳ ADR-0053, 0053a-0053c (Message queue & coalescing) - batch rapid user messages
    ⏳ ADR-0067, 0067a-0067c (Conversational delight factors) - humor, personality, warmth
    ⏳ ADR-0069, 0069a-0069c (P08 AffectModulation K0 impl) - emotion detection & empathy

Layer 4 (Runtime Core) - 8 Modules:

  Runtime (4 modules):
    ⏳ ADR-0017, 0017a-0017f (SessionState 6-section design) - Beliefs, Scoreboard, Control, Persona, Multimodal, Meta
    ⏳ ADR-0018, 0018a-0018c (3-tier eviction strategy) - soft/hard/OOM eviction cascades
    ⏳ ADR-0019, 0019a-0019d (FlatBuffers SessionState serialization) - delta encoding + zero-copy
    ⏳ ADR-0020, 0020a-0020c (Multi-tier storage L1/L2/L3) - RAM/SSD/S3 with LRU/LFU/Zstd
    ⏳ ADR-0021, 0021a-0021c (Turn history retention policies) - lifecycle management by band
    ⏳ ADR-0023, 0023a-0023c (Cursor-based turn pagination) - opaque cursor with K0 optimization

  Learning (4 modules):
    ⏳ ADR-0059, 0059a-0059e (Learning loop architecture) - feedback signals + drift detection
    ⏳ ADR-0060, 0060a-0060b (Adaptive KV cache management) - OWNS policy, L3 Model Hub implements

  **Phase Exit Criteria:**
  ⏳ SessionState (ADR-0017) operational with all 6 sections
  ⏳ Learning loop (ADR-0059) ingesting feedback from 3+ signal types
  ⏳ FlatBuffers serialization (ADR-0019) <1ms for 64KB sessions

Layer 5 (Infrastructure) - 19 Modules:

  Infrastructure & Scheduling (7 modules):
    ✅ ADR-0004a (Layer 1-2 event bus) - OWNS pub/sub communication backbone
    ⏳ ADR-0024, 0024a-0024d (Performance budgets & P95 targets) - latency/memory SLOs
    ⏳ ADR-0025, 0025a-0025e (KV cache management 512MB) - LRU-LFU hybrid, Zstd compression
    ⏳ ADR-0026, 0026a-0026d (Thermal hysteresis matrix) - thermal state with 5C buffer
    ⏳ ADR-0028, 0028a-0028c (WFQ scheduler) - weighted fair queuing, 4 priority classes
    ⏳ ADR-0049 (Fast/Smart lane router policy) - CRITICAL: admission control + routing
    ⏳ ADR-0057, 0057a-0057c (Voice-specific backpressure) - ASR frame drop, TTS degradation ladder
    ⏳ ADR-0061, 0061a-0061d (3-tier backpressure cascade) - watermarks, fairness, recovery

  Safety & Policy (5 modules):
    ⏳ ADR-0032, 0032a-0032d (Band-based egress rules) - GREEN/AMBER/RED enforcement
    ⏳ ADR-0035, 0035a-0035d (PII detection & redaction) - regex + ML-based NER + vault
    ⏳ ADR-0036, 0036a-0036d (E2EE for RED band) - AES-256-GCM + KMS integration
    ⏳ [TBD: Prompt/Secret Management] - OWNS policy, L3 Execution applies

  Observability (3 modules):
    ⏳ ADR-0029, 0029a-0029c (OpenTelemetry tracing) - OWNS distributed tracing infrastructure
    ⏳ ADR-0030, 0030a-0030c (Prometheus metrics) - OWNS metrics collection & export

  Event Bus & Coordination (4 modules):
    ⏳ ADR-0045, 0045a-0045d (Agent SSE coordination) - OWNS internal event bus for agents
    ⏳ ADR-0048 (K1 internal event bus) - OWNS pub/sub infrastructure

  **Phase Exit Criteria:**
  ⏳ Event bus (ADR-0048) operational with pub/sub for L1/L2
  ⏳ Backpressure cascade (ADR-0061) protecting system from overload
  ⏳ Observability (ADR-0029, 0030) integrated with Prometheus + OTel

**PHASE 1 GATE:** All Phase 1 ADRs implemented + ADR-0007d Commit validated + ADR-0003 monitors all 6 protocols + ADR-0028 scheduler operational

---

#### **Phase 2: External Systems Integration (Weeks 5-8)**
    ⏳ ADR-0016, 0016a-0016d (SSE event schemas) - server-sent events streaming
    ⏳ ADR-0040, 0040a-0040d (WebSocket realtime chat API) - chat protocol implementation
    ⏳ ADR-0041, 0041a-0041d (REST API session management) - session CRUD operations

  K0 Bridge & Integration (4 modules):
    ⏳ ADR-0001a (K0 bridge communication protocol) - JSON + FlatBuffers dual transport
    ⏳ ADR-0022, 0022a-0022d (K0 bridge bounded batching) - 10-50 msgs / 100ms windows
    ⏳ ADR-0042, 0042a-0042e (K0 SSE event streaming) - event production/consumption with replay
    ⏳ ADR-0043, 0043a-0043d (SSE topic taxonomy) - topic hierarchy + subscriptions + ACLs
    ⏳ ADR-0044, 0044a-0044d (K0 bridge HTTP/2 + FlatBuffers) - multiplexing + serialization
```

### Phase 2: External Systems Integration (Weeks 5-8)

**Goal:** Define K1 connection points to external systems (outside K1 kernel)

```
Voice I/O Integration (Layer 1 & Layer 5):
  ⏳ ADR-0056, 0056a-0056e (Voice pipeline implementation) - ASR, intent bridge, TTS, audio streaming
  ⏳ ADR-0057, 0057a-0057c (Voice-specific backpressure) - frame drop, degradation ladder, barge-in preemption
  ⏳ ADR-0068, 0068a-0068c (Voice quality measurement) - ASR WER evaluation, TTS MOS estimation
  ⏳ External adapters: Google Speech-to-Text, Azure Speech, OpenAI Whisper, ElevenLabs TTS, Piper TTS

Vision & Sensor Integration (Future):
  ⏳ ADR-TBD (Computer vision pipeline) - image processing integration
  ⏳ ADR-TBD (Real-time video processing) - video stream handling
  ⏳ External adapters: OpenCV, MediaPipe, TensorFlow, vision APIs

LLM Provider Integration (Layer 3 Model Hub):
  ⏳ ADR-0001b (Model Hub architecture) - multi-LLM integration layer
  ⏳ ADR-0027, 0027a-0027d (Model placement cascade) - provider selection + failover
  ⏳ ADR-0031, 0031a-0031d (Cost tracking per-session) - cost-aware fallback
  ⏳ ADR-0060, 0060a-0060b (Adaptive KV cache management) - cache management across providers
  ⏳ External providers: OpenAI (GPT-4), Anthropic (Claude), Google (Gemini), vLLM (local), Ollama

Tool & MCP Integration (Layer 3 Tool Execution):
  ⏳ ADR-0033, 0033a-0033d (Three-tier sandbox strategy) - Protocol/Sandbox/Band layers
  ⏳ ADR-0034, 0034a-0034d (MCP protocol for tool sandboxing) - JSON-RPC 2.0 integration
  ⏳ ADR-0010, 0010a-0010d (Capability-based security) - least-privilege tool access
  ⏳ External tools: Weather APIs, Search APIs, Calendar, Email, Databases, CMS (via MCP)

Storage & Persistence (Layer 4 & Layer 5):
  ⏳ ADR-0020, 0020a-0020c (Multi-tier storage L1/L2/L3) - RAM/SSD/S3 tiers
  ⏳ ADR-0022, 0022a-0022d (K0 bridge bounded batching) - efficient K0 communication
  ⏳ External stores: PostgreSQL (K0 WAL), Redis (cache), S3 (cold archive)

Observability & Monitoring (Layer 5):
  ⏳ ADR-0029, 0029a-0029e (Prometheus metrics RED method) - metrics export
  ⏳ ADR-0030, 0030a-0030d (Intelligent trace sampling) - trace export with sampling
  ⏳ ADR-0038, 0038a-0038d (Audit trail to K0 receipts) - audit logging
  ⏳ External backends: Prometheus (metrics), Jaeger/Datadog (traces), ELK/Splunk (logs)

**PHASE 2 GATE:** All external adapters wired + 3+ LLM providers + 5+ MCP tools + observability backends connected + ADR-0056 voice pipeline operational

---

#### **Phase 3: K0 Bridge & Multi-Device Sync (Weeks 9-10)**

K0 Kernel Integration (Layer 5 Bridge):
  ⏳ ADR-0001a (K0 bridge communication protocol) - JSON + FlatBuffers dual transport
  ⏳ ADR-0022, 0022a-0022d (K0 bridge bounded batching) - efficient batching
  ⏳ ADR-0042, 0042a-0042e (K0 SSE event streaming) - event consumption
  ⏳ ADR-0043, 0043a-0043d (SSE topic taxonomy) - topic subscriptions
  ⏳ ADR-0044, 0044a-0044d (K0 bridge HTTP/2 + FlatBuffers) - transport layer
  ⏳ K0 kernel interactions: State persistence, config retrieval, audit log shipping
```

### Phase 3: K0 Bridge Integration & Multi-Device Sync (Weeks 9-10)

**Goal:** Complete K0-K1 coupling and multi-device family sync

```
K0-K1 Bridge Core (Layer 5):
  ⏳ ADR-0001a (K0 bridge communication protocol) - JSON + FlatBuffers dual transports
  ⏳ ADR-0022, 0022a-0022d (K0 bridge bounded batching) - 10-50 msgs / 100ms windows
  ⏳ ADR-0042, 0042a-0042e (K0 SSE event streaming) - bidirectional event streaming
  ⏳ ADR-0043, 0043a-0043d (SSE topic taxonomy) - topic subscriptions + filtering + ACLs
  ⏳ ADR-0044, 0044a-0044d (K0 bridge HTTP/2 + FlatBuffers) - connection multiplexing

State Persistence & Recovery (Layer 4 & Layer 5):
  ⏳ ADR-0017, 0017a-0017f (SessionState 6-section design) - complete state structure
  ⏳ ADR-0019, 0019a-0019d (FlatBuffers SessionState serialization) - efficient serialization
  ⏳ ADR-0020, 0020a-0020c (Multi-tier storage L1/L2/L3) - warm/cold tier recovery
  ⏳ ADR-0021, 0021a-0021c (Turn history retention policies) - lifecycle management
  ⏳ ADR-0023, 0023a-0023c (Cursor-based turn pagination) - efficient history queries
  ⏳ ADR-0001f (K0-K1 boundary enforcement) - state mutation barriers

Multi-Device Family Sync (Layer 4 & K0):
  ⏳ ADR-0050, 0050a-0050d (Multi-device family sync strategy) - cross-device coherence
  ⏳ ADR-0050a (SessionState coherence guarantees) - RYW, Monotonic, Bounded guarantees
  ⏳ ADR-0050b (CRDT device-to-device merge) - deterministic LWW + vector clocks
  ⏳ ADR-0050c (LAN-first sync implementation) - mDNS discovery + TCP P07 + 5s polling
  ⏳ ADR-0050d (P2P E2EE internet sync) - device certificates + STUN + QUIC + ChaCha20-Poly1305

Distributed Coordination (Layer 2 & Layer 5):
  ⏳ ADR-0006, 0006a-0006e (3-phase orchestration) - agent coordination foundation
  ⏳ ADR-0006c (Parallel DAG execution) - dependency ordering across instances
  ⏳ ADR-0006d (Saga pattern integration) - compensating transactions for failures
  ⏳ ADR-0008, 0008a-0008d (Saga pattern error recovery) - distributed transaction semantics

  **NOTE on "Multi-instance K1":** ADR-0050 specifies DEVICE-FIRST architecture (LAN mDNS + P2P E2EE), NOT cloud-based multi-instance scaling. Each device runs its own K1 instance. Cross-device sync uses peer-to-peer protocols, not central orchestration. If cloud scaling needed later, requires NEW ADR (not ADR-0050).

**PHASE 3 GATE:** K0 bridge (ADR-0042/0043/0044) operational + ADR-0001f boundary enforced + ADR-0050a coherence guarantees validated + LAN sync (ADR-0050c) <1ms latency + P2P sync (ADR-0050d) <500ms latency

---

#### **Phase 4: Testing, UX & Production Extensions (Weeks 11-12)**

**Goal:** Comprehensive test suite, UX polish, and production features

```
Per-Layer Integration Testing (All Layers):
  ✅ ADR-0004d (Per-layer integration testing) - WARD framework strategy
  ⏳ ADR-0066, 0066a-0066c (Developer testing & simulation harness) - LLM eval + synthetic users
  ⏳ ADR-0070, 0070a-0070c (Observability evaluation infrastructure) - quality labeling + A/B testing

Full Stack E2E Tests (Layer 1→5):
  ⏳ ADR-TBD (End-to-end test scenarios) - voice→plan→execute→voice-output scenarios
  ⏳ ADR-TBD (Chaos engineering tests) - failure injection, recovery validation
  ⏳ ADR-TBD (Performance regression tests) - latency/memory SLO validation

Product UX & Personality (Layer 3 & Layer 1):
  ⏳ ADR-0065, 0065a-0065d (Product craft UX micro-interactions) - streaming text, device handoff
  ⏳ ADR-0067, 0067a-0067c (Conversational delight factors) - humor, warmth, personality
  ⏳ ADR-0069, 0069a-0069c (P08 AffectModulation K0 impl) - emotion detection + empathy
  ⏳ ADR-0071, 0071a-0071c (Multilingual & code-switching) - family language diversity

Voice Quality & Internationalization (Layer 1):
  ⏳ ADR-0068, 0068a-0068c (Voice quality measurement) - ASR WER, TTS MOS monitoring
  ⏳ ADR-0071, 0071a-0071c (Multilingual & code-switching) - language detection + preferences

Human-in-the-Loop Extensions (Layer 2):
  ⏳ ADR-0052, 0052a-0052d (Enhanced HITL protocols) - approval workflows, risk confirmation
  ⏳ ADR-0054, 0054a-0054c (Turn boundary management) - explicit/implicit turns
  ⏳ ADR-0055, 0055a-0055c (Context switch detection) - intent drift detection + history control

Learning & Adaptation (Layer 4):
  ⏳ ADR-0059, 0059a-0059e (Learning loop architecture) - feedback signals + drift detection
  ⏳ ADR-0060, 0060a-0060b (Adaptive KV cache management) - learning-driven cache placement
  ⏳ ADR-0071, 0071a-0071c (Multilingual & code-switching) - language learning preferences

Advanced Features (Future):
  ⏳ ADR-TBD (Proactive assistance algorithms) - timing + context for proactive help
  ⏳ ADR-TBD (Cross-family knowledge sharing) - shared learning across family members
  ⏳ ADR-TBD (Custom skill training) - family-specific workflows and automations

**PHASE 4 GATE:** E2E tests validate P95 latency budgets (ADR-0024) + voice quality metrics (ADR-0068) pass thresholds + ADR-0066 simulation harness operational + ADR-0050a coherence guarantees validated in production + all UX micro-interactions (ADR-0065) polished

---

## ADR Coverage & Implementation Status

### Layer 1: Input Processing

| Feature | Primary ADR | Details | Status |
|---------|-----------|---------|--------|
| Multi-modal stream handling | ADR-0056, 0056a-0056e | Voice (ASR), text, vision integration | ⏳ Layer 1 design |
| Intent classification | ADR-0058, 0058a-0058b | Voice intent + confidence thresholds | ⏳ Layer 1 design |
| PII detection | ADR-0035, 0035a-0035d | Regex + ML-based NER + vault | ⏳ Layer 1 design |
| Multilingual support | ADR-0071, 0071a-0071c | Language detection + code-switching | ⏳ Layer 1 design |
| Voice quality measurement | ADR-0068, 0068a-0068c | ASR WER evaluation + monitoring | ⏳ Layer 1 design |
| Security & privacy bands | ADR-0032, 0032a-0032d | GREEN/AMBER/RED enforcement | ⏳ Layer 1 design |

### Layer 2: Orchestration

| Feature | Primary ADR | Details | Status |
|---------|-----------|---------|--------|
| 3-phase orchestration | ADR-0006, 0006a-0006e | Contract Net Protocol + proposals | ⏳ Layer 2 design |
| 4-stage planning | ADR-0007, 0007a-0007d | Sketch (LLM) → Expand → Validate → Commit | ⏳ Layer 2 design |
| Protocol validation | ADR-0003, 0003a-0003d | MPST enforcement at runtime | ✅ Implemented |
| Error recovery | ADR-0008, 0008a-0008d | Saga pattern with compensating txns | ⏳ Layer 2 design |
| Cascading failures | ADR-0009, 0009a-0009c | Circuit breaker pattern | ⏳ Layer 2 design |
| HITL workflows | ADR-0052, 0052a-0052d | Approvals, risk confirmation | ⏳ Layer 2 design |
| Turn management | ADR-0054, 0054a-0054c | Explicit/implicit boundaries | ⏳ Layer 2 design |
| Context switching | ADR-0055, 0055a-0055c | Intent drift detection | ⏳ Layer 2 design |

### Layer 3: Execution

| Feature | Primary ADR | Details | Status |
|---------|-----------|---------|--------|
| Agent lifecycle FSM | ADR-0005, 0005a-0005e | PENDING→WARMING→ACTIVE→IDLE→DRAINING→TERMINATED | ✅ Implemented |
| Actor model | ADR-0002, 0002a-0002d | Message-passing, supervisor, router | ✅ Implemented |
| Model Hub | ADR-0001b | Multi-LLM integration layer | ⏳ Layer 3 design |
| Model placement | ADR-0027, 0027a-0027d | NPU/GPU/CPU/Remote selection | ⏳ Layer 3 design |
| Tool sandboxing | ADR-0033, 0033a-0033d | Protocol × Sandbox × Band layers | ⏳ Layer 3 design |
| MCP protocol | ADR-0034, 0034a-0034d | JSON-RPC 2.0 for tools | ⏳ Layer 3 design |
| Capability security | ADR-0010, 0010a-0010d | Least-privilege tokens | ⏳ Layer 3 design |
| Conversational delight | ADR-0067, 0067a-0067c | Humor, warmth, personality | ⏳ Layer 3 design |
| Emotion & empathy | ADR-0069, 0069a-0069c | P08 AffectModulation in K0 | ⏳ Layer 3 design |
| Message coalescing | ADR-0053, 0053a-0053c | Batch rapid user messages | ⏳ Layer 3 design |

### Layer 4: Runtime Core

| Feature | Primary ADR | Details | Status |
|---------|-----------|---------|--------|
| SessionState design | ADR-0017, 0017a-0017f | 6-section structure: Beliefs/Scoreboard/Control/Persona/Multimodal/Meta | ⏳ Layer 4 design |
| Memory eviction | ADR-0018, 0018a-0018c | 3-tier: soft/hard/OOM cascades | ⏳ Layer 4 design |
| Serialization | ADR-0019, 0019a-0019d | FlatBuffers + delta encoding + zero-copy | ⏳ Layer 4 design |
| Multi-tier storage | ADR-0020, 0020a-0020c | L1 (RAM) / L2 (SSD K0 WAL) / L3 (S3) | ⏳ Layer 4 design |
| Retention policies | ADR-0021, 0021a-0021c | Lifecycle by privacy band | ⏳ Layer 4 design |
| Turn pagination | ADR-0023, 0023a-0023c | Cursor-based with K0 optimization | ⏳ Layer 4 design |
| Learning loop | ADR-0059, 0059a-0059e | Feedback signals + drift detection | ⏳ Layer 4 design |
| Adaptive caching | ADR-0060, 0060a-0060b | Dynamic KV cache placement | ⏳ Layer 4 design |

### Layer 5: Infrastructure

| Feature | Primary ADR | Details | Status |
|---------|-----------|---------|--------|
| Performance budgets | ADR-0024, 0024a-0024d | TTFT, E2E, component latency SLOs | ⏳ Layer 5 design |
| KV cache management | ADR-0025, 0025a-0025e | 512MB budget, LRU-LFU, Zstd compression | ⏳ Layer 5 design |
| Thermal management | ADR-0026, 0026a-0026d | Hysteresis with 5C buffer | ⏳ Layer 5 design |
| WFQ scheduler | ADR-0028, 0028a-0028c | 4-tier priority + anti-starvation | ⏳ Layer 5 design |
| Prometheus metrics | ADR-0029, 0029a-0029e | RED method: Rate/Errors/Duration | ⏳ Layer 5 design |
| Trace sampling | ADR-0030, 0030a-0030d | Head/tail/adaptive strategies | ⏳ Layer 5 design |
| Cost tracking | ADR-0031, 0031a-0031d | Hierarchical budgets by level | ⏳ Layer 5 design |
| Band-based security | ADR-0032, 0032a-0032d | Network/filesystem/resource egress | ⏳ Layer 5 design |
| PII protection | ADR-0035, 0035a-0035d | Detection + redaction + vault | ⏳ Layer 5 design |
| E2EE for RED band | ADR-0036, 0036a-0036d | AES-256-GCM + KMS | ⏳ Layer 5 design |
| JWT authentication | ADR-0037, 0037a-0037d | Token generation + validation + refresh | ⏳ Layer 5 design |
| Audit trail receipts | ADR-0038, 0038a-0038d | Immutable audit logging | ⏳ Layer 5 design |
| Voice backpressure | ADR-0057, 0057a-0057c | Frame drop, degradation, barge-in | ⏳ Layer 5 design |
| Backpressure cascade | ADR-0061, 0061a-0061d | 3-tier watermarks + fairness | ⏳ Layer 5 design |
| FlatBuffers serialization | ADR-0011, 0011a-0011d | Zero-copy binary format | ⏳ Layer 5 design |
| Schema definitions | ADR-0012, 0012a-0012e | 76 schemas across 5 layers | ⏳ Layer 5 design |
| Schema versioning | ADR-0013, 0013a-0013d | 90-day deprecation workflow | ⏳ Layer 5 design |
| REST API | ADR-0014, 0014a-0014d | JSON + FlatBuffers dual format | ⏳ Layer 5 design |
| WebSocket protocol | ADR-0015, 0015a-0015e | Binary framing + flow control | ⏳ Layer 5 design |
| SSE streaming | ADR-0016, 0016a-0016d | Topic-based filtering | ⏳ Layer 5 design |
| Chat API | ADR-0040, 0040a-0040d | WebSocket realtime chat | ⏳ Layer 5 design |
| Session API | ADR-0041, 0041a-0041d | REST CRUD + pagination | ⏳ Layer 5 design |
| K0 bridge protocol | ADR-0001a | JSON + FlatBuffers dual transport | ⏳ Layer 5 design |
| K0 bridge batching | ADR-0022, 0022a-0022d | 10-50 msgs / 100ms windows | ⏳ Layer 5 design |
| K0 SSE streaming | ADR-0042, 0042a-0042e | Event production/consumption + replay | ⏳ Layer 5 design |
| SSE topic taxonomy | ADR-0043, 0043a-0043d | Topic hierarchy + subscriptions | ⏳ Layer 5 design |
| K0 bridge HTTP/2 | ADR-0044, 0044a-0044d | Multiplexing + serialization | ⏳ Layer 5 design |

### Cross-Layer Features

| Feature | Primary ADR | Involves Layers | Status |
|---------|-----------|-----------------|--------|
| Multi-device sync | ADR-0050, 0050a-0050d | L4 + K0 | ⏳ Future |
| Event bus | ADR-0004a, ADR-0045, ADR-0048 | L1-L5 | ✅ Backbone |
| Developer testing | ADR-0066, 0066a-0066c | All layers | ⏳ Testing |
| Observability eval | ADR-0070, 0070a-0070c | L2, L5 | ⏳ Testing |
| UX micro-interactions | ADR-0065, 0065a-0065d | L1, L3 | ⏳ UX Polish |

---
