# K1 Concierge — STATE

State in Concierge is fundamentally different from traditional software state. Because
the core output of this system is **what an LLM thinks, says, and does**, state has
two layers that must be understood together:

1. **Cognitive state** (FSM) — what mode the system is in. Determines which LLM is
   active, what prompt mode it receives, what bus topics it will react to.

2. **Contextual knowledge state** (SessionState sections) — what the LLM *knows* at
   the moment it is invoked. This includes conversation history, emotional trajectory,
   task progress, family context, and clarification gaps.

Neither layer alone defines system behavior. The FSM state selects the cognitive frame;
the SS sections provide the knowledge within that frame.

---

## 1. Cognitive state machine (FSM)

### 1.1 The 11 states

| State | What it means for the LLM | Active actor |
|---|---|---|
| `LISTENING` | System is idle. No active tasks. LLM not running. | None |
| `DISPATCHING` | User input received and classified. Front LLM assembles task dispatch or direct response. | Front |
| `COMPANIONING` | Task(s) dispatched to Back. Front is idle; Back is working. User may send new input (interrupt path). | Back (running), Front (idle) |
| `PROGRESSING` | Back has called a tool and is awaiting its result. A tool is in-flight. | Back (waiting) |
| `DELIVERING` | Back completed a task. Front LLM is presenting results to the user. | Front |
| `CLARIFYING_USER` | Front LLM detected ambiguity. Asking user a clarifying question before dispatching. | Front |
| `CLARIFYING_WORKER` | Back LLM hit an uncertainty it cannot resolve alone (HITL suspension). Front relays to user. | Front (relay mode) |
| `CANCELLING` | Cancel signal sent to Back. Waiting for task.failed confirmation. | Controller |
| `INTERRUPT_HANDLING` | New user input arrived while Back was working. Arbiter is classifying it. | Front (interrupt mode) |
| `PROACTIVE_WAKE` | Task completed while system was LISTENING (async delivery). | Controller → Front |
| `WEAVING` | Pending results exist. Front is synthesizing a multi-result response. | Front (weave mode) |

### 1.2 What LLM prompt mode each state triggers

| FSM State | Front Prompt Mode | Notes |
|---|---|---|
| `DISPATCHING` | `STANDARD` | Normal user turn |
| `DISPATCHING` (interrupt) | `INTERRUPT` | New input while work in progress |
| `DISPATCHING` (low confidence) | `CLARIFY_ASK` | Front detected ambiguity via Phase1 |
| `DELIVERING` | `PRESENT` | Present completed task result |
| `WEAVING` | `WEAVE` | Synthesize multiple pending results |
| `CLARIFYING_WORKER` | `HITL_RELAY` | Surface HITL request to user |
| `CLARIFYING_WORKER` (resolution) | `HITL_RESOLVE` | User answer → resume Back |
| `PROACTIVE_WAKE` | `PRESENT` | Proactive delivery without user prompt |
| `CANCELLING` | `CANCEL` | Inform user of cancellation |

Back has no prompt modes — it always receives structured task JSON. Its behavior is
shaped by the **ComplexityTier** (LOW / MEDIUM / HIGH) which determines:
- How many tool iterations it gets (6 / 10 / 14)
- Which tools are available (3 / 6 tools)

### 1.3 FSM transition table

