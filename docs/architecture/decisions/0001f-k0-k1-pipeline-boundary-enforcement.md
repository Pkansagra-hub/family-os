# ADR-0001f: K0/K1 Pipeline Boundary Enforcement — No Pipelines in K1

**Status:** 🚨 **CRITICAL - MANDATORY ENFORCEMENT** (2025-10-14)
**Date:** 2025-10-14
**Last Updated:** 2025-10-14
**Deciders:** K1 Architecture Team, K0 Memory Team
**Technical Story:** Hard-code K0/K1 architectural boundary to prevent pipeline violations
**Parent ADR:** [ADR-0001: K0/K1 Kernel Split](0001-k0-k1-kernel-split.md)
**Related ADRs:**
- [ADR-0001: K0/K1 Kernel Split](0001-k0-k1-kernel-split.md)
- [ADR-0001a: K0 Bridge Communication Protocol](0001a-k0-bridge-communication-protocol.md)
- [ADR-0059: Learning Loop (K1 Advisory-Only, K0 Persistence)](../../ADR_CREATION_PLAN_2025-10-14.md) - Planned Tier-1 ADR
- [ADR-0064: Self-Model & Consent (K0 P14 Implementation)](../../ADR_CREATION_PLAN_2025-10-14.md) - Planned Tier-2 ADR
- [ADR-0069: P08 AffectModulation (K0 Implementation)](../../ADR_CREATION_PLAN_2025-10-14.md) - Planned Tier-3 ADR

---

## 🚨 CRITICAL WARNING 🚨

**THIS ADR IS MANDATORY FOR ALL CODE REVIEWERS AND CONTRIBUTORS**

**ZERO TOLERANCE POLICY:**
- ❌ **NO pipelines (P01-P20) may be implemented in K1** - EVER
- ❌ **NO cognitive state may be stored in K1** - ALL state in K0
- ❌ **NO direct memory writes from K1** - ALL writes via K0 Command API
- ✅ **K1 MAY use stateless detectors** - but NO durable state, NO receipts

**ANY PR VIOLATING THIS BOUNDARY WILL BE REJECTED WITHOUT REVIEW**

---

## Executive Summary

This ADR establishes **hard-coded, immutable architectural boundaries** between K0 (Memory Microkernel) and K1 (Agentic Orchestrator) to prevent architectural violations, scope creep, and boundary erosion.

**The Hard Boundary (Authoritative):**

**K0 (Memory Microkernel):**
- Owns **ALL cognitive pipelines P01-P20** (deterministic, no external calls)
- Examples: P01 RecallQuery, P02 MemoryWrite, P03 AttentionGate, P04 Hippocampus, P05 ProspectiveTriggers, **P06 FeedbackIntegration**, P07 Sync/CRDT, **P08 AffectModulation**, P10 PII/ABAC, **P14 SelfModelUpdate**, P13 Emotional Intelligence, P18 PersonalizationSync, P20 ProactiveReminders
- K0 is the **ONLY** place where cognitive states are updated and receipts are issued
- K0 exposes: Query API (read), Command API (write), SSE API (event subscriptions)

**K1 (Agentic Orchestrator):**
- **NO PIPELINES** - Plans, orchestrates agents, chooses tools, calls K0 ports
- **NEVER mutates memory directly** - all writes via K0 Command API
- **NEVER hosts cognitive pipelines** - no P01-P20 implementations
- MAY use **stateless detectors** (affect sensing, ASR VAD, intent classification) to shape immediate reply only - **NO durable state, NO receipts**

**Critical Question Answered:**

**Q: "Do we require an affect module in K1?"**
**A: NO.**

Authoritative affect state (valence/arousal, salience) is owned by **K0 P08 AffectModulation**. K1 may have an optional **stateless "Affect Sensing Tool"** (no state, no receipts) to read local cues (prosody, word choice) and suggest tone for immediate reply generation. Any durable affect update goes through **K0→P08** via Command API.

---

## Context

### The Boundary Erosion Problem

**Historical Context:**
The K0/K1 split architecture ([ADR-0001](0001-k0-k1-kernel-split.md)) was designed with clear separation:
- **K0:** Durable memory, cognitive pipelines, state management
- **K1:** Ephemeral orchestration, agent coordination, tool execution

**Problem:** Without explicit boundary enforcement, architectural drift occurs:

1. **Temptation to add "simple" pipelines in K1:**
   - "Just a small affect detector, no big deal..."
   - "Let's cache self-model style vector in K1 for performance..."
   - "K1 can store learning feedback locally and batch-flush later..."

