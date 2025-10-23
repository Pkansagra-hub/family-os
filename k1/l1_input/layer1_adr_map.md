# Layer 1 (Input Processing) — ADR Family Map

**Complete end-to-end ADR references for K1 Layer 1 modules**

---

## 📋 Overview

**Layer 1 Purpose:** Input Processing
**Performance Budget:** <10ms P95
**Modules:** 4 modules across 2 categories (streams, orchestration)
**Primary Function:** Unified multi-modal input bus + 3-tier intent routing
**Total Relevant ADRs:** 91 ADRs across 31 families

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

## � Complete ADR Inventory for Layer 1

**Total ADRs:** 91 ADRs across 31 families

### ADR Families Relevant to Layer 1

| Family | Count | Key Focus Areas |
|--------|-------|-----------------|
| **WebSocket Binary Protocol** | 6 | Real-time bidirectional communication, token streaming, barge-in |
| **Voice Pipeline Implementation** | 7 | ASR, TTS, prosody controls, voice continuity |
| **FlatBuffers** | 5 | Zero-copy serialization, schema design, performance |
| **FlatBuffers Schemas** | 20 | Layer 1 schemas, type definitions, code generation |
| **Schema Versioning** | 5 | SemVer policy, backward compatibility, deprecation |
| **SSE Event Schemas** | 6 | Event taxonomy, streaming, filtering |
| **Capability Security** | 5 | Capability tokens, lifecycle, assignment, revocation |
| **Product Craft UX** | 5 | Streaming text, session continuity, quick actions |
| **Message Queue & Coalescing** | 4 | Nagle-style buffering, rate limiting, cancellation |
| **Turn Boundary Management** | 3 | Implicit pause detection, explicit submit |
| **Enhanced HITL Protocols** | 5 | RED band approval, nested clarifications, proactive confirmation |
| **Multi-Party Dialogue** | 3 | Speaker diarization, voice biometrics, turn-taking |
| **Ambient Sensor Fusion** | 3 | PIR/mmWave/BLE sensors, occupancy detection |
| **Embodied Awareness** | 3 | Location awareness, BLE proximity, presence |
| **K0 Memory Consolidation** | 5 | Hippocampal replay, sleep cycles, dream exploration |
| **Knowledge Graph** | 5 | Entity extraction, temporal reasoning, schema evolution |
| **Multilingual Support** | 1 | Language detection, code-switching |
| **Conversational Delight** | 1 | Humor, celebrations, easter eggs |
| **K0/K1 Architecture** | 8 | Dual-kernel, layer dependencies, testing, event bus |
| **Others** | 26 | REST API, OpenAPI, Prometheus metrics, K0 SSE, etc. |

---

## �📁 Module-by-Module ADR Map

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

## 🆕 Additional Layer 1 ADR Coverage (from ADR_REFERENCE)

### **Ambient Sensor Integration**

Layer 1 includes ambient sensor fusion for context-aware responses:

#### Sensor Drivers (ADR-0083, ADR-0083a)
- **PIR Motion Sensor** — `k1/l1_input/sensors/pir_motion_driver.py`
  - GPIO interface (RPi.GPIO), binary motion detection
  - <10ms latency, GREEN band, health monitoring 1Hz
  - Auto-restart (max 3 retries), SensorDriver interface

- **mmWave Radar Sensor** — `k1/l1_input/sensors/mmwave_radar_driver.py`
  - UART serial (LD2410 protocol), breathing/heartbeat detection
  - Range 50-500cm, micro-doppler signals, <20ms latency
  - GREEN band, health monitoring 1Hz

- **BLE Proximity Detector** — `k1/l1_input/sensors/ble_proximity_driver.py`
  - Bleak scanner, enrolled device tracking
  - MAC address hashing (SHA256[:8]), <50ms latency
  - AMBER band, detected identities (hashed)

#### Sensor Fusion (ADR-0083b)
- **Weighted Bayesian Fusion** — `k1/l1_input/sensors/sensor_fusion_engine.py`
  - 6 sensor weighted voting (Camera 0.40, mmWave 0.25, PIR 0.15, BLE 0.10, WiFi 0.05, Light 0.05)
  - Occupancy score (VACANT <0.30, POSSIBLY 0.30-0.60, OCCUPIED ≥0.60)
  - Temporal smoothing (5s rolling average), debouncing (2 consecutive readings)

---

### **Multi-Party Dialogue Support**

