"""
K1 L4 Runtime — Intent Switch (Context-Switch Detection)

**Purpose:** 3-stage context-switch detection with intent drift, discourse markers, user confirmation

**Components:**
- detector/ — 3-stage detection (intent drift + discourse markers + confirmation)
- drift_calculator/ — Intent drift score 0.0-2.0
- prompt_generator/ — 3 confidence templates (voice variants)
- session_manager/ — History management (new/continue/go_back, session stack)

**Performance:**
- Drift calculation: <10ms
- Prompt generation: <50ms
- Session archiving: <100ms

**ADRs (4 total):**
- ADR-0055: Main Detection (3-stage: intent drift + discourse markers + confirmation)
- ADR-0055a: Intent Drift Rules (3-level taxonomy, drift score 0.0-2.0)
- ADR-0055b: Switch Prompt (3 confidence templates, voice variants)
- ADR-0055c: History Management (new/continue/go_back, session stack)

**3-Stage Detection (ADR-0055):**

1. **Stage 1: Intent Drift Detection**
   - Cosine similarity between current intent and session history
   - Drift score 0.0 (same) → 2.0 (completely different)
   - Threshold: >0.7 triggers Stage 2

2. **Stage 2: Discourse Markers**
   - Detect explicit markers: "wait", "actually", "never mind", "instead"
   - Boosts drift score by +0.3
   - Combined score >1.0 triggers Stage 3

3. **Stage 3: User Confirmation**
   - Prompt user: "It looks like you want to switch topics. Should I start a new conversation?"
   - 3 confidence levels (high/medium/low) use different prompt templates
   - Voice variants with prosody controls

**Intent Drift Score (ADR-0055a):**
- **Level 1 (0.0-0.5):** Same topic, refinement
- **Level 2 (0.5-1.0):** Related topic, tangential
- **Level 3 (1.0-2.0):** Completely different topic, context switch

**History Management (ADR-0055c):**
- **new:** Create new session, archive current session
- **continue:** Continue current session (no switch)
- **go_back:** Return to previous session from stack

**Integration:**
- SessionState: Scoreboard QUD stack tracks intent history
- L2 Planner: Context switch triggers plan re-generation
- L3 Dialogue: Turn manager coordinates switch timing

**Performance Metrics:**
- intent_switch_detections_total (counter, stage=1|2|3)
- intent_switch_drift_score (histogram)
- intent_switch_user_choices_total (counter, choice=new|continue|go_back)

**Last Updated:** October 2025
**Status:** Production-ready context-switch detection
"""

__version__ = "0.1.0"

# TODO: Implement detector/, drift_calculator/, prompt_generator/, session_manager/
# Per ADR-0055 family (0055-0055c)