```
LISTENING:
  user.input               → DISPATCHING
  task.complete            → PROACTIVE_WAKE
  deferred_hitl.surface    → CLARIFYING_WORKER

DISPATCHING:
  task.dispatch            → COMPANIONING
  response.final           → LISTENING
  task.cancel              → CANCELLING
  clarification.detected   → CLARIFYING_USER
  pending_results.non_empty→ WEAVING

COMPANIONING:
  task.complete            → DELIVERING
  task.failed              → DELIVERING
  task.suspended           → CLARIFYING_WORKER
  user.input               → INTERRUPT_HANDLING
  tool.started             → PROGRESSING
  task.cancel              → CANCELLING
  task.dispatch (new)      → COMPANIONING (idempotent re-entry for parallel tasks)
  response.final           → LISTENING
  same_turn.task.complete  → LISTENING

PROGRESSING:
  tool.completed           → COMPANIONING
  task.complete            → DELIVERING
  task.failed              → DELIVERING
  task.suspended           → CLARIFYING_WORKER
  user.input               → INTERRUPT_HANDLING
  task.cancel              → CANCELLING

DELIVERING:
  response.final           → LISTENING
  pending_results.non_empty→ WEAVING

CLARIFYING_USER:
  user.input               → DISPATCHING

CLARIFYING_WORKER:
  user.input               → CLARIFYING_WORKER (same-turn HITL reply)
  task.resume              → COMPANIONING
  response.final           → CLARIFYING_WORKER while task active; LISTENING when no active task remains

CANCELLING:
  task.failed              → DELIVERING

INTERRUPT_HANDLING:
  interrupt.routed         → DISPATCHING

PROACTIVE_WAKE:
  proactive.routed         → DELIVERING

WEAVING:
  response.final           → LISTENING
  pending_results.non_empty→ WEAVING (re-weave for additional pending results)
```

Events that arrive outside the legal transitions are **dead-lettered** — published to
`dead.letter.v1` and recorded in the ledger; the FSM stays in its current state.

### 1.4 Full guard matrix (330 cells)

Every FSM state has an explicit guard action for every one of the 30 subscribed topics:
`TRANSITION` (execute transition), `PASSTHROUGH` (no state change, process event),
`OBSERVE` (no state change, record only), `QUEUE` (hold for later), `DEAD_LETTER`
(reject as illegal).

The guard matrix lives in `k1/concierge/fsm/transition_table.py:FULL_GUARD_TABLE`.

---

## 2. Contextual knowledge state (SessionState sections)

These are the sections of SessionState that Concierge reads. They define what the LLM
*knows* when it is invoked. They are **read-only from Concierge's perspective** —
mutations flow via bus events consumed by `MemoryWriter`.

### 2.1 Section read contracts

| Section | Read by | Read timing | Staleness risk |
|---|---|---|---|
| `persona` | Front every turn | At prompt assembly | None — family context changes rarely |
| `control` | Front + FSM every turn | At prompt assembly + event routing | Low — FSM writes its own overlay via ConciergeControlExtension |
| `history` | Front every turn, Back at task start | At prompt assembly | Front: live; Back: snapshot at start — NEVER re-read mid-ReAct |
| `task_state` | Back at task start | Snapshot-at-start | High during long tasks — see §2.2 |
| `task_artifacts` | Back at task start | Snapshot-at-start | Same as task_state |
| `beliefs` | Back at task start | Snapshot-at-start | Medium |
| `affective_now` | Front every turn | At prompt assembly | Medium — ExperienceLayer updates every 25 turns |
| `clarification` | Front in CLARIFY modes | At prompt assembly | High — changes after each HITL round |
| `scoreboard` | Back at task start | Snapshot-at-start | Low |

### 2.2 The SS snapshot contract (critical for Back actor)

Back reads SS exactly **once**, at task entry via `_read_ss_snapshot()`. This snapshot
is immutable for the duration of the ReAct loop. If a long-running task takes 14 tool
iterations and SS changes during that time (e.g., user updates a preference), Back
operates on stale data.

This is an **intentional design decision**: re-reading SS mid-ReAct would violate the
deterministic replay guarantee of the event-sourced ledger. The only re-read point
is `back_resume_handler()` — after a HITL suspension where SS may legitimately change.

---

## 3. Ephemeral per-turn state (`FSMTurnState`)

This is the volatile state that exists only for the duration of one turn. It is NOT
persisted to SS and is NOT part of the ledger.

