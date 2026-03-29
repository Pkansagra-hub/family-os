# Experience Layer -- Conversational Bond Engine

**Date:** February 27, 2026
**Status:** Design Whiteboard
**Context:** K1 Concierge POC, Experience Layer (poc/k1_poc/experience/)
**Scope:** What to implement, what to defer, and the philosophy behind it

---

## Core Philosophy: Fulfillment, Not Mirroring

In real conversation, people build bonds by *fitting into* each other's
emotional and conversational space. Not by mirroring (echoing sadness
back at a sad person) and not by opposing (forcing cheerfulness on
someone who is down). Instead: **fulfillment** -- giving the other
person what they emotionally need to move forward.

| User State | Wrong: Mirroring | Wrong: Opposing | Right: Fulfillment |
|---|---|---|---|
| Sad | "I can tell you're sad..." | "Cheer up! Look at the bright side!" | Gentle, practical, task-focused. Warm but not performative. Help them move forward. |
| Frustrated | "That IS frustrating..." | "Calm down, it's not a big deal." | Be the calm competent friend. De-escalate through action, not words about feelings. |
| Excited | "Wow, exciting!" | "Let's stay focused." | Amplify. Celebrate together. This is where energy matching IS correct. |
| Anxious | "I understand your worry..." | "There's nothing to worry about." | Project confidence. "I've got this" energy. Reduce uncertainty with facts. |
| Neutral | N/A | N/A | Efficient, friendly, don't overthink it. |

This is how families talk to each other. The system should feel like a
family member who *gets you* -- not a therapist narrating your feelings,
not a robot ignoring them.

---

## The Dead Pipeline Problem

Everything needed for emotional tone modulation already exists in the
codebase -- and none of it is active. Two disconnects exist:

### Disconnect 1: UltraBERT Writes Phase1 But Experience Layer Ignores It

**UltraBERT already runs every turn and writes real values:**

```
User input arrives
  -> _run_phase1_with_arbiter() [controller.py L1764]
    -> Phase1Pipeline.classify(text) [ultrabert_phase1.py]
      -> UltraBERT 12-head analysis (~20ms)
      -> Maps emotions -> primary_emotion, valence, arousal
    -> _write_phase1_to_ss(result) [controller.py L1620]
      -> affective_now.update(emotion=..., valence=..., arousal=...)
      -> scoreboard.set_user_intent(...)
      -> control.set_intent(...), set_primary_domain(...), escalate_safety(...)
```

So affective_now SS section already has REAL emotion/valence/arousal
from UltraBERT. The DynamicPromptBuilder already reads affective_now
and calls compute_affect_band(). But when Phase1 config is "stub"
(not "ultrabert"), StubPhase1Pipeline always returns valence=0.0,
arousal=0.0, primary_emotion="neutral".

**When UltraBERT IS active (config.phase1.pipeline == "ultrabert"):**
- Real emotion classification runs
- Real valence/arousal written to affective_now
- compute_affect_band() should resolve to real bands
- Tone blocks should activate

**Problem:** bootstrap.py _build_experience_context() feeds the
ExperienceLayer with EMPTY data regardless:

```python
# bootstrap.py L530-540 -- ALWAYS empty, ignores SS:
return {
    "turn_transcript": "",         # EMPTY -- never populated
    "affect_history": [],          # EMPTY -- never reads from SS
    "front_refine_affect_confidence": 0.0,
    "conversation_history": [],    # EMPTY -- never reads from SS
    ...
}
```

So even when UltraBERT writes real emotion data to affective_now,
the Experience Layer never sees it because _build_experience_context()
passes empty strings and empty lists.

### Disconnect 2: Experience Layer Output Not Fully Wired

_tick_experience() only publishes 2 of the 6 component outputs:

```python
# bootstrap.py L497-506
emotional = outputs.get("emotional")  # Published
fill = outputs.get("fill")            # Published
# "tone" from AffectiveMirror    -- DROPPED (not published, not written to SS)
# "timing" from RhythmController -- DROPPED
# "narrative"                    -- DROPPED
# "anticipation"                 -- DROPPED
```

### What IS Built and Wired (Working End-to-End When UltraBERT Active)

1. **affect.py** -- 5 affect bands (crisis, low, neutral, positive,
   elevated) with tone blocks injected into system prompt
