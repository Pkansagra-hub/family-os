# Full Architecture Implementation Plan

## Option B: Wire ConciergeFSM + Sub-Agents + All 12 SessionState Sections + Delta Bus

**Target Duration:** 1-2 days
**Status:** Planning
**Created:** 2026-02-04

---

## Executive Summary

The current demo has **all the pieces** but they are **not wired together**:

| Component | EXISTS | WIRED | NOTES |
|-----------|--------|-------|-------|
| SessionLLMBridge | YES | PARTIAL | Only uses 5-6 of 12 sections |
| ConciergeFSM | YES | NO | Completely bypassed in runner |
| IntentClassifier | YES | NO | Uses heuristics, not used at all |
| GapDetector | YES | NO | Heuristic-based, bypassed |
| ComplexityRouter | YES | NO | Not connected |
| TwoWayConcierge | YES | NO | Not used |
| TaskQueue | YES | NO | Not integrated |
| NotificationQueue | YES | NO | Not integrated |
| ToolExecutor | YES | YES | 21 tools, works |
| SimpleLLMClient | YES | YES | Real API calls |

**Goal:** Wire all existing components together as the architecture intended.

---

## Component Inventory

### Existing Files to REUSE (Don't Rewrite!)

```
poc/session_state_demo/
├── bridge.py                         # SessionLLMBridge (968 lines) - REUSE
├── llm_client.py                     # SimpleLLMClient (160 lines) - REUSE
├── config.py                         # Configuration - REUSE
│
├── concierge/                        # FSM Components - WIRE UP
│   ├── fsm.py                        # ConciergeFSM (366 lines) - WIRE UP
│   ├── classifier.py                 # IntentClassifier (372 lines) - WIRE UP
│   ├── gap_detector.py               # GapDetector (294 lines) - UPGRADE TO LLM
│   ├── router.py                     # ComplexityRouter (200 lines) - WIRE UP
│   └── states.py                     # State definitions (200 lines) - REUSE
│
├── anniversary_demo/
│   ├── runner.py                     # DemoRunner (778 lines) - MODIFY
│   ├── display.py                    # Display functions - REUSE
│   ├── script.py                     # Turn scripts - REUSE
│   │
│   ├── tools/
│   │   ├── executor.py               # ToolExecutor (812 lines) - REUSE
│   │   └── registry.py               # ToolRegistry (1139 lines) - REUSE
│   │
│   └── background/
│       ├── concierge_loop.py         # TwoWayConcierge (443 lines) - WIRE UP
│       ├── task_queue.py             # TaskQueue (340 lines) - WIRE UP
│       ├── notifications.py          # NotificationQueue (331 lines) - WIRE UP
│       └── registry.py               # TaskRegistry - WIRE UP
```

### Files to CREATE (New Code)

```
poc/session_state_demo/
├── anniversary_demo/
│   ├── agents/                       # NEW - Sub-agent system
│   │   ├── __init__.py
│   │   ├── base.py                   # BaseSubAgent (READ-ONLY)
│   │   ├── search_agent.py           # SearchAgent
│   │   └── booking_agent.py          # BookingAgent
│   │
│   └── bus/                          # NEW - Delta bus
│       ├── __init__.py
│       └── delta_bus.py              # Message passing
│
├── concierge/
│   └── llm_gap_detector.py           # NEW - LLM-driven gap detection
```

---

## Milestone Structure

### MILESTONE 5: Wire ConciergeFSM as Orchestrator

**Epic 5.1: FSM Integration into Runner**

| Issue | Task | Files Changed | Est Time |
|-------|------|---------------|----------|
| 5.1.1 | Import ConciergeFSM into runner.py | runner.py | 15 min |
| 5.1.2 | Replace direct LLM calls with fsm.process_input() | runner.py | 30 min |
| 5.1.3 | Connect FSM to bridge (already has constructor param) | runner.py | 15 min |
| 5.1.4 | Connect FSM to llm_client | runner.py | 15 min |
| 5.1.5 | Add state transition logging to display | runner.py, display.py | 30 min |
| 5.1.6 | Test FSM-driven demo for 5 turns | - | 30 min |

**Acceptance Criteria:**

- `runner.py` uses `ConciergeFSM.process_input()` for all turns
- FSM state transitions visible in output (LISTENING → ACKING → DISPATCHING → EXECUTING → DELIVERING)
- IntentClassifier categorizes each turn
- ComplexityRouter decides LOW/MEDIUM tier

---

### MILESTONE 6: All 12 SessionState Sections

