# FamilyOS End-to-End Demo: "The Anniversary Weekend"

## Document Purpose

This document defines the complete storyline, technical requirements, and development plan for the FamilyOS 30-turn demonstration. The demo showcases the full capability of the K1 Concierge system with real LLM calls, real tool execution, and production-grade architecture.

---

## CRITICAL: Current State vs Target State

### Current State: FAKE THEATER (Must Be Replaced)

The current `anniversary_demo/runner.py` is **100% hardcoded simulation**:

- NO real LLM calls - responses are templates
- NO real tool execution - just prints
- NO real SessionState - just mock counters
- NO real ConciergeFSM - just display logic
- Concierge has NO agency - everything scripted

### Target State: REAL LLM-DRIVEN ARCHITECTURE

**The Concierge MUST use real LLMs for everything:**

1. **LLM Generates Responses** - Not templates
2. **LLM Makes Tool Calls** - Via function calling, validated by schema
3. **LLM Detects Gaps** - Analyzes required params, asks clarification
4. **LLM Has Write Access** - Concierge writes to SessionState, sub-agents read
5. **LLM Spawns Sub-Agents** - For complex tasks (search, booking)
6. **Delta Bus Coordination** - Sub-agents send results back via message bus

### Architecture Reference

The REAL implementation already exists:

- `walkthrough_demo.py` - Uses real LLM via `SimpleLLMClient`
- `bridge.py` - Real `SessionLLMBridge` with `execute_tool_calls()`
- `concierge/fsm.py` - Real FSM with `IntentClassifier`, `GapDetector`
- `llm_client.py` - Real Google AI with function calling

**WE MUST WIRE ANNIVERSARY_DEMO TO USE THESE REAL COMPONENTS**

---

## Part 1: The Story

### Hook

A family planning Dad's surprise 50th birthday weekend. Mom coordinates everything through FamilyOS - things go wrong (crash!), but the AI saves the day. Demonstrates reliability, intelligence, and proactive assistance.

### Cast

| Character | Role | Interaction |
|-----------|------|-------------|
| Sarah (Mom) | Primary user | All 30 turns |
| Mike (Dad) | Birthday boy | Does not interact (surprise!) |
| Emma | Daughter, 16 | Receives messages from system |
| Jake | Son, 12 | Mentioned, needs supervision |
| Concierge | FamilyOS AI | Responds, acts, monitors |

### Emotional Arc

```
Hope          Complexity        CRISIS         Recovery        Joy
  |               |                |               |            |
  v               v                v               v            v
"Let's plan"  "Book that B&B"  *CRASH*     "You remembered!"  "Best birthday!"
  (1-8)         (9-14)         (15-20)        (21-25)         (26-30)
```

---

## Part 2: The 30-Turn Script

### ACT 1: SETUP & LEARNING (Turns 1-8)

**Features Demonstrated:** SessionState learning, intent classification, persona building, tool calls

---

#### Turn 1

**User Input:**

```
Hey, I need help planning a surprise for Mike's 50th birthday next Saturday
```

**System Behavior:**

- Intent: REQUEST (complexity: MEDIUM)
- SessionState: Create new session, record context
- No tool calls yet

**Expected Response Theme:**
Warm acknowledgment, ask about type of celebration

---

#### Turn 2

**User Input:**

```
Weekend getaway. He's been stressed at work, needs to relax. Maybe wine country?
```

**System Behavior:**

- Tool call: `update_persona(trait="relaxation_preference", value="high")`
- Tool call: `add_belief(subject="Mike", predicate="needs", object="relaxation", category="wellness")`
- Tool call: `add_belief(subject="user", predicate="interested_in", object="wine_country", category="travel")`
- SessionState: Record preferences

**Expected Response Theme:**
Validate the choice, ask Napa vs Sonoma, ask about kids

---

#### Turn 3

**User Input:**

```
Just us two. Emma can watch Jake for the weekend, she's 16 now
```

**System Behavior:**

- Tool call: `add_belief(subject="Emma", predicate="age", object="16", category="family")`
- Tool call: `add_belief(subject="Jake", predicate="has_sibling", object="Emma", category="family")`
- Tool call: `add_belief(subject="trip", predicate="party_size", object="2", category="travel")`
- SessionState: Family structure learned

**Expected Response Theme:**
Acknowledge romantic getaway, ask about budget

---

#### Turn 4

**User Input:**

```
Around $1500 total, maybe a bit more for something special
```

**System Behavior:**

