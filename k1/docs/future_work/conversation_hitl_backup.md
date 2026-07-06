# K1 Concierge — Future Architecture: Conversation Continuity & HITL

> Date: 2026-06-26
> Branch: `feature/prompt-architecture-refactor`
> Status: Design discussion — not implemented

---

## Overview

Three interconnected changes to make K1 conversations feel like talking to a human, not a request/response bot:

1. **React Loop Pause/Resume** — Actors stay alive. They don't terminate and restart.
2. **HITL As Persistent State** — Questions don't expire. User owns the pace.
3. **Conversation Planes** — Multiple conversation scopes in one chat, not one linear thread.

---

## 1. React Loop: Pause/Resume Instead of Terminate/Restart

> **STATUS: DEFERRED — Revisit after Phase 2 (HITL persistent state) is deployed and validated in production.**
> The checkpoint-based resume in `_resolve_needs_human_in_process()` (back.py:1029) already carries conversation continuity. Six loop instantiations vs one is invisible to the LLM — its state is the messages list, which checkpoint faithfully preserves. The risk of two resume code paths (in-memory vs serialized) diverging over time is real. If production data shows checkpoint→fresh-loop handoff produces degradation (tool re-binding errors, budget exhaustion, scratchpad loss), revisit this section with specific failure modes. See §17.2 for full analysis.

### Current Problem

Every conversation event creates a fresh `react_loop()` call. The loop terminates on every `response.final`, every HITL question, every `submit_result`. New loop = new scratchpad, new budget allocation, new tool dispatcher. Only continuity is chat history in SessionState + ReAct checkpoint carried through `HILSubTask`.

```
CURRENT:
  Front: react_loop() → runs → terminates → (FSM transitions)
  Back:  react_loop() → runs → hits HITL → terminates → (FSM transitions)
  Front: react_loop() → runs fresh (HITL_RELAY) → terminates
  User answers
  Front: react_loop() → runs fresh (HITL_RESOLVE) → terminates
  Back:  react_loop() → runs fresh (from checkpoint) → resumes

  6 react_loop() calls for one HITL round-trip.
  Scratchpad destroyed 6 times. Budget re-allocated 6 times.
```

### Proposed Model

`react_loop()` becomes a long-lived coroutine with three states: ACTIVE, PAUSED, TERMINATED. Pausing preserves the loop's in-memory state — iteration counter, message history, tool dispatcher state, budget remaining. Resuming continues from the pause point.

```
PROPOSED:
  Front react_loop() ACTIVE ──→ Back needs HITL ──→ Front PAUSES
    │
  Back react_loop() ACTIVE ──→ hits HITL ──→ Back PAUSES
    │                                        Back emits question to user
    │                                        Back awaits response
    │
  User answers
    │
  Back react_loop() RESUMES from pause point, processes answer
    │
  Back completes ──→ Front react_loop() RESUMES from pause point
    │
  Front weaves result naturally: "...anyway, cookies are done!"

  1 Front react_loop. 1 Back react_loop. Both long-lived.
  Pause/resume, not terminate/restart.
```

### Code Changes

**`react/loop.py` — New control event: `pause_for_hil`**

When the loop drains a `pause_for_hil` control event, instead of terminating:

- The loop emits the HIL question to the user (Back IS an LLM, writes natural language)
- The loop waits for the HIL response via a Future or control queue
- The loop injects both question and answer into its own `messages` list
- The loop continues from the same iteration

**`react/loop.py` — New control event: `pause_for_front`**

When Front's loop drains a `pause_for_front` event:

- Front pauses. Iteration state preserved. Messages list frozen.
- Returns `ReactResult(status="paused", ...)` with snapshot
- Caller stores the snapshot, releases the FrontLock
- When Back's HITL resolves or new user input arrives, Front resumes from snapshot

**`react/control.py` — New BackControlEvent types**

```python
class BackControlEvent:
    event_type: str  # + "pause_for_hil", "pause_for_front", "resume"
```

### What Stays The Same

- `ReActCheckpoint` — still needed for crash recovery, not for every HITL round-trip
- `react_loop()` API — same parameters. Pause is an internal state, not external API change
- Tool dispatcher — same
- Budget tracking — same. Budget counter freezes during pause.

---

## 2. HITL As Persistent State — No Force-Timeout

### Current Problem

`SuspensionManager._watch_timeout()` fires after 60s/120s. Task is auto-cancelled. User is forced to answer on the system's schedule, not their own. Mom doesn't set a timer on "chocolate chip or sugar?" — the question stays open until answered.

### Proposed Model

| What | Current | Proposed |
|------|---------|----------|
| Timer behavior | Hard: 60s → auto-cancel task | Soft: 60s → gentle nudge. Task STAYS SUSPENDED. |
| Task state after timeout | CANCELLED | SUSPENDED indefinitely |
| HITL pane in UI | Disappears after timeout | Stays visible. User answers whenever. |
| Back worker after timeout | Released (cancelled) | Back completes task with `awaiting_decision` status |
| HITL question lifecycle | Ephemeral (dies with timeout) | Persistent in SessionState |

### HITL As A SessionState Section

```
SS.pending_decisions: [
  {
    decision_id: "hil-abc123",
    task_id: "task-001",
    actor: "back",                    // "back" | "planner" | "orchestrator"
    hil_type: "selection",            // "clarification" | "approval" | "selection"
    question: "Which hotel? $280 or $310?",
    options: [
      {"label": "Hotel A — $280/night, 4.5★", "value": "hotel_a"},
      {"label": "Hotel B — $310/night, 4.2★", "value": "hotel_b"}
    ],
    created_at_turn: 12,
    status: "awaiting_user",          // "awaiting_user" | "resolved" | "superseded"
    resolution: null,
    react_snapshot: { ... },          // For task continuation if user answers later
    narrative_summary: (              // NEW: Back's natural-language summary for Front
      "I found two hotels under your $300 budget in downtown Napa. "
      "Hotel A ($280) has better reviews. Hotel B ($310) has a pool."
    ),
    remaining_work: (                 // NEW: What remains after decision
      "Once you choose, I'll book the room and send a confirmation."
    )
  }
]
```

### Back's New Termination Mode

Back no longer pauses indefinitely waiting for HITL. Instead, Back completes the task from its perspective:

Back's `submit_result` should include an optional `narrative_summary` field for Front to incorporate when weaving. See §17.6 for full analysis and handoff quality specification.

```
Back ReAct loop:
  → submit_result(status="awaiting_decision",
                   pending_decision_id="hil-abc123",
                   partial_results=[...],
                   narrative_summary="I found two hotels...",
                   remaining_work="Once you choose, I'll book...",
                   context_for_resume={...})
```

The task is COMPLETED from Back's view. Back has done everything it can without the decision. The worker is released. The lease is returned. No resource leak.

### Front's Role: Decision Surfacing

Front sees `pending_decisions` in SessionState. Front surfaces pending decisions at natural moments:

- **Conversation lull**: "Hey, we never decided on that hotel — want to pick now?"
- **Proactive wake**: User returns after 2 hours. Front: "Welcome back! Still waiting on your hotel choice."
- **User asks**: "What were we deciding about?" → Front reads pending_decisions and presents them.
- **New related task**: User says "book the cheaper hotel" → Front resolves the pending decision automatically.

### What Happens When User Finally Answers

```
User clicks/answers the pending decision:
  → hil.response event published
  → FSM spawns a NEW Back task: "continue task-001 with decision hotel_a"
  → New Back ReAct loop starts with:
      - Original task context from react_snapshot
      - User's decision injected as context
      - Remaining work: book the hotel, confirm, etc.
  → Back completes normally
  → Front weaves result: "Booked Hotel A for you! $280/night."
```

### What Gets Removed

- Hard timeouts on HITL questions — gone. User is never forced to answer on a timer.
- Auto-cancel on timeout — gone. Task stays alive until user resolves or supersedes.
- `SuspensionManager._watch_timeout()` task-cancellation path — replaced with soft nudge.

### What Gets Added

- `SS.pending_decisions` section — new
- `submit_result(status="awaiting_decision")` — new termination mode for Back
- Front's decision surfacing logic — prompts Front to check pending_decisions at natural moments
- Decision continuation flow — spawning new Back task from saved react_snapshot

---

## 3. Conversation Planes — Multiple Scopes, One Chat

### Current Problem

One linear chat. All messages in one thread. Back's HITL question appears inline between Front's messages about Jack. Context collision. Popup explosion for Planner flows (7 questions in a row). No visual separation between "daily chat" and "task coordination."

### Proposed Model

The user's chat is composed of **multiple panes**, each with its own conversation scope:

```
┌─────────────────────────────────────────────────────────┐
│  MAIN CHAT PLANE (Front ↔ User)                         │
│                                                         │
│  User: "Make cookies"                                   │
│  Front: "On it! What kind?"                             │
│  User: "Chocolate chip. Hey, remember Jack?"            │
│  Front: "Jack from soccer?"                             │
│  User: "Yeah, he's moving to Minnesota"                 │
│  Front: "Oh wow, when?"                                 │
│                                                         │
│  ┌─────────────────────────────────────────────────┐    │
│  │  PLANNING PLANE (Planner ↔ User) [active]       │    │
│  │                                                 │    │
│  │  Planner: "Let's plan your Hawaii trip!"        │    │
│  │  Planner: "Which dates are you thinking?"        │    │
│  │  User: "July 15-22"                             │    │
│  │  Planner: "Great! Budget range?"                │    │
│  │  User: "$3000"                                   │    │
│  │  Planner: "Hotel or Airbnb?"                     │    │
│  │  ...                                             │    │
│  └─────────────────────────────────────────────────┘    │
│                                                         │
│  [Hawaii Planning — active] [Cookies — baking...]       │
└─────────────────────────────────────────────────────────┘
```

### Pane Types

| Pane | Actor | Conversation Type | UI Behavior | Persistence |
|------|-------|-------------------|-------------|-------------|
| **Main** | Front ↔ User | Freeform chat, daily conversation | Always visible. Grows with history. | Full session |
| **Planning** | Planner ↔ User | Sustained planning conversation | Dedicated pane. Shows planner FSM state. Active until plan committed. | Until plan complete or session end |
| **Task HITL** | Back ↔ User | One-off decision from Back | Inline in main pane as a decision card. Not a separate pane. | Until resolved or superseded |
| **Notification** | System → User | Results, errors, proactive fills | Inline in main pane. | Ephemeral |

### Design Decision: Task HITL Is NOT A Separate Pane

Task HITL (single question from Back) appears **inline in main pane** as a structured decision card — not a separate pane. Rationale:

- A separate pane for one question is overkill
- The question is transient — answer it, it's gone
- It's related to the conversation that spawned it (the user asked for hotels; now Back needs a choice)
- Planning pane is separate because it's a SUSTAINED back-and-forth (7+ questions)

Task HITL as inline card preserves context while being visually distinct from Front's chat messages.

### Bus Topic Scoping

```
k1.session.{session_id}.main.user.input.v1          ← Main chat
k1.session.{session_id}.main.response.*.v1           ← Main chat responses
k1.session.{session_id}.planning.user.input.v1       ← Planning pane input
k1.session.{session_id}.planning.response.*.v1       ← Planning pane responses
k1.session.{session_id}.task.{task_id}.hil.request.v1 ← Task HITL
k1.session.{session_id}.task.{task_id}.hil.response.v1
```

Or: use `correlation_id` on existing topics to scope messages to panes without new topic proliferation.

### Chat History Partitioning

```
history_active: [
  {pane: "main",       entry_type: "user",    text: "Remember Jack?"},
  {pane: "main",       entry_type: "final",   text: "Jack from soccer?"},
  {pane: "task_hil",   task_id: "task-001",   entry_type: "hil_request",  text: "Which hotel?"},
  {pane: "task_hil",   task_id: "task-001",   entry_type: "hil_response", text: "Under $300"},
  {pane: "main",       entry_type: "user",    text: "He's moving to Minnesota"},
  {pane: "planning",   entry_type: "user",    text: "July 15-22"},
  {pane: "planning",   entry_type: "final",   text: "Great! Budget range?"},
]
```

### History Builders — Per-Pane Filtering

| Builder | Pane Filter | Window | Types Included |
|---------|-------------|--------|----------------|
| `history_to_front_messages()` | `pane == "main"` | 20 entries | user, final, proactive, weave |
| `history_to_back_context()` | `pane == "task_hil"` + matching `task_id` | 5 entries | user, final, hitl_response |
| Planner context | `pane == "planning"` | All entries | user, final |
| Front HITL surfacing | `pane == "task_hil"` where `status == "awaiting_user"` | All pending | hil_request |

### FSM Implications

The FSM does NOT need to manage all panes. Each pane is a separate actor conversation scoped by bus topics:

- **Main pane FSM**: Concierge FSM (LISTENING → DISPATCHING → COMPANIONING → ...). No change to states.
- **Planning pane FSM**: Planner's own FSM (IDLE → SKETCHING → VALIDATING → ...). Planner manages itself.
- **Task HITL**: No FSM state. It's a `pending_decisions` entry in SS. Front surfaces when appropriate.

The Concierge FSM doesn't need `CLARIFYING_WORKER` in the same way — Back's HITL becomes a decision card, not a state transition. Front stays in COMPANIONING. The conversation never pauses.

---

## 4. How Everything Works Together

### Scenario: User asks for hotels, keeps talking about Jack, Back needs decision

```
TURN 5: User asks for hotels
─────────────────────────────
Main pane: User → "Find me hotels in Napa next weekend"
FSM: LISTENING → DISPATCHING
Front: "On it! Let me check what's available."
FSM: COMPANIONING
Back: dispatched → searching hotels


TURN 6: User talks about Jack (Back still searching)
──────────────────────────────────────────────────────
Main pane: User → "Hey remember Jack from soccer?"
FSM: COMPANIONING + user.input → INTERRUPT_HANDLING → DISPATCHING
Front: "Of course! How's he doing?"
FSM: COMPANIONING (Branch 9: has_active_tasks → STAY)
Front react_loop: PAUSED (idle between turns, state preserved)


TURN 7: Back hits HITL — needs hotel choice
─────────────────────────────────────────────
Back's loop: submit_result(needs_human) → loop PAUSED
  → Creates pending_decision in SS:
    {decision_id: "hil-abc", question: "Hotel A $280 or Hotel B $310?"}
  → Back's loop completes: submit_result(awaiting_decision)
  → Worker released. Task is COMPLETED from Back's view.

FSM sees task.complete → DELIVERING
Front react_loop: RESUMED (was paused after Turn 6)
Front receives: task result + pending_decision in SS
Front produces: "Jack's doing great by the way! Oh — I found two hotels in Napa.
                Hotel A is $280, Hotel B is $310. Which works better for you?"
  [Inline decision card: ☐ Hotel A $280  ☐ Hotel B $310]

FSM: DELIVERING + response.final → LISTENING


TURN 8: User answers (could be 10 seconds or 2 hours later)
─────────────────────────────────────────────────────────────
User clicks "Hotel A $280"
  → hil.response published
  → pending_decision status → "resolved"
  → FSM spawns new Back task: "book hotel_a for next weekend"
  → Back executes → completes → Front weaves: "Booked! Hotel A for next weekend."

Main pane continues. Conversation never paused.
```

### Scenario: Hawaii Trip Planning (Planner Flow)

```
Main pane: User → "Let's plan a Hawaii trip"
FSM: LISTENING → DISPATCHING → Front dispatches to Orchestrator
Orchestrator: HIGH tier → PlanRequest → Planner

PLANNING PANE OPENS:
  Planner: SKETCHING
  Planner: "Let's plan this! Which dates are you thinking?"
  User: "July 15-22"
  Planner: "Great. What's your budget range?"
  User: "$3000 total"
  Planner: "Hotel or Airbnb?"
  User: "Hotel — something nice"
  Planner: "Which island?"
  User: "Maui"
  Planner: "Activities you want?"
  User: "Snorkeling, hiking, one nice dinner"
  Planner: "Rental car?"
  User: "Yes please"
  Planner: VALIDATING
  Planner: "Here's your 7-day Maui plan. Approve?"
  User: "Looks perfect!"
  Planner: COMMITTING → COMPLETED

All 8 exchanges in the planning pane. Main pane untouched.
Planner's react_loop: long-lived, pauses between user responses.
Front's react_loop in main pane: stayed PAUSED during planning,
  or stayed COMPANIONING if there were unrelated tasks running.

When planning completes:
  → CommittedPlan published
  → Orchestrator executes DAG
  → Front in main pane weaves result:
    "By the way, your Hawaii trip is all planned! July 15-22, Maui, hotel,
     snorkeling and hiking — I'll send you the details."
```

### What Happens If User Ignores Planning Pane And Keeps Chatting In Main?

