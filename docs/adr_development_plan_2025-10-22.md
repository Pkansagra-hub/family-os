# ADR Development Plan - October 22, 2025

**Purpose:** End-to-end plan for creating, updating, and enhancing ADRs to support 39 missing UX capabilities

**Status:** 📋 PLANNING PHASE
**Created:** 2025-10-22
**Owner:** Architecture Team
**Timeline:** 18-24 weeks (4.5-6 months)

---

## 📊 Executive Summary

**Scope Analysis:**

- **39 Missing Capabilities** identified for seamless UX
- **9 MVP Capabilities** (27% of unique features)
- **23 Post-MVP v1.1 Capabilities** (70% of unique features)
- **1 Post-MVP v1.2+ Capability** (3% - blocked by Knowledge Graph)
- **6 Duplicate Capabilities** (consolidate implementation)

**ADR Work Required:**

- **7-8 New ADRs** needed
- **10 Sub-ADRs** to extend existing ADRs
- **8 Major ADR Amendments** required
- **Total Work Items:** ~25-26

**Critical Findings:**

- ✅ **All 9 MVP capabilities already have ADR architecture!**
- ⚠️ **Knowledge Graph** is biggest gap (blocks 2 capabilities)
- ✅ **Graceful Degradation (#29)** already architected (3 ADRs)
- ⚠️ **K1 implementation debt**: 10-20% complete vs 80+ comprehensive ADRs

**Contract Integration:**

- **741 contract files** from existing ADRs (per contract_development_plan.md)
- **~150+ new contract files** needed for new ADRs
- **~80+ contract updates** for ADR amendments
- **Total:** ~970+ contract files

---

## 🎯 Development Phases

### **Phase 1: MVP ADR Enhancements (Weeks 1-6)**

- Verify Graceful Degradation implementation
- Create MVP sub-ADRs (5 items)
- Update ADR-0004 (52→56 modules)
- Update ADR-0017 (SessionState extensions)

### **Phase 2: Post-MVP ADR Architecture (Weeks 7-14)**

- Create 7-8 new ADRs
- Create 10 sub-ADRs
- Update 6 major ADRs

### **Phase 3: Contract & Implementation (Weeks 15-24)**

- Generate contracts from new ADRs
- Update existing contracts
- Implement MVP capabilities

---

## 📦 EPIC 1: MVP ADR Work (Weeks 1-6)

**Goal:** Enhance existing ADRs to support 9 MVP capabilities

**Priority:** 🔴 **CRITICAL** - Blocks MVP release

### **🧠 Context: Why This Matters for LLM-Powered Architecture**

FamilyOS is **NOT a traditional if/else chatbot** - it's an **LLM-powered agentic orchestrator** with:

- **4 AI Agents** (Planner, Supervisor, Consolidator, Arbiter) making runtime decisions
- **54 Pure Actors** (deterministic components) enforcing contracts
- **K0 Memory Kernel** (episodic, semantic, procedural) for context-aware intelligence
- **K1 Intelligence Module** orchestrating multi-agent collaboration via Contract Net Protocol

**Traditional Chatbot:** User asks → keyword matching → canned response
**FamilyOS:** User asks → LLM generates plan → orchestrator negotiates with agents → tools execute → context stored in memory → learned preferences applied

**Why MVP ADRs Matter:**

- **Graceful Degradation (#29):** LLMs need fallback strategies when resources constrained (thermal throttling → cascade NPU→GPU→CPU→Remote, not crash)
- **Cross-Modal Continuity (#1):** LLMs process text, voice, images seamlessly - need unified input bus to maintain conversation context across modality switches
- **Dialogue Repair (#10):** LLMs can misunderstand - need clarification pipeline with confidence thresholds (not hard-coded error messages)
- **Voice Continuity (#19):** LLMs generate text, TTS converts to speech - need persona persistence so voice tone stays consistent across sessions (not random prosody each time)
- **SessionState (#17):** LLMs are stateless - need 6-section state management to remember conversation context, preferences, affect (not restart from scratch each turn)

**This epic ensures LLM capabilities translate to seamless UX.**

---

### **Issue 1.1: Verify Graceful Degradation Implementation** 🚨 **HIGHEST PRIORITY**

**Capability:** #29 (Graceful Degradation Mode)
**Status:** Architecture complete (3 ADRs), **verify implementation exists**
**Effort:** 1 week
**Priority:** P0 - **PRODUCTION CRITICAL**

#### **🎯 What We're Trying to Accomplish**

**Problem:** LLM inference is **resource-intensive** (NPU: 30ms/10W, GPU: 50ms/12W, CPU: 120ms/15W). When device overheats or memory pressure increases, traditional systems **crash or hang**. FamilyOS must **gracefully degrade** to maintain functionality.

**LLM-Specific Challenges:**

- **Model Size:** LLMs are 1-10GB+, require NPU/GPU acceleration for real-time (<150ms TTFT)
- **Thermal Throttling:** Continuous inference generates heat, triggers thermal limits (85°C critical)
- **Resource Contention:** Multiple agents + tools + models compete for memory (512MB budget)
- **Context Length:** Long conversations consume more memory, slower inference

**Solution (Already Architected):**

- **ADR-0026 Thermal Hysteresis:** Monitor temperature, switch models preemptively (70°C → downgrade warning, 85°C → emergency cascade to remote)
- **ADR-0027 Model Placement Cascade:** 4-tier fallback (NPU → GPU → CPU → Remote Cloud), maintain <500ms P95 even on CPU
- **ADR-0061 Backpressure Cascade:** Per-stream watermarks (80% warn, 90% degrade, 95% reject), prevent OOM crashes

**Success Criteria:** LLM keeps responding even when device hot/low-memory (degraded quality acceptable, crash unacceptable)

**This is PRODUCTION CRITICAL because LLM workloads WILL hit resource limits in real family usage.**

#### **6-Point Plan:****1. Create New ADR:** ❌ **NOT NEEDED** - Already exists

- ADR-0026 (Thermal Hysteresis Matrix) ✅
- ADR-0027 (Model Placement Cascade) ✅
- ADR-0061 (3-Tier Backpressure Cascade) ✅

**2. Create Sub-ADR:** ❌ **NOT NEEDED**

**3. Update Existing ADR:**

- [ ] **ADR-0026:** Verify thermal sensor polling implementation
- [ ] **ADR-0027:** Verify 4-tier cascade (NPU→GPU→CPU→Remote) implementation
- [ ] **ADR-0061:** Verify backpressure watermark monitoring implementation
- **Status Check:** Grep codebase for implementation evidence

**4. Update ADR Family Map:**

- [ ] Add entries for Graceful Degradation components (if implemented)
- **File:** `docs/architecture/tables/adr_family_map.md`
- **Entries:**

     ```
     | Graceful Degradation | Thermal Monitoring | Sensor Polling | L5 | k1/l5_infrastructure/thermal/sensor_poller.py | ... | ADR-0026 |
     | Graceful Degradation | Thermal Monitoring | Hysteresis Controller | L5 | k1/l5_infrastructure/thermal/hysteresis.py | ... | ADR-0026 |
     | Graceful Degradation | Model Placement | Cascade Engine | L5 | k1/l5_infrastructure/placement/cascade_engine.py | ... | ADR-0027 |
     | Graceful Degradation | Model Placement | Circuit Breakers | L5 | k1/l5_infrastructure/placement/circuit_breakers.py | ... | ADR-0027 |
     | Graceful Degradation | Backpressure | Watermark Monitor | L5 | k1/l5_infrastructure/backpressure/watermark_monitor.py | ... | ADR-0061 |
     | Graceful Degradation | Backpressure | Cascade Controller | L5 | k1/l5_infrastructure/backpressure/cascade_controller.py | ... | ADR-0061 |
     ```

**5. Update Contract Development Plan:**

- [ ] **File:** `k1/contracts/contract_development_plan.md`
- [ ] **Verify contracts exist:**
  - Epic 4.3.3: Thermal & Placement Contracts (28 files) ✅
  - Epic 2.13: Backpressure Cascade Contracts (28 files) ✅
- [ ] **Add implementation status:** Mark as "IMPLEMENTED" or "PENDING"

**6. Verify Codebase Mentions:**

- [ ] **Search:** `grep -r "thermal" k1/l5_infrastructure/`
- [ ] **Search:** `grep -r "placement" k1/l5_infrastructure/`
- [ ] **Search:** `grep -r "backpressure" k1/l5_infrastructure/`
- [ ] **Search:** `grep -r "ADR-0026" k1/**/*.py`
- [ ] **Search:** `grep -r "ADR-0027" k1/**/*.py`
- [ ] **Search:** `grep -r "ADR-0061" k1/**/*.py`
- [ ] **Expected:** Implementation files referencing ADRs in docstrings
- [ ] **If MISSING:** Create implementation plan (6-8 weeks, 3 complex systems)

**Acceptance Criteria:**

- [ ] Implementation status documented (EXISTS or NEEDS_IMPLEMENTATION)
- [ ] If exists: ADR family map updated, contracts marked IMPLEMENTED
- [ ] If missing: Create implementation epic with 6-8 week timeline

---

### **Issue 1.2: ADR-0004 Amendment #2 - Add 4 New Modules**

**Capability:** #1 (Cross-Modal), #3 (Ambient Context), #11 (Multi-Party)
**Status:** New modules needed
**Effort:** 2 weeks
**Priority:** P0 - **MVP CRITICAL**

#### **🎯 What We're Trying to Accomplish**

**Problem:** LLMs can process **multiple modalities** (text, voice, images), but K1 architecture currently has **gaps** in unified input handling. Users expect **seamless transitions** ("Show me photos of Seattle" → "Book flight there" - LLM understands "there" = Seattle from image context).

**LLM-Powered Intelligence Needs:**

1. **Cross-Modal Context (Module #53 - Stream Switch):**
   - **Why LLM Needs This:** LLM sees conversation as sequence of messages. When user switches from voice → text → image, LLM needs **context preservation** (not separate conversations).
   - **Traditional Chatbot:** Each modality is separate pipeline (voice bot, text bot, image bot)
   - **FamilyOS:** Unified multi-modal bus feeds LLM with full conversation history regardless of input method
   - **Example:** User says "What's the weather?" (voice) → LLM generates response → User types "What about tomorrow?" (text) → LLM remembers "weather" context from voice turn

2. **Ambient Context Awareness (Module #54 - Ambient Sensor Fusion):**
   - **Why LLM Needs This:** LLM responses should be **contextually appropriate** (whisper when others present, don't suggest loud music during baby naptime)
   - **Traditional Chatbot:** No environmental awareness, always same volume/tone
   - **FamilyOS:** Sensor fusion (PIR motion, mmWave radar, BLE proximity, WiFi devices, camera person detection) feeds LLM with room state
   - **Example:** LLM detects "3 people in room" → adjusts response tone, avoids privacy-sensitive information

3. **Multi-Party Conversations (Module #55 - Speaker Diarization):**
   - **Why LLM Needs This:** Family conversations involve **multiple speakers**. LLM needs to know **who said what** to maintain per-person context.
   - **Traditional Chatbot:** Single user only, no speaker tracking
   - **FamilyOS:** Voice biometrics + spatial audio + face tracking → LLM sees "Dad: 'What's for dinner?'" vs "Mom: 'What's for dinner?'" as separate contexts
   - **Example:** Dad asks "Book dinner reservation" → LLM remembers Dad's preferences (steakhouse), Mom asks same → LLM remembers Mom's preferences (vegetarian)

4. **Meta Policy Engine (Module #56 - Social Norm Modeling):**
   - **Why LLM Needs This:** LLMs can generate **inappropriate responses** (suggest loud music at midnight, book expensive items without asking). Meta Policy provides **social context** to constrain LLM behavior.
   - **Traditional Chatbot:** Hard-coded rules ("if time > 10pm then quiet_mode")
   - **FamilyOS:** LLM learns family norms ("Dad always rejects loud activities after 9pm" → meta policy triggers proactive confirmation "You usually avoid this, proceed?")
   - **Example:** LLM suggests booking $500 concert tickets → Meta Policy detects "high-cost action, no explicit approval" → triggers HITL confirmation before executing

**Success Criteria:** LLM can handle multi-modal inputs, adapt to environment, distinguish speakers, respect family norms (not just respond to keywords)

**This is MVP because LLM intelligence without context awareness = frustrating user experience.**

#### **6-Point Plan:****1. Create New ADR:** ❌ **NOT NEEDED** - Amending ADR-0004

**2. Create Sub-ADR:** ✅ **YES**

- [ ] **ADR-0004f: Stream Switch Multi-Modal Bus**
  - **Purpose:** Unified multi-modal input bus for capability #1 (Cross-Modal Continuity)
  - **Location:** `docs/architecture/decisions/0004f-stream-switch-multi-modal-bus.md`
  - **Content:**
    - **Module #53:** `k1/l1_input/streams/stream_switch/`
    - **Components:** `MultiModalInputBus`, `ModalityTransitionManager`, `CrossModalContextPreserver`
    - **Integration:** Connect to all L1 stream operators (audio, video, text, touch, GPS)
    - **Performance:** <5ms modality switch P95
    - **Status:** Proposed for MVP

**3. Update Existing ADR:**

- [ ] **ADR-0004: 52-Module Architecture → 56-Module Architecture**
- **File:** `docs/architecture/decisions/0004-52-module-5-layer-architecture.md`
- **Changes:**
  - **Line ~50:** Update module count `52 modules` → `56 modules`
  - **Line ~150:** Add Layer 1 module: `m053: streams/stream_switch`
  - **Line ~155:** Add Layer 1 module: `m054: streams/ambient_sensor_fusion`
  - **Line ~160:** Add Layer 1 module: `m055: streams/speaker_diarization`
  - **Line ~165:** Add Layer 1 module: `m056: meta_policy`
- **Add Amendment Section:**

     ```markdown
     ## Amendment #2 (2025-10-22)

     **Reason:** Support 39 missing UX capabilities (Cross-Modal, Ambient Context, Multi-Party, Meta Policy)

     **Changes:**
     - Module count: 52 → 56 modules
     - Added 4 new Layer 1 modules:
       - m053: `k1/l1_input/streams/stream_switch/` (Cross-Modal Continuity)
       - m054: `k1/l1_input/streams/operators/ambient_sensor_fusion.py` (Ambient Context Awareness)
       - m055: `k1/l1_input/streams/operators/speaker_diarization.py` (Multi-Party Conversations)
       - m056: `k1/l1_input/meta_policy/` (Social Norm Modeling, Contextual Privacy, Proactive Confirmations)

     **Related Sub-ADRs:** ADR-0004f (Stream Switch)
     ```

**4. Update ADR Family Map:**

- [ ] **File:** `docs/architecture/tables/adr_family_map.md`
- [ ] **Add 4 new entries:**

     ```
     | Stream Processing | Stream Switch | Multi-Modal Bus | L1 | k1/l1_input/streams/stream_switch/bus.py | Voice→text→image continuity, modality transition, context preservation | ADR-0004f |
     | Stream Processing | Stream Switch | Modality Transition | L1 | k1/l1_input/streams/stream_switch/transition_manager.py | <5ms switch P95, session handoff, device state sync | ADR-0004f |
     | Stream Processing | Ambient Sensors | Sensor Fusion | L1 | k1/l1_input/streams/operators/ambient_sensor_fusion.py | PIR, mmWave, BLE, WiFi, camera person detection | ADR-0004 |
     | Stream Processing | Ambient Sensors | Context Detector | L1 | k1/l1_input/streams/operators/ambient_context_detector.py | Room occupancy, presence detection, privacy-aware responses | ADR-0004 |
     | Stream Processing | Multi-Speaker | Speaker Diarization | L1 | k1/l1_input/streams/operators/speaker_diarization.py | Voice biometrics, spatial audio, face tracking, turn-taking | ADR-0004 |
     | Stream Processing | Multi-Speaker | Speaker Identification | L1 | k1/l1_input/streams/operators/speaker_identifier.py | Family member recognition, speaker enrollment, voice embeddings | ADR-0004 |
     | Meta Policy | Social Norms | Norm Modeler | L1 | k1/l1_input/meta_policy/norm_modeler.py | Family norms, time-based rules, context-specific behaviors | ADR-0004 |
     | Meta Policy | Contextual Privacy | Dynamic Privacy Adjuster | L1 | k1/l1_input/meta_policy/dynamic_privacy_adjuster.py | Band adjustment (GREEN→AMBER→RED), sensor-based rules | ADR-0004 |
     | Meta Policy | Proactive Engagement | Proactive Confirmation | L1 | k1/l1_input/meta_policy/proactive_confirmation.py | Agent-initiated prompts, user acceptance tracking, frequency adaptation | ADR-0004 |
     ```

**5. Update Contract Development Plan:**

- [ ] **File:** `k1/contracts/contract_development_plan.md`
- [ ] **Add new Epic 1.5:** Stream Switch & Multi-Modal Contracts
  - Issue 1.5.1: Stream Switch Multi-Modal Bus Contracts (5 files)
  - Issue 1.5.2: Ambient Sensor Fusion Contracts (8 files)
  - Issue 1.5.3: Speaker Diarization Contracts (10 files)
  - Issue 1.5.4: Meta Policy Engine Contracts (12 files)
  - **Total:** ~35 new contract files

**6. Verify Codebase Mentions:**

- [ ] **Search:** `grep -r "ADR-0004" k1/l1_input/`
- [ ] **Check:** `k1/l1_input/streams/stream_switch/` exists? (NO - create directory structure)
- [ ] **Check:** `k1/l1_input/meta_policy/` exists? (NO - create directory structure)
- [ ] **Action:** Create placeholder directories with `__init__.py` + ADR references

**Acceptance Criteria:**

- [ ] ADR-0004 amended with 4 new modules
- [ ] ADR-0004f sub-ADR created (Stream Switch)
- [ ] ADR family map updated with 9 new entries
- [ ] Contract plan updated with Epic 1.5 (~35 files)
- [ ] Placeholder directories created in codebase

---

### **Issue 1.3: ADR-0054d Sub-ADR - Dialogue Repair & Clarification**

**Capability:** #10 (Dialogue Repair)
**Status:** New sub-ADR required
**Effort:** 1 week
**Priority:** P0 - **MVP CRITICAL**

#### **🎯 What We're Trying to Accomplish**

**Problem:** LLMs are **probabilistic** - they can **misunderstand** user intent (especially with noisy audio, ambiguous phrasing, or multi-turn context). Traditional chatbots fail silently or give generic "I don't understand" responses. FamilyOS needs **intelligent repair strategies**.

**LLM-Specific Challenges:**

- **Confidence Scores:** LLM outputs have confidence (e.g., intent classification: 0.87 confident "book_dinner", 0.42 confident "weather_query"). Need to detect **low confidence** and ask clarifying questions.
- **Hallucination Risk:** When LLM isn't sure, it may **hallucinate** (make up plausible-sounding but wrong answer). Better to **ask for clarification** than guess wrong.
- **Multi-Turn Context Loss:** LLM may mistrack conversation flow ("What about Tuesday?" - Tuesday for what? Dinner or meeting?). Need to **detect confusion** and repair.

**Traditional Chatbot Approach:**

```
User: "Book dinner for tomorrow"
Bot: "I don't understand" [dead end, user frustrated]
```

**FamilyOS LLM-Powered Approach:**

```
User: "Book dinner for tomorrow"
Planner LLM: [Confidence: 0.55 - ambiguous "tomorrow", missing time/location]
Clarification Manager: "I'd be happy to book dinner tomorrow. What time works, and do you have a restaurant in mind?"
User: "7pm at Italian place we went last month"
Planner LLM: [Confidence: 0.92 - searches memory for "Italian restaurant", finds "Luigi's", generates plan]
```

**Repair Strategies:**

1. **Confidence Threshold Triggering:** If intent confidence <0.6 → trigger clarification (not execute wrong action)
2. **Misunderstanding Detection:** Track user corrections ("No, I meant...") → learn misunderstanding patterns
3. **Repair Pattern Templates:**
   - **Rephrase:** "Let me make sure I understand - you want to..."
   - **Simplify:** "Could you break that down? I caught [X] but missed [Y]"
   - **Offer Options:** "Did you mean [Option A] or [Option B]?"
4. **Context Recovery:** When multi-turn context lost, ask "Are we still talking about [last topic]?"

**Success Criteria:** LLM admits uncertainty and asks clarifying questions (not fail silently or hallucinate), recovers from misunderstandings gracefully

**This is MVP because LLM misunderstandings are inevitable - need intelligent recovery, not brittle failure**

#### **6-Point Plan:****1. Create New ADR:** ❌ **NOT NEEDED**

**2. Create Sub-ADR:** ✅ **YES**

- [ ] **ADR-0054d: Dialogue Repair & Clarification Pipeline**
  - **File:** `docs/architecture/decisions/0054d-dialogue-repair-clarification-pipeline.md`
  - **Purpose:** Advanced misunderstanding handling for natural conversations
  - **Content:**
    - **Clarification Request Detection:** Confidence <0.6 → trigger clarification
    - **Repair Strategies:** Rephrase, simplify, offer options
    - **Misunderstanding Detection:** Track user corrections, repeated queries
    - **Repair Pattern Templates:** "Did you mean X or Y?", "I didn't catch that, could you rephrase?"
    - **Integration:** Extend ADR-0054 Turn Boundary Management for repair during active turns
    - **Performance:** <100ms clarification generation P95
    - **Status:** Proposed for MVP

**3. Update Existing ADR:**

- [ ] **ADR-0054: Turn Boundary Management**
- **File:** `docs/architecture/decisions/0054-turn-boundary-management.md`
- **Add Section:** "Extension: Dialogue Repair (ADR-0054d)"
- **Changes:**
  - **Line ~500:** Add reference to ADR-0054d for dialogue repair
  - **Add paragraph:**

       ```markdown
       ## Dialogue Repair Extension (ADR-0054d)

       Turn Boundary Management provides foundation for dialogue repair through dual-signal turn detection.
       See ADR-0054d for full clarification pipeline specification (repair strategies, confidence thresholds, templates).
       ```

**4. Update ADR Family Map:**

- [ ] **File:** `docs/architecture/tables/adr_family_map.md`
- [ ] **Add 3 new entries:**

     ```
     | Dialogue Management | Repair Pipeline | Clarification Manager | L3 | k1/l3_execution/dialogue/clarification_manager.py | Confidence <0.6 detection, repair triggering, <100ms generation | ADR-0054d |
     | Dialogue Management | Repair Pipeline | Repair Strategies | L3 | k1/l3_execution/dialogue/repair_strategies.py | Rephrase, simplify, offer options, pattern templates | ADR-0054d |
     | Dialogue Management | Repair Pipeline | Misunderstanding Detector | L3 | k1/l3_execution/dialogue/misunderstanding_detector.py | User corrections tracking, repeated queries, confidence scoring | ADR-0054d |
     ```

**5. Update Contract Development Plan:**

- [ ] **File:** `k1/contracts/contract_development_plan.md`
- [ ] **Update Epic 2.X:** Add Dialogue Repair contracts
  - Issue 2.X.1: Dialogue Repair Pipeline Contracts (8 files)
    - Clarification detection contract
    - Repair strategy contract
    - Misunderstanding pattern contract
    - Template library contract
    - Confidence threshold contract
    - Turn integration contract
    - Performance budget contract
    - Metrics contract

**6. Verify Codebase Mentions:**

- [ ] **Search:** `grep -r "ADR-0054" k1/l3_execution/dialogue/`
- [ ] **Check:** `k1/l3_execution/dialogue/` exists? (Currently empty per capability analysis)
- [ ] **Action:** Create placeholder directory structure:

     ```
     k1/l3_execution/dialogue/
     ├── __init__.py
     ├── clarification_manager.py
     ├── repair_strategies.py
     └── misunderstanding_detector.py
     ```

**Acceptance Criteria:**

- [ ] ADR-0054d created with full repair pipeline spec
- [ ] ADR-0054 updated with reference to sub-ADR
- [ ] ADR family map updated with 3 entries
- [ ] Contract plan updated with 8 repair contracts
- [ ] Placeholder dialogue/ directory created

---

### **Issue 1.4: ADR-0056e Sub-ADR - Voice Persona Persistence**

**Capability:** #19 (Voice Continuity)
**Status:** New sub-ADR required
**Effort:** 1 week
**Priority:** P0 - **MVP CRITICAL**

#### **🎯 What We're Trying to Accomplish**

**Problem:** LLMs generate **text responses**, TTS converts to **voice**. But prosody (pitch, rate, volume, emotional tone) is typically **randomized per session** or uses default settings. Users expect **consistent voice personality** across conversations.

**LLM + TTS Pipeline:**

```
User: "What's the weather?"
└─> LLM generates text: "It's 72°F and sunny today!"
    └─> TTS synthesizes speech: [pitch=?, rate=?, volume=?, emphasis=?]
        └─> User hears voice (but what tone? cheerful? neutral? formal?)
```

**Current Problem (No Persistence):**

- **Session 1 (Morning):** TTS uses cheerful tone (pitch +5 semitones, rate 1.2x)
- **Session 2 (Evening):** TTS resets to neutral (pitch 0, rate 1.0x) - **jarring inconsistency**
- **User Adjustment Lost:** User says "Speak slower" (rate → 0.8x) → works for current session → next session: reset to 1.0x (frustrating!)

**FamilyOS LLM-Powered Approach:**

```
Session 1:
User: "What's the weather?"
LLM: "It's 72°F and sunny today!"
TTS: [Load prosody from SessionState Section 4: pitch=+3, rate=1.1x, cheerful]
User: "Speak a bit slower"
TTS: [Adjust rate to 0.9x] → Persist to SessionState

Session 2 (Next Day):
User: "Good morning"
LLM: "Good morning! How can I help?"
TTS: [Load prosody from SessionState: pitch=+3, rate=0.9x, cheerful] ← CONSISTENT!
```

**Why This Matters for LLM Architecture:**

1. **Persona = Part of AI Identity:** LLM has "personality" in text (friendly, formal, concise). Voice prosody extends personality to audio. Consistency = trust.
2. **Affect Integration:** LLM detects user emotion (frustrated, happy) via ADR-0069 (AffectModulation). Voice should mirror emotional state across sessions (not reset to neutral).
3. **Per-Family-Member Preferences:** Multi-user system - Dad prefers deeper voice (pitch -5), Mom prefers cheerful (pitch +5). Need to store per-user prosody profiles.
4. **Learning Loop Integration:** LLM learns preferences over time. User repeatedly says "speak slower" → Learning Loop (ADR-0059) should permanently adjust default rate.

**Success Criteria:** Same voice tone/personality across sessions (user doesn't think "Why does the AI sound different today?"), user adjustments persist

**This is MVP because voice inconsistency breaks immersion and trust in LLM-powered assistant**

#### **6-Point Plan:****1. Create New ADR:** ❌ **NOT NEEDED**

**2. Create Sub-ADR:** ✅ **YES**

- [ ] **ADR-0056e: Voice Persona Persistence & Cross-Session Continuity**
  - **File:** `docs/architecture/decisions/0056e-voice-persona-persistence-cross-session.md`
  - **Purpose:** Consistent voice tone across sessions
  - **Content:**
    - **Prosody Parameter Storage:** Store ProsodyControls in SessionState Section 4 (Persona)
    - **Historical Prosody Tracking:** Remember pitch/rate used in past conversations
    - **Emotional State Continuity:** Maintain empathetic tone from last session
    - **Per-Family-Member Preferences:** Dad prefers deeper voice, Mom prefers cheerful tone
    - **Session Start:** Load prosody preferences from SessionState
    - **Session Updates:** Track adjustments (user says "speak slower" → persist rate=0.8)
    - **Learning Loop Integration:** Long-term preference learning via ADR-0059
    - **Performance:** <10ms prosody parameter load P95
    - **Status:** Proposed for MVP

**3. Update Existing ADR:**

- [ ] **ADR-0056: TTS Synthesis Streaming**
- **File:** `docs/architecture/decisions/0056-tts-synthesis-streaming.md` (or 0056d-tts-synthesis.md)
- **Add Amendment:**

     ```markdown
     ## Amendment #1 (2025-10-22): Voice Persona Persistence

     **Extension:** ADR-0056e adds cross-session voice continuity by persisting prosody parameters in SessionState Section 4.

     **Changes:**
     - Prosody parameters (pitch, rate, volume, emphasis) stored in SessionState Section 4 (Persona)
     - Session start: Load historical prosody from SessionState
     - Session updates: Track user adjustments ("speak slower") and persist
     - Per-family-member preferences supported
     - Learning Loop integration for long-term preference evolution

     **Related:** ADR-0017 (SessionState Section 4), ADR-0059 (Learning Loop)
     ```

**4. Update ADR Family Map:**

- [ ] **File:** `docs/architecture/tables/adr_family_map.md`
- [ ] **Add 2 new entries:**

     ```
     | TTS Synthesis | Voice Persona | Persona Persistence | L1 | k1/l1_input/streams/operators/voice_persona_manager.py | SessionState Section 4 integration, <10ms load, prosody tracking | ADR-0056e |
     | TTS Synthesis | Voice Persona | Per-User Preferences | L1 | k1/l1_input/streams/operators/voice_preference_manager.py | Family member voice profiles, pitch/rate/volume/emphasis storage | ADR-0056e |
     ```

**5. Update Contract Development Plan:**

- [ ] **File:** `k1/contracts/contract_development_plan.md`
- [ ] **Update existing Epic (TTS contracts):** Add voice persona contracts
  - Issue X.X.X: Voice Persona Persistence Contracts (6 files)
    - Prosody parameter schema contract
    - SessionState Section 4 integration contract
    - Per-user preference contract
    - Session load/save contract
    - Learning Loop integration contract
    - Metrics contract

**6. Verify Codebase Mentions:**

- [ ] **Search:** `grep -r "ADR-0056" k1/l1_input/streams/operators/`
- [ ] **Check:** TTS pipeline exists? (ADR-0056d mentioned in capability analysis)
- [ ] **Action:** Create voice persona manager placeholder

**Acceptance Criteria:**

- [ ] ADR-0056e created with prosody persistence spec
- [ ] ADR-0056 amended with reference to sub-ADR
- [ ] ADR family map updated with 2 entries
- [ ] Contract plan updated with 6 voice persona contracts
- [ ] Voice persona manager placeholder created

---

### **Issue 1.5: ADR-0017 Amendment #1 - SessionState Extensions**

**Capability:** #19 (Voice), #3 (Ambient), #11 (Multi-Party), #34 (Embodied), #36 (Self-Reference)
**Status:** SessionState needs new fields
**Effort:** 1 week
**Priority:** P0 - **MVP CRITICAL** (#19), P1 - **Post-MVP** (others)

#### **🎯 What We're Trying to Accomplish**

**Problem:** LLMs are **stateless** - each inference is independent. Without explicit state management, LLM "forgets" conversation context between turns. FamilyOS uses **SessionState (ADR-0017)** as the "memory buffer" that makes LLM conversations feel continuous.

**Traditional Chatbot:**

```
User: "What's the weather in Seattle?"
Bot: "75°F and sunny" [stored in session: location=Seattle]
User: "What about tomorrow?"
Bot: "Tomorrow in Seattle: 68°F and rainy" [retrieves location from session]
```

**LLM Without SessionState:**

```
User: "What's the weather in Seattle?"
LLM: "75°F and sunny" [generates response, no memory]
User: "What about tomorrow?"
LLM: "Tomorrow where? I need a location" [doesn't remember Seattle]
```

**LLM With SessionState (Current ADR-0017):**

```
User: "What's the weather in Seattle?"
LLM: "75°F and sunny"
SessionState Section 1 (Beliefs): [location: Seattle, last_query: weather]
User: "What about tomorrow?"
LLM: [Reads SessionState → sees location=Seattle] "Tomorrow in Seattle: 68°F and rainy"
```

**Why We Need NEW Fields (Amendment #1):**

**Current ADR-0017 has 6 sections:**

1. **Beliefs:** What user knows/believes
2. **Scoreboard:** Common ground (shared knowledge)
3. **Control:** Conversation flow state
4. **Persona:** User/agent personality
5. **Multimodal:** Cross-modal context
6. **Meta:** Conversation metadata

**Missing for LLM Intelligence:**

**Section 4 (Persona) - ADD:**

- **voice_prosody:** LLM's voice personality (pitch, rate, volume, emphasis) - **MVP for Issue 1.4**
- **emotional_state:** LLM's last known affect (from ADR-0069) - empathy continuity across sessions
- **self_model:** LLM's understanding of its own capabilities (for self-reference consistency "I can help with X but not Y")
- **family_vocabulary:** Custom terminology learned from family ("cottage" = vacation home, "Nonna" = grandmother)

**Section 5 (Multimodal) - ADD:**

- **ambient_context:** Room occupancy state (3 people present → whisper mode)
- **active_speakers:** Multi-party tracking (Dad speaking vs Mom speaking → different preferences)
- **device_presence:** Cross-device context (phone knows laptop is active → don't duplicate notifications)

**Success Criteria:** LLM maintains consistent personality, remembers environmental context, tracks multiple speakers, adapts voice across sessions

**This is MVP (#19 Voice) + Post-MVP (others) because SessionState is the "working memory" that makes LLM feel intelligent**

#### **6-Point Plan:****1. Create New ADR:** ❌ **NOT NEEDED**

**2. Create Sub-ADR:** ❌ **NOT NEEDED** - Amendment only

**3. Update Existing ADR:** ✅ **YES**

- [ ] **ADR-0017: SessionState 6-Section Design**
- **File:** `docs/architecture/decisions/0017-sessionstate-6-section-design.md` (or ADR-0017b)
- **Add Amendment #1:**

     ```markdown
     ## Amendment #1 (2025-10-22): SessionState Field Extensions

     **Reason:** Support 39 missing UX capabilities requiring new SessionState fields

     **Changes to Section 4 (Persona):**
     - **Voice Continuity (#19 - MVP):**
       - Add `voice_prosody: ProsodyControls` (pitch, rate, volume, emphasis)
       - Add `voice_history: List[ProsodySnapshot]` (historical voice parameters)
       - Add `emotional_state: AffectState` (last known affect from P08)

     - **Self-Reference Consistency (#36 - Post-MVP):**
       - Add `self_model: SelfModelMetadata` (agent's understanding of capabilities)
       - Add `personality_traits: Dict[str, float]` (formal=0.7, proactive=0.5)
       - Add `response_patterns: ResponseStyleHistory` (historical style tracking)
       - Add `consistency_validator: PersonaValidator` (validate self-references)

     - **Cultural Adaptation (#15 - Post-MVP):**
       - Add `family_vocabulary: Dict[str, str]` (custom terminology mappings)
       - Add `family_nicknames: Dict[str, List[str]]` (person → nicknames)

     **Changes to Section 5 (Multimodal):**
     - **Ambient Context (#3 - Post-MVP):**
       - Add `ambient_context: AmbientState` (room occupancy, presence detection)
       - Add `occupancy_history: List[OccupancyEvent]` (historical presence tracking)

     - **Multi-Party Conversations (#11 - Post-MVP):**
       - Add `active_speakers: List[SpeakerState]` (current speakers in conversation)
       - Add `speaker_profiles: Dict[str, SpeakerProfile]` (voice biometrics per family member)

     - **Embodied Awareness (#34 - Post-MVP):**
       - Add `device_presence: DevicePresenceState` (GPS, BLE proximity, screen state)
       - Add `cross_device_context: Dict[str, DeviceState]` (state of all family devices)

     **Size Budget Impact:**
     - Section 4 typical: 4KB → 6KB
     - Section 5 typical: 32KB → 40KB
     - Total SessionState: 64KB → 72KB (still under 128KB hard limit)

     **Related ADRs:** ADR-0056e (Voice Persona), ADR-0050 (Multi-Device Sync), ADR-0069 (Affect Modulation)
     ```

**4. Update ADR Family Map:**

- [ ] **File:** `docs/architecture/tables/adr_family_map.md`
- [ ] **Update existing SessionState entries** with new fields (no new rows needed)

**5. Update Contract Development Plan:**

- [ ] **File:** `k1/contracts/contract_development_plan.md`
- [ ] **Update Epic 4.1.1:** SessionState 6-Section Contracts
  - Add Amendment #1 note
  - Update Section 4 contract (6 new fields)
  - Update Section 5 contract (6 new fields)
  - No new files needed (existing contracts expanded)

**6. Verify Codebase Mentions:**

- [ ] **Search:** `grep -r "ADR-0017" k1/l4_runtime/session_state/`
- [ ] **Check:** SessionState model exists? (Per ADR family map: `k1/l4_runtime/session_state/model.py`)
- [ ] **Action:** Update SessionState model with new fields (placeholder types)

**Acceptance Criteria:**

- [ ] ADR-0017 amended with 12 new fields (6 in Section 4, 6 in Section 5)
- [ ] Size budget analysis included (72KB total)
- [ ] Contract plan updated (existing contracts expanded)
- [ ] SessionState model updated with placeholder field types

---

## 📦 EPIC 2: Post-MVP New ADRs (Weeks 7-12)

**Goal:** Create new ADRs for Post-MVP v1.1 capabilities

**Priority:** 🟡 **MEDIUM** - Not blocking MVP, but required for v1.1

### **🧠 Context: Scaling LLM Intelligence for Family Use**

**EPIC 1 achieved:** Basic LLM functionality (respond to queries, maintain context, degrade gracefully)

**EPIC 2 unlocks:** **Advanced LLM capabilities** that make FamilyOS feel like a **family member**, not just a tool.

**Key LLM Architecture Challenges:**

1. **Knowledge Graph (#21, #38) - CRITICAL GAP:**
   - **Problem:** LLMs have **parametric knowledge** (baked into model weights) but no **episodic knowledge** about YOUR family.
   - **Current:** LLM knows "Seattle is in Washington" (parametric) but NOT "Alice is Mom's sister" (family-specific).
   - **Solution:** K0 Knowledge Graph stores family relationships, nicknames, preferences as **structured data**. LLM queries KG for context: "Who is Alice?" → KG returns "Alice = Mom's sister, lives in Seattle, vegetarian, visits quarterly".
   - **Why Not Just Memory Search?** KG provides **relational queries** ("Who are Dad's siblings?"), **temporal tracking** ("Who was married in 2020?"), **graph traversal** ("How is Bob related to Carol?").

2. **Multi-Party Dialogue (#11, #35):**
   - **Problem:** LLMs see conversation as text stream. Family conversations = **multiple speakers with distinct preferences**.
   - **Current:** LLM can't distinguish "Dad: 'Book steakhouse'" vs "Mom: 'Book vegetarian restaurant'" - all input looks same.
   - **Solution:** Speaker diarization → LLM sees messages tagged with speaker ID → retrieves per-speaker preferences from KG/memory → generates personalized responses.

3. **Meta Policy & Social Norms (#22):**
   - **Problem:** LLMs can generate **contextually inappropriate responses** (suggest loud music during baby naptime, book expensive items without asking).
   - **Current:** No mechanism to **learn family norms** ("Dad always rejects actions after 10pm", "Never book >$100 without asking").
   - **Solution:** Meta Policy Engine observes approval/rejection patterns → builds norm model → constrains LLM behavior via proactive confirmations (HITL).

4. **Ambient Context, Emotion, Memory Consolidation:**
   - **Ambient Sensors (#3):** LLM adapts responses to room state (3 people present → avoid privacy-sensitive topics).
   - **Emotion Awareness (#12, #25, #31, #33):** LLM detects user frustration → adjusts tone empathetically.
   - **Memory Consolidation (#26):** Nightly reflection converts episodic memories → semantic knowledge (10 coffee orders → "User prefers cappuccino in morning").

**This epic transforms LLM from "smart chatbot" to "family intelligence layer".**

---

### **Issue 2.1: ADR-00XX - K0 Knowledge Graph Architecture** 🚨 **CRITICAL GAP**

**Capability:** #21 (Family Identity Graph), #38 (Temporal KG Queries)
**Status:** Missing - **BIGGEST ARCHITECTURAL GAP**
**Effort:** 2 weeks
**Priority:** P1 - **Blocks 2 capabilities**

#### **🎯 What We're Trying to Accomplish**

**Problem:** LLMs need **structured knowledge** about family relationships, not just conversation history. Current K0 Memory (FTS5 + FAISS) stores **unstructured text** ("Alice visited last Tuesday"). Knowledge Graph stores **structured relationships** (Alice --[sister_of]--> Mom, Alice --[lives_in]--> Seattle).

**Why LLMs Need Knowledge Graphs:**

**Scenario 1: Relationship Queries**

```
User: "Remind me who Alice is?"

WITHOUT Knowledge Graph:
LLM → searches K0 memory for "Alice" → finds 50 mentions → summarizes "Alice visited, likes coffee, vegetarian"
Problem: No structured relationship data, must infer from text

WITH Knowledge Graph:
LLM → queries KG: GET_ENTITY("Alice") → returns structured data:
{
  "name": "Alice",
  "relationships": [
    {"type": "sister_of", "target": "Mom", "confidence": 1.0},
    {"type": "lives_in", "target": "Seattle", "since": "2018"},
    {"type": "employed_by", "target": "Microsoft", "from": "2020", "to": "2023"}
  ],
  "attributes": {
    "diet": "vegetarian",
    "visit_frequency": "quarterly"
  }
}
LLM generates: "Alice is Mom's sister. She lives in Seattle and works at Microsoft. She's vegetarian and visits about once per quarter."
```

**Scenario 2: Temporal Queries**

```
User: "Who got married last year?"

WITHOUT Knowledge Graph:
LLM → searches memory for "married" + "2024" → finds partial mentions → may miss some events

WITH Knowledge Graph:
LLM → queries KG: GET_EVENTS(type="marriage", year=2024) → returns:
[
  {"person": "Bob", "spouse": "Carol", "date": "2024-06-15"},
  {"person": "Dave", "spouse": "Eve", "date": "2024-09-20"}
]
LLM generates: "Bob married Carol in June, and Dave married Eve in September."
```

**Scenario 3: Relationship Traversal**

```
User: "How is Bob related to Eve?"

WITHOUT Knowledge Graph:
LLM → searches memory → must infer from conversation text → error-prone

WITH Knowledge Graph:
LLM → queries KG: FIND_PATH("Bob", "Eve") → returns:
Bob --[brother_of]--> Alice --[sister_of]--> Mom --[parent_of]--> User --[married_to]--> Dave --[married_to]--> Eve
LLM generates: "Bob is your uncle (Mom's brother-in-law through Alice), and Eve is your spouse's new wife."
```

**LLM + Knowledge Graph Architecture:**

```
User Query → LLM Planner decides: "Need family context"
           ↓
K1 queries K0 Knowledge Graph: "GET_ENTITY('Alice')"
           ↓
KG returns structured data: {relationships: [...], attributes: {...}}
           ↓
LLM generates response using structured context (not guessing from text)
           ↓
New information extracted from conversation → stored in KG
```

**Success Criteria:** LLM can accurately answer "Who is X?", "How are X and Y related?", "What changed in 2020?", "Who lives in Seattle?" with structured data (not text inference)

**This is CRITICAL GAP because family relationships are core to personalization - LLM needs explicit graph structure, not fuzzy text matching**

#### **6-Point Plan:****1. Create New ADR:** ✅ **YES**

- [ ] **ADR-00XX: K0 Knowledge Graph Architecture**
  - **File:** `docs/architecture/decisions/00XX-k0-knowledge-graph-architecture.md`
  - **Purpose:** Temporal graph for family relationships, events, entity tracking
  - **Content:**
    - **Graph Schema:** Nodes (entities: people, places, events), Edges (relationships with timestamps)
    - **Temporal Edges:** `valid_from`, `valid_to` timestamps for relationship evolution
    - **Entity Types:** Person, Location, Event, Organization, Thing
    - **Relationship Types:** parent, child, sibling, spouse, friend, employed_by, located_at, participated_in
    - **Properties:** Attributes with version history (Alice: single → married in 2020)
    - **Storage:** SQLite graph schema (nodes table, edges table, temporal_edges table)
    - **Query API:** `k0/query/kg_temporal.py` with timeline queries
    - **Integration:** Convert conversations to KG entities (episodic memory → KG)
    - **Algorithms:** Shortest path, temporal reachability, relationship evolution tracking
    - **Visualization:** Export to Mermaid/GraphML for debugging
    - **Performance:** <50ms P95 graph query, <10ms P95 entity lookup
    - **Status:** Proposed for v1.1

**2. Create Sub-ADR:** ✅ **YES** - 4 sub-ADRs

- [ ] **ADR-00XXa: Temporal Graph Schema Design**
- [ ] **ADR-00XXb: Graph Query API & Traversal Algorithms**
- [ ] **ADR-00XXc: Episodic Memory → KG Integration**
- [ ] **ADR-00XXd: KG Visualization & Debugging Tools**

**3. Update Existing ADR:**

- [ ] **ADR-0001: K0/K1 Kernel Split**
- **Add paragraph:** Reference K0 Knowledge Graph as 8th K0 store (was 7)
- **Update line:** "7 memory types" → "8 memory types (episodic, semantic, procedural, snapshots, affect, self-model, social, **knowledge_graph**)"

**4. Update ADR Family Map:**

- [ ] **File:** `docs/architecture/tables/adr_family_map.md`
- [ ] **Add 8 new entries:**

     ```
     | K0 Core | Knowledge Graph | Graph Schema | N/A | k0/drivers/sqlite_kg.py | Nodes, edges, temporal_edges, entity types, relationship types | ADR-00XX |
     | K0 Core | Knowledge Graph | Temporal Edges | N/A | k0/kg/temporal_edges.py | valid_from/valid_to timestamps, relationship evolution, version history | ADR-00XXa |
     | K0 Core | Knowledge Graph | Query API | N/A | k0/query/kg_temporal.py | Timeline queries, entity lookup, relationship traversal, <50ms P95 | ADR-00XXb |
     | K0 Core | Knowledge Graph | Graph Traversal | N/A | k0/kg/traversal.py | Shortest path, temporal reachability, BFS/DFS algorithms | ADR-00XXb |
     | K0 Core | Knowledge Graph | Episodic Integration | N/A | k0/kg/episodic_integration.py | Convert conversations to entities, extract relationships, entity linking | ADR-00XXc |
     | K0 Core | Knowledge Graph | Entity Extractor | N/A | k0/kg/entity_extractor.py | NER (Named Entity Recognition), entity resolution, disambiguation | ADR-00XXc |
     | K0 Core | Knowledge Graph | Visualization | N/A | k0/kg/visualization.py | Mermaid export, GraphML export, debugging UI | ADR-00XXd |
     | K0 Core | Knowledge Graph | KG Metrics | N/A | k0/kg/metrics.py | Node count, edge count, query latency, entity resolution accuracy | ADR-00XX |
     ```

**5. Update Contract Development Plan:**

- [ ] **File:** `k1/contracts/contract_development_plan.md`
- [ ] **Add new Epic 3.X:** K0 Knowledge Graph Contracts
  - Issue 3.X.1: Graph Schema Contracts (10 files)
    - Node schema contract
    - Edge schema contract
    - Temporal edge contract
    - Entity types contract
    - Relationship types contract
    - Property versioning contract
    - SQLite schema contract
    - Migration contract
    - Indexing contract
    - Metrics contract
  - Issue 3.X.2: Query API Contracts (12 files)
    - Timeline query contract
    - Entity lookup contract
    - Relationship traversal contract
    - Shortest path contract
    - Temporal reachability contract
    - Query performance contract
    - Query result schema contract
    - Pagination contract
    - Error handling contract
    - Cache integration contract
    - K0 Bridge integration contract
    - Metrics contract
  - Issue 3.X.3: Episodic Integration Contracts (8 files)
    - Entity extraction contract
    - Relationship extraction contract
    - Entity resolution contract
    - Disambiguation contract
    - Conversation → KG pipeline contract
    - Batch processing contract
    - Error handling contract
    - Metrics contract
  - **Total:** ~30 new contract files

**6. Verify Codebase Mentions:**

- [ ] **Search:** `grep -r "knowledge_graph" k0/`
- [ ] **Check:** `k0/drivers/sqlite_kg.py` exists? **YES - PLACEHOLDER ONLY** (9 lines, NotImplementedError)
- [ ] **Action:** Document placeholder status, create implementation epic (10-12 weeks)

**Acceptance Criteria:**

- [ ] ADR-00XX created with full KG architecture
- [ ] 4 sub-ADRs created (schema, query, integration, visualization)
- [ ] ADR-0001 updated (7→8 memory types)
- [ ] ADR family map updated with 8 entries
- [ ] Contract plan updated with Epic 3.X (~30 files)
- [ ] Implementation epic created (10-12 weeks, blocking #21 and #38)

---

### **Issue 2.2: ADR-00XX - Multi-Party Dialogue Coordination**

**Capability:** #11 (Multi-Party Conversations), #35 (Conflict Resolution - duplicate)
**Status:** Missing ADR
**Effort:** 2 weeks
**Priority:** P2 - **Post-MVP v1.1**

#### **🎯 What We're Trying to Accomplish**

**Problem:** LLMs process **single-user conversations** by default. Family use = **multiple speakers** with **distinct preferences, contexts, and overlapping turns**. FamilyOS needs to track **who said what** and respond appropriately to each person.

**LLM Challenge: Speaker Attribution**

```
WITHOUT Multi-Party Coordination:
Dad: "Book dinner reservation for tonight"
Mom (simultaneously): "What's the weather tomorrow?"
LLM receives: [mixed audio stream] → ASR transcribes: "Book dinner reservation for tonight what's the weather tomorrow"
LLM: [confused] "I heard something about dinner and weather, can you clarify?"

WITH Multi-Party Coordination:
Dad: "Book dinner reservation for tonight" [Speaker ID: Dad, Voice Embedding: 0.92 confidence]
Mom: "What's the weather tomorrow?" [Speaker ID: Mom, Voice Embedding: 0.89 confidence]
LLM receives two separate inputs:
  - Message 1: speaker=Dad, text="Book dinner reservation for tonight"
  - Message 2: speaker=Mom, text="What's the weather tomorrow?"
LLM Orchestrator: [Assigns Agent 1 to Dad's request, Agent 2 to Mom's request]
Response 1 (to Dad): "I'll book dinner at your usual steakhouse for 7pm" [uses Dad's preferences from KG]
Response 2 (to Mom): "Tomorrow will be 68°F and rainy in Seattle" [uses Mom's location from SessionState]
```

**LLM-Powered Multi-Party Architecture:**

**1. Speaker Diarization (Who is speaking?):**

```
Audio Input → Voice Biometrics (ML model) → Speaker Embeddings (768-dim vectors)
           ↓
Compare to enrolled profiles: [Dad: embedding_distance=0.08, Mom: 0.92, Alice: 0.85]
           ↓
Best match: Dad (confidence 0.92)
           ↓
Tag message with speaker_id="Dad"
```

**2. Per-Speaker Context (What does this person prefer?):**

```
LLM receives message tagged with speaker_id="Dad"
           ↓
Query SessionState Section 2 (Scoreboard): GET_SPEAKER_CONTEXT("Dad")
           ↓
Returns: {
  "preferences": {"restaurant": "steakhouse", "meeting_time": "7pm"},
  "recent_queries": ["weather", "calendar"],
  "conversation_style": "concise"
}
           ↓
LLM generates response using Dad's context (not Mom's)
```

**3. Turn-Taking Coordination (When do overlaps happen?):**

```
Turn Manager detects: Dad speaking (confidence 0.92) + Mom speaking (confidence 0.89)
           ↓
Overlapping Speech Detector: [CONFLICT - simultaneous speakers]
           ↓
Strategy: Queue Mom's request, respond to Dad first (first-speaker priority)
OR: Parallel processing (Orchestrator assigns 2 agents, both respond)
```

**4. Conflict Resolution (What if preferences clash?):**

```
Dad: "Book dinner at steakhouse tonight"
Mom (immediately after): "Actually, let's do vegetarian restaurant"
           ↓
LLM Conflict Detector: Opposing requests (steakhouse vs vegetarian) from different speakers
           ↓
Meta Policy: "I heard conflicting preferences - Dad suggested steakhouse, Mom suggested vegetarian. Which would you both prefer?"
           ↓
Users negotiate → LLM proceeds with consensus
```

**Success Criteria:** LLM correctly attributes utterances to speakers, uses per-speaker preferences, handles overlapping turns gracefully, detects conflicting requests

**This is Post-MVP because multi-party coordination requires ML models (speaker embeddings) + complex orchestration logic - defer until single-user experience solid**

#### **6-Point Plan:****1. Create New ADR:** ✅ **YES**

- [ ] **ADR-00XX: Multi-Party Dialogue Coordination**
  - **File:** `docs/architecture/decisions/00XX-multi-party-dialogue-coordination.md`
  - **Purpose:** Multi-speaker tracking and turn-taking coordination
  - **Content:**
    - **Speaker Diarization:** Voice biometrics (speaker embeddings), spatial audio (mic array), face tracking (camera)
    - **Speaker Enrollment:** Family members record voice samples for training
    - **Voice Embedding Extraction:** Pre-trained model (x-vector or ECAPA-TDNN)
    - **Real-time Speaker Matching:** Compare current audio to enrolled embeddings (confidence >0.8)
    - **Turn-Taking Coordination:** Extend ADR-0054 Turn Boundary for multiple speakers
    - **Overlapping Speech Detection:** Detect simultaneous speakers (conflict marker)
    - **Speaker Context Tracking:** Store per-speaker state in SessionState Section 2 (Scoreboard)
    - **Conflict Resolution (Capability #35):** Sentiment divergence detection, mediation strategies
    - **Performance:** <100ms P95 speaker identification, <50ms turn allocation
    - **Status:** Proposed for v1.1

**2. Create Sub-ADR:** ✅ **YES** - 3 sub-ADRs

- [ ] **ADR-00XXa: Speaker Diarization & Voice Biometrics**
- [ ] **ADR-00XXb: Multi-Party Turn-Taking Coordination**
- [ ] **ADR-00XXc: Conflict Resolution Strategies**

**3. Update Existing ADR:**

- [ ] **ADR-0054: Turn Boundary Management**
- **Add section:** "Multi-Party Extension (ADR-00XX)"
- **Note:** Turn Boundary currently single-user, extend for multi-party

**4. Update ADR Family Map:**

- [ ] **Add 6 new entries:**

     ```
     | Multi-Party Dialogue | Speaker Diarization | Speaker Identifier | L1 | k1/l1_input/streams/operators/speaker_identifier.py | Voice biometrics, embeddings, confidence >0.8, <100ms P95 | ADR-00XXa |
     | Multi-Party Dialogue | Speaker Diarization | Speaker Enrollment | L1 | k1/l1_input/streams/operators/speaker_enrollment.py | Voice sample recording, embedding training, profile storage | ADR-00XXa |
     | Multi-Party Dialogue | Turn Coordination | Multi-Party Turn Manager | L3 | k1/l3_execution/dialogue/multi_party_turn_manager.py | Speaker allocation, overlapping detection, <50ms allocation | ADR-00XXb |
     | Multi-Party Dialogue | Turn Coordination | Overlapping Speech Detector | L3 | k1/l3_execution/dialogue/overlapping_detector.py | Simultaneous speaker detection, conflict marker | ADR-00XXb |
     | Multi-Party Dialogue | Conflict Resolution | Sentiment Divergence Detector | L3 | k1/l3_execution/dialogue/sentiment_divergence.py | Opposing emotional states, conflict detection | ADR-00XXc |
     | Multi-Party Dialogue | Conflict Resolution | Mediation Strategies | L3 | k1/l3_execution/dialogue/mediation_strategies.py | De-escalation, facilitation, compromise templates | ADR-00XXc |
     ```

**5. Update Contract Development Plan:**

- [ ] **Add new Epic:** Multi-Party Dialogue Contracts (~25 files)

**6. Verify Codebase Mentions:**

- [ ] **Check:** `k1/l1_input/streams/operators/speaker_diarization.py` exists? **NO**
- [ ] **Action:** Create placeholder (already done in Issue 1.2)

**Acceptance Criteria:**

- [ ] ADR-00XX created with full multi-party spec
- [ ] 3 sub-ADRs created
- [ ] ADR-0054 updated with multi-party extension reference
- [ ] ADR family map updated with 6 entries
- [ ] Contract plan updated with ~25 files

---

### **Issue 2.3: ADR-00XX - Meta Policy & Social Norm Engine**

**Capability:** #22 (Social Norm Understanding)
**Status:** Missing ADR (ADR-0052 HITL exists but not full meta policy)
**Effort:** 1.5 weeks
**Priority:** P2 - **Post-MVP v1.1**

#### **🎯 What We're Trying to Accomplish**

**Problem:** LLMs can generate **contextually inappropriate actions** because they lack **social context**. Traditional AI uses hard-coded rules ("if time > 10pm then reject"). LLM-powered FamilyOS needs **learned social norms** that adapt to family preferences.

**LLM Challenge: Unbounded Action Space**

```
WITHOUT Meta Policy:
User: "Play loud music" [Time: 11pm, Baby sleeping in next room]
LLM Planner: [Generates plan: "Execute tool: smart_speaker.play(volume=80)"]
Orchestrator: [Executes immediately]
Result: 🚨 Baby wakes up, parents frustrated

WITH Meta Policy:
User: "Play loud music" [Time: 11pm]
LLM Planner: [Generates plan: "Execute tool: smart_speaker.play(volume=80)"]
           ↓
Meta Policy Engine: [Checks norms]
  - Norm 1: "No loud activities after 9pm" (learned from 20 rejections)
  - Norm 2: "Baby naptime 8pm-7am" (from calendar + rejections)
  - Context: Time=11pm, Baby_sleeping=true
           ↓
Meta Policy: [HIGH RISK - violates 2 norms] → Triggers proactive confirmation
           ↓
HITL: "I noticed it's 11pm and the baby is sleeping. You usually avoid loud activities now. Still proceed with music at high volume?"
User: "No, nevermind" OR "Yes, use headphones instead"
```

**LLM-Powered Norm Learning (Not Hard-Coded):**

**Traditional Rule-Based Approach:**

```python
# Hard-coded rules (inflexible)
if current_time.hour >= 22:
    reject("No loud activities after 10pm")
if baby_sleeping and volume > 50:
    reject("Baby is sleeping")
```

**Problem:** Requires developer to anticipate every scenario, can't adapt to family-specific norms

**FamilyOS LLM-Powered Approach:**

```
Norm Learning Loop:
1. Observe user behavior:
   - Action: "Play loud music at 11pm" → User response: "No, too late" [REJECT]
   - Action: "Play loud music at 11pm" → User response: "Shh, baby sleeping" [REJECT]
   - Action: "Play loud music at 2pm" → User response: "Sure" [APPROVE]

2. LLM Pattern Recognition (via Learning Loop ADR-0059):
   - Analyze 50 interactions → detect pattern: "Loud activities rejected after 9pm"
   - Generate norm rule: {
       "rule": "quiet_hours",
       "condition": "time >= 21:00 OR baby_sleeping == true",
       "action": "require_confirmation",
       "confidence": 0.87,
       "learned_from": 20 rejections
     }

3. Store norm in K0 Policy Database (via K0 P06 Learning Loop)

4. Meta Policy Engine enforces norm:
   - Future request: "Play loud music at 11pm"
   - Meta Policy queries norms → finds "quiet_hours" rule (confidence 0.87)
   - Triggers HITL proactive confirmation (ADR-0052d)
```

**Types of Learnable Norms:**

- **Time-Based:** "No loud activities after 9pm", "Don't disturb Dad during work hours 9am-5pm"
- **Cost-Based:** "Ask before booking >$100", "Require approval for purchases >$500"
- **Privacy-Based:** "Don't share RED band data when guests present", "Avoid personal topics when 3+ people detected"
- **Contextual:** "Formal tone for work emails", "Casual tone for family chat", "Don't suggest errands during family dinner 6-7pm"

**Success Criteria:** LLM learns family-specific norms from approval/rejection patterns, proactively asks before violating norms, adapts to changing preferences over time

**This is Post-MVP because norm learning requires Learning Loop (ADR-0059) working + sufficient training data (50+ interactions) - defer until basic functionality stable**

#### **6-Point Plan:****1. Create New ADR:** ✅ **YES**

- [ ] **ADR-00XX: Meta Policy & Social Norm Engine**
  - **File:** `docs/architecture/decisions/00XX-meta-policy-social-norm-engine.md`
  - **Purpose:** Family norm modeling and contextual policy enforcement
  - **Content:**
    - **Norm Detection:** Track approval/rejection patterns from user interactions
    - **Time-Based Rules:** Quiet hours, work hours, family time
    - **Context-Specific Behaviors:** Formal tone for work, casual for family
    - **Norm Storage:** K0 Policy database (via K0 P06 Learning Loop advisory)
    - **Norm Enforcement:** ADR-0052d Proactive Risk Confirmation integration
    - **Example Norms:** "Don't disturb Dad after 10pm", "No loud music after 9pm", "Ask before booking >$100"
    - **Performance:** <5ms norm lookup P95, <50ms norm evaluation
    - **Status:** Proposed for v1.1

**2. Create Sub-ADR:** ✅ **YES** - 2 sub-ADRs

- [ ] **ADR-00XXa: Norm Detection & Learning**
- [ ] **ADR-00XXb: Norm Enforcement & Policy Integration**

**3. Update Existing ADR:**

- [ ] **ADR-0052: Enhanced HITL Protocols**
- **Add Extension #5:** Meta Policy Proactive Confirmations
- **Reference:** ADR-00XX for full norm engine spec

**4. Update ADR Family Map:**

- [ ] **Add 4 new entries:**

     ```
     | Meta Policy | Social Norms | Norm Modeler | L1 | k1/l1_input/meta_policy/norm_modeler.py | Pattern detection, rule generation, <5ms lookup | ADR-00XXa |
     | Meta Policy | Social Norms | Norm Learning | L1 | k1/l1_input/meta_policy/norm_learner.py | Approval/rejection tracking, confidence scoring | ADR-00XXa |
     | Meta Policy | Social Norms | Norm Enforcer | L1 | k1/l1_input/meta_policy/norm_enforcer.py | Policy evaluation, proactive confirmation trigger, <50ms | ADR-00XXb |
     | Meta Policy | Social Norms | Norm Storage | L1 | k1/l1_input/meta_policy/norm_storage.py | K0 P06 integration, policy database, norm versioning | ADR-00XXb |
     ```

**5. Update Contract Development Plan:**

- [ ] **Add new Epic:** Meta Policy Contracts (~15 files)

**6. Verify Codebase Mentions:**

- [ ] **Check:** `k1/l1_input/meta_policy/` exists? **NO** (created in Issue 1.2)

**Acceptance Criteria:**

- [ ] ADR-00XX created with norm engine spec
- [ ] 2 sub-ADRs created
- [ ] ADR-0052 updated with Extension #5
- [ ] ADR family map updated with 4 entries
- [ ] Contract plan updated with ~15 files

---

### **Issue 2.4-2.7: Additional New ADRs**

Following same 6-point plan format, create:

- [ ] **Issue 2.4:** ADR-00XX - Ambient Sensor Fusion (Capability #3)
- [ ] **Issue 2.5:** ADR-00XX - Non-Goal Dialogue Management (Capability #23 - Humor & Small Talk)
- [ ] **Issue 2.6:** ADR-00XX - K0 Memory Consolidation Pipeline (Capability #26 - Dream/Reflection)
- [ ] **Issue 2.7:** ADR-00XX - Embodied Awareness & Device Presence (Capability #34)

**Note:** Capability #12 (Emotion-Aware Responses) may NOT need new ADR - enhance ADR-0069 instead.

---

## 📦 EPIC 3: Post-MVP ADR Extensions (Weeks 13-18)

**Goal:** Create sub-ADRs to extend existing ADRs

**Priority:** 🟡 **MEDIUM** - Not blocking MVP

### **🧠 Context: Specialized LLM Intelligence Modules**

**EPIC 1 + 2 achieved:** Core LLM functionality + advanced capabilities (KG, multi-party, meta policy)

**EPIC 3 unlocks:** **Specialized LLM modules** that make FamilyOS feel **predictive, empathetic, and self-aware**.

**Key LLM Architecture Enhancements:**

**1. Learning Loop Specializations (ADR-0059f/g/h):**

- **Base Learning Loop (ADR-0059):** Generic pattern recognition (3-tier feedback signals)
- **Procedural Recall (0059f):** LLM learns **temporal routines** ("Every Monday 7am → coffee order")
- **Proactive Anticipation (0059g):** LLM **predicts future needs** ("Meeting in 30min + traffic heavy → suggest leaving now")
- **Reflection Prompts (0059h):** LLM **generates meta-cognitive questions** ("You asked about Seattle 5 times this week - planning a trip?")

**Why Specialized Modules?**

- **Traditional ML:** One model learns everything (overfits or underfits)
- **LLM + Specialized Modules:** Base LLM handles language understanding, specialized modules handle **pattern detection in specific domains** (temporal patterns, spatial patterns, goal tracking)

**2. Affect Modulation Extensions (ADR-0069a/b):**

- **Base Affect (ADR-0069):** Real-time emotion detection (text sentiment + voice prosody + facial cues)
- **Temporal Mood Tracking (0069a):** LLM tracks **long-term emotional trends** ("User frustrated 3 days in a row → wellness check-in?")
- **Voice Emotion Mirroring (0069b):** LLM **adjusts TTS tone** to match detected emotion (user frustrated → calm empathetic voice)

**Why This Matters:**

- **Traditional Chatbot:** Same tone every time (robotic)
- **LLM + Affect Modulation:** Emotionally adaptive ("I sense you're frustrated, let me help" vs "Great to hear you're excited!")

**3. Smart Home & Third-Party Extensions (ADR-0033 amendments, ADR-0050e):**

- **Tool Execution (ADR-0033):** Generic MCP tool protocol (608 tools)
- **Smart Home (0033 Amendment):** IoT-specific adapters (Home Assistant, HomeKit, Google Home, MQTT)
- **Plugin System (0033 Amendment):** Third-party capability binding (OAuth-like flow, least privilege)
- **Device Presence (0050e):** Cross-device context (phone knows laptop active → coordinate notifications)

**Why Extensions?**

- **Base ADR:** General architecture (protocol layer, sandbox layer)
- **Extensions:** Domain-specific implementations (IoT protocols, plugin security model, device coordination)

**This epic makes LLM intelligence feel human-like: predictive, empathetic, contextually aware across devices.**

---

### **Issue 3.1-3.10: Sub-ADR Creation**

Create 10 sub-ADRs following same 6-point plan:

- [ ] **Issue 3.1:** ADR-0059f - Procedural Recall & Temporal Patterns (Capability #27)
- [ ] **Issue 3.2:** ADR-0059g - Proactive Anticipation Engine (Capability #30)
- [ ] **Issue 3.3:** ADR-0059h - User Reflection Prompt Generation (Capability #39)
- [ ] **Issue 3.4:** ADR-0069a - Temporal Mood Tracking (Capability #31)
- [ ] **Issue 3.5:** ADR-0069b - Voice Emotion Mirroring (Capability #33 - duplicate of #25)
- [ ] **Issue 3.6:** ADR-0033 Amendment #1 - Smart Home IoT + Plugin System (Capabilities #16, #17)
- [ ] **Issue 3.7:** ADR-0050e - Device Presence Sensing (Capability #34)
- [ ] **Issue 3.8:** ADR-0052 Amendment #1 - Add Extension #5 (Meta Policy Proactive Confirmations)
- [ ] **Issue 3.9:** ADR-0054 Amendment #1 - Multi-Party Support (Capability #11)
- [ ] **Issue 3.10:** ADR-0059 Amendment #1 - Specialized Learning Modules

---

## 📊 Summary Tables

### **ADR Work Breakdown**

| **Type**                      | **Count**                | **Effort** | **Priority**     | **Phase**                |
| ----------------------------- | ------------------------ | ---------- | ---------------- | ------------------------ |
| **Verify Implementation**     | 1 (Graceful Degradation) | 1 week     | P0 - MVP         | Phase 1                  |
| **ADR Amendments**            | 4                        | 5 weeks    | P0 - MVP         | Phase 1                  |
| **Sub-ADRs (MVP)**            | 2                        | 2 weeks    | P0 - MVP         | Phase 1                  |
| **New ADRs**                  | 7-8                      | 12 weeks   | P1-P2 - Post-MVP | Phase 2                  |
| **Sub-ADRs (Post-MVP)**       | 8                        | 10 weeks   | P2 - Post-MVP    | Phase 3                  |
| **ADR Amendments (Post-MVP)** | 4                        | 4 weeks    | P2 - Post-MVP    | Phase 3                  |
| **TOTAL**                     | 26-27                    | 34 weeks   |                  | 18-24 weeks parallelized |

### **Contract Work Breakdown**

| **Type**                           | **Count** | **Effort** | **Phase**       |
| ---------------------------------- | --------- | ---------- | --------------- |
| **New Contracts (New ADRs)**       | ~150      | 8 weeks    | Phase 2-3       |
| **Updated Contracts (Amendments)** | ~80       | 4 weeks    | Phase 1-3       |
| **Existing Contracts**             | 741       | -          | Already planned |
| **TOTAL**                          | ~970      | 12 weeks   | -               |

### **Capability Implementation Dependencies**

| **Capability**             | **Requires ADR**       | **Requires Implementation** | **Timeline** |
| -------------------------- | ---------------------- | --------------------------- | ------------ |
| #29 (Graceful Degradation) | ✅ Exists (3 ADRs)      | ⚠️ Verify exists             | 0-8 weeks    |
| #1 (Cross-Modal)           | ✅ Sub-ADR 0004f        | Needs impl                  | 2-3 weeks    |
| #2 (Barge-in)              | ✅ Exists ADR-0057c     | Needs impl                  | 1-2 weeks    |
| #4 (Service Handoffs)      | ✅ Exists ADR-0033      | Needs impl                  | 3-4 weeks    |
| #6 (Cross-Tool Workflow)   | ✅ Exists ADR-0006/0007 | Needs impl                  | 5-6 weeks    |
| #7 (Memory Utilization)    | ✅ Exists ADR-0001      | K0 done, K1 needs           | 2-3 weeks    |
| #10 (Dialogue Repair)      | ⏳ Sub-ADR 0054d        | Needs impl                  | 3-4 weeks    |
| #14 (Cross-Device Flow)    | ✅ Exists ADR-0050      | In progress (M2-M3)         | 4-5 weeks    |
| #19 (Voice Continuity)     | ⏳ Sub-ADR 0056e        | Needs impl                  | 3-4 weeks    |

---

## 🎯 Critical Path Analysis

**MVP Critical Path (18-24 weeks parallelized):**

```
Week 1-2:  Verify Graceful Degradation (#29) [HIGHEST PRIORITY]
           └─ If missing: Add 6-8 weeks to timeline

Week 2-4:  ADR-0004 Amendment #2 (4 new modules)
           ADR-0054d Sub-ADR (Dialogue Repair)
           [Parallel]

Week 4-6:  ADR-0056e Sub-ADR (Voice Persona)
           ADR-0017 Amendment #1 (SessionState)
           [Parallel]

Week 7-12: Implement MVP capabilities
           └─ Planner (5-6 weeks) [Blocks #7, #30, #39]
           └─ Tool Execution (3-4 weeks) [Blocks #4, #16, #17]
           └─ Dialogue Management (3-4 weeks) [Blocks #2, #10, #23]
           [Can parallelize if separate teams]

Week 13-18: Post-MVP ADR work
            └─ Knowledge Graph ADR [BIGGEST GAP]
            └─ Multi-Party Dialogue ADR
            └─ Meta Policy ADR
            [Can parallelize]

Week 19-24: Post-MVP implementation
            └─ Based on new ADRs from Week 13-18
```

**Blocking Dependencies:**

1. **Graceful Degradation (#29)** - If not implemented, adds 6-8 weeks to timeline
2. **Planner (#6)** - Blocks Memory Utilization (#7), Anticipation (#30), Reflection (#39)
3. **Tool Execution (#4)** - Blocks Service Handoffs, Smart Home (#16), Third-Party Trust (#17)
4. **Knowledge Graph** - Blocks Family Identity Graph (#21), Temporal KG Queries (#38)

---

## 📋 Issue Template

For each issue, use this format:

```markdown
## Issue X.X: [Title]

**Capability:** #N ([Capability Name])
**Status:** [New ADR / Sub-ADR / Amendment]
**Effort:** [X weeks]
**Priority:** [P0-MVP / P1 / P2]

### 6-Point Plan:

**1. Create New ADR:**
- [ ] [ADR number and title]
- [ ] [File path]
- [ ] [Purpose statement]

**2. Create Sub-ADR:**
- [ ] [Sub-ADR number and title]
- [ ] [Content outline]

**3. Update Existing ADR:**
- [ ] [ADR to update]
- [ ] [Specific changes]
- [ ] [Line numbers to modify]

**4. Update ADR Family Map:**
- [ ] Add [N] new entries
- [ ] [Table entries]

**5. Update Contract Development Plan:**
- [ ] Add Epic/Issue
- [ ] [Number] new contract files
- [ ] [Contract file list]

**6. Verify Codebase Mentions:**
- [ ] Search for [pattern]
- [ ] Check [directory] exists
- [ ] Create [placeholders]

**Acceptance Criteria:**
- [ ] [Criterion 1]
- [ ] [Criterion 2]
- [ ] [Criterion 3]
```

---

## 🔍 Next Steps

1. **Week 1:** Execute Issue 1.1 (Verify Graceful Degradation) - **IMMEDIATE**
2. **Week 2-6:** Execute Issues 1.2-1.5 (MVP ADR work)
3. **Week 7-12:** Create new ADRs for Post-MVP capabilities
4. **Week 13-18:** Create sub-ADRs and amendments
5. **Week 19-24:** Generate contracts and begin implementation

**Responsibility:** Architecture Team owns ADR creation, Contract Team owns contract generation, Engineering Teams own implementation

**Review Cadence:** Weekly ADR review sessions, bi-weekly contract reviews

**Success Metrics:**

- All 26-27 ADR work items completed
- ~970 contract files generated
- 9 MVP capabilities fully architected (already done!)
- 33 unique capabilities architected (39 minus 6 duplicates)

---

**END OF PLAN**