- Tool call: `add_belief(subject="trip", predicate="budget", object="$1500-2000", category="travel")`
- Tool call: `update_persona(trait="budget_flexibility", value="moderate")`

**Expected Response Theme:**
Confirm budget, offer to find options

---

#### Turn 5

**User Input:**

```
Yes, find me some options. Oh, and Mike has a mild shellfish allergy, so keep that in mind for restaurants
```

**System Behavior:**

- Tool call: `add_belief(subject="Mike", predicate="allergy", object="shellfish", category="health", confidence=1.0)`
- SessionState: Critical health info stored with high confidence

**Expected Response Theme:**
Acknowledge allergy (important!), start searching

---

#### Turn 6

**User Input:**

```
Sonoma sounds better than Napa, more relaxed vibe
```

**System Behavior:**

- Tool call: `add_belief(subject="trip", predicate="destination", object="Sonoma", category="travel")`
- Tool call: `update_persona(trait="vibe_preference", value="relaxed_over_busy")`

**Expected Response Theme:**
Confirm Sonoma, describe search progress

---

#### Turn 7

**User Input:**

```
What did you find?
```

**System Behavior:**

- Tool call: `search_accommodations(location="Sonoma", dates="next_saturday+1", budget_per_night=500, party_size=2)`
- Present 2-3 options with details

**Expected Response Theme:**
List options with prices, ratings, highlights

---

#### Turn 8

**User Input:**

```
The Vineyard Inn sounds perfect. What's included?
```

**System Behavior:**

- Tool call: `get_accommodation_details(name="Vineyard Inn", location="Sonoma")`
- Detailed info retrieval

**Expected Response Theme:**
Detailed breakdown, ask if user wants to book

---

### ACT 2: LLM-DRIVEN GAP DETECTION (Turns 9-14)

**Features Demonstrated:** LLM attempts tool call, detects missing required params, asks clarification, retries

---

#### Turn 9

**User Input:**

```
Book it! Two nights, Saturday and Sunday
```

**System Behavior:**

- Tool call: `book_accommodation(name="Vineyard Inn", location="Sonoma", check_in="next_saturday", nights=2, guests=2)`
- Booking succeeds

**Expected Response Theme:**
Confirmation with details, ask what's next

---

#### Turn 10

**User Input:**

```
Now I need to arrange something special for his actual birthday dinner
```

**System Behavior:**

- LLM attempts: `book_restaurant(occasion="birthday", ...)`
- **GAP DETECTED:** Missing required params (date, time, cuisine, party_size)
- LLM generates clarification questions

**Expected Response Theme:**
"I'd love to book a birthday dinner! A few questions: Which evening - Saturday or Sunday? Any cuisine preference? And what time works best?"

---

#### Turn 11

**User Input:**

```
Saturday evening, around 7pm. He loves Italian food
```

**System Behavior:**

- Tool call: `search_restaurants(location="Sonoma", cuisine="Italian", date="next_saturday", time="19:00", party_size=2, avoid_ingredients=["shellfish"])`
- Note: System remembers shellfish allergy from Turn 5!

**Expected Response Theme:**
List Italian restaurants, note that shellfish-safe options prioritized

---

#### Turn 12

**User Input:**

```
Della Santina's looks great. Can you check if they do anything special for birthdays?
```

**System Behavior:**

- Tool call: `get_restaurant_details(name="Della Santina's", query="birthday_specials")`

**Expected Response Theme:**
Details about birthday offerings

---

#### Turn 13

**User Input:**

```
Perfect, book it. Oh wait - can you also add a note about the shellfish allergy?
```

**System Behavior:**

- Tool call: `book_restaurant(name="Della Santina's", date="next_saturday", time="19:00", party_size=2, special_requests=["50th birthday celebration", "shellfish allergy - IMPORTANT"])`

**Expected Response Theme:**
Confirmation with allergy note highlighted

---

#### Turn 14

**User Input:**

```
Great. What about transportation? Should we drive or is there a better option?
```

**System Behavior:**

- LLM attempts: `suggest_transportation(...)`
- **GAP DETECTED:** Missing origin, preferred travel style
- Clarification generated

**Expected Response Theme:**
"Are you driving from home, or flying in? And does Mike prefer scenic drives or quick routes?"

---

### ACT 3: BACKGROUND TASKS + CRASH (Turns 15-20)

**Features Demonstrated:** Background task creation, concurrent monitoring, CRASH, RESTORE with full memory

---

#### Turn 15

**User Input:**

```
We'll drive from San Francisco. He likes scenic routes. Oh, and can you keep an eye on the weather? I don't want rain to ruin the weekend
```