| Field | Type | Description |
|---|---|---|
| `pending_results` | `deque[dict]` | Task results waiting to be delivered to user |
| `deferred_results` | `list[dict]` | Results deferred (user typing, DEFER policy decision) |
| `front_busy` | `bool` | True while Front LLM is running (FrontLock) |
| `active_weave_timer` | `asyncio.TimerHandle | None` | M8 WeavePolicy batch timer |
| `typing_active` | `bool` | True while user is typing (typing signal pauses weave timer) |

`FSMTurnState` is rebuilt from ledger via `project_pending_results()` on crash recovery.

---

## 4. Accumulated conversational state

This state persists across turns within a session. It lives in SessionState (persisted
to SQLite via MemoryWriter) and in the ledger (event log).

### 4.1 `history` section — typed conversation log

Each entry: `{ turn, type, role, text, timestamp_ms, source, task_id? }`

Entry types and their LLM significance:

| Entry type | Role | When created | LLM impact |
|---|---|---|---|
| `user` | user | Every user input turn | Forms user-side chat context |
| `task_dispatch` | system | task.dispatch emitted | Context about what was requested |
| `task_complete` | assistant | task.complete received | Raw result (Front rewrites in its voice) |
| `task_failed` | system | task.failed received | Error context for Front response |
| `task_suspended` | system | HITL suspension | Signals open question for Front |
| `hil_request` | system | hil.requested emitted | The clarification question surfaced to user |
| `hil_response` | user | User HITL answer | The resolution injected into Back resume |
| `assistant_response` | assistant | response.final | What Front actually said |
| `cancel_confirmed` | system | Cancel completed | Cancellation acknowledgement |
| `dead_letter` | system | Any illegal event | Debug signal for LLM to know what was rejected |
| `intent` | system | intent.arbitrated | Arbiter's classification decision |

History window sizes by mode (from config):
- `STANDARD`: 5 turns
- `INTERRUPT`: 3 turns
- `DELIVERING/WEAVING`: 5 turns
- `HITL_RELAY/HITL_RESOLVE`: 3 turns

### 4.2 `affective_now` section — LLM emotional model

Not persisted raw — computed by `EmotionalProcessor` from recent transcript.

| Field | Range | LLM use |
|---|---|---|
| `valence` | -1.0 to +1.0 | Positive/negative emotional tone |
| `arousal` | 0.0 to 1.0 | Calm to excited |
| `dominance` | 0.0 to 1.0 | Passive to assertive |
| `trend` | stable / rising / falling | Emotional trajectory |
| `band` | crisis / low / neutral / positive / elevated | Drives `AffectiveMirror` adjustments |
| `confidence` | 0.0 to 1.0 | Reliability of estimate |

`AffectiveMirror` uses this to adjust Front's tone (warmth, formality, pace,
mirror_intensity) in every prompt. Crisis band → slow pace, warm, no mirroring.
Excited band → fast pace, warm, high mirroring.

### 4.3 `control` section — FSM overlay

Written by `ConciergeControlExtension` (M4 E4.1.2). Extends the shared `ControlSection`
with FSM-specific fields:

| Field | Type | Significance |
|---|---|---|
| `fsm_state` | `str` | Current `ConciergeState.name` — Front reads this to know its cognitive mode |
| `active_task_ids` | `set[str]` | Tasks currently running — informs Arbiter |
| `complexity_tier` | `ComplexityTier` | Current task tier — informs Back tool selection |
| `flow_state` | `str` | FSM state string for Front's prompt assembly |
| `domain_context` | `str` | Phase1 domain from last classification |
| `intent_classification` | `IntentClassification` | SINGLE / BUNDLED / CHAINED |
| `privacy_band` | `PrivacyBand` | Consent level affecting LLM data use |

### 4.4 `task_state` section — task lifecycle mirror

Maintained by `TaskBridge`. Each active task entry contains:
- `task_id`, `status` (dispatched / in_progress / completed / failed / suspended / cancelled)
- `intents: list[TaskIntent]`
- `progress_pct: float`
- `artifacts: list[dict]`
- `depends_on: str | None`

