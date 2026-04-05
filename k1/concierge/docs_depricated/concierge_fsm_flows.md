# Concierge FSM -- Complete Flow Catalog

> **Status**: AUTHORITATIVE -- derived from concierge.md FSM specification
> **Source**: `k1/concierge/concierge.md` Sections 5, 17, 18, 19, 22, 27, 32, 33, 36
> **Last Updated**: 2026-02-16

This document enumerates **every reachable flow** through the Concierge FSM, including normal paths, clarification loops, user interrupts at every interruptible state, safety overrides, circuit breaker degradation cascades, crash recovery, HIL from Planner, proactive injection, multi-message batching, and watchdog timeouts.

Each flow is derived directly from the 8-state / 14-event / 14-transition FSM defined in concierge.md Section 17.3.

---

## Part 1: Complete FSM State Catalog (8 States)

```
+------------------+------------------------------------------+---------------------------+----------------+
| State            | Purpose                                  | Typical Duration          | Interruptible  |
+------------------+------------------------------------------+---------------------------+----------------+
| LISTENING        | Awaiting user input. FSM idle            | Indefinite                | No             |
| ACKING           | Phase 1: UltraBERT classification        | 22-28ms                   | No             |
| CLARIFYING       | LLM needs info before proceeding         | User-dependent (5-60s)    | Yes            |
| DISPATCHING      | Route by complexity tier                 | <5ms                      | Yes            |
| COMPANIONING     | Keep conversation moving while           | 200ms-2s (MED/HIGH)       | Yes            |
|                  | backend works                            |                           |                |
| PROGRESSING      | Stream incremental deltas                | 500ms-30s                 | Yes            |
| DELIVERING       | Final results + cognitive writes         | <50ms                     | No             |
| INTERRUPT_HANDLING| User changes topic mid-turn             | <100ms                    | No             |
+------------------+------------------------------------------+---------------------------+----------------+
```

**Interruptible states**: DISPATCHING, COMPANIONING, PROGRESSING, CLARIFYING
**Non-interruptible states**: LISTENING, ACKING, DELIVERING, INTERRUPT_HANDLING

Rationale: Atomic operations (classification in ACKING, final delivery in DELIVERING) must complete to preserve data integrity. INTERRUPT_HANDLING is itself a transition -- allowing interrupts during interrupt processing would create infinite recursion.

---

## Part 2: Complete Event Catalog (14 Events)

```
+---------------------------+---------------------------+-----------------------------------------------+
| Event                     | Source                    | Description                                   |
+---------------------------+---------------------------+-----------------------------------------------+
| MESSAGE_RECEIVED          | IInputPort                | New user message arrives                       |
| PHASE1_COMPLETE           | TurnProcessor             | UltraBERT + hypothesis done, no gaps           |
| GAPS_DETECTED             | IntentProcessor           | Information gaps found by GapDetector          |
| CLARIFICATION_RECEIVED    | IInputPort                | User answers clarification question            |
| MAX_ROUNDS_REACHED        | ClarificationTracker      | 3 rounds exhausted (CONC-08)                   |
| DISPATCH_STARTED          | TurnProcessor             | Task dispatched by tier                        |
| PRELIMINARY_ACK_SENT      | ToolDispatcher            | ACK delivered to user via OutputManager        |
| PROGRESS_RECEIVED         | DeltaAggregator           | Delta batch arrived from Orchestrator/Fabric   |
| DISPATCH_COMPLETE         | IDispatchPort             | Orchestrator/direct execution done             |
| RESPONSE_DELIVERED        | OutputManager             | Final response sent to user via SSE            |
| TURN_COMPLETE             | TurnProcessor             | Turn boundary writes done                      |
| INTERRUPT_DETECTED        | IInputPort                | New msg during interruptible state             |
| INTERRUPT_HANDLED         | FSMController             | Cancel done, abbreviated turn_end complete     |
| CRISIS_DETECTED           | SafetyGate                | Safety override triggered (CRISIS band)        |
+---------------------------+---------------------------+-----------------------------------------------+
```

---

## Part 3: Complete Transition Table (All 14 Valid Transitions)

```
+--------------------+------------------------+--------------------+----------------------+------------------------------------------+
| From State         | Event                  | To State           | Guard                | Action                                   |
+--------------------+------------------------+--------------------+----------------------+------------------------------------------+
| LISTENING          | MESSAGE_RECEIVED       | ACKING             | turn_lock available  | acquire_lock(),                          |
|                    |                        |                    |                      | start_watchdog(120s),                    |
|                    |                        |                    |                      | init FSMContext                           |
+--------------------+------------------------+--------------------+----------------------+------------------------------------------+
| ACKING             | CRISIS_DETECTED        | DELIVERING         | safety_band == CRISIS| emit_crisis_response(),                  |
|                    |                        |                    |                      | skip Phase 2 entirely                    |
+--------------------+------------------------+--------------------+----------------------+------------------------------------------+
| ACKING             | PHASE1_COMPLETE        | DISPATCHING        | gaps.empty &&        | dispatch_by_tier(tier)                   |
|                    |                        |                    | confidence > 0.6     |                                          |
+--------------------+------------------------+--------------------+----------------------+------------------------------------------+
| ACKING             | GAPS_DETECTED          | CLARIFYING         | gaps.non_empty &&    | emit_clarification(gaps[0])              |
|                    |                        |                    | rounds < 3           |                                          |
+--------------------+------------------------+--------------------+----------------------+------------------------------------------+
| CLARIFYING         | CLARIFICATION_RECEIVED | ACKING             | --                   | re-run Phase 1 with                      |
|                    |                        |                    |                      | augmented input                          |
+--------------------+------------------------+--------------------+----------------------+------------------------------------------+
| CLARIFYING         | MAX_ROUNDS_REACHED     | DISPATCHING        | rounds >= 3          | ClarificationTracker.escalate(),         |
|                    |                        |                    |                      | proceed with best_guess                  |
+--------------------+------------------------+--------------------+----------------------+------------------------------------------+
| DISPATCHING        | PRELIMINARY_ACK_SENT   | COMPANIONING       | tier in (MED, HIGH)  | emit preliminary via                     |
|                    |                        |                    |                      | OutputManager(REALTIME)                  |
+--------------------+------------------------+--------------------+----------------------+------------------------------------------+
| DISPATCHING        | DISPATCH_COMPLETE      | DELIVERING         | tier == LOW (direct) | package Phase2Result                     |
+--------------------+------------------------+--------------------+----------------------+------------------------------------------+
| COMPANIONING       | PROGRESS_RECEIVED      | PROGRESSING        | delta batch available| stream_deltas via DeltaAggregator        |
+--------------------+------------------------+--------------------+----------------------+------------------------------------------+
| COMPANIONING       | DISPATCH_COMPLETE      | DELIVERING         | Orchestrator done    | package Phase2Result                     |
+--------------------+------------------------+--------------------+----------------------+------------------------------------------+
| PROGRESSING        | DISPATCH_COMPLETE      | DELIVERING         | all dispatches       | package Phase2Result                     |
|                    |                        |                    | settled              |                                          |
+--------------------+------------------------+--------------------+----------------------+------------------------------------------+
| DELIVERING         | RESPONSE_DELIVERED     | LISTENING          | --                   | turn_end() -> release_lock() ->          |
|                    |                        |                    |                      | tick_experience()                        |
+--------------------+------------------------+--------------------+----------------------+------------------------------------------+
| * (interruptible)  | INTERRUPT_DETECTED     | INTERRUPT_HANDLING | is_interruptible()   | cancel_inflight(),                       |
|                    |                        |                    | == True              | abbreviated turn_end()                   |
+--------------------+------------------------+--------------------+----------------------+------------------------------------------+
| INTERRUPT_HANDLING | INTERRUPT_HANDLED      | ACKING             | --                   | re-enter with new message,               |
|                    |                        |                    |                      | new FSMContext                            |
+--------------------+------------------------+--------------------+----------------------+------------------------------------------+
```

Any (state, event) pair not in this table raises `InvalidTransitionError`.

---

## Part 4: Complete End-to-End Flow Designs

### Flow 1: NORMAL LOW TIER (No Interruptions)

**Scenario**: Simple query, direct response, no Orchestrator involvement
**Example**: "What's the weather in London?"
**Tier**: LOW (complexity < 0.3)

```
LISTENING
    |
    v MESSAGE_RECEIVED
ACKING
    +-- UltraBERT (22ms): intent=weather, complexity=LOW (0.2), gaps=[], safety=GREEN
    +-- Write Elision Gate: beliefs_active unchanged (no new entities relevant)
    +-- Phase1Result: tier=LOW, hypothesis={primary="query_memory", confidence=0.92}
    |
    v PHASE1_COMPLETE (gaps empty, confidence > 0.6)
DISPATCHING
    +-- Route: LOW tier -> dispatch_direct() to Fabric (bypasses Orchestrator)
    +-- LLM ReAct loop starts:
    |     Iteration 1: acknowledge(ack_type="progress", message="Checking London weather...",
    |                               next_tool="invoke_capability")
    |                   invoke_capability(capability="tool.read.weather_api", params={city:"London"})
    +-- invoke_capability returns: {temp: 12, condition: "cloudy"}
    |
    v DISPATCH_COMPLETE (tier==LOW, direct execution done)
DELIVERING
    +-- LLM iteration 2 (final): "It's 12C in London with partly cloudy skies."
    +-- Cognitive writes: update_scoreboard(operation="upsert_task", status="completed")
    +-- OutputManager.enqueue(response)
    +-- turn_end():
    |     1. Flush OutputManager
    |     2. Append to history_active
    |     3. Update meta (turn_count++)
    |     4. Release Single Writer lock
    |     5. Checkpoint LOCAL COLD
    |     6. K0 sync (fire-and-forget)
    |     7. Check experience triggers (turn_count % 20/25/30)
    |
    v RESPONSE_DELIVERED
LISTENING
```

**State Path**: `LISTENING -> ACKING -> DISPATCHING -> DELIVERING -> LISTENING`
**Events**: `MESSAGE_RECEIVED -> PHASE1_COMPLETE -> DISPATCH_COMPLETE -> RESPONSE_DELIVERED`
**Duration**: ~800ms (Phase 1: 28ms + LLM: ~600ms + tools: ~100ms + boundary: ~70ms)
**Tool Calls**: 2 (acknowledge + invoke_capability)
**LLM Iterations**: 2
**SessionState Writes**: Phase 1 (1-4 sections via Write Elision) + Phase 2 (scoreboard) + Turn Boundary (history, meta)

---

### Flow 2: NORMAL MEDIUM TIER (No Interruptions)

**Scenario**: Multi-step task requiring Orchestrator but not Planner
**Example**: "Book a restaurant for dinner Saturday"
**Tier**: MEDIUM (complexity 0.3-0.7, max 2 Fabric calls per ORCH-10)

```
LISTENING
    |
    v MESSAGE_RECEIVED
ACKING
    +-- UltraBERT (22ms): intent=plan_event, complexity=MEDIUM (0.5), gaps=[], safety=GREEN
    +-- entities=[dinner:EVENT], temporal=[Saturday:DATE_REL -> 2026-02-21]
    +-- Write Elision: beliefs_active WRITE (entities detected), affective_now ELIDE (neutral)
    +-- Phase1Result: tier=MEDIUM, hypothesis={primary="plan_event", confidence=0.78}
    |
    v PHASE1_COMPLETE (gaps empty, confidence > 0.6)
DISPATCHING
    +-- Build TaskEnvelope(tier=MEDIUM, capabilities=["restaurant.search"],
    |     context={temporal: "2026-02-21", entities: ["dinner"]})
    +-- IDispatchPort.dispatch_envelope() -> Orchestrator mailbox (WFQ INTERACTIVE 30%)
    +-- LLM: acknowledge(ack_type="progress", message="Searching restaurants for Saturday...",
    |         next_tool="none")
    |
    v PRELIMINARY_ACK_SENT (tier in MEDIUM/HIGH)
COMPANIONING
    +-- Display "Searching restaurants for Saturday..." to user via SSE
    +-- Orchestrator processes TaskEnvelope:
    |     1. DAG: restaurant.search -> restaurant.filter (max 2 Fabric calls, ORCH-10)
    |     2. Fabric executes restaurant.search (2-5s)
    +-- Typing indicator on/off
    +-- IInputPort.has_buffered() checked at every await boundary -> False (no interrupt)
    |
    v PROGRESS_RECEIVED (DeltaAggregator receives k1.orchestration.step.completed.v1)
PROGRESSING
    +-- DeltaAggregator batches delta (500ms window, CONC-10)
    +-- Stream to user: "Found 3 Italian restaurants matching your criteria..."
    +-- FSMContext: deltas_received += 1
    +-- More steps executing in Orchestrator DAG...
    |
    v DISPATCH_COMPLETE (k1.orchestration.dag.completed.v1)
DELIVERING
    +-- AggregatedResult: {restaurants: [{name: "Trattoria", rating: 4.5}, ...]}
    +-- LLM final call with tool_results[]:
    |     "I found 3 options for Saturday dinner:
    |      1. Trattoria -- 4.5 stars
    |      2. Bella Italia -- 4.3 stars
    |      3. La Dolce Vita -- 4.1 stars
    |      Would you like me to book one?"
    +-- Cognitive writes:
    |     update_scoreboard(operation="upsert_task", task_id="restaurant_booking", status="pending")
    |     update_narrative(operation="new_thread", topic="restaurant_booking", domains=["PLANNING"])
    +-- OutputManager.enqueue(response)
    +-- turn_end() (full 9-step process)
    |
    v RESPONSE_DELIVERED
LISTENING
```

**State Path**: `LISTENING -> ACKING -> DISPATCHING -> COMPANIONING -> PROGRESSING -> DELIVERING -> LISTENING`
**Events**: `MESSAGE_RECEIVED -> PHASE1_COMPLETE -> PRELIMINARY_ACK_SENT -> PROGRESS_RECEIVED -> DISPATCH_COMPLETE -> RESPONSE_DELIVERED`
**Duration**: 3-10s (Phase 1: 28ms + dispatch: 5ms + Orchestrator: 2-8s + delivery: 70ms)
**Tool Calls**: 3-8 (acknowledge + Orchestrator DAG steps + cognitive writes)
**LLM Iterations**: 2-4
**Key Invariant**: ORCH-10 (MEDIUM tier max 2 Fabric calls)

---

### Flow 3: NORMAL HIGH TIER (No Interruptions)

**Scenario**: Complex planning requiring Planner 4-stage pipeline (SKETCH->EXPAND->VALIDATE->COMMIT)
**Example**: "Plan a 7-day Italy trip for our anniversary"
**Tier**: HIGH (complexity > 0.7, requires CommittedPlan per ORCH-11)