**System Behavior:**

- Tool call: `plan_route(origin="San Francisco", destination="Sonoma", preference="scenic")`
- **BACKGROUND TASK:** `start_background_monitor(type="weather", location="Sonoma", dates=["next_saturday", "next_sunday"], alert_conditions=["rain", "storm"])`
- Concurrent task registered

**Expected Response Theme:**
Route suggestion + confirmation that weather is being monitored

---

#### Turn 16

**User Input:**

```
Perfect route! How long is the drive?
```

**System Behavior:**

- Retrieve cached route info
- Background task continues silently

**Expected Response Theme:**
Drive time, scenic highlights along the way

---

#### Turn 17

**User Input:**

```
One more thing - I need to brief Emma on watching Jake. Can you remind me to do that on Friday?
```

**System Behavior:**

- Tool call: `schedule_reminder(recipient="user", message="Brief Emma on Jake-sitting instructions", datetime="friday_evening")`
- Reminder scheduled

**Expected Response Theme:**
Confirmation of reminder

---

#### Turn 18

**User Input:**

```
Actually, can FamilyOS just send Emma the instructions directly? She's in our family group
```

**System Behavior:**

- LLM attempts: `send_family_message(to="Emma", ...)`
- **GAP DETECTED:** Missing actual instructions content
- Clarification needed

**Expected Response Theme:**
"I can send Emma the weekend instructions! What should I include? Emergency contacts, Jake's schedule, house rules?"

---

#### Turn 19

**User Input:**

```
Yes all of that. Jake has soccer practice Saturday at 9am, make sure she knows. And give her our hotel contact info in case of emergenc--
```

**System Behavior:**

- Mid-sentence capture
- Tool call starts: `compose_family_message(...)`

---

#### Turn 20 - THE CRASH

**System Event:**

```
[SYSTEM CRASH SIMULATION]

*Screen goes black*
*3 second pause*
*System restarts*
```

**System Behavior:**

- Session terminated unexpectedly
- Restore from last checkpoint
- Detect incomplete turn
- Resume context

**Expected Response (POST-RESTORE):**
"Welcome back, Sarah! I see we were in the middle of preparing instructions for Emma about watching Jake this weekend. You mentioned Jake's soccer at 9am Saturday and emergency contacts. Should I complete that message to Emma?"

**Demonstrated:**

- Full session restored from SQLite
- Incomplete turn detected
- Context maintained: trip details, bookings, family info, allergies - EVERYTHING

---

### ACT 4: PROACTIVE CONCIERGE (Turns 21-25)

**Features Demonstrated:** Background task notification, proactive suggestions, 2-way concurrent operation

---

#### Turn 21

**User Input:**

```
Yes! Finish that message to Emma. Include everything she needs
```

**System Behavior:**

- Tool call: `send_family_message(to="Emma", subject="Weekend Instructions - Jake", content={emergency_contacts, jake_schedule, hotel_info, house_rules})`
- Message compiled from all learned context

**Expected Response Theme:**
Confirmation of message sent, summary of contents

---

#### Turn 22

**User Input:**

```
Thanks. Let me think... is there anything else I'm forgetting?
```

**System Behavior:**

- LLM reviews entire session context
- Proactive gap analysis

**Expected Response Theme:**
Checklist: "Based on our planning: Vineyard Inn, Della Santina's, scenic route, Emma briefed, weather monitored. You might also consider: gift for Mike? Cover story for the surprise? Sunday activities?"

---

#### Turn 23

**User Input:**

```
Oh good point about Sunday! What's there to do near the inn?
```

**System Behavior:**

- Tool call: `search_activities(location="Vineyard Inn, Sonoma", date="next_sunday", category="relaxation")`

**Expected Response Theme:**
List of activities: spa, wine tasting, walking trails

---

#### Turn 24 - BACKGROUND ALERT

**System Event:**

```
[BACKGROUND TASK TRIGGER]
Weather monitor detects forecast change
```

**System Behavior:**

- Background task fires notification
- Interrupts conversation gracefully

**Expected Response:**
"Quick heads up, Sarah - I've been watching the Sonoma weather. Saturday looks beautiful (72F, sunny), but there's now a 60% chance of rain Sunday afternoon. You might want to plan indoor activities for Sunday. The inn's spa does couples massages - want me to look into that?"

**Demonstrated:**

- Background task running independently
- Proactive notification
- Actionable suggestion based on context

---

#### Turn 25

**User Input:**

```
Yes, book a couples massage for Sunday! Late morning so we can check out after
```

**System Behavior:**