2. **AFFECT_MODE_INTERACTIONS** -- 13 (mode, band) interaction blocks
   (e.g., "CRISIS + CLARIFICATION: Ask YES/NO instead of open-ended")
3. **AffectModifiers** -- Per-band overrides for iteration budget,
   history window, response length hints
4. **DynamicPromptBuilder Stage 3** -- Reads affective_now SS section,
   calls compute_affect_band(), injects tone blocks
5. **UltraBERT Phase 1 Pipeline** -- 12-head classifier that maps
   emotions to valence/arousal and writes to affective_now SS
6. **_write_phase1_to_ss()** -- Writes emotion/valence/arousal to
   affective_now, intent to scoreboard, safety to control

### The Affect Pipeline Is NOT Dead -- It Is Disconnected

When phase1.pipeline == "ultrabert":
- UltraBERT runs, writes REAL values to affective_now
- DynamicPromptBuilder reads affective_now -> compute_affect_band()
- This SHOULD already produce real affect bands and tone blocks
- The affect pipeline works end-to-end WITHOUT ExperienceLayer

When phase1.pipeline == "stub" (default for tests):
- StubPhase1Pipeline writes valence=0.0, arousal=0.0 always
- compute_affect_band() always returns "neutral"
- All tone blocks are dead code

### What the Experience Layer Should Actually Do

The Experience Layer does NOT need to duplicate UltraBERT's work.
UltraBERT provides the per-turn raw signal. The Experience Layer
provides **cross-turn trajectory and adaptation**:

- **EmotionalProcessor**: Track trajectory over N turns (trending
  sadder? recovering? stable?). UltraBERT sees one message at a time.
  EP sees the arc.
- **AffectiveMirror**: Take the trajectory + persona baseline and
  compute the fulfillment response strategy (not just band selection,
  but warmth/formality modulation).
- **ResponseStyleAdapter**: Learn the user's communication preferences
  over the session (verbosity, message style).

---

## Active Components (Implement Now)

### 1. EmotionalProcessor -- The Trajectory Tracker

**Purpose:** UltraBERT gives you the emotion of THIS turn. EP gives you
the arc: "user has been getting increasingly frustrated over 5 turns"
or "user was sad but is recovering." This cross-turn trajectory is what
enables the fulfillment philosophy -- you can't "try to make them happy"
if you don't know they're on a downward trend.

**What it reads (already in SS, written by UltraBERT Phase 1):**

- affective_now.valence (current turn, from UltraBERT)
- affective_now.arousal (current turn, from UltraBERT)
- affective_now.emotion (current turn, from UltraBERT)
- affect_history (accumulated from prior turns)

**IMPORTANT:** EP does NOT re-classify the user's message. UltraBERT
already did that. EP reads UltraBERT's output from affective_now and
computes the trajectory over time.

**Heuristic approach:**

- Maintain sliding window of last N affective_now snapshots
- Weighted moving average: recent turns weighted more heavily
- Trend = slope of valence over window (rising/falling/stable)
- Confidence = inverse of variance (stable signal = high confidence)
- Dominance inferred from intent patterns (commands vs questions)

**Output:** EmotionalTrajectory (updates affective_now with trajectory)

- valence: smoothed -1.0 to +1.0 (trajectory, not single-turn)
- arousal: smoothed 0.0 to 1.0
- dominance: 0.0 to 1.0
- trend: "rising" | "falling" | "stable"
- confidence: 0.0 to 1.0

**Budget:** 1ms (pure math on existing SS data)

**Key difference from current broken state:**

```
BEFORE (broken): EP stub returns defaults -> overrides UltraBERT values -> flat
AFTER (correct): EP reads UltraBERT values FROM SS -> computes trajectory -> writes TRAJECTORY back
```

EP enriches UltraBERT's per-turn signal, not replaces it.

---

### 2. AffectiveMirror -- The Bond Builder

**Purpose:** Take EmotionalTrajectory and produce ToneAdjustment that
implements the fulfillment philosophy, modulated by persona baseline.

**Why it exists separately from EP:**
- EP computes *what the user feels* (signal reading)
- AM computes *how the system should respond* (fulfillment strategy)
- Persona modulates AM output: high-formality persona stays professional
  even during positive energy. High-warmth persona runs warmer even
  during neutral band.