**Epic 6.1: HOT Tier Full Utilization**

| Issue | Task | Section | Est Time |
|-------|------|---------|----------|
| 6.1.1 | Wire `control` section - turn lock, flow state | control | 30 min |
| 6.1.2 | Wire `scoreboard` section - track current referents + QUD | scoreboard | 45 min |
| 6.1.3 | Wire `clarifications` section - store pending gaps | clarifications | 30 min |
| 6.1.4 | Wire `narrative_active` section - track conversation phase | narrative_active | 30 min |
| 6.1.5 | Ensure beliefs_active is populated from tools | beliefs_active | 15 min |
| 6.1.6 | Ensure history_active captures all turns | history_active | 15 min |
| 6.1.7 | Ensure affective_now updated on emotion changes | affective_now | 15 min |
| 6.1.8 | Ensure meta section has session info | meta | 15 min |

**Epic 6.2: WARM Tier Full Utilization**

| Issue | Task | Section | Est Time |
|-------|------|---------|----------|
| 6.2.1 | Wire `beliefs_history` - evicted beliefs | beliefs_history | 30 min |
| 6.2.2 | Wire `history_recent` - turns 11-40 | history_recent | 30 min |
| 6.2.3 | Wire `persona` - inject into LLM context | persona | 30 min |
| 6.2.4 | Wire `telemetry` - tokens, latency, costs | telemetry | 20 min |

**Epic 6.3: Context Injection to LLM**

| Issue | Task | Files Changed | Est Time |
|-------|------|---------------|----------|
| 6.3.1 | Update build_llm_context() to include ALL sections | bridge.py | 45 min |
| 6.3.2 | Create CONTEXT_INJECTION block for system prompt | runner.py | 30 min |
| 6.3.3 | Add "KNOWN FACTS" section from beliefs_active | runner.py | 20 min |
| 6.3.4 | Add "USER PREFERENCES" section from persona | runner.py | 20 min |
| 6.3.5 | Add "CURRENT TOPIC" from scoreboard | runner.py | 20 min |
| 6.3.6 | Add "PENDING CLARIFICATIONS" if any | runner.py | 15 min |
| 6.3.7 | Add "CONVERSATION PHASE" from narrative_active | runner.py | 15 min |

**Acceptance Criteria:**

- System prompt includes context from all 12 sections
- LLM sees: KNOWN FACTS, USER PREFERENCES, CURRENT TOPIC, PENDING CLARIFICATIONS
- bridge.get_snapshot() shows all sections with data
- Memory usage stays under 96KB cap

---

### MILESTONE 7: LLM-Driven Gap Detection

**Epic 7.1: Replace Heuristic Gap Detector**

| Issue | Task | Files Changed | Est Time |
|-------|------|---------------|----------|
| 7.1.1 | Create LLMGapDetector class | concierge/llm_gap_detector.py | 1 hr |
| 7.1.2 | Gap detection prompt template | llm_gap_detector.py | 30 min |
| 7.1.3 | Parse LLM output for gaps | llm_gap_detector.py | 30 min |
| 7.1.4 | Integrate with ConciergeFSM | fsm.py | 30 min |
| 7.1.5 | Store gaps in clarifications section | bridge.py | 20 min |
| 7.1.6 | Test gap detection on Turn 10, 14, 18 | - | 30 min |

**LLMGapDetector Design:**

```python
class LLMGapDetector:
    """Use LLM to detect missing information."""

    GAP_DETECTION_PROMPT = """
    Given this user request: "{user_input}"
    And this tool the user likely wants: {tool_schema}
    And these known facts: {beliefs}

    Identify ANY missing required parameters.
    For each gap, provide:
    - gap_type: what's missing
    - question: natural question to ask user
    - confidence: 0-1

    If no gaps, return empty list.
    """

    async def detect_gaps(self, user_input: str, context: Dict) -> List[Gap]:
        # Call LLM with gap detection prompt
        # Parse structured response
        # Return Gap objects
```

**Acceptance Criteria:**

- Gap detection uses LLM reasoning, not regex patterns
- LLM generates natural clarification questions
- Gaps stored in `clarifications` section
- FSM enters CLARIFYING state when gaps detected

---

### MILESTONE 8: Sub-Agent Architecture with Delta Bus

**Epic 8.1: Base Sub-Agent Framework**

| Issue | Task | Files Changed | Est Time |
|-------|------|---------------|----------|
| 8.1.1 | Create BaseSubAgent class | agents/base.py | 45 min |
| 8.1.2 | Implement READ-ONLY SessionState access | agents/base.py | 30 min |
| 8.1.3 | Create sub-agent LLM context (separate from Concierge) | agents/base.py | 30 min |
| 8.1.4 | Define agent result message format | agents/base.py | 20 min |

