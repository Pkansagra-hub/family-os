# Concierge FSM PoC -- Implementation Plan

**Document Type**: PoC Implementation Plan (Milestone / Epic / Issues)
**Version**: 2.0 -- Flow Coverage Edition
**Created**: 2026-02-17
**Updated**: 2026-02-18
**Status**: PLANNING
**Priority**: HIGH
**Target**: `poc/concierge_fsm_poc/` -- Standalone interactive demo
**Scenario**: Weekend Family Trip (Lake Tahoe) -- 20-turn flow coverage
**Branch**: `k1-kernel`
**Authoritative Flows**: `k1/concierge/concierge_fsm_flows.md` (32 flows)

---

## Executive Summary

Prove the Concierge FSM + ReAct + Real SessionState triangle works end-to-end
by exercising **every reachable FSM flow** in an interactive demo. This PoC is a
**flow-coverage test harness**: 20 out of 32 documented flows from
`concierge_fsm_flows.md` are tested in a scripted 20-turn Lake Tahoe story.
A user types messages into a Rich TUI, the FSM drives state transitions, the
LLM (Gemini 2.5 Flash) reasons via a ReAct loop with 13+1 tools, and cognitive
writes land in a REAL `SessionStateManager` (SQLite-backed via `create_standalone()`).

**What is REAL**:

| Layer | Implementation |
| ----- | -------------- |
| SessionState | `k1.sessionstate.create_standalone()`, MutationGuard, 12 sections, SQLite LOCAL COLD, eviction |
| FSM | 8 states, 14 transitions, deterministic table lookup (aligned to `concierge_fsm_flows.md` Part 3) |
| ReAct Loop | Gemini 2.5 Flash, Scratchpad, COGNITIVE_TOOLS filter, batch extraction |
| LLM Tool Calling | Real function-calling with structured JSON |

**What is MOCKED**:

| Layer | Mock Strategy |
| ----- | ------------- |
| Phase 1 (ACKING) | Keyword classifier (no UltraBERT). Simulates failure for F26 heuristic fallback. |
| Planner / Orchestrator | `execute_workflow` returns canned results |
| Fabric execution | `invoke_capability` returns canned results per capability name |
| K0 Bridge | `recall_memory` returns canned family memory items |
| Discovery | `discover_capabilities` returns hardcoded capability list |
| Schema | `get_capability_schema` returns hardcoded schemas for demo capabilities |
| Circuit Breaker | Simulated CB-open state for F24 full-fallback test |
| Watchdog Timer | Configurable timeout trigger for F15 watchdog test |

**Success Criteria**:

- [ ] 20 of 32 documented flows exercised in a 20-turn demo (see Flow Coverage Matrix)
- [ ] All 8 FSM states visited; all 14 transitions fired at least once
- [ ] Cognitive tools write to real SessionState; snapshot reflects changes
- [ ] Clarification loop: single-round (F4) and max-rounds force-proceed (F5)
- [ ] Interrupt handling from 4 interruptible states: DISPATCHING (F6), COMPANIONING (F7), PROGRESSING (F8), CLARIFYING (F10)
- [ ] Non-interruptible state rejection: DELIVERING queues message for next turn (F11)
- [ ] Crisis bypass: ACKING -> DELIVERING with static response, no LLM (F12)
- [ ] Safety bands: RED blocks action tools (F13), AMBER enables enhanced logging (F14)
- [ ] Degradation paths: watchdog timeout (F15), full fallback (F24), classifier failure (F26), SessionState write failure (F27)
- [ ] User-initiated cancel (F31), clarification timeout (F32)
- [ ] Multi-message batch: second message merged as supplement, not interrupt (F17)
- [ ] Clarification-then-interrupt: resolve round 1, interrupt round 2 (F18)
- [ ] SessionState persists across turns (SQLite); beliefs/scoreboard accumulate
- [ ] Rich TUI shows FSM state, turn history, SessionState snapshot between turns
- [ ] All tests pass

**Relation to Production Plan**:
This PoC validates assumptions in `CONCIERGE_PRODUCTION_IMPLEMENTATION_PLAN_V2.md`.
Specifically: FSMController transitions, ToolDispatcher ReAct loop structure,
ReactLoopScratchpad lifecycle, and cognitive-tool-to-SessionState write path.
All code lives in `poc/` -- NOT in `k1/concierge/`.

**Authoritative Flow Reference**: `k1/concierge/concierge_fsm_flows.md` (32 flows, 14 events, 14 transitions).
All FSM events, transitions, and flow paths in this plan are aligned to that file.

---

## SessionState as Structured Memory (Replacing Chat History)

**Core Insight**: SessionState is not telemetry -- it IS the LLM's memory.
Instead of passing growing chat history into every prompt (unbounded tokens,
no structure, hallucination over noise), the system and LLM **write structured
facts into SessionState sections**, and the LLM **reads them on demand**.

This gives us:

- **Bounded tokens**: HOT tier is 48KB max, never grows unbounded
- **Structured facts**: triples, referents, threads -- not raw text
- **On-demand loading**: LLM pulls only the sections it needs
- **No hallucination over noise**: facts are verified writes, not inferred from chat
- **Persistence across sessions**: SQLite COLD tier survives restarts

### Per-Turn Write Lifecycle (3 Phases)

Every turn follows this write sequence. Implementation code MUST follow this
exact order or SessionState will be stale during Phase 2 LLM reasoning.

```
Phase 1 -- SYSTEM WRITES (before LLM sees anything)
  control        <- system sets turn_number, active_agent, tier, safety_band
  affective_now  <- system writes Phase1Result.emotion into affective_now.update()
  scoreboard     <- system writes Phase1Result.entities as referents via add_referent()
  meta           <- system stamps turn_start_ts, session_id

Phase 2 -- LLM WRITES (via cognitive tools during ReAct loop)
  beliefs_active <- LLM calls update_beliefs(add_fact, ...) for discovered facts
  scoreboard     <- LLM calls update_scoreboard() to refine tasks, topics, QUDs
  clarifications <- LLM calls update_clarifications() to record/resolve gaps
  narrative_active <- LLM calls update_narrative() to create/switch threads
  affective_now  <- LLM calls refine_affect() to override Phase 1 emotion (rare)

Phase 3 -- SYSTEM WRITES (after LLM response generated)
  history_active <- system appends {role, content, tool_calls, turn_number}
  meta           <- system stamps turn_end_ts, tokens_used
  telemetry      <- system writes latency, tool_call_count, iteration_count
  [checkpoint]   <- system triggers COLD flush if history_active > eviction threshold
```

### Per-Section Population Table

Every section has an explicit writer, write mechanism, and read consumer.
**No section is written "somehow" -- each has a concrete code path.**

| # | Section | Tier | Writer | Write Mechanism | When Written | LLM Reads It For |
|---|---------|------|--------|-----------------|--------------|-------------------|
| 1 | `control` | HOT | System | `mutate("control", "update", {turn_number, active_agent, tier, safety_band})` | Phase 1 (every turn) | Knows current turn context, tier constraints |
| 2 | `beliefs_active` | HOT | LLM | `update_beliefs(add_fact, subject, predicate, obj, confidence)` | Phase 2 (when LLM discovers facts) | Recall established facts without re-asking user |
| 3 | `scoreboard` | HOT | System + LLM | System: `add_referent` from Phase1Result entities. LLM: `update_scoreboard` for tasks/topics/QUDs | Phase 1 (entities) + Phase 2 (tasks) | Track active tasks, mentioned entities, open questions |
| 4 | `history_active` | HOT | System | Append `{role, content, tool_calls, turn_number}` after response | Phase 3 (every turn) | Recent conversation context (last N turns) |
| 5 | `clarifications` | HOT | LLM | `update_clarifications(record_gap, ...)` / `resolve_gap` / `expire_gap` | Phase 2 (when info missing) | Know what's been asked, avoid re-asking same question |
| 6 | `affective_now` | HOT | System + LLM | System: `update(emotion, intensity, ...)` from Phase1Result. LLM: `refine_affect` override | Phase 1 (emotion) + Phase 2 (rare override) | Tone adjustment, empathy calibration |
| 7 | `narrative_active` | HOT | LLM | `update_narrative(new_thread, switch_thread, ...)` | Phase 2 (when conversation threads change) | Track conversation arc, know which thread is active |
| 8 | `meta` | HOT | System | Stamp `turn_start_ts`, `turn_end_ts`, `session_id`, `tokens_used` | Phase 1 + Phase 3 | Session metadata, token budget awareness |
| 9 | `beliefs_history` | WARM | System | Evicted from `beliefs_active` when full | On eviction | `promote_belief(warm_to_hot)` to resurface old facts |
| 10 | `history_recent` | WARM | System | Evicted from `history_active` when full | On eviction | Broader conversation context if needed |
| 11 | `persona` | WARM | System | Pre-loaded at session start (family profile, preferences) | Session init | Family member names, ages, preferences, constraints |
| 12 | `telemetry` | WARM | System | Write latency, tool_call_count, error_count per turn | Phase 3 | Not read by LLM -- observability only |

### Read Path Architecture

The LLM accesses SessionState through two mechanisms:

**1. System Prompt Injection (every turn, automatic)**

- Before each LLM call, the system prompt builder calls `read_session_state(section=None)`
- This returns a **headline overview** of all 5 readable HOT sections:
  - beliefs_active: fact_count, entity_count, pinned_count
  - scoreboard: referent_count, topic_count, open_question_count, user_intent
  - clarifications: pending_count, is_blocked
  - affective_now: emotion, intensity, valence, empathy_needed
  - narrative_active: thread_count, active_thread_id, arc_position
- This costs ~200 tokens -- always affordable, gives LLM situational awareness
- Injected into system prompt as structured JSON under `## Current SessionState`

**2. On-Demand Detail (LLM actively calls read_session_state)**

- LLM calls `read_session_state(section="beliefs_active")` to get full fact list
- LLM calls `read_session_state(section="scoreboard")` to see all referents/topics
- Only pulled when LLM decides it needs the detail (e.g., before answering a belief-dependent question)
- This is a regular tool call in the ReAct loop, costs 1 iteration

**3. External Memory (LLM calls recall_memory)**

- For facts NOT in SessionState (long-term family knowledge from K0)
- Returns canned memory items in PoC; real implementation queries K0 bridge

### What This Replaces

| Old Approach (Chat History) | New Approach (SessionState) |
|---|---|
| Pass last N messages as prompt context | System writes structured facts, LLM reads on demand |
| Tokens grow linearly with conversation | HOT tier capped at 48KB, evicts to WARM |
| LLM must re-infer facts from raw text | Facts are explicit triples with confidence |
| No cross-session persistence | SQLite COLD tier persists across sessions |
| All context loaded every call | Overview in system prompt, detail on demand |
| Model hallucinated over noisy input | Writes are MutationGuard-validated, structured |

### Implementation Checklist (DO NOT SKIP)

These are the concrete code artifacts that make this architecture work.
Each must exist and be wired correctly for the PoC to function.

- [ ] **Phase 1 System Writer** (`demo.py` or `react/loop.py`): After Phase1Result, write `control`, `affective_now`, `scoreboard`, `meta` sections
- [ ] **Phase 3 Turn Logger** (`demo.py`): After LLM response, append to `history_active`, stamp `meta`, write `telemetry`
- [ ] **System Prompt Builder** (`llm/client.py` LLM-001): Inject `read_session_state(section=None)` overview + current FSM state + tier-filtered tool list
- [ ] **read_session_state tool** (`tools/read_mock.py` READ-004): Already implemented -- overview mode + detail mode with per-section extractors
- [ ] **Cognitive tools** (`tools/cognitive.py` COG-001-007): Already implemented -- LLM writes to beliefs, scoreboard, clarifications, narrative, affect
- [ ] **Persona pre-load** (`demo.py` DEMO-002): At session init, write family profile to `persona` section

---

## Reuse from Existing PoC (`poc/react_scratchpad_poc/`)

| Component | Source File | Adaptation |
|-----------|------------|------------|
| Gemini client | `llm/gemini_client.py` | Strip benchmark code, keep `generate()`, `extract_findings_batch()` |
| Scratchpad model | `core/models.py` | Keep `Scratchpad`, `Finding`, `LoopBudget`, token compaction logic |
| COGNITIVE_TOOLS filter | `runners/smart_react.py` | Direct reuse of frozenset + extraction filter |
| Tool parameter format | `tools/concierge_tools.py` | Schema structure reused, implementations replaced |

---

## Milestone Overview

```text
MILESTONE 1: FSM Core + Foundation
  Epic 1.1: FSM Controller (8 states, 14 transitions, aligned to flows file)
  Epic 1.2: Mock Phase 1 Classifier (20-turn keyword rules)

MILESTONE 2: Tool System (13+1 tools)
  Epic 2.1: Signal Tool (acknowledge)
  Epic 2.2: Cognitive Tools (6) -- real SessionState writes
  Epic 2.3: Read Tool Mocks (3+1: recall_memory, discover_capabilities, summarize_context, read_session_state)
  Epic 2.4: Action Tool Mocks (3)
  Epic 2.5: Schema Tool (get_capability_schema)
  Epic 2.6: Tool Registry + Tier Allowlist

MILESTONE 3: ReAct Loop (FSM-aware)
  Epic 3.1: Scratchpad + Models
  Epic 3.2: LLM Client (Gemini)
  Epic 3.3: FSM-Aware ReAct Loop (clarification gate + interrupt handler)

MILESTONE 4: Demo Runner (Rich TUI)
  Epic 4.1: Interactive CLI Entry Point
  Epic 4.2: Story Timeline + Mock Data (20 turns, flow-mapped)

MILESTONE 5: Tests (Flow Coverage)
  Epic 5.1: FSM Unit Tests (14 transition types, 22 tests)
  Epic 5.2: Cognitive Tool Integration Tests (8 tests)
  Epic 5.3: Flow Coverage Tests (20 flows, 20 tests)
  Epic 5.4: End-to-End Integration Test (20-turn story)
```