**Fulfillment mapping (not mirroring):**

```
User valence < -0.3 (sad/frustrated):
  warmth += 0.15 above persona baseline
  formality -= 0.1 (slightly more casual, approachable)
  mirror_intensity = 0.0 (do NOT mirror negativity)
  Strategy: warm + action-oriented. Help them, don't narrate feelings.

User valence > 0.5 (excited/happy):
  warmth += 0.1
  mirror_intensity = 0.7 (energy matching IS appropriate here)
  Strategy: amplify, celebrate, share the excitement.

User arousal > 0.7 + valence < -0.5 (crisis/panic):
  warmth = 0.6 (warm but not excessive)
  formality += 0.1 (slightly more structured = grounding)
  mirror_intensity = 0.0 (absolutely do not mirror panic)
  Strategy: calm, competent, structured. Ground them.

User neutral:
  Use persona baseline as-is.
  Strategy: efficient, friendly, standard.
```

**Output:** ToneAdjustment
- warmth: 0.0-1.0 (modulated around persona baseline)
- formality: 0.0-1.0 (modulated around persona baseline)
- pace: "slow" | "normal" | "fast"
- mirror_intensity: 0.0-1.0

**Budget:** 1ms (arithmetic on EP output + persona config)

**Integration:** ToneAdjustment needs to be written to SS and consumed
by DynamicPromptBuilder. Currently only "emotional" and "fill" outputs
are published by bootstrap._tick_experience(). Need to wire "tone"
output to SS and have the builder read it.

---

### 3. ResponseStyleAdapter (Renamed from RhythmController)

**Purpose:** Learn and adapt to each user's communication preferences.
Not timing/pacing (that adds latency). Style and shape of responses.

**The insight:** Some users love long detailed responses. Others want
"just tell me the answer." Some users fire rapid short messages
back-to-back (conversational style). Others compose one complete
message. The system should learn this and adapt.

**What it tracks (from existing conversation data):**

| Signal | Source | What It Tells Us |
|---|---|---|
| User avg message length | conversation_history | Long = user handles detail. Short = user wants concise. |
| User message frequency | turn timestamps | Rapid-fire = conversational style. Spaced = composed style. |
| Re-ask rate | conversation_history | User re-asks shorter = previous response was too verbose. |
| Question complexity | UltraBERT intent | Complex question = can handle complex answer. |
| Member profile defaults | persona section | Starting point before adaptation. |

**Output:** ResponseStyle (replaces TimingParams)
- response_length_preference: "concise" | "balanced" | "detailed"
- message_style: "single_complete" | "conversational_bursts"
- verbosity_level: 0.0 to 1.0

**Heuristic approach:**
```
avg_user_msg_len = running_average(user_message_lengths, window=10)

if avg_user_msg_len < 30 chars:
    response_length_preference = "concise"
    verbosity_level = 0.3
elif avg_user_msg_len < 100 chars:
    response_length_preference = "balanced"
    verbosity_level = 0.5
else:
    response_length_preference = "detailed"
    verbosity_level = 0.7

# Multi-message pattern detection
if count(messages_within_5s) / total_messages > 0.4:
    message_style = "conversational_bursts"
else:
    message_style = "single_complete"
```

**Integration with prompt:** ResponseStyle hints are injected into the
system prompt as advisory guidance:
- concise: "Keep responses brief and to the point. 2-3 sentences max unless the topic requires detail."
- detailed: "User appreciates thorough responses. Include context and explanation."
- conversational_bursts: "Keep each message short. User prefers quick back-and-forth."

**Budget:** 0.5ms (counters and averages)

**Why this is not the old RhythmController:**
The old RhythmController was about delivery timing (pre_delay_ms,
inter_chunk_ms, typing indicators). That concept adds latency to an
already-slow LLM pipeline and provides marginal UX benefit. The new
ResponseStyleAdapter shapes *what* the LLM generates, not *when* it
delivers. Zero latency added.

---

## Deferred Components (Keep as Stubs)

### 4. NarrativeWeaver -- DEFERRED