```
Main pane keeps going — Front and user talk about Jack, cookies, whatever.
Planning pane stays open with Planner's last question visible.
User can return to planning pane whenever.
Planner's loop is PAUSED, not consuming resources (or completed with
  submit_result(awaiting_decision) if the pause is too long).

If user never returns to planning pane before session ends:
  → Planner's partial state is persisted as pending_decisions in SS
  → On next session, Front surfaces: "We never finished planning Hawaii —
    want to continue?"
```

---

## 5. Implementation Layers — What Changes Where

### Layer 1: react_loop (core change)

| File | Change |
|------|--------|
| `react/loop.py` | Add PAUSED state. New control events: `pause_for_hil`, `pause_for_front`, `resume`. Loop no longer terminates on HITL — it suspends and resumes. |
| `react/control.py` | New `BackControlEvent` types. New `FrontControlEvent` class for Front loop control. |
| `react/checkpoint.py` | Less critical — pause preserves in-memory state. Checkpoint still needed for crash recovery and cross-session resume. |

### Layer 2: HITL (behavior change, not structural)

| File | Change |
|------|--------|
| `k1/hil/service.py` | Remove hard timeout → task-cancel path. Add soft nudge. `needs_human()` returns `awaiting_decision` status. |
| `k1/hil/suspension.py` | `_watch_timeout()`: replace cancel with soft nudge. Add `pending_decisions` persistence. |
| `tools/implementations.py` | `submit_result()`: add `status="awaiting_decision"` mode. Back can complete task while leaving decision open. |
| `k1/concierge/events/hitl.py` | Add `DecisionPending` and `DecisionResolved` canonical events. |

### Layer 3: SessionState (new section)

| File | Change |
|------|--------|
| `k1/sessionstate/` | New section: `pending_decisions`. Schema: decision_id, task_id, actor, hil_type, question, options, status, resolution, react_snapshot. |
| `delta/writer_registry.py` | Register `pending_decisions` writer (FSM via TaskBridge). |

### Layer 4: History & Panes (progressive)

| File | Change |
|------|--------|
| `fsm/history_writer.py` | Add `pane` field to `TypedHistoryEntry`. Add `pane` parameter to `write()`. |
| `react/history.py` | `build_chat_history()`: filter by pane. `build_chat_history_for_back()`: filter by pane + task_id. |
| `bus/topics.py` | Add pane-scoped topic constants (or use correlation_id). |

### Layer 5: Planner Integration (future)

| File | Change |
|------|--------|
| `k1/planner/` | Planner's react loop uses pause/resume. HITL questions go to planning pane topics. |
| `k1/orchestrator/` | Orchestrator routes planning pane messages. |
| `k1/kernel/service.py` | Planner gets session-scoped HIL. Planning pane bus topics registered. |

### Layer 6: UI (future)

| Change |
|--------|
| Multi-pane rendering: main pane, planning pane, inline decision cards. |
| Decision card UX: clickable options, optional text input, no countdown timer. |
| Planning pane UX: collapsible, shows Planner FSM state ("Sketching your trip..."). |
| Pane switcher: user can toggle between main and planning pane. |

---

## 6. What Gets Removed / Simplified

| Removed | Replaced By |
|---------|-------------|
| `CLARIFYING_WORKER` as a Front-relay state | Back talks directly. Decision card in main pane. FSM stays in COMPANIONING. **Audited safe — see §12.12 and §17.5.** |
| `CLARIFYING_USER` uncertainty-driven state | Front asks clarifying questions naturally within DISPATCHING — no state transition needed. Or kept as a lightweight mode. |
| Hard HITL timeout → auto-cancel | Soft nudge. Decision persists in SS. User answers when ready. |
| Back loop terminate → FSM → Front loop start | Both loops pause/resume. No terminate/restart cycle. |
| `_on_task_suspended()` creating HILSubTask + routing to Front | Back creates pending_decision in SS. Front surfaces naturally. |
| `_on_task_resume()` rebuilding ResumeContext | New Back task spawned from react_snapshot when user answers. |

---

## 7. Open Questions

1. **Front pause during Back HITL**: If Front is paused while Back asks a question, but user sends a NEW main pane message — does Front resume to answer the new message, or stay paused until Back's HITL resolves? Proposed: Front resumes. Back's HITL is a decision card — it doesn't block main conversation.

2. **Planner loop pause duration**: Planner's loop may stay paused for hours if user ignores the planning pane. Should Planner complete with `awaiting_decision` after N minutes of inactivity? Proposed: Yes. After 5 minutes of planning pane inactivity, Planner persists state to SS, completes with awaiting_decision, releases resources. When user returns, a new Planner loop is spawned from saved state.

3. **Multiple pending decisions from same task**: If Back asks "which hotel?" and user doesn't answer, then later Back asks "which dates?" for a different task — do both appear as decision cards? Proposed: Yes. Each is a separate pending_decision. Front surfaces them in order of creation or relevance.

4. **Decision superseding**: If Back asked "which hotel?" but then the hotel search was cancelled — what happens to the pending decision? Proposed: `status = "superseded"`. Front doesn't surface superseded decisions. They remain in SS for audit.

5. **Crash recovery with paused loops**: If the process crashes while a loop is paused, what's recovered? Proposed: Pending decisions are in SS (persisted). On recovery, loops restart from saved state. Pause is in-memory and lost — but the decision card in SS preserves the conversation state. The user sees "Still waiting on your hotel choice" after recovery.

---

## 8. How SessionState Is Actually Used Today — Findings From Code

> Source: `k1/sessionstate/` (20 sections), `k1/concierge/actors/front.py`, `k1/concierge/actors/back.py`, `k1/concierge/prompt/builder.py`, `k1/concierge/prompt/back_prompt.py`

### 8.1 SessionState Sections

```
k1/sessionstate/sections/
├── affective_now.py       — Emotion, valence, arousal (Front writes)
├── artifacts_warm.py      — WARM tier: old artifacts
├── beliefs_active.py      — S-P-O triples + confidence (Front writes)
├── beliefs_history.py     — Historical beliefs
├── clarifications.py      — Semantic gaps (Front writes)
├── control.py             — FlowState, TurnLock, IntentClass, SafetyCtx, active_tasks
├── grounding.py           — Spatial/temporal grounding context
├── history_active.py      — TypedHistoryEntry[] (FSM writes via HistoryWriter)
├── history_recent.py      — Recent history buffer
├── meta.py                — Turn count, latency, telemetry
├── narrative_active.py    — Thread state, switches (Front writes)
├── persona.py             — Immutable: tone, family, prefs
├── place_registry.py      — Known locations
├── scoreboard.py          — QUD stack, referents, salience (Front writes)
├── spatial.py             — Spatial context
├── task_artifacts.py      — Durable outputs from completed tasks (FSM writes via TaskBridge)
├── task_state.py          — Task lifecycle per task (FSM writes via TaskBridge)
├── telemetry.py           — Telemetry data
├── temporal.py            — Temporal context
└── trust_level.py         — Trust accumulator
```

### 8.2 Front's SS Reads (from `front.py` + `prompt/builder.py`)

Front reads SS at multiple stages during handler execution:

| Stage | Sections Read | How | Purpose |
|-------|--------------|-----|---------|
| FSM state | `control` | `_safe_get_section(ss, "control")` → `flow_state` | Determine current FSM state |
| Mode selection | `affective_now`, `clarifications`, `task_state` | `affect_dict_from_session()`, `_get_clarification_state()`, `_get_task_state_dict()` | Determine PromptMode + affect band |
| Domain & tier | `control` | `section.domain_context`, `section.tier` | Complexity routing context |
| Scenario data | `task_state`, `clarifications`, `persona` | Varies by mode (STANDARD, WEAVE, HITL_RELAY, etc.) | Mode-specific context |
| Chat history | `history_active` | `_get_history_active()` → `get_typed_entries()` | Last 20 entries for LLM context |
| Family context | `persona` | `_extract_family_context()` → `_preferences.family` | Family members, dietary, DND, tone |
| OPP enrichment | `history_active`, `task_state`, `persona` | Re-reads for dynamic identity + OPP-7 | Enriched context |
| Prompt build | All sections per `SS_READ_CONFIGS` | `DynamicPromptBuilder.build(ss=ss)` | Full prompt assembly |

**Front reads 10 sections total:** `control`, `affective_now`, `clarifications`, `task_state`, `history_active`, `persona`, `beliefs_active`, `scoreboard`, `narrative_active`, `task_artifacts`.

### 8.3 Back's SS Reads (from `back.py` + `prompt/back_prompt.py`)

Back reads SS **ONCE** at task start via `_read_ss_snapshot(ss)`. Returns a pre-rendered dict consumed by `build_back_prompt()`:

| Key | Source Section | Extraction | Prompt Template |
|-----|---------------|------------|-----------------|
| `beliefs_prompt` | `beliefs_active` | `SECTION_RENDERERS["beliefs_active"][0]` → full text | `{beliefs_narrative}` |
| `referents` | `scoreboard` | `section.get_referents()` → dict | `{scoreboard_narrative}` |
| `task_state_prompt` | `task_state` | Full-mode renderer or `.to_prompt()` | `{task_state_narrative}` |
| `task_artifacts_prompt` | `task_artifacts` | Full-mode renderer or `.to_prompt()` | `{artifacts_narrative}` |
| `safety_band` | `control` | `section.safety.band` → GREEN/AMBER/RED | `{safety_narrative}` |
| `history_entries` | `history_active` | `get_typed_entries()` → list | `build_chat_history_for_back()` |
| `persona_prefs` | `persona` | `get("payment_method"/"dietary"/"accessibility")` | `{persona_narrative}` |

**Back explicitly does NOT read:** `affective_now`, `clarifications`, `narrative_active`, `meta` — documented as "Front's concern" or "irrelevant to task execution."

On resume, `back_resume_handler()` calls `_read_ss_snapshot(ss)` **fresh** — capturing any SS changes during suspension.

**Contract:** Snapshot-at-start. Immutable for loop duration. No mid-loop SS reads. Re-read only on resume.

### 8.4 What Already Supports Our Proposals

| Proposal | Existing Support | What's Missing |
|----------|-----------------|----------------|
| **Task summaries** | Back reads `task_state_prompt` — already shows "other tasks in flight." `{task_state_narrative}` is in Back's system prompt. | Needs concise one-liner format per task (currently raw section text). |
| **Pending decisions** | No existing section. `task_state` tracks `SUSPENDED` status + `pending_hil` flag. `HILSubTask` stored in `task_state` entry. | New `pending_decisions` SS section. Or enrich `task_state` entries with decision metadata. |
| **Conversation surface** | `history_active` exists. Front reads last 20. Back reads last 5 (filtered). | A shared "last 5 exchanges" extract without type prefixes, for all actors. |
| **Unified history** | Front and Back read from same `history_active` section. Different windows and filters. | Add `hitl_request`/`hitl_response` visibility to Front when relevant. Remove type prefixes from shared extracts. |
| **Task context per actor** | Back already receives task-specific context (task JSON as user message). Does NOT see other tasks' full details — just summaries via `task_state_prompt`. | Planner context not yet integrated into SS reads. |
| **Actor state** | ReAct messages list — loop-internal, not in SS. ReAct checkpoint saved to `HILSubTask` on suspension. | With pause/resume, checkpoint is less needed for HITL. Still needed for crash recovery. |

### 8.5 What Changes In SessionState (Minimal)

The existing SS architecture already supports our proposals with minimal additions:

**New section or enriched existing:**

```
Option A: New SS section "pending_decisions"
  - Schema: decision_id, task_id, actor, hil_type, question, options,
            status, resolution, react_snapshot, created_at_turn
  - Writer: FSM via TaskBridge
  - Readers: Front (for surfacing), Back (on task resume)

Option B: Enrich task_state entries
  - Add: pending_decision_id, pending_decision_question,
         pending_decision_options, pending_decision_status
  - Simpler. No new section. Decision lives inside the task that spawned it.
  - Drawback: decision outlives the task if task completes with awaiting_decision.
```

**Recommendation:** Option B for V1 (enrich `task_state`). Option A if Planner flows require cross-task decision tracking.

**New history entry types (minimal):**

```
TypedHistoryEntry additions:
  entry_type: "decision_request"   — Back asks user for input
  entry_type: "decision_response"  — User answers
  pane: "main" | "planning"        — optional scope discriminator
```

**History builder changes (minimal):**

```python
# Front sees: user, final, proactive, weave, decision_request, decision_response
# Back sees: user, final, hitl_response, decision_response (for own task_id)
# Planner sees: user, final (pane == "planning")
```

### 8.6 What Does NOT Need To Change

- **Section schemas** — `beliefs_active`, `scoreboard`, `task_state`, `task_artifacts`, `control`, `history_active`, `persona` remain unchanged.
- **Read patterns** — `_read_ss_snapshot()` interface stays. Snapshot-at-start contract stays.
- **Write patterns** — FSM remains single writer. TaskBridge remains the bridge. HistoryWriter remains the sole history writer.
- **MutationGuard** — No changes. SS capacity + tier constraints unchanged.
- **public_types.py** — Stable boundary. Add new types only if new section created.

---

## 9. Consolidated Change List — What We Actually Need To Build

### Phase 1: React Loop Pause/Resume (Foundation)

| # | What | Files | Effort |
|---|------|-------|--------|
| 1.1 | Add `pause_for_hil` control event to `BackControlEvent` | `react/control.py` | ~5 lines |
| 1.2 | Back loop drains `pause_for_hil`: emits question, waits for response via Future, injects into messages, continues | `react/loop.py` | ~40 lines |
| 1.3 | Add `pause_for_front` control event | `react/control.py` | ~5 lines |
| 1.4 | Front loop drains `pause_for_front`: saves state, returns `ReactResult(status="paused")` | `react/loop.py` | ~30 lines |
| 1.5 | Back's `_resolve_needs_human_in_process()` uses new pause mechanism instead of terminating loop | `actors/back.py` | ~30 lines change |

### Phase 2: HITL As Persistent State

| # | What | Files | Effort |
|---|------|-------|--------|
| 2.1 | Add `status="awaiting_decision"` to `submit_result()` tool | `tools/implementations.py`, `tools/schemas_back.py` | ~20 lines |
| 2.2 | Back completes task with `awaiting_decision` — creates pending decision in `task_state` entry, releases worker | `actors/back.py` | ~30 lines |
| 2.3 | Add `pending_decision_*` fields to `TaskStateEntry` | `k1/sessionstate/sections/task_state.py` | ~15 lines |
| 2.4 | Remove hard timeout → task-cancel in `SuspensionManager._watch_timeout()`. Replace with soft nudge. | `k1/hil/suspension.py` | ~15 lines change |
| 2.5 | Front's `DynamicPromptBuilder` reads pending decisions from `task_state` for surfacing | `prompt/builder.py` | ~20 lines |
| 2.6 | Decision continuation: FSM spawns new Back task from saved `react_snapshot` when user answers | `fsm/controller.py` | ~40 lines |

### Phase 3: Handoff Quality & Voice Consistency (Context Layering)

> **Renamed from "Unified Voice" — the real problem is handoff quality, not identity headers. See §17.6.**

| # | What | Files | Effort |
|---|------|-------|--------|
| 3.1 | Add shared `IDENTITY_BLOCK` to all three actor prompts (Front, Back, Planner) | `prompt/builder.py`, `prompt/back_prompt.py`, planner prompt | ~20 lines |
| 3.1a | Add `narrative_summary` field to Back's `submit_result` — natural-language summary of what was done and why, for Front to quote/paraphrase when weaving | `tools/implementations.py`, `tools/schemas_back.py` | ~15 lines |
| 3.1b | Add `remaining_work` field to Back's `submit_result` — what remains after the decision, for continuation context | `tools/implementations.py`, `tools/schemas_back.py` | ~10 lines |
| 3.1c | Add `{back_narrative}` and `{back_remaining}` to Front's weave prompt template | `prompt/builder.py` | ~5 lines |
| 3.2 | Add "conversation surface" extract — last 5 exchanges without type prefixes | `react/history.py` | ~15 lines |
| 3.3 | Add task summary rendering — concise one-liner per active task | `prompt/back_prompt.py` (`_task_state_narrative`) | ~20 lines |
| 3.4 | Remove type prefixes from `history_to_front_messages()` for shared surface | `react/history.py` | ~5 lines change |
| 3.5 | Add `pane` field to `TypedHistoryEntry` (optional, default `"main"`) | `fsm/controller.py` (TypedHistoryEntry), `fsm/history_writer.py` | ~10 lines |

### Phase 4: Planner Integration (Future)

| # | What | Files | Effort |
|---|------|-------|--------|
| 4.1 | Planner uses pause/resume react loop | `k1/planner/` | ~50 lines |
| 4.2 | Planner reads SS via same `_read_ss_snapshot()` pattern | `k1/planner/` | ~30 lines |
| 4.3 | Planner HITL goes to `pending_decisions` via `task_state` enrichment | `k1/planner/` | ~20 lines |
| 4.4 | Orchestrator routes planning pane messages on session bus | `k1/orchestrator/` | ~15 lines |