- Tool call: `book_spa_service(location="Vineyard Inn", service="couples_massage", date="next_sunday", time="11:00", guests=2)`

**Expected Response Theme:**
Confirmation, note about checkout timing

---

### ACT 5: FAMILY COMPLEXITY + RESOLUTION (Turns 26-30)

**Features Demonstrated:** Multi-user family awareness, scheduled check-ins, integration summary, emotional payoff

---

#### Turn 26

**User Input:**

```
You mentioned a cover story - I told Mike I have a work conference in Napa. Should I add any details to make it believable?
```

**System Behavior:**

- LLM reasoning about deception plausibility
- Proactive suggestion

**Expected Response Theme:**
Suggest details: conference name, schedule, why he can't come. Offer to create calendar event as alibi.

---

#### Turn 27

**User Input:**

```
Good idea. Create a fake calendar event for "Tech Summit Napa" from Friday to Sunday. Just in case he looks at my calendar
```

**System Behavior:**

- Tool call: `create_calendar_event(title="Tech Summit Napa", start="friday", end="sunday", visibility="private", notes="COVER STORY - do not share")`

**Expected Response Theme:**
Confirmation, note about privacy settings

---

#### Turn 28

**User Input:**

```
Can FamilyOS check in on Emma Saturday afternoon? Just to make sure she and Jake are doing okay?
```

**System Behavior:**

- Tool call: `schedule_family_checkin(target="Emma", datetime="saturday_14:00", message="Hi Emma! Just checking in - how's everything going with Jake? Need anything?")`
- Tool call: `schedule_notification(recipient="user", trigger="emma_response", message="Emma responded to check-in")`

**Expected Response Theme:**
Confirmation of scheduled check-in, note that user will be notified of response

---

#### Turn 29

**User Input:**

```
Perfect. I think we're all set. Can you give me a complete summary of everything?
```

**System Behavior:**

- Compile full session summary
- Tool call: `generate_trip_summary(session_id=current)`

**Expected Response Theme:**
Complete formatted summary:

- Accommodation: Vineyard Inn, 2 nights
- Dinner: Della Santina's, Saturday 7pm (shellfish allergy noted)
- Spa: Couples massage, Sunday 11am
- Transportation: Scenic route from SF, ~1.5 hours
- Weather: Saturday sunny, Sunday rain afternoon
- Family: Emma briefed, check-in scheduled Saturday 2pm
- Cover: Tech Summit Napa on calendar
- Budget tracking: ~$X of $1500-2000 spent

---

#### Turn 30

**User Input:**

```
This is incredible. Mike is going to be so surprised. Thank you!
```

**System Behavior:**

- Emotional recognition
- Tool call: `update_emotion(state="gratitude", confidence=0.95)`
- Session summary saved

**Expected Response Theme:**
Warm closing: "You've put together an amazing surprise! I'll keep monitoring the weather and remind you Friday about last-minute prep. Have a wonderful weekend celebrating Mike's 50th! He's lucky to have someone who plans like this."

---

## Part 3: Technical Requirements

### CRITICAL ARCHITECTURE CHANGE: LLM-First Design

**The Concierge is the brain. The LLM IS the Concierge.**

```
+-------------------------------------------------------------------------+
|                           USER INPUT                                     |
+-------------------------------------------------------------------------+
                                   |
                                   v
+-------------------------------------------------------------------------+
|                     CONCIERGE (LLM with Write Access)                    |
|  +-------------------------------------------------------------------+  |
|  |  System Prompt:                                                    |  |
|  |  - You ARE the FamilyOS Concierge                                 |  |
|  |  - You have WRITE access to SessionState via tools                |  |
|  |  - You can SPAWN sub-agents for complex tasks                     |  |
|  |  - You REMEMBER everything via SessionState persistence           |  |
|  |  - You DETECT gaps when info is missing and ASK                   |  |
|  +-------------------------------------------------------------------+  |
|                                                                          |
|  Tools Available (Write Access):                                         |
|  - add_belief(subject, predicate, object, confidence)                   |
|  - update_persona(trait, value)                                          |
|  - update_emotion(state, confidence)                                     |
|  - spawn_search_agent(type, params) -> returns results                  |
|  - spawn_booking_agent(service, params) -> returns confirmation         |
|  - send_family_message(to, subject, body)                               |
|  - schedule_reminder(when, message)                                      |
|  - start_background_monitor(type, target, conditions)                   |
|  - create_calendar_event(title, start, end, visibility)                 |
+-------------------------------------------------------------------------+
                                   |
                    +--------------+--------------+
                    |              |              |
                    v              v              v
+----------------------+ +------------------+ +----------------------+
|   SessionState       | |   Sub-Agents     | |  Background Tasks    |
|   (Concierge WRITES) | |   (READ-ONLY)    | |  (Async monitors)    |
|                      | |                  | |                      |
| - history_active     | | SearchAgent:     | | WeatherMonitor:      |
| - beliefs_active     | |  - search hotels | |  - polls forecast    |
| - persona            | |  - search food   | |  - emits alert       |
| - affective_now      | |  - search spa    | |                      |
| - telemetry          | |                  | | PriceMonitor:        |
|                      | | BookingAgent:    | |  - watches prices    |
| CHECKPOINT --------> | |  - book hotel    | |  - emits alert       |
|   to SQLite          | |  - book dinner   | |                      |
+----------------------+ |  - book spa      | +----------------------+
                         +------------------+
                                   |
                                   v
                    +------------------------------+
                    |        DELTA BUS             |
                    |  Sub-agent -> Concierge msgs |
                    |  Background -> Concierge msgs|
                    |  Concierge gets ALL results  |
                    +------------------------------+
```