Back reads this as a snapshot at task start. `TaskBridge` prunes completed tasks
after `PRUNE_COMPLETED_AFTER_TURNS` turns; evicts artifacts after `EVICT_ARTIFACTS_AFTER_TURNS`.

---

## 5. Cancellation state model

Cancellation is not a simple boolean. `CancellationHandler` maintains per-task
`CancellationToken` objects. Each token has a reason:
- `USER_REQUESTED` — user explicitly cancelled
- `SAFETY_ABORT` — RED safety band triggered
- `TIMEOUT` — task deadline exceeded

Back's ReAct loop polls `cancel_token.is_cancelled()` at each iteration boundary.
Cancellation is **cooperative**, not pre-emptive — Back finishes the current tool call
before honouring the cancel signal.

The arbiter's CANCEL decision sets the token AND transitions the FSM to CANCELLING.
The CANCELLING state waits for `task.failed.v1` before transitioning to DELIVERING.

---

## 6. Response delivery state (`WeavePolicy` and `WeaveQueue`)

Task results do not go directly to the user. They enter the `WeaveQueue` and the
`WeavePolicy` decides when to deliver them. This creates a **delivery intent state**:

| WeaveDecision | Meaning | LLM impact |
|---|---|---|
| `IMMEDIATE` | Flush results now, no delay | Front invoked immediately in DELIVERING mode |
| `BATCH` | Wait `window_ms` then flush | Results accumulate; Front presents a cohesive summary |
| `DEFER` | Hold — user is typing | User may be about to send a follow-up; wait for natural break |
| `DIGEST` | Summarise group into a digest | Multiple results → single narrative summary |
| `SUPPRESS` | Drop result — not relevant | Result arrived too late or in wrong state |

The 9-rule decision table:
1. HITL surface pending → IMMEDIATE
2. RED safety band → IMMEDIATE
3. URGENT task result → IMMEDIATE
4. User typing → DEFER
5. Front busy → BATCH (wider window)
6. Turn age > threshold → IMMEDIATE
7. Pool draining (all workers near done) → BATCH (short window)
8. Pool pressure high (many workers busy) → BATCH (wider window)
9. Default → BATCH (500ms)

`TypingPolicyReEvaluator` re-evaluates on typing_start (cancel active timer) and
typing_stop after 500ms debounce (restart timer or trigger immediate).

---

## 7. Crash recovery state reconstruction

After a crash, `CrashRecoveryOrchestrator` replays all ledger entries to rebuild state.
The reconstructed FSM state is derived deterministically from the event sequence:

Priority order: `CLARIFYING_WORKER > WEAVING > COMPANIONING > DISPATCHING > LISTENING`

This means: if the last event before crash was a `task.suspended`, the system resumes
in `CLARIFYING_WORKER` — the HITL question is re-surfaced to the user. If `task.complete`
was emitted but `response.final` was not, the system resumes in `WEAVING` with the
pending result re-queued.

---

## 8. Concurrency model

| Layer | Concurrency model |
|---|---|
| FSM Controller | Single asyncio event loop; all handler methods are coroutines run sequentially |
| Front actor | Single active invocation enforced by `FrontLock` (`DEFAULT_MAX_QUEUE_DEPTH` queue) |
| Back actors | Parallel via `BackPool` — multiple tasks may run concurrently |
| WeavePolicy | Stateless per-invocation; timer is owned by FSM controller |
| SessionState reads | Snapshot-at-start for Back; live reads for Front (each turn) |
| SS mutations | Serialized via `MemoryWriter` consumer; all mutations are bus events |
| InMemoryLedgerStore | Thread-safe via `threading.Lock` |

`FrontLock` ensures only one Front LLM call runs at a time. If a second Front
invocation arrives while Front is busy (e.g., during INTERRUPT_HANDLING), it is queued
up to `DEFAULT_MAX_QUEUE_DEPTH`. Overflow raises `FrontLockOverflowError` → dead-letter.