```
LISTENING
    |
    v MESSAGE_RECEIVED
ACKING
    +-- UltraBERT (22ms): intent=plan_event, complexity=HIGH (0.85), gaps=[], safety=GREEN
    +-- entities=[Italy:LOC, anniversary:FAMILY_EVENT], temporal=[7-day:DURATION]
    +-- Write Elision: beliefs_active WRITE (entities), affective_now WRITE (excited 0.7)
    +-- Phase1Result: tier=HIGH, hypothesis={primary="plan_event", confidence=0.88}
    |
    v PHASE1_COMPLETE
DISPATCHING
    +-- Build TaskEnvelope(tier=HIGH, capabilities=[],
    |     context={beliefs_snapshot, entities, temporal, affective_state})
    +-- IDispatchPort.dispatch_envelope() -> Orchestrator mailbox
    +-- Orchestrator: tier=HIGH -> PlannerAdapter.request_plan(PlanRequest)
    +-- acknowledge(ack_type="progress", message="Planning your Italy trip...", next_tool="none")
    |
    v PRELIMINARY_ACK_SENT
COMPANIONING
    +-- Display "Planning your Italy trip..." to user
    +-- Planner starts 4-stage pipeline:
    |
    +-- [t+0s]  SKETCH stage starts
    |     k1.agent.planner.delta.v1 {stage:"SKETCH", status:"STARTED"}
    |     Concierge: "Working on a plan..."
    |
    +-- [t+5s]  ProactiveAgent fires (wait > 5000ms):
    |     K0 P06 had emitted curiosity.intent.v1 -> gap: "Emma's piano lessons progress?"
    |     ProactiveAgent: "While I'm planning your trip, how are Emma's piano lessons going?"
    |     User responds: "She loves them! Practicing every day."
    |     -> IMemoryPort.store({content: "Emma loves piano, practices daily",
    |                           correlation: {gap_id: original_gap}})
    |     -> K0 P02 ingests, P03 resolves gap in next consolidation cycle
    |     (Proactive response does NOT change FSM state -- stays in COMPANIONING)
    |
    +-- [t+8s]  SKETCH stage completes
    |     k1.agent.planner.delta.v1 {stage:"SKETCH", status:"COMPLETED"}
    |
    +-- [t+10s] EXPAND stage starts/completes
    |     "Putting the details together..."
    |
    +-- [t+15s] VALIDATE stage
    |     "Validating feasibility..."
    |
    +-- [t+17s] COMMIT stage
    |     plan.ready.v1 -> Orchestrator receives CommittedPlan
    |     Orchestrator builds DAG from CommittedPlan
    |
    +-- IInputPort.has_buffered() checked throughout -> False
    |
    v PROGRESS_RECEIVED (multiple times, from DAG step completions)
PROGRESSING
    +-- DeltaAggregator receives step deltas:
    |     k1.orchestration.step.completed.v1 x N
    |     Stream each: "Checking flights...", "Comparing hotels...", "Booking tours..."
    +-- DAG execution: 5-30s of step deltas
    |
    v DISPATCH_COMPLETE (k1.orchestration.dag.completed.v1)
DELIVERING
    +-- AggregatedResult: {itinerary: {...}, flights: [...], hotels: [...], tours: [...]}
    +-- LLM final call: "Here's your 7-day Italy itinerary:
    |     Day 1: Arrive Rome, check into Hotel Roma...
    |     Day 2: Vatican tour in the morning..."
    +-- Cognitive writes:
    |     update_scoreboard(upsert_task, "italy_trip", "completed")
    |     update_narrative(close_thread, "italy_trip")
    |     update_beliefs(add_fact, "family", "anniversary_trip_planned", "Italy 7-day")
    +-- OutputManager.enqueue(response)
    +-- turn_end() (full, including experience triggers if turn_count hits modular interval)
    |
    v RESPONSE_DELIVERED
LISTENING
```

**State Path**: `LISTENING -> ACKING -> DISPATCHING -> COMPANIONING -> PROGRESSING -> DELIVERING -> LISTENING`
**Events**: `MESSAGE_RECEIVED -> PHASE1_COMPLETE -> PRELIMINARY_ACK_SENT -> PROGRESS_RECEIVED (multiple) -> DISPATCH_COMPLETE -> RESPONSE_DELIVERED`
**Duration**: 15-60s (Phase 1: 28ms + Planner: 10-30s + DAG: 5-30s + delivery: 100ms)
**Tool Calls**: 5-15
**LLM Iterations**: 3-6
**Key Invariant**: ORCH-11 (HIGH tier requires CommittedPlan before execution)
**Key Feature**: ProactiveAgent fills idle time with K0-originated gap-filling questions; user responses go to K0 P02 for closed-loop learning

---

### Flow 4: CLARIFICATION FLOW (Single Round)

**Scenario**: Intent detected but information gaps prevent action
**Example**: "Remind me to call her"
**Trigger**: GapDetector finds ENTITY_MISSING + REFERENCE_UNRESOLVED

```
LISTENING
    |
    v MESSAGE_RECEIVED
ACKING
    +-- UltraBERT (22ms): intent=set_reminder, confidence=0.45 (low)
    +-- entities=[her -> PRONOUN, unresolved], temporal=[]
    +-- ReferenceResolver: "her" -> check scoreboard.referents + beliefs_active
    |     No recent female referent with high salience -> UNRESOLVED
    +-- GapDetector:
    |     Gap 1: ENTITY_MISSING (WHO to remind about, required slot for set_reminder)
    |     Gap 2: REFERENCE_UNRESOLVED ("her" has no antecedent)
    |     Gap 3: TIME_AMBIGUOUS (WHEN -- no temporal expression detected, required slot)
    +-- ConfidenceScorer: uncertainty = 0.55 + 0.15 + 0.05 + 0.10 = 0.85 (high uncertainty)
    +-- Phase1Result: tier=LOW (despite gaps, intent is simple), gaps=[ENTITY_MISSING, TIME_AMBIGUOUS]
    |
    v GAPS_DETECTED (gaps.non_empty && round_count < 3)
CLARIFYING
    +-- ClarificationTracker.start_round(intent_id) -> rounds = 1
    +-- LLM receives gap context in prompt:
    |     [DETECTED GAPS]
    |       - ENTITY_MISSING: WHO to remind about (required for set_reminder)
    |       - TIME_AMBIGUOUS: WHEN to set reminder (required for set_reminder)
    +-- LLM formulates: "I'd be happy to set a reminder! Who would you like me to
    |     remind you about, and when should I remind you?"
    +-- OutputManager.enqueue(clarification_question)
    +-- FSMContext: pending_clarification=True, wait_for_user=True
    +-- IInputPort.receive_with_timeout(300000) -- 5min clarification timeout
    |
    v (User responds: "My mom, tomorrow morning")
      CLARIFICATION_RECEIVED
ACKING (re-enter with enriched context)
    +-- New Phase 1 with augmented input (original + clarification response)
    +-- UltraBERT: intent=set_reminder, confidence=0.92 (now resolved)
    +-- entities=[Mom -> PERSON -> Sarah Chen (from beliefs_active)]
    +-- temporal=[tomorrow morning -> 2026-02-17T09:00:00 (resolved)]
    +-- ReferenceResolver: "Mom" = Sarah Chen (LOCKED)
    +-- GapDetector: no remaining gaps
    +-- Phase1Result: gaps=[], tier=LOW
    |
    v PHASE1_COMPLETE (gaps empty, confidence > 0.6)
DISPATCHING
    +-- LLM: acknowledge(ack_type="progress", message="Setting reminder to call Sarah Chen
    |         tomorrow morning", next_tool="invoke_capability")
    +-- invoke_capability(capability="reminder.create",
    |     params={person: "Sarah Chen", date: "2026-02-17", time: "09:00"})
    |
    v DISPATCH_COMPLETE
DELIVERING
    +-- LLM: "Done! I'll remind you to call Sarah Chen tomorrow at 9am."
    +-- Cognitive writes: update_scoreboard(upsert_task, "reminder", "completed")
    +-- turn_end()
    |
    v RESPONSE_DELIVERED
LISTENING
```

**State Path**: `LISTENING -> ACKING -> CLARIFYING -> ACKING -> DISPATCHING -> DELIVERING -> LISTENING`
**Events**: `MESSAGE_RECEIVED -> GAPS_DETECTED -> CLARIFICATION_RECEIVED -> PHASE1_COMPLETE -> DISPATCH_COMPLETE -> RESPONSE_DELIVERED`
**Duration**: ~5-60s (depends on user response time)
**Key Feature**: State re-enters ACKING with enriched context; resolved references become LOCKED in prompt
**Invariant**: CONC-08 (max 3 clarification rounds)

---

### Flow 5: MAX CLARIFICATION ROUNDS (3 Rounds Exhausted)

**Scenario**: User keeps giving ambiguous answers, system force-proceeds after 3 rounds
**Example**: Budget question for event planning -- user answers vaguely 3 times

```
LISTENING
    |
    v MESSAGE_RECEIVED
ACKING
    +-- UltraBERT: intent=plan_event, confidence=0.65, gaps=[CONSTRAINT_UNCLEAR (budget)]
    +-- Phase1Result: gaps=[{type=CONSTRAINT_UNCLEAR, slot="budget"}]
    |
    v GAPS_DETECTED (gaps.non_empty && rounds < 3)
CLARIFYING (Round 1)
    +-- ClarificationTracker.rounds = 1
    +-- LLM: "What's your budget for this event?"
    +-- Wait for user

User: "Not too expensive"
    |
    v CLARIFICATION_RECEIVED
ACKING (re-enter, Round 2 attempt)
    +-- UltraBERT: intent=plan_event, "Not too expensive" still ambiguous
    +-- GapDetector: CONSTRAINT_UNCLEAR persists (no numeric budget extracted)
    +-- Phase1Result: gaps still present
    |
    v GAPS_DETECTED (gaps.non_empty && rounds < 3)
CLARIFYING (Round 2)
    +-- ClarificationTracker.rounds = 2
    +-- LLM: "Could you give me a specific budget range? For example, $50-100 or $200+?"
    +-- Wait for user

User: "Reasonable"
    |
    v CLARIFICATION_RECEIVED
ACKING (re-enter, Round 3 attempt)
    +-- UltraBERT: still ambiguous, no numeric extraction
    +-- GapDetector: CONSTRAINT_UNCLEAR persists
    +-- Phase1Result: gaps still present
    |
    v GAPS_DETECTED (gaps.non_empty && rounds < 3)
CLARIFYING (Round 3)
    +-- ClarificationTracker.rounds = 3
    +-- LLM: "Last question -- what's the maximum you'd want to spend?"
    +-- Wait for user

User: "Affordable"
    |
    v CLARIFICATION_RECEIVED
ACKING (Round 4 check -- but max reached)
    +-- UltraBERT: still ambiguous
    +-- ClarificationTracker.should_force_proceed(intent_id) -> True (rounds >= 3)
    |
    v MAX_ROUNDS_REACHED (rounds >= 3)
DISPATCHING (force proceed with best hypothesis)
    +-- ClarificationTracker.escalate(): EscalationDecision.BEST_GUESS
    +-- ComplexityRouter: proceed with moderate budget assumption
    +-- LLM: acknowledge(ack_type="progress",
    |         message="I'll work with a moderate budget range...",
    |         next_tool="invoke_capability")
    +-- Continue execution with fallback values
    ... (normal DISPATCHING -> COMPANIONING/DELIVERING flow)
```

**State Path**: `LISTENING -> ACKING -> CLARIFYING -> ACKING -> CLARIFYING -> ACKING -> CLARIFYING -> ACKING -> DISPATCHING -> ...`
**Events**: `MESSAGE_RECEIVED -> (GAPS_DETECTED -> CLARIFICATION_RECEIVED) x3 -> MAX_ROUNDS_REACHED -> ...`
**Key Invariant**: CONC-08 (exactly 3 clarification rounds max, never infinite loop)
**Design Principle**: System always moves forward -- never gets stuck in a clarification loop

---

### Flow 6: USER INTERRUPT DURING DISPATCHING (Earliest Interruptible Point)

**Scenario**: User sends new message while in DISPATCHING state (just after Phase 1, before Orchestrator/Fabric starts)
**Example**: "What's the weather?" then immediately "Actually, set a timer for 5 minutes"

```
LISTENING
    |
    v MESSAGE_RECEIVED (Message 1: "What's the weather?")
ACKING
    +-- UltraBERT: intent=weather, tier=LOW
    +-- Phase1Result: tier=LOW
    |
    v PHASE1_COMPLETE
DISPATCHING
    +-- Start building dispatch (invoke_capability for weather)
    +-- IInputPort.has_buffered() check -> True (Message 2 already waiting)
    +-- Current state DISPATCHING is INTERRUPTIBLE
    |
    v INTERRUPT_DETECTED
INTERRUPT_HANDLING
    +-- 1. Cancel in-flight: no dispatch sent yet, nothing to cancel
    +-- 2. Partial flush: no results collected (too early)
    +-- 3. turn_end_abbreviated():
    |     - Record turn_status = INTERRUPTED
    |     - Release Single Writer lock
    |     - Checkpoint LOCAL COLD (control section only)
    |     - SKIP: history append, telemetry, K0 sync, experience triggers
    +-- 4. Buffer Message 2 for processing
    |
    v INTERRUPT_HANDLED
ACKING (with Message 2: "Actually, set a timer for 5 minutes")
    +-- New FSMContext created (fresh turn)
    +-- UltraBERT: intent=set_reminder, entities=[timer:MISC], temporal=[5min:DURATION]
    +-- Phase1Result: tier=LOW, gaps=[]
    |
    v PHASE1_COMPLETE
DISPATCHING
    +-- LLM: acknowledge(ack_type="progress", message="Setting 5-minute timer",
    |         next_tool="invoke_capability")
    +-- invoke_capability(capability="timer.create", params={duration_min: 5})
    ... (continue normal LOW flow)
```

**State Path**: `LISTENING -> ACKING -> DISPATCHING -> INTERRUPT_HANDLING -> ACKING -> DISPATCHING -> DELIVERING -> LISTENING`
**Events**: `MESSAGE_RECEIVED -> PHASE1_COMPLETE -> INTERRUPT_DETECTED -> INTERRUPT_HANDLED -> PHASE1_COMPLETE -> DISPATCH_COMPLETE -> RESPONSE_DELIVERED`
**Key Feature**: Original turn discarded entirely (no partial results), new message gets fresh context
**Data Preservation**: None (interrupt happened before any execution)

---

### Flow 7: USER INTERRUPT DURING COMPANIONING (No Partial Results Yet)

**Scenario**: User interrupts while Orchestrator has been dispatched but no results received yet
**Example**: "What's the weather?" interrupted by "Never mind, set a timer"

```
LISTENING
    |
    v MESSAGE_RECEIVED (Message 1: "What's the weather?")
ACKING -> DISPATCHING -> PRELIMINARY_ACK_SENT
    |
    v
COMPANIONING
    +-- Display "Checking weather..." to user
    +-- Orchestrator/Fabric executing (800ms elapsed, no results yet)
    +-- IInputPort.has_buffered() check at await boundary -> True (Message 2 waiting)
    +-- Current state COMPANIONING is INTERRUPTIBLE
    |
    v INTERRUPT_DETECTED
INTERRUPT_HANDLING
    +-- 1. Cancel in-flight: IDispatchPort.cancel_dispatch(envelope_id)
    |     -> Orchestrator receives cancel -> stops DAG -> CancelResult.CANCELLED
    +-- 2. Partial flush: no completed results (nothing received)
    +-- 3. turn_end_abbreviated():
    |     - turn_status = INTERRUPTED
    |     - Release lock
    |     - Minimal checkpoint
    +-- 4. Buffer Message 2
    |
    v INTERRUPT_HANDLED
ACKING (with Message 2: "Never mind, set a timer")
    +-- New turn starts with fresh context
    +-- UltraBERT: intent=set_reminder, temporal=[timer]
    +-- Continue normal flow with new intent
```