2. **Incremental Scope Creep:**
   - Week 1: Add stateless affect detector in K1 ✅ (acceptable)
   - Week 2: Add local affect caching "for performance" ⚠️ (slippery slope)
   - Week 3: Add affect persistence in K1 SessionState ❌ (boundary violation)
   - Week 4: K1 now has mini-pipeline, duplicates K0 P08 ❌❌ (architectural disaster)

3. **Cross-Team Confusion:**
   - K1 team: "We thought affect was K1 responsibility since we generate empathy responses"
   - K0 team: "No, P08 AffectModulation is K0 pipeline, K1 just reads it"
   - Result: Duplicate implementations, state inconsistency, merge conflicts

4. **Code Review Ambiguity:**
   - Reviewer: "Is this K1 affect tool violating boundary?"
   - Author: "No, it's just a stateless detector, see ADR-0069"
   - Reviewer: "But ADR-0069 says K0 P08... which is authoritative?"
   - Result: PR approved incorrectly, boundary eroded

**Solution:** This ADR hard-codes the boundary with:
- Explicit "What K0 Does" / "What K1 Does" lists
- Concrete examples of violations vs allowed patterns
- Enforcement mechanisms (CI/CD, code review checklist)
- Mandatory reference in all memory/pipeline PRs

---

## Decision

We establish **hard-coded, immutable architectural boundaries** between K0 and K1.

### 1. What K0 Does (Memory Microkernel)

**K0 Owns ALL Cognitive Pipelines P01-P20:**

| Pipeline | Purpose | State Ownership | Example |
|----------|---------|----------------|---------|
| **P01 RecallQuery** | Multi-store memory retrieval | K0 Episodic/Semantic/KG | FTS + Vector + KG fusion |
| **P02 MemoryWrite** | Durable memory persistence | K0 WAL + SQLite | SessionState delta batching |
| **P03 AttentionGate** | Working memory salience | K0 Cache tier (RAM) | Boost recent memories |
| **P04 Hippocampus** | Episodic consolidation | K0 Episodic store | DG→CA3→CA1 encoding |
| **P05 ProspectiveTriggers** | Future reminders | K0 Procedural store | "Remind me Wednesday 4pm" |
| **P06 FeedbackIntegration** | Learning persistence | K0 WAL + preferences | Advisory feedback → durable state |
| **P07 Sync/CRDT** | State synchronization | K0 WAL + CRDT | Cross-device session resume |
| **P08 AffectModulation** | Emotion detection + empathy | K0 SessionState Scoreboard | Valence/arousal state |
| **P10 PII/ABAC** | Privacy + access control | K0 Encrypted vault | PII redaction, consent enforcement |
| **P13 Emotional Intelligence** | Multi-modal affect analysis | K0 P08 (same as above) | Text + prosody + facial cues |
| **P14 SelfModelUpdate** | Persona + style management | K0 SessionState Persona | Style vector, exemplars, consent |
| **P18 PersonalizationSync** | User trait loading | K0 Self-Model store | Formality, verbosity, emoji_use |
| **P20 ProactiveReminders** | Proactive suggestions | K0 P05 (same as above) | Quiet hours, trigger policy |

**K0 Responsibilities:**
- ✅ All pipeline P01-P20 implementations (deterministic, no external LLM calls)
- ✅ Cognitive state updates (affect, self-model, episodic memories)
- ✅ Receipt issuance for all writes (audit trail)
- ✅ WAL persistence (ACID guarantees)
- ✅ Multi-store retrieval (FTS, Vector, KG, Episodic)
- ✅ Privacy enforcement (PII redaction, ABAC, consent)

**K0 APIs Exposed to K1:**
- **Query API (P01-P10 read operations):** RecallQuery, AttentionGate, PersonalizationSync
- **Command API (P02-P20 write operations):** MemoryWrite, FeedbackIntegration, SelfModelUpdate, ProspectiveTriggers
- **SSE API (event subscriptions):** Memory updates, affect changes, proactive reminders

---

### 2. What K1 Does (Agentic Orchestrator)

**K1 Has ZERO Pipelines:**

**K1 Responsibilities:**
- ✅ Agent orchestration (3-phase: Negotiation → Selection → Execution)
- ✅ Planning (4-stage: Sketch → Expand → Validate → Commit)
- ✅ Tool execution (MCP protocol, sandboxing)
- ✅ Turn-taking (HITL, barge-in, clarification)
- ✅ Voice pipeline (ASR→Intent→Tools→TTS→Audio)
- ✅ Backpressure cascade (watermarks, degradation)
- ✅ K0 port calls (Query/Command/SSE APIs)

**K1 NEVER:**
- ❌ Hosts cognitive pipelines (no P01-P20 implementations)
- ❌ Mutates memory directly (no WAL writes, no SQLite updates)
- ❌ Stores durable cognitive state (no affect, no self-model, no episodic memories)
- ❌ Issues receipts (only K0 issues receipts)
- ❌ Implements learning with state (no feedback persistence)