#### Speaker Diarization (ADR-0082, ADR-0082a)
- **Voice Biometrics** — `k1/l1_input/streams/operators/speaker_identifier.py`
  - ECAPA-TDNN 768-dim embeddings, 93-95% accuracy, <100ms P95 latency
  - Cosine similarity matching >0.8 threshold
  - AES-256-GCM encrypted voice profiles, confidence tracking

- **Speaker Enrollment** — `k1/l1_input/streams/operators/speaker_enrollment.py`
  - Voice sample recording (30-60 seconds), 10-15 phonetically diverse utterances
  - ECAPA-TDNN embedding training, speaker profile creation
  - SNR >20dB environment validation, privacy-aware storage (K0 encrypted)

- **Runtime Matching** — `k1/l1_input/streams/operators/profile_matcher.py`
  - VAD segmentation, ONNX inference (<50ms)
  - Cosine similarity vs enrolled profiles
  - Confidence thresholds (>0.9 high, 0.8-0.9 medium, <0.8 unknown)

---

### **Embodied Awareness (Multi-Device Presence)**

#### Location Awareness (ADR-0085, ADR-0085a)
- **GPS Tracking** — `k1/l1_input/streams/operators/location/gps_tracker.py`
  - CoreLocation (iOS), FusedLocationProvider (Android)
  - High precision <10m, RED privacy band (local-only, never synced)
  - Degrade to GREEN city-level before sync

- **WiFi Triangulation** — `k1/l1_input/streams/operators/location/wifi_triangulator.py`
  - BSSID triangulation via Google Geolocation API
  - Medium precision <50m, AMBER privacy band (hash SSID/BSSID before sync)
  - Building-level accuracy, <5s P95 update latency

- **IP Geolocation** — `k1/l1_input/streams/operators/location/ip_geolocator.py`
  - MaxMind GeoLite2 database (local lookup)
  - City-level precision ~5km, GREEN privacy band (safe to sync)
  - <100ms P95 lookup latency

- **Coarse Location Classifier** — `k1/l1_input/streams/operators/location/coarse_classifier.py`
  - 4 categories (HOME, WORK, TRAVELING, UNKNOWN)
  - WiFi SSID direct match, GPS proximity check (<100m)
  - Haversine distance calculation, context-aware responses

#### BLE Proximity (ADR-0085b)
- **Beacon Advertising** — `k1/l1_input/streams/operators/ble/beacon_advertiser.py`
  - iBeacon compatible, family-scoped UUID
  - Major=device_type (1-5), Minor=battery_level (0-100)
  - TX_Power=-59dBm, continuous advertising

- **Beacon Scanning** — `k1/l1_input/streams/operators/ble/beacon_scanner.py`
  - 3-second scan duration, 5-second interval
  - 4 proximity zones (NEAR >-65dBm <2m, MEDIUM -65 to -80dBm 2-10m, FAR -80 to -95dBm >10m, OUT_OF_RANGE <-95dBm)
  - Distance estimation (path loss exponent N=2.5), <200ms scan latency

---

### **Enhanced HITL Protocols**

#### RED Band Approval (ADR-0052b)
- **Audit Trail** — `k0/receipts/red_band_audit.py`
  - 7-year retention to K0 receipts (SOC2/ISO27001 compliance)
  - Full audit: approval_id, operation, confidence_factors, phrase match result
  - Immutable append-only logs

#### Nested Clarifications (ADR-0052c)
- **QUD Stack** — Questions Under Discussion theory (Roberts 1996)
  - Hierarchical question structure, ClarificationHistory as dialogue state
  - Multi-turn dialogue state tracking

#### Proactive Confirmation (ADR-0052d)
- **Feedback Signals** — `k0/learning/feedback_integration.py`
  - 1.0 (agent was right), 0.5 (partial correctness), 0.0 (agent was wrong)
  - Feed to Learning Loop (ADR-0059)

---

### **Message Queue & Coalescing**

#### Coalesce Window (ADR-0053, ADR-0053a)
- Nagle-style buffering: 200ms window or 500 chars
- Natural conversation flow, reduced API calls 70-80%
- Turn boundary detection: 2-3s pause threshold

#### Rate Limits (ADR-0053b)
- Token bucket algorithm: 5 messages/second per session
- Burst capacity: 10 messages
- 429 errors, exponential backoff (100ms → 3.2s)

#### Cancel Path (ADR-0053c)
- **K0 Bridge Integration** — `k1/bridge_k0/k0_bridge_client.py`
  - rollback method (WAL transaction abort)
  - pending_writes dict, logger.info k0_rollback

---

### **Turn Boundary Management**