**State Path**: `LISTENING -> ACKING -> DISPATCHING -> COMPANIONING -> INTERRUPT_HANDLING -> ACKING -> ...`
**Events**: `MESSAGE_RECEIVED -> PHASE1_COMPLETE -> PRELIMINARY_ACK_SENT -> INTERRUPT_DETECTED -> INTERRUPT_HANDLED -> ...`
**Data Preservation**: None (Orchestrator hadn't returned results)
**Polling**: IInputPort.has_buffered() checked between tool calls and at DeltaAggregator.flush() boundaries (<0.1ms overhead)

---

### Flow 8: USER INTERRUPT DURING PROGRESSING (With Partial Results)

**Scenario**: User refines request while Orchestrator has completed some steps
**Example**: "Book a restaurant" interrupted by "Wait, change to Italian only"

```
LISTENING
    |
    v MESSAGE_RECEIVED (Message 1: "Book a restaurant for Saturday")
ACKING -> DISPATCHING -> COMPANIONING (normal MEDIUM start)
    |
    v PROGRESS_RECEIVED
PROGRESSING
    +-- Step 1 complete (restaurant.search): found 10 restaurants
    +-- DeltaAggregator: stream "Found 10 restaurants near you..." to user
    +-- Step 2 starting (restaurant.filter)
    +-- FSMContext: deltas_received = 1, partial results: {restaurants: [10 items]}
    |
    v (User sends Message 2: "Wait, change to Italian only")
    IInputPort.has_buffered() -> True at DeltaAggregator.flush() boundary
    Current state PROGRESSING is INTERRUPTIBLE
    |
    v INTERRUPT_DETECTED
INTERRUPT_HANDLING
    +-- 1. Cancel in-flight: IDispatchPort.cancel_dispatch(envelope_id)
    |     -> Orchestrator cancels DAG, stops restaurant.filter step
    +-- 2. Partial flush: collect completed step results
    |     -> restaurant.search results preserved: {restaurants: [10 items]}
    |     -> Save to FSMContext.partial_results
    +-- 3. turn_end_abbreviated():
    |     - Record turn_status = INTERRUPTED
    |     - Save partial results into context for next turn
    |     - Release lock
    +-- 4. Buffer Message 2 with context from partial results
    |
    v INTERRUPT_HANDLED
ACKING (with Message 2 + partial context)
    +-- ContextAssembler includes: "Previous search found: [10 restaurants]"
    +-- UltraBERT: intent=refine_search (or plan_event), entities=[Italian:MISC]
    +-- GapDetector: now has rich context from partial results, no gaps
    +-- Phase1Result: gaps=[], tier=MEDIUM (refinement query)
    |
    v PHASE1_COMPLETE
DISPATCHING
    +-- Build new TaskEnvelope with tier=MEDIUM, capabilities=["restaurant.filter"]
    +-- params include: {restaurants: partial_results, cuisine: "Italian"}
    +-- Continue new turn with preserved context
    ... (normal MEDIUM flow -> filter to Italian only -> deliver results)
```

**State Path**: `LISTENING -> ... -> PROGRESSING -> INTERRUPT_HANDLING -> ACKING -> DISPATCHING -> ...`
**Events**: `... -> PROGRESS_RECEIVED -> INTERRUPT_DETECTED -> INTERRUPT_HANDLED -> PHASE1_COMPLETE -> ...`
**Data Preservation**: Partial results PRESERVED and fed into new context via ContextAssembler
**Key Feature**: Seamless refinement -- user doesn't need to re-state the original search

---

### Flow 9: USER INTERRUPT DURING HIGH TIER PROGRESSING (Planner Partials)

**Scenario**: User adds a constraint while Planner has completed SKETCH stage
**Example**: "Plan Italy trip" interrupted by "Actually, make sure to include Rome"

```
LISTENING
    |
    v MESSAGE_RECEIVED (Message 1: "Plan a trip to Italy")
ACKING -> DISPATCHING -> COMPANIONING (HIGH tier start)
    |
    +-- Planner SKETCH stage completes (partial plan sketch)
    +-- k1.agent.planner.delta.v1: {stage: "SKETCH", status: "COMPLETED"}
    +-- Planner EXPAND stage starts...
    |
    v PROGRESS_RECEIVED (from Orchestrator relaying planner deltas)
PROGRESSING
    +-- Stream: "Sketching itinerary... considering Venice, Florence, Milan"
    +-- Planner working on EXPAND stage (3s elapsed)
    |
    v (User sends Message 2: "Actually, make sure to include Rome")
    IInputPort.has_buffered() -> True
    Current state PROGRESSING is INTERRUPTIBLE
    |
    v INTERRUPT_DETECTED
INTERRUPT_HANDLING
    +-- 1. Cancel in-flight: IDispatchPort.cancel_dispatch(envelope_id)
    |     -> Orchestrator cancels Planner pipeline
    |     -> Planner: EXPAND stage aborted, SKETCH results available
    +-- 2. Partial flush: collect planner stage outputs
    |     -> SKETCH partial plan: {cities: ["Venice", "Florence", "Milan"], duration: "7-day"}
    |     -> EXPAND partial: incomplete (aborted)
    +-- 3. turn_end_abbreviated():
    |     - Save partial plan context to FSMContext
    |     - Record turn_status = INTERRUPTED
    |     - Release lock
    +-- 4. Buffer Message 2 with planner partials
    |
    v INTERRUPT_HANDLED
ACKING (with Message 2 + planner partials)
    +-- ContextAssembler includes: "Previous plan sketch: Italy, Venice, Florence, Milan (7-day)"
    +-- UltraBERT: intent=refine_plan (or plan_event), entities=[Rome:LOC]
    +-- GapDetector: now has plan context, no gaps
    +-- Phase1Result: tier=HIGH (still complex), hypothesis={refinement of plan}
    |
    v PHASE1_COMPLETE
DISPATCHING
    +-- Build new TaskEnvelope(tier=HIGH,
    |     context={partial_plan: sketch, new_requirement: "include Rome"})
    +-- Orchestrator sends to Planner with enriched context
    +-- Planner SKETCH stage runs again, now including Rome
    ... (complete HIGH tier flow with Rome included)
```

**State Path**: `LISTENING -> ... -> PROGRESSING -> INTERRUPT_HANDLING -> ACKING -> DISPATCHING -> COMPANIONING -> PROGRESSING -> DELIVERING -> LISTENING`
**Data Preservation**: Planner SKETCH partials preserved, new requirement merged
**Key Feature**: User refinement is additive -- system builds on previous work, doesn't start from scratch

---

### Flow 10: CLARIFICATION INTERRUPT (User Changes Topic During Clarification)

**Scenario**: LLM asks clarifying question, user responds with completely new topic
**Example**: LLM: "What's your budget?" User: "Actually, what's the weather tomorrow?"

```
LISTENING
    |
    v MESSAGE_RECEIVED (Message 1: "Plan an event")
ACKING
    +-- UltraBERT: intent=plan_event, gaps=[CONSTRAINT_UNCLEAR (budget, date, type)]
    +-- Phase1Result: gaps=[budget_missing, type_missing]
    |
    v GAPS_DETECTED
CLARIFYING
    +-- LLM: "I'd love to help plan something! What kind of event are you thinking,
    |     and what's your budget?"
    +-- ClarificationTracker.rounds = 1
    +-- FSMContext: pending_clarification=True, original_intent="plan_event"
    +-- Wait for user
    |
    v (User sends: "What's the weather tomorrow?")
    IInputPort receives message
    IntentProcessor detects: user_response intent = "weather" != expected clarification answer
    CLARIFYING is INTERRUPTIBLE
    |
    v INTERRUPT_DETECTED (clarification mismatch treated as interrupt)
INTERRUPT_HANDLING
    +-- 1. Discard pending clarification (user didn't answer it)
    +-- 2. Clear FSMContext.pending_clarification
    +-- 3. ClarificationTracker: clear rounds for abandoned intent
    +-- 4. turn_end_abbreviated():
    |     - No partial results to preserve
    |     - Release lock
    +-- 5. Buffer new message for fresh processing
    |
    v INTERRUPT_HANDLED
ACKING (with new message: "What's the weather tomorrow?")
    +-- UltraBERT: intent=weather, temporal=[tomorrow]
    +-- No context from previous clarification preserved (user abandoned it)
    +-- Phase1Result: gaps=[], tier=LOW
    |
    v PHASE1_COMPLETE
    ... (normal LOW weather flow)
```

**State Path**: `LISTENING -> ACKING -> CLARIFYING -> INTERRUPT_HANDLING -> ACKING -> DISPATCHING -> DELIVERING -> LISTENING`
**Events**: `MESSAGE_RECEIVED -> GAPS_DETECTED -> INTERRUPT_DETECTED -> INTERRUPT_HANDLED -> PHASE1_COMPLETE -> ...`
**Data Preservation**: None -- clarification context discarded (user changed topic)
**Key Feature**: System recognizes that the "clarification answer" is actually a new intent, not an answer to the pending question

---

### Flow 11: USER CORRECTION DURING DELIVERY (Non-Interruptible State)

**Scenario**: User corrects while final response is being streamed
**Example**: Concierge says "I'll remind you about Mom", user says "It's for Dad, not Mom"

```
LISTENING
    |
    v MESSAGE_RECEIVED (Message 1: "Remind me about Mom's appointment")
ACKING -> DISPATCHING -> DELIVERING
    |
    v RESPONSE_DELIVERED (streaming in progress)
    +-- OutputManager streaming: "I've set a reminder about Mom's appointment..."
    +-- IInputPort.has_buffered() check during stream -> True (Message 2 waiting)
    +-- Current state DELIVERING is NOT INTERRUPTIBLE (Section 17.1)
    +-- Message 2 is BUFFERED, not processed yet
    |
    v RESPONSE_DELIVERED (complete)
    +-- Full response delivered
    +-- turn_end() completes (history, meta, checkpoint, K0 sync)
    +-- FSM transitions to LISTENING
    |
    v (Now in LISTENING, buffered message available)
    MESSAGE_RECEIVED (Message 2: "It's for Dad, not Mom")
    |
    v
ACKING
    +-- UltraBERT: intent=other (correction), entities=[Dad:PERSON, Mom:PERSON]
    +-- ContextAssembler includes previous turn's history (Mom's reminder just set)
    +-- Phase1Result: hypothesis={correction of previous action}, tier=LOW
    |
    v PHASE1_COMPLETE
DISPATCHING
    +-- LLM sees context: previous turn set reminder for Mom, user corrects to Dad
    +-- acknowledge(ack_type="commit", message="Updating reminder to Dad's appointment",
    |     next_tool="invoke_capability")
    +-- invoke_capability(capability="reminder.update",
    |     params={old_person: "Mom/Sarah Chen", new_person: "Dad/Mike Chen"})
    |
    v DISPATCH_COMPLETE
DELIVERING
    +-- LLM: "Updated! The reminder is now for Dad's appointment instead of Mom's."
    +-- Cognitive writes:
    |     update_beliefs(correct_fact, "reminder", "person", "Mike Chen")
    |     update_scoreboard(upsert_task, "reminder_correction", "completed")
    +-- turn_end()
    |
    v RESPONSE_DELIVERED
LISTENING
```

**State Path**: `LISTENING -> ... -> DELIVERING -> LISTENING -> ACKING -> DISPATCHING -> DELIVERING -> LISTENING`
**Events**: Turn 1 completes normally, Turn 2 processes correction as new turn
**Key Feature**: DELIVERING is non-interruptible, so corrections queue for NEXT turn
**Design Principle**: Final delivery must be atomic -- partial responses must be avoided

---

### Flow 12: CRISIS DETECTION AND BYPASS

**Scenario**: Safety system detects crisis keywords, bypasses ALL normal FSM processing
**Example**: User expresses self-harm thoughts
**Safety Band**: CRISIS (highest severity)

```
LISTENING
    |
    v MESSAGE_RECEIVED (Message: expressing self-harm)
ACKING
    +-- UltraBERT (22ms): safety_familyos head -> CRISIS (confidence 0.99)
    +-- SafetyGate.evaluate() -> CRISIS detected
    +-- CRISIS keywords match (hardcoded scan, NON-NEGOTIABLE even if UltraBERT is down)
    +-- Bypass normal Phase1Result processing
    |
    v CRISIS_DETECTED (safety_band == CRISIS)
DELIVERING (direct, no Phase 2, no LLM, no tools)
    +-- CRISIS_STATIC_RESPONSE (hardcoded, zero external dependencies):
    |     "If you or someone you know is in crisis, please contact
    |      emergency services (911) or the 988 Suicide and Crisis Lifeline."
    +-- OutputManager.enqueue(crisis_response, priority=REALTIME)
    +-- Emit k1.concierge.crisis.detected.v1 via IDeltaPort
    +-- Log to safety audit trail
    +-- NO cognitive writes, NO tool calls, NO state mutations
    +-- turn_end() minimal:
    |     - Release lock
    |     - Checkpoint
    |     - SKIP experience triggers
    |
    v RESPONSE_DELIVERED
LISTENING (ready for next message)
```

**State Path**: `LISTENING -> ACKING -> DELIVERING -> LISTENING`
**Events**: `MESSAGE_RECEIVED -> CRISIS_DETECTED -> RESPONSE_DELIVERED`
**Duration**: ~25ms total (Phase 1 only, bypasses ALL Phase 2)
**Invariants Enforced**: CONC-05 (safety first), CONC-06 (CRISIS bypass)
**Zero-Dependency Guarantee**: Static response works even if LLM, Orchestrator, Fabric, K0, and all Circuit Breakers are down
**Safety-Critical Error Handling**: If IOutputPort fails during CRISIS, retry aggressively (5 attempts, 50ms each). CRISIS response delivery is the HIGHEST priority operation in the entire system.

---

### Flow 13: RED SAFETY BAND (Elevated Protocol)

**Scenario**: Safety system detects concerning but not crisis-level content
**Example**: "I've been feeling really down lately"
**Safety Band**: RED (persistent sadness, isolation, hopelessness, substance)

```
LISTENING
    |
    v MESSAGE_RECEIVED
ACKING
    +-- UltraBERT: safety_familyos head -> RED (subcategory="persistent_sadness", confidence=0.87)
    +-- SafetyGate.evaluate() -> RED detected
    +-- Phase1Result: safety_band=RED, but continue (not CRISIS)
    |
    v PHASE1_COMPLETE (safety_band != CRISIS, proceed to DISPATCHING)
DISPATCHING
    +-- ComplexityRouter: RED forces MINIMUM MEDIUM tier (even if complexity says LOW)
    +-- Build TaskEnvelope(tier=MEDIUM) -- overridden tier
    +-- acknowledge(ack_type="understanding", message="I hear you're feeling down...",
    |     next_tool="none")
    +-- ToolDispatcher safety context: safety_band=RED
    |     -> Action tools BLOCKED (ToolDispatcher safety check)
    |     -> Only Cognitive and Read tools allowed
    +-- Additional safety logging enabled
    |
    v PRELIMINARY_ACK_SENT
COMPANIONING
    +-- Orchestrator runs with enhanced monitoring
    +-- All action tools blocked in ToolDispatcher (no booking, no sending, no creating)
    +-- Cognitive tools allowed: refine_affect, update_beliefs, update_narrative
    +-- Read tools allowed: recall_memory (check if user has expressed this before)
    |
    v PROGRESS_RECEIVED / DISPATCH_COMPLETE
PROGRESSING / DELIVERING
    +-- LLM response crafted with HIGH warmth level, empathetic tone
    +-- Emotional mirroring: warmth_level=HIGH, formality=CASUAL, encouragement=True
    +-- Cognitive writes: update_beliefs, refine_affect (track emotional state)
    +-- turn_end()
    |
    v RESPONSE_DELIVERED
LISTENING
```

**State Path**: `LISTENING -> ACKING -> DISPATCHING -> COMPANIONING -> PROGRESSING -> DELIVERING -> LISTENING`
**Key Feature**: RED overrides tier selection (minimum MEDIUM), blocks action tools
**Design Principle**: When user is emotionally vulnerable, prevent accidental actions and prioritize empathetic response

---

### Flow 14: AMBER SAFETY BAND (Caution)

**Scenario**: Mild concern detected, proceed with caution but normal routing
**Example**: "I'm stressed about work deadlines"
**Safety Band**: AMBER (stress, mild sadness, frustration, health mention)

```
LISTENING
    |
    v MESSAGE_RECEIVED
ACKING
    +-- UltraBERT: safety_familyos -> AMBER (subcategory="stress")
    +-- SafetyGate.evaluate() -> AMBER (not RED, not CRISIS)
    +-- Phase1Result: safety_band=AMBER
    +-- Tier routing: NORMAL (AMBER does NOT override tier)
    |
    v PHASE1_COMPLETE
DISPATCHING
    +-- ComplexityRouter: normal routing (no override -- AMBER is GREEN for routing)
    +-- ToolDispatcher gets safety_band=AMBER in context
    +-- Action tools STILL ALLOWED (AMBER allows actions)
    +-- Enhanced logging enabled for safety audit trail
    |
    v ... (normal tier flow, LOW/MEDIUM/HIGH depending on complexity)
DELIVERING
    +-- All tools allowed but with enhanced logging
    +-- Emotional mirroring may adjust tone based on stress context
    +-- LLM prompt includes: persona.tone_hints suggesting empathetic framing
    +-- Experience layer tracks emotional trajectory
    +-- turn_end()
    |
    v RESPONSE_DELIVERED
LISTENING
```

**State Path**: Normal tier flow (same as Flow 1, 2, or 3 depending on complexity)
**Key Feature**: AMBER informs emotional processing and logging but DOES NOT change routing or block tools
**Safety Distinction**: GREEN=normal, AMBER=caution+logging, RED=restricted+override tier, CRISIS=bypass everything

---

### Flow 15: WATCHDOG TIMEOUT (Turn Exceeds 120 Seconds)

**Scenario**: Turn takes longer than absolute maximum watchdog timer
**Example**: HIGH tier task stuck in Planner for >120s
**Invariant**: CONC-15 (120s max turn)

```
LISTENING
    |
    v MESSAGE_RECEIVED
ACKING
    +-- turn_start(): start_watchdog(120s) -- CONC-15 absolute max
    +-- Phase1Result: tier=HIGH
    |
    v PHASE1_COMPLETE
DISPATCHING -> COMPANIONING
    |
    v PROGRESS_RECEIVED
PROGRESSING
    +-- Planner stages running... SKETCH complete... EXPAND in progress...
    +-- At t=121s, watchdog timer fires
    +-- Current state PROGRESSING is INTERRUPTIBLE
    |
    v INTERRUPT_DETECTED (internal watchdog event, mapped to INTERRUPT_DETECTED)
INTERRUPT_HANDLING
    +-- 1. Cancel in-flight: IDispatchPort.cancel_dispatch(envelope_id)
    |     -> Orchestrator cancels Planner and DAG
    +-- 2. Partial flush: collect any completed step results
    |     -> Some planner stages + DAG steps may have completed
    +-- 3. turn_end_abbreviated():
    |     - Record turn_status = TIMEOUT
    |     - Release lock
    +-- 4. Prepare apology message (system-generated, not user input)
    |
    v INTERRUPT_HANDLED
ACKING (system-generated timeout message, not new user input)
    +-- This is an internal "turn timeout" turn
    +-- LLM receives context: "Previous turn timed out after 120s. Partial results: [...]"
    +-- LLM generates apology with whatever partial results exist
    |
    v PHASE1_COMPLETE -> DISPATCHING -> DELIVERING
    +-- "I'm sorry, that took longer than expected. Here's what I found so far:
    |     [partial results if any]. Would you like me to try again with a simpler approach?"
    +-- turn_end()
    |
    v RESPONSE_DELIVERED
LISTENING
```

**State Path**: `LISTENING -> ... -> PROGRESSING -> INTERRUPT_HANDLING -> ACKING -> DELIVERING -> LISTENING`
**Events**: `... -> (internal watchdog) INTERRUPT_DETECTED -> INTERRUPT_HANDLED -> PHASE1_COMPLETE -> RESPONSE_DELIVERED`
**Invariant Enforced**: CONC-15 (120s max turn, never hangs)
**Key Feature**: Watchdog is separate from circuit breakers -- it fires even if all backends are responsive but slow

---

### Flow 16: CIRCUIT BREAKER OPEN -- TIER DEGRADATION CASCADE

**Scenario**: Orchestrator unavailable, system degrades gracefully through tier ladder
**Example**: HIGH tier request when CB_ORCHESTRATOR is OPEN

```
LISTENING
    |
    v MESSAGE_RECEIVED (HIGH tier intent: "Plan a birthday party")
ACKING
    +-- Phase1Result: tier=HIGH
    |
    v PHASE1_COMPLETE
DISPATCHING
    +-- Check CB_ORCHESTRATOR.state -> OPEN
    +-- ErrorRouter.classify() -> DEGRADE (FabricOrchestratorAdapter, DEGRADED)
    +-- Tier degradation cascade (Concierge-owned, NOT Orchestrator's responsibility):
    |
    +-- Attempt 1: HIGH -> MEDIUM downgrade
    |     Build TaskEnvelope(tier=MEDIUM, capabilities=["party.search", "venue.search"])
    |     IDispatchPort.dispatch_envelope() -> CB still OPEN -> REJECTED
    |
    +-- Attempt 2: MEDIUM -> LOW downgrade
    |     Cancel envelope, fall back to ToolDispatcher direct (dispatch_direct)
    |     acknowledge(ack_type="progress", message="I'll handle this directly for now...",
    |       next_tool="invoke_capability")
    |     invoke_capability(capability="party.search", params={...})
    |     If Fabric succeeds -> continue with LOW quality response
    |
    +-- Attempt 3: LOW -> CANNED (if CB_FABRIC also OPEN)
    |     All tiers exhausted
    |     Select canned response by intent_class:
    |       "I can't complete that right now, but I'm here to chat.
    |        Would you like to try again later?"
    |     Emit k1.concierge.degraded.v1 event
    |
    v DISPATCH_COMPLETE or (implicit failure)
DELIVERING
    +-- Deliver whatever response was possible (LOW quality or canned)
    +-- Emit k1.concierge.turn.completed.v1 with degradation_level=MODERATE or SEVERE
    +-- turn_end()
    |
    v RESPONSE_DELIVERED
LISTENING
```

**State Path**: `LISTENING -> ACKING -> DISPATCHING -> (varies by successful tier) -> DELIVERING -> LISTENING`
**Key Feature**: Degradation is Concierge-owned, not Orchestrator's responsibility
**Circuit Breakers Involved**: CB_ORCHESTRATOR, CB_FABRIC, CB_PLANNER may all trigger
**Half-Open Probes**: CB_ORCHESTRATOR probes every 60s, CB_FABRIC every 30s
**User Experience**: Progressively reduced capability, but NEVER hangs or crashes

---

### Flow 17: MULTI-MESSAGE BATCH (User Types Multiple Messages Rapidly)

**Scenario**: User sends several messages in quick succession before the system processes any
**Example**: "What's the weather?" -> "In Paris" -> "Tomorrow"

```
LISTENING
    |
    v MESSAGE_RECEIVED (Message 1: "What's the weather?")
ACKING
    +-- Phase1Result: tier=LOW, gaps=[LOC missing, TIME ambiguous]
    |
    v GAPS_DETECTED
CLARIFYING
    +-- LLM: "Sure! What city would you like weather for?"
    +-- ClarificationTracker.rounds = 1
    +-- Wait for user
    |
    v (Message 2 already buffered: "In Paris")
    +-- IntentProcessor: "In Paris" matches expected clarification (location answer)
    +-- This is a VALID CLARIFICATION ANSWER, not an interrupt
    CLARIFICATION_RECEIVED
ACKING (with enriched context: weather + Paris)
    +-- UltraBERT: intent=weather, entities=[Paris:LOC], temporal=[]
    +-- GapDetector: TIME_AMBIGUOUS still present (no time reference)
    +-- Phase1Result: gaps=[TIME_AMBIGUOUS]
    |
    v GAPS_DETECTED (gaps.non_empty && rounds < 3)
CLARIFYING (Round 2)
    +-- LLM: "What day would you like the weather for?"
    +-- ClarificationTracker.rounds = 2
    +-- Wait for user
    |
    v (Message 3 already buffered: "Tomorrow")
    +-- IntentProcessor: "Tomorrow" matches expected clarification (temporal answer)
    +-- This is a VALID CLARIFICATION ANSWER, not an interrupt
    CLARIFICATION_RECEIVED
ACKING (with enriched context: weather + Paris + tomorrow)
    +-- UltraBERT: intent=weather, entities=[Paris:LOC], temporal=[tomorrow -> 2026-02-17]
    +-- GapDetector: no gaps remaining
    +-- Phase1Result: gaps=[], tier=LOW
    |
    v PHASE1_COMPLETE
DISPATCHING
    +-- acknowledge(ack_type="progress", message="Checking Paris weather for tomorrow",
    |     next_tool="invoke_capability")
    +-- invoke_capability(capability="tool.read.weather_api", params={city: "Paris", date: "2026-02-17"})
    |
    v DISPATCH_COMPLETE
DELIVERING
    +-- "Tomorrow in Paris: 8C, light rain expected. Bring an umbrella!"
    +-- turn_end()
    |
    v RESPONSE_DELIVERED
LISTENING
```

**State Path**: `LISTENING -> ACKING -> CLARIFYING -> ACKING -> CLARIFYING -> ACKING -> DISPATCHING -> DELIVERING -> LISTENING`
**Key Feature**: System correctly distinguishes between interrupt (new topic) and clarification answer (same topic)
**Distinction Logic**: IntentProcessor compares incoming message's classified intent against pending clarification's expected slot type. If the message fills a gap slot (location, time), it's a clarification answer. If it's a completely new intent, it's an interrupt.

---

### Flow 18: USER INTERRUPT DURING CLARIFICATION WITH VALID CLARIFICATION ANSWER THEN INTERRUPT

**Scenario**: System asks clarification, user answers, then DURING the second round immediately interrupts
**Example**: "Plan something" -> (LLM asks "what?") -> "Dinner" -> (LLM asks "when?") -> "Forget it, check my emails"

```
LISTENING
    |
    v MESSAGE_RECEIVED ("Plan something")
ACKING -> GAPS_DETECTED
CLARIFYING (Round 1)
    +-- LLM: "What kind of event?"
    |
    v CLARIFICATION_RECEIVED ("Dinner")
ACKING (enriched: plan_event + dinner)
    +-- gaps still present: TEMPORAL missing (when?)
    |
    v GAPS_DETECTED
CLARIFYING (Round 2)
    +-- LLM: "Great, dinner! When were you thinking?"
    +-- Wait for user
    |
    v (User sends: "Forget it, check my emails")
    IntentProcessor: "check my emails" is NOT a temporal answer
    This is a new intent (query_memory / manage_task), NOT a clarification answer
    CLARIFYING is INTERRUPTIBLE
    |
    v INTERRUPT_DETECTED
INTERRUPT_HANDLING
    +-- 1. Discard pending clarification (dinner planning abandoned)
    +-- 2. Clear ClarificationTracker state for plan_event intent
    +-- 3. turn_end_abbreviated()
    +-- 4. Buffer new message
    |
    v INTERRUPT_HANDLED
ACKING ("check my emails")
    +-- UltraBERT: intent=query_memory, entities=[emails:MISC]
    +-- Phase1Result: tier=LOW, gaps=[]
    ... (normal email check flow)
```

**State Path**: `LISTENING -> ACKING -> CLARIFYING -> ACKING -> CLARIFYING -> INTERRUPT_HANDLING -> ACKING -> ...`
**Key Feature**: Even after answering one clarification successfully, user can interrupt the NEXT round
**Data Preservation**: All clarification context from abandoned intent is discarded

---

### Flow 19: HUMAN-IN-THE-LOOP (HIL) FROM PLANNER

**Scenario**: Planner needs human approval or clarification during HIGH tier execution
**Example**: Planner finds expensive flight, needs user approval before booking
**Source**: k1.hil.approval_request.v1 event from Planner via HILCoordinator

```
LISTENING
    |
    v MESSAGE_RECEIVED (HIGH tier: "Book flights to Italy for our trip")
ACKING -> DISPATCHING -> PRELIMINARY_ACK_SENT
    |
    v
COMPANIONING
    +-- Orchestrator invokes Planner
    +-- Planner: SKETCH -> EXPAND (finds flight options)
    +-- Planner reaches VALIDATE stage
    +-- Planner needs human approval (expensive purchase: $2,500 flight package)
    +-- HILCoordinator.request_approval(request_id, context)
    +-- Emits: k1.hil.approval_request.v1 via K1 Bus
    |
    v (Concierge receives k1.hil.approval_request.v1)
    FSM transitions: COMPANIONING -> CLARIFYING (HIL variant)
CLARIFYING (HIL -- Planner-originated, not LLM-originated)
    +-- ClarificationTracker.on_approval_request(request_id)
    +-- LLM frames the approval request naturally:
    |     "I've found a flight package for $2,500 (round trip, Rome).
    |      Should I go ahead and book it?"
    +-- OutputManager.enqueue(approval_question)
    +-- Wait for user response
    |
    v (User responds: "Yes, book it")
    CLARIFICATION_RECEIVED
    +-- ClarificationTracker: match response to pending request_id
    +-- Emit k1.hil.approval_response.v1 via IDeltaPort:
    |     ApprovalResponse(request_id, plan_id, response_type="approved")
    +-- Clear pending HIL request
    |
    FSM transitions: CLARIFYING -> COMPANIONING (back to waiting for Planner)
COMPANIONING (resumed)
    +-- Planner receives k1.hil.approval_response.v1
    +-- HILCoordinator._wait_for_response() unblocks
    +-- ValidateService resumes, approves plan
    +-- COMMIT stage executes
    +-- plan.ready.v1 -> Orchestrator builds DAG
    +-- DAG executes (book flights, confirm hotels)
    |
    v PROGRESS_RECEIVED (DAG step completions)
PROGRESSING
    +-- Stream: "Booking flights...", "Confirming hotel...", "Done!"
    |
    v DISPATCH_COMPLETE
DELIVERING
    +-- "Your Italy flights are booked! $2,500 round trip to Rome,
    |     departing March 15, returning March 22."
    +-- turn_end()
    |
    v RESPONSE_DELIVERED
LISTENING
```

**State Path**: `LISTENING -> ACKING -> DISPATCHING -> COMPANIONING -> CLARIFYING -> COMPANIONING -> PROGRESSING -> DELIVERING -> LISTENING`
**Events**: `... -> PRELIMINARY_ACK_SENT -> (HIL event) -> CLARIFICATION_RECEIVED -> PROGRESS_RECEIVED -> DISPATCH_COMPLETE -> RESPONSE_DELIVERED`
**Key Feature**: Planner-originated HIL uses the SAME CLARIFYING state as LLM-originated clarification
**HIL Timeout**: 120s (from OrchestratorConfig). If user doesn't respond, Orchestrator Reaper evicts the HIL context and the step fails.

---

### Flow 20: HIL REJECTION FROM PLANNER

**Scenario**: User rejects Planner's approval request
**Example**: "No, that's too expensive. Find something cheaper."

```
(Same as Flow 19 setup, but user rejects)

CLARIFYING (HIL)
    +-- LLM: "I've found a flight package for $2,500. Should I book it?"
    +-- Wait for user
    |
    v (User responds: "No, that's too expensive. Find something cheaper.")
    CLARIFICATION_RECEIVED
    +-- ClarificationTracker: match response to pending request_id
    +-- Emit k1.hil.approval_response.v1:
    |     ApprovalResponse(request_id, plan_id, response_type="rejected",
    |       modifications={"constraint": "cheaper flights, max $1500"})
    |
    FSM: CLARIFYING -> COMPANIONING
COMPANIONING
    +-- Planner receives rejection with modifications
    +-- Planner may restart EXPAND stage with new budget constraint
    +-- Or Planner may emit another approval_request with cheaper option
    |
    +-- [If Planner finds cheaper option]:
    |     k1.hil.approval_request.v1 again
    |     COMPANIONING -> CLARIFYING (another HIL round)
    |     LLM: "I found a $1,200 option with a layover. Book this one?"
    |     User: "Yes!"
    |     -> Normal approval flow continues
    |
    +-- [If Planner exhausts options]:
    |     k1.orchestration.dag.completed.v1 with success=false
    |     COMPANIONING -> DELIVERING
    |     "I couldn't find flights within your budget. Would you like to
    |      try different dates or consider trains?"
    |
    v DISPATCH_COMPLETE / DELIVERING
    ... (varies based on Planner result)
```

**State Path**: `... -> CLARIFYING -> COMPANIONING -> CLARIFYING -> COMPANIONING -> ...` (may loop)
**Key Feature**: HIL rejection feeds modifications back to Planner, which may re-try or fail
**Important**: HIL rounds from Planner do NOT count against CONC-08 (3 max clarification rounds). CONC-08 applies to Concierge's own LLM clarification, not Planner HIL.

---

### Flow 21: PROACTIVE AGENT INJECTION DURING HIGH TIER

**Scenario**: During long wait, K0 emits gap question that Concierge injects as natural conversation
**Example**: K0 detected stale gap about Emma's piano lessons

```
LISTENING
    |
    v MESSAGE_RECEIVED (HIGH tier: "Plan Italy trip")
ACKING -> DISPATCHING -> PRELIMINARY_ACK_SENT
    |
    v
COMPANIONING
    +-- Orchestrator working (Planner in SKETCH stage, ~10s)
    +-- [t+5000ms] ProactiveAgent.generate_fill_message() fires (wait > 5s threshold)
    |
    +-- ProactiveAgent checks incoming signals:
    |     K0 P06 had emitted curiosity.intent.v1 via SSE:
    |       {gap_type: "STALE_ANCHOR", subject: "Emma", attribute: "piano_lessons",
    |        question_blueprint: "How are {subject}'s piano lessons going?",
    |        importance_score: 0.78}
    |
    +-- ProactiveAgent frames naturally:
    |     "While I'm planning your trip, I had a quick question --
    |      you mentioned last week that Emma started piano lessons.
    |      How's that going?"
    +-- OutputManager.enqueue(proactive_message, priority=BACKGROUND)
    |
    +-- FSM STAYS IN COMPANIONING (proactive injection does NOT change FSM state)
    |
    +-- [t+8000ms] User responds: "She's loving them! Practicing every day now."
    |     This response goes to DeltaAggregator (as K0 gap fill), NOT as a new turn
    |     IMemoryPort.store({
    |       content: "Emma loves piano lessons, practices daily",
    |       correlation: {gap_id: original_gap_id, resolution_type: "proactive_answer"},
    |       topic: "memory.delta"
    |     })
    |     -> K0 P02 ingests -> P03 next consolidation resolves gap
    |     -> Closed-loop learning complete
    |
    +-- REMAIN IN COMPANIONING (backend still working)
    |
    +-- [t+15000ms] Orchestrator/Planner results start arriving
    |
    v PROGRESS_RECEIVED
PROGRESSING
    +-- Normal delta streaming with both:
    |     1. Trip planning results
    |     2. Brief acknowledgment of piano answer: "Great to hear about Emma!"
    |
    v DISPATCH_COMPLETE
DELIVERING
    +-- Final response includes trip plan + acknowledgment of proactive answer
    +-- turn_end()
    |
    v RESPONSE_DELIVERED
LISTENING
```

**State Path**: `LISTENING -> ACKING -> DISPATCHING -> COMPANIONING (stays here for proactive) -> PROGRESSING -> DELIVERING -> LISTENING`
**Key Feature**: Proactive injection does NOT change FSM state. User responses to proactive questions are routed to DeltaAggregator/IMemoryPort, not treated as new turns or interrupts.
**Trigger Conditions**: Only in COMPANIONING during HIGH tier, only after 5s of wait time, max 1 proactive question per turn
**Source**: K0 P06 Active Learning -> curiosity.intent.v1 via SSE -> Bridge -> K1 Bus -> ProactiveAgent

---

### Flow 22: PROACTIVE AGENT -- NO K0 GAPS AVAILABLE

**Scenario**: Long wait but K0 has no gap questions to ask
**Example**: HIGH tier, 10s wait, K0 has no pending gaps

```
COMPANIONING (HIGH tier, t+5000ms)
    |
    +-- ProactiveAgent.generate_fill_message():
    |     k0_questions = [] (no pending curiosity.intent.v1 events)
    |     -> Generate warmth message instead:
    |        "Still working on that for you -- just pulling together the details..."
    +-- OutputManager.enqueue(warmth_message, priority=BACKGROUND)
    +-- Typing indicator toggle
    |
    +-- [t+12000ms] If still waiting:
    |     ProactiveAgent may emit another warmth message:
    |     "Almost there! Comparing options..."
    |
    +-- REMAIN IN COMPANIONING until backend responds
```

**State Path**: Same as normal HIGH flow
**Key Feature**: Even without K0 gaps, ProactiveAgent keeps conversation alive with warmth messages

---

### Flow 23: SESSION CRASH AND RECOVERY

**Scenario**: Session crashes mid-turn, system restores from checkpoint
**Lifecycle Phase**: LC_CRASH_RECOVERY (Section 22.6)

```
Normal turn in PROGRESSING state
    +-- System crashes unexpectedly (process kill, OOM, etc.)
    +-- Session state lost in memory
    +-- BUT: LOCAL COLD (SQLite) has last completed turn's checkpoint
    |
    v CRASH DETECTED (on session resume)
CRASH_RECOVERY (FSMController.crash_recovery())
    |
    +-- 1. Bootstrap: create 9 services + connect 8 ports (no state needed)
    |
    +-- 2. Detect incomplete turn:
    |     Read control section from LOCAL COLD
    |     control.turn_lock is NOT None -> crashed during active turn
    |
    +-- 3. Rollback incomplete turn:
    |     Clear turn_lock
    |     Increment lock_version (prevents stale writes from ghost processes)
    |     Set turn_status = ROLLED_BACK
    |     Discard un-flushed DeltaAggregator batch
    |
    +-- 4. Reconcile Local Outbox:
    |     Read pending K0 writes from SQLite outbox table
    |     If Bridge online: drain outbox (fire-and-forget)
    |     If Bridge offline: leave in outbox for eventual sync
    |
    +-- 5. Restore from LOCAL COLD:
    |     Read full HOT + WARM snapshot from SQLite
    |     Validate CRC-32 checksums per section
    |     If checksum mismatch: rebuild from K0 (~500ms)
    |     If K0 also unavailable: empty section (bounded data loss)
    |
    +-- 6. Resume:
    |     Load persona (PersonaEngine + style)
    |     Init 7 circuit breakers -> all CLOSED (clean slate)
    |     Start delta subscriptions + DeltaAggregator timer
    |
    +-- 7. Emit k1.concierge.session.recovered.v1
    |     Log recovery telemetry: {session_id, lock_version, rolled_back_turn,
    |       restore_source, duration_ms, sections_restored, outbox_drained}
    |
    v FSM -> LISTENING
LISTENING (ready for new user message)
    +-- Last completed turn preserved
    +-- Crashed turn is LOST (max loss = 1 turn)
    +-- User may need to re-send their last message
```

**State Path**: N/A (crash recovery is outside normal FSM)
**Key Feature**: Edge-First design ensures LOCAL COLD always has last completed turn via turn_end() checkpoint
**Guarantee**: Maximum data loss = 1 turn
**Recovery Time**: P95 < 50ms (from LOCAL COLD), ~500ms if K0 rebuild needed

---

### Flow 24: FALLBACK RESPONSE (Multiple Systems Failing)

**Scenario**: Progressive degradation until only canned response works
**Example**: LLM cascade exhausted, Orchestrator CB open, Fabric CB open

```
LISTENING
    |
    v MESSAGE_RECEIVED
ACKING
    +-- UltraBERT works -> Phase1Result: tier=MEDIUM, safety=GREEN
    |
    v PHASE1_COMPLETE
DISPATCHING
    +-- CB_ORCHESTRATOR: OPEN -> DEGRADE
    +-- Tier cascade: MEDIUM -> LOW
    +-- dispatch_direct() to Fabric
    +-- CB_FABRIC: OPEN -> DEGRADE
    +-- LOW also fails -> no Fabric execution possible
    +-- ErrorRouter: all tiers exhausted -> ABORT pathway, but try LLM first
    +--
    +-- LLM attempt for at least a text response:
    |     CB_MODEL: also OPEN -> cascade L1 -> L2 -> L3 all fail
    |     ErrorRouter: LLM cascade exhausted -> FALLBACK to template
    |
    v (no successful dispatch, no LLM)
DELIVERING (fallback/canned)
    +-- Select canned response by intent_class (from Phase1Result):
    |     plan_event: "I can't help with planning right now, but I'm here to chat."
    |     set_reminder: "I can't set reminders at the moment. Please try again shortly."
    |     query_memory: "I'm having trouble searching my memory. Give me a moment."
    |     default: "I'm experiencing some difficulties. Please try again in a moment."
    +-- OutputManager.enqueue(canned_response, priority=REALTIME)
    +-- Emit k1.concierge.turn.failed.v1 with degradation_level=SEVERE
    +-- turn_end() (minimal: release lock, checkpoint, no history append for canned)
    |
    v RESPONSE_DELIVERED
LISTENING
```

**State Path**: `LISTENING -> ACKING -> DISPATCHING -> DELIVERING -> LISTENING`
**Key Feature**: Turn ALWAYS completes with a meaningful (if limited) response -- system NEVER hangs
**Canned Templates**: Keyed by (intent_class, tier) from Phase1Result classification

---

### Flow 25: LLM TIMEOUT AND CASCADE

**Scenario**: Primary LLM provider times out, system cascades to backup providers
**Example**: Phase 2 LLM call exceeds 30s timeout (CONC-16)

```
DISPATCHING (or DELIVERING during final LLM call)
    |
    +-- LLM.execute_prompt() -> 30s timeout fires (CONC-16)
    +-- CB_MODEL records failure in sliding window
    |
    +-- ErrorRouter: ModelGatewayAdapter, RECOVERABLE -> RETRY(2, 100ms)
    +-- Retry 1 (100ms delay): same provider -> timeout again
    +-- Retry 2 (200ms delay): same provider -> timeout again
    |
    +-- CB_MODEL: failures >= threshold (5 in 60s window) -> OPEN
    +-- LLM Cascade: L1 exhausted -> try L2 (different provider/model)
    |
    +-- [If L2 succeeds]: Continue turn normally, user unaware of cascade
    |
    +-- [If L2 fails]: Try L3 (smallest/fastest fallback model)
    |
    +-- [If L3 fails]: CB fully OPEN -> CANNED_RESPONSE fallback
    |     Template by (intent_class, tier):
    |       "I'm having trouble generating a response right now. Please try again."
    |
    v DELIVERING (with whatever response was possible)
    ... (turn completes)
```

**State Path**: Varies (depends on which phase the LLM timeout occurs in)
**Key Feature**: 3-tier LLM cascade with circuit breaker protection
**Half-Open Probe**: CB_MODEL probes every 30s with one real request

---

### Flow 26: ULTRABERT FAILURE (Heuristic Fallback)

**Scenario**: UltraBERT model unavailable, fall back to 5-rule heuristic classifier
**Example**: CB_CLASSIFICATION is OPEN

```
LISTENING
    |
    v MESSAGE_RECEIVED
ACKING
    +-- UltraBERTAdapter.classify() -> CB_CLASSIFICATION is OPEN
    +-- ErrorRouter: UltraBERTAdapter, DEGRADED -> FALLBACK(HeuristicFallbackClassifier)
    |
    +-- HeuristicFallbackClassifier executes (<1ms):
    |     Rule 1: CRISIS keywords scan (hardcoded, NON-NEGOTIABLE safety invariant)
    |     Rule 2: Question + <20 words -> conversational / LOW
    |     Rule 3: remind/schedule/set keywords -> task / MEDIUM
    |     Rule 4: plan/help me with keywords -> planning / HIGH
    |     Rule 5: Default -> conversational / LOW
    |
    +-- Heuristic confidence: ~0.5 (vs UltraBERT ~0.85+)
    +-- ALL Phase 1 SessionState writes ELIDED (no UltraBERT head data)
    +-- Only safety_band set from keyword scan
    +-- Phase1Result: tier from heuristic, safety_band from keyword scan
    |
    v PHASE1_COMPLETE (degraded accuracy, user unaware)
DISPATCHING
    +-- Normal Phase 2 proceeds with degraded Phase 1 context
    +-- LLM has less pre-grounded data (no entities, emotions, temporal info)
    +-- LLM compensates by asking more clarifying questions
    ... (normal flow, possibly with more clarification rounds)
```

**State Path**: Normal flow, but Phase 1 is heuristic instead of neural
**User Impact**: Slightly less accurate routing and context, user likely unaware
**Half-Open Probe**: CB_CLASSIFICATION probes every 10s

---

### Flow 27: SESSIONSTATE WRITE FAILURE

**Scenario**: MutationGuard rejects a write during Phase 2 cognitive tool execution
**Example**: HOT tier over 48KB limit (CONC-20)

```
DISPATCHING / DELIVERING (during Phase 2 LLM tool loop)
    |
    +-- LLM calls update_beliefs(add_fact, "Dad", "works_at", "Acme Corp")
    +-- ToolDispatcher -> IStatePort.write("beliefs_active", delta)
    +-- MutationGuard.preflight():
    |     SIZE_EXCEEDED: beliefs_active would exceed 8KB section budget
    |     MutationResponse: REJECTED, category=CAPACITY
    |
    +-- ErrorRouter: SessionKernelAdapter, DEGRADED -> DEGRADE(StaleSnapshot)
    +-- ToolResult fed back to LLM: {success: false, error_code: "CAPACITY",
    |     error_message: "beliefs_active section full (8KB). Consider using
    |     summarize_context() or promote_belief(hot_to_k0) to free space."}
    |
    +-- LLM compensates (next iteration):
    |     Option A: Call summarize_context() to compress beliefs section
    |     Option B: Call promote_belief(hot_to_k0) to persist old beliefs to K0
    |     Option C: Skip write, include fact in response text only
    |
    +-- Turn continues with adapted strategy
    |
    v ... (normal completion)
```

**State Path**: Normal flow, with retry/adaptation in the LLM loop
**Key Feature**: LLM receives structured error feedback and can adapt its strategy
**Invariant**: CONC-20 (HOT tier 48KB), CONC-21 (WARM tier 48KB)

---

### Flow 28: INTERRUPT DURING HIL (User Interrupts Planner Approval)

**Scenario**: Planner asks for approval, user ignores and asks something unrelated
**Example**: "Should I book the $2500 flight?" -> User: "What time is it in Tokyo?"

```
COMPANIONING
    |
    v (k1.hil.approval_request.v1 from Planner)
CLARIFYING (HIL)
    +-- LLM: "I found a $2,500 flight package. Should I book it?"
    +-- Wait for user
    |
    v (User sends: "What time is it in Tokyo?")
    IntentProcessor: "What time is it in Tokyo?" is query_memory intent, NOT approval answer
    CLARIFYING is INTERRUPTIBLE
    |
    v INTERRUPT_DETECTED
INTERRUPT_HANDLING
    +-- 1. Cancel in-flight: IDispatchPort.cancel_dispatch(envelope_id)
    |     -> Orchestrator receives cancel -> Planner pipeline aborted
    |     -> HIL request expires (HILCoordinator timeout or explicit cancel)
    +-- 2. Discard pending HIL context
    +-- 3. turn_end_abbreviated()
    +-- 4. Buffer new message
    |
    v INTERRUPT_HANDLED
ACKING ("What time is it in Tokyo?")
    +-- UltraBERT: intent=query_memory, entities=[Tokyo:LOC]
    +-- Phase1Result: tier=LOW, gaps=[]
    +-- Normal LOW flow (check timezone API)
    ... (respond with Tokyo time)
```

**State Path**: `... -> CLARIFYING -> INTERRUPT_HANDLING -> ACKING -> ... -> LISTENING`
**Key Feature**: Abandoning a Planner HIL request cancels the entire Planner pipeline
**Data Loss**: Planner plan is discarded. If user wants to revisit, they must re-initiate.
**Important Design Note**: HIL requests have a 120s timeout on the Orchestrator side anyway. Explicit cancellation via interrupt is cleaner.

---

### Flow 29: EXPERIENCE LAYER TRIGGER DURING TURN_END

**Scenario**: Turn count hits a modular interval, triggering Experience Layer processing
**Example**: Turn 100 -- triggers NarrativeWeaving (% 20), EmotionalProcessing (% 25), AnticipatoryResponse (not % 30)

```
DELIVERING
    |
    v RESPONSE_DELIVERED
    +-- turn_end() executes:
    |     Steps 1-7 complete (flush, history, meta, lock release, checkpoint, K0 sync)
    |
    +-- Step 8: tick_experience(turn_count=100)
    |     Check triggers:
    |       100 % 20 == 0 -> NarrativeWeaving fires
    |       100 % 25 == 0 -> EmotionalProcessing + EmotionalMirroring fire
    |       100 % 30 != 0 -> AnticipatoryResponse does NOT fire
    |
    +-- NarrativeWeaving.weave() (<10ms, pure heuristic):
    |     Input: last 20 turns from history_active + scoreboard
    |     Output: NarrativeCluster[] (conversation thread clusters)
    |     Write: update_narrative(clusters) via IStatePort
    |
    +-- EmotionalProcessing.process() (<5ms, pure heuristic):
    |     Input: last 25 turns' affective_now snapshots
    |     Output: EmotionalTrajectory{trend=IMPROVING, dominant="content", transitions=2}
    |     Write: affective_now.trajectory via IStatePort
    |
    +-- EmotionalMirroring.compute() (<2ms, always after EmotionalProcessing):
    |     Input: EmotionalTrajectory + current persona
    |     Output: ToneAdjustment{warmth=MEDIUM, formality=CASUAL, encouragement=True}
    |     Write: persona.tone_hints via IStatePort
    |
    +-- Total experience budget: <17ms (well within 500ms max)
    |
    v Step 9: Emit k1.concierge.turn.completed.v1
LISTENING
```

**State Path**: Normal flow with experience processing in turn_end()
**Key Feature**: Experience Layer is NON-BLOCKING (async during turn_end), and its results inform FUTURE turns' LLM prompts (via [RESPONSE STYLE] section in DynamicPromptBuilder)
**Intervals**: NarrativeWeaving: every 20 turns, EmotionalProcessing: every 25 turns, AnticipatoryResponse: every 30 turns
**Combined Budget**: Max 500ms (usually completes in <50ms)

---

### Flow 30: ORCHESTRATOR HIL FALLBACK REQUEST

**Scenario**: Orchestrator encounters ambiguity during DAG execution (not Planner), routes fallback to user
**Example**: DAG step fails with ambiguous capability resolution, Orchestrator asks user to choose
**Source**: k1.hil.fallback.v1 event from Orchestrator

```
COMPANIONING (MEDIUM or HIGH tier, Orchestrator executing DAG)
    |
    +-- Orchestrator DAG step: restaurant.search returns 2 ambiguous results
    +-- Orchestrator cannot decide autonomously (ORCH-02: no LLM)
    +-- Emits k1.hil.fallback.v1 via IDeltaEmitPort:
    |     {request_id, trace_id, context: "Two restaurants match equally. User preference needed.",
    |      options: ["Trattoria Milano ($$)", "Casa Roma ($$$)"]}
    |
    v (Concierge receives k1.hil.fallback.v1)
    FSM: COMPANIONING -> CLARIFYING (fallback variant)
CLARIFYING (fallback)
    +-- LLM frames choice naturally:
    |     "I found two great options! Which would you prefer?
    |      1. Trattoria Milano -- moderate price
    |      2. Casa Roma -- upscale experience"
    +-- Wait for user
    |
    v (User responds: "Trattoria Milano")
    CLARIFICATION_RECEIVED
    +-- Emit k1.hil.fallback_response.v1:
    |     FallbackResponse(request_id, trace_id, user_response="Trattoria Milano")
    |
    FSM: CLARIFYING -> COMPANIONING (Orchestrator resumes DAG)
COMPANIONING
    +-- Orchestrator receives fallback response, resumes DAG execution
    +-- Continue step with selected restaurant
    |
    v PROGRESS_RECEIVED / DISPATCH_COMPLETE
    ... (normal completion)
```

**State Path**: `... -> COMPANIONING -> CLARIFYING -> COMPANIONING -> ...`
**Key Feature**: Same CLARIFYING state handles LLM clarification, Planner HIL, and Orchestrator fallback

---

### Flow 31: USER OVERRIDE DURING EXECUTION

**Scenario**: User wants to cancel or modify an in-progress task
**Example**: "Cancel that booking" while Orchestrator is executing
**Source**: k1.hil.override_response.v1

```
COMPANIONING or PROGRESSING (task in progress)
    |
    v (User sends: "Cancel that booking")
    IInputPort.has_buffered() -> True
    Current state is INTERRUPTIBLE
    |
    v INTERRUPT_DETECTED
INTERRUPT_HANDLING
    +-- 1. Cancel in-flight: IDispatchPort.cancel_dispatch(envelope_id)
    +-- 2. Partial flush: collect completed results (some bookings may have succeeded)
    +-- 3. turn_end_abbreviated()
    +-- 4. Buffer cancel message
    |
    v INTERRUPT_HANDLED
ACKING ("Cancel that booking")
    +-- UltraBERT: intent=manage_task (cancel/modify), confidence=0.85
    +-- ContextAssembler: previous turn had active booking task
    +-- Phase1Result: tier=LOW (cancellation is simple)
    |
    v PHASE1_COMPLETE
DISPATCHING
    +-- LLM recognizes cancellation intent with context from previous turn
    +-- acknowledge(ack_type="commit", message="Cancelling the booking...",
    |     next_tool="invoke_capability")
    +-- invoke_capability(capability="booking.cancel", params={booking_id: from_partial_results})
    |
    v DISPATCH_COMPLETE
DELIVERING
    +-- "Done! I've cancelled the restaurant booking."
    +-- If partial results existed (e.g., flight already booked but hotel not):
    |     "I cancelled the hotel booking. Note: the flight was already confirmed --
    |      would you like me to cancel that too?"
    +-- Cognitive writes: update_scoreboard(upsert_task, "booking", "cancelled")
    +-- turn_end()
    |
    v RESPONSE_DELIVERED
LISTENING
```

**State Path**: `... -> INTERRUPT_HANDLING -> ACKING -> DISPATCHING -> DELIVERING -> LISTENING`
**Key Feature**: System intelligently handles partial cancellation (some steps completed, some not)

---

### Flow 32: CLARIFICATION TIMEOUT (User Doesn't Respond)

**Scenario**: LLM asks clarifying question, user never responds within timeout
**Example**: LLM asks "What cuisine?" and user walks away

```
ACKING
    |
    v GAPS_DETECTED
CLARIFYING
    +-- LLM: "What cuisine would you prefer?"
    +-- ClarificationTracker.rounds = 1
    +-- IInputPort.receive_with_timeout(300000) -- 5 minute timeout
    |
    +-- [300 seconds pass, no response]
    +-- receive_with_timeout returns None
    |
    +-- Clarification timeout triggered:
    |     turn_end_abbreviated()
    |     Record turn_status = CLARIFICATION_TIMEOUT
    |     Release lock
    |
    v FSM -> LISTENING (abandon turn)
LISTENING
    +-- Turn abandoned, no response sent to user
    +-- When user eventually returns and sends a new message,
    |     it starts a completely fresh turn
```

**State Path**: `LISTENING -> ACKING -> CLARIFYING -> LISTENING` (timeout, no DELIVERING)
**Key Feature**: System doesn't hang forever waiting for clarification
**Timeout**: 5 minutes (configurable per deployment)

---

## Part 5: Complete Flow Classification Matrix

| Flow # | Name | Primary States | Interruptible Points | Data Persistence | User Experience |
|--------|------|---------------|---------------------|------------------|-----------------|
| 1 | Normal LOW | L->A->D->De->L | D only (brief) | Full | Fast response (~800ms) |
| 2 | Normal MEDIUM | L->A->D->Co->P->De->L | D, Co, P | Full | Progressive (~3-10s) |
| 3 | Normal HIGH | L->A->D->Co->P->De->L | D, Co, P | Full + proactive | Engaged wait (~15-60s) |
| 4 | Clarification (single) | L->A->Cl->A->D->De->L | Cl | Enriched context | Q&A |
| 5 | Max clarification rounds | L->A->(Cl->A)x3->D->... | Cl | Force-proceed | Slightly confused user |
| 6 | Interrupt at DISPATCHING | L->A->D->IH->A->... | D | None (too early) | Clean switch |
| 7 | Interrupt at COMPANIONING | ...->Co->IH->A->... | Co | None (no results yet) | Fresh start |
| 8 | Interrupt at PROGRESSING | ...->P->IH->A->... | P | Partial preserved | Seamless refinement |
| 9 | Interrupt HIGH PROGRESSING | ...->P->IH->A->D->Co->P->De | P | Planner partials | Smart refinement |
| 10 | Clarification interrupt | L->A->Cl->IH->A->... | Cl | Discard | Topic switch |
| 11 | Correction during delivery | ...->De->L->A->D->De->L | None (De not int.) | Full preserved | Next-turn correction |
| 12 | Crisis | L->A->De->L | None | None | Safety response (~25ms) |
| 13 | RED safety | L->A->D->Co->P->De->L | Normal | Full | Cautious, empathetic |
| 14 | AMBER safety | Normal tier flow | Normal | Full | Enhanced logging |
| 15 | Watchdog timeout | ...->P->IH->A->De->L | P (forced) | Partial | Apology + partial |
| 16 | CB degradation cascade | L->A->D->(tier ladder)->De->L | D | Varies | Degraded quality |
| 17 | Multi-message batch | Complex Cl/A interleave | Multiple | Accumulated | Seamless |
| 18 | Clarification then interrupt | L->A->Cl->A->Cl->IH->A->... | Cl (round 2) | Discard | Topic switch |
| 19 | HIL from Planner (approval) | ...->Co->Cl->Co->P->De->L | Cl (HIL) | Full | Approval dialog |
| 20 | HIL rejection | ...->Cl->Co->Cl->Co->... | Cl (HIL) | Varied | Re-try or fail |
| 21 | Proactive injection | ...->Co (stays)->P->De->L | Co (special) | Full + gap fill | Engaged wait |
| 22 | Proactive -- no K0 gaps | ...->Co (stays)->P->De->L | Co | Full | Warmth messages |
| 23 | Crash recovery | N/A | N/A | Checkpoint | Transparent restart |
| 24 | Full fallback | L->A->D->De->L | D | None | Canned response |
| 25 | LLM timeout cascade | Varies | Varies | Varies | Degraded/canned |
| 26 | UltraBERT failure | L->A(heuristic)->D->... | Normal | Degraded Phase 1 | Slightly less accurate |
| 27 | SessionState write failure | Normal flow | Normal | Partial (adapted) | Transparent |
| 28 | Interrupt during HIL | ...->Cl(HIL)->IH->A->... | Cl (HIL) | Planner discarded | Abandon plan |
| 29 | Experience trigger | Normal + turn_end processing | N/A | Full + experience | Transparent |
| 30 | Orchestrator HIL fallback | ...->Co->Cl->Co->... | Cl (fallback) | Full | Choice dialog |
| 31 | User override/cancel | ...->IH->A->D->De->L | Any interruptible | Partial cancel | Confirmation |
| 32 | Clarification timeout | L->A->Cl->L | N/A | None | Abandoned turn |

---

## Part 6: LLM as the Heart of the Concierge -- How Flows Are Driven, Not Hardcoded

### 6.1 The Core Thesis: Rails, Not Tracks

None of the 32 flows above are hardcoded execution paths. There is no `if intent == "weather": run_weather_flow()` anywhere in the system. Instead, the architecture provides **rails** (FSM states, transition guards, tool schemas, budget limits, safety bands) and the **LLM drives the conversation naturally within those rails**.

The FSM is a **safety harness**, not a choreographer. It answers: "What is the system allowed to do right now?" The LLM answers: "What should the system actually do?"

```
+--------------------------------------------------------------------+
|                      WHAT IS HARDCODED (Rails)                     |
+--------------------------------------------------------------------+
| - 8 FSM states and 14 valid transitions                           |
| - Phase 1 UltraBERT classification (22ms, deterministic)          |
| - Safety bands (GREEN/AMBER/RED/CRISIS)                           |
| - Tier routing (LOW/MEDIUM/HIGH complexity thresholds)             |
| - Tool budget limits per tier (6/12/20 calls)                     |
| - Clarification round limit (3 max, CONC-08)                     |
| - Watchdog timer (120s, CONC-15)                                  |
| - Circuit breaker thresholds and fallback chains                  |
| - CRISIS static response (zero dependencies)                     |
| - MutationGuard size limits (HOT 48KB, sections budgeted)        |
| - ACK-first tool bundle validation                                |
| - Interruptibility matrix (which states allow interrupt)          |
+--------------------------------------------------------------------+

+--------------------------------------------------------------------+
|                      WHAT THE LLM DECIDES (Driver)                 |
+--------------------------------------------------------------------+
| - Whether to ask a clarifying question or proceed                 |
| - What to say in every response (tone, content, length)           |
| - Which tools to call and in what order                           |
| - Whether to acknowledge with "progress", "commit", or "closure" |
| - What beliefs to write, update, or correct                      |
| - How to frame errors and partial results to the user             |
| - Whether to refine UltraBERT's emotion classification            |
| - When to shift narrative threads or push QUD                     |
| - How to phrase HIL approval requests from Planner naturally      |
| - How to handle user corrections (detect, apologize, fix)        |
| - What to do when a tool fails (retry differently, inform user)   |
| - Whether a user response is a clarification answer or interrupt  |
+--------------------------------------------------------------------+
```

### 6.2 The LLM Never Sees "Flows" -- It Sees Context + Tools + Rules

The LLM receives a **DynamicPromptBuilder**-assembled system prompt every turn. This prompt contains NO flow diagrams, NO state machine specifications, NO "you are in Flow 7." Instead, it contains:

```
[IDENTITY]          -> Who you are (FamilyOS Concierge for {family_name})
[SESSION CONTEXT]   -> Live SessionState snapshot (beliefs, emotions, tasks, history)
[ALREADY RESOLVED]  -> Pre-grounded references ("Mom" = Sarah Chen, LOCKED)
[CLASSIFICATION]    -> Phase 1 output (intent, safety, entities, emotions, tier)
[PLAN CONTEXT]      -> Active Planner state if HIGH tier (step N of M)
[TOOLS AVAILABLE]   -> Tier-filtered tool schemas (8 for LOW, 13 for MEDIUM/HIGH)
[TOOL CALLING RULES]-> ACK-first, budget limits, pairing rules
[RESPONSE STYLE]    -> Tone hints from Experience Layer (warmth, formality, encouragement)
[CONSTRAINTS]       -> Max tool calls, timeout, max tokens
```

The LLM reads this context and **decides what to do**. Every "flow" in Part 4 is an emergent behavior of the LLM operating within the rail system, not a pre-programmed script.

### 6.3 How the LLM Drives Each Flow Category

#### 6.3.1 Normal Flows (1-3) -- LLM Chooses Tools Naturally

The LLM doesn't know it's in a "LOW tier flow." It knows:

- It has 8 tools available (LOW allowlist)
- The user asked "What's the weather in London?"
- Phase 1 says: intent=weather, safety=GREEN, tier=LOW
- It has `invoke_capability` available

So it naturally decides:

1. Call `acknowledge(ack_type="progress", message="Checking London weather...", next_tool="invoke_capability")`
2. Call `invoke_capability(capability="tool.read.weather_api", params={city: "London"})`
3. Read the tool result
4. Formulate a natural response: "It's 12C in London with partly cloudy skies."

If the user had asked something complex like "Plan a trip," the LLM would see MORE tools (discover_capabilities, execute_workflow, spawn_via_fabric) and Phase 1 would say tier=HIGH. The LLM would naturally use those richer tools. **The tier system doesn't tell the LLM what flow to run; it constrains which tools are available**, and the LLM self-organizes.

#### 6.3.2 Clarification Flows (4-5) -- LLM Asks Because It Genuinely Needs Info

There is no `ClarificationEngine` that decides to ask questions. The LLM itself, seeing the context:

```
[CLASSIFICATION FROM PHASE 1]
  Intent: set_reminder (confidence: 0.45)  <-- low confidence
  Entities: ["her" -> PRONOUN, UNRESOLVED]
  Gaps detected by Phase 1: ENTITY_MISSING, TIME_AMBIGUOUS
```

...naturally concludes it cannot proceed and asks: "I'd be happy to set a reminder! Who would you like me to remind you about, and when?"

The FSM simply notices "the LLM produced text but no tools that would trigger DISPATCHING" and transitions to CLARIFYING. When the user responds, the FSM feeds the enriched input back through Phase 1 and gives the LLM another chance. The LLM now sees resolved context and proceeds.

The CONC-08 guard (3 max rounds) is NOT the LLM deciding to stop. It's the FSM **overriding** the LLM: "You've asked 3 times, proceed with what you have." This is a rail, not a track.

#### 6.3.3 Interrupt Flows (6-10) -- LLM Doesn't Handle Interrupts, FSM Does

Interrupt detection is **entirely FSM infrastructure**. The LLM has no concept of "interrupt." What happens:

1. `IInputPort.has_buffered()` returns true (polled between tool calls)
2. FSM checks if current state is interruptible
3. If yes: FSM cancels in-flight work, runs abbreviated turn_end, creates fresh context
4. New message enters Phase 1 as a completely fresh turn
5. LLM receives fresh context and has no idea a previous turn was interrupted

The LLM's job is simply to respond well to whatever context it receives. If partial results from a cancelled turn are injected into the new context via ContextAssembler, the LLM uses them naturally. The LLM doesn't "handle interrupts" -- it just sees richer context on the next turn.

#### 6.3.4 Safety Flows (12-14) -- FSM Applies Safety, LLM Adapts to Constraints

Safety enforcement is a **layered system** where the FSM and infrastructure act BEFORE the LLM:

| Layer | Component | Decision |
|-------|-----------|----------|
| 1 | UltraBERT safety head | Classify safety band (22ms, deterministic) |
| 2 | SafetyGate | CRISIS -> bypass EVERYTHING, emit static response (LLM never runs) |
| 3 | ComplexityRouter | RED -> force MEDIUM minimum tier (LLM gets more tools/budget) |
| 4 | ToolDispatcher | RED -> block action tools (LLM can only use cognitive/read) |
| 5 | DynamicPromptBuilder | Inject safety_band into prompt, inject tone hints (warmth=HIGH for RED) |
| 6 | **LLM** | Responds empathetically, WITHIN the constraints already applied |

For CRISIS, the LLM never even executes. The static response is hardcoded. For RED, the LLM runs but with restricted tools -- it cannot accidentally book a flight while the user is expressing distress. For AMBER, the LLM runs normally but sees tone hints suggesting empathy.

The LLM doesn't decide safety policy. It responds naturally within whatever safety constraints the infrastructure has applied.

#### 6.3.5 Degradation Flows (16, 24-27) -- LLM Adapts to Failures Via Tool Results

When a circuit breaker opens or a tool fails, the LLM receives **structured error feedback**:

```python
ToolResult(
    success=False,
    data={
        "error_code": "CB_OPEN",
        "error_message": "Orchestrator unavailable. Consider simpler approach."
    }
)
```

The LLM then decides how to respond. It might:

- Try a different tool (`invoke_capability` directly instead of `execute_workflow`)
- Inform the user: "I'm having trouble with that right now. Let me try a simpler approach..."
- Use `summarize_context` to compress and retry with less context

The tier degradation cascade (HIGH->MEDIUM->LOW->CANNED) is Concierge infrastructure, but within each tier, the LLM freely chooses its strategy. Only when ALL tiers are exhausted does the system fall back to canned templates (this is the one case where the LLM is bypassed entirely, similar to CRISIS).

#### 6.3.6 HIL Flows (19-20, 28, 30) -- LLM Frames Machine Requests as Natural Conversation

When the Planner needs human approval, the raw event looks like:

```json
{
  "request_id": "hil-7291",
  "context": "Flight package: $2500 round-trip, Rome, Mar 15-22",
  "options": ["approve", "reject", "modify"]
}
```

The LLM receives this as context and frames it naturally: "I've found a flight package for $2,500 -- round trip to Rome, March 15 to 22. Should I go ahead and book it?"

This is critical: the Planner emits structured data, but the **LLM is what makes it feel like a natural conversation.** A different LLM with different personality training would phrase the same approval request differently. The FSM doesn't care how the LLM phrases it -- it only cares that the CLARIFYING state tracks the pending approval and routes the user's response back correctly.

#### 6.3.7 Proactive Flows (21-22) -- LLM Weaves Gap-Filling Into Natural Conversation

K0 emits structured gap data:

```json
{
  "gap_type": "STALE_ANCHOR",
  "subject": "Emma",
  "attribute": "piano_lessons",
  "question_blueprint": "How are {subject}'s piano lessons going?"
}
```

The ProactiveAgent feeds this to the LLM during COMPANIONING idle time. The LLM transforms the mechanical question blueprint into: "While I'm planning your trip -- you mentioned last week that Emma started piano lessons. How's that going?"

The LLM makes it conversational, adds temporal context ("last week"), and connects it naturally to what the user is currently doing. Without the LLM, it would be an awkward questionnaire.

### 6.4 The ReAct Loop is the Universal Execution Engine

Every flow in Part 4 runs through the SAME ReAct agentic loop (Section 7.5 of concierge.md):

```python
while iteration < MAX_TOOL_ITERATIONS:
    response = await llm.complete_with_tools(system_prompt, messages, tools)

    if not response.tool_calls:
        final_content = response.content  # LLM done, no more tools
        break

    # Validate tool bundle (ACK-first, pairing, budget)
    validation = validate_tool_bundle(response.tool_calls)
    if validation.errors:
        messages.append(error_feedback)  # LLM learns from mistake
        continue

    # Execute tools, feed results back
    for call in response.tool_calls:
        result = tool_executor.execute(call)
        if call.name == "acknowledge":
            stream_to_user(result)  # Immediate display
    messages.append(tool_results)
```

This loop is identical whether:

- The LLM is handling a simple weather query (1 iteration, 2 tools)
- The LLM is processing a complex trip plan (6 iterations, 15 tools)
- The LLM is recovering from a tool failure (retry in next iteration)
- The LLM is writing beliefs after learning new family information

The flow "shape" (which states the FSM visits) emerges from what tools the LLM calls and what results they produce. The FSM transitions are reactive consequences of LLM decisions, not pre-programmed paths.

### 6.5 How the LLM Self-Corrects Within the Rails

The LLM doesn't always get it right on the first try. The rail system provides structured feedback that lets it adapt:

| LLM Mistake | Rail Response | LLM Recovery |
|-------------|---------------|--------------|
| Calls `invoke_capability` without `acknowledge` first | ToolBundleValidator rejects bundle, feeds error back | LLM re-emits with acknowledge + tool pair |
| Calls `spawn_via_fabric` at LOW tier | Allowlist check rejects, feeds "tool not available at LOW tier" | LLM uses `invoke_capability` instead |
| Exceeds tool call budget (e.g., 7th call on LOW) | ToolBudgetExhaustedError forces final response | LLM synthesizes answer from available results |
| Writes beliefs_active beyond 8KB | MutationGuard rejects with CAPACITY error | LLM calls `promote_belief(hot_to_k0)` to free space, retries |
| Asks user a question already resolved | ContextResolver LOCKED refs in prompt prevent re-asking | LLM sees "Mom = Sarah Chen (LOCKED)" and uses it directly |
| Gives vague acknowledgment ("got it") | ToolBundleValidator warns (non-blocking) | Next iteration, LLM gives specific: "Setting reminder for 3pm" |

This feedback loop means the LLM improves within a single turn. Iteration 1 might be rejected, iteration 2 succeeds. The user sees only the successful output.

### 6.6 Why This Architecture Supports Natural Conversation

Traditional chatbot architectures have:

- Hardcoded intent-to-handler routing: `intent_weather -> WeatherHandler.execute()`
- Predefined dialog trees: if user says X, respond with Y
- State machines that prescribe behavior: `BOOKING_STATE -> ask_date -> ask_guests -> confirm`

The Concierge architecture inverts this:

| Aspect | Traditional | Concierge |
|--------|-------------|-----------|
| **Who decides flow?** | Developer at build time | LLM at runtime |
| **How are intents handled?** | One handler per intent | LLM decides strategy per context |
| **How is clarification done?** | Slot-filling rules | LLM asks naturally, FSM tracks rounds |
| **How are errors shown?** | Canned error messages | LLM crafts contextual apology |
| **How does tone adapt?** | Static per-persona | Experience Layer feeds dynamic hints to LLM |
| **How is safety enforced?** | Block/allow lists | Multi-layered: UltraBERT + SafetyGate + ToolDispatcher + LLM |
| **How does conversation evolve?** | Doesn't (static handlers) | LLM learns within session via SessionState writes |

### 6.7 The Contract Between FSM and LLM

The FSM and the LLM have a clear contract:

**FSM promises to the LLM:**

1. You will always receive accurate, fresh context (DynamicPromptBuilder rebuilds every turn)
2. You will only see tools you are allowed to use (tier-filtered allowlist)
3. References are pre-resolved so you don't re-ask (LOCKED refs in prompt)
4. If you need more info, ask -- I'll manage the CLARIFYING state for you
5. Your tool calls will be validated BEFORE execution -- you'll get error feedback, not silent failures
6. Your cognitive writes will be guarded -- you can't accidentally corrupt SessionState
7. Timing is handled -- you don't need to worry about timeouts or deadlines

**LLM promises to the FSM:**

1. I will call acknowledge() before effectful tools (ACK-first contract)
2. I will not exceed the tool budget (if forced to stop, I'll synthesize from available data)
3. I will respect LOCKED references (never re-ask what's already resolved)
4. I will use the appropriate response style (tone hints from Experience Layer)
5. I will frame HIL requests naturally (not dump raw data to user)
6. I will adapt to tool failures (try alternatives or inform user gracefully)

### 6.8 What Happens If You Swap the LLM?

Because the LLM is the driver within a rail system, swapping LLMs changes the **personality** of the flows but not their **safety properties**:

| Property | LLM-dependent? | Why? |
|----------|----------------|------|
| Response tone and warmth | Yes | LLM personality varies |
| Which tools are called in which order | Yes | Different reasoning strategies |
| Whether clarification is asked | Partially | LLM decides, but CONC-08 caps at 3 rounds |
| Safety response to CRISIS | **No** | Static response, LLM bypassed entirely |
| Tool budget enforcement | **No** | Infrastructure, not LLM |
| Interrupt handling | **No** | FSM infrastructure, LLM never involved |
| Data integrity (MutationGuard) | **No** | Infrastructure, LLM writes are guarded |
| Tier routing | **No** | UltraBERT (Phase 1), not LLM |
| Safety band classification | **No** | UltraBERT head, not LLM |
| Watchdog timeout | **No** | Infrastructure timer |

This is the power of the rails-not-tracks design: **safety is infrastructure, personality is LLM.** You can hot-swap GPT-4o for Claude for Gemini, and the safety properties hold. The conversation quality changes, but the invariants don't.

### 6.9 Emergent Behaviors -- Flows the FSM Doesn't Know About

Because the LLM drives tool selection, it can produce behaviors that weren't explicitly designed as flows:

1. **Spontaneous belief correction**: User says "Mom isn't allergic to peanuts anymore, she got desensitized." LLM calls `update_beliefs(operation="correct_fact", subject="Mom", predicate="allergic_to", object_value="peanuts_REMOVED")`. No "correction flow" exists -- the LLM just uses cognitive tools naturally.

2. **Multi-domain turns**: User asks "Book Italian for Saturday and remind me to call Mom at 3pm." A traditional system would need a "multi-intent handler." Here, the LLM naturally chains: acknowledge -> invoke_capability(restaurant) -> acknowledge -> invoke_capability(reminder) within the same ReAct loop.

3. **Emotional course-correction**: LLM detects sarcasm that UltraBERT classified as "happy." Calls `refine_affect(override_emotion="frustration", reasoning="user said 'great, just great' -- sarcastic tone")`. Experience Layer picks this up on the next turn and adjusts warmth.

4. **Contextual follow-ups**: After booking a restaurant, LLM remembers (from beliefs_active) that Dad is diabetic. Asks "Any dietary restrictions I should let the restaurant know about? I remember your dad is diabetic." This isn't a flow -- it's the LLM reading context and acting naturally.

5. **Graceful degradation narrative**: When the Orchestrator is down, instead of a robotic "Service unavailable," the LLM crafts: "I'm having a bit of trouble with my planning tools right now. Let me try a simpler approach -- how about I just search for restaurants directly?"

These emergent behaviors are the entire point. The FSM provides safety; the LLM provides humanity.

### 6.10 Summary: The Architecture of Natural Conversation

```
+------------------------------------------------------------------+
|                     CONVERSATION STACK                            |
+------------------------------------------------------------------+
|                                                                  |
|  Layer 5: NATURAL LANGUAGE                                       |
|  ┌──────────────────────────────────────────────────┐            |
|  │ LLM (ReAct loop)                                 │            |
|  │ - Reads context, decides action, calls tools     │            |
|  │ - Generates natural responses                     │            |
|  │ - Self-corrects on validation errors              │            |
|  │ - Frames machine data as human conversation       │            |
|  └──────────────────────────────────────────────────┘            |
|                         |                                        |
|  Layer 4: TOOLS + CONTEXT                                        |
|  ┌──────────────────────────────────────────────────┐            |
|  │ DynamicPromptBuilder + ToolDispatcher + 13 Tools  │            |
|  │ - Assembles live context every turn               │            |
|  │ - Validates tool calls (schema, budget, ACK-first)│            |
|  │ - Routes to ports (State, Memory, Fabric, Output) │            |
|  │ - Feeds errors back to LLM for self-correction    │            |
|  └──────────────────────────────────────────────────┘            |
|                         |                                        |
|  Layer 3: SAFETY + ROUTING                                       |
|  ┌──────────────────────────────────────────────────┐            |
|  │ UltraBERT + SafetyGate + ComplexityRouter         │            |
|  │ - 22ms deterministic classification (12 heads)    │            |
|  │ - Safety band enforcement (CRISIS bypass)         │            |
|  │ - Tier assignment + tool allowlist filtering       │            |
|  │ - Pre-grounding: entities, time, references       │            |
|  └──────────────────────────────────────────────────┘            |
|                         |                                        |
|  Layer 2: STATE MACHINE (Rails)                                  |
|  ┌──────────────────────────────────────────────────┐            |
|  │ FSMController + 8 states + 14 transitions         │            |
|  │ - Tracks what phase the system is in              │            |
|  │ - Enforces interruptibility rules                 │            |
|  │ - Guards: max rounds, watchdog, budget            │            |
|  │ - Crash recovery + experience triggers            │            |
|  └──────────────────────────────────────────────────┘            |
|                         |                                        |
|  Layer 1: INFRASTRUCTURE                                         |
|  ┌──────────────────────────────────────────────────┐            |
|  │ 8 Hexagonal Ports + 7 Circuit Breakers            │            |
|  │ - Input/Output transport (WebSocket/SSE)          │            |
|  │ - SessionState (HOT/WARM/COLD with MutationGuard) │            |
|  │ - Fabric/Orchestrator/Planner dispatch            │            |
|  │ - K0 Bridge for long-term memory                  │            |
|  │ - Delta Bus for observability                     │            |
|  └──────────────────────────────────────────────────┘            |
|                                                                  |
+------------------------------------------------------------------+
```

The LLM sits at the top of this stack. It is the only component that generates user-facing language. Everything below it exists to:

1. Give it accurate context (Layers 3-4)
2. Constrain its behavior to safe boundaries (Layers 2-3)
3. Execute its decisions reliably (Layer 1)

This is why the 32 flows in Part 4 are **descriptions of emergent behavior**, not specifications of hardcoded paths. The same architecture produces all 32 flows -- and infinitely many more that haven't been enumerated -- because the LLM naturally adapts to whatever context and constraints it receives.

---

### 6.11 Can ANY LLM Drive the Concierge? -- Minimum Capability Requirements

The short answer is **no**. Not every LLM can drive the Concierge. The architecture imposes a hard capability floor below which a model cannot function at all, and a soft capability floor below which the experience degrades to the point of uselessness.

This section is the definitive analysis of what an LLM must be able to do, what happens when it cannot, and which model classes fit where.

#### 6.11.1 The Five Hard Requirements (Non-Negotiable)

These are binary. A model either meets them or it cannot drive the Concierge at all. There is no graceful degradation -- the turn simply fails.

| # | Requirement | Why It Is Mandatory | What Breaks Without It |
|---|-------------|---------------------|----------------------|
| **H1** | **Function/Tool Calling** | The ReAct loop (Section 7.5) requires the LLM to emit structured `tool_calls` in its response. Every single flow in Part 4 depends on the LLM calling at least `acknowledge()`. The ACK-first rule (Section 7.3) makes tool calling the prerequisite for any effectful action. | ToolBundleValidator receives no `tool_calls` array. ReAct loop terminates at iteration 1 with no tools executed. Every turn beyond simple chat degrades to text-only, which triggers DELIVERING without any context enrichment, memory writes, or task execution. The model becomes a chatbot with amnesia. |
| **H2** | **Sufficient Context Window** | DynamicPromptBuilder (Section 7.4) assembles a system prompt with 9 sections: IDENTITY, SESSION CONTEXT, ALREADY RESOLVED, CLASSIFICATION, PLAN CONTEXT, TOOLS AVAILABLE (up to 13 tool schemas), TOOL CALLING RULES, RESPONSE STYLE, CONSTRAINTS. Plus the full conversation history managed by ContextAssembler. CONC-22 mandates 128K context window. | If the model's context window is too small, the assembled prompt gets truncated. The LLM loses tool schemas (cannot call tools it cannot see), loses ALREADY RESOLVED references (re-asks questions that were already answered), loses SESSION CONTEXT (forgets who the family members are). ContextAssembler triggers summarization at 80% of the window (102,400 tokens for 128K). A model with 4K context cannot even fit the system prompt alone. |
| **H3** | **Multi-Turn Structured Reasoning** | The ReAct loop runs up to MAX_TOOL_ITERATIONS = 10. Each iteration feeds tool results back to the LLM. The model must read the result of `acknowledge()`, understand the confirmation, then decide whether to call the next tool or produce a final response. For MEDIUM/HIGH tiers, chains of 2-6 iterations are typical. | A model that cannot track state across iterations will repeat tool calls, ignore tool results, or produce incoherent tool sequences. ToolBundleValidator catches invalid bundles and feeds errors back, but a model that cannot learn from these errors within the same turn will exhaust all 10 iterations producing nothing. The cascade falls to CANNED_RESPONSE. |
| **H4** | **Reliable Instruction Following** | The system prompt contains explicit rules: ACK-first ordering, LOCKED reference compliance, budget limits, tool allowlist adherence. ToolBundleValidator rejects violations structurally. But the LLM must follow these instructions at a high enough success rate that it does not burn through iteration budget on validation retries. | A model that follows instructions 50% of the time will spend half its iteration budget on ToolBundleValidator rejections. For LOW tier (max 3 LLM calls), one failed validation leaves only 2 attempts to complete the entire turn. For a 5-tool workflow, that is not enough. The failure rate compounds: P(success) = P(valid_per_call)^N, where N is the number of tool calls needed. |
| **H5** | **Structured Output Fidelity** | Tool calls must conform to exact JSON schemas. The 13 tool schemas include complex parameter types: nested objects (MemoryQuery), enums (AckType, SignalType), arrays (entity lists), optional fields with semantic meaning. `validate_tool_bundle()` performs strict schema validation. | Malformed JSON, wrong parameter names, missing required fields, or type mismatches all cause instant rejection. Unlike chat quality (which degrades gracefully), schema compliance is binary: the call either parses or it does not. Models that hallucinate parameter names or cannot produce nested JSON reliably will fail validation on every attempt. |

#### 6.11.2 The Soft Requirements (Graceful Degradation)

These affect quality, not functionality. A model that meets all five hard requirements but misses soft requirements will produce technically correct but experientially poor conversations.

| # | Requirement | Effect When Present | Effect When Absent |
|---|-------------|--------------------|--------------------|
| **S1** | Emotional nuance | `refine_affect()` tool used appropriately; tone matches user mood | Flat, robotic responses. Affect detection exists (Phase 1 UltraBERT), but the LLM ignores it. Family members feel unheard. |
| **S2** | Natural framing | Machine data wrapped in conversational language ("I found a great Italian place..." vs "Result: restaurant_name=Luigi's") | Technically correct but transactional. The experience feels like a search engine, not a family assistant. |
| **S3** | Sophisticated clarification | Asks targeted, minimal questions; combines related unknowns into single ask | Broad, repetitive clarification questions. Burns through the 3-round clarification limit (CONC-08) without resolving ambiguity. |
| **S4** | Proactive connection | Connects current request to stored context ("Since you mentioned Sarah is vegetarian last time...") | Technically correct but misses opportunities. Memory is read but not leveraged conversationally. |
| **S5** | Tone adaptation | Adjusts formality, humor, directness based on persona and affect | One-size-fits-all tone. Sounds the same when a child asks a fun question as when a parent asks about scheduling. |

#### 6.11.3 Model Class Analysis: Who Can and Cannot Drive the Concierge

```
+----------------------------------------------------------------------+
|                    LLM CAPABILITY SPECTRUM                           |
+----------------------------------------------------------------------+
|                                                                      |
|  TINY (1-3B params)          SMALL (7-13B)        LARGE (70B+/API)  |
|  Phi-3-mini, TinyLlama       Mistral-7B,          GPT-4o, Claude,   |
|  Gemma-2B, Qwen-2.5-1.5B     Llama-3.1-8B,        GPT-4o-mini,     |
|                               Phi-3-medium         Llama-3.1-70B    |
|                                                                      |
|  H1 Function Calling:  FAIL  H1: PARTIAL           H1: PASS         |
|  Most tiny models lack        Some support it,      Native support   |
|  function calling entirely.   quality varies.       in all frontier  |
|  Those that do: unreliable    Llama-3.1-8B has it   models and most  |
|  schema compliance.           but struggles with    70B+ open models.|
|                               complex schemas.                       |
|                                                                      |
|  H2 Context Window:    FAIL  H2: MARGINAL          H2: PASS         |
|  Typically 2K-4K native.      8K-32K typical.       128K standard    |
|  Cannot fit system prompt     Can fit LOW tier      for GPT-4o,      |
|  + 13 tool schemas.          prompts. Cannot       Claude, Gemini.  |
|                               sustain 10-iteration  Full CONC-22     |
|                               conversations.        compliance.      |
|                                                                      |
|  H3 Multi-Turn:        FAIL  H3: PARTIAL           H3: PASS         |
|  Lose coherence after         Track 2-3 iterations  Reliable across  |
|  1-2 tool result cycles.      then drift. Work for  10 iterations    |
|  Cannot sustain ReAct loop.   LOW tier (1-2 iter).  with tool result |
|                                                     integration.     |
|                                                                      |
|  H4 Instruction Follow: FAIL H4: PARTIAL           H4: PASS         |
|  Ignore system prompt rules   Follow most rules     High compliance  |
|  >40% of the time.           but miss edge cases   rate (>95%).     |
|  ACK-first compliance <50%.   (ACK-first pairing,  ToolBundleValid- |
|                               LOCKED ref respect).  ator rarely      |
|                                                     rejects.         |
|                                                                      |
|  H5 Schema Fidelity:   FAIL  H5: PARTIAL           H5: PASS         |
|  Cannot produce nested JSON   Handle simple schemas Handle all 13    |
|  reliably. Hallucinate        (acknowledge, signal) concierge tool   |
|  parameter names.             but fail on complex   schemas with     |
|                               ones (search_memory,  correct nesting, |
|                               schedule_task).       types, enums.    |
|                                                                      |
|  VERDICT: CANNOT DRIVE       VERDICT: LOW TIER     VERDICT: FULL    |
|  Not viable for any tier.    ONLY, with caveats.   CAPABILITY.      |
|  Would exhaust iteration     Needs constrained     Can drive all    |
|  budget on every turn and    tool allowlist and    32 flows across  |
|  cascade to CANNED.          close monitoring.     all tiers.       |
|                                                                      |
+----------------------------------------------------------------------+
```

#### 6.11.4 The Self-Correction Safety Net -- And Why It Has Limits

The architecture includes a powerful self-correction mechanism (Section 6.5). When ToolBundleValidator rejects a tool call, it returns a structured error:

```
ValidationError:
  tool: "acknowledge"
  field: "next_tool"
  error: "next_tool='search_memory' but acknowledge was not called first"
  hint: "Call acknowledge() before any effectful tool"
```

This error is injected into the LLM's context for the next iteration. A capable model reads this, understands the violation, and corrects its behavior. This is how the rail system self-heals.

**But self-correction has a hard ceiling**: the iteration budget.

```
+---------------------------------------------------------------------+
|              SELF-CORRECTION BUDGET ANALYSIS                        |
+---------------------------------------------------------------------+
|                                                                     |
|  Tier      LLM Calls   Tool Calls   Useful Iterations If           |
|            Budget       Budget       50% Validation Fail Rate       |
|  -------   ---------   ----------   ---------------------------     |
|  LOW       3           6            1.5 useful (need 1-2)  RISKY   |
|  MEDIUM    5           12           2.5 useful (need 2-4)  TIGHT   |
|  HIGH      10          20           5.0 useful (need 3-6)  MAYBE   |
|                                                                     |
|  At 50% validation failure (typical small model):                   |
|    LOW tier has ~50% chance of completing a simple turn             |
|    MEDIUM tier has ~40% chance of completing a multi-step turn      |
|    HIGH tier is impossible (would need 6-12 successful calls)       |
|                                                                     |
|  At 90% validation success (typical frontier model):                |
|    LOW tier: 99.7% completion rate                                  |
|    MEDIUM tier: 98.4% completion rate                               |
|    HIGH tier: 95.1% completion rate                                 |
|                                                                     |
|  At 95% validation success (ideal):                                 |
|    All tiers effectively never fail on validation                   |
|                                                                     |
+---------------------------------------------------------------------+
```

The self-correction mechanism turns a 90%-capable model into a 99%-reliable system. But it cannot turn a 50%-capable model into a reliable one. The math does not work: too many iterations are consumed by retries, leaving too few for actual work.

#### 6.11.5 The Architecture Already Knows This -- ILLMPort Capability Routing

The Concierge does not assume all models are equal. The architecture explicitly models model capabilities through `ILLMPort`:

```python
def available_capabilities(self) -> FrozenSet[str]:
    """Return currently available LLM capabilities.
    Returns subset of: {"CHAT", "TOOL_CALL", "STRUCTURED", "VISION", "REASON"}
    """
```

The `HubRequest` includes a `capability` tag that routes to different models:

| Capability | Purpose | Typical Model | Minimum Requirement |
|-----------|---------|---------------|---------------------|
| `CHAT` | Final response generation | GPT-4o / Claude | Basic text generation. Even canned responses qualify. |
| `TOOL_CALL` | ReAct agentic loop | GPT-4o / Claude | **Full function calling + multi-turn reasoning**. This is the hard bar. |
| `STRUCTURED` | JSON schema extraction | GPT-4o-mini | Reliable JSON output. Smaller models can do this. |
| `VISION` | Image understanding | GPT-4o | Multimodal input. Specialized capability. |
| `REASON` | Complex multi-step reasoning | o1 / Claude | Extended reasoning chains. Only reasoning-class models. |

The key insight: **TOOL_CALL capability is the gatekeeper**. A model that cannot do TOOL_CALL cannot drive the ReAct loop, which means it cannot drive any flow beyond simple chat. And TOOL_CALL requires all five hard requirements simultaneously.

The LLM cascade makes this explicit:

```
L1: Primary provider (GPT-4o / Claude) ----> Full TOOL_CALL capability
    |
    v (on failure)
L2: Different provider / model -----------> Still needs TOOL_CALL
    |
    v (on failure)
L3: CANNED_RESPONSE (CB OPEN) ------------> No LLM at all. Pre-written templates.
```

There is no L2.5 that says "use a tiny model for degraded tool calling." The cascade goes from full-capability models directly to canned responses. The architecture does not attempt to use a less capable model for agentic work -- it would rather bypass the LLM entirely than use one that will waste iteration budget failing.

#### 6.11.6 Tier-Specific Model Viability Matrix

Could the architecture route different tiers to different model sizes? In theory, yes. In practice, the requirements are still steep for all tiers:

| Tier | Min Context Needed | Tool Calls | Iteration Depth | Min Viable Model Class |
|------|-------------------|------------|-----------------|----------------------|
| **LOW** | ~8K-16K (system prompt + short history + 8 tool schemas) | 1-6 (typically 2-3: acknowledge + 1 tool) | 1-2 iterations | Small/medium with reliable function calling (GPT-4o-mini, Llama-3.1-70B) |
| **MEDIUM** | ~16K-32K (+ longer history + 13 schemas + tool results) | 2-12 (typically 4-8: acknowledge + multi-step) | 2-4 iterations | Medium/large with strong function calling (GPT-4o-mini, Claude Haiku, Llama-3.1-70B) |
| **HIGH** | ~32K-64K (+ plan context + multi-step history + all results) | 3-20 (orchestrated multi-step with Planner) | 3-6 iterations | Large frontier only (GPT-4o, Claude Sonnet/Opus, Llama-3.1-405B) |
| **CRISIS** | ~4K (minimal prompt, no tools) | 0 (tools disabled) | 0 (safety template only) | Any model or no model (canned CRISIS response) |

**Critical observation**: Even LOW tier requires a model that can reliably produce structured `tool_calls` for `acknowledge()` + at least one cognitive/read tool, follow ACK-first ordering, and handle a system prompt with 8 tool schemas. This rules out most sub-7B models.

#### 6.11.7 The Bottom Line

```
+----------------------------------------------------------------------+
|                    CAN THIS MODEL DRIVE THE CONCIERGE?               |
+----------------------------------------------------------------------+
|                                                                      |
|  Model Type               LOW    MEDIUM    HIGH    All 32 Flows?    |
|  -----------------------  -----  --------  ------  ---------------  |
|  Tiny (1-3B)              NO     NO        NO      NO               |
|  Small (7-13B)            MAYBE  NO        NO      NO               |
|  Medium API (mini class)  YES    PARTIAL   NO      NO               |
|  Large Frontier            YES    YES       YES     YES              |
|  Reasoning (o1/R1 class)  YES    YES       YES     YES (REASON cap) |
|                                                                      |
|  "MAYBE" = Works if validation failure rate <30% AND turn is simple  |
|  "PARTIAL" = Works for 2-3 step workflows, fails on 5+ step ones    |
|                                                                      |
+----------------------------------------------------------------------+
```

**The definitive answer**: The Concierge cannot be driven by "any" LLM. The minimum viable model for full capability is a **frontier-class model with native function calling, 128K context window, and >90% instruction-following compliance**. Smaller models can handle LOW-tier turns if they support reliable tool calling, but they cannot sustain the multi-iteration, multi-tool workflows that MEDIUM and HIGH tiers require. Tiny models (sub-7B) are completely non-viable -- they would exhaust the iteration budget on ToolBundleValidator rejections and cascade to canned responses on virtually every turn.

The architecture is honest about this. It does not try to make small models work for agentic tasks. The LLM cascade goes directly from capable models to canned responses, with no middle ground. The rails protect the user experience by catching failures early, but they cannot manufacture capability that the model does not have.

---

## Part 7: Key Design Principles and Insights

### 1. Interruptible vs Non-Interruptible States

| Category | States | Rationale |
|----------|--------|-----------|
| **Interruptible** | DISPATCHING, COMPANIONING, PROGRESSING, CLARIFYING | Work-in-progress can be cancelled safely |
| **Non-Interruptible** | LISTENING, ACKING, DELIVERING, INTERRUPT_HANDLING | Atomic operations must complete for data integrity |

ACKING is non-interruptible because Phase 1 takes only 22ms and produces safety classification -- interrupting could miss a CRISIS detection. DELIVERING is non-interruptible because final response + cognitive writes + checkpoint must be atomic.

### 2. Data Preservation Rules on Interrupt

| Interrupt Point | Partial Results Available | Action |
|----------------|--------------------------|--------|
| DISPATCHING | None (dispatch hasn't started) | Discard everything, fresh start |
| COMPANIONING (no results) | None (backend started but no deltas yet) | Discard, fresh start |
| COMPANIONING (HIL pending) | HIL request context | Discard, cancel Planner pipeline |
| PROGRESSING (with results) | Completed step outputs | PRESERVE partial results, feed into new context |
| CLARIFYING | Clarification context only | Discard if topic changed, keep if topic same |

### 3. Clarification Recognition Logic

The system distinguishes between a clarification answer (same topic) and an interrupt (new topic) using IntentProcessor:

- **Same topic**: Incoming message fills a pending gap slot (entity, time, constraint)
- **New topic**: Incoming message's classified intent doesn't match any pending gap type
- **Edge case**: Multi-message batch where rapid messages may be clarification answers queued before the question was even displayed

### 4. Degradation is Concierge-Owned

Orchestrator NEVER auto-degrades. The tier degradation cascade is entirely Concierge's responsibility:

```
HIGH -> MEDIUM: Drop Planner, keep 2 Fabric calls
MEDIUM -> LOW: Drop Orchestrator, use direct ToolDispatcher
LOW -> CANNED: Drop Fabric/LLM, use template response
```

### 5. Safety Band Hierarchy

| Band | Routing Impact | Tool Restrictions | Tone Impact |
|------|---------------|-------------------|-------------|
| GREEN | Normal | None | Normal |
| AMBER | Normal | None (enhanced logging) | Empathetic framing |
| RED | Override to MEDIUM min | Action tools BLOCKED | HIGH warmth, cautious |
| CRISIS | BYPASS all FSM states | ALL tools blocked | Static safety response |

### 6. CLARIFYING State Serves Three Purposes

The CLARIFYING state is polymorphic -- it handles three different sources of clarification need:

| Source | Entry | Exit | Round Counting |
|--------|-------|------|---------------|
| **LLM-originated** (gaps detected) | ACKING -> CLARIFYING | CLARIFYING -> ACKING | Counts against CONC-08 (3 max) |
| **Planner HIL** (approval/clarification) | COMPANIONING -> CLARIFYING | CLARIFYING -> COMPANIONING | Does NOT count against CONC-08 |
| **Orchestrator fallback** (ambiguity) | COMPANIONING -> CLARIFYING | CLARIFYING -> COMPANIONING | Does NOT count against CONC-08 |

### 7. Crash Recovery Guarantee

- LOCAL COLD checkpoint at every turn_end() (atomic SQLite write)
- Maximum data loss = 1 turn (the crashed turn only)
- Edge-First design: system operates WITHOUT K0 (LOCAL COLD is always available)
- Recovery time: P95 < 50ms from LOCAL COLD, ~500ms if K0 rebuild needed

### 8. Proactive Agent Design Boundaries

- Only fires during COMPANIONING in HIGH tier after 5s wait
- Does NOT change FSM state (stays in COMPANIONING)
- User responses go to DeltaAggregator/IMemoryPort, not new turns
- Max 1 proactive question per turn
- K0 detects gaps, K1 phrases questions -- strict separation
- If no K0 gaps available, emit warmth messages instead

### 9. Circuit Breaker Coverage

Every external dependency has a CB with defined fallback:

| Dependency | CB | Fallback |
|-----------|-----|----------|
| UltraBERT | CB_CLASSIFICATION | 5-rule heuristic (<1ms) |
| LLM | CB_MODEL | 3-tier cascade, then templates |
| SessionState | CB_SESSIONSTATE | Stale read, skip write |
| Orchestrator | CB_ORCHESTRATOR | Tier degradation to LOW |
| Planner | CB_PLANNER | Skip planning, direct execution |
| Fabric | CB_FABRIC | Capability unavailable |
| SSE | CB_SSE | Buffer 5 messages, flush on reconnect |

### 10. Turn Never Hangs

Every path through the FSM is guaranteed to complete:

- Watchdog timer (120s) catches runaway turns
- Circuit breakers prevent indefinite waits on external dependencies
- Clarification timeout (5 minutes) prevents stuck CLARIFYING states
- Degradation cascade always reaches CANNED as final fallback
- Even total system failure results in a meaningful error message to the user