### Total Estimated Effort

| Phase | Files Touched | New Lines | Changed Lines |
|-------|--------------|-----------|---------------|
| Phase 1 | 3 | ~80 | ~30 |
| Phase 2 | 5 | ~155 | ~15 |
| Phase 3 | 5 | ~95 | ~25 |
| Phase 4 | 3 | ~115 | 0 |
| **Total** | **~12** | **~445** | **~70** |

Most changes are additive. No architectural rewrite. The existing SS infrastructure, read patterns, write patterns, and FSM state machine remain intact.

---

## 10. Production Hardening — Risks & Mitigations From Architecture Review

> These risks were identified during external architecture review and MUST be addressed before production deployment. They are ordered by severity.

### 10.1 The "Stale World" Problem (Temporal Drift) — CRITICAL

**Risk:** If a user takes 3 days to answer "Which hotel?", the real-world data (prices, availability, dates) has changed. If Back resumes from a 3-day-old `react_snapshot` and blindly executes the booking tool, it will either fail via API error or hallucinate a confirmation.

**Mitigation — Pre-Resume Validation:** Every resumed loop must check data freshness before executing action tools:

```python
# In react_loop, first iteration after resume from long pause:
if self._paused_duration > self._data_freshness_ttl:
    # DON'T execute the next tool from the snapshot.
    # First iteration after resume MUST be refresh_context() or check_availability().
    enforce_refresh = True
```

| Resume Context | Required First Action |
|---------------|----------------------|
| Hotel booking (prices) | `check_availability()` — verify price + dates |
| Weather check | `refresh_weather()` — pull current forecast |
| Calendar scheduling | `check_calendar_conflicts()` — verify slot still open |
| Generic LLM task | Re-read relevant SS sections fresh |

**Implementation:**

- Add `data_freshness_ttl` field to `pending_decision` / `react_snapshot`
- Add `refresh_required: bool` flag to resume context
- Back's react loop checks this flag on first post-resume iteration
- If `refresh_required=True`, enforces that the first tool call is a validation/refresh tool, not an action tool

### 10.2 Short Pause vs Long Pause — In-Memory vs Serialized State

**Risk:** Coroutines alive in memory for hours holding DB/HTTP connections cause memory fragmentation and block deployments. Process restart (deployment, crash) kills in-memory coroutines instantly.

**Mitigation — Two-Tier Pause Strategy:**

| Pause Duration | Strategy | State Location |
|---------------|----------|---------------|
| **Short Pause** (< 60s) | Keep coroutine alive. Await Future. | In-memory |
| **Long Pause** (> 60s) | Serialize full state to SS. Destroy coroutine. Spawn fresh on resume. | SessionState |

**Serialization must be comprehensive enough to perfectly recreate the LLM's chain-of-thought:**

```python
# What gets serialized for long pause:
react_snapshot = {
    "messages": [...],               # Full ReAct message history
    "tool_history": [...],           # Tool call records
    "completed_tool_call_ids": [...], # Prevent re-execution
    "completed_tool_arg_keys": [...], # Prevent re-execution by args hash
    "last_iteration": 5,             # Resume from iteration 6
    "budget_remaining": 3,           # Remaining iterations
    "scratchpad": {...},             # Ephemeral loop state (ADR-0098)
    "tool_dispatcher_state": {...},  # Dispatcher internal state
    "paused_at_ns": 123456789,       # For freshness calculation
    "data_freshness_ttl_seconds": 3600, # How long data stays valid
}
```

**Note:** The current `ReActCheckpoint` already captures `messages`, `tool_history`, `completed_tool_call_ids`, `suspension_count`, `budget_remaining`, `last_iteration`, `scratchpad`. It needs to be enriched with `tool_dispatcher_state` and `data_freshness_ttl`.

### 10.3 State Bloat & "Zombie" Decisions

**Risk:** If users ignore planning panes or HITL cards, `pending_decisions` grows indefinitely in SessionState, increasing latency and token cost for every subsequent turn. A session with 50 stale pending decisions becomes slow.

**Mitigation — Decay/Relevance Strategy:**

| Age | Action |
|-----|--------|
| < 24 hours | Active. Front surfaces at natural moments. |
| 24h – 7 days | Dormant. Front surfaces only if user asks or context matches. |
| 7 – 30 days | Archived. Moved to `archived_decisions` section. Not in active SS reads. |
| > 30 days | Purged. Removed entirely. Front mentions: "We had an old decision about hotels — want to restart?" |

**Contradiction Detection:** If user says something that contradicts a pending decision:

- User: "I'm not going to Napa anymore" → Front marks `pending_decision{hotels_in_napa}` as `superseded`
- User: "Book the cheapest one" → Front auto-resolves `pending_decision{hotel_choice}` with the cheapest option

**Implementation:**

- Background GC worker: sweeps `pending_decisions` every hour
- Front prompt includes pending decisions summary; LLM can mark them `superseded` via cognitive tools
- `SS.archived_decisions` section for cold storage

### 10.4 Cross-Plane Context Blindness — Facts Must Be Global

**Risk:** If history is strictly partitioned by pane, facts established in one pane are invisible to other panes. User says "My budget is $3000" in Planning Pane. Later says "Find me a nice dinner" in Main Pane. Main Pane LLM doesn't know about the budget constraint.

**Mitigation — Global Beliefs, Scoped History:**

```
HISTORY (partitioned by pane for context window management):
  Main pane history → Front sees
  Planning pane history → Planner sees
  Task HITL history → Back sees

BELIEFS (global, all actors read):
  SS.beliefs_active → Front, Back, Planner ALL read this
  SS.persona → ALL read this
  SS.scoreboard.referents → ALL read this
  SS.task_state → ALL read task summaries
```

**Rule:** When any actor extracts a durable fact (budget, preference, constraint, decision), it MUST be written to `beliefs_active` or `persona` — NEVER kept only in chat history. Chat history is scoped. Beliefs are global.

**Implementation:**

- Planner's `extract_facts()` stage writes to `beliefs_active` via SS writer port
- Back's `submit_result()` includes `extracted_beliefs: [...]` that Front writes to SS
- Front's cognitive tools (`update_beliefs()`) remain the primary belief writer
- **ENFORCEMENT (NEW):** `beliefs_active` writer MUST reject writes from scoped panes unless the fact is marked `global=True`. This prevents Planner from writing pane-local facts as global beliefs by accident. The contract: `write_belief(subject, predicate, object, confidence, global=False)` — if `global=False` and the writer's source is scoped (planner, task_hitl), the write is routed to a pane-local belief store instead. Only `global=True` writes go to the shared `beliefs_active` section.

### 10.5 Enriched `react_snapshot` For Perfect Resume

**Current state:** `ReActCheckpoint` saves `messages`, `tool_history`, `completed_tool_call_ids`, `last_iteration`, `budget_remaining`, `scratchpad`.

**Needed additions for long pause resume:**

| Field | Purpose |
|-------|---------|
| `tool_dispatcher_state` | Which tools were bound, which were attempted, allowlist state |
| `data_freshness_ttl` | How long the snapshot data remains valid |
| `paused_at_ns` | Wall clock when paused — for freshness calculation |
| `capability_bindings` | Which Fabric capabilities were discovered + bound |
| `last_tool_result_data` | The actual response from the last tool call (not just success/failure) |

### 10.6 `hitl_metadata` For Back's `awaiting_decision`

When Back submits `awaiting_decision`, it should declare data freshness requirements:

```python
submit_result(
    status="awaiting_decision",
    pending_decision_id="hil-abc123",
    hitl_metadata={
        "data_freshness_ttl": "24h",            # Hotel prices valid for 24h
        "refresh_on_resume": ["check_availability"], # Must re-validate before booking
        "critical_fields": ["price", "dates", "room_type"], # These MUST be re-checked
        "can_proceed_without_user": False,       # Cannot auto-resolve
    }
)
```

This metadata is stored alongside the `react_snapshot` in `pending_decision`. When the user answers after the TTL, the resume flow enforces a context refresh before executing the next action tool.

### 10.7 UI Affordances For Multi-Actor Conversation

**Risk:** User doesn't know which "brain" they're talking to. Three actors producing output in one chat requires clear visual distinction.

**Mitigation:**

| Visual Element | Purpose |
|---------------|---------|
| Subtle actor indicator | Small icon/color on each message: 🟢 Front (chat), 🔵 Back (task), 🟣 Planner (planning) |
| Decision cards | Visually distinct from chat messages — bordered, tappable, no timestamp pressure |
| Planning thread | Indented/collapsible block within main chat. Shows Planner FSM state. |
| Actor transition | When Back completes and Front weaves: Front message is normal chat style even though it contains Back's results |

**Design principle:** The actor distinction should be subtle enough that new users don't notice it, but visible enough that engaged users can understand what's happening. Most messages should look like they came from "the Concierge" — one voice.

### 10.8 Garbage Collection Worker

**Risk:** `pending_decisions` accumulates indefinitely without cleanup.

**Implementation:**

```python
class PendingDecisionsGC:
    """Hourly sweep of pending_decisions."""

    ARCHIVE_AFTER_DAYS = 7
    PURGE_AFTER_DAYS = 30

    async def sweep(self, ss: SessionStateManager):
        for decision in ss.pending_decisions.get_all():
            age_days = (now - decision.created_at).days

            if decision.status == "awaiting_user" and age_days >= self.PURGE_AFTER_DAYS:
                ss.archived_decisions.add(decision)
                ss.pending_decisions.remove(decision.decision_id)

            elif decision.status == "resolved" and age_days >= self.ARCHIVE_AFTER_DAYS:
                ss.archived_decisions.add(decision)
                ss.pending_decisions.remove(decision.decision_id)
```

---

## 11. Updated Open Questions (With Answers From Review)

1. **Front pause during Back HITL + new user input:** Front MUST resume. The pause is an implementation detail. User sees continuous conversation. Front processes the new message and may weave: *"Jack is doing great! By the way, I still need you to pick between Hotel A and B."*

2. **Planner loop pause duration:** Planner MUST complete with `awaiting_decision` after 5 minutes. Cannot hold a coroutine hostage. Serialize FSM state + partial plan to SS. Destroy coroutine. Spawn fresh on user return.

3. **Multiple pending decisions:** Surface all, but group by relevance. Don't spam the user. *"We have a few pending choices for your Napa trip: Hotel, Dates, and Rental Car. Want to knock them out now?"*

4. **Decision superseding:** `status = "superseded"` is correct. Front must explicitly acknowledge: *"Got it — trip cancelled. I've discarded the hotel and rental car choices."*

5. **Crash recovery:** In-memory pause is volatile. On recovery, `pending_decisions` in SS is the source of truth. Front: *"Sorry, I had a quick reboot! We were still waiting on your hotel choice."* Spawn new loop from `react_snapshot`.

---

## 12. Grounded Spec — Actual Code Touchpoints

> This section grounds every proposal from §1–§4 against real code. All findings are from reading the actual source, not inferred from the spec.

### 12.1 React Loop — What Actually Exists

**File:** `k1/concierge/react/loop.py` (line 1048)
**Signature:** `async def react_loop(actor, system_prompt, messages, tools, max_iterations, model, tool_dispatcher, on_text_response, cancellation_check, trace_id, session_id, scenario, validator, on_stream, control_queue, completed_tool_call_ids, completed_tool_arg_keys, reasoning_effort) -> ReactResult`

**Termination conditions (what causes the loop to return):**

| Condition | Status | Actor |
|-----------|--------|-------|
| Text response with NO tool calls | `"complete"` | Front only |
| `submit_result()` tool call | `"complete"` or `"suspended"` | Back only |
| `max_iterations` reached | `"budget_exhausted"` | Both |
| Degenerate/malformed output after retries | `"loop_degenerate"` | Both |
| `cancellation_check()` returns True | `"cancelled"` | Both |
| Back exhausts without `submit_result` | `"missing_submit_result"` | Back only |

**Key finding: NO pause mechanism exists.** The loop is a one-shot coroutine. It runs, it terminates, it returns a `ReactResult`. There is no "paused" status. The only way to "resume" is to call `react_loop()` again with the checkpoint state passed as `completed_tool_call_ids` and `completed_tool_arg_keys`.

**Control queue draining (`_drain_control_events`, line ~1260):**

- Drains `BackControlEvent` from `control_queue: asyncio.Queue`
- Handles `cancel` → sets `cancel_requested = True`
- Handles `parameter_update` → appends control message to messages, extends budget if at cap
- **No other event types handled.** No `pause_for_hil`, no `resume`, no `pause_for_front`.

**ReactResult dataclass (line ~500):**

```python
@dataclass
class ReactResult:
    status: str          # "complete", "suspended", "cancelled", "budget_exhausted", etc.
    text: str | None     # Front: final response text. Back: None.
    data: dict | None    # Back: submit_result() arguments. Front: None.
    dispatched_tasks: list[dict]
    parallel_tool_calls: int
    sequential_tool_calls: int
    iteration_durations_ms: list[int]
    loop_events: list[dict[str, Any]]
```

### 12.2 Control Events — What Actually Exists

**File:** `k1/concierge/react/control.py`
**`BackControlEvent` dataclass:**

```python
@dataclass(slots=True)
class BackControlEvent:
    event_type: str        # Currently: "cancel" | "parameter_update"
    task_id: str
    payload: dict[str, Any]
    created_at_ns: int
    received_at_iteration: int
```

**`ReactLoopEvent` dataclass:** Observability-only marker for notable loop decisions. Not used for control.

**Key finding:** Only TWO event types exist: `cancel` and `parameter_update`. Adding `pause_for_hil`, `pause_for_front`, and `resume` requires extending `_drain_control_events()` in `loop.py` and the `BackControlEvent` enum.

### 12.3 ReActCheckpoint — What Actually Exists

**File:** `k1/concierge/react/checkpoint.py`

```python
@dataclass(frozen=True, slots=True)
class ReActCheckpoint:
    task_id: str
    messages: list[dict[str, Any]]
    tool_history: list[dict[str, Any]]
    completed_tool_call_ids: list[str]
    suspension_count: int
    budget_remaining: int
    last_iteration: int
    scratchpad: dict[str, Any]
    version: int = 1
```

**Key finding:** This is ALREADY the serialization format for long-pause resume. It captures messages, tool history, completed IDs, budget, iteration. What's MISSING from our spec's §10.5:

- `tool_dispatcher_state` (which capabilities were bound)
- `data_freshness_ttl` (how long snapshot data stays valid)
- `paused_at_ns` (wall clock when paused)
- `capability_bindings` (discovered + bound capabilities)

The `completed_tool_keys()` method builds `{tool_name}:{args_hash}` dedup keys from `tool_history` — this prevents re-execution on resume. Already implemented.

### 12.4 HITL Flow — What Actually Exists

**File:** `k1/concierge/actors/back.py` (line 1029)
**Function:** `_resolve_needs_human_in_process()`

This is the ACTUAL HITL implementation. Here's the exact flow:

```
Back react_loop() returns ReactResult(status="suspended", data={...})
  → back_handler detects status="suspended"
  → calls _resolve_needs_human_in_process(result, hil_port, ...)
  → Builds NeedsHumanRequest from result.data:
      caller_key=f"back:{task_id}"
      hil_type=data.get("hil_type", "clarification")
      question=data.get("question", "...")
      options=normalized options
      timeout_ms=config.actors.back.hitl_timeout_s * 1000
  → Calls hil_port.needs_human(req) — AWAITS THE FUTURE
  → On timeout: returns ReactResult(status="cancelled", error_code="HIL_TIMEOUT")
  → On response: appends resume message to messages list
  → Calls react_loop() AGAIN with:
      completed_tool_call_ids from checkpoint
      completed_tool_arg_keys from checkpoint
      budget from checkpoint (cp_budget_remaining)
  → Returns the new ReactResult
  → Loop continues for max_rounds (max_suspensions_per_task, default 2)
```

**Key findings:**

1. **The multi-round HIL loop already exists.** `_resolve_needs_human_in_process` loops up to `max_rounds` (configurable, default 2). Each round: send request → await response → call `react_loop()` again.

2. **Checkpoint-based resume already works.** The function passes `completed_tool_call_ids` and `completed_tool_arg_keys` from the checkpoint to prevent re-execution. Budget remaining is preserved.

3. **Hard timeout exists and is enforced.** `response.timed_out` check returns `status="cancelled"` with `error_code="HIL_TIMEOUT"`. This is the "force user to answer" behavior we want to replace with persistent state.

4. **The function calls `react_loop()` FRESH each round.** Not pause/resume — it's a new coroutine with checkpoint state injected. This is EXACTLY what the spec proposes to change.

### 12.5 Front HITL Modes — What Actually Exists

**File:** `k1/concierge/actors/front.py`

**HITL_RELAY mode (line 520):**