### Access Control Model

| Component | SessionState Access | Can Call LLM | Notes |
|-----------|---------------------|--------------|-------|
| Concierge | **READ + WRITE** | YES | The brain, full control |
| SearchAgent | READ only | YES (own context) | Returns results to Concierge |
| BookingAgent | READ only | YES (own context) | Returns confirmation to Concierge |
| BackgroundTask | READ only | NO | Just monitors, emits events |
| User | N/A | N/A | Interacts via Concierge only |

### What Is Real (Production-Grade)

| Component | Implementation | Notes |
|-----------|----------------|-------|
| LLM Calls | Real Gemini API | Function calling enabled |
| Tool Execution | Real function invocation | Validated against schemas |
| SessionState | Real SQLite persistence | FlatBuffers serialization |
| Checkpoint/Restore | Real serialization | Survives crash |
| ConciergeFSM | Real state machine | LISTENING->ACKING->DISPATCHING->DELIVERING |
| Gap Detection | **LLM-driven** | LLM analyzes params, generates question |
| Sub-Agents | Real LLM calls | Separate context, results via bus |

### What Is Simulated (Demo Only)

| Component | Simulation | Notes |
|-----------|------------|-------|
| User Input | Static scripted messages | Same user input each run |
| External APIs | Mock responses | Hotels/restaurants don't exist |
| Crash Event | Triggered at Turn 20 | `os.kill()` or similar |
| Weather Data | Scripted change at Turn 24 | Not real forecast |

---

## Part 4: Development Plan - REVISED

### ✅ COMPLETED Milestone 0: Kill The Theater

**Goal:** Remove all fake/hardcoded code from anniversary_demo
**Duration:** 1 day
**Status:** COMPLETE - Implemented 2024

#### Epic 0.1: Gut The Runner ✅

| Issue | Description | Status |
|-------|-------------|--------|
| 0.1.1 | Remove all mock response generation | ✅ Removed `_generate_response()` |
| 0.1.2 | Remove all fake tool simulation | ✅ Removed `_simulate_tool_call()` |
| 0.1.3 | Remove fake state tracking | ✅ Removed mock dicts, uses real metrics |
| 0.1.4 | Wire to real SessionLLMBridge | ✅ Imports and uses `bridge.py` |
| 0.1.5 | Wire to real ConciergeFSM | ✅ Uses FSM via bridge integration |
| 0.1.6 | Wire to real SimpleLLMClient | ✅ Imports and uses `llm_client.py` |

**Implementation Notes:**
- New `runner.py` uses `SessionLLMBridge` for real persistence
- Uses `SimpleLLMClient.complete_with_tools()` for real LLM calls
- Uses `ToolRegistry.get_all_schemas_for_llm()` for function calling
- System prompt defined: `CONCIERGE_SYSTEM_PROMPT` with full context
- 73 tests passing

### Milestone 1: Real Concierge Integration

**Goal:** Make Concierge use real LLM with function calling
**Duration:** 2 days

#### Epic 1.1: LLM-Driven Concierge Core

| Issue | Description | Acceptance Criteria |
|-------|-------------|---------------------|
| 1.1.1 | Create Concierge system prompt | Instructs LLM it IS the concierge with write access |
| 1.1.2 | Define tool schemas for ALL tools | 18+ tools with full JSON schemas |
| 1.1.3 | Implement tool execution layer | Real function calls, not mocks |
| 1.1.4 | SessionState write integration | Tools actually write to SessionState |
| 1.1.5 | Gap detection via LLM | LLM sees missing params, generates clarification |
| 1.1.6 | Test with 5 real turns | LLM responds naturally, uses tools correctly |