**K1 MAY (Stateless Detectors Only):**
- ✅ Use **stateless "Affect Sensing Tool"** for local cues:
  - Input: Prosody (pitch, energy), word choice (frustrated language)
  - Output: Suggested tone for immediate reply ("use empathetic tone")
  - **NO STATE:** Tool does NOT store affect, does NOT issue receipts
  - **NO WRITES:** Tool CANNOT update K0 affect state
  - **Use case:** Real-time tone control during K1 LLM generation
  - **Persistence:** Any affect needing storage goes through **K0 P08 Command API**

- ✅ Use **stateless ASR VAD** for voice activity detection:
  - Input: Audio frames (20ms chunks)
  - Output: Voice/silence classification for turn boundaries
  - **NO STATE:** VAD does NOT store audio history, no durable buffers
  - **Use case:** Real-time turn boundary detection for voice pipeline

- ✅ Use **stateless Intent Classifier** for user intent:
  - Input: Text (user message)
  - Output: Intent category (question, command, clarification)
  - **NO STATE:** Classifier does NOT learn, does NOT update
  - **Use case:** Fast intent routing for orchestrator

---

### 3. Examples of Allowed K1 Patterns (Stateless Detectors)

#### Example 1: Stateless Affect Sensing Tool (✅ Allowed)

```python
# K1 Tool: Stateless Affect Sensing
class AffectSensingTool:
    """
    Stateless affect detector for immediate reply shaping.
    NO STATE, NO RECEIPTS, NO WRITES to K0.
    """
    def detect_local_cues(self, text: str, prosody: AudioFeatures) -> ToneSuggestion:
        # Analyze prosody (pitch, energy) for frustration cues
        frustration_score = self._analyze_prosody(prosody)

        # Analyze text for frustrated language ("this sucks", "why doesn't this work")
        text_frustration = self._analyze_text(text)

        # Combine scores
        total_frustration = (frustration_score + text_frustration) / 2

        if total_frustration > 0.7:
            return ToneSuggestion(tone="empathetic", reason="user_frustrated")
        elif total_frustration > 0.4:
            return ToneSuggestion(tone="supportive", reason="user_mildly_frustrated")
        else:
            return ToneSuggestion(tone="neutral", reason="user_calm")

    def _analyze_prosody(self, prosody: AudioFeatures) -> float:
        # NO STATE: Just compute score from audio features
        return (prosody.pitch_variance + prosody.energy_variance) / 2

    def _analyze_text(self, text: str) -> float:
        # NO STATE: Just keyword matching for frustrated language
        frustrated_keywords = ["sucks", "doesn't work", "broken", "frustrated"]
        return sum(1 for kw in frustrated_keywords if kw in text.lower()) / len(frustrated_keywords)

# K1 Usage in LLM Generation:
tone_suggestion = affect_sensing_tool.detect_local_cues(user_message, audio_prosody)
prompt = f"Respond with {tone_suggestion.tone} tone. User message: {user_message}"
response = llm.generate(prompt)

# NO WRITES: Affect sensing tool does NOT update K0 P08
# IF K1 wants to persist affect state, it MUST call K0 P08:
k0_bridge.command(
    command_type="affect_update",
    port="P08",
    payload={"valence": -0.5, "arousal": 0.7, "reason": "user_frustrated"}
)
```

**Why This Is Allowed:**
- ✅ No durable state (affect sensing tool is stateless)
- ✅ No receipts (no K0 writes)
- ✅ No persistence (affect state NOT stored in K1)
- ✅ Immediate reply shaping only (used for LLM prompt tuning)
- ✅ K0 P08 called separately for durable affect updates

---

#### Example 2: Stateless ASR VAD (✅ Allowed)

```python
# K1 Tool: Stateless Voice Activity Detection
class ASRVAD:
    """
    Stateless VAD for voice activity detection.
    NO STATE, NO AUDIO HISTORY, NO DURABLE BUFFERS.
    """
    def detect_voice_activity(self, audio_frame: bytes) -> VoiceActivity:
        # Compute energy for this frame only (no history)
        energy = self._compute_energy(audio_frame)

        # Threshold-based voice/silence classification
        if energy > 0.02:  # Voice threshold
            return VoiceActivity(is_voice=True, confidence=0.9)
        else:
            return VoiceActivity(is_voice=False, confidence=0.8)

    def _compute_energy(self, audio_frame: bytes) -> float:
        # NO STATE: Just compute RMS energy for this frame
        samples = np.frombuffer(audio_frame, dtype=np.int16)
        return np.sqrt(np.mean(samples**2)) / 32768.0

# K1 Usage in Voice Pipeline:
for audio_frame in audio_stream:
    voice_activity = vad.detect_voice_activity(audio_frame)
    if voice_activity.is_voice:
        # Continue processing voice input
        pass
    else:
        # Detect turn boundary (silence for 2s)
        pass

# NO WRITES: VAD does NOT store audio history in K1 or K0
```

