# Layer 1 (Input Processing) — ADR Family Map

**Complete end-to-end ADR references for K1 Layer 1 modules**

---

## 📋 Overview

**Layer 1 Purpose:** Input Processing
**Performance Budget:** <10ms P95
**Modules:** 4 modules across 2 categories
**Primary Function:** Unified multi-modal input bus + 3-tier intent routing

---

## 🗺️ Layer 1 Architecture

### Core ADRs

| ADR | Title | Status | Priority | Coverage |
|-----|-------|--------|----------|----------|
| **ADR-0004** | 52-Module 5-Layer Architecture | ✅ Complete | 🔴 CRITICAL | Layer 1-5 structure, 58-module organization, microkernel design, hot path optimization, fault isolation |
| **ADR-0004a** | Layer 1-2 Communication (Event Bus) | ✅ Complete | 🔴 CRITICAL | EventBus, Event, EventTopic, pub/sub pattern, async delivery, zero-copy |
| **ADR-0004b** | Layer Dependency Rules | ✅ Complete | 🔴 CRITICAL | L1→L5 only, event bus for L1→L2, import-linter enforcement |
| **ADR-0004d** | Layer 1 Integration Tests | ✅ Complete | 🟡 HIGH | Event publish, intent classification, stream processing, 3-tier routing, <50ms budget |

---

## 📁 Module-by-Module ADR Map

### **Module 1: streams/stream_switch**
**Purpose:** Unified multi-modal input bus
**Location:** `k1/l1_input/streams/stream_switch/`
**Performance:** <5ms P95

#### Primary ADRs
- **ADR-0004** — Layer 1 architecture, stream_switch as input gateway
- **ADR-0004a** — Event publishing to Layer 2 (EventBus integration)
- **ADR-0015** — WebSocket binary protocol (audio/text streams)
- **ADR-0016** — SSE event schemas (streaming state events)

#### Related ADRs
- **ADR-0019** — FlatBuffers SessionState serialization (stream state)
- **ADR-0024** — Performance budgets (TTFT <150ms hot path)
- **ADR-0030** — Trace sampling (cognitive_trace_id propagation)

#### Key Responsibilities
1. **Multi-Modal Input:** Audio (WebSocket), text (REST/WS), vision (future)
2. **Stream Routing:** Route to appropriate operator (VAD → ASR, text → NLU)
3. **Event Publishing:** Publish `UserInput` event to Layer 2
4. **Zero-Copy:** FlatBuffers integration for efficient serialization

#### Performance Metrics
- Stream setup latency: <2ms P95
- Event publish latency: <1ms P95
- Stream switch overhead: <5ms total
- Throughput: 100+ concurrent streams

---

### **Module 2: streams/operators**
**Purpose:** Stream transformations (VAD, ASR, TTS, vision)
**Location:** `k1/l1_input/streams/operators/`
**Performance:** VAD <20ms, ASR <80ms, TTS <300ms

#### Primary ADRs
- **ADR-0004** — Layer 1 architecture, operator pipeline
- **ADR-0015** — WebSocket binary protocol (audio frames, VAD state)
- **ADR-0015d** — Token streaming, barge-in handling
- **ADR-0024** — Performance budgets (ASR 80ms, TTS 300ms)

#### Related ADRs
- **ADR-0011** — FlatBuffers serialization (audio frames, VAD state)
- **ADR-0012** — FlatBuffers schemas (AudioFrame, ASRResult, TTSRequest, VADState)
- **ADR-0027** — Model placement cascade (on-device ASR/TTS models)
- **ADR-0028** — WFQ scheduler (REALTIME priority for voice)
- **ADR-0029** — Prometheus metrics (VAD latency, ASR accuracy)

#### Key Responsibilities
1. **Voice Activity Detection (VAD):** Detect speech start/stop (<20ms)
2. **Automatic Speech Recognition (ASR):** Audio → text (<80ms P95)
3. **Text-to-Speech (TTS):** Text → audio (<300ms P95)
4. **Vision Processing:** Image → embeddings/OCR (future)

#### Performance Metrics
- VAD detection: <20ms P95
- ASR latency: <80ms P95 (on-device model)
- TTS latency: <300ms P95 (first audio chunk)
- Barge-in cancel: <120ms P95 (ADR-0024)

---