---

## Directory Structure

```
poc/concierge_fsm_poc/
  __init__.py
  demo.py                       # [M4] Rich TUI interactive entry point
  fsm/
    __init__.py
    controller.py                # [M1] State, Event, Action enums + FSMController
    phase1_mock.py               # [M1] Keyword classifier -> Phase1Result
  react/
    __init__.py
    loop.py                      # [M3] FSM-aware ReAct loop
    scratchpad.py                # [M3] Scratchpad + Finding models
  tools/
    __init__.py
    registry.py                  # [M2] 13+1 tool registry with category + tier
    cognitive.py                 # [M2] 6 tools -> real SessionState.mutate()
    signal.py                    # [M2] acknowledge() -> Rich panel
    read_mock.py                 # [M2] recall_memory, discover_capabilities, summarize_context
    action_mock.py               # [M2] invoke_capability, spawn_via_fabric, execute_workflow
    schema.py                    # [M2] get_capability_schema with demo capability schemas
  llm/
    __init__.py
    client.py                    # [M3] Gemini 2.5 Flash client (adapted)
  scenarios/
    __init__.py
    trip_timeline.py             # [M4] Story timeline data + mock responses
  tests/
    __init__.py
    test_fsm.py                  # [M5] All 14 transitions + invalid rejection
    test_cognitive_tools.py      # [M5] Real SessionState writes via each tool
    test_flows.py                # [M5] All 20 testable flows (F1-F32 subset)
    test_integration.py          # [M5] Full 20-turn story end-to-end
```

---

## Flow Coverage Matrix (from `concierge_fsm_flows.md`)

All 32 documented flows classified by PoC testability. "Testable" means the flow
can be exercised with LOW/MEDIUM tiers, mocked Phase 1, mocked Planner/Orchestrator,
and no K0 bridge.

### Testable Flows (20 of 32) -- Covered by 20-Turn Story

| Flow | Name | Turn | State Path | What It Tests |
| ---- | ---- | ---- | ---------- | ------------- |
| F1 | Normal LOW | T1 | L-A-D-De-L | LOW direct dispatch, no companion phase |
| F2 | Normal MEDIUM | T2 | L-A-D-Co-P-De-L | MEDIUM companion + progress phase |
| F4 | Clarification (1 round) | T4 | L-A-Cl-A-D-Co-P-De-L | GAPS_DETECTED, single-round clarification |
| F5 | Max clarification (3 rounds) | T5 | L-A-Cl-A-Cl-A-Cl(MAX)-D-De-L | MAX_ROUNDS_REACHED force-proceed |
| F6 | Interrupt at DISPATCHING | T6 | L-A-D(INT)-IH-A-D-Co-P-De-L | Interrupt before work starts |
| F7 | Interrupt at COMPANIONING | T7 | L-A-D-Co(INT)-IH-A-D-Co-P-De-L | Interrupt during companion wait |
| F8 | Interrupt at PROGRESSING | T8 | L-A-D-Co-P(INT)-IH-A-D-Co-P-De-L | Interrupt with partial results preserved |
| F10 | Clarification interrupt | T9 | L-A-Cl(INT)-IH-A-D-De-L | Topic change during clarification |
| F11 | Non-interruptible rejection | T14 | De(MSG QUEUED)-L-A-D-De-L | DELIVERING rejects interrupt, queues message |
| F12 | CRISIS bypass | T10 | L-A(CRISIS)-De-L | Static response, no LLM, no tools |
| F13 | RED safety band | T11 | L-A-D-Co-P-De-L | Action tools BLOCKED, tier override to MEDIUM |
| F14 | AMBER safety band | T3 | L-A-D-De-L | Enhanced logging, normal routing |
| F15 | Watchdog timeout | T15 | L-A-D-Co-P(TIMEOUT)-IH-A-... | 120s forced interrupt from timer |
| F17 | Multi-message batch | T12 | L-A(+MSG)-D-De-L | Second message merged as supplement |
| F18 | Clarification then interrupt | T13 | L-A-Cl-A-Cl(INT)-IH-A-D-De-L | Resolve round 1, interrupt round 2 |
| F24 | Full fallback (canned) | T16 | L-A-D(CB OPEN)-De-L | All capabilities fail, canned response |
| F26 | Classifier failure | T17 | L-A(HEURISTIC)-D-De-L | Phase 1 throws, keyword heuristic fallback |
| F27 | SessionState write failure | T18 | L-A-D-De-L | MutationGuard rejects, LLM adapts |
| F31 | User cancel | T19 | L-A-D-Co-P(CANCEL)-IH-A-... | Explicit "cancel" command, no new topic |
| F32 | Clarification timeout | T20 | L-A-Cl(TIMEOUT)-L | User walks away, turn abandoned |

### Non-Testable Flows (12 of 32) -- Require Real HIGH/Planner/K0

| Flow | Name | Why Not Testable |
| ---- | ---- | ---------------- |
| F3 | Normal HIGH | Requires real Planner envelope, K0 agent spawn |
| F9 | Interrupt HIGH PROGRESSING | Requires real Planner with partial envelope |
| F16 | Circuit Breaker cascade | Requires real CB with 3 degradation levels + Planner fallback |
| F19 | HIL from Planner (accept) | Requires real Planner generating HIL request |
| F20 | HIL from Planner (reject) | Requires real Planner generating HIL request |
| F21 | Proactive agent checkin | Requires K0 agent runtime + proactive event |
| F22 | Proactive streamer dismiss | Requires K0 agent runtime + streaming infrastructure |
| F23 | Crash recovery | Requires process crash + StateJournal replay |
| F25 | LLM timeout cascade | Requires real multi-model cascade (Flash->Pro->Haiku) |
| F28 | Interrupt during HIL | Requires real Planner HIL flow |
| F29 | Experience triggers | Requires K0 experience layer + trigger evaluation |
| F30 | Orchestrator HIL | Requires real Orchestrator generating HIL |

### Transition Coverage

All 14 transitions from `concierge_fsm_flows.md` Part 3 are covered:

| # | From | Event | To | Covered By |
| - | ---- | ----- | -- | ---------- |
| T1 | LISTENING | MESSAGE_RECEIVED | ACKING | All turns |
| T2 | ACKING | CRISIS_DETECTED | DELIVERING | F12 (Turn 10) |
| T3 | ACKING | PHASE1_COMPLETE | DISPATCHING | F1, F2, F6-F8, F13-F15, F17, F24, F26-F27 |
| T4 | ACKING | GAPS_DETECTED | CLARIFYING | F4, F5, F10, F18, F32 |
| T5 | CLARIFYING | CLARIFICATION_RECEIVED | ACKING | F4, F5, F18 |
| T6 | CLARIFYING | MAX_ROUNDS_REACHED | DISPATCHING | F5 (Turn 5) |
| T7 | DISPATCHING | PRELIMINARY_ACK_SENT | COMPANIONING | F2, F7, F8, F13, F15, F31 |
| T8 | DISPATCHING | DISPATCH_COMPLETE | DELIVERING | F1, F14, F17, F24, F26, F27 (LOW direct) |
| T9 | COMPANIONING | PROGRESS_RECEIVED | PROGRESSING | F2, F8, F15, F31 |
| T10 | COMPANIONING | DISPATCH_COMPLETE | DELIVERING | F7 (fast complete during companion) |
| T11 | PROGRESSING | DISPATCH_COMPLETE | DELIVERING | F2, F8 (after progress) |
| T12 | DELIVERING | RESPONSE_DELIVERED | LISTENING | All turns that reach DELIVERING |
| T13 | *(interruptible) | INTERRUPT_DETECTED | INTERRUPT_HANDLING | F6, F7, F8, F10, F15, F18, F31 |
| T14 | INTERRUPT_HANDLING | INTERRUPT_HANDLED | ACKING | F6, F7, F8, F10, F15, F18, F31 |

---

## Story Timeline (20 Turns -- Weekend Family Trip, Flow Coverage)

Each turn maps to one or more documented flows. The story follows a family
planning and executing a weekend trip to Lake Tahoe.

### Part A: Getting Started (Turns 1-3, Happy Paths)

| Turn | User Message | Tier | Flow | FSM Path | Key Tools | What It Proves |
| ---- | ------------ | ---- | ---- | -------- | --------- | -------------- |
| T1 | "What's the weather like in Lake Tahoe this weekend?" | LOW | F1 | L->A(P1C)->D(DC)->De(RD)->L | `acknowledge`, `invoke_capability(weather_lookup)`, `update_beliefs`, `update_scoreboard` | Normal LOW: direct DISPATCH_COMPLETE->DELIVERING, no companion phase |
| T2 | "Check for kid-friendly activities near Lake Tahoe" | MEDIUM | F2 | L->A(P1C)->D(PAS)->Co(PR)->P(DC)->De(RD)->L | `acknowledge`, `discover_capabilities`, `invoke_capability(activity_search)`, `update_scoreboard`, `update_narrative` | Normal MEDIUM: PRELIMINARY_ACK_SENT->COMPANIONING->PROGRESSING full path |
| T3 | "Does anyone have food allergies I should know about?" | LOW | F14 | L->A(P1C)->D(DC)->De(RD)->L | `acknowledge`, `recall_memory`, `update_beliefs(add_fact)` | AMBER safety band: medical query, enhanced logging, normal routing |

### Part B: Clarification Loops (Turns 4-5)

| Turn | User Message | Tier | Flow | FSM Path | Key Tools | What It Proves |
| ---- | ------------ | ---- | ---- | -------- | --------- | -------------- |
| T4 | "Plan our hotel stay at Lake Tahoe" | MEDIUM | F4 | L->A(GD)->Cl // user: "Sat-Sun, 4 people" // Cl(CR)->A(P1C)->D(PAS)->Co(PR)->P(DC)->De(RD)->L | `get_capability_schema(hotel_booking)`, `update_clarifications(record_gap)`, ask user, `update_clarifications(resolve_gap)`, `execute_workflow`, `update_scoreboard` | Single-round clarification: GAPS_DETECTED->CLARIFYING->CLARIFICATION_RECEIVED->ACKING->proceed |
| T5 | "Book something special for Mom's anniversary dinner" | MEDIUM | F5 | L->A(GD)->Cl(CR)->A(GD)->Cl(CR)->A(GD)->Cl(MRR)->D(DC)->De(RD)->L | `get_capability_schema(restaurant_search)`, `update_clarifications(record_gap)` x3, `update_clarifications(resolve_gap)` x2 | Max-rounds clarification: 3 rounds, MAX_ROUNDS_REACHED force-proceed with defaults |

### Part C: Interrupt Handling (Turns 6-9)

| Turn | User Message | Tier | Flow | FSM Path | Key Tools | What It Proves |
| ---- | ------------ | ---- | ---- | -------- | --------- | -------------- |
| T6 | "Find snowshoe rental places" // interrupt @ DISPATCHING: "Wait, ski lessons instead" | LOW | F6 | L->A->D(ID)->IH(IHd)->A(P1C)->D(DC)->De(RD)->L | `cancel_inflight`, `partial_flush`, re-entry | Interrupt at DISPATCHING: before work starts, clean cancel |
| T7 | "Best family restaurants in Tahoe" // interrupt @ COMPANIONING: "Vegetarian only" | MEDIUM | F7 | L->A->D(PAS)->Co(ID)->IH(IHd)->A->D(PAS)->Co(PR)->P(DC)->De(RD)->L | `cancel_inflight`, `partial_flush`, re-entry with refined query | Interrupt at COMPANIONING: work started but no results yet |
| T8 | "Compare hotel prices" // interrupt @ PROGRESSING: "Check Airbnb too" | MEDIUM | F8 | L->A->D(PAS)->Co(PR)->P(ID)->IH(IHd)->A->D(PAS)->Co(PR)->P(DC)->De(RD)->L | `partial_flush` (preserves partial hotel data), re-entry | Interrupt at PROGRESSING: partial results preserved in SessionState |
| T9 | "Plan the drive to Tahoe" // clarification: "How many cars?" // interrupt: "Fly instead" | MEDIUM | F10 | L->A(GD)->Cl(ID)->IH(IHd)->A(P1C)->D(DC)->De(RD)->L | `update_clarifications(record_gap)`, `cancel_inflight` | Interrupt at CLARIFYING: topic change overrides clarification |

### Part D: Safety and Crisis (Turns 10-11)

| Turn | User Message | Tier | Flow | FSM Path | Key Tools | What It Proves |
| ---- | ------------ | ---- | ---- | -------- | --------- | -------------- |
| T10 | "My kid just fell and is bleeding at the ski slope" | CRISIS | F12 | L->A(CD)->De(RD)->L | Static crisis response (hardcoded), NO LLM call | CRISIS bypass: ACKING->DELIVERING direct, no dispatch, no tools, static response |
| T11 | "Look up the ER number and directions to Barton Memorial Hospital" | RED->MED | F13 | L->A(P1C)->D(PAS)->Co(PR)->P(DC)->De(RD)->L | `recall_memory`, `discover_capabilities` (action tools BLOCKED) | RED safety band: tier overridden to MEDIUM, action tools filtered out, read/cognitive only |