**Why This Is Allowed:**
- ✅ No durable state (VAD is stateless frame-by-frame)
- ✅ No audio history stored (no buffers in K1)
- ✅ Immediate turn boundary detection only
- ✅ No K0 writes (VAD does not persist audio)

---

### 4. Examples of FORBIDDEN K1 Patterns (Violations)

#### Violation 1: K1 Storing Affect State (❌ FORBIDDEN)

```python
# ❌ FORBIDDEN: K1 caching affect state
class K1SessionState:
    def __init__(self):
        self.affect_cache = {  # ❌ VIOLATION: Durable affect state in K1
            "valence": 0.5,
            "arousal": 0.3,
            "last_updated": "2025-10-14T10:00:00Z"
        }

    def update_affect(self, valence: float, arousal: float):
        # ❌ VIOLATION: K1 updating affect directly
        self.affect_cache["valence"] = valence
        self.affect_cache["arousal"] = arousal
        self.affect_cache["last_updated"] = datetime.now().isoformat()

        # ❌ VIOLATION: K1 NOT calling K0 P08
        # This is durable state in K1 without K0 persistence!

# Why This Is FORBIDDEN:
# - Affect state is durable (cached in K1 SessionState)
# - K1 is NOT calling K0 P08 for authoritative persistence
# - If K1 crashes, affect state is lost
# - K0 P08 and K1 affect_cache can diverge (inconsistency)
```

**Correct Pattern:**
```python
# ✅ CORRECT: K1 reads affect from K0, does NOT cache
class K1SessionState:
    def get_affect(self) -> Affect:
        # ✅ CORRECT: Always read from K0 P08
        response = k0_bridge.query(
            query_type="affect_state",
            port="P08"
        )
        return Affect(
            valence=response["valence"],
            arousal=response["arousal"]
        )

    def update_affect(self, valence: float, arousal: float):
        # ✅ CORRECT: K1 calls K0 P08 Command API
        k0_bridge.command(
            command_type="affect_update",
            port="P08",
            payload={"valence": valence, "arousal": arousal}
        )
        # K0 P08 issues receipt, K1 does NOT store affect
```

---

#### Violation 2: K1 Implementing Learning Loop with State (❌ FORBIDDEN)

```python
# ❌ FORBIDDEN: K1 learning loop with state
class K1LearningLoop:
    def __init__(self):
        self.feedback_history = []  # ❌ VIOLATION: Durable feedback in K1
        self.learned_preferences = {}  # ❌ VIOLATION: Durable preferences in K1

    def add_feedback(self, feedback: Feedback):
        # ❌ VIOLATION: K1 storing feedback locally
        self.feedback_history.append(feedback)

        # ❌ VIOLATION: K1 updating learned preferences
        self.learned_preferences[feedback.key] = feedback.value

        # ❌ VIOLATION: K1 NOT calling K0 P06 for persistence

# Why This Is FORBIDDEN:
# - Learning feedback is durable state (stored in K1)
# - K1 is NOT calling K0 P06 FeedbackIntegration
# - If K1 crashes, all feedback history is lost
# - K0 P06 and K1 learned_preferences can diverge
```

**Correct Pattern (ADR-0059):**
```python
# ✅ CORRECT: K1 advisory-only, K0 P06 persists
class K1LearningLoop:
    def add_feedback(self, feedback: Feedback):
        # ✅ CORRECT: K1 emits advisory signal to K0 P06
        k0_bridge.command(
            command_type="feedback_integration",
            port="P06",
            payload={
                "feedback_type": feedback.type,  # explicit/implicit/behavioral
                "key": feedback.key,
                "value": feedback.value,
                "weight": feedback.weight  # 1.0/0.5/0.2
            }
        )
        # K0 P06 validates, persists, issues receipt
        # K1 does NOT store feedback history or learned preferences
```

---

#### Violation 3: K1 Caching Self-Model Style Vector (❌ FORBIDDEN)

```python
# ❌ FORBIDDEN: K1 caching self-model
class K1SessionState:
    def __init__(self):
        self.style_vector_cache = {  # ❌ VIOLATION: Durable self-model in K1
            "formality": 0.3,
            "directness": 0.8,
            "emoji_use": True
        }

    def get_style_vector(self) -> StyleVector:
        # ❌ VIOLATION: K1 returning cached style vector
        return StyleVector(**self.style_vector_cache)

    def update_style_vector(self, updates: Dict):
        # ❌ VIOLATION: K1 updating cache directly
        self.style_vector_cache.update(updates)

        # ❌ VIOLATION: K1 NOT calling K0 P14

# Why This Is FORBIDDEN:
# - Self-model is durable state (cached in K1)
# - K1 is NOT calling K0 P14 SelfModelUpdate for authoritative state
# - K0 P14 and K1 cache can diverge
# - Consent checks bypassed (K0 P10 ABAC not consulted)
```