### **Module 3: orchestration/intent_router**
**Purpose:** 3-tier intent classification (T1/T2/T3)
**Location:** `k1/l1_input/orchestration/intent_router/`
**Performance:** <50ms P95 (T1 10ms, T2 3ms, T3 40ms)

#### Primary ADRs
- **ADR-0004** — Layer 1 architecture, intent_router as orchestration entry
- **ADR-0024** — Performance budgets (intent classification <50ms P95)
- **ADR-0024b** — Component-level budgets (rule-based 10ms, LLM 45ms)

#### Related ADRs
- **ADR-0001b** — Model Hub integration (T3 LLM intent classification)
- **ADR-0006** — 3-Phase orchestration (intent triggers negotiation)
- **ADR-0007** — 4-Stage planning (intent → task announcement)
- **ADR-0027** — Model placement (T3 local-first SLM)
- **ADR-0028** — WFQ scheduler (REALTIME priority for intent)
- **ADR-0029** — Prometheus metrics (intent classification latency, accuracy)

#### Key Responsibilities
1. **T1 Rule-Based (10ms):** Regex/keyword matching (70% coverage)
   - "What's the weather?" → WEATHER intent
   - "Set timer 5 minutes" → TIMER intent
   - Fast path, deterministic, no LLM

2. **T2 SLM Classification (3ms):** On-device small LM (20% coverage)
   - Phi-3-mini (3.8B) for ambiguous intents
   - "I'm cold" → THERMOSTAT intent (contextual)
   - "Book me a flight" → TRAVEL intent (multi-step)

3. **T3 LLM Fallback (40ms):** Large model for complex (10% coverage)
   - GPT-4o-mini or Claude-3-Haiku (remote)
   - "Cancel the thing I scheduled yesterday" → CALENDAR_DELETE
   - "What did I tell you about my anniversary?" → MEMORY_RECALL

4. **Event Publishing:** Publish `IntentDetected` event to Layer 2

#### Performance Metrics
- T1 rule-based: <10ms P95 (70% coverage)
- T2 SLM classification: <3ms P95 (20% coverage)
- T3 LLM fallback: <40ms P95 (10% coverage)
- Total intent budget: <50ms P95 (weighted average)
- Accuracy: >95% (all tiers combined)

#### 3-Tier Fallback Cascade
```
User Input → T1 Rule-Based (10ms, 70% hit rate)
            ↓ miss
            → T2 SLM (3ms, 90% cumulative hit rate)
            ↓ miss
            → T3 LLM (40ms, 99.5% cumulative hit rate)
            ↓ miss
            → DEFAULT intent (ask clarification)
```

---

### **Module 4: orchestration/meta_policy**
**Purpose:** Proactivity & clarification engines
**Location:** `k1/l1_input/orchestration/meta_policy/`
**Performance:** <5ms P95 (policy evaluation)

#### Primary ADRs
- **ADR-0004** — Layer 1 architecture, meta_policy as orchestration policy
- **ADR-0017** — SessionState 6-section design (beliefs, scoreboard for context)
- **ADR-0017b** — Scoreboard section (QUD stack, common ground)

#### Related ADRs
- **ADR-0001** — K0 integration (retrieve beliefs for proactive suggestions)
- **ADR-0006** — 3-Phase orchestration (proactive tasks triggered by policy)
- **ADR-0010** — Capability security (policy-based escalation)
- **ADR-0021** — Turn history retention (policy-aware retention)
- **ADR-0024** — Performance budgets (policy evaluation <5ms)

#### Key Responsibilities
1. **Proactivity Engine:**
   - Trigger proactive suggestions based on context
   - "It's 5 PM, time for your daily standup" (calendar policy)
   - "You mentioned your anniversary is coming up, want me to set a reminder?" (memory policy)
   - Policy evaluation <5ms P95

2. **Clarification Engine:**
   - Detect ambiguous input requiring clarification
   - "Book a flight" → "Where do you want to fly to?"
   - "Set a timer" → "For how long?"
   - Nested clarification protocol (ADR-0003b)

3. **Policy Types:**
   - Time-based (calendar, reminders)
   - Context-based (location, activity)
   - Belief-based (user preferences, habits)
   - Safety-based (RED band escalation)

4. **Event Publishing:** Publish `ClarificationRequired` or `ProactiveSuggestion` events