#### Implicit Pause (ADR-0054a)
- Research foundation: Sacks et al. 1974 TRP (0.5-2.5s)
- Google 1.5-2.0s, Alexa 2.0-2.5s, Siri 1.8-2.2s silence thresholds
- <1s pause = mid-thought (don't interrupt), >2s = clear turn end

#### Explicit Submit (ADR-0054b)
- Send button click, Enter key, Shift+Enter, voice "Send" command
- Immediate processing (no wait)

---

### **Voice Pipeline Implementation**

#### ASR Ingress (ADR-0056a)
- **Frame Handling** — 20ms audio frames, buffering strategy, frame drop policy at 80% capacity
- **VAD Processing** — Energy threshold -50dB, 2s silence threshold, RMS energy calculation
- **Partial Results** — Stream intermediate ASR transcripts, is_partial flag, typing indicator UX

#### TTS Synthesis (ADR-0056d, ADR-0056f)
- **Prosody Controls** — Pitch control (Hz), rate control (words/min), emphasis patterns (stress)
- **SSML Generation** — Convert text + prosody to SSML, `<prosody>` tags, `<emphasis>` tags
- **Voice Persona Persistence** — SessionState Section 4 integration, prosody parameter load/save (<10ms P95)
- **Per-User Voice Preferences** — Per-family-member voice profiles, preference learning via Learning Loop

#### Audio Output (ADR-0056e)
- **Buffer Management** — Jitter buffer (80ms), frame reordering, packet loss recovery

---

### **Product Craft UX**

#### Streaming Text & Typing (ADR-0065a)
- **Typing Indicator** — Client-side instant <16ms, CSS animation 3 dots
- **Token Streaming** — Progressive text rendering, 50 tokens/s rate limiting, first token <150ms

#### Session Continuity (ADR-0065b)
- **Device Handoff** — 4-stage protocol: discovery, prompt, transfer, reconciliation
- **Session Transfer** — Last 10 turns transfer, FlatBuffers <50ms serialization, AES-256-GCM encrypted

#### Quick Actions (ADR-0065c)
- **Action Generator** — Generate 3-5 chips, templates for common patterns, LLM-powered for complex
- **Client Rendering** — Chip UI components, keyboard navigation Tab/Arrow, 30s countdown

#### Costly Action Confirmation (ADR-0065d)
- **Action Detection** — SAFETY CRITICAL: detect money transfer, account deletion, data deletion
- **Confirmation Request** — Explicit typed phrases, case-sensitive validation, 5-minute expiration
- **Receipt Generation** — 7-year audit retention, multi-channel delivery chat/email/SMS

---

### **Conversational Delight**

#### Personality System (ADR-0067)
- **Humor Generator** — 50+ templates (puns, callbacks, cultural refs), <200ms generation
- **Celebration Handler** — Milestone detection, goal achievements, celebratory responses
- **Easter Egg System** — Hidden triggers (42, konami_code), low-frequency (0.1% probability)

---

### **Multilingual Support**

#### Language Detection (ADR-0071)
- **Language Detector** — `k1/multilingual/language_detector.py`
  - fastText 9 languages (en, es, fr, de, it, pt, zh, ja, ko)
  - >98% accuracy, <5ms latency, confidence scores

- **Code-Switching Handler** — `k1/multilingual/code_switching.py`
  - Bilingual conversations, 3 styles: MIRROR (match user), UNIFIED (single language), WEIGHTED (blend)

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

## 📚 Complete ADR Reference List (91 ADRs)

### **Quick Reference: All ADRs for Layer 1 - Input**

| ADR | Title | Family |
|-----|-------|--------|
| **ADR-0001** | Memory Kernel | K0 Core |
| **ADR-0001f** | Memory Kernel (Multi-Store) | K0 Core |
| **ADR-0004** | Ambient Sensors | Stream Processing / K1 Core |
| **ADR-0004b** | Dependencies | K1 Core |
| **ADR-0004c** | Documentation | ADR Notes |
| **ADR-0004d** | Testing | K1 Core |
| **ADR-0004f** | Stream Switch | Stream Processing |
| **ADR-0010** | Core System | Capability Security |
| **ADR-0010a** | Token Lifecycle | Capability Security |
| **ADR-0010b** | Assignment Policy | Capability Security |
| **ADR-0010d** | Revocation | Capability Security |
| **ADR-0011a** | Schema Design | FlatBuffers |
| **ADR-0011b** | Code Generation | FlatBuffers |
| **ADR-0011c** | Performance | FlatBuffers |
| **ADR-0011d** | Schema Evolution | FlatBuffers |
| **ADR-0012** | Schema Taxonomy | FlatBuffers Schemas |
| **ADR-0012a** | Layer 1 Schemas | FlatBuffers Schemas |
| **ADR-0013** | SemVer Policy | Schema Versioning |
| **ADR-0013a** | Version Registry | Schema Versioning |
| **ADR-0013b** | CI/CD Automation | Schema Versioning |
| **ADR-0013c** | Deprecation Workflow | Schema Versioning |
| **ADR-0013d** | Contract Testing | Schema Versioning |
| **ADR-0014b** | OpenAPI Generation | REST API Dual Format |
| **ADR-0014d** | Client SDKs | REST API Dual Format |
| **ADR-0015** | Protocol Design | WebSocket Binary Protocol |
| **ADR-0015a** | Protocol Design | WebSocket Binary Protocol |
| **ADR-0015b** | Flow Control | WebSocket Binary Protocol |
| **ADR-0015c** | Reconnection | WebSocket Binary Protocol |
| **ADR-0015d** | Streaming | WebSocket Binary Protocol |
| **ADR-0015e** | Client SDK | WebSocket Binary Protocol |
| **ADR-0016** | Event Taxonomy | SSE Event Schemas |
| **ADR-0016a** | Event Taxonomy | SSE Event Schemas |
| **ADR-0016c** | Filtering | SSE Event Schemas |
| **ADR-0016d** | Browser Integration | SSE Event Schemas |
| **ADR-0019** | Serialization Core | FlatBuffers SessionState |
| **ADR-0019a** | Schema Definition | FlatBuffers SessionState |
| **ADR-0021c** | Compliance | Turn History Retention |
| **ADR-0022d** | FlatBuffers Schema | K0 Bridge Batching |
| **ADR-0023c** | K0 WAL Query | Cursor-Based Pagination |
| **ADR-0029** | Component Metrics | Prometheus Metrics |
| **ADR-0029c** | Component Metrics | Prometheus Metrics |
| **ADR-0042a** | Event Production | K0 SSE Event Streaming |
| **ADR-0042d** | Backpressure | K0 SSE Event Streaming |
| **ADR-0043c** | Topic Routing | SSE Topic Taxonomy |
| **ADR-0046** | Configuration | SSE-WebSocket Bridge |
| **ADR-0047** | SDK Generation | OpenAPI 3.1 Specs |
| **ADR-0048** | K0/K1 Separation | K1 Internal Event Bus |
| **ADR-0049** | Configuration | Fast/Smart Lane Router |
| **ADR-0050** | Sync Strategy | Multi-Device Family Sync |
| **ADR-0052** | Research Foundation | Enhanced HITL Protocols |
| **ADR-0052b** | RED Band Approval | Enhanced HITL Protocols |
| **ADR-0052c** | Nested Clarifications | Enhanced HITL Protocols |
| **ADR-0052d** | Proactive Confirmation | Enhanced HITL Protocols |
| **ADR-0053** | Main | Message Queue & Coalescing |
| **ADR-0053a** | Coalesce Window | Message Queue & Coalescing |
| **ADR-0053b** | Rate Limits | Message Queue & Coalescing |
| **ADR-0053c** | Cancel Path | Message Queue & Coalescing |
| **ADR-0054** | Main | Turn Boundary Management |
| **ADR-0054a** | Implicit Pause | Turn Boundary Management |
| **ADR-0054b** | Explicit Submit | Turn Boundary Management |
| **ADR-0056** | TTS Synthesis | Voice Pipeline Implementation |
| **ADR-0056a** | ASR Ingress | Voice Pipeline Implementation |
| **ADR-0056d** | TTS Synthesis | Voice Pipeline Implementation |
| **ADR-0056e** | Audio Output | Voice Pipeline Implementation |
| **ADR-0056f** | TTS Synthesis | Voice Pipeline Implementation |
| **ADR-0065** | Core System | Product Craft UX |
| **ADR-0065a** | Streaming Text & Typing | Product Craft UX |
| **ADR-0065b** | Session Continuity | Product Craft UX |
| **ADR-0065c** | Quick Actions | Product Craft UX |
| **ADR-0065d** | Costly Action Confirmation | Product Craft UX |
| **ADR-0066** | Simulation Harness | Developer Testing |
| **ADR-0067** | Personality System | Conversational Delight |
| **ADR-0071** | Language Detection | Multilingual Support |
| **ADR-0081** | Knowledge Graph | K0 Core |
| **ADR-0081a** | Knowledge Graph | K0 Core |
| **ADR-0081b** | Knowledge Graph | K0 Core |
| **ADR-0081c** | Knowledge Graph | K0 Core |
| **ADR-0081d** | Knowledge Graph | K0 Core |
| **ADR-0082** | Core Architecture | Multi-Party Dialogue |
| **ADR-0082a** | Speaker Diarization | Multi-Party Dialogue |
| **ADR-0083** | Sensor Drivers | Ambient Sensor Fusion |
| **ADR-0083a** | Sensor Drivers | Ambient Sensor Fusion |
| **ADR-0083b** | Sensor Fusion | Ambient Sensor Fusion |
| **ADR-0084** | Core Architecture | K0 Memory Consolidation |
| **ADR-0084a** | Hippocampal Replay | K0 Memory Consolidation |
| **ADR-0084b** | Sleep State Machine | K0 Memory Consolidation |
| **ADR-0084c** | Knowledge Graph Consol. | K0 Memory Consolidation |
| **ADR-0084d** | Dream Exploration | K0 Memory Consolidation |
| **ADR-0085** | Core Architecture | Embodied Awareness |
| **ADR-0085a** | Location Awareness | Embodied Awareness |
| **ADR-0085b** | BLE Proximity | Embodied Awareness |

### **Cross-Cutting ADRs (Affect All Layer 1)**

**Architecture & Design:**
- ADR-0002 — Actor Model (all Layer 1 modules are pure actors, deterministic)
- ADR-0004 — 52-Module 5-Layer Architecture (Layer 1 definition, hot path)
- ADR-0004a — Event Bus (Layer 1→2 communication, pub/sub)
- ADR-0004b — Import Linting (L1→L5 only, no L1→L2/L3/L4 direct imports)
- ADR-0004d — Layer 1 Integration Tests (end-to-end test suite)

**Serialization & Data:**
- ADR-0011 — FlatBuffers serialization (zero-copy, <1ms serialize)
- ADR-0012 — 76 FlatBuffers schemas (Layer 1: AudioFrame, ASRResult, TTSRequest, VADState, IntentDetected, etc.)
- ADR-0013 — Schema versioning (SemVer, backward compatibility)
- ADR-0019 — SessionState serialization (Layer 1 reads SessionState for context)

**Observability:**
- ADR-0029 — Prometheus metrics (RED method: rate/error/duration for Layer 1 modules)
- ADR-0030 — Trace sampling (cognitive_trace_id propagation, Layer 1 entry point)

**Performance & Reliability:**
- ADR-0024 — Performance budgets (Layer 1: <10ms P95 total)
- ADR-0028 — WFQ scheduler (Layer 1 publishes to REALTIME/INTERACTIVE queues)
- ADR-0009 — Circuit breaker (Layer 1 integrates circuit breakers for ASR/TTS/LLM)

**Security & Privacy:**
- ADR-0010 — Capability security (Layer 1 reads capabilities for intent validation)
- ADR-0032 — Egress control (Layer 1 respects privacy bands for intent routing)
- ADR-0035 — PII detection (Layer 1 redacts PII from audio/text before Layer 2)

**Cost & Resource Management:**
- ADR-0027 — Model placement cascade (Layer 1 ASR/TTS on-device first)
- ADR-0031 — Cost tracking (Layer 1 tracks T3 LLM intent costs)

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

**Status:** ✅ **COMPLETE & ENHANCED** — All Layer 1 ADRs mapped end-to-end with comprehensive coverage from ADR_REFERENCE.md
**Last Updated:** January 2025 (Enhanced with ADR_REFERENCE integration)
**Total ADRs:** 91 ADRs across 31 families covering Layer 1 (4 primary + 87 supporting/cross-cutting)
**Coverage:** 100% of Layer 1 modules (4/4 modules mapped)
**New Additions:** Ambient sensors, multi-party dialogue, embodied awareness, HITL protocols, message coalescing, turn boundaries, voice pipeline, UX craft, personality, multilingual

---

## 📖 Documentation Notes

**Source Files:**
- Primary map: `k1/l1_input/layer1_adr_map.md` (this file)
- ADR reference: `k1/l1_input/ADR_REFERENCE.md` (auto-generated comprehensive inventory)
- Generation script: `scripts/generate_layer_adr_references.py`

**Regeneration:**
To regenerate the ADR_REFERENCE.md file:
```bash
python scripts/generate_layer_adr_references.py
```

**Integration:** This map combines:
1. Original layer1_adr_map.md structure (module-by-module breakdown)
2. ADR_REFERENCE.md comprehensive inventory (91 ADRs across 31 families)
3. Cross-cutting concerns and architectural patterns
4. Performance budgets, observability, and testing strategies