**Correct Pattern (ADR-0064):**
```python
# ✅ CORRECT: K1 reads self-model from K0, does NOT cache
class K1SessionState:
    def get_style_vector(self) -> StyleVector:
        # ✅ CORRECT: Always read from K0 P14
        response = k0_bridge.query(
            query_type="self_model_read",
            port="P14",
            payload={"user_id": self.user_id}
        )
        # K0 P10 ABAC enforces consent before returning style vector
        return StyleVector(**response["style_vector"])

    def update_style_vector(self, updates: Dict):
        # ✅ CORRECT: K1 calls K0 P14 Command API
        k0_bridge.command(
            command_type="self_model_update",
            port="P14",
            payload={
                "user_id": self.user_id,
                "updates": updates
            }
        )
        # K0 P14 validates, persists, issues receipt
        # K1 does NOT cache style vector
```

---

## 5. Enforcement Mechanisms

### 5.1 Code Review Checklist (Mandatory)

**Every PR touching memory/pipelines MUST include:**

```markdown
## K0/K1 Boundary Compliance Checklist

**MANDATORY - PR WILL BE REJECTED IF NOT COMPLETED**

- [ ] **Read ADR-0001f:** I have read and understood the K0/K1 pipeline boundary rules
- [ ] **No Pipelines in K1:** This PR does NOT implement any P01-P20 pipelines in K1
- [ ] **No Durable State in K1:** This PR does NOT store cognitive state (affect, self-model, feedback) in K1
- [ ] **K0 Command API Used:** All memory writes use K0 Command API (P02, P06, P08, P14, etc.)
- [ ] **Stateless Detectors Only:** If K1 tools added, they are stateless (no state, no receipts)
- [ ] **Architect Approval:** If touching K0/K1 boundary, architect has approved design

**Violations Found:**
- [ ] None (✅ Compliant)
- [ ] Minor (⚠️ Needs refactor before merge)
- [ ] Major (❌ PR must be rejected)

**Architect Sign-Off (if required):**
- Architect Name: __________________
- Date: __________________
- Approval: ✅ Approved / ❌ Rejected
```

**Reviewer Responsibilities:**
1. Verify checklist is completed by PR author
2. Scan code for forbidden patterns:
   - K1 storing affect/self-model/feedback in SessionState
   - K1 implementing pipelines (P01-P20 logic)
   - K1 mutating memory directly (no K0 Command API)
3. If violation found: Request architect review + refactor
4. If compliant: Approve PR

---

### 5.2 CI/CD Automated Checks

**GitHub Actions Workflow (`.github/workflows/k0-k1-boundary-check.yml`):**

```yaml
name: K0/K1 Boundary Enforcement

on: [pull_request]

jobs:
  boundary-check:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3

      - name: Check for K1 Pipeline Violations
        run: |
          # Forbidden patterns in K1 code
          VIOLATIONS=""

          # Check 1: K1 implementing P01-P20 pipelines
          if grep -r "class P0[0-9].*Pipeline" k1/; then
            VIOLATIONS="$VIOLATIONS\n❌ K1 implements P01-P20 pipeline (FORBIDDEN)"
          fi

          # Check 2: K1 storing affect state
          if grep -r "affect_cache\|affect_state\|self.affect" k1/session_state.py; then
            VIOLATIONS="$VIOLATIONS\n❌ K1 caching affect state (FORBIDDEN)"
          fi

          # Check 3: K1 storing self-model
          if grep -r "style_vector_cache\|self.style_vector" k1/session_state.py; then
            VIOLATIONS="$VIOLATIONS\n❌ K1 caching self-model (FORBIDDEN)"
          fi

          # Check 4: K1 storing feedback history
          if grep -r "feedback_history\|learned_preferences" k1/learning/; then
            VIOLATIONS="$VIOLATIONS\n❌ K1 storing learning state (FORBIDDEN)"
          fi

          # Check 5: K1 direct SQLite writes (must use K0 Bridge)
          if grep -r "sqlite3.connect\|cursor.execute.*INSERT" k1/; then
            VIOLATIONS="$VIOLATIONS\n❌ K1 writing to SQLite directly (FORBIDDEN)"
          fi

          # Report violations
          if [ -n "$VIOLATIONS" ]; then
            echo -e "\n🚨 K0/K1 BOUNDARY VIOLATIONS DETECTED 🚨"
            echo -e "$VIOLATIONS"
            echo -e "\n❌ PR REJECTED - See ADR-0001f for rules"
            exit 1
          else
            echo "✅ K0/K1 boundary compliance verified"
          fi

      - name: Check for Stateless Detector Compliance
        run: |
          # Allowed patterns: Stateless detectors in K1
          # Verify no state storage, no receipts issued

          # Check: Affect sensing tool is stateless
          if grep -r "class AffectSensingTool" k1/tools/; then
            if grep -r "self.affect_history\|self.state" k1/tools/affect_sensing.py; then
              echo "❌ AffectSensingTool has state (FORBIDDEN)"
              exit 1
            fi
            echo "✅ AffectSensingTool is stateless (allowed)"
          fi

          # Check: ASR VAD is stateless
          if grep -r "class ASRVAD" k1/voice/; then
            if grep -r "self.audio_buffer\|self.history" k1/voice/vad.py; then
              echo "❌ ASRVAD has state (FORBIDDEN)"
              exit 1
            fi
            echo "✅ ASRVAD is stateless (allowed)"
          fi
```