### Part E: Edge Cases (Turns 12-14)

| Turn | User Message | Tier | Flow | FSM Path | Key Tools | What It Proves |
| ---- | ------------ | ---- | ---- | -------- | --------- | -------------- |
| T12 | "What's checkout time at Hyatt?" + rapid "Also, is the pool heated?" | LOW | F17 | L->A(+MSG merged)->D(DC)->De(RD)->L | Both queries merged, single dispatch | Multi-message batch: second message is supplement, not interrupt |
| T13 | "Reserve a dinner spot tonight" // clarify "How many?" -> "4" // clarify "Cuisine?" // interrupt: "Pizza delivery instead" | MEDIUM | F18 | L->A(GD)->Cl(CR)->A(GD)->Cl(ID)->IH(IHd)->A(P1C)->D(DC)->De(RD)->L | `update_clarifications(record_gap)`, resolve round 1, interrupt round 2 | Clarification-then-interrupt: answer round 1, interrupt round 2 |
| T14 | [User types during DELIVERING]: "Actually make it 5 people" | -- | F11 | De(MSG QUEUED)->L(new turn)->A->D->De->L | Message queued, processed next turn | Non-interruptible DELIVERING: message not lost, handled as new turn |

### Part F: Degradation and Failure (Turns 15-18)

| Turn | User Message | Tier | Flow | FSM Path | Key Tools | What It Proves |
| ---- | ------------ | ---- | ---- | -------- | --------- | -------------- |
| T15 | "Calculate optimal route with all stops, traffic, weather, road conditions" | MEDIUM | F15 | L->A->D(PAS)->Co(PR)->P...(TIMEOUT)->IH(IHd)->A->fallback | Watchdog fires forced INTERRUPT_DETECTED after 120s (mocked) | Watchdog timeout: system-initiated interrupt, not user |
| T16 | "Book a private boat tour on the lake" | LOW | F24 | L->A(P1C)->D(CB OPEN)->De(RD)->L | All `invoke_capability` calls return CB-open error, canned fallback | Full fallback: all circuit breakers open, canned apology response |
| T17 | "What time does the gondola start tomorrow?" | LOW | F26 | L->A(CLASSIFIER FAIL)->D(DC)->De(RD)->L | Phase 1 mock throws, keyword heuristic fallback used | Classifier failure: UltraBERT (mock) fails, heuristic gives degraded-but-usable result |
| T18 | "Remember that Jake loves the snow activities more than anything" | LOW | F27 | L->A->D(DC)->De(RD)->L | `update_beliefs` -> MutationGuard rejects (capacity), LLM adapts | SessionState write failure: oversized data rejected, LLM proceeds without persistence |

### Part G: User Control and Timeout (Turns 19-20)

| Turn | User Message | Tier | Flow | FSM Path | Key Tools | What It Proves |
| ---- | ------------ | ---- | ---- | -------- | --------- | -------------- |
| T19 | "Start planning tomorrow's full itinerary" // user types "cancel" | MEDIUM | F31 | L->A->D(PAS)->Co(PR)->P(CANCEL)->IH(IHd)->A->... | Explicit cancel command, different from interrupt (no new topic) | User-initiated cancel: explicit stop, no replacement message |
| T20 | "Plan something fun for the evening" // [user walks away, no response to clarification] | MEDIUM | F32 | L->A(GD)->Cl...(TIMEOUT)->L | Clarification timeout after 60s (mocked), turn abandoned | Clarification timeout: session returns to LISTENING, partial state cleaned up |

### FSM Event Legend

| Abbrev | Event | Description |
| ------ | ----- | ----------- |
| P1C | PHASE1_COMPLETE | Phase 1 classification done, no gaps |
| GD | GAPS_DETECTED | Phase 1 found missing required info |
| CR | CLARIFICATION_RECEIVED | User answered clarification question |
| MRR | MAX_ROUNDS_REACHED | 3 clarification rounds exhausted |
| PAS | PRELIMINARY_ACK_SENT | Ack displayed, enter companion phase |
| PR | PROGRESS_RECEIVED | Progress update from execution |
| DC | DISPATCH_COMPLETE | All execution done |
| RD | RESPONSE_DELIVERED | Final response shown to user |
| CD | CRISIS_DETECTED | Safety band == CRISIS |
| ID | INTERRUPT_DETECTED | User interrupt or watchdog timeout |
| IHd | INTERRUPT_HANDLED | Interrupt processed, ready for re-entry |

---

## Mock Capability Schemas (for `get_capability_schema`)

| Capability Name | Required Inputs | Optional Inputs |
| --------------- | --------------- | --------------- |
| `tool.execute.weather_lookup` | `location`, `date_range` | `units` |
| `tool.execute.hotel_booking` | `location`, `check_in`, `check_out`, `guests` | `budget_max`, `star_rating`, `amenities` |
| `tool.execute.activity_search` | `location`, `domain` | `age_group`, `max_results` |
| `tool.execute.restaurant_search` | `location`, `cuisine_type`, `party_size`, `time` | `kid_friendly`, `budget`, `dietary_restrictions` |
| `workflow.trip_planning` | `destination`, `dates`, `family_size` | `budget`, `preferences` |
| `tool.execute.rental_lookup` | `location`, `item_type` | `duration`, `quantity` |
| `tool.execute.flight_search` | `origin`, `destination`, `date`, `passengers` | `class`, `budget` |
| `tool.execute.route_planner` | `origin`, `destination`, `stops` | `avoid_highways`, `traffic_model` |
| `tool.execute.boat_tour` | `location`, `date`, `group_size` | `tour_type`, `budget` |

---

# MILESTONE 1: FSM Core + Foundation

**Goal**: Deterministic FSM with all 8 states and 14 transitions. Mock Phase 1.
**Depends On**: Nothing
**Estimated Lines**: ~320
**Files**: `fsm/controller.py`, `fsm/phase1_mock.py`, `fsm/__init__.py`

---

## Epic 1.1: FSM Controller

**Goal**: Pure-logic FSM with zero I/O. Deterministic table lookup.
**File**: `poc/concierge_fsm_poc/fsm/controller.py`
**Est**: ~180 lines

### Issue FSM-001: State, Event, Action Enums

| Field | Value |
|-------|-------|
| **Title** | Define State, Event, Action enums for 8-state FSM |
| **Priority** | P0 |
| **Estimate** | 30 min |
| **Status** | NOT STARTED |

**Description**:

Create three enums aligned to `concierge_fsm_flows.md` Part 2 (14 events):

```python
class State(str, Enum):
    LISTENING = "LISTENING"
    ACKING = "ACKING"
    CLARIFYING = "CLARIFYING"
    DISPATCHING = "DISPATCHING"
    COMPANIONING = "COMPANIONING"
    PROGRESSING = "PROGRESSING"
    DELIVERING = "DELIVERING"
    INTERRUPT_HANDLING = "INTERRUPT_HANDLING"

class Event(str, Enum):
    # Phase 1 outcomes
    MESSAGE_RECEIVED = "message_received"        # User sends message
    PHASE1_COMPLETE = "phase1_complete"           # Classification done, no gaps
    GAPS_DETECTED = "gaps_detected"               # Required info missing
    CRISIS_DETECTED = "crisis_detected"           # Safety band == CRISIS

    # Clarification
    CLARIFICATION_RECEIVED = "clarification_received"  # User answered clarification
    MAX_ROUNDS_REACHED = "max_rounds_reached"          # 3 rounds exhausted, force-proceed

    # Dispatch + Execution
    DISPATCH_STARTED = "dispatch_started"         # Phase 2 tool loop begins
    PRELIMINARY_ACK_SENT = "preliminary_ack_sent" # Ack shown, enter companion (MED/HIGH)
    PROGRESS_RECEIVED = "progress_received"       # Execution progress update
    DISPATCH_COMPLETE = "dispatch_complete"        # All execution done

    # Delivery
    RESPONSE_DELIVERED = "response_delivered"      # Final response shown to user
    TURN_COMPLETE = "turn_complete"                # Turn fully done, checkpoint

    # Interrupt
    INTERRUPT_DETECTED = "interrupt_detected"      # User interrupt or watchdog
    INTERRUPT_HANDLED = "interrupt_handled"         # Interrupt processed, re-enter

class Action(str, Enum):
    ACQUIRE_LOCK = "acquire_lock"
    RUN_PHASE1 = "run_phase1"
    ROUTE_BY_TIER = "route_by_tier"
    CRISIS_RESPONSE = "crisis_response"
    SEND_CLARIFICATION = "send_clarification"
    MERGE_CLARIFICATION = "merge_clarification"
    FORCE_PROCEED = "force_proceed"
    START_TOOL_LOOP = "start_tool_loop"
    SEND_ACKNOWLEDGE = "send_acknowledge"
    STREAM_PROGRESS = "stream_progress"
    ASSEMBLE_RESPONSE = "assemble_response"
    FLUSH_AND_CHECKPOINT = "flush_and_checkpoint"
    CANCEL_INFLIGHT = "cancel_inflight"
    PARTIAL_FLUSH = "partial_flush"
    REENTER_ACKING = "reenter_acking"
```

**Acceptance Criteria**:

- [ ] All 8 states from concierge.md Section 5.1
- [ ] All 14 events from `concierge_fsm_flows.md` Part 2
- [ ] All 15 actions from transition table
- [ ] Enums use `str` mixin for JSON serialization

---

### Issue FSM-002: Transition Table + FSMController

| Field | Value |
| ----- | ----- |
| **Title** | Implement FSMController with deterministic TRANSITION_TABLE (14 transitions, aligned to flows file) |
| **Priority** | P0 |
| **Estimate** | 1.5 hr |
| **Status** | NOT STARTED |

**Description**:

Implement the full transition table as a class-level dict. All transitions are
pure lookups -- zero I/O, zero external calls. **Aligned to `concierge_fsm_flows.md`
Part 3 (14 transitions exactly).**

Key differences from earlier plan:

- Clarification triggers from ACKING (GAPS_DETECTED), not from DISPATCHING
- MAX_ROUNDS_REACHED: CLARIFYING -> DISPATCHING (force-proceed after 3 rounds)
- LOW tier: DISPATCHING + DISPATCH_COMPLETE -> DELIVERING (skip companion)
- COMPANIONING + DISPATCH_COMPLETE -> DELIVERING (Orchestrator done early)
- Interrupt from 4 states: DISPATCHING, COMPANIONING, PROGRESSING, CLARIFYING
- No self-loop (PROGRESSING + PROGRESS_RECEIVED stays in production; PoC uses
  single DISPATCH_COMPLETE event for simplicity)

```python
class FSMController:
    # Interruptible states (from flows file Part 3)
    INTERRUPTIBLE: frozenset[State] = frozenset({
        State.DISPATCHING, State.COMPANIONING,
        State.PROGRESSING, State.CLARIFYING,
    })

    TRANSITION_TABLE: Dict[Tuple[State, Event], Tuple[State, List[Action]]] = {
        # T1: New message arrives
        (State.LISTENING, Event.MESSAGE_RECEIVED):
            (State.ACKING, [Action.ACQUIRE_LOCK, Action.RUN_PHASE1]),

        # T2: Crisis detected in Phase 1 (bypass all dispatch)
        (State.ACKING, Event.CRISIS_DETECTED):
            (State.DELIVERING, [Action.CRISIS_RESPONSE]),

        # T3: Phase 1 complete, no gaps -> dispatch
        (State.ACKING, Event.PHASE1_COMPLETE):
            (State.DISPATCHING, [Action.ROUTE_BY_TIER]),

        # T4: Phase 1 found gaps -> clarify (rounds < 3)
        (State.ACKING, Event.GAPS_DETECTED):
            (State.CLARIFYING, [Action.SEND_CLARIFICATION]),

        # T5: User answered clarification -> re-enter ACKING
        (State.CLARIFYING, Event.CLARIFICATION_RECEIVED):
            (State.ACKING, [Action.MERGE_CLARIFICATION]),

        # T6: 3 rounds exhausted -> force-proceed to DISPATCHING
        (State.CLARIFYING, Event.MAX_ROUNDS_REACHED):
            (State.DISPATCHING, [Action.FORCE_PROCEED, Action.ROUTE_BY_TIER]),

        # T7: Ack sent -> enter companion phase (MEDIUM/HIGH tier)
        (State.DISPATCHING, Event.PRELIMINARY_ACK_SENT):
            (State.COMPANIONING, [Action.SEND_ACKNOWLEDGE, Action.START_TOOL_LOOP]),

        # T8: Dispatch done immediately -> deliver (LOW tier, no companion)
        (State.DISPATCHING, Event.DISPATCH_COMPLETE):
            (State.DELIVERING, [Action.ASSEMBLE_RESPONSE]),

        # T9: Progress update during companion phase
        (State.COMPANIONING, Event.PROGRESS_RECEIVED):
            (State.PROGRESSING, [Action.STREAM_PROGRESS]),

        # T10: Orchestrator/tool done while still in companion
        (State.COMPANIONING, Event.DISPATCH_COMPLETE):
            (State.DELIVERING, [Action.ASSEMBLE_RESPONSE]),

        # T11: All work done after progress phase
        (State.PROGRESSING, Event.DISPATCH_COMPLETE):
            (State.DELIVERING, [Action.ASSEMBLE_RESPONSE]),

        # T12: Response shown -> return to LISTENING
        (State.DELIVERING, Event.RESPONSE_DELIVERED):
            (State.LISTENING, [Action.FLUSH_AND_CHECKPOINT]),

        # T13: Interrupt from any interruptible state (dynamically resolved)
        # Implemented via is_interruptible() check in transition() method
        (State.DISPATCHING, Event.INTERRUPT_DETECTED):
            (State.INTERRUPT_HANDLING, [Action.CANCEL_INFLIGHT, Action.PARTIAL_FLUSH]),
        (State.COMPANIONING, Event.INTERRUPT_DETECTED):
            (State.INTERRUPT_HANDLING, [Action.CANCEL_INFLIGHT, Action.PARTIAL_FLUSH]),
        (State.PROGRESSING, Event.INTERRUPT_DETECTED):
            (State.INTERRUPT_HANDLING, [Action.CANCEL_INFLIGHT, Action.PARTIAL_FLUSH]),
        (State.CLARIFYING, Event.INTERRUPT_DETECTED):
            (State.INTERRUPT_HANDLING, [Action.CANCEL_INFLIGHT, Action.PARTIAL_FLUSH]),

        # T14: Interrupt processed -> re-enter ACKING with new message
        (State.INTERRUPT_HANDLING, Event.INTERRUPT_HANDLED):
            (State.ACKING, [Action.REENTER_ACKING]),
    }

    def __init__(self) -> None:
        self._state: State = State.LISTENING
        self._history: list[tuple[State, Event, State]] = []

    @property
    def state(self) -> State:
        return self._state

    @property
    def history(self) -> list[tuple[State, Event, State]]:
        return list(self._history)

    def is_interruptible(self) -> bool:
        return self._state in self.INTERRUPTIBLE

    def transition(self, event: Event) -> tuple[State, list[Action]]:
        key = (self._state, event)
        if key not in self.TRANSITION_TABLE:
            raise InvalidTransitionError(self._state, event)
        new_state, actions = self.TRANSITION_TABLE[key]
        self._history.append((self._state, event, new_state))
        self._state = new_state
        return new_state, actions

    def reset(self) -> None:
        self._state = State.LISTENING
        self._history.clear()
```