#### Epic 1.2: Sub-Agent Architecture

| Issue | Description | Acceptance Criteria |
|-------|-------------|---------------------|
| 1.2.1 | Define sub-agent spawn protocol | Concierge calls `spawn_agent(type, params)` |
| 1.2.2 | SearchAgent implementation | READ-ONLY SessionState, returns results |
| 1.2.3 | BookingAgent implementation | READ-ONLY SessionState, confirms booking |
| 1.2.4 | Delta bus message passing | Sub-agents send results to Concierge |
| 1.2.5 | Concierge receives and integrates | Concierge gets results, continues conversation |

### Milestone 2: Tool Implementation

**Goal:** Create all 18+ tools needed for the demo scenario
**Duration:** 2 days

#### Epic 2.1: SessionState Write Tools (Concierge Only)

| Issue | Description | Acceptance Criteria |
|-------|-------------|---------------------|
| 2.1.1 | `add_belief` tool | Writes to beliefs_active section |
| 2.1.2 | `update_persona` tool | Writes to persona section |
| 2.1.3 | `update_emotion` tool | Writes to affective_now section |

#### Epic 2.2: Sub-Agent Spawn Tools

| Issue | Description | Acceptance Criteria |
|-------|-------------|---------------------|
| 2.2.1 | `search_accommodations` tool | Spawns SearchAgent, returns mock results |
| 2.2.2 | `search_restaurants` tool | Spawns SearchAgent, returns mock results |
| 2.2.3 | `search_activities` tool | Spawns SearchAgent, returns mock results |
| 2.2.4 | `book_accommodation` tool | Spawns BookingAgent, returns confirmation |
| 2.2.5 | `book_restaurant` tool | Spawns BookingAgent, returns confirmation |
| 2.2.6 | `book_spa_service` tool | Spawns BookingAgent, returns confirmation |
| 2.2.7 | `get_accommodation_details` tool | Returns detailed mock info |
| 2.2.8 | `get_restaurant_details` tool | Returns detailed mock info |
| 2.2.9 | `plan_route` tool | Returns mock route with scenic option |

#### Epic 2.3: Family & Calendar Tools

| Issue | Description | Acceptance Criteria |
|-------|-------------|---------------------|
| 2.3.1 | `send_family_message` tool | Logs message, updates SessionState |
| 2.3.2 | `schedule_family_checkin` tool | Schedules background check-in |
| 2.3.3 | `create_calendar_event` tool | Logs event, updates SessionState |
| 2.3.4 | `schedule_reminder` tool | Schedules reminder |
| 2.3.5 | `generate_trip_summary` tool | Compiles from SessionState |

#### Epic 2.4: Background Monitor Tools

| Issue | Description | Acceptance Criteria |
|-------|-------------|---------------------|
| 2.4.1 | `start_background_monitor` tool | Registers async monitor |
| 2.4.2 | `stop_background_monitor` tool | Cancels monitor |
| 2.4.3 | Weather monitor impl | Triggers alert at Turn 24 |

### Milestone 3: Demo Runner Integration

**Goal:** Wire the 30-turn script to real components
**Duration:** 2 days

#### Epic 3.1: Script Engine with Real LLM

| Issue | Description | Acceptance Criteria |
|-------|-------------|---------------------|
| 3.1.1 | Load turn script with user inputs | Script provides user message only |
| 3.1.2 | Send to real ConciergeFSM | FSM processes through LLM |
| 3.1.3 | Display real LLM response | Whatever LLM generates |
| 3.1.4 | Display real tool calls | From LLM function calling |
| 3.1.5 | Track real SessionState changes | From bridge.get_snapshot() |
| 3.1.6 | Real latency metrics | Actual LLM call times |

#### Epic 3.2: Event Triggers

| Issue | Description | Acceptance Criteria |
|-------|-------------|---------------------|
| 3.2.1 | Implement real crash | `os.kill()` at Turn 19/20 boundary |
| 3.2.2 | Real restore flow | SessionLLMBridge restores from checkpoint |
| 3.2.3 | Weather alert via Delta bus | Background task emits, Concierge receives |

#### Epic 3.3: Metrics & Summary