**Enforcement:**
- CI/CD checks run on every PR
- If violations detected: PR fails, author must refactor
- If compliant: PR passes automated checks, proceeds to human review

---

### 5.3 ADR Master Reference (Mandatory Cross-Link)

**In `docs/architecture/decisions/ADR_MASTER_REFERENCE.md`:**

```markdown
## 🚨 CRITICAL GOVERNANCE ADRs 🚨

**MANDATORY REVIEW FOR ALL CONTRIBUTORS:**

- **[ADR-0001f: K0/K1 Pipeline Boundary Enforcement](0001f-k0-k1-pipeline-boundary-enforcement.md)** 🚨
  - **Status:** CRITICAL - MANDATORY ENFORCEMENT
  - **Scope:** ALL code touching K0/K1 boundary, memory, pipelines
  - **Rule:** NO pipelines in K1, ALL state in K0, ALL writes via K0 Command API
  - **Enforcement:** CI/CD checks + code review checklist + architect approval
  - **Violations:** PR rejected without review

**All ADRs touching pipelines MUST reference ADR-0001f:**
- ADR-0059: Learning Loop (K1 Advisory-Only, K0 Persistence) → References 0001f
- ADR-0064: Self-Model & Consent (K0 P14 Implementation) → References 0001f
- ADR-0069: P08 AffectModulation (K0 Implementation) → References 0001f
```

---

### 5.4 Architect Review Triggers

**When to require architect approval:**

1. **New K1 tools/detectors:**
   - If tool has state (even temporary buffers) → Architect review required
   - If tool writes to K0 (even via Command API) → Architect review required
   - If tool caches K0 data (affect, self-model, feedback) → Architect review required

2. **New K0 pipelines:**
   - All new P01-P20 implementations → Architect review required
   - All pipeline modifications → Architect review required

3. **K0/K1 API changes:**
   - New Query/Command/SSE endpoints → Architect review required
   - K0 Bridge Client changes → Architect review required

4. **SessionState schema changes:**
   - Adding new sections to K1 SessionState → Architect review required
   - Storing K0-owned data in K1 SessionState → Architect review required (likely REJECTED)

**Architect Review Process:**
1. PR author flags PR with `needs-architect-review` label
2. Architect reviews against ADR-0001f boundary rules
3. Architect approves or rejects with rationale
4. If approved: PR proceeds to merge
5. If rejected: PR author refactors, re-submits for review

---

## 6. Affected ADRs (Cross-References)

### ADR-0059: Learning Loop (K1 Advisory-Only, K0 Persistence)

**Alignment with ADR-0001f:**
- ✅ **K1 Role:** Advisory-only signals (parameter suggestions, config recommendations)
- ✅ **K1 NEVER:** Persists learned preferences directly
- ✅ **K0 P06 FeedbackIntegration:** Authoritative persistence
- ✅ **Flow:** K1 emits advisory feedback → K0 P06 validates → persists → issues receipt

**Boundary Compliance:**
```python
# K1 emits advisory signal
k0_bridge.command(
    command_type="feedback_integration",
    port="P06",
    payload={
        "feedback_type": "explicit",  # 1.0 weight
        "key": "user_prefers_brief_responses",
        "value": True,
        "weight": 1.0
    }
)
# K0 P06 persists, K1 does NOT store feedback
```

---

### ADR-0064: Self-Model & Consent (K0 P14 Implementation)

**Alignment with ADR-0001f:**
- ✅ **K0 P14 SelfModelUpdate:** Owns style vector, exemplars, consent
- ✅ **K0 P10 ABAC:** Enforces consent policy
- ✅ **K1 Role:** Reads via K0 Query, requests updates via K0 Command
- ✅ **K1 NEVER:** Caches style vector, mutates self-model directly