- `_extract_scenario_data(PromptMode.HITL_RELAY, ...)` unwraps the HIL envelope
- Extracts: `hil_type`, `hil_question`, `hil_options`, `hil_side_effects`, `task_action`, `task_context`
- Front's react_loop runs with `max_iterations=1` (from `CRISIS_MAX_ITERATIONS`)
- Front produces ONE text response: the natural-language question
- `on_text_response` is called AFTER react_loop returns (not inside the loop)

**HITL_RESOLVE mode (line 554):**

- `_extract_scenario_data(PromptMode.HITL_RESOLVE, ...)` reads suspended task from `task_state`
- Extracts: `original_question`, `user_answer`, `hil_type`, `hil_options`, `pending_hil_id`, `task_id`
- Front's react_loop runs with `max_iterations=3` (from config)
- After react_loop: `_build_resolution()` constructs the resolution dict
- After resolution: `_build_resolution_frame()` creates `HILResolutionFrame`
- `build_task_resume()` envelope is published → Back resumes
- The `task.resume` emission happens in `front_handler` AFTER react_loop returns

**Key finding:** Front HITL_RELAY and HITL_RESOLVE are SEPARATE react_loop calls. Each one starts fresh. The spec proposes collapsing these into the main Front loop's pause/resume cycle.

### 12.6 Back SS Reads — What Actually Exists

**File:** `k1/concierge/actors/back.py`

`_read_ss_snapshot(ss)` reads SS ONCE at task start:

```python
snapshot = {
    "beliefs_prompt": ...,          # from beliefs_active section
    "referents": ...,               # from scoreboard section
    "task_state_prompt": ...,       # from task_state section
    "task_artifacts_prompt": ...,   # from task_artifacts section
    "safety_band": ...,             # from control section
    "history_entries": ...,         # from history_active section
    "persona_prefs": ...,           # from persona section
}
```

**Contract:** Snapshot-at-start. Immutable for loop duration. On HIL resume, `_read_ss_snapshot()` is called AGAIN to capture any SS changes during suspension. This is in `_resolve_needs_human_in_process` — the fresh `react_loop()` call uses the updated snapshot.

**Key finding for our spec:** The re-read-on-resume pattern ALREADY exists. When Back resumes after HIL, it gets fresh SS state. This partially addresses the "stale world" problem (§10.1) — beliefs and task state are fresh. But tool results from the checkpoint (prices, availability) are NOT re-validated.

### 12.7 Front SS Reads — What Actually Exists

**File:** `k1/concierge/actors/front.py`

Front reads SS at MULTIPLE stages during handler execution:

1. `determine_mode()` — reads `control`, `affective_now`, `clarifications`, `task_state`
2. `_extract_scenario_data()` — reads mode-specific sections
3. `DynamicPromptBuilder.build(ss=ss)` — reads ALL sections per `SS_READ_CONFIGS`
4. After react_loop — reads `task_state` for HITL_RESOLVE resolution

**Key finding:** Front's SS reads are NOT snapshot-at-start. They happen at multiple points during handler execution. This means Front always sees the LATEST SS state. This is different from Back's snapshot pattern.

### 12.8 Tool Dispatcher — What Actually Exists

**File:** `k1/concierge/tools/dispatcher.py`

The `ToolDispatcher` manages:

- Allowlist enforcement (which tools are available per actor/tier)
- Budget tracking (tool call count limits)
- Schema validation
- Policy checks (safety band, side effects)
- Execution routing (to Fabric, MCP, K0, WASM)
- Result recording (`ToolResult`)

**Key finding for our spec:** The dispatcher state (which capabilities were bound, which were attempted, allowlist state) is NOT currently serialized in `ReActCheckpoint`. For long-pause resume (§10.2), we need to add `tool_dispatcher_state` serialization. The `_bind_tool_context()` function in `back.py` binds correlation scope — this state would need to be preserved.

### 12.9 What the Spec Got Right vs Wrong

**Got right:**

- `ReActCheckpoint` is the right serialization format for long pause (just needs enrichment)
- `completed_tool_call_ids` dedup prevents re-execution on resume
- `control_queue` is the right injection point for new control events
- `BackControlEvent` is the right extension point for `pause_for_hil`
- Front HITL_RELAY with `max_iterations=1` is wasteful — it starts a whole loop for one response
- Back's multi-round HIL via `_resolve_needs_human_in_process` already does checkpoint-based resume

**Got wrong or oversimplified:**

- The spec says "Back loop pauses" — but the loop TERMINATES with `status="suspended"`. The "pause" happens in `_resolve_needs_human_in_process`, which is the CALLER, not the loop itself.
- The spec says "Front loop pauses" — but Front's loop always terminates. The "pause" would need to happen in `front_handler`, which is the CALLER.
- The spec proposes adding `pause_for_hil` as a control event DRAINABLE inside the loop. But the loop's `_drain_control_events` currently only handles `cancel` and `parameter_update`. Adding a new event type that causes the loop to yield control mid-iteration is a significant change — it would need to break out of the iteration loop and return a special status.
- The spec says `submit_result(status="awaiting_decision")` is new. But `submit_result` already supports `result_type="needs_human"` — this IS the awaiting_decision mode. The difference is that currently it triggers the hard-timeout await, whereas we want it to create a persistent `pending_decision` and release the worker.

### 12.10 Revised Implementation Plan (Grounded)

Based on actual code, here's what needs to change:

**Phase 1: Control Events (3 files, ~80 lines)**

| # | Change | File | Line |
|---|--------|------|------|
| 1.1 | Add `"pause_for_hil"` to `BackControlEvent.event_type` enum | `react/control.py` | ~15 |
| 1.2 | Add `pause_for_hil` handling in `_drain_control_events()`: emit question, await Future, inject response, continue | `react/loop.py` | ~1260 |
| 1.3 | Add `"pause_for_front"` to `BackControlEvent.event_type` | `react/control.py` | ~15 |
| 1.4 | Add `pause_for_front` handling: save state, return `ReactResult(status="paused")` | `react/loop.py` | ~1260 |

**Phase 2: HITL Persistent State (5 files, ~140 lines)**

| # | Change | File | Line |
|---|--------|------|------|
| 2.1 | Modify `_resolve_needs_human_in_process()`: on timeout, create `pending_decision` in SS instead of returning `cancelled` | `actors/back.py` | ~1140 |
| 2.2 | Add `pending_decision_*` fields to `TaskStateEntry` (or new SS section) | `sessionstate/sections/task_state.py` | New |
| 2.3 | Front's `DynamicPromptBuilder` reads pending decisions for surfacing | `prompt/builder.py` | New |
| 2.4 | Decision continuation: FSM spawns new Back task from `react_snapshot` | `fsm/controller.py` | New |
| 2.5 | Remove hard timeout → task-cancel in `SuspensionManager` | `k1/hil/suspension.py` | Modify |

**Phase 3: Unified Voice (4 files, ~60 lines)**

| # | Change | File | Line |
|---|--------|------|------|
| 3.1 | Extract shared `IDENTITY_BLOCK` constant | `prompt/builder.py` | New |
| 3.2 | Add `IDENTITY_BLOCK` to Back's system prompt | `prompt/back_prompt.py` | ~50 |
| 3.3 | Add "conversation surface" extract (last 5 exchanges, no prefixes) | `react/history.py` | New |
| 3.4 | Add `pane` field to `TypedHistoryEntry` | `fsm/controller.py` | ~TypedHistoryEntry |

### 12.11 Exact Code Insertion Points

**`react/loop.py` — `_drain_control_events()` (line ~1260):**

```python
# CURRENT:
if event_type == "cancel":
    cancel_requested = True
    continue
if event_type == "parameter_update":
    drained_parameter_updates += 1

# ADD:
if event_type == "pause_for_hil":
    # Emit question via on_text_response, await Future for response,
    # inject both into messages, continue loop
    ...
if event_type == "pause_for_front":
    # Save state, return ReactResult(status="paused", ...)
    ...
```

**`actors/back.py` — `_resolve_needs_human_in_process()` (line ~1140):**

```python
# CURRENT:
if getattr(response, "timed_out", False):
    return ReactResult(
        status="cancelled",
        data={"error_code": "HIL_TIMEOUT", "partial_results": data},
    )

# CHANGE TO:
if getattr(response, "timed_out", False):
    # Create pending_decision in SS, release worker
    # The decision persists until user answers or supersedes
    _create_pending_decision(task_id, data, react_checkpoint)
    return ReactResult(
        status="awaiting_decision",
        data={"pending_decision_id": decision_id, "partial_results": data},
    )
```

---

### 12.12 CLARIFYING_WORKER Removal Audit

> **Audit date:** 2026-06-27. **Conclusion:** SAFE to remove. See §17.5 for full migration path.

**Current transitions into CLARIFYING_WORKER** (from `fsm/transition_table.py:87,101-102,121-122`):

| From State | Trigger |
|---|---|
| `LISTENING` | `TRIGGER_DEFERRED_HITL` |
| `COMPANIONING` | `TOPIC_TASK_SUSPENDED` |
| `COMPANIONING` | `TOPIC_HIL_REQUEST` (M6 unified HIL gate) |

**Current transitions out of CLARIFYING_WORKER** (from `fsm/transition_table.py:133-143`):

| Trigger | Target |
|---|---|
| `TOPIC_USER_INPUT` | `CLARIFYING_WORKER` (re-entrant) |
| `TOPIC_TASK_RESUME` | `COMPANIONING` |
| `TOPIC_TASK_FAILED` | `DELIVERING` |
| `TOPIC_TASK_COMPLETE` | `DELIVERING` |
| `TOPIC_FINAL_RESPONSE` | `None` (suppressed) |

**Migration:** In the new model, all entries into CLARIFYING_WORKER are replaced by staying in COMPANIONING. Front reads `pending_decisions` from SS via `DynamicPromptBuilder` and surfaces decisions naturally in conversation. The HITL_RELAY and HITL_RESOLVE prompt modes are folded into STANDARD mode. Back's `submit_result(awaiting_decision)` returns the task to "complete" status, which triggers DELIVERING → LISTENING → COMPANIONING on the next turn. No other FSM state depends on CLARIFYING_WORKER as a predecessor.

**What COMPANIONING absorbs:**

| Old (via CLARIFYING_WORKER) | New (via COMPANIONING) |
|---|---|
| Front runs HITL_RELAY mode (max_iterations=1) | Front runs STANDARD mode with pending_decision context from SS |
| Front produces relay question text | Front produces natural response that weaves decision surface into conversation |
| FSM parks in CLARIFYING_WORKER awaiting user response | FSM stays in COMPANIONING (Branch 9: has_active_tasks → stay) |
| User answers → FSM runs HITL_RESOLVE mode (max_iterations=3) | User answers → Front runs STANDARD mode, detects hil_response, resolves pending_decision, spawns new Back task |
| Back resumes via `_resolve_needs_human_in_process` checkpoint | Back spawns fresh with checkpoint state (unchanged from current — checkpoint already handles this) |

**Risk:** `TOPIC_FINAL_RESPONSE` is suppressed in CLARIFYING_WORKER (`None` target) but is NOT suppressed in COMPANIONING. This means Front will produce a response when Back's decision is pending. This is actually the DESIRED behavior — Front should respond naturally.

---

## 13. UI Design Spec — Grounded Against `ui/web/static/`

> **Read first:** `ui/web/static/app.js` (~9,200 lines), `index.html`, `styles.css`.
> All class names, DOM IDs, and function names below are **exact** from these files.
> Nothing is invented. Everything references real code.

### 13.1 Existing UI Infrastructure — What We Already Have

#### 13.1.1 Message Rendering Pipeline

```
addMessageRow(kind, sender, text, opts)     → .message-row div        (line ~2612)
  ├── .message-row--user                      flex-direction: row-reverse
  ├── .message-row--assistant                 normal flow
  ├── .message-row--system                    justify-content: center
  ├── .message-row--settled                   animation: answerMaterialize (blur→clear)
  └── .message-working                        active generation state

addUserMessage(text)                          → addMessageRow("user", member, text)    (line ~2653)
addAssistantMessage(text, o)                  → addMessageRow("assistant", "C", text)  (line ~2654)
addSystemMessage(text)                        → addMessageRow("system", null, text)    (line ~2655)

createStreamingMessage(id)                    → .message-row--assistant.message-working (line ~2657)
ensureStreamingMessage()                      → creates if !state.streamingMsgId        (line ~2669)
```

The **runtime pill** rendered inside streaming/working messages uses:

- `.runtime-pill` with state modifiers: `--planning`, `--tool_calling`, `--executing`, `--verifying`, `--waiting_for_approval`, `--blocked`
- `.runtime-lane` with source modifiers: `--front`, `--back`, `--tools`, `--plan`, `--policy`, `--approval`, `--blocked`
- `.runtime-confidence` with `--high` / `--steady` / `--forming`
- `.runtime-phase-rail` → `.runtime-phase` → `.runtime-phase-dot` + `.runtime-phase-line`

**Key insight:** `--waiting_for_approval` already exists as a runtime pill state. This is the exact visual anchor for persistent HITL.

#### 13.1.2 HIL Widget — Current Implementation

```
handleHilRequest(msg)                         → renders approve/deny widget  (line ~2196)
  │
  ├── Short-circuits "needs_human" AND "clarification" kinds
  │     (must arrive via chat, not HIL widget)
  │
  ├── _buildHilCardInner(id, title, body, approveLabel, denyLabel)    (line ~2150)
  │     └── <div> title + body + approve/deny buttons + status area
  │
  ├── In-chat row:   .message-row--system with .message-bubble (rose border)
  │     DOM id = "hil-{request_id}"
  │
  └── Floating overlay: position:fixed, top:84px, right:20px
        DOM id = "hil-overlay-{request_id}"

handleHilPresented(msg)                       → arms chat input as HIL answer channel  (line ~2181)
  │   Sets input.dataset:
  │     data-hil-active       = "true"
  │     data-hil-request-id   = msg.hil_request_id
  │     data-hil-kind         = msg.kind
  │     data-hil-task-id      = msg.task_id

sendHilResponse(hilMsg, approved)             → sends { type: "hil_response", ... }   (line ~2319)
  │   Drops stale "needs_human" responses

_setHilWidgetState(baseIds, statusText)       → disables buttons, shows status         (line ~2161)
```

#### 13.1.3 Home Decision Lane — Existing Pattern

```
_renderHomeDecisions(items)                   → #home-decision-list        (line ~1422)
  │
  └── .home-decision-row.home-decision-row--{tone}
        ├── <span>    app name (e.g., "Tasks")
        ├── <strong>  decision title
        └── <small>   detail text

Tones: "critical" (red), "active" (brand blue), "overdue" (amber)
CSS:  box-shadow: inset 4px 0 0 var(--tone-color)
      background: var(--bg-card)
      border-radius: var(--r-lg)
```

**Key insight:** `.home-decision-row` is the exact visual pattern to adapt for inline chat decision cards. It's already designed, tested, and uses existing token system.

#### 13.1.4 FSM State Display

```
#fsm-badge.fsm-badge                          → in chat header, collapsible <details>  (index.html ~L310)
  ├── .fsm-dot                                → pulsing dot (animation: pulse 2s)
  └── #fsm-state                              → text: "INITIALIZING", "LISTENING", etc.

setFsmBadge(stateName)                        → state.fsmState = stateName              (line ~3263)
updateFsmState(toState, fromState, trigger)   → setFsmBadge + timeline entry           (line ~3253)
```

#### 13.1.5 WebSocket Message Types — Current Inventory

```
case "init"            → handleInit(msg)
case "response"        → handleResponse(msg)          // final assistant response
case "stream_chunk"    → handleStreamChunk(msg)       // incremental text/thinking
case "proactive"       → handleProactive(msg)         // proactive notification
case "weave"           → handleWeave(msg)             // batch woven messages
case "system"          → handleSystem(msg)            // system notification
case "turn_info"       → handleTurnInfo(msg)
case "member_switched" → handleMemberSwitched(msg)
case "timeline"        → addTimelineEntry(msg.entry)
case "timeline_batch"  → addTimelineEntry batch
case "affect_update"   → updateAffect(msg.emotion, msg.valence)
case "fsm_state"       → updateFsmState(msg.to_state, msg.from_state, msg.trigger)
case "fsm_current"     → setFsmBadge(msg.state)
case "activity"        → updateDashboard(msg.data)
case "tool_event"      → handleToolEvent(msg)
case "tool_refresh"    → handleToolRefresh(msg)
case "status_report"   → /* silent */
case "hil_request"     → handleHilRequest(msg)        // binary approve/deny widget
case "hil_presented"   → handleHilPresented(msg)      // arm input as HIL channel
case "task_failed"     → handleTaskFailed(msg)
case "session_updated"   → handleSessionUpdated(msg)
case "session_activated" → handleSessionActivated(msg)
```

#### 13.1.6 Chat Session Persistence (Slice 8)