**Epic 8.2: SearchAgent Implementation**

| Issue | Task | Files Changed | Est Time |
|-------|------|---------------|----------|
| 8.2.1 | Create SearchAgent class | agents/search_agent.py | 45 min |
| 8.2.2 | SearchAgent system prompt | agents/search_agent.py | 20 min |
| 8.2.3 | Wire to search tools (accommodations, restaurants, activities) | agents/search_agent.py | 30 min |
| 8.2.4 | Return results via Delta bus | agents/search_agent.py | 20 min |

**Epic 8.3: BookingAgent Implementation**

| Issue | Task | Files Changed | Est Time |
|-------|------|---------------|----------|
| 8.3.1 | Create BookingAgent class | agents/booking_agent.py | 45 min |
| 8.3.2 | BookingAgent system prompt | agents/booking_agent.py | 20 min |
| 8.3.3 | Wire to booking tools | agents/booking_agent.py | 30 min |
| 8.3.4 | Return confirmations via Delta bus | agents/booking_agent.py | 20 min |

**Epic 8.4: Delta Bus Implementation**

| Issue | Task | Files Changed | Est Time |
|-------|------|---------------|----------|
| 8.4.1 | Create DeltaBus class | bus/delta_bus.py | 45 min |
| 8.4.2 | Message format: AgentResult | bus/delta_bus.py | 20 min |
| 8.4.3 | Subscribe/publish pattern | bus/delta_bus.py | 30 min |
| 8.4.4 | Wire Concierge as subscriber | runner.py | 20 min |
| 8.4.5 | Wire sub-agents as publishers | agents/*.py | 20 min |

**Sub-Agent Architecture:**

```
Concierge (LLM, WRITE access)
    │
    ├── spawn_search_agent(type="accommodation", params={...})
    │       │
    │       v
    │   SearchAgent (LLM, READ-ONLY access)
    │       │
    │       └── executes search_accommodations tool
    │       │
    │       └── publishes result to Delta Bus
    │               │
    │               v
    └── receives AgentResult via Delta Bus subscription
    │
    └── integrates result into response to user
```

**Acceptance Criteria:**

- SearchAgent and BookingAgent have own LLM contexts
- Sub-agents can ONLY read SessionState (no writes)
- Results flow through Delta bus
- Concierge receives and integrates sub-agent results

---

### MILESTONE 9: Scoreboard + Narrative Tracking

**Epic 9.1: Scoreboard Implementation**

| Issue | Task | Files Changed | Est Time |
|-------|------|---------------|----------|
| 9.1.1 | Define scoreboard schema | bridge.py | 20 min |
| 9.1.2 | Track current referents (Mike, Emma, trip, etc.) | runner.py | 30 min |
| 9.1.3 | Track QUD (Question Under Discussion) | runner.py | 30 min |
| 9.1.4 | Track salience scores | runner.py | 30 min |
| 9.1.5 | Update scoreboard after each turn | runner.py | 20 min |
| 9.1.6 | Inject scoreboard into LLM context | runner.py | 20 min |

**Scoreboard Schema:**

```python
scoreboard = {
    "referents": {
        "Mike": {"type": "person", "salience": 0.9, "last_mention": 5},
        "trip": {"type": "plan", "salience": 0.95, "last_mention": 6},
        "Vineyard Inn": {"type": "place", "salience": 0.8, "last_mention": 8},
    },
    "qud": "What accommodations should we book?",
    "topic": "accommodation_booking",
    "phase": "planning",
}
```

**Epic 9.2: Narrative Tracking**

| Issue | Task | Files Changed | Est Time |
|-------|------|---------------|----------|
| 9.2.1 | Define narrative phases | concierge/states.py | 20 min |
| 9.2.2 | Track narrative thread | runner.py | 30 min |
| 9.2.3 | Detect phase transitions (setup → booking → crisis → resolution) | runner.py | 30 min |
| 9.2.4 | Store in narrative_active section | bridge.py | 20 min |
| 9.2.5 | Inject phase info into LLM context | runner.py | 15 min |

**Narrative Phases:**

```python
class NarrativePhase(Enum):
    SETUP = "setup"           # Learning context (Turns 1-8)
    BOOKING = "booking"       # Making reservations (Turns 9-14)
    EXECUTION = "execution"   # Background tasks (Turns 15-19)
    CRISIS = "crisis"         # Crash/restore (Turn 20)
    RECOVERY = "recovery"     # Post-crash (Turns 21-25)
    RESOLUTION = "resolution" # Wrap up (Turns 26-30)
```

**Acceptance Criteria:**

- Scoreboard tracks all mentioned entities with salience
- QUD updated after each turn
- Narrative phase detected and stored
- LLM context includes "CURRENT TOPIC: {scoreboard.topic}" and "PHASE: {narrative.phase}"

---

### MILESTONE 10: TwoWayConcierge + Background Integration

**Epic 10.1: Wire TwoWayConcierge**

| Issue | Task | Files Changed | Est Time |
|-------|------|---------------|----------|
| 10.1.1 | Replace direct FSM usage with TwoWayConcierge wrapper | runner.py | 30 min |
| 10.1.2 | Initialize TaskQueue | runner.py | 15 min |
| 10.1.3 | Initialize NotificationQueue | runner.py | 15 min |
| 10.1.4 | Wire notification callbacks to display | runner.py | 30 min |
| 10.1.5 | Test background task creation | - | 20 min |

**Epic 10.2: Weather Monitor Integration**

| Issue | Task | Files Changed | Est Time |
|-------|------|---------------|----------|
| 10.2.1 | Create weather monitor handler | background/monitors.py | 30 min |
| 10.2.2 | Register in TaskRegistry | background/registry.py | 15 min |
| 10.2.3 | Fire notification at Turn 24 | runner.py | 20 min |
| 10.2.4 | Display weather alert with suggested action | display.py | 20 min |
| 10.2.5 | Concierge receives via notification queue | runner.py | 20 min |

**Acceptance Criteria:**

- TwoWayConcierge wraps FSM and handles background tasks
- Weather monitor starts at Turn 15
- Weather alert fires at Turn 24
- Concierge integrates alert into response naturally

---

## Implementation Order

**Day 1 (4-6 hours):**

1. MILESTONE 5: Wire ConciergeFSM (2 hours)
2. MILESTONE 6: All 12 sections (2-3 hours)
3. Test full 30-turn demo with FSM

**Day 2 (4-6 hours):**

1. MILESTONE 7: LLM-driven gap detection (2 hours)
2. MILESTONE 8: Sub-agents + Delta bus (2-3 hours)
3. Test sub-agent spawning

**Day 3 (if needed - 2-4 hours):**

1. MILESTONE 9: Scoreboard + narrative (1.5 hours)
2. MILESTONE 10: TwoWayConcierge + background (1.5 hours)
3. Full integration test

---

## Files Changed Summary

| File | Changes |
|------|---------|
| `runner.py` | Replace LLM calls with FSM, add context injection, add sub-agent spawning |
| `bridge.py` | Expand build_llm_context() for all 12 sections |
| `concierge/fsm.py` | Wire LLMGapDetector, add sub-agent hooks |
| `concierge/llm_gap_detector.py` | NEW - LLM-driven gap detection |
| `agents/base.py` | NEW - BaseSubAgent with READ-ONLY access |
| `agents/search_agent.py` | NEW - SearchAgent |
| `agents/booking_agent.py` | NEW - BookingAgent |
| `bus/delta_bus.py` | NEW - Message passing |
| `display.py` | Add FSM state display, add sub-agent display |

---

## Expected Outcome

After implementation:

1. **Concierge Response Quality:**
   - Short when appropriate (greetings, confirmations)
   - Long when needed (explanations, lists)
   - Context-aware (references stored beliefs, persona)
   - Natural clarification questions (LLM-generated)

2. **Architecture Compliance:**
   - FSM orchestrates conversation flow
   - All 12 SessionState sections populated and used
   - Sub-agents have READ-ONLY access
   - Delta bus coordinates agent results
   - Background tasks run independently

3. **Demo Features:**
   - Real intent classification visible
   - Real gap detection (LLM-driven)
   - Real sub-agent spawning
   - Real background notifications
   - Full crash/restore with complete state

---

## Verification Checklist

After each milestone, verify:

- [ ] No regressions in existing 30-turn demo
- [ ] FSM state transitions logged
- [ ] All 12 sections show data in bridge.get_snapshot()
- [ ] LLM context includes injected state
- [ ] Sub-agent results flow through Delta bus
- [ ] Crash/restore preserves all state
- [ ] Memory stays under 96KB cap

---

*Plan Created: 2026-02-04*
*Based on: end_to_end_demo_story.md, sessionstate_internal.mmd*
*Components Audit: All existing components identified for reuse*