**Boundary Compliance:**
```python
# K1 reads self-model from K0 (no caching)
response = k0_bridge.query(
    query_type="self_model_read",
    port="P14",
    payload={"user_id": user_id}
)
style_vector = StyleVector(**response["style_vector"])

# K1 requests self-model update via K0 P14
k0_bridge.command(
    command_type="self_model_update",
    port="P14",
    payload={
        "user_id": user_id,
        "updates": {"formality": 0.5}  # User preference changed
    }
)
# K0 P14 validates consent, persists, issues receipt
```

**New Sub-ADR: ADR-0064d (Decode-Knobs Mapping):**
- **K0 Role:** P14 stores knob mappings alongside style vector
- **K1 Role:** Reads mappings, applies to LLM generation calls
- **Boundary Compliance:** K1 reads knobs from K0, does NOT cache mappings

---

### ADR-0069: P08 AffectModulation (K0 Implementation)

**Alignment with ADR-0001f:**
- ✅ **K0 P08 AffectModulation:** Authoritative affect state (valence/arousal, salience)
- ✅ **K0 Role:** P08 stores affect in SessionState Scoreboard (ADR-0017b), issues receipts
- ✅ **K1 Role:** Optional stateless "Affect Sensing Tool" for local cues (NO state, NO receipts)
- ✅ **K1 NEVER:** Stores affect, caches valence/arousal

**Boundary Compliance:**
```python
# K1 optional stateless affect sensing tool
tone_suggestion = affect_sensing_tool.detect_local_cues(user_message, audio_prosody)
# Returns: ToneSuggestion(tone="empathetic", reason="user_frustrated")

# K1 uses suggestion for immediate LLM prompt tuning (stateless)
prompt = f"Respond with {tone_suggestion.tone} tone. User: {user_message}"
response = llm.generate(prompt)

# K1 updates K0 P08 for durable affect persistence
k0_bridge.command(
    command_type="affect_update",
    port="P08",
    payload={
        "valence": -0.5,  # Negative affect detected
        "arousal": 0.7,   # High arousal (frustration)
        "reason": "user_frustrated"
    }
)
# K0 P08 persists affect state, K1 does NOT cache
```

---

## Consequences

### Positive ✅

**✅ Architectural Clarity:**
- Clear "What K0 Does" / "What K1 Does" lists eliminate confusion
- No ambiguity about pipeline ownership (ALL pipelines in K0)
- **Result:** Teams can work independently without boundary disputes

**✅ Prevents Scope Creep:**
- Hard-coded rules prevent incremental boundary erosion
- CI/CD checks catch violations automatically
- **Result:** Architecture remains clean over time

**✅ Code Review Efficiency:**
- Mandatory checklist streamlines reviews
- Automated CI/CD checks reduce human error
- **Result:** Faster PR approvals, fewer rework cycles

**✅ Enables Confident Refactoring:**
- Teams can refactor K1/K0 independently knowing boundary is enforced
- No fear of "hidden dependencies" across boundary
- **Result:** Faster iteration, cleaner code

**✅ Onboarding Simplicity:**
- New contributors read ADR-0001f → understand boundary immediately
- Checklist guides them to compliant implementations
- **Result:** Reduced onboarding time, fewer mistakes

---

### Negative ⚠️

**⚠️ Increased Latency for K0 Reads:**
- K1 CANNOT cache K0 data (affect, self-model) → must query K0 every time
- **Impact:** +10-50ms latency per K0 Query call
- **Mitigation:** Optimize K0 Query performance (hot tier caching, FAISS indexes), batch queries where possible

**⚠️ Code Review Overhead:**
- Mandatory checklist + architect review for boundary-touching PRs
- **Impact:** +1-2 days review cycle for complex PRs
- **Mitigation:** Architect on-call rotation, async reviews, pre-review design docs

**⚠️ CI/CD Check Maintenance:**
- Automated grep checks require maintenance as codebase evolves
- **Impact:** False positives/negatives if patterns change
- **Mitigation:** Regular review of CI/CD rules, escape hatches for legitimate patterns

**⚠️ Learning Curve for K1 Stateless Tools:**
- Developers used to stateful tools may struggle with "no state" constraint
- **Impact:** Initial confusion, more questions during implementation
- **Mitigation:** Provide reference implementations (ADR-0069 Affect Sensing Tool), code examples, documentation

---

## Summary

**K0/K1 Pipeline Boundary Enforcement Complete** ✅

This ADR establishes **hard-coded, immutable architectural boundaries** between K0 (Memory Microkernel) and K1 (Agentic Orchestrator):