**Acceptance Criteria**:

- [ ] Exactly 14 transition types from `concierge_fsm_flows.md` Part 3 (18 table entries due to 4 interruptible states)
- [ ] `transition()` returns `(new_state, actions)`
- [ ] Invalid transitions raise `InvalidTransitionError`
- [ ] `is_interruptible()` returns True for DISPATCHING, COMPANIONING, PROGRESSING, CLARIFYING
- [ ] `history` tracks all past transitions
- [ ] `reset()` returns to LISTENING
- [ ] LOW path: DISPATCHING + DISPATCH_COMPLETE -> DELIVERING (no companion)
- [ ] MEDIUM path: DISPATCHING + PRELIMINARY_ACK_SENT -> COMPANIONING -> PROGRESSING -> DELIVERING

---

### Issue FSM-003: InvalidTransitionError + ErrorSeverity

| Field | Value |
|-------|-------|
| **Title** | Define InvalidTransitionError and ErrorSeverity enum |
| **Priority** | P0 |
| **Estimate** | 15 min |
| **Status** | NOT STARTED |

**Description**:

```python
class InvalidTransitionError(Exception):
    def __init__(self, state: State, event: Event):
        self.state = state
        self.event = event
        super().__init__(f"No transition from {state.value} on {event.value}")

class ErrorSeverity(str, Enum):
    RECOVERABLE = "recoverable"
    DEGRADED = "degraded"
    TERMINAL = "terminal"
```

**Acceptance Criteria**:

- [ ] Error carries `state` and `event` for debugging
- [ ] ErrorSeverity matches Section 5.5

---

## Epic 1.2: Mock Phase 1 Classifier

**Goal**: Keyword-based classifier replacing UltraBERT. Enough to route tiers.
**File**: `poc/concierge_fsm_poc/fsm/phase1_mock.py`
**Est**: ~90 lines

### Issue PH1-001: Phase1Result Dataclass

| Field | Value |
|-------|-------|
| **Title** | Define Phase1Result dataclass for mock classification output |
| **Priority** | P0 |
| **Estimate** | 20 min |
| **Status** | NOT STARTED |

**Description**:

```python
@dataclass
class Phase1Result:
    intent: str                      # e.g. "weather_lookup", "trip_planning"
    tier: Literal["LOW", "MEDIUM"]   # Complexity tier
    safety_band: str                 # "GREEN", "RED", "CRISIS"
    entities: dict[str, str]         # Extracted entities {"location": "Lake Tahoe"}
    emotion: str                     # Primary emotion label
    confidence: float                # Classification confidence 0.0-1.0
    gaps: list[str]                  # Detected information gaps
```

**Acceptance Criteria**:

- [ ] All fields needed by DISPATCHING routing
- [ ] `tier` limited to LOW and MEDIUM (PoC scope)
- [ ] `safety_band` defaults to GREEN

---

### Issue PH1-002: MockPhase1Classifier

| Field | Value |
|-------|-------|
| **Title** | Implement keyword-based Phase 1 classifier |
| **Priority** | P0 |
| **Estimate** | 30 min |
| **Status** | NOT STARTED |

**Description**:

Keyword rules for the 20-turn flow-coverage story:

| Keywords | Intent | Tier | Safety | Notes |
| -------- | ------ | ---- | ------ | ----- |
| weather, forecast, temperature | `weather_lookup` | LOW | GREEN | T1 (F1) |
| activity, activities, kid-friendly, fun | `activity_search` | MEDIUM | GREEN | T2 (F2), T20 (F32) |
| allergy, allergies, food restriction | `recall_family_info` | LOW | AMBER | T3 (F14) -- medical query |
| plan, hotel, stay, book, reserve | `hotel_booking` | MEDIUM | GREEN | T4 (F4), T8 (F8) |
| special, anniversary, dinner | `restaurant_search` | MEDIUM | GREEN | T5 (F5) |
| snowshoe, rental, ski, lesson | `rental_lookup` | LOW | GREEN | T6 (F6) |
| restaurant, food, eat, dining, vegetarian | `restaurant_search` | MEDIUM | GREEN | T7 (F7) |
| drive, route, fly, flight | `route_planner` | MEDIUM | GREEN | T9 (F10) |
| emergency, crisis, bleeding, hurt, danger | `crisis` | -- | CRISIS | T10 (F12) |
| ER, hospital, emergency room, directions | `medical_lookup` | MEDIUM | RED | T11 (F13) |
| checkout, pool, heated | `hotel_info` | LOW | GREEN | T12 (F17) |
| reserve, dinner, tonight, pizza | `restaurant_search` | MEDIUM | GREEN | T13 (F18) |
| boat, tour, lake | `boat_tour` | LOW | GREEN | T16 (F24) |
| gondola, time, start | `activity_search` | LOW | GREEN | T17 (F26) |
| remember, jake, loves, snow | `store_belief` | LOW | GREEN | T18 (F27) |
| itinerary, plan, tomorrow | `trip_planning` | MEDIUM | GREEN | T19 (F31) |
| cancel, stop, never mind | (cancel signal) | -- | -- | T19 user cancel |

Special mock behaviors:

- **F26 (T17)**: `raise_on_next=True` flag causes classifier to throw `ClassifierError`;
  fallback heuristic uses keyword matching with `confidence=0.3`
- **F24 (T16)**: `force_cb_open=True` flag causes all capability invocations to
  return `CircuitBreakerOpenError`
- **F15 (T15)**: `watchdog_timeout_ms=2000` (mocked as 2s for demo, real is 120s)
- **F27 (T18)**: No special Phase 1 behavior; failure happens in SessionState write

Default fallback: `intent="general"`, `tier="LOW"`, `safety_band="GREEN"`.

Also extracts entities via simple regex:

- Location: "Lake Tahoe", "Tahoe" -> `{"location": "Lake Tahoe"}`
- Budget: "$300" -> `{"budget": "300"}`
- Dates: "Saturday", "Sunday" -> `{"dates": "Saturday, Sunday"}`
- People: "4 people", "5 people" -> `{"party_size": "4"}`

**Acceptance Criteria**:

- [ ] Returns `Phase1Result` for any input string
- [ ] Correctly routes all 20 demo turns
- [ ] `safety_band="CRISIS"` for crisis keywords (T10)
- [ ] `safety_band="RED"` for medical emergency keywords (T11)
- [ ] `safety_band="AMBER"` for medical info keywords (T3)
- [ ] `raise_on_next` flag triggers `ClassifierError` for F26 test
- [ ] Gap detection: returns `gaps=["check_in", "check_out", "guests"]` for hotel without dates

---

# MILESTONE 2: Tool System (13+1 Tools)

**Goal**: All 14 tools implemented. Cognitive tools write to real SessionState.
Read/Action tools return canned data. Schema tool returns hardcoded capability schemas.
**Depends On**: Milestone 1 (Phase1Result for tier routing)
**Estimated Lines**: ~680
**Files**: `tools/cognitive.py`, `tools/signal.py`, `tools/read_mock.py`,
`tools/action_mock.py`, `tools/schema.py`, `tools/registry.py`

---

## Epic 2.1: Signal Tool

**File**: `poc/concierge_fsm_poc/tools/signal.py`
**Est**: ~40 lines

### Issue SIG-001: acknowledge() Tool

| Field | Value |
|-------|-------|
| **Title** | Implement acknowledge() signal tool |
| **Priority** | P0 |
| **Estimate** | 20 min |
| **Status** | NOT STARTED |

**Description**:

Immediate user-facing message. In the PoC, prints to Rich console with a styled
panel. No SessionState writes.

```python
def acknowledge(ack_type: str, message: str, next_tool: str) -> dict:
    """
    ack_type: "commit" | "progress" | "closure"
    message: User-facing text (max 150 tokens)
    next_tool: Name of next tool or "none"
    """
    console.print(Panel(message, title=f"[ACK: {ack_type}]", ...))
    return {"displayed": True, "formatted_message": message}
```

**Acceptance Criteria**:

- [ ] Accepts `ack_type`, `message`, `next_tool`
- [ ] Prints to Rich console with styled panel
- [ ] Returns `{"displayed": True, "formatted_message": ...}`
- [ ] Zero SessionState writes

---

## Epic 2.2: Cognitive Tools (6) -- Real SessionState Writes

**File**: `poc/concierge_fsm_poc/tools/cognitive.py`
**Est**: ~220 lines

### Issue COG-001: Cognitive Tool Base + SessionState Wiring

| Field | Value |
|-------|-------|
| **Title** | Create base cognitive write path wired to SessionStateManager.mutate() |
| **Priority** | P0 |
| **Estimate** | 30 min |
| **Status** | NOT STARTED |

**Description**:

All 6 cognitive tools share the same write path:

```python
class CognitiveToolSet:
    def __init__(self, manager: SessionStateManager):
        self._manager = manager

    def _write(self, section: str, operation: str, data: dict) -> dict:
        result = self._manager.mutate(section, operation, data)
        snapshot = self._manager.get_snapshot()
        section_data = snapshot.get(section, {})
        return {
            "success": result.applied,
            "section_bytes": len(str(section_data)),
            "rejection_reason": str(result.reason) if not result.applied else None,
        }
```

The manager is created via `create_standalone(session_id, db_path)` at demo
startup and injected into `CognitiveToolSet`.

**Acceptance Criteria**:

- [ ] Constructor takes `SessionStateManager`
- [ ] `_write()` calls `manager.mutate(section, operation, data)`
- [ ] Returns success/failure with section_bytes
- [ ] MutationGuard validates writes (real rejection on capacity overflow)

---

### Issue COG-002: update_scoreboard()

| Field | Value |
|-------|-------|
| **Title** | Implement update_scoreboard cognitive tool |
| **Priority** | P0 |
| **Estimate** | 20 min |
| **Status** | NOT STARTED |

**Description**:

Operations: `upsert_task`, `resolve_referent`, `push_qud`, `pop_qud`,
`update_salience`, `shift_topic`.

Writes to `scoreboard` section (6KB budget within HOT 48KB).

```python
def update_scoreboard(self, operation: str, **kwargs) -> dict:
    data = {"operation": operation, **kwargs}
    return self._write("scoreboard", operation, data)
```

**Acceptance Criteria**:

- [ ] All 6 operations accepted
- [ ] Writes to `scoreboard` section via `_write()`
- [ ] Returns `success`, `section_bytes`

---

### Issue COG-003: update_beliefs()

| Field | Value |
|-------|-------|
| **Title** | Implement update_beliefs cognitive tool |
| **Priority** | P0 |
| **Estimate** | 20 min |
| **Status** | NOT STARTED |

**Description**:

Operations: `add_fact`, `correct_fact`, `invalidate_fact`, `add_preference`.
Writes to `beliefs_active` section (8KB budget).

**Acceptance Criteria**:

- [ ] All 4 operations accepted
- [ ] Generates `belief_id` (UUID)
- [ ] Writes to `beliefs_active` section
- [ ] Returns `success`, `belief_id`, `section_bytes`

---

### Issue COG-004: update_clarifications()

| Field | Value |
|-------|-------|
| **Title** | Implement update_clarifications cognitive tool |
| **Priority** | P0 |
| **Estimate** | 20 min |
| **Status** | NOT STARTED |