```
state.sessions = []                           → fetched from /api/sessions
state.activeSessionId = ""                    → current active session
state.sessionsLoading = false
state.switching = false                       → guard during activateSession

fetchSessions()                               → GET /api/sessions                          (line ~1836)
renderSessionList()                           → .chat-session-item in #chat-sessions-list
createNewChat()                               → POST /api/sessions → activateSession
activateSession(sessionId)                    → POST /api/sessions/{id}/activate            (line ~1904)
deleteSession(sessionId)                      → DELETE /api/sessions/{id}
loadMessagesIntoChat(messages)                → iterates turns → addUser/AssistantMessage    (line ~1963)
clearChatMessages()                           → #messages.innerHTML = ""
```

### 13.2 New UI Components Required

#### 13.2.1 Inline Decision Card (`decision-card`)

**Purpose:** Display a Back HITL question inline in the chat stream as a tappable card with options, not a binary approve/deny widget.

**Why new instead of extending `handleHilRequest`:** The current HIL widget handles `capability_gate` and `approval` kinds via approve/deny buttons. The spec's §2 says `needs_human` and `clarification` kinds must become persistent decision cards with multiple tappable options (Hotel A vs Hotel B, which doctor, which time slot). The current widget deliberately short-circuits these kinds (line ~2205: `if (kind === "needs_human" || kind === "clarification") { ... return; }`).

**DOM structure — adapts `.home-decision-row` pattern into chat:**

```html
<div class="message-row message-row--decision" id="decision-{decision_id}">
  <div class="message-avatar message-avatar--concierge" aria-hidden="true">
    <span>C</span>
  </div>
  <div class="decision-card" data-decision-state="pending">
    <!-- State: pending | answered | timed_out | superseded -->
    <div class="decision-card__header">
      <span class="decision-card__badge">Needs your input</span>
      <span class="decision-card__age" id="decision-age-{decision_id}">just now</span>
    </div>
    <p class="decision-card__question">{Back's HITL question text, e.g. "Which hotel?"}</p>
    <div class="decision-card__options">
      <button class="decision-option" data-decision-id="{decision_id}" data-option="0">
        <span class="decision-option__label">Option A</span>
        <small class="decision-option__detail">$200/night · 4.8★</small>
      </button>
      <button class="decision-option" data-decision-id="{decision_id}" data-option="1">
        <span class="decision-option__label">Option B</span>
        <small class="decision-option__detail">$180/night · 4.5★</small>
      </button>
    </div>
    <div class="decision-card__footer">
      <span class="decision-card__context">from planning · tap an option</span>
    </div>
  </div>
</div>
```

**State modifiers on `.decision-card`:**

| `data-decision-state` | Visual | When |
|---|---|---|
| `pending` | Full opacity, tappable options, subtle pulse on badge | Awaiting user response |
| `answered` | Reduced opacity, selected option highlighted, checkmark icon | User answered |
| `timed_out` | Greyed out, "No longer relevant" label | Context changed, decision stale |
| `superseded` | Collapsed to one-liner "Resolved by later decision" | Newer decision covers same ground |

**CSS classes needed** (use existing token system, no new color tokens):

```css
.decision-card {
  /* Adapt from .home-decision-row — not a button, informational card */
  background: var(--bg-card);
  border: 1px solid var(--border-light);
  border-radius: var(--r-lg);
  padding: var(--sp-5);
  max-width: 420px;
  box-shadow: var(--shadow-sm);
  transition: opacity var(--t-norm), box-shadow var(--t-norm);
}

.decision-card[data-decision-state="pending"] {
  box-shadow: inset 4px 0 0 var(--brand-blue), var(--shadow-sm);
}
.decision-card[data-decision-state="answered"] {
  opacity: 0.72;
  box-shadow: inset 4px 0 0 var(--color-green), var(--shadow-sm);
}
.decision-card[data-decision-state="timed_out"] {
  opacity: 0.48;
  box-shadow: inset 4px 0 0 var(--text-quaternary), var(--shadow-xs);
}
.decision-card[data-decision-state="superseded"] {
  max-height: 42px;
  overflow: hidden;
  opacity: 0.52;
  box-shadow: inset 4px 0 0 var(--text-quaternary), var(--shadow-xs);
}

.decision-option {
  /* Adapt from .chat-suggestion button pattern */
  display: flex;
  flex-direction: column;
  align-items: flex-start;
  width: 100%;
  padding: var(--sp-3) var(--sp-4);
  background: var(--bg-muted);
  border: 1px solid var(--border-light);
  border-radius: var(--r-md);
  text-align: left;
  transition: background var(--t-fast), border-color var(--t-fast);
  cursor: pointer;
}
.decision-option:hover {
  background: var(--bg-hover);
  border-color: var(--brand-blue);
}
.decision-option--selected {
  background: var(--brand-blue-soft);
  border-color: var(--brand-blue);
}
```

**Dark mode:** All tokens auto-remap via existing `html[data-theme="dark"]` block. No separate dark mode CSS needed.

**JS handler (new function ~after `handleHilRequest`):**

```js
// NEW: ~line 2318
function handleDecisionPending(msg) {
    // msg = { type: "decision_pending", decision_id, task_id, question,
    //         options: [{label, detail}], source: "back"|"planner", pane: "main"|"planning" }
    finishStreaming();  // same pattern as handleHilRequest
    const row = document.createElement("div");
    row.id = "decision-" + msg.decision_id;
    row.className = "message-row message-row--decision";
    row.innerHTML = _buildDecisionCard(msg);
    dom.messages.appendChild(row);
    scrollChatToBottom();
}

function _buildDecisionCard(msg) {
    // Builds .decision-card with options from msg.options
    // Adapts pattern from _buildHomeActivityFeed's renderItem logic
}

function handleDecisionResolved(msg) {
    // msg = { type: "decision_resolved", decision_id, selected_option, status }
    // Transition card to "answered" state
    const card = document.getElementById("decision-" + msg.decision_id);
    if (card) {
        const inner = card.querySelector(".decision-card");
        if (inner) inner.dataset.decisionState = "answered";
        // Highlight selected option
        const selected = card.querySelector(`[data-option="${msg.selected_option}"]`);
        if (selected) selected.classList.add("decision-option--selected");
    }
}

function handleDecisionSuperseded(msg) {
    // msg = { type: "decision_superseded", decision_id, by_decision_id }
    // Collapse old card
    const card = document.getElementById("decision-" + msg.decision_id);
    if (card) {
        const inner = card.querySelector(".decision-card");
        if (inner) inner.dataset.decisionState = "superseded";
    }
}
```

#### 13.2.2 Planning Pane

**Purpose:** A collapsible side panel within the chat view where Planner's conversation scope runs independently. Currently NO planning pane exists. The chat is a single `#messages` stream.

**Why not reuse the activity rail:** The activity rail (`.activity-rail`, `#activity-rail`) is a fixed right-side panel for background process tracking. It's designed for status cards, not conversation. Overloading it would break its purpose.

**Approach — collapsible sub-panel within `#view-chat`:**

```html
<!-- Inserted after #chat-area, before #input-form -->
<section id="planning-pane" class="planning-pane planning-pane--collapsed">
  <div class="planning-pane__toggle">
    <button id="planning-pane-toggle" aria-expanded="false">
      <span class="planning-pane__dot" aria-hidden="true"></span>
      <span>Planning</span>
      <span id="planning-pane-badge" class="planning-pane__badge hidden">0</span>
    </button>
  </div>
  <div id="planning-pane-body" class="planning-pane__body">
    <div id="planning-messages" class="planning-messages"></div>
  </div>
</section>
```

**CSS — adapt from existing `.activity-rail` + `.chat-area` patterns:**

```css
.planning-pane {
  border-top: 1px solid var(--border-light);
  background: var(--bg-subtle);
  transition: max-height var(--t-slow);
}
.planning-pane--collapsed {
  max-height: 44px;  /* toggle bar only */
}
.planning-pane--expanded {
  max-height: 320px;
}
.planning-pane__body {
  overflow-y: auto;
  max-height: 276px;
  padding: var(--sp-3) var(--sp-4);
}
.planning-pane__badge {
  /* Adapt from .chat-session-item badge pattern */
  background: var(--brand-blue);
  color: #fff;
  border-radius: var(--r-full);
  padding: 0 6px;
  font-size: 11px;
  font-weight: 600;
}
```

**Mobile (<900px):** Planning pane becomes a full-width bottom sheet instead of inline panel. Uses existing `.modal-dialog` overlay pattern.

**JS handler (new):**

```js
// NEW: ~after handleDecisionPending
function handlePlanningPaneOpen(msg) {
    // msg = { type: "planning_pane_open", plan_id, summary }
    const pane = document.getElementById("planning-pane");
    if (pane) {
        pane.classList.remove("planning-pane--collapsed");
        pane.classList.add("planning-pane--expanded");
    }
    // Clear previous planning messages
    const messages = document.getElementById("planning-messages");
    if (messages) messages.innerHTML = "";
    // Add initial plan message
    _addPlanningMessage("assistant", msg.summary);
}

function handlePlanningPaneUpdate(msg) {
    // msg = { type: "planning_pane_update", step, text, status }
    _addPlanningMessage("assistant", msg.text, { label: msg.status });
}

function handlePlanningPaneClose(msg) {
    const pane = document.getElementById("planning-pane");
    if (pane) {
        pane.classList.add("planning-pane--collapsed");
        pane.classList.remove("planning-pane--expanded");
    }
}

function _addPlanningMessage(kind, text, opts = {}) {
    // Lightweight inline message for planning pane (not full .message-row)
    const el = document.createElement("div");
    el.className = "planning-message planning-message--" + kind;
    el.innerHTML = `<span class="planning-message__text">${escapeHtml(text)}</span>`;
    const container = document.getElementById("planning-messages");
    if (container) container.appendChild(el);
}
```

#### 13.2.3 FSM State → Visual Mapping

**Current:** `setFsmBadge(stateName)` updates `#fsm-state` text only. The `.fsm-badge` has no per-state styling except the `.fsm-dot` pulse animation.

**Proposed:** Map K1 Concierge FSM states to visual signals on the chat header, chat area, and input. The user should never see "CLARIFYING_WORKER" — they see the chat area subtly change.

```js
// NEW: ~line 3263, extends setFsmBadge
const FSM_VISUAL_MAP = {
    "LISTENING":          { dotColor: "var(--brand-blue)",      areaClass: "",              inputHint: "Tell me what needs sorting." },
    "DISPATCHING":        { dotColor: "var(--brand-blue)",      areaClass: "chat-area--dispatched", inputHint: null },
    "COMPANIONING":       { dotColor: "var(--color-green)",     areaClass: "chat-area--companioning", inputHint: "I'm working on it..." },
    "PROGRESSING":        { dotColor: "var(--brand-blue)",      areaClass: "chat-area--working", inputHint: null },
    "DELIVERING":         { dotColor: "var(--color-green)",     areaClass: "",              inputHint: null },
    "CLARIFYING_USER":    { dotColor: "var(--color-yellow)",    areaClass: "chat-area--question", inputHint: "I need your input on this." },
    "CLARIFYING_WORKER":  { dotColor: "var(--color-yellow)",    areaClass: "chat-area--question", inputHint: "Checking with someone..." },
    "CANCELLING":         { dotColor: "var(--color-red)",       areaClass: "",              inputHint: null },
    "INTERRUPT_HANDLING": { dotColor: "var(--color-purple)",    areaClass: "chat-area--interrupted", inputHint: null },
    "PROACTIVE_WAKE":     { dotColor: "var(--brand-blue)",      areaClass: "",              inputHint: null },
    "WEAVING":            { dotColor: "var(--color-teal)",      areaClass: "chat-area--weaving", inputHint: null },
};

function setFsmBadge(stateName) {
    state.fsmState = stateName;
    if (dom.fsmState) dom.fsmState.textContent = stateName;

    // NEW: Apply visual mapping
    const mapping = FSM_VISUAL_MAP[stateName];
    if (mapping) {
        // FSM dot color
        const dot = document.querySelector(".fsm-dot");
        if (dot) dot.style.backgroundColor = mapping.dotColor;

        // Chat area class — clear previous, set new
        const area = document.getElementById("chat-area");
        if (area) {
            area.classList.remove(
                "chat-area--dispatched", "chat-area--companioning",
                "chat-area--working", "chat-area--question",
                "chat-area--interrupted", "chat-area--weaving"
            );
            if (mapping.areaClass) area.classList.add(mapping.areaClass);
        }

        // Input placeholder — only update if no HIL is active
        const input = dom.input;
        if (input && mapping.inputHint && input.dataset.hilActive !== "true") {
            input.placeholder = mapping.inputHint;
        }
    }

    // Refresh environment (state change affects cognition mode)
    applyShellState({ viewId: state.currentView, weather: state.householdWeather });
}
```

**Per-state `#chat-area` visual subtleties** (CSS — minimal, using existing border/shadow tokens):

```css
.chat-area--question {
  /* Subtle warm border-top when concierge needs user input */
  border-top: 2px solid var(--color-yellow);
  transition: border-color var(--t-norm);
}
.chat-area--companioning {
  /* Calm green pulse when concierge is thinking alongside user */
  border-top: 2px solid var(--color-green);
}
.chat-area--working {
  border-top: 2px solid var(--brand-blue);
}
```

**Key design rule:** Users never see FSM state names. They never see "CLARIFYING_WORKER." They see the chat area subtly change, the input hint shift, and optionally a decision card appear. The FSM badge in the collapsible `<details>` is for debugging/demos only.

#### 13.2.4 Actor Indicators

**Current:** `.message-avatar--concierge` is the only special avatar. All assistant messages get the same "C" avatar. User messages get the current member avatar. No Front/Back/Planner distinction.

**Proposed:** Add a subtle source label to `.message-meta` that identifies which actor authored the message. Not a different avatar — too visually noisy. Use the existing `.message-label-cue` pattern (currently shows "Concierge" on assistant messages).

```css
.message-label-cue--back {
  /* Existing .message-label-cue is brand blue */
  color: var(--color-purple);  /* Back = purple */
}
.message-label-cue--planner {
  color: var(--color-teal);   /* Planner = teal */
}
/* Front keeps the default brand blue */
```

**Implementation — extend `addMessageRow()` (line ~2612):**

```js
// New optional field in opts: source: "front" | "back" | "planner"
const sourceClass = opts.source === "back" ? "message-label-cue--back"
                 : opts.source === "planner" ? "message-label-cue--planner"
                 : "";
// Append to existing .message-label-cue element
```

### 13.3 New WebSocket Message Types

Add to `handleMessage()` switch (line ~1777):

| `msg.type` | Handler | Purpose |
|---|---|---|
| `decision_pending` | `handleDecisionPending(msg)` | Back emits a HITL question — render inline decision card with tappable options |
| `decision_resolved` | `handleDecisionResolved(msg)` | User answered OR system resolved — transition card to answered/superseded |
| `decision_superseded` | `handleDecisionSuperseded(msg)` | Newer decision covers same ground — collapse old card |
| `planning_pane_open` | `handlePlanningPaneOpen(msg)` | Planner starts — open planning pane with initial summary |
| `planning_pane_update` | `handlePlanningPaneUpdate(msg)` | Planner step — add message to planning pane |
| `planning_pane_close` | `handlePlanningPaneClose(msg)` | Planner done — collapse planning pane |
| `actor_indicator` | `handleActorIndicator(msg)` | Optional: set current active actor for label rendering (front/back/planner) |

**Message shapes:**

```js
// decision_pending
{
  type: "decision_pending",
  decision_id: "dec_abc123",
  task_id: "task_xyz",
  question: "Which hotel would you prefer?",
  options: [
    { label: "The Grand", detail: "$200/night · 4.8★ · Downtown" },
    { label: "Cozy Inn",   detail: "$180/night · 4.5★ · Near park" }
  ],
  source: "back",           // "back" | "planner"
  pane: "main",             // "main" | "planning"
  context: "from planning"  // short context label for footer
}

// decision_resolved
{
  type: "decision_resolved",
  decision_id: "dec_abc123",
  selected_option: 0,
  answer_text: "The Grand",
  status: "answered"        // "answered" | "timed_out"
}

// decision_superseded
{
  type: "decision_superseded",
  decision_id: "dec_old456",
  by_decision_id: "dec_new789"
}
```

### 13.4 Streaming + HITL Interaction

**Current behavior:** `handleHilRequest()` calls `finishStreaming()` (line ~2197). This KILLS the current stream — the streaming message is removed, streaming buffers cleared. If a HITL question arrives while Concierge is still generating text, the partial text is lost.

**Proposed:** Two-phase approach:

**Phase A (immediate — no spec change needed):** `handleDecisionPending()` also calls `finishStreaming(true)`. Consistency with existing `handleHilRequest` pattern. This means: if Back hits HITL mid-stream, the partial stream is cleared and the decision card appears. Acceptable tradeoff for V0 — streaming text wasn't useful anyway if Back needs user input to continue.