| Issue | Description | Acceptance Criteria |
|-------|-------------|---------------------|
| 3.3.1 | Real latency per turn | Actual P50/P95/P99 |
| 3.3.2 | Real tool call count | From actual LLM responses |
| 3.3.3 | Real SessionState growth | From bridge.get_snapshot() |
| 3.3.4 | K1 coverage report | Based on actual features used |

### Milestone 4: Polish & Testing

**Goal:** Make demo reliable and impressive
**Duration:** 1 day

#### Epic 4.1: Reliability

| Issue | Description | Acceptance Criteria |
|-------|-------------|---------------------|
| 4.1.1 | Handle LLM errors gracefully | Retry logic, fallback responses |
| 4.1.2 | Validate all 30 turns | Each turn produces expected behavior |
| 4.1.3 | Test crash/restore 5 times | Restore works reliably every time |
| 4.1.4 | Performance optimization | No turn takes >5 seconds |

#### Epic 4.2: Visual Polish

| Issue | Description | Acceptance Criteria |
|-------|-------------|---------------------|
| 4.2.1 | ASCII art for key moments | Crash screen, restore animation |
| 4.2.2 | Progress indicator | "Turn X of 30" with progress bar |
| 4.2.3 | Section dividers | Clear visual separation of Acts |
| 4.2.4 | Color coding | User=green, AI=blue, System=yellow, Alert=red |

#### Epic 4.3: Documentation

| Issue | Description | Acceptance Criteria |
|-------|-------------|---------------------|
| 4.3.1 | Demo run instructions | README with setup and run commands |
| 4.3.2 | Architecture diagram | Visual showing all components |
| 4.3.3 | Feature checklist | What's demonstrated at each turn |

---

## Part 5: File Structure - REVISED

```
poc/session_state_demo/
|
|-- bridge.py                    # KEEP - Real SessionLLMBridge
|-- llm_client.py               # KEEP - Real SimpleLLMClient
|-- session_state.py            # KEEP - Real SessionState
|-- config.py                   # KEEP - Configuration
|-- tools.py                    # EXISTING - Basic tools
|
|-- concierge/                  # KEEP - Real FSM (USE THIS!)
|   |-- __init__.py
|   |-- fsm.py                  # Real state machine
|   |-- classifier.py           # Intent classification
|   |-- gap_detector.py         # UPGRADE to LLM-driven
|   |-- router.py               # Complexity routing
|   |-- states.py               # State definitions
|
|-- walkthrough_demo.py         # REFERENCE - Shows correct real LLM pattern
|
|-- demo_docs/
|   |-- end_to_end_demo_story.md      # This document
|
|-- anniversary_demo/           # REWRITE - Wire to real components
|   |-- __init__.py
|   |-- script.py               # User inputs only (no fake responses)
|   |-- runner.py               # REWRITE - Use real ConciergeFSM + Bridge
|   |-- display.py              # KEEP - Visual output (works well)
|   |
|   |-- tools/                  # EXPAND - Real tool implementations
|   |   |-- __init__.py
|   |   |-- registry.py         # Tool schema registry (exists, expand)
|   |   |-- session_tools.py    # add_belief, update_persona (exists)
|   |   |-- travel_tools.py     # search_*, book_*, get_*_details
|   |   |-- family_tools.py     # send_message, schedule_checkin
|   |   |-- calendar_tools.py   # create_event, schedule_reminder
|   |   |-- monitor_tools.py    # start/stop_background_monitor
|   |
|   |-- agents/                 # NEW - Sub-agent implementations
|   |   |-- __init__.py
|   |   |-- base.py             # BaseSubAgent (READ-ONLY access)
|   |   |-- search_agent.py     # SearchAgent (own LLM context)
|   |   |-- booking_agent.py    # BookingAgent (own LLM context)
|   |
|   |-- background/             # EXPAND - Background task system
|       |-- __init__.py
|       |-- task_queue.py       # Async task management
|       |-- delta_bus.py        # NEW - Message passing to Concierge
|       |-- weather_monitor.py  # Weather simulation
|       |-- notifications.py    # Proactive notifications
```

---

## Part 6: What We MUST Do Next

### Immediate Actions (In Order)

1. **Study `walkthrough_demo.py` lines 450-550** - Shows real LLM integration
2. **Study `bridge.py` lines 170-300** - Shows real SessionState writes
3. **Study `concierge/fsm.py`** - Shows real state machine
4. **Gut `anniversary_demo/runner.py`** - Remove ALL fake code
5. **Wire runner.py to real components** - Import Bridge, FSM, LLMClient

### The Core Code Change

**BEFORE (Current Theater - MUST DELETE):**