**Description**:

Operations: `record_gap`, `resolve_gap`, `expire_gap`.
Writes to `clarifications` section (4KB budget).

Critical for the clarification loop (Turn 3-4 of the demo).

**Acceptance Criteria**:

- [ ] `record_gap` creates gap entry with `gap_id`
- [ ] `resolve_gap` marks gap as resolved
- [ ] Writes to `clarifications` section
- [ ] Returns `success`, `gap_id`, `open_gaps_count`

---

### Issue COG-005: update_narrative()

| Field | Value |
|-------|-------|
| **Title** | Implement update_narrative cognitive tool |
| **Priority** | P0 |
| **Estimate** | 20 min |
| **Status** | NOT STARTED |

**Description**:

Operations: `new_thread`, `switch_thread`, `resume_thread`,
`continue_thread`, `close_thread`.
Writes to `narrative_active` section (4KB budget).

**Acceptance Criteria**:

- [ ] All 5 operations accepted
- [ ] `new_thread` generates `thread_id`
- [ ] Writes to `narrative_active` section
- [ ] Returns `success`, `thread_id`, `active_threads`

---

### Issue COG-006: refine_affect()

| Field | Value |
|-------|-------|
| **Title** | Implement refine_affect cognitive tool |
| **Priority** | P1 |
| **Estimate** | 15 min |
| **Status** | NOT STARTED |

**Description**:

Override Phase 1 emotion classification in `affective_now` section (4KB budget).
Rare tool -- only called when LLM detects nuance Phase 1 missed.

**Acceptance Criteria**:

- [ ] Accepts `override_emotion`, `override_intensity`, `override_valence`, `reasoning`
- [ ] Writes to `affective_now` section
- [ ] Returns `success`, `override_applied`

---

### Issue COG-007: promote_belief()

| Field | Value |
|-------|-------|
| **Title** | Implement promote_belief cognitive tool |
| **Priority** | P1 |
| **Estimate** | 15 min |
| **Status** | NOT STARTED |

**Description**:

Directions: `warm_to_hot` and `hot_to_k0`.
In the PoC, `hot_to_k0` is mocked (returns success with fake receipt).
`warm_to_hot` reads from `beliefs_history` and writes to `beliefs_active`.

**Acceptance Criteria**:

- [ ] `warm_to_hot`: reads WARM, writes HOT
- [ ] `hot_to_k0`: mocked, returns fake `k0_store_receipt`
- [ ] Returns `success`, `belief_id`, `destination`

---

## Epic 2.3: Read Tool Mocks (3+1)

**File**: `poc/concierge_fsm_poc/tools/read_mock.py`
**Est**: ~200 lines

### Issue READ-001: recall_memory() Mock

| Field | Value |
|-------|-------|
| **Title** | Implement recall_memory read tool with canned family data |
| **Priority** | P0 |
| **Estimate** | 20 min |
| **Status** | NOT STARTED |

**Description**:

Returns canned family memory items for the trip scenario:

| Query Match | Mock Response |
|------------|--------------|
| "allergy" / "food" | `[{subject: "Mom", predicate: "allergic_to", object: "shellfish"}, {subject: "Jake", predicate: "allergic_to", object: "peanuts"}]` |
| "lake tahoe" / "trip" | `[{type: "event", summary: "Family went to Lake Tahoe in 2024, stayed at Hyatt Regency"}]` |
| default | `[{type: "general", summary: "No specific memories found"}]` |

**Acceptance Criteria**:

- [ ] Returns keyword-matched canned results
- [ ] Response structure matches `MemoryRecallResult` schema
- [ ] Includes `query_latency_ms` (mocked)

---

### Issue READ-002: discover_capabilities() Mock

| Field | Value |
|-------|-------|
| **Title** | Implement discover_capabilities read tool with hardcoded capability list |
| **Priority** | P0 |
| **Estimate** | 20 min |
| **Status** | NOT STARTED |

**Description**:

Returns the 5 demo capabilities regardless of query:

```python
DEMO_CAPABILITIES = [
    {"name": "tool.execute.weather_lookup", "domain": ["TRAVEL"], "safety_band": "GREEN"},
    {"name": "tool.execute.hotel_booking", "domain": ["TRAVEL"], "safety_band": "AMBER"},
    {"name": "tool.execute.activity_search", "domain": ["TRAVEL", "FAMILY"], "safety_band": "GREEN"},
    {"name": "tool.execute.restaurant_search", "domain": ["FOOD", "FAMILY"], "safety_band": "GREEN"},
    {"name": "workflow.trip_planning", "domain": ["TRAVEL", "PLANNING"], "safety_band": "AMBER"},
]
```

**Acceptance Criteria**:

- [ ] Returns all 5 demo capabilities
- [ ] Response structure matches `DiscoveryResult` schema
- [ ] Filters by `domain` and `safety_band` if provided

---

### Issue READ-003: summarize_context() Mock

| Field | Value |
|-------|-------|
| **Title** | Implement summarize_context read tool using real SessionState snapshot |
| **Priority** | P1 |
| **Estimate** | 30 min |
| **Status** | NOT STARTED |

**Description**:

Semi-real: reads actual SessionState snapshot via `manager.get_snapshot()`,
then does simple extractive summarization (key-value flattening, no LLM call).

**Acceptance Criteria**:

- [ ] Reads real SessionState snapshot
- [ ] Generates text summary of HOT sections
- [ ] Returns `summary`, `original_tokens`, `summary_tokens`, `compression_ratio`

---

### Issue READ-004: read_session_state() -- Active Section Reader

| Field | Value |
|-------|-------|
| **Title** | Implement read_session_state for structured section reading (overview + detail) |
| **Priority** | P0 |
| **Estimate** | 45 min |
| **Status** | NOT STARTED |

**Description**:

This is the PRIMARY read mechanism for LLM to access SessionState content.
Unlike `get_snapshot()` which returns only diagnostics (size metrics),
`read_session_state` returns actual section content.

Two modes:

**Overview mode** (`section=None`): Returns headline counters for all 5 readable
HOT sections. Costs ~200 tokens. Injected into system prompt every turn.

```python
{
  "mode": "overview",
  "sections": {
    "beliefs_active": {"fact_count": 3, "entity_count": 2, "pinned_count": 0},
    "scoreboard": {"referent_count": 4, "topic_count": 1, "open_question_count": 0, "user_intent": "trip_planning"},
    "clarifications": {"pending_count": 0, "recently_resolved_count": 1, "is_blocked": False},
    "affective_now": {"current_emotion": "curious", "intensity": 0.6, "valence": 0.7, "empathy_needed": False},
    "narrative_active": {"thread_count": 2, "active_thread_id": "t-001", "arc_position": "middle"}
  }
}
```

**Detail mode** (`section="beliefs_active"`): Returns full structured content for
one section using real read APIs (`list_facts()`, `list_referents()`, etc.).

Per-section extractors:

- `beliefs_active`: `list_facts()` -> `[{id, subject, predicate, object, confidence, source, is_pinned}]`, `get_mentioned_location()`, `get_mentioned_time()`
- `scoreboard`: `list_referents()` -> `[{id, text, entity_id, entity_type, salience}]`, `list_topics()`, `list_open_questions()`, `get_user_intent()`
- `clarifications`: `get_pending()` -> `[{id, agent_id, question, priority, status, options}]`, `list_recently_resolved()`, `is_blocked`
- `affective_now`: `get_metadata()` -> `{current_emotion, intensity, valence, arousal, dominance, trajectory, confidence, source, empathy_needed, celebration_appropriate}`
- `narrative_active`: `get_all_threads()` -> `[{id, title, goal, state, is_goal_met, started_turn, last_active_turn, related_entities}]`, `get_metadata()` -> `{current_thread_id, arc_position, arc_progress}`

Readable sections: `beliefs_active`, `scoreboard`, `clarifications`, `affective_now`, `narrative_active`

Non-readable: `control` (system-only), `history_active` (use `recall_memory`),
`meta` (system-only), `beliefs_history` / `history_recent` / `persona` / `telemetry` (WARM tier).

**Acceptance Criteria**:

- [ ] Overview mode returns headline counters for 5 readable sections
- [ ] Detail mode returns full structured content via per-section extractors
- [ ] `READABLE_SECTIONS` frozenset defines allowed sections
- [ ] `ValueError` on invalid section name
- [ ] Gemini-compatible JSON schema with section enum
- [ ] Injected into system prompt every turn (overview mode) via system prompt builder

---

## Epic 2.4: Action Tool Mocks (3)

**File**: `poc/concierge_fsm_poc/tools/action_mock.py`
**Est**: ~120 lines

### Issue ACT-001: invoke_capability() Mock

| Field | Value |
|-------|-------|
| **Title** | Implement invoke_capability action tool with canned results |
| **Priority** | P0 |
| **Estimate** | 20 min |
| **Status** | NOT STARTED |

**Description**:

Returns canned results based on capability name:

| Capability | Mock Result |
|-----------|------------|
| `tool.execute.weather_lookup` | `{temperature: "45F", conditions: "Partly cloudy", snow: "4 inches base"}` |
| `tool.execute.hotel_booking` | `{hotel: "Hyatt Regency Lake Tahoe", rate: "$289/night", available: true}` |
| `tool.execute.activity_search` | `{activities: [{name: "Heavenly Ski Resort", kid_friendly: true}, {name: "Lake Tahoe Snowshoe Tour", kid_friendly: true}]}` |
| `tool.execute.restaurant_search` | `{restaurants: [{name: "Gar Woods Grill", kid_friendly: true, cuisine: "American"}, {name: "Sunnyside Restaurant", cuisine: "Lakeside seafood"}]}` |
| default | `{error: "Capability not found"}` |

**Acceptance Criteria**:

- [ ] Returns canned data keyed by capability name
- [ ] Simulates latency field `duration_ms`
- [ ] Returns `success`, `data`, `provider_id`

---

### Issue ACT-002: spawn_via_fabric() Mock

| Field | Value |
|-------|-------|
| **Title** | Implement spawn_via_fabric action tool mock |
| **Priority** | P1 |
| **Estimate** | 15 min |
| **Status** | NOT STARTED |

**Description**:

Always returns success with `status="registered"`. Does not actually create agents.

**Acceptance Criteria**:

- [ ] Returns `{success: true, agent_name: <input>, status: "registered"}`

---

### Issue ACT-003: execute_workflow() Mock

| Field | Value |
|-------|-------|
| **Title** | Implement execute_workflow action tool with canned trip planning result |
| **Priority** | P0 |
| **Estimate** | 20 min |
| **Status** | NOT STARTED |

**Description**:

Returns canned workflow result for `workflow.trip_planning`:

```python
{
    "success": True,
    "envelope_id": "env-trip-001",
    "status": "completed",
    "results": {
        "hotel": {"name": "Hyatt Regency Lake Tahoe", "rate": "$289/night", "confirmed": True},
        "activities": [
            {"name": "Heavenly Ski Resort - Kids Zone", "time": "Saturday 10am-2pm"},
            {"name": "Lake Tahoe Snowshoe Tour", "time": "Sunday 9am-12pm"},
        ],
        "total_cost_estimate": "$850",
    },
}
```

**Acceptance Criteria**:

- [ ] Returns canned trip planning results
- [ ] For unknown workflows, returns `status="rejected"`

---

## Epic 2.5: Schema Tool

**File**: `poc/concierge_fsm_poc/tools/schema.py`
**Est**: ~100 lines

### Issue SCH-001: get_capability_schema() Tool

| Field | Value |
|-------|-------|
| **Title** | Implement get_capability_schema with 5 demo capability schemas |
| **Priority** | P0 |
| **Estimate** | 30 min |
| **Status** | NOT STARTED |

**Description**:

Returns hardcoded schemas for the 5 demo capabilities. This is the tool that
enables schema-driven clarification: the LLM calls it, sees required_inputs,
compares against what's available in SessionState, and if required params are
missing, transitions to CLARIFYING.

```python
CAPABILITY_SCHEMAS = {
    "tool.execute.weather_lookup": {
        "name": "tool.execute.weather_lookup",
        "required_inputs": ["location", "date_range"],
        "optional_inputs": ["units"],
        "output_schema": {"temperature": "str", "conditions": "str"},
        "safety_band_min": "GREEN",
        "avg_latency_ms": 200,
    },
    "tool.execute.hotel_booking": {
        "name": "tool.execute.hotel_booking",
        "required_inputs": ["location", "check_in", "check_out", "guests"],
        "optional_inputs": ["budget_max", "star_rating", "amenities"],
        "output_schema": {"hotel": "str", "rate": "str", "available": "bool"},
        "safety_band_min": "AMBER",
        "avg_latency_ms": 1500,
    },
    # ... 3 more
}
```

**Acceptance Criteria**:

- [ ] Returns full schema for any of the 5 demo capabilities
- [ ] Returns `not_found` error for unknown capability names
- [ ] Schema includes `required_inputs`, `optional_inputs`, `output_schema`, `safety_band_min`

---

## Epic 2.6: Tool Registry + Tier Allowlist

**File**: `poc/concierge_fsm_poc/tools/registry.py`
**Est**: ~80 lines

### Issue REG-001: ToolRegistry with Category + Tier Filtering

| Field | Value |
|-------|-------|
| **Title** | Implement ToolRegistry with 14 tools, categories, tier allowlist |
| **Priority** | P0 |
| **Estimate** | 30 min |
| **Status** | NOT STARTED |

**Description**:

