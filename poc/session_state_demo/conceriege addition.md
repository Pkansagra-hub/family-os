Read [](file:///d%3A/familyos/poc/session_state_demo)

Read [](file:///d%3A/familyos/poc/session_state_demo/bridge.py#1-1), lines 1 to 150

Read [](file:///d%3A/familyos/poc/session_state_demo/demo.py#1-1), lines 1 to 200

Read [](file:///d%3A/familyos/poc/session_state_demo/llm_client.py#1-1), lines 1 to 150

Read [](file:///d%3A/familyos/poc/session_state_demo/tools.py)

Read [](file:///d%3A/familyos/poc/session_state_demo/demo.py#200-200), lines 200 to 395

Read [](file:///d%3A/familyos/poc/session_state_demo/write_gate.py#1-1), lines 1 to 200

Read [](file:///d%3A/familyos/poc/session_state_demo/scripted_demo.py)

Now let me look at the K1 Concierge FSM in the architecture to understand what we need:

Read [](file:///d%3A/familyos/architecture_diagrams/k1/k1_cognitive_architecture_skeleton.mmd#70-70), lines 70 to 200

Now I have a complete understanding. Let me write a plan for adding a simple Concierge FSM to the demo:

---

## Plan: Simple Concierge FSM for Session State Demo

### Current State Analysis

**What we have:**
```
poc/session_state_demo/
├── bridge.py          # SessionLLMBridge - direct LLM calls, no FSM
├── demo.py            # Interactive CLI - simple input → LLM → output loop
├── scripted_demo.py   # Scripted 5-turn demo
├── llm_client.py      # Google AI wrapper
├── tools.py           # 3 tools: update_persona, update_emotion, add_belief
├── write_gate.py      # Dedup gate
├── display.py         # Colorized output
└── config.py          # Configuration
```

**Current Flow (No FSM):**
```
User Input → record_user_turn() → build_context() → LLM call → execute_tools() → record_assistant_turn()
```

**Target Flow (With FSM):**
```
User Input → [LISTENING] → [ACKING] → (classify) → [CLARIFYING?] → [DISPATCHING] → [EXECUTING] → [DELIVERING]
                  ↑                         ↓ (gaps found)              ↓
                  └─────────────────────────┘                    [COMPANIONING]
```

---

### Minimal Concierge FSM Design

**Goal**: Add the **core FSM loop** without full UltraBERT. Use simple heuristics + LLM for classification.

#### States to Implement (Simplified)

| State | Purpose | Demo Implementation |
|-------|---------|---------------------|
| **LISTENING** | Wait for input | Entry point (already implicit) |
| **ACKING** | Classify intent, detect gaps | Heuristic + optional LLM |
| **CLARIFYING** | Ask clarification questions | Generate question, wait for answer |
| **DISPATCHING** | Route by complexity | LOW/MEDIUM tier only |
| **EXECUTING** | Run tools | Current tool execution |
| **DELIVERING** | Send response | Current response output |

#### Complexity Router (Simplified)

| Tier | Criteria | Path |
|------|----------|------|
| **LOW** | Single intent, no gaps, greetings | Direct tool → response |
| **MEDIUM** | Multi-intent or minor gaps | LLM reasoning → tools → response |
| **HIGH** | Not implemented in POC | (future: Orchestrator → Planner) |

#### Gap Detection (Simplified)

Check for common gaps without UltraBERT:
- **Missing time**: "remind me" without when
- **Vague pronouns**: "them", "it" without referent
- **Missing quantity**: "buy some" without amount
- **Ambiguous person**: "my family" without who specifically

---

### Implementation Plan

#### New Files

```
poc/session_state_demo/
├── concierge/
│   ├── __init__.py
│   ├── fsm.py           # ConciergeFSM class
│   ├── states.py        # State definitions & transitions
│   ├── classifier.py    # Intent + complexity classification
│   ├── gap_detector.py  # Gap detection heuristics
│   └── router.py        # Complexity-based routing
```

#### Phase 1: FSM Core (2 hours)

1. **Create `states.py`** - State enum and transitions
   ```python
   class ConciergeState(Enum):
       LISTENING = "listening"
       ACKING = "acking"
       CLARIFYING = "clarifying"
       DISPATCHING = "dispatching"
       EXECUTING = "executing"
       DELIVERING = "delivering"
   ```

2. **Create `fsm.py`** - Main FSM controller
   - State machine with transition rules
   - Event-driven transitions
   - Integration with SessionState

#### Phase 2: Classification (1.5 hours)

3. **Create `classifier.py`** - Intent classification
   - Heuristic intent detection (keywords, patterns)
   - Complexity tier assignment (LOW/MEDIUM)
   - Optional: Use LLM for complex cases

4. **Create `gap_detector.py`** - Gap detection
   - Regex-based patterns for common gaps
   - Context inference from SessionState
   - Uncertainty scoring

#### Phase 3: Routing & Integration (1.5 hours)

5. **Create `router.py`** - Complexity router
   - Route LOW tier directly to tools
   - Route MEDIUM tier through LLM reasoning

6. **Update bridge.py** - Integrate FSM
   - Replace direct LLM call with FSM processing
   - Add FSM state tracking to stats

#### Phase 4: Demo Updates (1 hour)

7. **Update display.py** - FSM state visualization
   - Show current state in output
   - Show transitions
   - Show gap detection results

8. **Create `concierge_demo.py`** - FSM-focused demo
   - Scripted scenarios that trigger clarification
   - Show complexity routing in action

---

### File Details

#### `concierge/states.py`
```python
from enum import Enum, auto
from dataclasses import dataclass
from typing import Optional, List

class ConciergeState(Enum):
    LISTENING = auto()      # Waiting for user input
    ACKING = auto()         # Processing input, classifying
    CLARIFYING = auto()     # Need more info from user
    DISPATCHING = auto()    # Routing to execution path
    EXECUTING = auto()      # Running tools
    DELIVERING = auto()     # Sending response

class ComplexityTier(Enum):
    LOW = "low"       # <2s, simple tool call
    MEDIUM = "medium" # 2-10s, LLM reasoning
    HIGH = "high"     # Not implemented (would go to Planner)

@dataclass
class ClassificationResult:
    primary_intent: str
    complexity: ComplexityTier
    gaps: List[str]
    confidence: float
    requires_clarification: bool
```

#### `concierge/gap_detector.py`
```python
# Heuristic gap detection patterns
GAP_PATTERNS = {
    "missing_time": [
        (r"remind me|set reminder|remind", "When should I remind you?"),
        (r"schedule|book|appointment", "What time works for you?"),
    ],
    "missing_quantity": [
        (r"buy some|get some|order", "How many would you like?"),
    ],
    "vague_reference": [
        (r"\bthem\b|\bit\b|\bthose\b", "Who or what are you referring to?"),
    ],
    "missing_location": [
        (r"meet|go to|visit", "Where would you like to meet?"),
    ],
}
```

#### `concierge/fsm.py`
```python
class ConciergeFSM:
    """
    Simplified Concierge FSM for demo.

    States: LISTENING → ACKING → CLARIFYING? → DISPATCHING → EXECUTING → DELIVERING
    """

    def __init__(self, bridge: SessionLLMBridge):
        self._bridge = bridge
        self._state = ConciergeState.LISTENING
        self._pending_gaps: List[str] = []
        self._classification: Optional[ClassificationResult] = None

    async def process_input(self, user_input: str) -> TurnResult:
        """Process user input through FSM."""
        # LISTENING → ACKING
        self._transition(ConciergeState.ACKING)
        classification = await self._classify(user_input)

        # Check for gaps
        if classification.requires_clarification:
            # ACKING → CLARIFYING
            self._transition(ConciergeState.CLARIFYING)
            return TurnResult(
                state=self._state,
                needs_clarification=True,
                clarification_question=classification.gaps[0],
            )

        # ACKING → DISPATCHING
        self._transition(ConciergeState.DISPATCHING)

        # Route by complexity
        if classification.complexity == ComplexityTier.LOW:
            # LOW: Direct tool execution
            result = await self._execute_low_tier(user_input)
        else:
            # MEDIUM: LLM reasoning + tools
            result = await self._execute_medium_tier(user_input)

        # EXECUTING → DELIVERING
        self._transition(ConciergeState.DELIVERING)

        # Back to LISTENING
        self._transition(ConciergeState.LISTENING)

        return result
```

---

### Demo Scenarios

**Scenario 1: Clarification Flow**
```
User: "Remind me about the meeting"
[ACKING] Intent: set_reminder, Gaps: ["missing_time"]
[CLARIFYING] "When should I remind you about the meeting?"
User: "Tomorrow at 9am"
[ACKING] Intent: set_reminder, Gaps: [] (resolved)
[DISPATCHING] Tier: LOW
[EXECUTING] Tool: set_reminder
[DELIVERING] "I'll remind you about the meeting tomorrow at 9am"
```

**Scenario 2: Low Complexity**
```
User: "Hi!"
[ACKING] Intent: greeting, Tier: LOW, Gaps: []
[DISPATCHING] Direct response (no tools)
[DELIVERING] "Hello! How can I help you today?"
```

**Scenario 3: Medium Complexity**
```
User: "I'm planning a family trip to Japan with two kids ages 8 and 12"
[ACKING] Intent: [travel_planning, record_family_info], Tier: MEDIUM
[DISPATCHING] → LLM reasoning
[EXECUTING] Tools: add_belief, update_persona
[DELIVERING] "That sounds exciting! Japan is great for families..."
```

---

### Success Metrics

| Metric | Target |
|--------|--------|
| FSM states visible in output | All 6 states shown |
| Clarification triggers | At least 2 demo scenarios |
| Complexity routing | LOW/MEDIUM correctly classified |
| Latency overhead | <50ms for FSM logic |
| Coverage increase | From 45% to ~55% |

---

### Estimated Time: 6 hours total

| Phase | Time | Deliverable |
|-------|------|-------------|
| Phase 1: FSM Core | 2h | `states.py`, `fsm.py` |
| Phase 2: Classification | 1.5h | `classifier.py`, `gap_detector.py` |
| Phase 3: Integration | 1.5h | `router.py`, updated bridge.py |
| Phase 4: Demo | 1h | `concierge_demo.py`, display updates |

---

### Questions Before Implementation

1. **Should clarification loop back to user input?** (Yes in real system, but for demo we could auto-provide answers in scripted mode)

2. **Include intent detection via LLM?** (Can use simple heuristics for POC, or one LLM call for classification)

3. **Show FSM state in output?** (Yes - visually show `[ACKING]`, `[CLARIFYING]`, etc.)

---

Shall I proceed with Phase 1 (FSM Core)?