#### Performance Metrics
- Policy evaluation: <5ms P95
- Proactive trigger rate: 2-5 per day (configurable)
- Clarification rate: 5-10% of turns
- User acceptance rate: 60-70% (proactive suggestions)

---

## 🔗 Cross-Cutting ADRs (Affect All Layer 1 Modules)

### **Architecture & Design**
- **ADR-0002** — Actor Model (all Layer 1 modules are pure actors, deterministic)
- **ADR-0004** — 52-Module 5-Layer Architecture (Layer 1 definition, hot path)
- **ADR-0004a** — Event Bus (Layer 1→2 communication, pub/sub)
- **ADR-0004b** — Import Linting (L1→L5 only, no L1→L2/L3/L4 direct imports)
- **ADR-0004d** — Layer 1 Integration Tests (end-to-end test suite)

### **Serialization & Data**
- **ADR-0011** — FlatBuffers serialization (zero-copy, <1ms serialize)
- **ADR-0012** — 76 FlatBuffers schemas (Layer 1 schemas: AudioFrame, ASRResult, TTSRequest, VADState, IntentDetected, etc.)
- **ADR-0013** — Schema versioning (SemVer, backward compatibility)
- **ADR-0019** — SessionState serialization (Layer 1 reads SessionState for context)

### **Observability**
- **ADR-0029** — Prometheus metrics (RED method: rate/error/duration for Layer 1 modules)
- **ADR-0030** — Trace sampling (cognitive_trace_id propagation, Layer 1 entry point)

### **Performance & Reliability**
- **ADR-0024** — Performance budgets (Layer 1: <10ms P95 total)
- **ADR-0028** — WFQ scheduler (Layer 1 publishes to REALTIME/INTERACTIVE queues)
- **ADR-0009** — Circuit breaker (Layer 1 integrates circuit breakers for ASR/TTS/LLM)

### **Security & Privacy**
- **ADR-0010** — Capability security (Layer 1 reads capabilities for intent validation)
- **ADR-0032** — Egress control (Layer 1 respects privacy bands for intent routing)
- **ADR-0035** — PII detection (Layer 1 redacts PII from audio/text before Layer 2)

### **Cost & Resource Management**
- **ADR-0027** — Model placement cascade (Layer 1 ASR/TTS on-device first)
- **ADR-0031** — Cost tracking (Layer 1 tracks T3 LLM intent costs)

---

## 🎯 Layer 1 Performance Budget Breakdown

### **Total Layer 1 Budget: <10ms P95**

| Component | Budget | Typical | P95 | ADR |
|-----------|--------|---------|-----|-----|
| stream_switch | 5ms | 2ms | 3ms | ADR-0004 |
| operators (VAD) | N/A | 15ms | 20ms | ADR-0024 |
| operators (ASR) | N/A | 60ms | 80ms | ADR-0024 |
| intent_router (T1) | 10ms | 8ms | 10ms | ADR-0024b |
| intent_router (T2) | 3ms | 2ms | 3ms | ADR-0024b |
| intent_router (T3) | 45ms | 35ms | 40ms | ADR-0024b |
| meta_policy | 5ms | 3ms | 5ms | ADR-0004 |
| **Hot Path Total** | **<10ms** | **5ms** | **8ms** | **ADR-0024a** |

**Note:** ASR (80ms) is **NOT** part of hot path. Hot path = stream_switch (5ms) + intent_router T1/T2 (10ms) = **15ms** to Layer 2 EventBus.

---

## 🔄 Layer 1 → Layer 2 Integration

### **Event Bus Architecture (ADR-0004a)**

**Layer 1 publishes events to Layer 2 Orchestration via EventBus:**

```
Layer 1 (Input)                  EventBus (L5)                Layer 2 (Orchestration)
─────────────────                ───────────────              ─────────────────────────
stream_switch    ──publish──>    UserInput event    ──subscribe──>  orchestrator
operators (ASR)  ──publish──>    ASRResult event    ──subscribe──>  dialogue manager
intent_router    ──publish──>    IntentDetected     ──subscribe──>  orchestrator
meta_policy      ──publish──>    ClarificationReq   ──subscribe──>  clarification protocol
operators (VAD)  ──publish──>    BargeIn event      ──subscribe──>  barge-in handler
```