**Reason:** The LLM (Gemini) already does narrative tracking natively
through conversation history in the prompt. Before adding a heuristic
overlay, we need to benchmark the LLM's native narrative coherence to
understand:
- Does it lose thread after N turns?
- Does it fail to reconnect topics?
- Does it miss context from memory recalls?

If the LLM handles narrative well (likely for shorter sessions), adding
NarrativeWeaver risks conflicting signals. Benchmark first.

**Action:** Keep stub. Add "Narrative Coherence Benchmark" to backlog.

### 5. AnticipatoryResponder -- DEFERRED

**Reason:** Pre-fetching and intent prediction add architectural
complexity with marginal benefit at POC stage. The LLM already handles
follow-up intent well through conversation context. Premature
optimization of capability pre-warming.

**Action:** Keep stub.

### 6. ProactiveAgent -- DEFERRED

**Reason:** Fill messages during long waits require a full Front LLM
invocation. This adds latency and cost by definition. The FSM already
handles wait states. In a POC, silent waiting is acceptable. Implement
when the system is stable and the cost/benefit is clearer.

**Action:** Keep stub.

---

## Total Latency Budget

| Component | Budget | Nature |
|---|---|---|
| EmotionalProcessor | 1ms | Pure math on UltraBERT output + affect_history |
| AffectiveMirror | 1ms | Arithmetic on EP output + persona config |
| ResponseStyleAdapter | 0.5ms | Counters and running averages |
| **Total** | **< 3ms** | **Zero LLM calls. Zero I/O. Zero network.** |

For comparison: a single LLM call is 500-2000ms. The experience layer
adds < 0.2% overhead.

---

## What Changes in User Experience

### Before (Current State)

Every response uses "neutral" tone regardless of user emotion. Same
verbosity for a user who writes one-word messages and a user who writes
paragraphs. Same style always. Robotic consistency.

The LLM's own personality provides some natural variation, but it has
no signal about the user's emotional state or communication preferences.
It guesses from conversation text alone.

### After (With Active Components)

**Emotional adaptation:**
- User says "my mom's surgery got moved up, I'm freaking out" -->
  EP detects crisis band --> prompt gets "Lead with ACTION. One sentence
  acknowledgment, then numbered options. Shorter response." -->
  LLM response is structured, grounding, action-oriented.

- Same user next day: "great news, surgery went perfectly!" -->
  EP detects positive band --> prompt gets "Match their energy.
  Celebrate wins together." --> LLM shares the excitement.

**Style adaptation:**
- User consistently sends short messages ("whats for dinner",
  "order pizza", "pepperoni") --> RSA sets concise mode -->
  prompt gets "Keep responses brief, 2-3 sentences max" -->
  LLM stops generating walls of text.

- Different user writes detailed messages with full context -->
  RSA sets detailed mode --> prompt gets "User appreciates
  thorough responses" --> LLM provides comprehensive answers.

**The bond effect:**
The system "fits into" the user's conversational space. Not by
announcing "I detect you are sad" -- but by naturally adjusting
tone, length, and energy. Like talking to someone who gets you.

---

## Wiring Requirements

### Current Signal Flow (UltraBERT Active)

```
User input
  |
  v
Phase 1: UltraBERT classify(text) [~20ms, single forward pass]
  |
  v
_write_phase1_to_ss():
  affective_now.update(emotion, valence, arousal, confidence)
  scoreboard.set_user_intent(intent, confidence)
  control.set_intent(), set_primary_domain(), escalate_safety()
  |
  v
TurnLock.release() -- Phase 1 committed
  |
  v
Front LLM starts (DynamicPromptBuilder reads affective_now)
  |
  v
compute_affect_band(affective_now) -> AffectBand
  |
  v
AFFECT_TONE_BLOCKS[band] -> injected into system prompt
AFFECT_MODE_INTERACTIONS[(mode, band)] -> additional blocks
AffectModifiers[band] -> iteration budget, history window
  |
  v
Front LLM generates response WITH affect-modulated prompt
  |
  v
_tick_experience(runtime) -- AFTER front_handler completes
  |
  v
_build_experience_context() -> EMPTY DICT (BUG: ignores SS)
  |
  v
ExperienceLayer.tick() -> all stubs return defaults (wasted)
```

### Target Signal Flow (With Experience Layer Active)