**Phase B (after §1 loop pause):** If `react_loop()` can pause, Front stream finishes naturally BEFORE Back emits the decision card. Sequence:

1. Front `react_loop()` finishes its current generation naturally
2. Back `react_loop()` hits HITL, pauses
3. Back emits `decision_pending` — no stream to interrupt
4. Decision card appears AFTER the Front response, not mid-stream

### 13.5 GAP-HIL-009 Coexistence

**Current:** `handleHilPresented()` sets `data-hil-active="true"` on `#message-input` (line ~2181). `sendMessage()` checks this (line ~3371) and routes the user's next text as a HIL reply, not a new conversation turn.

**Decision card coexistence:** When a decision card is rendered and user taps an option, the option click handler sends a `hil_response` (reusing existing `sendHilResponse` pattern). When the user types a free-text answer to the same question (using the armed input), `sendMessage()` routes it as a HIL reply.

**No conflict.** The decision card and the armed input serve the same purpose: route the user's answer to the pending HIL request. The decision card offers structured options; the input offers free-text. Both go through the same `hil_response` WS message.

**Clear decision context on answer:**

```js
// In the decision option click handler:
function _onDecisionOptionClick(decisionId, optionIndex) {
    const card = document.getElementById("decision-" + decisionId);
    // Mark as answered immediately (optimistic)
    const inner = card?.querySelector(".decision-card");
    if (inner) inner.dataset.decisionState = "answered";

    // Send HIL response via existing mechanism
    send({
        type: "hil_response",
        hil_request_id: /* from dataset */,
        approved: true,
        payload: { decision_id: decisionId, selected_option: optionIndex },
        task_id: /* from dataset */,
    });

    // Clear HIL markers from input (consistent with sendMessage line ~3397)
    const input = dom.input;
    if (input) {
        delete input.dataset.hilActive;
        delete input.dataset.hilRequestId;
        delete input.dataset.hilKind;
        delete input.dataset.hilTaskId;
    }
}
```

### 13.6 Home Decision Lane Integration

**Current:** `_renderHomeDecisions()` in `loadHomeDashboard()` shows event conflicts, task decisions, reminders, chores, shopping approvals. Source data comes from adapter APIs (`/api/tasks`, `/api/calendar`, etc.).

**Gap:** Back's pending decisions (`decision_pending`) arrive via WebSocket, not adapters. Home dashboard can't see them.

**Fix:** Maintain a local cache of pending decisions in `state`:

```js
// NEW state field:
state.pendingDecisions: [],    // decisions from WS that haven't been resolved
```

When `handleDecisionPending` fires, push to `state.pendingDecisions`. When `handleDecisionResolved` fires, remove. `_buildHomePulseModel()` reads `state.pendingDecisions` and includes them in the `decisions` array as items with `app: "Concierge"`, `target: "chat"`, `tone: "active"`.

**This makes "Back is waiting for your input" appear as a decision card on Home, tappable to jump to chat.**

### 13.7 Mobile Layout (<900px)

**Sidebar collapses** to icon-only mode at 900px (existing breakpoint, `styles.css`). All new components follow:

| Component | Desktop | Mobile (<900px) |
|---|---|---|
| Decision card | Inline in `#messages`, max-width 420px | Full-width in `#messages`, max-width 100% |
| Planning pane | Inline below `#chat-area` | Full-width bottom sheet overlay (adapt `.modal-dialog` pattern) |
| FSM badge | In collapsible `<details>` | Hidden (too noisy on small screen) |
| Actor labels | `.message-label-cue--back/--planner` | Same (subtle enough) |
| Home decision lane | In `.home-deep-grid` right panel | Collapses to single column (existing behavior) |

### 13.8 Accessibility

- Decision options are `<button>` elements with `aria-label`, keyboard navigable via Tab + Enter
- Decision card states use `data-decision-state` attribute, not color alone (screen readers can query)
- Planning pane toggle uses `aria-expanded`
- `aria-live="polite"` on `#messages` already exists — new decision cards announce naturally
- `.decision-option` gets `:focus-visible` ring from existing global rule (line ~140 of `styles.css`)

### 13.9 CSS File Changes — Summary

No new color tokens. No new font sizes. All values from existing `:root` / `html[data-theme="dark"]` token system.

New CSS block to append to `styles.css` (~12 rules, ~80 lines):

1. `.decision-card` + 4 state modifiers
2. `.decision-option` + `:hover` + `--selected`
3. `.message-row--decision` (extends `.message-row`)
4. `.planning-pane` + `--collapsed` + `--expanded`
5. `.planning-pane__body` + `.planning-pane__badge`
6. `.planning-message` inline message
7. `.chat-area--question` / `--companioning` / `--working` subtle borders
8. `.message-label-cue--back` / `--planner` color variants
9. `@media (max-width: 900px)` adjustments for planning pane bottom sheet

### 13.10 JS File Changes — Summary

**New functions** (~after line ~2318, after HIL widget block):

- `handleDecisionPending(msg)` — render inline decision card
- `_buildDecisionCard(msg)` — build decision card HTML
- `handleDecisionResolved(msg)` — transition card to answered
- `handleDecisionSuperseded(msg)` — collapse old card
- `_onDecisionOptionClick(decisionId, optionIndex)` — option tap handler
- `handlePlanningPaneOpen(msg)` — expand planning pane
- `handlePlanningPaneUpdate(msg)` — add planning message
- `handlePlanningPaneClose(msg)` — collapse planning pane
- `_addPlanningMessage(kind, text, opts)` — lightweight pane message

**Modified functions:**

- `setFsmBadge()` (line ~3263) — add `FSM_VISUAL_MAP` lookup
- `handleMessage()` (line ~1777) — add 7 new `case` entries
- `state` object (line ~19) — add `pendingDecisions: []`
- `_buildHomePulseModel()` (line ~1072) — read `state.pendingDecisions`
- `sendMessage()` (line ~3371) — no change needed; already handles `data-hil-active` for free-text answers

**Approximate line budget:** ~180 new lines, ~30 modified lines.

### 13.11 Decision Card Lifecycle (End-to-End Sequence)

```
┌─ Back hits HITL in _resolve_needs_human_in_process()
│   → creates pending_decision in SS (§2.2)
│   → returns ReactResult(status="awaiting_decision")
│
├─ FSM transitions → CLARIFYING_USER
│   → setFsmBadge("CLARIFYING_USER")
│       → .chat-area gets .chat-area--question border
│       → input placeholder: "I need your input on this."
│
├─ Back publishes WS message:
│   { type: "decision_pending", decision_id, question, options, source, pane }
│
├─ UI: handleDecisionPending(msg)
│   → finishStreaming(true)
│   → render .message-row--decision with .decision-card
│   → state.pendingDecisions.push(msg)
│   → home dashboard refresh shows it in decision lane
│
│   ┌─ User taps option → _onDecisionOptionClick()
│   │   → optimistic: card → "answered" state
│   │   → send hil_response WS message
│   │   → clear HIL markers from input
│   │
│   └─ OR User types answer → sendMessage()
│       → input.dataset.hilActive="true" → routes as hil_response
│       → clear HIL markers
│
├─ UI: handleDecisionResolved(msg)
│   → card transitions to "answered"
│   → state.pendingDecisions = state.pendingDecisions.filter(...)
│
├─ Back receives hil_response
│   → resumes react_loop() from checkpoint
│   → continues execution
│
└─ FSM transitions → PROGRESSING → DELIVERING
    → setFsmBadge clears .chat-area--question
    → input placeholder restored
```

---

## 14. Test Strategy

> **Rule:** NEVER run full kernel suite (`pytest tests/k1/kernel/`). NEVER run full fabric suite unsolicited.
> Run ONLY the tests listed below, plus targeted regression on directly-touched files.

### 14.1 Unit Tests — Conversation Continuity

| Test | File | What It Validates |
|---|---|---|
| `test_narrative_summary_in_submit_result` | `tests/k1/concierge/tools/test_submit_result.py` | Back's `submit_result(status="awaiting_decision")` includes `narrative_summary` and `remaining_work` fields, usable by Front's weave prompt |
| `test_back_pause_on_hitl` | `tests/k1/concierge/actors/test_back_hitl.py` | Back's `_resolve_needs_human_in_process` returns `awaiting_decision` instead of `cancelled` on timeout |
| `test_back_checkpoint_enrichment` | `tests/k1/concierge/react/test_checkpoint.py` | `ReActCheckpoint` serializes/deserializes new fields (`tool_dispatcher_state`, `data_freshness_ttl_seconds`, `paused_at_ns`, `capability_bindings`) |
| `test_pending_decision_persist` | `tests/k1/concierge/hitl/test_pending_decision.py` | `pending_decision` survives in SS across task restarts, FSM transitions, and browser reload |
| `test_decision_supersede` | `tests/k1/concierge/hitl/test_pending_decision.py` | Newer decision marks older as superseded, older decision card collapses in UI |
| `test_fsm_clarifying_user_no_timeout` | `tests/k1/concierge/fsm/test_fsm_hitl.py` | FSM stays in CLARIFYING_USER indefinitely, exits only on user response or supersede |

### 14.2 Integration Tests — UI Decisions

| Test | File | What It Validates |
|---|---|---|
| `test_decision_card_render` | `tests/ui/test_decision_cards.py` | `handleDecisionPending` renders `.decision-card` with correct options, state, CSS classes |
| `test_decision_option_tap` | `tests/ui/test_decision_cards.py` | Tapping option fires hil_response, transitions card to "answered" |
| `test_decision_superseded_collapse` | `tests/ui/test_decision_cards.py` | Superseded card collapses to one-line summary |
| `test_planning_pane_open_close` | `tests/ui/test_planning_pane.py` | Planning pane toggle expands/collapses correctly |

### 14.3 Property Tests — Conversation Continuity

| Test | File | What It Validates |
|---|---|---|
| `test_decision_never_lost` | `tests/k1/concierge/hitl/test_continuity_properties.py` | For any sequence of: pause, timeout, supersede, answer — the decision_id appears exactly once in resolved or pending state |
| `test_no_zombie_decisions` | `tests/k1/concierge/hitl/test_continuity_properties.py` | After 100 random operations, no decision cards remain in "pending" state with associated tasks completed |

---

## 15. Build Order & Rollout

### Phase 1: Backend Foundation (Week 1)

> **NOTE:** Loop pause/resume (§1) is DEFERRED. This phase now focuses on checkpoint enrichment + persistent HITL.

1. Enrich `ReActCheckpoint` with 4 new fields (§12.11): `tool_dispatcher_state`, `data_freshness_ttl_seconds`, `paused_at_ns`, `capability_bindings`
2. Wire `scratchpad` from checkpoint into `react_loop()` parameter (currently only `completed_tool_call_ids`, `completed_tool_arg_keys`, and `budget_remaining` are wired — gap identified in §17.2)
3. Add `pending_decision_*` fields to `TaskStateEntry`
4. Modify `_resolve_needs_human_in_process()` timeout path → `awaiting_decision`
5. Add `narrative_summary` and `remaining_work` fields to `submit_result()` schema (§17.6)
6. Add FSM Branch 11: CLARIFYING_WORKER persists until user answers

**Feature flag:** `k1_concierge_persistent_hitl` (env var, default `false`)

### Phase 2: UI Decision Cards (Week 2)

1. Add 7 new WS message types to handler
2. Implement `handleDecisionPending/Resolved/Superseded`
3. Add `.decision-card` CSS block
4. Wire `state.pendingDecisions` into home dashboard

### Phase 3: Planning Pane (Week 3)

1. Implement planning pane DOM + CSS
2. Implement `handlePlanningPaneOpen/Update/Close`
3. Mobile bottom-sheet variant

### Phase 4: Polish (Week 4)

1. FSM visual mapping (`setFsmBadge` extension)
2. Actor labels (`.message-label-cue--back/--planner`)
3. Accessibility audit
4. Dark mode verification

### Rollback Plan

- Feature flag off → all new behavior bypassed
- `pending_decision` in SS is additive — removing it leaves existing TaskState intact
- New WS message types are ignored by old UI (unknown `case` falls through silently)
- New CSS classes have no effect if HTML doesn't use them

---

## 16. Production Readiness

### 16.1 Performance Budgets

- Decision card render: <5ms DOM (single `.message-row` append, no layout thrash)
- `state.pendingDecisions` grows at most 1 decision per Back task; capped at 10
- Home dashboard refresh: <60ms additional (pendingDecisions lookup is O(n) on <10 items)
- Planning pane: max 320px height, virtual-scroll not needed for <20 messages

### 16.2 Multi-Device (M5)

- `pending_decision` lives in SS, not local state — survives device switch
- Decision cards re-render on `loadMessagesIntoChat()` if decisions are included in session messages
- **Open question:** Should `pending_decision` be included in session message history? If yes, `activateSession` would re-render decision cards from saved state.

### 16.3 Offline / Reconnect

- WebSocket reconnect (existing: 3s auto-retry, `connect()` line ~1752)
- On reconnect, `handleInit` re-sends session state — `pendingDecisions` would need to be re-populated
- **Gap:** No mechanism to replay missed `decision_pending`/`decision_resolved` messages during disconnection window. Mitigation: on WS reconnect, query `/api/decisions/pending` to refresh state.

### 16.4 Security

- Decision option values are backend-validated (not trusted from UI)
- `hil_response` message already validated by existing `sendHilResponse()` (line ~2319: drops stale "needs_human" responses)
- Decision card HTML uses `escapeHtml()` for all user-facing text

### 16.5 Logging / Debugging

- All new WS message types log to console (existing pattern: `console.info(...)`)
- Decision card state transitions are traceable via `state.pendingDecisions` snapshot
- FSM visual map failures are silent (fall back to text-only badge)

---

## 17. Response to Architecture Review — Grounded Analysis

> **Date:** 2026-06-27
> **Review summary:** An external architecture review recommended deferring §1 (loop pause/resume), reconsidering §3 (conversation planes), auditing CLARIFYING_WORKER removal, and deepening the unified voice proposal. This section engages with each critique point-by-point, grounding every claim against actual code.

### 17.1 Guiding Principle

The reviewer's core insight is correct: **structural plumbing alone doesn't make conversation feel human.** The things that matter are: initiative (system surfaces decisions without being asked), memory continuity (user never re-explains), natural decision integration (cards follow conversational lead-in, not pop up in isolation), and graceful handling of user attention shifts (Jack scenario). The implementation must be judged against these, not against loop elegance.

With that principle established, here is the point-by-point analysis.

---

### 17.2 §1 — React Loop Pause/Resume: DEFERRED Is The Right Call

**Reviewer claim:** Checkpoint-based resume already works. 6 instantiations vs 1 is invisible to the user. Two resume code paths (in-memory vs serialized) create divergence risk.

**Code evidence (from `loop.py`, `checkpoint.py`, `back.py`):**

The loop at `k1/concierge/react/loop.py` has **zero pause mechanism.** The `_drain_control_events()` function (line 1267) handles only `cancel` and `parameter_update`. Adding `pause_for_hil` would require breaking out of the monolithic `for iteration in range(hard_max_iterations):` loop mid-iteration — a significant refactor of ~1,200 lines of synchronous control flow.

The checkpoint at `k1/concierge/react/checkpoint.py` has 8 fields that **perfectly map** to `react_loop()`'s optional parameters:

| Checkpoint Field | `react_loop()` Parameter | Wired? |
|---|---|---|
| `completed_tool_call_ids` | `completed_tool_call_ids: set[str]` | ✅ In `_resolve_needs_human_in_process()` (back.py:1068) |
| `tool_history` → `completed_tool_keys()` | `completed_tool_arg_keys: set[str]` | ✅ In `_resolve_needs_human_in_process()` (back.py:1069) |
| `budget_remaining` | replaces default `max(2, max_iterations)` | ✅ In `_resolve_needs_human_in_process()` (back.py:1070) |
| `messages` | `messages: list[ModelMessage]` | ✅ Rebuilt from checkpoint (back.py:949–1012) |
| `scratchpad` | NOT wired into `react_loop()` params | ❌ Gap |

**The LLM's state IS the messages list.** Whether 6 fresh loops or 1 paused loop processes the same messages, the LLM receives identical context windows. The LLM has no "memory" of its own chain-of-thought across API calls — only the messages sent in the next request. So 6 instantiations vs 1 is **genuinely invisible** at the LLM layer.

**The operational difference** is:

- 6 loops = 6 budget allocations (mitigated by `budget_remaining`)
- 6 loops = 6 tool dispatcher binds (NOT serialized today — gap)
- 6 loops = 6 scratchpad initializations (NOT wired today — gap from table above)