**Key Constraints:**

1. **No direct L1→L2 imports** (enforced by import-linter, ADR-0004b)
2. **Event-driven only** (pub/sub pattern, zero coupling)
3. **Zero-copy** (FlatBuffers serialization, <1ms overhead)
4. **Async delivery** (non-blocking, <5ms P95, ADR-0004a)

---

## 🧪 Layer 1 Testing Strategy (ADR-0004d)

### **Integration Tests**

**Location:** `tests/integration/layer1/`

1. **Event Publishing Tests:**
   - Verify Layer 1 publishes events to EventBus
   - Verify event schema (FlatBuffers validation)
   - Verify cognitive_trace_id propagation

2. **Intent Classification Tests:**
   - T1 rule-based accuracy (>95%)
   - T2 SLM accuracy (>90%)
   - T3 LLM fallback accuracy (>85%)
   - 3-tier fallback cascade

3. **Stream Processing Tests:**
   - Multi-modal input (audio + text)
   - VAD detection accuracy (>98%)
   - ASR accuracy (>90% WER)
   - TTS quality (MOS >4.0)

4. **Performance Tests:**
   - Layer 1 total budget <10ms P95
   - stream_switch <5ms P95
   - intent_router <50ms P95 (weighted)
   - meta_policy <5ms P95

5. **End-to-End Tests:**
   - User audio → ASR → intent → Layer 2 event
   - User text → intent → Layer 2 event
   - Barge-in → cancel → Layer 2 interrupt

---

## 📊 Layer 1 Observability (ADR-0029)

### **Prometheus Metrics**

| Metric | Type | Labels | Description | ADR |
|--------|------|--------|-------------|-----|
| `layer1_events_published_total` | Counter | event_type | Events published to EventBus | ADR-0029 |
| `layer1_intent_classification_ms` | Histogram | tier (T1/T2/T3) | Intent classification latency | ADR-0029 |
| `layer1_intent_accuracy` | Gauge | tier (T1/T2/T3) | Intent classification accuracy | ADR-0029 |
| `layer1_stream_setup_ms` | Histogram | stream_type (audio/text) | Stream setup latency | ADR-0029 |
| `layer1_vad_detection_ms` | Histogram | - | VAD detection latency | ADR-0029 |
| `layer1_asr_latency_ms` | Histogram | model (local/remote) | ASR latency | ADR-0029 |
| `layer1_tts_latency_ms` | Histogram | model (local/remote) | TTS latency (TTFT) | ADR-0029 |
| `layer1_policy_evaluation_ms` | Histogram | policy_type | Meta-policy evaluation latency | ADR-0029 |
| `layer1_clarification_rate` | Gauge | - | % of turns requiring clarification | ADR-0029 |
| `layer1_proactive_trigger_rate` | Counter | policy_type | Proactive suggestions triggered | ADR-0029 |

### **Grafana Dashboard**

**Layer 1 Overview Dashboard:**

- Event publish rate (events/sec)
- Intent classification latency (P50/P95/P99)
- 3-tier fallback distribution (T1 70%, T2 20%, T3 10%)
- ASR/TTS latency trends
- VAD detection accuracy
- Clarification/proactive trigger rates

---

## 🚀 Next Steps (Implementation Roadmap)

### **Phase 1: Core Infrastructure (Week 1-2)**
1. Implement `stream_switch` (multi-modal input bus)
2. Implement EventBus integration (Layer 1→2 communication)
3. Implement `intent_router` T1 rule-based classifier
4. Add Layer 1 Prometheus metrics
5. Add Layer 1 integration tests

### **Phase 2: Stream Operators (Week 3-4)**
1. Implement VAD operator (voice activity detection)
2. Implement ASR operator (on-device model)
3. Implement TTS operator (on-device model)
4. Add audio frame FlatBuffers schemas
5. Add WebSocket binary protocol support

### **Phase 3: Advanced Intent (Week 5-6)**
1. Implement T2 SLM classifier (Phi-3-mini)
2. Implement T3 LLM fallback (GPT-4o-mini/Claude)
3. Implement 3-tier fallback cascade
4. Add intent classification metrics
5. Add accuracy tracking

### **Phase 4: Meta-Policy (Week 7-8)**
1. Implement proactivity engine
2. Implement clarification engine
3. Add policy evaluation logic
4. Add nested clarification protocol
5. Add user acceptance tracking