Central registry that maps tool names to handler functions, with metadata:

```python
@dataclass
class ToolDefinition:
    name: str
    category: Literal["signal", "cognitive", "read", "action", "meta"]
    handler: Callable
    description: str
    parameters: dict             # JSON schema for LLM function calling
    tiers: set[str]              # {"LOW", "MEDIUM"} -- which tiers allow this tool

class ToolRegistry:
    def __init__(self):
        self._tools: dict[str, ToolDefinition] = {}

    def register(self, tool_def: ToolDefinition) -> None: ...
    def get(self, name: str) -> ToolDefinition: ...
    def get_for_tier(self, tier: str) -> list[ToolDefinition]: ...
    def get_llm_declarations(self, tier: str) -> list[dict]: ...
```

Tier allowlist (from concierge.md Section 10.6):

| Tool | LOW | MEDIUM |
|------|-----|--------|
| `acknowledge` | Y | Y |
| `update_scoreboard` | Y | Y |
| `update_beliefs` | Y | Y |
| `update_clarifications` | Y | Y |
| `update_narrative` | Y | Y |
| `refine_affect` | Y | Y |
| `promote_belief` | -- | Y |
| `recall_memory` | Y | Y |
| `discover_capabilities` | -- | Y |
| `summarize_context` | Y | Y |
| `invoke_capability` | Y | Y |
| `spawn_via_fabric` | -- | Y |
| `execute_workflow` | -- | Y |
| `get_capability_schema` | -- | Y |

**Acceptance Criteria**:

- [ ] All 14 tools registered
- [ ] `get_for_tier("LOW")` returns 9 tools
- [ ] `get_for_tier("MEDIUM")` returns 14 tools
- [ ] `get_llm_declarations()` returns Gemini-compatible function declarations

---

# MILESTONE 3: ReAct Loop (FSM-Aware)

**Goal**: LLM-powered ReAct loop that operates within FSM rails. Drives
DISPATCHING through DELIVERING. Handles clarification and interrupt transitions.
**Depends On**: Milestone 1 (FSM), Milestone 2 (tools)
**Estimated Lines**: ~550
**Files**: `react/loop.py`, `react/scratchpad.py`, `llm/client.py`

---

## Epic 3.1: Scratchpad + Models

**File**: `poc/concierge_fsm_poc/react/scratchpad.py`
**Est**: ~120 lines

### Issue PAD-001: Scratchpad + Finding + LoopBudget Models

| Field | Value |
|-------|-------|
| **Title** | Port Scratchpad, Finding, LoopBudget models from existing PoC |
| **Priority** | P0 |
| **Estimate** | 30 min |
| **Status** | NOT STARTED |

**Description**:

Adapted from `poc/react_scratchpad_poc/core/models.py`. Carry over:

- `Finding`: extracted fact from tool results
- `LoopBudget`: max_iterations, max_tool_calls, token limits
- `Scratchpad`: findings list, tool history, compaction logic, token tracking
- `COGNITIVE_TOOLS` frozenset (from smart_react.py)

Key changes from existing PoC:

- Remove benchmark-specific fields
- Add `fsm_state: State` field to Scratchpad for FSM awareness
- Keep `needs_compaction()` with token-based ratio (0.8 of 128K)

**Acceptance Criteria**:

- [ ] `Finding`, `LoopBudget`, `Scratchpad` dataclasses/models
- [ ] `COGNITIVE_TOOLS` frozenset with all 7 cognitive/signal tool names
- [ ] `needs_compaction()` works with token-based ratio
- [ ] `fsm_state` field on Scratchpad

---

## Epic 3.2: LLM Client

**File**: `poc/concierge_fsm_poc/llm/client.py`
**Est**: ~180 lines

### Issue LLM-001: Gemini Client Adaptation

| Field | Value |
|-------|-------|
| **Title** | Port Gemini client from existing PoC, strip benchmark code |
| **Priority** | P0 |
| **Estimate** | 30 min |
| **Status** | NOT STARTED |

**Description**:

Adapted from `poc/react_scratchpad_poc/llm/gemini_client.py`. Keep:

- `generate()` with function-calling support
- `extract_findings_batch()` for single-LLM-call extraction
- API key loading from `.env`
- Token counting

Remove:

- Benchmark-specific logging/metrics
- Scenario-specific code

Add:

- FSM-aware system prompt template that includes:
  - Current FSM state
  - SessionState snapshot (from HOT sections)
  - Tool allowlist for current tier
  - Pending clarifications
  - Active task scoreboard

**System Prompt Builder (CRITICAL -- do not skip)**:

The system prompt is the bridge between SessionState and the LLM. It MUST
be rebuilt before EVERY LLM call (not just the first). Structure:

```
## Role
You are the FamilyOS Concierge assistant.

## Current State
FSM State: {fsm.state.value}
Turn: {turn_number}
Tier: {phase1_result.tier}
Safety Band: {phase1_result.safety_band}

## SessionState Overview
{read_session_state(manager, section=None)}    <-- ~200 tokens

## Available Tools
{registry.get_llm_declarations(tier)}          <-- tier-filtered

## Instructions
- Use read_session_state(section="...") to pull detail before answering
  belief-dependent questions
- Write discovered facts to beliefs_active via update_beliefs
- Track tasks and entities in scoreboard via update_scoreboard
- Create/switch narrative threads to track conversation topics
- If required info is missing, record a gap via update_clarifications
- Do NOT re-ask the user for info already in beliefs_active
```

This builder lives in `build_system_prompt()` inside `llm/client.py` or a
dedicated `prompts.py` file. It calls `read_session_state(manager, section=None)`
for the overview and `registry.get_llm_declarations(tier)` for tool filtering.

**Acceptance Criteria**:

- [ ] `generate()` works with Gemini 2.5 Flash function-calling
- [ ] `extract_findings_batch()` for post-iteration extraction
- [ ] System prompt includes FSM state + SessionState context
- [ ] `build_system_prompt()` calls `read_session_state(section=None)` for overview
- [ ] System prompt rebuilt before EVERY LLM call (not cached across iterations)
- [ ] Tool declarations filtered by tier via `registry.get_llm_declarations(tier)`
- [ ] API key from `.env` or environment variable

---

## Epic 3.3: FSM-Aware ReAct Loop

**File**: `poc/concierge_fsm_poc/react/loop.py`
**Est**: ~250 lines

### Issue LOOP-001: ReAct Loop Core

| Field | Value |
|-------|-------|
| **Title** | Implement FSM-aware ReAct loop that drives Phase 2 |
| **Priority** | P0 |
| **Estimate** | 2 hr |
| **Status** | NOT STARTED |

**Description**:

The ReAct loop runs inside FSM states DISPATCHING through DELIVERING. It:

1. Receives `Phase1Result` from mock classifier
2. Assembles context: SessionState snapshot + Phase1Result + conversation history
3. Iterates: LLM generates thought+tool_calls -> execute tools -> extract findings
4. Cognitive tools write to real SessionState (COGNITIVE_TOOLS filter skips extraction)
5. Detects clarification need -> triggers FSM CLARIFICATION_NEEDED event
6. Detects completion -> triggers FSM TASK_COMPLETE event
7. Generates final response text

```python
class ReActLoop:
    def __init__(
        self,
        fsm: FSMController,
        tools: ToolRegistry,
        llm: GeminiClient,
        session_manager: SessionStateManager,
        scratchpad: Scratchpad,
    ):
        ...

    async def run(self, phase1: Phase1Result, user_message: str) -> ReActResult:
        """
        Execute Phase 2 ReAct loop.

        Returns:
            ReActResult with final_response, tool_calls_made,
            iterations, findings_count, fsm_transitions
        """
        ...
```

Loop structure per iteration:

1. Build prompt with SessionState snapshot + scratchpad summary
2. Call LLM with tier-filtered tool declarations
3. If LLM returns text only -> done (DISPATCH_COMPLETE)
4. If LLM returns tool calls:
   a. Execute each tool via registry
   b. If tool is cognitive -> result goes to SessionState (skip extraction)
   c. If tool is read/action -> extract findings into scratchpad
   d. If `update_clarifications(record_gap)` called -> check if LLM wants
      to ask user -> handled by demo runner (Phase 1 emits GAPS_DETECTED)
5. Check budget (max_iterations, max_tool_calls)
6. If needs_compaction -> compact scratchpad
7. Next iteration

FSM event firing within loop:

- On entry: `PRELIMINARY_ACK_SENT` (MEDIUM) or immediate execution (LOW)
- During: `PROGRESS_RECEIVED` on progress updates (MEDIUM only)
- On completion: `DISPATCH_COMPLETE` -> DELIVERING
- On interrupt: `INTERRUPT_DETECTED` -> INTERRUPT_HANDLING

**Acceptance Criteria**:

- [ ] FSM transitions: fires PRELIMINARY_ACK_SENT, PROGRESS_RECEIVED, DISPATCH_COMPLETE, RESPONSE_DELIVERED
- [ ] COGNITIVE_TOOLS filter: cognitive/signal results skipped for extraction
- [ ] LOW path: DISPATCH_COMPLETE fires directly from DISPATCHING (no companion)
- [ ] MEDIUM path: PRELIMINARY_ACK_SENT -> COMPANIONING -> PROGRESS_RECEIVED -> PROGRESSING -> DISPATCH_COMPLETE
- [ ] Budget enforcement: max 10 iterations, max 20 tool calls
- [ ] Scratchpad compaction at 80% of context window
- [ ] Returns `ReActResult` with full execution trace

---

### Issue LOOP-002: Clarification Gate

| Field | Value |
|-------|-------|
| **Title** | Implement clarification detection and FSM CLARIFYING transition |
| **Priority** | P0 |
| **Estimate** | 30 min |
| **Status** | NOT STARTED |

**Description**:

When the LLM:

1. Calls `get_capability_schema` and sees required_inputs
2. Determines required params are missing from SessionState/user message
3. Calls `update_clarifications(record_gap, ...)` with the gap
4. Generates a natural language question for the user

The clarification is handled at the demo runner level, not inside the ReAct loop:

- Phase 1 mock detects gaps -> returns `Phase1Result` with `gaps` non-empty
- Demo runner fires `FSM.transition(Event.GAPS_DETECTED)` -> CLARIFYING
- Demo runner displays question, waits for user input
- On user response: `FSM.transition(Event.CLARIFICATION_RECEIVED)` -> ACKING
- Increment round counter. If rounds >= 3: `Event.MAX_ROUNDS_REACHED` -> DISPATCHING
- Re-run Phase 1 with enriched context (merge clarification into message)

Flow coverage:

- T4 (F4): Single round clarification (hotel dates missing)
- T5 (F5): Max rounds (3x clarification, then force-proceed)
- T13 (F18): Resolve round 1, interrupt during round 2
- T20 (F32): Clarification asked, user doesn't respond (timeout)

**Acceptance Criteria**:

- [ ] Phase1 mock returns `gaps` list for under-specified queries
- [ ] Demo runner fires GAPS_DETECTED when gaps non-empty
- [ ] CLARIFICATION_RECEIVED fires on user answer
- [ ] MAX_ROUNDS_REACHED fires after 3 rounds (F5)
- [ ] Round counter tracked in turn context
- [ ] Resume works: user response merges into context

---

### Issue LOOP-003: Interrupt Handler

| Field | Value |
|-------|-------|
| **Title** | Implement interrupt handling during ReAct loop |
| **Priority** | P1 |
| **Estimate** | 30 min |
| **Status** | NOT STARTED |

**Description**:

For the PoC, interrupt is simulated via flags and timers:

**User interrupt (F6, F7, F8, F10, F18, F31)**:

- Demo runner sets `interrupt_pending = True` with the new message
- ReAct loop checks `fsm.is_interruptible()` + flag at start of each iteration
- If interruptible: fire `FSM.transition(Event.INTERRUPT_DETECTED)` -> INTERRUPT_HANDLING
- Save partial scratchpad state to SessionState (Action.PARTIAL_FLUSH)
- Fire `FSM.transition(Event.INTERRUPT_HANDLED)` -> ACKING
- Demo runner processes the new message from ACKING

**Watchdog timeout (F15)**:

- Configurable `watchdog_timeout_ms` (2000ms for demo, 120s real)
- Timer fires `INTERRUPT_DETECTED` if ReAct loop exceeds budget
- Same flow as user interrupt but with `source="watchdog"`

**Non-interruptible rejection (F11)**:

- If `not fsm.is_interruptible()` (DELIVERING state), message is queued
- After `RESPONSE_DELIVERED`, queued message processed as new turn

**User cancel (F31)**:

- "cancel" / "stop" detected in user input during PROGRESSING
- Same interrupt path but no replacement message; return to LISTENING

**Clarification timeout (F32)**:

- Timer fires after 60s (mocked 3s) of no user response during CLARIFYING
- Returns FSM to LISTENING, cleans up partial state

Flow coverage:

- T6 (F6): Interrupt at DISPATCHING
- T7 (F7): Interrupt at COMPANIONING
- T8 (F8): Interrupt at PROGRESSING with partial results
- T9 (F10): Interrupt at CLARIFYING (topic change)
- T13 (F18): Interrupt during round 2 of clarification
- T14 (F11): Non-interruptible DELIVERING rejection
- T15 (F15): Watchdog timeout
- T19 (F31): User cancel
- T20 (F32): Clarification timeout

**Acceptance Criteria**:

- [ ] Loop checks `is_interruptible()` + interrupt flag each iteration
- [ ] Fires INTERRUPT_DETECTED + INTERRUPT_HANDLED events
- [ ] Partial state saved to SessionState via PARTIAL_FLUSH
- [ ] Non-interruptible states queue the message for next turn
- [ ] Watchdog timer fires INTERRUPT_DETECTED after configurable timeout
- [ ] Cancel command triggers interrupt path without replacement message
- [ ] Clarification timeout returns to LISTENING

---

# MILESTONE 4: Demo Runner (Rich TUI)

**Goal**: Interactive CLI with Rich panels, colored FSM transitions, live state display.
**Depends On**: Milestones 1-3
**Estimated Lines**: ~350
**Files**: `demo.py`, `scenarios/trip_timeline.py`

---

## Epic 4.1: Interactive CLI Entry Point

**File**: `poc/concierge_fsm_poc/demo.py`
**Est**: ~200 lines

### Issue DEMO-001: Rich TUI Main Loop

| Field | Value |
|-------|-------|
| **Title** | Implement interactive Rich TUI with FSM state display |
| **Priority** | P0 |
| **Estimate** | 1.5 hr |
| **Status** | NOT STARTED |

**Description**:

Main loop:

```
1. Initialize: SessionStateManager (create_standalone), FSMController, ToolRegistry, LLM
2. Display welcome panel with scenario description
3. While True:
   a. Show current FSM state in header
   b. Show story hint for current turn (from timeline)
   c. Prompt user for input
   d. If "quit"/"exit" -> break
   e. If "snapshot" -> display SessionState snapshot
   f. If "history" -> display FSM transition history
   g. Else:
      - FSM: LISTENING -> ACKING (fire MESSAGE_RECEIVED)
      - Phase 1: classify(message) -> Phase1Result
      - If safety_band == CRISIS:
          FSM: fire CRISIS_DETECTED -> DELIVERING (static response)
      - Elif gaps non-empty:
          FSM: fire GAPS_DETECTED -> CLARIFYING
          Clarification loop (max 3 rounds):
            Display question, wait for user input
            Fire CLARIFICATION_RECEIVED -> ACKING
            Re-classify. If still gaps and rounds < 3: repeat
            If rounds >= 3: fire MAX_ROUNDS_REACHED -> DISPATCHING
      - Else:
          FSM: fire PHASE1_COMPLETE -> DISPATCHING
      - Display classification panel (tier, intent, entities, safety)
      - Phase 2: ReAct loop
        LOW: fire DISPATCH_COMPLETE -> DELIVERING
        MEDIUM: fire PRELIMINARY_ACK_SENT -> COMPANIONING
                fire PROGRESS_RECEIVED -> PROGRESSING
                fire DISPATCH_COMPLETE -> DELIVERING
      - Check for interrupt/cancel/watchdog during loop
      - Display tool calls, findings, FSM transitions in styled panels
      - Display final response
      - FSM: fire RESPONSE_DELIVERED -> LISTENING
      - Show SessionState diff (what changed this turn)
      - Show flow ID (e.g., "Flow F1 completed")
4. Cleanup: manager.stop(), display session summary + coverage report
```

Rich panels to display:

| Panel | Content | When |
|-------|---------|------|
| Header | FSM state, turn number, tier | Always visible |
| Story Hint | Suggested next message from timeline | Before each prompt |
| Classification | Phase1Result fields | After Phase 1 |
| Tool Call | Tool name + arguments + result (condensed) | Each tool execution |
| Acknowledgment | `acknowledge()` message | When ACK fires |
| Response | Final LLM response | After Phase 2 |
| State Diff | SessionState changes this turn | After response |
| Clarification | Question from LLM | When CLARIFYING |

**Phase 1 System Writes (CRITICAL -- do not skip)**:

After `Phase1Result` is obtained but BEFORE the ReAct loop starts, the demo
runner (or loop entry point) MUST write these sections:

```python
# Phase 1 system writes -- populate SessionState before LLM sees it
manager.mutate("control", "update", {
    "turn_number": turn_number,
    "active_agent": "concierge",
    "tier": phase1_result.tier,
    "safety_band": phase1_result.safety_band,
})
manager.mutate("affective_now", "update", {
    "emotion": phase1_result.emotion,
    "intensity": 0.5,  # default from Phase 1
    "valence": 0.0,
    "source": f"phase1:{phase1_result.intent}",
    "turn_number": turn_number,
})
for entity_key, entity_value in phase1_result.entities.items():
    manager.mutate("scoreboard", "add_referent", {
        "text": entity_value,
        "entity_id": f"p1-{entity_key}",
        "entity_type": entity_key,
        "salience": phase1_result.confidence,
    })
```

Without these writes, the LLM will see empty SessionState in the system prompt
and will not know the current tier, safety band, or extracted entities.

**Phase 3 Turn Logger (CRITICAL -- do not skip)**:

After the LLM response is generated and DELIVERED but BEFORE returning to LISTENING,
the demo runner MUST log the turn to `history_active`:

```python
# Phase 3 system writes -- record what happened this turn
manager.mutate("history_active", "append", {
    "turn_number": turn_number,
    "user_message": user_message,
    "assistant_response": final_response,
    "tool_calls": [tc.to_dict() for tc in tool_calls_made],
    "fsm_path": [str(s) for s in fsm.history[-N:]],  # this turn's transitions
    "timestamp": datetime.utcnow().isoformat(),
})
manager.mutate("meta", "update", {
    "turn_end_ts": datetime.utcnow().isoformat(),
    "tokens_used": total_tokens_this_turn,
})
```

Without this, later turns will not be able to see what happened in earlier turns
when the LLM reads `history_active` for recent conversation context.

**Acceptance Criteria**:

- [ ] Rich console with styled panels
- [ ] FSM state displayed in header
- [ ] Classification panel after Phase 1
- [ ] Tool call panels during Phase 2
- [ ] SessionState diff after each turn
- [ ] "snapshot" and "history" commands work
- [ ] Graceful shutdown with `manager.stop()`
- [ ] Phase 1 system writes: control, affective_now, scoreboard, meta BEFORE ReAct loop
- [ ] Phase 3 turn logger: history_active, meta AFTER response delivered
- [ ] Persona pre-load: family profile written to `persona` section at session init

---

### Issue DEMO-002: Session Initialization

| Field | Value |
|-------|-------|
| **Title** | Wire SessionStateManager, FSM, tools, LLM at startup |
| **Priority** | P0 |
| **Estimate** | 30 min |
| **Status** | NOT STARTED |

**Description**:

```python
async def initialize():
    # Real SessionState (SQLite-backed)
    session_id = f"trip-demo-{uuid.uuid4().hex[:8]}"
    db_path = Path.home() / ".familyos" / "poc" / "concierge_fsm.db"
    manager = create_standalone(session_id=session_id, db_path=db_path)
    manager.start()

    # FSM
    fsm = FSMController()

    # Tools
    cognitive = CognitiveToolSet(manager)
    tool_registry = build_registry(cognitive, manager)

    # LLM
    llm = GeminiClient()

    return manager, fsm, tool_registry, llm
```

**Persona Pre-Load (CRITICAL -- do not skip)**:

At session initialization, BEFORE any turns, pre-load family profile into
the `persona` section so the LLM can reference family members without asking:

```python
# Persona pre-load -- family profile for the Lake Tahoe scenario
manager.mutate("persona", "update", {
    "family_name": "Demo Family",
    "members": [
        {"name": "Mom", "role": "parent", "allergies": ["shellfish"], "preferences": ["relaxation", "dining"]},
        {"name": "Dad", "role": "parent", "preferences": ["outdoors", "photography"]},
        {"name": "Jake", "role": "child", "age": 12, "allergies": ["peanuts"], "preferences": ["snow", "adventure"]},
        {"name": "Emma", "role": "child", "age": 8, "preferences": ["indoors", "crafts", "animals"]},
    ],
    "home_location": "San Francisco, CA",
    "vehicle": "SUV",
})
```

**Acceptance Criteria**:

- [ ] `create_standalone()` with PoC-specific db_path
- [ ] `manager.start()` called before any mutations
- [ ] All 14 tools registered
- [ ] LLM client initialized with API key
- [ ] Persona section pre-loaded with family profile BEFORE first turn
- [ ] Phase 1 system writer wired (control, affective_now, scoreboard, meta)
- [ ] Phase 3 turn logger wired (history_active, meta)

---

## Epic 4.2: Story Timeline + Mock Data

**File**: `poc/concierge_fsm_poc/scenarios/trip_timeline.py`
**Est**: ~150 lines

### Issue STORY-001: Trip Timeline Data Structure

| Field | Value |
| ----- | ----- |
| **Title** | Define 20-turn story timeline with hints, flow mapping, and mock response data |
| **Priority** | P1 |
| **Estimate** | 1 hr |
| **Status** | NOT STARTED |

**Description**:

```python
@dataclass
class TurnHint:
    turn_number: int
    flow_id: str                    # e.g. "F1", "F12"
    suggested_message: str
    interrupt_message: str | None   # If turn involves interrupt
    clarification_answers: list[str]  # Pre-scripted clarification responses
    expected_tier: str
    expected_safety: str            # GREEN, AMBER, RED, CRISIS
    expected_tools: list[str]
    description: str
    fsm_path: str                   # Expected state path
    special_flags: dict[str, Any]   # e.g. {"raise_on_next": True, "force_cb_open": True}

TRIP_TIMELINE: list[TurnHint] = [
    TurnHint(
        turn_number=1,
        flow_id="F1",
        suggested_message="What's the weather like in Lake Tahoe this weekend?",
        interrupt_message=None,
        clarification_answers=[],
        expected_tier="LOW",
        expected_safety="GREEN",
        expected_tools=["acknowledge", "invoke_capability", "update_beliefs", "update_scoreboard"],
        description="Normal LOW: direct dispatch, no companion phase",
        fsm_path="L->A(P1C)->D(DC)->De(RD)->L",
        special_flags={},
    ),
    # ... 19 more turns (see Story Timeline section)
]
```

**Acceptance Criteria**:

- [ ] All 20 turns defined with flow_id mapping to `concierge_fsm_flows.md`
- [ ] Interrupt messages provided for F6, F7, F8, F10, F18, F31 turns
- [ ] Clarification answers provided for F4, F5, F18 turns
- [ ] Special flags for F15 (watchdog), F24 (CB open), F26 (classifier fail), F27 (write fail)
- [ ] Mock response data keyed by capability/query for action/read tools
- [ ] FSM path documented per turn matching flow coverage matrix

---

# MILESTONE 5: Tests

**Goal**: Verify all 20 testable flows and all 14 transitions work correctly.
**Depends On**: Milestones 1-4
**Estimated Lines**: ~450
**Files**: `tests/test_fsm.py`, `tests/test_cognitive_tools.py`,
`tests/test_flows.py`, `tests/test_integration.py`

---

## Epic 5.1: FSM Unit Tests

**File**: `poc/concierge_fsm_poc/tests/test_fsm.py`
**Est**: ~120 lines

### Issue TEST-001: FSM Transition Tests (14 transition types)

| Field | Value |
| ----- | ----- |
| **Title** | Test all 14 transition types (18 table entries) and invalid transition rejection |
| **Priority** | P0 |
| **Estimate** | 45 min |
| **Status** | NOT STARTED |

**Test Cases** (22 tests, aligned to `concierge_fsm_flows.md` Part 3):

| Test | From | Event | Expected To | Transition# |
| ---- | ---- | ----- | ----------- | ----------- |
| test_t1_listening_to_acking | LISTENING | MESSAGE_RECEIVED | ACKING | T1 |
| test_t2_crisis_bypass | ACKING | CRISIS_DETECTED | DELIVERING | T2 |
| test_t3_phase1_complete | ACKING | PHASE1_COMPLETE | DISPATCHING | T3 |
| test_t4_gaps_detected | ACKING | GAPS_DETECTED | CLARIFYING | T4 |
| test_t5_clarification_received | CLARIFYING | CLARIFICATION_RECEIVED | ACKING | T5 |
| test_t6_max_rounds_reached | CLARIFYING | MAX_ROUNDS_REACHED | DISPATCHING | T6 |
| test_t7_preliminary_ack | DISPATCHING | PRELIMINARY_ACK_SENT | COMPANIONING | T7 |
| test_t8_low_direct_deliver | DISPATCHING | DISPATCH_COMPLETE | DELIVERING | T8 |
| test_t9_progress_received | COMPANIONING | PROGRESS_RECEIVED | PROGRESSING | T9 |
| test_t10_companion_dispatch_complete | COMPANIONING | DISPATCH_COMPLETE | DELIVERING | T10 |
| test_t11_progress_dispatch_complete | PROGRESSING | DISPATCH_COMPLETE | DELIVERING | T11 |
| test_t12_response_delivered | DELIVERING | RESPONSE_DELIVERED | LISTENING | T12 |
| test_t13a_interrupt_dispatching | DISPATCHING | INTERRUPT_DETECTED | INTERRUPT_HANDLING | T13 |
| test_t13b_interrupt_companioning | COMPANIONING | INTERRUPT_DETECTED | INTERRUPT_HANDLING | T13 |
| test_t13c_interrupt_progressing | PROGRESSING | INTERRUPT_DETECTED | INTERRUPT_HANDLING | T13 |
| test_t13d_interrupt_clarifying | CLARIFYING | INTERRUPT_DETECTED | INTERRUPT_HANDLING | T13 |
| test_t14_interrupt_handled | INTERRUPT_HANDLING | INTERRUPT_HANDLED | ACKING | T14 |
| test_invalid_from_listening | LISTENING | DISPATCH_COMPLETE | InvalidTransitionError | -- |
| test_invalid_from_delivering | DELIVERING | INTERRUPT_DETECTED | InvalidTransitionError | -- |
| test_is_interruptible_true | DISPATCHING/COMPANIONING/PROGRESSING/CLARIFYING | -- | True | -- |
| test_is_interruptible_false | LISTENING/ACKING/DELIVERING/INTERRUPT_HANDLING | -- | False | -- |
| test_history_tracking | -- | multiple | history list correct | -- |