1. **K0 Owns ALL Pipelines P01-P20:** RecallQuery, MemoryWrite, AttentionGate, Hippocampus, ProspectiveTriggers, FeedbackIntegration, Sync/CRDT, AffectModulation, PII/ABAC, SelfModelUpdate, Emotional Intelligence, PersonalizationSync, ProactiveReminders
2. **K1 Has ZERO Pipelines:** Plans, orchestrates, executes tools, calls K0 ports (Query/Command/SSE)
3. **K1 MAY Use Stateless Detectors:** Affect sensing, ASR VAD, intent classification - NO durable state, NO receipts
4. **Enforcement:** CI/CD checks, code review checklist, architect approval, ADR master reference

**Critical Question Answered:**
- **Q:** "Do we require an affect module in K1?"
- **A:** NO. Affect state lives in **K0 P08 AffectModulation**. K1 may have stateless sensing tool for immediate reply shaping, but all durable state via K0.

**Status:** Mandatory for all contributors, enforced via CI/CD + code review.

---

## Implementation

### Phase 1: Documentation & Training (Week 1)
- [x] Create ADR-0001f (this document)
- [ ] Add ADR-0001f to ADR Master Reference (🚨 CRITICAL section)
- [ ] Update ADR-0059, ADR-0064, ADR-0069 to reference 0001f
- [ ] Create training slides for team (K0/K1 boundary rules)
- [ ] Host team training session (1 hour, mandatory attendance)

### Phase 2: CI/CD Checks (Week 2)
- [ ] Implement GitHub Actions workflow (`.github/workflows/k0-k1-boundary-check.yml`)
- [ ] Add grep checks for forbidden patterns (K1 pipelines, state caching, direct SQLite writes)
- [ ] Add checks for stateless detector compliance (no state, no receipts)
- [ ] Test CI/CD on sample PRs (intentionally add violations, verify detection)
- [ ] Enable required check on all PRs to `main` branch

### Phase 3: Code Review Process (Week 3)
- [ ] Add K0/K1 Boundary Compliance Checklist to PR template
- [ ] Set up architect review rotation (2 architects on-call each week)
- [ ] Document architect review process (triggers, approval criteria)
- [ ] Add review guidelines to `CONTRIBUTING.md`

### Phase 4: Existing Code Audit (Weeks 4-5)
- [ ] Audit K1 codebase for violations:
  - [ ] Check K1 SessionState for cached affect/self-model/feedback
  - [ ] Check K1 learning loop for durable state
  - [ ] Check K1 tools for state storage
- [ ] Refactor violations to comply with ADR-0001f
- [ ] Add unit tests for stateless detectors (verify no state)
- [ ] Integration tests for K0/K1 boundary (verify all writes via K0 Command API)

---

## Success Metrics

**Enforcement:**
- ✅ 100% of PRs touching K0/K1 boundary have completed checklist
- ✅ CI/CD checks catch 95%+ of violations automatically
- ✅ Zero boundary violations merged to `main` branch (enforced by CI/CD + review)
- ✅ Architect review completed within 48 hours for flagged PRs

**Team Understanding:**
- ✅ 100% of team members attend boundary training session
- ✅ New contributors complete boundary quiz (80%+ pass rate)
- ✅ Boundary questions drop by 50% after training (tracked in Slack)

**Codebase Compliance:**
- ✅ Zero K1 pipeline implementations (P01-P20 all in K0)
- ✅ Zero K1 durable state (affect, self-model, feedback)
- ✅ 100% of K1 memory writes via K0 Command API (no direct SQLite)
- ✅ Stateless detectors verified in unit tests (no state assertions)

---

## References

- [ADR-0001: K0/K1 Kernel Split](0001-k0-k1-kernel-split.md)
- [ADR-0001a: K0 Bridge Communication Protocol](0001a-k0-bridge-communication-protocol.md)
- [ADR-0059: Learning Loop (K1 Advisory-Only, K0 Persistence)](../../ADR_CREATION_PLAN_2025-10-14.md) - Planned Tier-1 ADR
- [ADR-0064: Self-Model & Consent (K0 P14 Implementation)](../../ADR_CREATION_PLAN_2025-10-14.md) - Planned Tier-2 ADR
- [ADR-0069: P08 AffectModulation (K0 Implementation)](../../ADR_CREATION_PLAN_2025-10-14.md) - Planned Tier-3 ADR
- [K0 Memory Module Documentation](https://github.com/your-org/memory_kernel)
- [K1 Intelligence Module Documentation](https://github.com/your-org/intelligence_module)

---

**Document Version:** 1.0
**Status:** 🚨 CRITICAL - MANDATORY ENFORCEMENT
**Next Review:** 2025-11-14 (monthly boundary audit)