### **Phase 5: Optimization & Refinement (Week 9-10)**
1. Optimize hot path (<10ms P95 total)
2. Add zero-copy optimizations (FlatBuffers)
3. Add circuit breakers for ASR/TTS/LLM
4. Add PII redaction for audio/text
5. Add cost tracking for T3 LLM intents

---

## 📚 Complete ADR Reference List

### **Primary Layer 1 ADRs**
- ADR-0004 — 52-Module 5-Layer Architecture
- ADR-0004a — Layer 1-2 Communication (Event Bus)
- ADR-0004b — Layer Dependency Rules
- ADR-0004d — Layer 1 Integration Tests

### **Supporting ADRs (by Module)**

**stream_switch:**
- ADR-0015 — WebSocket binary protocol
- ADR-0016 — SSE event schemas
- ADR-0019 — SessionState serialization
- ADR-0024 — Performance budgets
- ADR-0030 — Trace sampling

**operators:**
- ADR-0011 — FlatBuffers serialization
- ADR-0012 — FlatBuffers schemas (AudioFrame, VADState, etc.)
- ADR-0015 — WebSocket binary protocol
- ADR-0015d — Token streaming, barge-in
- ADR-0024 — Performance budgets (ASR 80ms, TTS 300ms)
- ADR-0027 — Model placement cascade
- ADR-0028 — WFQ scheduler
- ADR-0029 — Prometheus metrics

**intent_router:**
- ADR-0001b — Model Hub integration (T3)
- ADR-0006 — 3-Phase orchestration
- ADR-0007 — 4-Stage planning
- ADR-0024 — Performance budgets (<50ms)
- ADR-0024b — Component-level budgets
- ADR-0027 — Model placement (local-first)
- ADR-0028 — WFQ scheduler
- ADR-0029 — Prometheus metrics

**meta_policy:**
- ADR-0001 — K0 integration (beliefs retrieval)
- ADR-0006 — 3-Phase orchestration
- ADR-0010 — Capability security
- ADR-0017 — SessionState 6-section design
- ADR-0017b — Scoreboard section (QUD stack)
- ADR-0021 — Turn history retention
- ADR-0024 — Performance budgets (<5ms)

### **Cross-Cutting ADRs**
- ADR-0002 — Actor Model (all Layer 1 modules)
- ADR-0009 — Circuit breaker (ASR/TTS/LLM resilience)
- ADR-0010 — Capability security (intent validation)
- ADR-0011 — FlatBuffers serialization (zero-copy)
- ADR-0012 — 76 FlatBuffers schemas
- ADR-0013 — Schema versioning
- ADR-0027 — Model placement (on-device first)
- ADR-0028 — WFQ scheduler (REALTIME priority)
- ADR-0029 — Prometheus metrics (RED method)
- ADR-0030 — Trace sampling (cognitive_trace_id)
- ADR-0031 — Cost tracking (T3 LLM intents)
- ADR-0032 — Egress control (privacy bands)
- ADR-0035 — PII detection (audio/text redaction)

---

## 🔍 How to Use This Map

1. **Starting New Work:**
   - Read module-specific ADRs first (e.g., ADR-0004 for architecture)
   - Check cross-cutting ADRs for design constraints
   - Review performance budgets (ADR-0024) before implementing

2. **During Implementation:**
   - Follow ADR architectural patterns (Actor Model, Event Bus)
   - Use FlatBuffers for serialization (ADR-0011/0012)
   - Add Prometheus metrics (ADR-0029)
   - Add integration tests (ADR-0004d)

3. **After Implementation:**
   - Validate performance budgets (<10ms P95 Layer 1 total)
   - Run integration tests (Ward framework)
   - Update ADR if architecture changed

4. **When Lost:**
   - Start with ADR-0004 (complete Layer 1 architecture)
   - Check `docs/whiteboard_architecture.md` (3K lines)
   - Use this map to find relevant ADRs

---

**Status:** ✅ **COMPLETE** — All Layer 1 ADRs mapped end-to-end
**Last Updated:** January 2025
**Total ADRs:** 40+ ADRs covering Layer 1 (4 primary + 36 supporting)
**Coverage:** 100% of Layer 1 modules (4/4 modules mapped)