**Acceptance Criteria**:

- [ ] All 14 transition types pass (18 table entries exercised)
- [ ] Invalid transitions raise `InvalidTransitionError`
- [ ] `is_interruptible()` correct for all 8 states
- [ ] History tracking verified
- [ ] DELIVERING rejects INTERRUPT_DETECTED (non-interruptible)

---

## Epic 5.2: Cognitive Tool Integration Tests

**File**: `poc/concierge_fsm_poc/tests/test_cognitive_tools.py`
**Est**: ~80 lines

### Issue TEST-002: Cognitive Tools Write to Real SessionState

| Field | Value |
| ----- | ----- |
| **Title** | Verify each cognitive tool writes to real SessionState via MutationGuard |
| **Priority** | P0 |
| **Estimate** | 30 min |
| **Status** | NOT STARTED |

**Test Cases** (8 tests):

| Test | Tool | Section | Verify |
| ---- | ---- | ------- | ------ |
| test_update_scoreboard_write | update_scoreboard | scoreboard | section has data after write |
| test_update_beliefs_write | update_beliefs | beliefs_active | belief_id returned, data persisted |
| test_update_clarifications_write | update_clarifications | clarifications | gap_id returned |
| test_update_narrative_write | update_narrative | narrative_active | thread_id returned |
| test_refine_affect_write | refine_affect | affective_now | override applied |
| test_promote_belief_warm_to_hot | promote_belief | beliefs_active | belief moved |
| test_mutation_guard_rejection | update_beliefs | beliefs_active | rejection on oversized data (F27) |
| test_snapshot_reflects_writes | multiple | multiple | snapshot shows accumulated data |

All tests use `create_for_testing()` for fast in-memory SessionState.

**Acceptance Criteria**:

- [ ] Each cognitive tool writes to correct section
- [ ] MutationGuard rejects oversized writes (exercises F27 path)
- [ ] Snapshot reflects all accumulated writes

---

## Epic 5.3: Flow Coverage Tests

**File**: `poc/concierge_fsm_poc/tests/test_flows.py`
**Est**: ~200 lines

### Issue TEST-003: Flow Coverage Test Suite (20 flows)

| Field | Value |
| ----- | ----- |
| **Title** | Test all 20 PoC-testable flows from `concierge_fsm_flows.md` |
| **Priority** | P0 |
| **Estimate** | 2 hr |
| **Status** | NOT STARTED |

Each test drives the FSM through a complete flow path, verifying state
transitions and key behaviors. Uses `create_for_testing()` SessionState.

**Test Cases** (20 tests, one per flow):

| Test | Flow | Category | What It Verifies |
| ---- | ---- | -------- | ---------------- |
| test_f1_normal_low | F1 | Happy | L->A->D->De->L (LOW, no companion) |
| test_f2_normal_medium | F2 | Happy | L->A->D->Co->P->De->L (MEDIUM, full path) |
| test_f4_clarification_single | F4 | Clarify | L->A->Cl->A->D->...->De->L (1 round) |
| test_f5_max_clarification | F5 | Clarify | 3 rounds, MAX_ROUNDS_REACHED->D |
| test_f6_interrupt_dispatching | F6 | Interrupt | D(INT)->IH->A->D->...->De->L |
| test_f7_interrupt_companioning | F7 | Interrupt | Co(INT)->IH->A->D->...->De->L |
| test_f8_interrupt_progressing | F8 | Interrupt | P(INT)->IH->A->..., partial results check |
| test_f10_interrupt_clarifying | F10 | Interrupt | Cl(INT)->IH->A->D->De->L (topic change) |
| test_f11_non_interruptible | F11 | Edge | DELIVERING rejects INT, queues msg |
| test_f12_crisis_bypass | F12 | Safety | A(CRISIS)->De->L, no tools, static response |
| test_f13_red_safety | F13 | Safety | Action tools blocked, read/cognitive only |
| test_f14_amber_safety | F14 | Safety | Normal routing, enhanced logging flag |
| test_f15_watchdog_timeout | F15 | Degrade | Timer fires INT during PROGRESSING |
| test_f17_multi_message | F17 | Edge | Second message merged, not interrupt |
| test_f18_clarify_then_interrupt | F18 | Combo | Resolve round 1, interrupt round 2 |
| test_f24_full_fallback | F24 | Degrade | All CB open, canned response |
| test_f26_classifier_failure | F26 | Degrade | Phase 1 throws, heuristic fallback |
| test_f27_write_failure | F27 | Degrade | MutationGuard rejects, LLM adapts |
| test_f31_user_cancel | F31 | Control | Explicit cancel, no replacement topic |
| test_f32_clarification_timeout | F32 | Control | Timeout during CLARIFYING -> LISTENING |

**Acceptance Criteria**:

- [ ] All 20 testable flows pass
- [ ] Each test verifies complete FSM state path (not just start/end)
- [ ] Interrupt tests verify partial state preservation
- [ ] Safety tests verify tool filtering (RED blocks action tools)
- [ ] Degradation tests verify fallback behavior
- [ ] Tests are independent and can run in any order

---

## Epic 5.4: End-to-End Integration Test

**File**: `poc/concierge_fsm_poc/tests/test_integration.py`
**Est**: ~50 lines

### Issue TEST-004: Full 20-Turn Story Integration

| Field | Value |
| ----- | ----- |
| **Title** | End-to-end test running all 20 story turns sequentially |
| **Priority** | P1 |
| **Estimate** | 1 hr |
| **Status** | NOT STARTED |

**Description**:

Runs all 20 turns programmatically (no user input, scripted from `TRIP_TIMELINE`).
Uses `create_for_testing()` for fast execution. Verifies:

1. FSM returns to LISTENING after each turn
2. SessionState accumulates beliefs, scoreboard entries, narrative threads
3. All 14 transition types fired at least once across 20 turns
4. All 8 FSM states visited at least once
5. Clarification loops: single-round (T4), max-rounds (T5), timeout (T20)
6. Interrupts: DISPATCHING (T6), COMPANIONING (T7), PROGRESSING (T8), CLARIFYING (T9)
7. Safety: CRISIS (T10), RED (T11), AMBER (T3)
8. Degradation: watchdog (T15), fallback (T16), classifier fail (T17), write fail (T18)
9. Edge: multi-message (T12), clarify+interrupt (T13), non-interruptible (T14), cancel (T19)
10. Final snapshot contains data from all successful turns

**Acceptance Criteria**:

- [ ] All 20 turns execute without error
- [ ] FSM ends at LISTENING after each turn (or confirmed abandoned for T20)
- [ ] SessionState snapshot grows across turns
- [ ] Coverage report: all 14 transitions fired, all 8 states visited
- [ ] No regressions when run repeatedly

---

# Summary

| Milestone | Epics | Issues | Est. Lines | Depends On |
| --------- | ----- | ------ | ---------- | ---------- |
| M1: FSM Core | 2 | 5 | ~320 | Nothing |
| M2: Tool System | 6 | 12 | ~780 | M1 |
| M3: ReAct Loop | 3 | 5 | ~600 | M1, M2 |
| M4: Demo Runner | 2 | 3 | ~450 | M1-M3 |
| M5: Tests | 4 | 4 | ~450 | M1-M4 |
| **TOTAL** | **17** | **29** | **~2,600** | |

---

# Risk Register

| Risk | Impact | Mitigation |
| ---- | ------ | ---------- |
| SessionState `mutate()` API incompatible with cognitive tool data shapes | HIGH | Validate data shapes against section schemas in M2 before wiring |
| Gemini function-calling format changes | MEDIUM | Isolate in `llm/client.py`, keep existing tested format |
| Rich TUI adds complexity | LOW | Rich is well-tested; styled panels are straightforward |
| Interrupt simulation fidelity | LOW | Real async interrupt is production scope; PoC uses flag-based simulation |
| MutationGuard rejects demo writes | MEDIUM | Use `create_for_testing()` during development; switch to `create_standalone()` for final demo |
| 20-turn story exceeds Gemini context window | MEDIUM | Scratchpad compaction + per-turn context reset (snapshot only, not full history) |
| Phase 1 mock too brittle for 20 varied messages | LOW | Expand keyword rules; fallback to general/LOW is acceptable |
| Watchdog/timeout mocking not representative | LOW | Use configurable delays; production timing is separate concern |

---

# Appendix A: FSM Transition Table (Aligned to `concierge_fsm_flows.md` Part 3)

```text
#   | From                | Event                  | To                  | Actions                              | Guard
----|---------------------|------------------------|---------------------|--------------------------------------|------
T1  | LISTENING           | MESSAGE_RECEIVED       | ACKING              | acquire_lock, run_phase1             | turn_lock available
T2  | ACKING              | CRISIS_DETECTED        | DELIVERING          | crisis_response                      | safety_band == CRISIS
T3  | ACKING              | PHASE1_COMPLETE        | DISPATCHING         | route_by_tier                        | gaps.empty && confidence > 0.6
T4  | ACKING              | GAPS_DETECTED          | CLARIFYING          | send_clarification                   | gaps.non_empty && rounds < 3
T5  | CLARIFYING          | CLARIFICATION_RECEIVED | ACKING              | merge_clarification                  | --
T6  | CLARIFYING          | MAX_ROUNDS_REACHED     | DISPATCHING         | force_proceed, route_by_tier         | rounds >= 3
T7  | DISPATCHING         | PRELIMINARY_ACK_SENT   | COMPANIONING        | send_acknowledge, start_tool_loop    | tier in {MEDIUM, HIGH}
T8  | DISPATCHING         | DISPATCH_COMPLETE      | DELIVERING          | assemble_response                    | tier == LOW
T9  | COMPANIONING        | PROGRESS_RECEIVED      | PROGRESSING         | stream_progress                      | --
T10 | COMPANIONING        | DISPATCH_COMPLETE      | DELIVERING          | assemble_response                    | --
T11 | PROGRESSING         | DISPATCH_COMPLETE      | DELIVERING          | assemble_response                    | --
T12 | DELIVERING          | RESPONSE_DELIVERED     | LISTENING           | flush_and_checkpoint                 | --
T13 | *(interruptible)    | INTERRUPT_DETECTED     | INTERRUPT_HANDLING  | cancel_inflight, partial_flush       | is_interruptible()
T14 | INTERRUPT_HANDLING   | INTERRUPT_HANDLED      | ACKING              | reenter_acking                       | --
```

Interruptible states: DISPATCHING, COMPANIONING, PROGRESSING, CLARIFYING
Non-interruptible: LISTENING, ACKING, DELIVERING, INTERRUPT_HANDLING

---

# Appendix B: Flow-to-Turn Cross Reference

| Flow | Turn | Events Fired | Unique Contribution |
| ---- | ---- | ------------ | ------------------- |
| F1 | T1 | MR, P1C, DC, RD | LOW direct path (T8 transition) |
| F2 | T2 | MR, P1C, PAS, PR, DC, RD | MEDIUM full path (T7, T9, T11) |
| F4 | T4 | MR, GD, CR, P1C, PAS, PR, DC, RD | Single clarification (T4, T5) |
| F5 | T5 | MR, GD, CR, GD, CR, GD, MRR, DC, RD | Max rounds (T6) |
| F6 | T6 | MR, P1C, ID, IHd, P1C, DC, RD | Interrupt at DISPATCHING |
| F7 | T7 | MR, P1C, PAS, ID, IHd, P1C, PAS, PR, DC, RD | Interrupt at COMPANIONING |
| F8 | T8 | MR, P1C, PAS, PR, ID, IHd, P1C, PAS, PR, DC, RD | Interrupt at PROGRESSING + partial |
| F10 | T9 | MR, GD, ID, IHd, P1C, DC, RD | Interrupt at CLARIFYING |
| F11 | T14 | (queued), MR, P1C, DC, RD | Non-interruptible rejection |
| F12 | T10 | MR, CD, RD | Crisis bypass (T2) |
| F13 | T11 | MR, P1C, PAS, PR, DC, RD | RED safety band |
| F14 | T3 | MR, P1C, DC, RD | AMBER safety band |
| F15 | T15 | MR, P1C, PAS, PR, ID(watchdog), IHd | Watchdog timeout |
| F17 | T12 | MR(+merge), P1C, DC, RD | Multi-message batch |
| F18 | T13 | MR, GD, CR, GD, ID, IHd, P1C, DC, RD | Clarify+interrupt combo |
| F24 | T16 | MR, P1C, DC(CB fail), RD | Full fallback |
| F26 | T17 | MR(fail->heur), P1C, DC, RD | Classifier failure |
| F27 | T18 | MR, P1C, DC, RD | Write failure |
| F31 | T19 | MR, P1C, PAS, PR, ID(cancel), IHd | User cancel |
| F32 | T20 | MR, GD, (timeout) | Clarification timeout |