```
User input
  |
  v
Phase 1: UltraBERT classify(text) [~20ms]
  |
  v
_write_phase1_to_ss(): affective_now, scoreboard, control
  |
  v
TurnLock.release()
  |
  v
Front LLM starts (reads affective_now for THIS turn's band)
  |
  v
compute_affect_band() -> tone blocks -> affect-modulated prompt
  |
  v
Front LLM generates response
  |
  v
_tick_experience(runtime) -- AFTER front_handler
  |
  v
_build_experience_context():
  - reads affective_now FROM SS (UltraBERT's values)
  - reads conversation_history FROM SS
  - reads user message lengths, timestamps
  |
  v
EmotionalProcessor: reads UltraBERT's affective_now + history
  -> computes trajectory (trend, smoothed valence, confidence)
  -> writes trajectory back to affective_now
  |
  v
AffectiveMirror: reads trajectory + persona baseline
  -> computes fulfillment-based ToneAdjustment
  -> writes to SS for next turn's prompt
  |
  v
ResponseStyleAdapter: reads message lengths, timestamps
  -> computes response_length_preference, verbosity_level
  -> writes to SS for next turn's prompt
```

Key change: the Experience Layer runs AFTER the current turn's LLM
response (so it doesn't add latency to the current response). Its
outputs affect the NEXT turn's prompt assembly.

### Fix 1: _build_experience_context Must Read SS

```python
# bootstrap.py -- CURRENT (broken):
"turn_transcript": "",
"affect_history": [],

# SHOULD BE:
"turn_transcript": _get_last_user_message(runtime),
"affect_history": _get_affect_history(runtime.session_state),
"conversation_history": _get_conversation_history(runtime),
```

### Fix 2: _tick_experience Must Publish All Outputs

```python
# bootstrap.py -- CURRENT (drops tone, timing):
emotional = outputs.get("emotional")  # Published
fill = outputs.get("fill")            # Published

# ADD:
tone = outputs.get("tone")
if tone is not None:
    _write_tone_to_ss(runtime.session_state, tone)

style = outputs.get("timing")  # will be ResponseStyle
if style is not None:
    _write_response_style_to_ss(runtime.session_state, style)
```

### Currently Wired (bootstrap.py _tick_experience)

- EP "emotional" output --> published to bus
- PA "fill" output --> published to bus

### Needs Wiring

- AM "tone" output --> write ToneAdjustment to SS, DynamicPromptBuilder
  reads it for warmth/formality modulation
- RSA "timing" output --> needs new ResponseStyle dataclass, write to SS,
  DynamicPromptBuilder reads it for response length/verbosity hints

### DynamicPromptBuilder Integration Points
- Stage 3 (Affect Tone Blocks): Already reads affective_now --> will
  activate once EP writes real values
- New: Read ToneAdjustment from SS for persona modulation
- New: Read ResponseStyle from SS for length/verbosity prompt hints

---

## Implementation Order

1. **EmotionalProcessor** -- Highest ROI. Activates entire dead affect
   pipeline. Implement first, test that affect bands start changing.

2. **AffectiveMirror** -- Chain after EP. Adds persona modulation on
   top of raw emotional signal. Wire tone output to SS.

3. **ResponseStyleAdapter** -- New dataclass, new heuristics, new
   prompt injection. Independent of EP/AM. Can be implemented in
   parallel.

4. **DynamicPromptBuilder wiring** -- Consume ToneAdjustment and
   ResponseStyle from SS. Inject advisory hints into prompt.

---

## Open Questions

1. **ResponseStyle prompt injection format:** Should verbosity hints be
   a separate prompt section or appended to the existing AFFECT_TONE_BLOCKS?

2. **Affect history window size:** How many past trajectories should EP
   use for moving average? Too few = reactive. Too many = sluggish.
   Start with 5, tune empirically.

3. **Persona baseline source:** Where does the persona warmth/formality
   baseline come from? Currently in smith_family.py demo profile. For
   POC, hardcode defaults. For production, read from member profile.

4. **ResponseStyle persistence:** Should learned response preferences
   persist across sessions (write to K0 memory) or reset each session?
   POC: session-only. Production: persist to K0.

5. **Benchmark before NarrativeWeaver:** What metrics define "good
   narrative coherence"? Need to define benchmark criteria before we
   can measure the LLM's native performance.