```python
# anniversary_demo/runner.py - CURRENT FAKE CODE
class DemoRunner:
    def _generate_response(self, turn):
        return turn.response_theme  # HARDCODED TEMPLATE!

    def _simulate_tool_call(self, tool_name, turn):
        print_tool_call(tool_name, mock_args)  # JUST DISPLAY!

    async def _simulate_processing(self, turn):
        await asyncio.sleep(0.3)  # FAKE DELAY!
```

**AFTER (Real LLM - WHAT WE NEED):**

```python
# anniversary_demo/runner.py - REAL LLM INTEGRATION
from poc.session_state_demo.bridge import SessionLLMBridge
from poc.session_state_demo.concierge import ConciergeFSM
from poc.session_state_demo.llm_client import SimpleLLMClient
from poc.session_state_demo.config import get_config

class DemoRunner:
    def __init__(self):
        config = get_config()
        self.bridge = SessionLLMBridge(
            session_id=f"anniversary-demo-{int(time.time())}",
            db_path=str(config.db_path),
        )
        self.llm = SimpleLLMClient(
            api_key=config.google_api_key,
            model=config.google_model,
        )
        self.fsm = ConciergeFSM(
            bridge=self.bridge,
            llm_client=self.llm,
        )

    async def _execute_turn(self, user_input: str):
        # REAL - Let the Concierge FSM handle everything
        result = await self.fsm.process_input(user_input)

        # Display REAL tool calls from LLM
        for call in result.tool_calls:
            print_tool_call(call['name'], call['args'])

        # Display REAL response from LLM
        print_assistant_message(result.response)

        return result
```

### Success Criteria

- [ ] NO hardcoded responses - LLM generates everything
- [ ] NO fake tool calls - Real function calling + execution
- [ ] NO mock SessionState - Real persistence to SQLite
- [ ] LLM detects gaps naturally - Not scripted
- [ ] Concierge has WRITE access to SessionState
- [ ] Sub-agents have READ-ONLY access
- [ ] Delta bus passes messages
- [ ] Real checkpoint/restore works

---

## Part 7: Estimated Timeline - REVISED

| Milestone | Duration | Deliverable |
|-----------|----------|-------------|
| M0: Kill Theater | 1 day | Remove all fake code from runner.py |
| M1: Real Integration | 2 days | Wire to real Bridge + FSM + LLM |
| M2: Tool Implementation | 2 days | All 18+ tools working with real execution |
| M3: Sub-Agents & Bus | 1 day | SearchAgent, BookingAgent, DeltaBus |
| M4: Polish & Testing | 1 day | Reliable, beautiful demo |
| **Total** | **7 days** | **Production-ready REAL demo** |

---

## Appendix: Tool Schemas

### search_accommodations

```json
{
  "name": "search_accommodations",
  "description": "Search for hotels, B&Bs, or vacation rentals",
  "parameters": {
    "type": "object",
    "required": ["location", "check_in_date", "nights"],
    "properties": {
      "location": {"type": "string", "description": "City or region"},
      "check_in_date": {"type": "string", "description": "Check-in date"},
      "nights": {"type": "integer", "description": "Number of nights"},
      "budget_per_night": {"type": "number", "description": "Max price per night"},
      "party_size": {"type": "integer", "description": "Number of guests"},
      "amenities": {"type": "array", "items": {"type": "string"}}
    }
  }
}
```

### book_restaurant

```json
{
  "name": "book_restaurant",
  "description": "Make a restaurant reservation",
  "parameters": {
    "type": "object",
    "required": ["restaurant_name", "date", "time", "party_size"],
    "properties": {
      "restaurant_name": {"type": "string"},
      "date": {"type": "string"},
      "time": {"type": "string"},
      "party_size": {"type": "integer"},
      "special_requests": {"type": "array", "items": {"type": "string"}},
      "dietary_restrictions": {"type": "array", "items": {"type": "string"}}
    }
  }
}
```

### start_background_monitor

```json
{
  "name": "start_background_monitor",
  "description": "Start monitoring something in the background",
  "parameters": {
    "type": "object",
    "required": ["monitor_type", "target"],
    "properties": {
      "monitor_type": {"type": "string", "enum": ["weather", "price", "availability"]},
      "target": {"type": "string", "description": "What to monitor (location, item, etc)"},
      "dates": {"type": "array", "items": {"type": "string"}},
      "alert_conditions": {"type": "array", "items": {"type": "string"}}
    }
  }
}
```

---

*Document Created: February 4, 2026*
*Last Updated: February 4, 2026*
*Status: APPROVED - Ready for Development*
