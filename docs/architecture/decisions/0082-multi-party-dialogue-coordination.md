# ADR-0082: Multi-Party Dialogue Coordination

**Status:** Proposed
**Date:** 2025-10-22
**Priority:** P2 - Post-MVP v1.1
**Capabilities:** #11 (Multi-Party Conversations), #35 (Conflict Resolution)
**Related ADRs:** ADR-0054 (Turn Boundary Management), ADR-0017 (SessionState), ADR-0069 (Affect Modulation), ADR-0082a (Speaker Diarization), ADR-0082b (Turn-Taking), ADR-0082c (Conflict Resolution)

---

## Context

### **Problem Statement**

LLMs process **single-user conversations** by default. Family use cases require handling **multiple speakers** with:

- **Distinct preferences** (Dad prefers steakhouse, Mom prefers vegetarian)
- **Different contexts** (Dad's calendar, Mom's location)
- **Overlapping turns** (simultaneous speech from 2+ people)
- **Conflicting requests** (opposing goals requiring mediation)

**Current Limitation:** K1 Intelligence Module lacks multi-speaker awareness. Without speaker attribution, the system:

1. **Confuses speaker intent** (mixed audio stream → ambiguous transcription)
2. **Loses personalization** (can't distinguish Dad's vs Mom's preferences)
3. **Fails on overlaps** (simultaneous speech → garbled transcription or dropped messages)
4. **Misses conflicts** (opposing requests processed sequentially without conflict detection)

### **LLM-Specific Challenges**

**Challenge 1: Speaker Attribution Without Visual Cues**

Traditional chatbots assume single user OR use explicit user login. Voice-first family assistant must identify speakers from **audio alone** (no login, minimal friction).

```
WITHOUT Multi-Party Coordination:
Dad: "Book dinner reservation for tonight"
Mom (simultaneously): "What's the weather tomorrow?"
ASR: "Book dinner reservation for tonight what's the weather tomorrow" [mixed transcription]
LLM Planner: [Confused - single garbled request] "I'm not sure what you need, can you clarify?"

WITH Multi-Party Coordination:
Audio Input → Speaker Diarization → Two separate streams:
  - Stream 1: speaker_id="Dad", confidence=0.92, text="Book dinner reservation for tonight"
  - Stream 2: speaker_id="Mom", confidence=0.89, text="What's the weather tomorrow?"
LLM Orchestrator: [Assigns 2 agents in parallel]
  - Agent 1 → Dad's request: Queries KG for Dad's restaurant preferences → "Steakhouse 7pm"
  - Agent 2 → Mom's request: Queries SessionState for Mom's location → "Seattle weather tomorrow"
Response: [Two separate TTS outputs, spatially separated OR sequential with speaker tags]
```

**Challenge 2: Per-Speaker Context Retrieval**

LLM needs to retrieve **different context** depending on who is speaking:

```
Dad says: "What's on my calendar?"
→ LLM queries SessionState Section 2 (Scoreboard) with speaker_id="Dad"
→ Returns Dad's calendar: [Meeting 3pm, Dentist 5pm]

Mom says: "What's on my calendar?"
→ LLM queries SessionState Section 2 (Scoreboard) with speaker_id="Mom"
→ Returns Mom's calendar: [Yoga 10am, Client call 2pm]
```

**Challenge 3: Overlapping Speech & Turn Allocation**

Family conversations have **frequent overlaps** (not sequential turns like chatbot UI):

```
Turn Manager detects:
  - Dad speaking (0.92 confidence) at timestamp T=0ms
  - Mom speaking (0.89 confidence) at timestamp T=50ms [OVERLAP detected]

Strategy Options:
1. **First-Speaker Priority:** Queue Mom's request, respond to Dad first (latency +500ms for Mom)
2. **Parallel Processing:** Orchestrator assigns 2 agents, both process simultaneously (2× compute)
3. **Interrupt Handling:** Mom's request has higher priority (e.g., urgent) → pause Dad's processing
```

**Challenge 4: Conflict Detection & Mediation**

LLM must detect **opposing requests** and mediate:

```
Dad: "Book dinner at steakhouse tonight"
Mom (immediately after): "Actually, let's do vegetarian restaurant"

LLM Conflict Detector:
  - Analyzes both requests: [steakhouse vs vegetarian] → CONFLICT detected
  - Sentiment analysis: Dad neutral (0.5), Mom assertive (0.7) → Mom's preference may override
  - Meta Policy: "Conflicting preferences require mediation"

Mediation Strategy:
LLM: "I heard conflicting preferences - Dad suggested steakhouse, Mom suggested vegetarian. Which would you both prefer?"
[Waits for user negotiation]
Dad: "Vegetarian is fine"
LLM: [Proceeds with vegetarian restaurant booking using Mom's preferences]
```

### **Success Criteria**

1. **Speaker Identification:** Correctly attribute utterances to speakers with >90% accuracy (>0.8 confidence threshold)
2. **Per-Speaker Context:** Retrieve and apply correct preferences/context for each identified speaker
3. **Overlap Handling:** Process overlapping speech without data loss (queue OR parallel processing)
4. **Conflict Detection:** Detect opposing requests and trigger mediation (not execute conflicting actions)
5. **Performance:** <100ms P95 speaker identification, <50ms P95 turn allocation decision

---

## Decision

### **Architecture: 3-Layer Multi-Party Pipeline**

**Layer 1: Speaker Diarization (Who is speaking?)**
→ See ADR-0082a for full specification

- **Voice Biometrics:** Extract 768-dim speaker embeddings using pre-trained x-vector or ECAPA-TDNN model
- **Enrollment:** Family members record 30-60 second voice samples for profile creation
- **Real-time Matching:** Compare current audio embedding to enrolled profiles (cosine similarity >0.8 = match)
- **Fallback:** Unknown speakers labeled as "Guest_1", "Guest_2" (no access to private data)

**Layer 2: Multi-Party Turn-Taking (When do overlaps happen?)**
→ See ADR-0082b for full specification

- **Overlapping Speech Detection:** Timestamp analysis + audio energy thresholding
- **Turn Allocation Strategies:**
  - **First-Speaker Priority:** Queue subsequent speakers (sequential processing)
  - **Parallel Processing:** Orchestrator assigns multiple agents (higher compute cost)
  - **Priority-Based Preemption:** Urgent requests interrupt non-urgent ones
- **Turn Boundary Extension:** Enhance ADR-0054 Turn Boundary for multi-speaker scenarios
- **Speaker Context Retrieval:** Query SessionState Section 2 (Scoreboard) with `speaker_id` parameter

**Layer 3: Conflict Resolution (What if preferences clash?)**
→ See ADR-0082c for full specification

- **Sentiment Divergence Detection:** Analyze emotional tone of conflicting requests (assertive vs neutral)
- **Conflict Types:**
  - **Goal Conflicts:** Opposing actions (steakhouse vs vegetarian)
  - **Timing Conflicts:** Same resource, different times (Dad wants music now, Mom wants quiet)
  - **Priority Conflicts:** Both want urgent action (who gets served first?)
- **Mediation Strategies:**
  - **Explicit Confirmation:** "I heard conflicting preferences - which should I prioritize?"
  - **Sentiment-Based Priority:** Defer to speaker with stronger emotional urgency
  - **Meta Policy Integration:** Apply learned family norms ("Mom's dietary restrictions always take priority")

### **Data Flow: Multi-Party Request Processing**

```
┌─────────────────────────────────────────────────────────────────────────┐
│ LAYER 1: SPEAKER DIARIZATION                                            │
├─────────────────────────────────────────────────────────────────────────┤
│ Audio Input (Multi-Channel)                                             │
│   ↓                                                                      │
│ Voice Activity Detection (VAD) → Segment speech regions                 │
│   ↓                                                                      │
│ Speaker Embedding Extraction (x-vector/ECAPA-TDNN)                      │
│   ↓                                                                      │
│ Profile Matching (cosine similarity > 0.8)                              │
│   ↓                                                                      │
│ Speaker Attribution: [speaker_id="Dad", confidence=0.92, segment=T0-T3] │
└─────────────────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────────────────┐
│ LAYER 2: TURN-TAKING COORDINATION                                       │
├─────────────────────────────────────────────────────────────────────────┤
│ Turn Manager: Receives attributed segments                              │
│   ↓                                                                      │
│ Overlap Detection: [Dad T0-T3, Mom T1-T4] → OVERLAP 50% (T1-T3)        │
│   ↓                                                                      │
│ Turn Allocation Strategy:                                               │
│   - Option 1: First-Speaker Priority → Queue Mom (Dad first)            │
│   - Option 2: Parallel Processing → 2 Agents                            │
│   - Option 3: Priority Preemption → Check urgency signals               │
│   ↓                                                                      │
│ Speaker Context Retrieval:                                              │
│   - Query SessionState Section 2 (Scoreboard) with speaker_id="Dad"     │
│   - Returns: {preferences, recent_queries, conversation_style}          │
└─────────────────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────────────────┐
│ LAYER 3: CONFLICT RESOLUTION                                            │
├─────────────────────────────────────────────────────────────────────────┤
│ Conflict Detector: Analyzes requests from multiple speakers             │
│   ↓                                                                      │
│ Goal Comparison: [Dad: steakhouse, Mom: vegetarian] → CONFLICT          │
│   ↓                                                                      │
│ Sentiment Analysis (ADR-0069):                                          │
│   - Dad: neutral (0.5), Mom: assertive (0.7) → Mom higher urgency       │
│   ↓                                                                      │
│ Meta Policy Query: "Dietary restrictions always prioritize" (learned)   │
│   ↓                                                                      │
│ Mediation Strategy: Explicit Confirmation                               │
│   - "I heard conflicting preferences - prioritizing vegetarian per      │
│     family dietary rules. Dad, is that okay?"                           │
│   ↓                                                                      │
│ Await User Response → Proceed with consensus                            │
└─────────────────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────────────────┐
│ LLM ORCHESTRATOR: Execute with Speaker-Specific Context                 │
├─────────────────────────────────────────────────────────────────────────┤
│ Agent 1 (Dad's request):                                                │
│   - KG Query: GET_PREFERENCES(speaker_id="Dad")                         │
│   - Generates plan using Dad's context                                  │
│                                                                          │
│ Agent 2 (Mom's request):                                                │
│   - KG Query: GET_PREFERENCES(speaker_id="Mom")                         │
│   - Generates plan using Mom's context                                  │
└─────────────────────────────────────────────────────────────────────────┘
```

### **Integration Points**

**1. SessionState Section 2 (Scoreboard) - Per-Speaker Context**

Extend `SessionState.scoreboard` with speaker-specific state:

```python
# ADR-0017 SessionState Section 2 Extension
scoreboard: {
    "speakers": {
        "Dad": {
            "speaker_id": "Dad",
            "voice_profile_id": "profile_001",
            "preferences": {
                "restaurant": "steakhouse",
                "meeting_time": "7pm",
                "response_style": "concise"
            },
            "recent_queries": ["weather", "calendar"],
            "last_interaction_ts": 1729620000000000,
            "active": true  # Currently in conversation
        },
        "Mom": {
            "speaker_id": "Mom",
            "voice_profile_id": "profile_002",
            "preferences": {
                "restaurant": "vegetarian",
                "dietary_restrictions": ["vegetarian", "gluten-free"],
                "response_style": "detailed"
            },
            "recent_queries": ["calendar", "grocery list"],
            "last_interaction_ts": 1729620050000000,
            "active": true
        }
    },
    "active_speakers": ["Dad", "Mom"],  # Currently speaking
    "conversation_mode": "multi_party"
}
```

**2. Turn Boundary Management (ADR-0054) - Multi-Speaker Extension**

Current ADR-0054 assumes single speaker per turn. Extend for multi-party:

```python
# Turn Boundary Multi-Party Extension
turn_state: {
    "turn_id": "turn_00042",
    "mode": "multi_party",  # NEW: single_user | multi_party
    "speakers": [
        {
            "speaker_id": "Dad",
            "segment_start_ts": 1729620000000000,
            "segment_end_ts": 1729620003000000,
            "confidence": 0.92,
            "utterance": "Book dinner reservation for tonight"
        },
        {
            "speaker_id": "Mom",
            "segment_start_ts": 1729620001000000,  # Overlap with Dad
            "segment_end_ts": 1729620004000000,
            "confidence": 0.89,
            "utterance": "What's the weather tomorrow?"
        }
    ],
    "overlap_detected": true,
    "overlap_duration_ms": 2000,  # T1-T3 overlap
    "allocation_strategy": "parallel_processing"
}
```

**3. K0 Knowledge Graph (ADR-0081) - Speaker Profiles**

Store speaker preferences in Knowledge Graph:

```cypher
# Speaker entity nodes
(Dad:Person {
    name: "Dad",
    speaker_id: "Dad",
    voice_profile_id: "profile_001"
})

# Preference relationships
(Dad)-[:PREFERS_RESTAURANT {type: "steakhouse", confidence: 0.95}]->(Steakhouse:RestaurantType)
(Mom)-[:PREFERS_RESTAURANT {type: "vegetarian", confidence: 1.0}]->(Vegetarian:RestaurantType)
(Mom)-[:HAS_DIETARY_RESTRICTION {type: "vegetarian"}]->(Restriction:DietaryRestriction)

# Family norm (learned from 20 interactions)
(Family)-[:FAMILY_NORM {
    rule: "dietary_restrictions_prioritize",
    confidence: 0.87,
    learned_from: 20
}]->(NormRule)
```

**4. Affect Modulation (ADR-0069) - Sentiment Divergence**

Detect emotional tone differences for conflict resolution:

```python
# Sentiment divergence detection
sentiment_analysis = {
    "Dad": {
        "utterance": "Book dinner at steakhouse tonight",
        "sentiment": "neutral",
        "confidence": 0.5,
        "urgency": 0.3
    },
    "Mom": {
        "utterance": "Actually, let's do vegetarian restaurant",
        "sentiment": "assertive",
        "confidence": 0.7,
        "urgency": 0.6  # Higher urgency → may override
    },
    "divergence_detected": true,
    "conflict_type": "goal_conflict"
}
```

### **Performance Budget**

| **Metric**                     | **Target (P95)** | **Rationale**                                                                 |
|--------------------------------|------------------|-------------------------------------------------------------------------------|
| Speaker Identification Latency | <100ms           | Real-time diarization must not block ASR pipeline (ADR-0053 TTFT <150ms)      |
| Voice Embedding Extraction     | <50ms            | x-vector/ECAPA-TDNN inference on CPU (optimized ONNX runtime)                 |
| Profile Matching (Cosine Sim)  | <10ms            | Compare 768-dim embeddings against 10 enrolled profiles                       |
| Turn Allocation Decision       | <50ms            | Overlap detection + strategy selection (first-speaker vs parallel)            |
| Conflict Detection             | <100ms           | Goal comparison + sentiment analysis (ADR-0069)                               |
| **Total Multi-Party Overhead** | **<200ms**       | Added latency on top of single-user flow (acceptable for family conversations)|

**Justification:** 200ms overhead is acceptable because:
1. Multi-party conversations are typically **slower-paced** than single-user (social dynamics, turn-taking)
2. Parallel processing strategy can offset latency for concurrent speakers
3. User expectation: Family assistant prioritizes **correctness** (right speaker context) over speed

### **Speaker Enrollment Flow**

**First-Time Setup (Per Family Member):**

```
User: "Add new family member"
System: "Please state your name"
User: "This is Dad"
System: "Hi Dad, I'll now record your voice profile. Please read the following sentences naturally:"

[Enrollment prompts - 30-60 seconds total]:
1. "The quick brown fox jumps over the lazy dog"
2. "I need help with my calendar and grocery list"
3. "What's the weather forecast for this week?"
[... 5-7 more sentences covering phonetic diversity]

System: [Extracts 10-15 embeddings, averages to create profile]
         [Stores profile in K0 with speaker_id="Dad", voice_profile_id="profile_001"]

System: "Voice profile created for Dad. I'll now recognize you in conversations."
```

**Enrollment Requirements:**
- **Duration:** 30-60 seconds of speech (10-15 utterances)
- **Environment:** Quiet room (SNR >20dB) for clean training data
- **Diversity:** Sentences cover diverse phonemes for robust embedding
- **Storage:** 768-dim embedding + metadata (~5KB per profile)

### **Unknown Speaker Handling**

**Scenario:** Guest visits family home, speaks to assistant

```
Audio Input → Speaker Diarization → No profile match (all similarities <0.8)
           ↓
System labels: speaker_id="Guest_1" (temporary ID)
           ↓
Privacy Policy: Guest speakers have restricted access
  - ❌ Cannot access family calendar
  - ❌ Cannot access private memories (RED/AMBER band)
  - ✅ Can query public information (weather, news)
  - ✅ Can control shared devices (music, lights) if allowed by family
           ↓
System: "I don't recognize your voice. I can help with general queries, but I'll need family member confirmation for private information."
```

### **Conflict Resolution Strategies**

**Strategy 1: Explicit Confirmation (Default)**

```
Dad: "Book dinner at steakhouse"
Mom: "Let's do vegetarian restaurant"
→ Conflict Detector: [steakhouse vs vegetarian]
→ LLM: "I heard conflicting preferences - Dad suggested steakhouse, Mom suggested vegetarian. Which would you both prefer?"
→ [Wait for user negotiation]
```

**Strategy 2: Sentiment-Based Priority**

```
Dad: "Book steakhouse" [neutral sentiment, urgency=0.3]
Mom: "Actually, vegetarian restaurant" [assertive sentiment, urgency=0.7]
→ Sentiment Divergence: Mom higher urgency (0.7 vs 0.3)
→ LLM: "Prioritizing Mom's preference (vegetarian) based on urgency. Dad, is that okay?"
```

**Strategy 3: Meta Policy Learned Norms**

```
Meta Policy Query: GET_NORM(context="dietary_restrictions")
→ Returns: {rule: "dietary_restrictions_always_prioritize", confidence: 0.87}
→ LLM: "Following family dietary rules, I'll book a vegetarian restaurant. Dad, this aligns with Mom's restrictions - okay?"
```

**Strategy 4: Time-Based Deferral**

```
Dad: "Play loud music" [11pm, baby sleeping]
Mom: "Please don't, baby is asleep"
→ Conflict + Meta Policy: "No loud activities after 9pm" (learned norm)
→ LLM: "It's 11pm and the baby is sleeping. I'll defer to Mom's preference for quiet. Dad, how about headphones instead?"
```

### **Edge Cases**

**Edge Case 1: Rapid Speaker Switching (Barge-In)**

```
Dad starts: "Book dinner at—"
Mom interrupts: "Actually, I already booked dinner"
→ Barge-In Detection (ADR-0054c): Mom's speech confidence >0.8 while Dad speaking
→ Turn Manager: Interrupt Dad's processing, queue request
→ LLM: [Responds to Mom first] "Great, I see you booked dinner. Dad, did you still need something?"
```

**Edge Case 2: Three+ Speakers (Multi-Way Conversation)**

```
Dad: "What's for dinner?"
Mom: "Vegetarian pasta"
Child: "Can we have pizza instead?"
→ Turn Manager: 3 speakers detected
→ Strategy: First-Speaker Priority (sequential processing)
  1. Respond to Dad: "Mom suggested vegetarian pasta, but [Child] wants pizza. Want to decide?"
  2. Queue Mom/Child responses for follow-up
```

**Edge Case 3: Low-Confidence Speaker ID (<0.8)**

```
Audio Input → Speaker Diarization → Best match: Dad (confidence=0.65, below threshold)
→ System: Uncertain speaker attribution
→ Fallback: "I'm not sure who's speaking. Could you confirm?"
OR: Proceed with generic context (no personalization until confirmed)
```

**Edge Case 4: Speaker Profile Drift (Voice Changes Over Time)**

```
Dad's voice changes due to: cold, aging, background noise
→ Profile matching: Dad (confidence=0.75, below 0.8 threshold)
→ Adaptive Update: "Your voice sounds a bit different today - are you [Dad]?"
→ User confirms → System updates profile with new embeddings (incremental learning)
```

---

## Consequences

### **Positive**

1. **Personalized Multi-User Experience:** Each family member gets responses tailored to their preferences, context, and conversation history
2. **Graceful Overlap Handling:** System doesn't break when multiple people speak (queuing OR parallel processing)
3. **Conflict Mediation:** LLM acts as intelligent mediator for opposing requests (not blind execution)
4. **Privacy-Aware:** Unknown speakers (guests) restricted from private family data
5. **Learned Norms:** Meta Policy Engine learns family-specific conflict resolution patterns over time

### **Negative**

1. **Enrollment Friction:** Family members must record 30-60 second voice samples (one-time setup burden)
2. **Compute Overhead:** Speaker diarization adds <200ms latency + CPU cost for embedding extraction
3. **Profile Maintenance:** Voice profiles may drift over time (require periodic re-enrollment OR adaptive updates)
4. **Privacy Risk:** Voice biometrics stored in K0 (must encrypt profiles, restrict access)
5. **Complex Debugging:** Multi-party conflicts introduce non-deterministic behavior (harder to test/debug)

### **Risks & Mitigations**

| **Risk**                                  | **Impact** | **Mitigation**                                                                 |
|-------------------------------------------|------------|--------------------------------------------------------------------------------|
| Speaker misidentification (Dad → Mom)     | HIGH       | Require >0.8 confidence threshold, fallback to "unknown" if ambiguous          |
| Voice spoofing (recording of Dad's voice) | MEDIUM     | Future: Liveness detection (interactive enrollment), anti-spoofing models      |
| Profile storage breach (voice biometrics) | HIGH       | Encrypt embeddings at rest (AES-256-GCM per ADR-0036), restrict K0 port access |
| Conflict resolution loops (endless back-and-forth) | MEDIUM | Max 3 mediation attempts → escalate to "Please decide offline and tell me" |
| Performance degradation (4+ speakers)     | MEDIUM     | Limit max concurrent speakers to 3, queue additional speakers                  |

### **Tradeoffs**

**Tradeoff 1: Enrollment Burden vs Personalization Quality**
- **Decision:** Require 30-60 second enrollment per family member
- **Rationale:** High-quality embeddings enable accurate speaker ID (>90%), worth one-time friction

**Tradeoff 2: First-Speaker Priority vs Parallel Processing**
- **Decision:** Default to First-Speaker Priority (sequential), opt-in to Parallel Processing for power users
- **Rationale:** Parallel processing doubles compute cost, most families tolerate +500ms queue latency

**Tradeoff 3: Explicit Confirmation vs Sentiment-Based Priority**
- **Decision:** Start with Explicit Confirmation (conservative), learn toward Sentiment-Based over time
- **Rationale:** Avoid incorrect assumptions early (trust-building phase), automate after high confidence (>0.87)

---

## Implementation Plan

### **Phase 1: Speaker Diarization Foundation (Weeks 1-4)**

**Week 1-2: Voice Biometrics Integration**
- [ ] Integrate x-vector OR ECAPA-TDNN model (ONNX runtime for CPU inference)
- [ ] Create enrollment flow (record 30-60 second samples, extract embeddings)
- [ ] Store profiles in K0 with encryption (AES-256-GCM per ADR-0036)
- [ ] Implement profile matching (cosine similarity >0.8)

**Week 3-4: Real-Time Speaker Identification**
- [ ] Extend ADR-0053 ASR pipeline with speaker diarization stage
- [ ] Implement VAD (Voice Activity Detection) for speech segmentation
- [ ] Tag ASR output with `speaker_id` + `confidence` metadata
- [ ] Handle unknown speakers (Guest_1, Guest_2 labels)

**Deliverables:**
- `k1/l1_input/streams/operators/speaker_identifier.py` (real-time matching)
- `k1/l1_input/streams/operators/speaker_enrollment.py` (profile creation)
- WARD tests: Enrollment flow, profile matching accuracy (>90%), unknown speaker handling

### **Phase 2: Multi-Party Turn-Taking (Weeks 5-8)**

**Week 5-6: Overlap Detection & Turn Allocation**
- [ ] Implement overlapping speech detector (timestamp + energy analysis)
- [ ] Create turn allocation strategies: First-Speaker Priority, Parallel Processing, Priority Preemption
- [ ] Extend ADR-0054 Turn Boundary for multi-speaker scenarios
- [ ] Integrate with SessionState Section 2 (Scoreboard) for speaker context retrieval

**Week 7-8: Speaker Context Management**
- [ ] Extend SessionState Section 2 (Scoreboard) with per-speaker state
- [ ] Implement speaker context retrieval API: `GET_SPEAKER_CONTEXT(speaker_id)`
- [ ] Integrate K0 Knowledge Graph (ADR-0081) for speaker preferences
- [ ] Handle speaker switching (barge-in from ADR-0054c)

**Deliverables:**
- `k1/l3_execution/dialogue/multi_party_turn_manager.py` (turn allocation)
- `k1/l3_execution/dialogue/overlapping_detector.py` (overlap detection)
- WARD tests: Overlap handling, turn allocation strategies, speaker context retrieval

### **Phase 3: Conflict Resolution (Weeks 9-12)**

**Week 9-10: Conflict Detection**
- [ ] Implement goal comparison (opposing actions: steakhouse vs vegetarian)
- [ ] Integrate sentiment analysis (ADR-0069) for urgency detection
- [ ] Create conflict type taxonomy: goal, timing, priority conflicts
- [ ] Query Meta Policy Engine for learned family norms

**Week 11-12: Mediation Strategies**
- [ ] Implement Explicit Confirmation strategy (default)
- [ ] Implement Sentiment-Based Priority (opt-in)
- [ ] Implement Meta Policy Learned Norms (adaptive)
- [ ] Create mediation loop with max 3 attempts (prevent endless back-and-forth)

**Deliverables:**
- `k1/l3_execution/dialogue/sentiment_divergence.py` (conflict detection)
- `k1/l3_execution/dialogue/mediation_strategies.py` (resolution tactics)
- WARD tests: Conflict detection accuracy, mediation loop termination, norm integration

### **Phase 4: Integration & Testing (Weeks 13-14)**

**Week 13: End-to-End Integration**
- [ ] Wire speaker diarization → turn-taking → conflict resolution pipeline
- [ ] Test multi-party scenarios: 2 speakers, 3 speakers, unknown speakers
- [ ] Performance tuning: <100ms speaker ID, <50ms turn allocation

**Week 14: Edge Case Hardening**
- [ ] Test rapid speaker switching (barge-in)
- [ ] Test low-confidence speaker ID (<0.8 threshold)
- [ ] Test profile drift (voice changes over time)
- [ ] Security audit: Voice biometric encryption, anti-spoofing

**Deliverables:**
- End-to-end WARD tests: Multi-party conversation flows
- Performance benchmarks: <200ms total multi-party overhead
- Security validation: Encrypted profiles, restricted guest access

---

## Metrics & Observability

### **Speaker Identification Metrics**

```python
# Prometheus metrics
speaker_identification_latency_ms = Histogram(
    'speaker_identification_latency_ms',
    'Speaker diarization latency',
    buckets=[10, 25, 50, 75, 100, 150, 200]
)

speaker_identification_confidence = Histogram(
    'speaker_identification_confidence',
    'Speaker match confidence score',
    buckets=[0.5, 0.6, 0.7, 0.8, 0.85, 0.9, 0.95, 1.0]
)

speaker_identification_accuracy = Gauge(
    'speaker_identification_accuracy',
    'Speaker ID accuracy (ground truth validation)'
)

unknown_speaker_detections_total = Counter(
    'unknown_speaker_detections_total',
    'Total unknown speaker detections (guests)'
)
```

### **Turn-Taking Metrics**

```python
overlapping_speech_detections_total = Counter(
    'overlapping_speech_detections_total',
    'Total overlapping speech events'
)

turn_allocation_latency_ms = Histogram(
    'turn_allocation_latency_ms',
    'Turn allocation decision latency',
    buckets=[5, 10, 25, 50, 75, 100]
)

turn_allocation_strategy = Counter(
    'turn_allocation_strategy',
    'Turn allocation strategy used',
    ['strategy']  # first_speaker, parallel, priority_preemption
)

speaker_context_retrieval_latency_ms = Histogram(
    'speaker_context_retrieval_latency_ms',
    'SessionState speaker context retrieval latency',
    buckets=[5, 10, 25, 50]
)
```

### **Conflict Resolution Metrics**

```python
conflict_detections_total = Counter(
    'conflict_detections_total',
    'Total conflict detections',
    ['conflict_type']  # goal, timing, priority
)

mediation_strategy_used = Counter(
    'mediation_strategy_used',
    'Mediation strategy applied',
    ['strategy']  # explicit_confirmation, sentiment_priority, meta_policy
)

mediation_success_rate = Gauge(
    'mediation_success_rate',
    'Mediation success rate (user accepts resolution)'
)

mediation_loop_iterations = Histogram(
    'mediation_loop_iterations',
    'Number of mediation attempts before resolution',
    buckets=[1, 2, 3, 4, 5]
)
```

### **Alerts**

```yaml
# Grafana alerts
alerts:
  - alert: HighSpeakerMisidentificationRate
    expr: speaker_identification_accuracy < 0.9
    for: 5m
    severity: warning
    description: "Speaker ID accuracy dropped below 90% - check profile drift"

  - alert: MultiPartyLatencyExceeded
    expr: histogram_quantile(0.95, speaker_identification_latency_ms) > 100
    for: 2m
    severity: critical
    description: "Speaker diarization P95 latency >100ms - performance degradation"

  - alert: FrequentConflictDetections
    expr: rate(conflict_detections_total[5m]) > 0.5
    for: 10m
    severity: info
    description: "High conflict rate - may indicate family tension or preference drift"
```

---

## Sub-ADRs

- **ADR-0082a:** Speaker Diarization & Voice Biometrics (x-vector/ECAPA-TDNN, enrollment, profile matching)
- **ADR-0082b:** Multi-Party Turn-Taking Coordination (overlap detection, turn allocation strategies, speaker context)
- **ADR-0082c:** Conflict Resolution Strategies (sentiment divergence, mediation tactics, meta policy integration)

---

## References

### **Research Foundation**

1. **Speaker Diarization:**
   - Snyder et al. (2018): "X-vectors: Robust DNN Embeddings for Speaker Recognition" (Johns Hopkins University)
   - Desplanques et al. (2020): "ECAPA-TDNN: Emphasized Channel Attention for Speaker Recognition" (Ghent University)
   - Bredin et al. (2020): "pyannote.audio: Neural Building Blocks for Speaker Diarization" (CNRS/IRIT)

2. **Multi-Party Dialogue:**
   - Traum & Rickel (2002): "Embodied Agents for Multi-party Dialogue in Immersive Virtual Worlds" (USC ICT)
   - Bohus & Horvitz (2011): "Multiparty Turn Taking in Situated Dialog" (Microsoft Research)
   - Skantze (2021): "Turn-taking in Conversational Systems and Human-Robot Interaction" (KTH Sweden)

3. **Conflict Resolution:**
   - De Dreu & Gelfand (2008): "Conflict in the Workplace: Sources, Functions, and Dynamics" (Stanford)
   - Pruitt & Rubin (1986): "Social Conflict: Escalation, Stalemate, and Settlement" (NYU)
   - Fisher & Ury (1981): "Getting to Yes: Negotiating Agreement Without Giving In" (Harvard Negotiation Project)

### **Related ADRs**

- **ADR-0017:** SessionState 6-Section Design (Section 2 Scoreboard extended for per-speaker context)
- **ADR-0054:** Turn Boundary Management (extended for multi-party overlaps, barge-in)
- **ADR-0069:** Affect Modulation (sentiment divergence for conflict detection)
- **ADR-0081:** K0 Knowledge Graph (speaker preference storage, family norm learning)
- **ADR-0036:** E2EE for RED Band Data (voice biometric encryption)

### **External Standards**

- **NIST Speaker Recognition Evaluation (SRE):** Industry benchmark for speaker verification accuracy
- **VoxCeleb Dataset:** Large-scale speaker identification corpus (>7,000 speakers, 1M+ utterances)
- **DIHARD Challenge:** Diarization benchmarks for real-world scenarios (overlapping speech, noise)

---

## Changelog

- **2025-10-22:** Initial proposal for Multi-Party Dialogue Coordination (v1.1 Post-MVP)

---

**Next Steps:**

1. **Review:** Architecture review with stakeholders (2 weeks)
2. **Prototyping:** Proof-of-concept with x-vector model on VoxCeleb dataset (3 weeks)
3. **Sub-ADR Creation:** Create ADR-0082a, ADR-0082b, ADR-0082c (4 weeks)
4. **Contract Development:** Add Epic for Multi-Party Dialogue Contracts (~25 files)
5. **Implementation:** Follow 14-week implementation plan (Phase 1-4)