**Two resume code paths would indeed diverge.** The reviewer correctly identifies this as a real maintenance risk. If we implement in-memory pause AND checkpoint serialization, Path A (live coroutine) and Path B (checkpoint→fresh loop) must stay behaviorally identical. Path B is the "hard" path (must serialize/deserialize perfectly). Path A is the "easy" path (just don't destroy the coroutine). In practice, bugs would accumulate in Path B (the majority of real-world usage, since pauses >60s are common), while Path A would appear to work flawlessly in development.

**Decision: DEFER §1.** The reviewer is correct. Implement Phase 2 (HITL as persistent state) first. The checkpoint-based resume in `_resolve_needs_human_in_process()` already carries conversation continuity. If after Phase 2 deployment we observe that the checkpoint→fresh-loop handoff produces perceptible degradation (tool re-binding errors, budget exhaustion from restart, scratchpad loss causing context drift), THEN revisit §1 with the specific failure mode in hand. Until then, §1 is solving a problem we haven't observed.

**What we KEEP from §1 design:** The control event architecture (`pause_for_hil`, `pause_for_front`) and the `ReactResult(status="paused")` design are preserved in the document as reference architecture. They may be needed for Planner's long-lived planning loops. But they are NOT a prerequisite for Phase 2.

**What we DO NOW instead:** Close the scratchpad gap. Add `scratchpad` parameter to `react_loop()` or find where scratchpad is initialized and ensure it reads from the checkpoint. This is ~5 lines, not the ~80 lines of the full §1 proposal.

---

### 17.3 §2 — HITL As Persistent State: BUILD THIS FIRST (Everyone Agrees)

**Reviewer claim:** This is the core win. Low risk. Directly addresses the human-feeling problem.

**Alignment:** 100%. The reviewer, the document, and the code all point in the same direction.

The reviewer adds an important implementation insight not in the original document:

> The real win from HITL-as-persistent-state makes loop pause/resume largely unnecessary. If Back cleanly exits with `awaiting_decision` and a fresh Back task spawns when the user answers — that's already the right behavior.

This is correct. The checkpoint carries the continuity. The user sees: question → answer → result. The implementation sees: loop terminates → checkpoint stored → fresh loop from checkpoint. The loop lifecycle is an implementation detail.

**Additional grounding — what the document should ADD:**

The reviewer's point about **handoff quality** in §17.6 (below) applies here too. When Back exits with `awaiting_decision`, the `submit_result` payload should include a natural-language narrative summary of what Back did and what remains. This summary becomes the "context" Front uses to weave the decision into conversation. Without it, Front only has structured data + the question text — and the weave will feel like a status update, not a natural continuation.

**Action:** Add `narrative_summary` and `remaining_work` fields to the `submit_result(status="awaiting_decision")` payload specification in §2.

---

### 17.4 §3 — Conversation Planes: RIGHT PROBLEM, RISKY SOLUTION — Partial Agreement

**Reviewer claims:**

1. Attention fragmentation — two active panes = two attention demands
2. "Task mode" break — pane architecture feels like a sophisticated app, not a person
3. Bus topic proliferation — routing ambiguity generates edge case bugs
4. Planner should ask questions in main chat first

**Where the reviewer is RIGHT:**

Point 4 is correct as a FIRST STEP. Planner asking one question at a time in the main conversation, with Front weaving responses naturally, is the human-feeling target. The document should prescribe this as the DEFAULT behavior for Planner flows, with the planning pane reserved for:

- Power users who want to SEE the plan in progress (shopping cart analogy)
- Long-running planning sessions where main chat continues independently
- Cases where the user explicitly requests to "work on this plan" while chatting

**Where the reviewer OVERSTATES:**

The attention fragmentation risk assumes users WILL be confused by two panes. But the document's design already mitigates this: the planning pane is **collapsible** (`.planning-pane--collapsed`, max-height 44px toggle bar only), **optional** (user can ignore it and keep chatting in main), and **non-blocking** (main chat continues unimpeded). The reviewer's "two active attention demands" scenario only manifests if the user CHOOSES to engage with both simultaneously — which is power-user behavior, not default behavior.

The bus topic proliferation concern can be addressed by using `correlation_id` on existing topics instead of creating new topic hierarchies. This is already noted as an alternative in §3 ("Or: use `correlation_id` on existing topics to scope messages to panes without new topic proliferation").

**Decision: KEEP the planning pane design, but add a DEGRADED MODE.**

The document's Phase 3 (Planning Pane, Week 3) was already correctly sequenced AFTER Phase 2. The review doesn't change the build order — it confirms it. But we should add:

- **Degraded mode:** Planner's default behavior is inline in main chat (one question at a time, Front weaves). The planning pane is an opt-in upgrade for sustained planning sessions with >3 back-and-forth questions.
- **Planner FSM should detect** when its conversation is "sustained" (>3 exchanges) and then suggest: "I can move this to a planning pane so we don't lose track — want me to?"

This preserves the planning pane design for where it adds value while defaulting to the simpler, more human-feeling approach.

**Decision on bus topics:** Use `correlation_id` on existing topics as the primary scoping mechanism. The pane-scoped topic hierarchy (`k1.session.{id}.planning.*.v1`) is preserved as a future optimization if correlation_id-based filtering proves insufficient at scale.

---

### 17.5 CLARIFYING_WORKER Removal — AUDIT CONFIRMS IT'S SAFE (With Caveats)

**Reviewer claim:** Front's COMPANIONING state must absorb HITL_RELAY and HITL_RESOLVE modes. This is non-trivial.

**Code evidence (from `front.py`, `fsm/transition_table.py`):**

The CLARIFYING_WORKER state (from `k1/concierge/fsm/states.py:42`):

```
CLARIFYING_WORKER = auto()
```

Current transitions (from `k1/concierge/fsm/transition_table.py:133-143`):

| Trigger | Target |
|---|---|
| `TOPIC_USER_INPUT` | `CLARIFYING_WORKER` (re-entrant) |
| `TOPIC_TASK_RESUME` | `COMPANIONING` |
| `TOPIC_TASK_FAILED` | `DELIVERING` |
| `TOPIC_TASK_COMPLETE` | `DELIVERING` |
| `TOPIC_FINAL_RESPONSE` | `None` (suppressed) |

How CLARIFYING_WORKER is entered (from transition_table.py:87,101-102,121-122):

| From State | Trigger |
|---|---|
| `LISTENING` | `TRIGGER_DEFERRED_HITL` |
| `COMPANIONING` | `TOPIC_TASK_SUSPENDED` |
| `COMPANIONING` | `TOPIC_HIL_REQUEST` (M6 unified HIL gate) |

**What HITL_RELAY does (front.py, ~line 520):**

- `_extract_scenario_data(PromptMode.HITL_RELAY, ...)` extracts `hil_type`, `hil_question`, `hil_options`, `hil_side_effects`, `task_action`, `task_context`
- Front's react_loop runs with `max_iterations=1`
- Front produces ONE text response: the natural-language question
- `on_text_response` is called AFTER react_loop returns

**What HITL_RESOLVE does (front.py, ~line 554):**

- `_extract_scenario_data(PromptMode.HITL_RESOLVE, ...)` reads suspended task from `task_state`
- Extracts: `original_question`, `user_answer`, `hil_type`, `hil_options`, `pending_hil_id`, `task_id`
- Front's react_loop runs with `max_iterations=3`
- After react_loop: `_build_resolution()` constructs the resolution dict
- `build_task_resume()` envelope is published → Back resumes

**Audit conclusion: CLARIFYING_WORKER removal is SAFE with the following migration path.**

In the new model, COMPANIONING absorbs HITL_RELAY and HITL_RESOLVE as follows:

| Old | New |
|---|---|
| FSM enters CLARIFYING_WORKER | FSM stays in COMPANIONING |
| Front runs HITL_RELAY mode (1 iter) | Front runs STANDARD mode but reads `pending_decisions` from SS via `DynamicPromptBuilder` |
| Front produces relay question | Front produces natural response that weaves decision surface into conversation |
| FSM waits in CLARIFYING_WORKER | FSM stays in COMPANIONING (Branch 9: has_active_tasks → stay) |
| User answers → FSM enters HITL_RESOLVE mode | User answers → Front runs STANDARD mode, detects `hil_response`, resolves pending decision, spawns new Back task |
| Back resumes from checkpoint | Back spawns fresh with checkpoint state (unchanged from current) |

**What makes this safe:**

1. `COMPANIONING` already handles "has active tasks, stay here" via Branch 9 (response_final_table.py)
2. `DynamicPromptBuilder` already reads `task_state` — just needs to also read `pending_decision_*` fields
3. The FSM doesn't need CLARIFYING_WORKER to manage HITL — Back's `submit_result(awaiting_decision)` returns the task to "complete" status, which triggers DELIVERING, which triggers LISTENING, which triggers COMPANIONING when the next user input arrives
4. No other FSM state lists CLARIFYING_WORKER as a predecessor for its own transitions (verified: transition_table.py has no entries where `from_state == ConciergeState.CLARIFYING_WORKER` is a dependency for entering another state — it only lists exits FROM CLARIFYING_WORKER)

**What requires care:**

1. `TOPIC_FINAL_RESPONSE` is suppressed in CLARIFYING_WORKER (`None` target). In COMPANIONING, it's not suppressed — Front will produce a response. This is actually the DESIRED behavior: Front should respond naturally when Back's decision is pending.
2. The `_build_resolution()` logic from HITL_RESOLVE must be preserved in Front's handler for the `hil_response` case. This is a refactor, not a removal.
3. GAP-HIL-006 (Branch 11 in response_final_table.py) becomes a non-issue — CLARIFYING_WORKER no longer exists, so the bug of "collapsing CLARIFYING_WORKER before user answers" disappears.

**Impact on document:** §6's removal table is correct. Add a §12.12 "CLARIFYING_WORKER Removal Audit" subsection with the above migration table.

---

### 17.6 Unified Voice (§3, Phase 3) — The Real Problem Is Handoff Quality

**Reviewer claim:** Adding a shared IDENTITY_BLOCK is correct but undersells the actual problem. The human-feeling gap is about handoff seams — when Back's work surfaces in Front's voice.

**Analysis:** The reviewer is CORRECT. The identity block (20 lines, §9, 3.1) is easy and low-risk. But the actual voice problem is richer:

**Current handoff:** Back's `submit_result(data={...})` → Front receives structured data → Front's prompt says "weave this into conversation" → Front produces text.

**The gap:** Front doesn't know WHY Back did what it did. Front sees results, not intent. The weave is a translation of structured data into natural language — adequate but not great. A human assistant wouldn't say "I found two hotels" — they'd say "There are two options that fit your $300 budget and are walking distance to the winery" — carrying forward the REASONING, not just the result.

**What to ADD to the document:**

Back's `submit_result` should include an optional `narrative_summary` field:

```python
submit_result(
    status="complete",  # or "awaiting_decision"
    result_type="task",
    data={...},                     # Structured data (existing)
    narrative_summary=(             # NEW: For Front to incorporate
        "I found two hotels under your $300 budget in downtown Napa. "
        "Hotel A ($280) has better reviews and is walking distance to "
        "the wine train. Hotel B ($310) is slightly over budget but has "
        "a pool. I recommend A unless you want the pool."
    ),
    remaining_work=(                # NEW: For continuation context
        "Once you choose, I'll book the room and send a confirmation."
    ),
)
```

Front's weave prompt then includes Back's narrative summary as source material to quote or paraphrase from — not just structured data to translate. This makes the handoff feel like two humans briefing each other, not like an API response being formatted for display.

**This is a 30-line change** (add two fields to `submit_result` schema + add `{back_narrative}` to Front's weave prompt template) with outsized impact on human-feeling.

**Also add:** Back's `IDENTITY_BLOCK` should include a directive to produce natural-language narrative summaries in `submit_result`, not just structured data. This aligns Back's output style with Front's conversational voice without requiring them to share the exact same prompt.

**Impact on document:** Add §9 Phase 3 items 3.1a and 3.1b for narrative_summary and remaining_work. Rename Phase 3 from "Unified Voice" to "Handoff Quality & Voice Consistency."

---

### 17.7 What The Document Genuinely Gets Right (Reviewer Confirmed)

The reviewer explicitly agrees with these parts — no changes needed:

| Component | Status |
|---|---|
| HITL as persistent state (§2) | ✅ Correct. Build first. |
| Stale world mitigation (§10.1) | ✅ Required. Without it, resumed tasks corrupt. |
| Belief globality (§10.4) | ✅ Required. Enforce at contract layer, not just document. |
| GC worker for pending decisions (§10.8) | ✅ Required. Without it, SS grows unbounded. |
| Grounded code audit (§12) | ✅ Valuable. Self-correction makes implementation plan trustworthy. |
| Jack scenario (§4) | ✅ Right test case. Validate end-to-end before building panes. |

**Enhancement to §10.4:** The reviewer suggests enforcing belief globality at the contract layer, not just documenting it. Add: `beliefs_active` writer should reject writes from scoped panes unless the fact is marked `global=True`. This prevents Planner from writing pane-local facts as global beliefs by accident.

---

### 17.8 Revised Priority Order — Post-Review

| Priority | What | Effort | Rationale |
|---|---|---|---|
| **P0** | Phase 2: HITL as persistent state (§2) | ~140 lines | Directly addresses the human-feeling gap. Low risk. Clean architecture. |
| **P0** | Stale world mitigation (§10.1) + enriched checkpoint (§10.5) | ~40 lines | Without these, resumed tasks will corrupt. |
| **P0** | Belief globality enforcement (§10.4) + GC worker (§10.8) | ~30 lines | Prevent context blindness and SS bloat. |
| **P1** | Handoff quality: narrative_summary + remaining_work (§17.6) | ~30 lines | Outsized impact on human-feeling. Easy to add. |
| **P1** | UI decision cards (§13.2.1) | ~180 lines | Visual affordance for pending decisions. |
| **P1** | CLARIFYING_WORKER removal + FSM migration (§17.5) | ~50 lines | Simplify FSM. Remove a state that's no longer needed. |
| **P2** | FSM visual mapping (§13.2.3) + actor labels (§13.2.4) | ~40 lines | Polish. Users never see FSM state names. |
| **P2** | Voice consistency: shared identity block (Phase 3) | ~20 lines | Small win, easy. |
| **P3** | Planning pane (§13.2.2) with degraded inline-first mode (§17.4) | ~100 lines | Right end state, wrong first step. Build after main chat flow is solid. |
| **DEFERRED** | Loop pause/resume (§1) | ~80 lines | Revisit after Phase 2 proves insufficient in production. |

**Total: ~560 lines (down from ~770 in original §9 plan, since Phase 1 is deferred).**

---

### 17.9 Summary — What Changes In The Document

| Section | Change |
|---|---|
| §1 header | Add `[DEFERRED — revisit after Phase 2 production validation]` banner |
| §2 `submit_result` | Add `narrative_summary` and `remaining_work` fields to example |
| §6 removal table | Add note: "CLARIFYING_WORKER removal audited safe — see §17.5" |
| §9 Phase 3 | Rename to "Handoff Quality & Voice Consistency." Add 3.1a (narrative_summary), 3.1b (remaining_work) |
| §10.4 | Add: "Enforce at contract layer — reject pane-scoped writes to global beliefs" |
| §12 | Add §12.12 "CLARIFYING_WORKER Removal Audit" with migration table |
| §14.1 | Add test: `test_narrative_summary_in_submit_result` |
| §15 Phase 1 | Remove loop pause/resume items. Add checkpoint enrichment items. |
| **NEW §17** | This section — Response to Architecture Review |

---

## 18. Implementation Checklist — Exact Work Items

> **How to use this section:** Each item has a checkbox `[ ]`, a file path, a one-line description, a line estimate, and test coverage. Work through P0 first, then P1, P2, P3. Each item references the section where it's designed in detail.

---

### P0 — MUST DO FIRST (Foundation: Without These, Nothing Else Works)

#### P0.1: Enrich ReActCheckpoint For Long-Pause Resume

> **Design:** §10.5, §12.3 &nbsp;|&nbsp; **Files:** `k1/concierge/react/checkpoint.py`

| # | What | File(s) | Lines | Test |
|---|---|---|---|---|
| [ ] | Add `tool_dispatcher_state: dict` field | `react/checkpoint.py` | ~3 | `test_back_checkpoint_enrichment` |
| [ ] | Add `data_freshness_ttl_seconds: int = 3600` field | `react/checkpoint.py` | ~2 | `test_back_checkpoint_enrichment` |
| [ ] | Add `paused_at_ns: int = 0` field | `react/checkpoint.py` | ~2 | `test_back_checkpoint_enrichment` |
| [ ] | Add `capability_bindings: list[dict]` field | `react/checkpoint.py` | ~2 | `test_back_checkpoint_enrichment` |
| [ ] | Update `from_dict()` to handle new fields (backward-compat: default if missing) | `react/checkpoint.py` | ~10 | `test_back_checkpoint_enrichment` |
| [ ] | Update `to_dict()` to serialize new fields | `react/checkpoint.py` | ~5 | `test_back_checkpoint_enrichment` |

#### P0.2: Wire scratchpad From Checkpoint Into react_loop()

> **Design:** §17.2 &nbsp;|&nbsp; **Files:** `k1/concierge/react/loop.py`, `k1/concierge/actors/back.py`

| # | What | File(s) | Lines | Test |
|---|---|---|---|---|
| [ ] | Add `scratchpad: dict | None = None` parameter to `react_loop()` | `react/loop.py` ~1048 | ~3 | existing regression |
| [ ] | Initialize loop's scratchpad from parameter if provided (else default empty dict) | `react/loop.py` | ~5 | existing regression |
| [ ] | Pass `checkpoint.scratchpad` when building resume call in `_resolve_needs_human_in_process()` | `actors/back.py` ~1070 | ~3 | `test_back_checkpoint_enrichment` |

#### P0.3: HITL As Persistent State — Backend

> **Design:** §2, §17.3 &nbsp;|&nbsp; **Files:** `k1/concierge/actors/back.py`, `k1/concierge/tools/`, `k1/sessionstate/`, `k1/hil/`

| # | What | File(s) | Lines | Test |
|---|---|---|---|---|
| [ ] | Add `pending_decision_id`, `pending_decision_question`, `pending_decision_options`, `pending_decision_status` fields to `TaskStateEntry` | `k1/sessionstate/sections/task_state.py` | ~15 | `test_pending_decision_persist` |
| [ ] | Add `narrative_summary: str | None` and `remaining_work: str | None` to `submit_result()` schema | `tools/schemas_back.py` | ~10 | `test_narrative_summary_in_submit_result` |
| [ ] | Wire `narrative_summary` + `remaining_work` into `submit_result()` implementation | `tools/implementations.py` | ~10 | `test_narrative_summary_in_submit_result` |
| [ ] | Modify `_resolve_needs_human_in_process()`: on timeout → create `pending_decision` in SS, return `awaiting_decision` instead of `cancelled` | `actors/back.py` ~1140 | ~25 | `test_back_pause_on_hitl` |
| [ ] | Remove hard timeout → task-cancel path in `SuspensionManager._watch_timeout()`. Replace with soft nudge (emit `pending_decision` event, don't cancel). | `k1/hil/suspension.py` | ~15 | `test_fsm_clarifying_user_no_timeout` |
| [ ] | Front's `DynamicPromptBuilder` reads `pending_decision_*` fields from `task_state` for surfacing | `prompt/builder.py` | ~20 | `test_fsm_clarifying_user_no_timeout` |
| [ ] | Add `{back_narrative}` and `{back_remaining}` to Front's weave prompt template | `prompt/builder.py` | ~5 | existing regression |
| [ ] | FSM: Decision continuation — spawn new Back task from `react_snapshot` when user answers (existing `HIL_RESOLVE` path, adapted) | `fsm/controller.py` | ~40 | `test_pending_decision_persist` |

#### P0.4: Stale World Mitigation

> **Design:** §10.1 &nbsp;|&nbsp; **Files:** `k1/concierge/actors/back.py`, `k1/concierge/react/`

| # | What | File(s) | Lines | Test |
|---|---|---|---|---|
| [ ] | Add `data_freshness_ttl_seconds` to `pending_decision` struct in `task_state` | same as P0.3 item 1 | ~2 | included in P0.3 tests |
| [ ] | Add `refresh_required: bool` flag to resume context in `_resolve_needs_human_in_process()` | `actors/back.py` ~1140 | ~5 | `test_back_pause_on_hitl` |
| [ ] | Back's first post-resume iteration: if `refresh_required=True` and `paused_duration > ttl`, enforce refresh tool before action tool (validation check, not execution) | `react/loop.py` ~1400 | ~15 | `test_back_checkpoint_enrichment` |

#### P0.5: Belief Globality Enforcement

> **Design:** §10.4, §17.7 &nbsp;|&nbsp; **Files:** `k1/sessionstate/sections/beliefs_active.py`

| # | What | File(s) | Lines | Test |
|---|---|---|---|---|
| [ ] | Add `global: bool = False` parameter to belief write path | `beliefs_active.py` write method | ~5 | `test_belief_globality_enforcement` |
| [ ] | Reject pane-scoped writes (planner, task_hitl source) unless `global=True` | `beliefs_active.py` | ~10 | `test_belief_globality_enforcement` |
| [ ] | Route `global=False` writes from scoped sources to pane-local belief store instead | `beliefs_active.py` | ~10 | `test_belief_globality_enforcement` |

#### P0.6: Garbage Collection Worker

> **Design:** §10.3, §10.8 &nbsp;|&nbsp; **Files:** `k1/concierge/hitl/`

| # | What | File(s) | Lines | Test |
|---|---|---|---|---|
| [ ] | Implement `PendingDecisionsGC` class: hourly sweep, archive >7 days, purge >30 days, supersede on contradiction | `k1/concierge/hitl/gc.py` (new) | ~40 | `test_pending_decisions_gc` |
| [ ] | Register GC worker in kernel lifecycle (start on boot, stop on shutdown) | `k1/kernel/service.py` | ~10 | `test_pending_decisions_gc` |

---

### P1 — HIGH PRIORITY (Core Behavior: User-Visible Improvements)

#### P1.1: CLARIFYING_WORKER Removal + FSM Migration

> **Design:** §6, §12.12, §17.5 &nbsp;|&nbsp; **Files:** `k1/concierge/fsm/`, `k1/concierge/actors/front.py`

| # | What | File(s) | Lines | Test |
|---|---|---|---|---|
| [ ] | Remove `CLARIFYING_WORKER` from ConciergeState enum | `fsm/states.py` | ~1 | `test_fsm_clarifying_worker_removal` |
| [ ] | Remove CLARIFYING_WORKER entries from transition_table (3 entry rows + 5 exit rows) | `fsm/transition_table.py` | ~8 | `test_fsm_clarifying_worker_removal` |
| [ ] | Re-route entry triggers to COMPANIONING: `TOPIC_TASK_SUSPENDED`, `TOPIC_HIL_REQUEST`, `TRIGGER_DEFERRED_HITL` | `fsm/transition_table.py` | ~3 | `test_fsm_clarifying_worker_removal` |
| [ ] | Remove CLARIFYING_WORKER case from `decide_response_final()` Branch 11 | `fsm/response_final_table.py` | ~1 | `test_fsm_clarifying_worker_removal` |
| [ ] | Fold HITL_RELAY mode logic into STANDARD mode: `DynamicPromptBuilder` reads `pending_decisions` and includes decision surface in standard prompt | `actors/front.py`, `prompt/builder.py` | ~20 | `test_fsm_clarifying_worker_removal` |
| [ ] | Fold HITL_RESOLVE mode logic into STANDARD mode: detect `hil_response` in user input, resolve pending_decision, spawn new Back task | `actors/front.py` | ~15 | `test_fsm_clarifying_worker_removal` |

#### P1.2: UI — Decision Cards

> **Design:** §13.2.1, §13.3 &nbsp;|&nbsp; **Files:** `ui/web/static/app.js`, `ui/web/static/styles.css`, `ui/web/static/index.html`

| # | What | File(s) | Lines | Test |
|---|---|---|---|---|
| [ ] | Add 3 new WS message types to `handleMessage()`: `decision_pending`, `decision_resolved`, `decision_superseded` | `app.js` ~1777 | ~6 | `test_decision_card_render` |
| [ ] | Implement `handleDecisionPending(msg)`: render `.decision-card` with options, append to `#messages` | `app.js` new | ~20 | `test_decision_card_render` |
| [ ] | Implement `_buildDecisionCard(msg)`: build card HTML from msg.options | `app.js` new | ~20 | `test_decision_card_render` |
| [ ] | Implement `handleDecisionResolved(msg)`: transition card to "answered" state, highlight selected option | `app.js` new | ~12 | `test_decision_option_tap` |
| [ ] | Implement `handleDecisionSuperseded(msg)`: collapse old card to one-line | `app.js` new | ~8 | `test_decision_superseded_collapse` |
| [ ] | Implement `_onDecisionOptionClick(decisionId, optionIndex)`: optimistic answer, send hil_response, clear HIL markers | `app.js` new | ~18 | `test_decision_option_tap` |
| [ ] | Add `.decision-card` CSS block: 4 state modifiers, hover, selected | `styles.css` | ~50 | visual validation |
| [ ] | Add `.message-row--decision` CSS extension | `styles.css` | ~5 | visual validation |
| [ ] | Add `state.pendingDecisions: []` to state object | `app.js` ~19 | ~1 | `test_decision_card_render` |
| [ ] | Wire `state.pendingDecisions` into `_buildHomePulseModel()` for home dashboard decision lane | `app.js` ~1072 | ~5 | visual validation |

#### P1.3: Handoff Quality — narrative_summary + remaining_work

> **Design:** §17.6, §17.3 &nbsp;|&nbsp; **Files:** `k1/concierge/tools/`, `k1/concierge/prompt/`

| # | What | File(s) | Lines | Test |
|---|---|---|---|---|
| [ ] | Add `narrative_summary: str | None` field to Back's system prompt: directive to produce natural-language summary in `submit_result` | `prompt/back_prompt.py` | ~10 | `test_narrative_summary_in_submit_result` |
| [ ] | Add `remaining_work: str | None` field: directive to state what remains after decision | `prompt/back_prompt.py` | ~5 | `test_narrative_summary_in_submit_result` |
| [ ] | Add `{back_narrative}` template variable to Front's weave prompt | `prompt/builder.py` | ~5 | existing regression |

---

### P2 — POLISH (Feel & Polish: Users Never See FSM State Names)

#### P2.1: FSM Visual Mapping

> **Design:** §13.2.3 &nbsp;|&nbsp; **Files:** `ui/web/static/app.js`, `ui/web/static/styles.css`

| # | What | File(s) | Lines | Test |
|---|---|---|---|---|
| [ ] | Add `FSM_VISUAL_MAP` constant mapping 11 states → dotColor, areaClass, inputHint | `app.js` ~3263 | ~15 | visual validation |
| [ ] | Extend `setFsmBadge()` to apply dot color, chat-area class, input placeholder | `app.js` ~3263 | ~20 | visual validation |
| [ ] | Add `.chat-area--question`, `.chat-area--companioning`, `.chat-area--working` CSS classes (border-top colors) | `styles.css` | ~10 | visual validation |

#### P2.2: Actor Source Labels

> **Design:** §13.2.4 &nbsp;|&nbsp; **Files:** `ui/web/static/app.js`, `ui/web/static/styles.css`

| # | What | File(s) | Lines | Test |
|---|---|---|---|---|
| [ ] | Add `.message-label-cue--back` (purple) and `.message-label-cue--planner` (teal) CSS | `styles.css` | ~6 | visual validation |
| [ ] | Extend `addMessageRow()` to accept `opts.source` and apply source class to label cue | `app.js` ~2612 | ~5 | visual validation |

#### P2.3: Voice Consistency — Shared Identity Block

> **Design:** §9 Phase 3, §10.7 &nbsp;|&nbsp; **Files:** `k1/concierge/prompt/`

| # | What | File(s) | Lines | Test |
|---|---|---|---|---|
| [ ] | Extract shared `IDENTITY_BLOCK` constant (tone, persona, family context) | `prompt/builder.py` (new constant) | ~10 | existing regression |
| [ ] | Add `IDENTITY_BLOCK` to Back's system prompt | `prompt/back_prompt.py` ~50 | ~5 | existing regression |
| [ ] | Add `IDENTITY_BLOCK` to Planner's system prompt | `k1/planner/` prompt | ~5 | existing regression |

#### P2.4: Accessibility Audit

> **Design:** §13.8 &nbsp;|&nbsp; **Files:** `ui/web/static/`

| # | What | File(s) | Lines | Test |
|---|---|---|---|---|
| [ ] | Verify `.decision-option` buttons have `aria-label` | `app.js` new code | ~3 | manual |
| [ ] | Verify planning pane toggle uses `aria-expanded` | `index.html`, `app.js` | ~2 | manual |
| [ ] | Verify dark mode renders correctly (all tokens auto-remap) | `styles.css` | ~0 | visual |
| [ ] | Verify keyboard navigation: Tab → Enter on decision options | `app.js` | ~0 | manual |

---

### P3 — FUTURE (Build After Main Chat Flow Is Solid)

#### P3.1: Planning Pane

> **Design:** §13.2.2, §17.4 &nbsp;|&nbsp; **Files:** `ui/web/static/app.js`, `ui/web/static/styles.css`, `ui/web/static/index.html`

| # | What | File(s) | Lines | Test |
|---|---|---|---|---|
| [ ] | Add `#planning-pane` DOM structure after `#chat-area` in chat view | `index.html` | ~10 | `test_planning_pane_open_close` |
| [ ] | Add `.planning-pane` CSS: collapsed/expanded states, toggle bar, body | `styles.css` | ~25 | `test_planning_pane_open_close` |
| [ ] | Implement `handlePlanningPaneOpen/Update/Close(msg)` handlers | `app.js` new | ~25 | `test_planning_pane_open_close` |
| [ ] | Add `@media (max-width: 900px)` bottom-sheet variant | `styles.css` | ~10 | visual validation |
| [ ] | Add 3 new WS message types: `planning_pane_open`, `planning_pane_update`, `planning_pane_close` | `app.js` ~1777 | ~3 | `test_planning_pane_open_close` |
| [ ] | Planner: add degraded inline-first mode (>3 exchanges → suggest pane upgrade) | `k1/planner/` | ~15 | `test_planning_pane_open_close` |

#### P3.2: Planner Integration

> **Design:** §9 Phase 4, §5 Layer 5 &nbsp;|&nbsp; **Files:** `k1/planner/`, `k1/orchestrator/`

| # | What | File(s) | Lines | Test |
|---|---|---|---|---|
| [ ] | Planner reads SS via `_read_ss_snapshot()` pattern (same as Back) | `k1/planner/` | ~30 | existing regression |
| [ ] | Planner HITL writes to `pending_decisions` via `task_state` enrichment | `k1/planner/` | ~20 | existing regression |
| [ ] | Orchestrator routes planning pane messages on session bus using `correlation_id` | `k1/orchestrator/` | ~15 | existing regression |

---

### DEFERRED — Loop Pause/Resume (Revisit After P0–P3 Validated In Production)

> **Design:** §1, §17.2 &nbsp;|&nbsp; **Files:** `k1/concierge/react/`, `k1/concierge/actors/`

| # | What | File(s) | Lines | Test |
|---|---|---|---|---|
| [ ] | Add `"pause_for_hil"` to `BackControlEvent.event_type` + handling in `_drain_control_events()` | `react/control.py`, `react/loop.py` | ~45 | TBD |
| [ ] | Add `"pause_for_front"` to `BackControlEvent.event_type` + handling | `react/control.py`, `react/loop.py` | ~35 | TBD |
| [ ] | Wire `_resolve_needs_human_in_process()` to use new pause mechanism instead of terminate/restart | `actors/back.py` | ~30 | TBD |

---

### Test Coverage Summary

| Tier | Test File | Tests |
|---|---|---|
| P0 | `tests/k1/concierge/react/test_checkpoint.py` | `test_back_checkpoint_enrichment` |
| P0 | `tests/k1/concierge/actors/test_back_hitl.py` | `test_back_pause_on_hitl` |
| P0 | `tests/k1/concierge/tools/test_submit_result.py` | `test_narrative_summary_in_submit_result` |
| P0 | `tests/k1/concierge/hitl/test_pending_decision.py` | `test_pending_decision_persist`, `test_decision_supersede` |
| P0 | `tests/k1/concierge/fsm/test_fsm_hitl.py` | `test_fsm_clarifying_user_no_timeout` |
| P0 | `tests/k1/concierge/hitl/test_gc.py` | `test_pending_decisions_gc` |
| P0 | `tests/k1/sessionstate/test_beliefs.py` | `test_belief_globality_enforcement` |
| P1 | `tests/k1/concierge/fsm/test_fsm_hitl.py` | `test_fsm_clarifying_worker_removal` |
| P1 | `tests/ui/test_decision_cards.py` | `test_decision_card_render`, `test_decision_option_tap`, `test_decision_superseded_collapse` |
| P2 | `tests/ui/test_planning_pane.py` | `test_planning_pane_open_close` |
| DEFERRED | `tests/k1/concierge/hitl/test_continuity_properties.py` | `test_decision_never_lost`, `test_no_zombie_decisions` |

---

### Line Budget Summary

| Tier | Python Files | JS/CSS/HTML Files | Total Lines |
|---|---|---|---|
| P0 (Foundation) | ~215 | ~0 | **~215** |
| P1 (Core Behavior) | ~70 | ~145 | **~215** |
| P2 (Polish) | ~25 | ~41 | **~66** |
| P3 (Future) | ~80 | ~73 | **~153** |
| DEFERRED | ~110 | ~0 | **~110** |
| **Grand Total** | **~500** | **~259** | **~759** |

> **Note:** DEFERRED items (~110 lines) are excluded from Phase 1–4 build plan. Active work: ~649 lines across all priority tiers.
