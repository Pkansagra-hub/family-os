# Scan #10: ledger/ + experience/ + identity/ + compression/

**Scanned**: 2026-04-04
**Files**: 17 Python files across 4 folders (~2,197 lines)

---

## 1. LEDGER/ (5 files, ~945 lines)

### 1.1 `ledger/__init__.py` (~42 lines)

Package docstring: "V3 append-only conversation ledger. M1 E1.2: Event-sourced conversation ledger infrastructure."

**Exports (\_\_all\_\_)**:
- `ILedgerStore`, `InMemoryLedgerStore`, `LedgerEntry` (from `.store`)
- `LedgerWriter` (from `.writer`)
- `project_cancel_state`, `project_history`, `project_hitl_state`, `project_pending_results`, `project_suspension_state`, `project_task_states` (from `.projections`)

**Imports from other k1.\* packages**: None (re-exports only from within ledger)

---

### 1.2 `ledger/store.py` (~190 lines)

#### `LedgerEntry` (frozen dataclass, slots=True)
Immutable record in the conversation ledger.

| Field | Type | Description |
|-------|------|-------------|
| `seq` | `int` | Monotonic sequence number within session (1-based) |
| `event_id` | `str` | Domain UUID4 from CanonicalEventMeta (idempotency key) |
| `event_type` | `str` | Canonical event type string (e.g. "task.completed") |
| `session_id` | `str` | Session scope identifier |
| `payload` | `dict[str, Any]` | Full serialized event payload (from to_payload()) |
| `written_at_utc` | `str` | Wall-clock UTC timestamp when entry was written (ISO 8601) |

#### `ILedgerStore` (Protocol, runtime_checkable)
Storage protocol for the conversation ledger.

| Method | Signature | Returns |
|--------|-----------|---------|
| `append` | `(self, entry: LedgerEntry) -> int` | Assigned sequence number |
| `read` | `(self, session_id: str, from_seq: int = 0, to_seq: int \| None = None) -> list[LedgerEntry]` | Entries in sequence order |
| `read_by_type` | `(self, session_id: str, event_type: str) -> list[LedgerEntry]` | Matching entries in sequence order |
| `exists` | `(self, event_id: str) -> bool` | Whether event_id already written |

#### `InMemoryLedgerStore`
In-memory ledger store for POC and testing. Thread-safe via `threading.Lock`.

| Slot | Type |
|------|------|
| `_entries` | `list[LedgerEntry]` |
| `_event_ids` | `set[str]` |
| `_next_seq` | `int` |
| `_lock` | `threading.Lock` |

| Method | Signature | Returns | Notes |
|--------|-----------|---------|-------|
| `__init__` | `(self) -> None` | — | Initializes empty store, seq starts at 1 |
| `append` | `(self, entry: LedgerEntry) -> int` | Assigned seq | Creates new frozen LedgerEntry with correct seq |
| `read` | `(self, session_id: str, from_seq: int = 0, to_seq: int \| None = None) -> list[LedgerEntry]` | Filtered entries | |
| `read_by_type` | `(self, session_id: str, event_type: str) -> list[LedgerEntry]` | Filtered by type | |
| `exists` | `(self, event_id: str) -> bool` | O(1) set lookup | |
| `count` | `(self, session_id: str \| None = None) -> int` | Entry count | Convenience for testing |
| `read_all` | `(self, session_id: str \| None = None) -> list[LedgerEntry]` | All entries | Convenience for replay/testing |

**Cross-component imports**: None (stdlib only: `logging`, `threading`, `dataclasses`, `typing`)

---

### 1.3 `ledger/writer.py` (~128 lines)

#### `LedgerWriter`
Append-only writer with idempotency for a single session. Each FSM controller instance creates its own LedgerWriter.

| Slot | Type |
|------|------|
| `_store` | `ILedgerStore` |
| `_session_id` | `str` |

| Method | Signature | Returns | Notes |
|--------|-----------|---------|-------|
| `__init__` | `(self, store: ILedgerStore, session_id: str) -> None` | — | |
| `session_id` (property) | `-> str` | Session ID | |
| `store` (property) | `-> ILedgerStore` | Underlying store | Exposed for projections/replay |
| `append` | `async (self, event: CanonicalEventMeta) -> int` | Sequence number | Idempotent: skips if event_id exists |
| `append_sync` | `(self, event: CanonicalEventMeta) -> int` | Sequence number | Synchronous version, same idempotency |
| `_find_existing_seq` | `(self, event_id: str) -> int` | Existing seq or -1 | O(n) scan for POC |

**Cross-component imports**:
- `from k1.concierge.ledger.store import ILedgerStore, LedgerEntry`
- `TYPE_CHECKING: from k1.concierge.events.base import CanonicalEventMeta`

---

### 1.4 `ledger/projections.py` (~510 lines)

Pure projection functions: events in → state out. No side effects. Used for crash recovery, debugging, and testing.

#### Module-level constants:

**`_HISTORY_EVENT_MAP: dict[str, tuple[str, str]]`** — Maps canonical event_type → (entry_type, role):
| Event Type | Entry Type | Role |
|------------|-----------|------|
| `conversation.user_input.received` | `user` | `user` |
| `task.created` | `task_dispatch` | `system` |
| `task.completed` | `task_complete` | `assistant` |
| `task.failed` | `error` | `system` |
| `task.cancelled` | `cancel_confirmed` | `system` |
| `task.suspended` | `task_suspended` | `system` |
| `task.resumed` | `task_resumed` | `system` |
| `hil.requested` | `hil_request` | `system` |
| `hil.resolved` | `hil_response` | `user` |
| `conversation.weave.emitted` | `assistant_response` | `assistant` |
| `conversation.intent.arbitrated` | `intent` | `system` |
| `conversation.dead_lettered` | `dead_letter` | `system` |

**`_TURN_INCREMENT_EVENTS: frozenset[str]`** — `{"conversation.user_input.received"}`

#### Free functions:

| Function | Signature | Returns | Notes |
|----------|-----------|---------|-------|
| `_extract_text` | `(event_type: str, payload: dict[str, Any]) -> str` | Display text | Extracts human-readable text per event type |
| `_extract_source` | `(event_type: str, payload: dict[str, Any]) -> str` | Source actor | Infers actor from payload or event type prefix |
| `project_history` | `(entries: list[LedgerEntry]) -> list[dict[str, Any]]` | History entry dicts | Replays events into TypedHistoryEntry-compatible dicts. Keys: turn, type, role, text, timestamp_ms, source, [task_id] |
| `project_cancel_state` | `(entries: list[LedgerEntry]) -> tuple[set[str], set[str]]` | (active_task_ids, cancelled_task_ids) | M9 E9.1.2: Cancel protocol recovery |
| `project_suspension_state` | `(entries: list[LedgerEntry]) -> tuple[dict[str, dict[str, Any]], dict[str, int]]` | (active_suspensions, suspension_counts) | M9 E9.2.3: Suspension recovery |
| `project_hitl_state` | `(entries: list[LedgerEntry]) -> tuple[dict[str, dict[str, Any]], dict[str, int], dict[str, list[dict[str, Any]]]]` | (pending_requests, hil_counts, hil_histories) | M9 E9.3.2: HITL coordinator recovery |
| `project_task_states` | `(entries: list[LedgerEntry]) -> dict[str, TaskStateEntry]` | task_id → TaskStateEntry | Full task lifecycle: created→progressed→completed/failed/cancelled/suspended/resumed + HIL events |
| `project_pending_results` | `(entries: list[LedgerEntry]) -> deque[dict[str, Any]]` | Pending results queue | Weave candidate events minus already-delivered |
| `project_dead_letters` | `(entries: list[LedgerEntry]) -> list[dict[str, Any]]` | Dead-letter payload dicts | M2 E2.5.2: Extracts `conversation.dead_lettered` events |
| `_iso_to_ms` | `(iso_str: str) -> int` | Epoch milliseconds | Utility: ISO 8601 → ms conversion |

**Cross-component imports**:
- `from k1.concierge.protocols.hitl_persistence import TaskStateEntry, TaskStatus`
- `TYPE_CHECKING: from k1.concierge.ledger.store import LedgerEntry`

---

### 1.5 `ledger/recovery.py` (~225 lines)

#### `CrashRecoveryReport` (dataclass)
Summary of a crash recovery attempt.

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `recovered` | `bool` | `False` | Whether recovery succeeded |
| `event_count` | `int` | `0` | Total ledger events replayed |
| `tasks_restored` | `int` | `0` | Task states restored to TaskBridge |
| `cancelled_restored` | `int` | `0` | Cancelled tasks restored |
| `suspensions_restored` | `int` | `0` | Active suspensions restored |
| `hitl_pending_restored` | `int` | `0` | Pending HITL requests restored |
| `pending_results_restored` | `int` | `0` | Pending results restored |
| `history_entries` | `int` | `0` | History entries rebuilt |
| `active_task_count` | `int` | `0` | Non-terminal tasks |
| `derived_state` | `str` | `"LISTENING"` | FSM state derived from events |
| `error` | `str` | `""` | Error message if failed |
| `_details` | `dict[str, Any]` | `{}` | Internal detail storage |

| Method | Signature | Returns |
|--------|-----------|---------|
| `summary` | `(self) -> str` | One-line summary string |

#### `CrashRecoveryOrchestrator`
Rebuilds FSM protocol state from ledger events. M9 E9.5.1.

Recovery order (dependency-safe):
1. Project task states → rebuild TaskBridge
2. Project cancel state → rebuild CancellationHandler
3. Project suspension state → rebuild SuspensionManager
4. Project HITL state → rebuild HILCoordinator
5. Project pending results → rebuild FSMTurnState
6. Project history → store in report
7. Derive _active_task_ids from projected task states
8. Derive FSM state from event patterns

| Method | Signature | Returns | Notes |
|--------|-----------|---------|-------|
| `recover` | `(self, fsm: Any, ledger_store: ILedgerStore, session_id: str) -> CrashRecoveryReport` | Recovery report | Main entry point. E9.5.5: safe fallback on failure |
| `_do_recover` | `(self, fsm: Any, entries: list[LedgerEntry], report: CrashRecoveryReport) -> None` | — | Internal: runs all 8 recovery steps |
| `_derive_fsm_state` | `(self, entries: list[LedgerEntry], task_states: dict[str, Any], pending: Any) -> str` | State string | E9.5.3: Priority: CLARIFYING_WORKER > WEAVING > COMPANIONING > DISPATCHING > LISTENING |

**Cross-component imports**:
- `from k1.concierge.ledger.projections import project_cancel_state, project_history, project_pending_results, project_task_states`
- `from k1.concierge.protocols.hitl_persistence import TaskStatus`
- `TYPE_CHECKING: from k1.concierge.ledger.store import ILedgerStore, LedgerEntry`

**FSM duck-type dependencies** (via `fsm: Any`):
- `fsm._task_bridge.rebuild_from_projection(task_states)`
- `fsm._cancel_handler.rebuild_from_events(entries)`
- `fsm._suspension_manager.rebuild_from_events(entries)`
- `fsm._hil_coordinator.rebuild_from_events(entries)`
- `fsm._turn_state.rebuild_from_projection(pending)`

---

## 2. EXPERIENCE/ (8 files, ~776 lines)

### 2.1 `experience/__init__.py` (~46 lines)

**Exports (\_\_all\_\_)**: 7 output dataclasses + 6 component classes + 1 orchestrator

| Category | Exports |
|----------|---------|
| Output dataclasses | `Anticipation`, `EmotionalTrajectory`, `FillMessage`, `NarrativeContext`, `ResponseStyle`, `TimingParams`, `ToneAdjustment` |
| Component classes | `AffectiveMirror`, `AnticipatoryResponder`, `EmotionalProcessor`, `NarrativeWeaver`, `ProactiveAgent`, `RhythmController` |
| Orchestrator | `ExperienceLayer` |

Component inventory with cadence:
- `EmotionalProcessor` → `EmotionalTrajectory` (every 25th turn)
- `AffectiveMirror` → `ToneAdjustment` (chained after EP)
- `NarrativeWeaver` → `NarrativeContext` (every 20th turn)
- `AnticipatoryResponder` → `Anticipation` (every 30th turn)
- `ProactiveAgent` → `FillMessage` (COMPANIONING + wait > 5s)
- `RhythmController` → `TimingParams` (every output)

---

### 2.2 `experience/layer.py` (~155 lines)

#### `ExperienceLayer`
Orchestrates all 6 experience components. Called by FSM after every turn_end.

| Instance Variable | Type |
|-------------------|------|
| `emotional_processor` | `EmotionalProcessor` |
| `affective_mirror` | `AffectiveMirror` |
| `narrative_weaver` | `NarrativeWeaver` |
| `anticipatory_responder` | `AnticipatoryResponder` |
| `proactive_agent` | `ProactiveAgent` |
| `rhythm_controller` | `RhythmController` |
| `turn_count` | `int` |

| Method | Signature | Returns | Notes |
|--------|-----------|---------|-------|
| `__init__` | `(self) -> None` | — | Creates all 6 components |
| `tick` | `async (self, fsm_state: str, context: dict) -> dict` | Dict of component name → typed output | Fires components at cadence; respects EP skip rule |

**tick() context dict expected keys**:
- `turn_transcript: str`
- `affect_history: list[dict]`
- `front_refine_affect_confidence: float`
- `conversation_history: list[dict]`
- `memory_recalls: list[dict]`
- `task_state: dict`
- `user_patterns: dict`
- `wait_duration_ms: int`
- `persona: dict`
- `user_cadence: dict`

**tick() envelope keys**: `"emotional"`, `"tone"`, `"narrative"`, `"anticipation"`, `"fill"`, `"timing"`

**Cadence logic**:
- EP fires when `turn_count % emotional_processor_cadence == 0` AND `front_refine_affect_confidence <= ep_skip_confidence_threshold`
- AM fires immediately after EP (chained, not independent cadence)
- NW fires when `turn_count % narrative_weaver_cadence == 0`
- AR fires when `turn_count % anticipatory_responder_cadence == 0`
- PA fires when `fsm_state == "COMPANIONING"` AND `wait_duration_ms > proactive_wait_threshold_ms`
- RC fires every tick (always)

**Cross-component imports**:
- `from k1.concierge.config import get_config`
- All 6 component imports from within experience/

---

### 2.3 `experience/affective_mirror.py` (~125 lines)

#### `ToneAdjustment` (dataclass)
Output consumed by DynamicPromptBuilder identity section.

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `warmth` | `float` | `0.5` | 0.0 (clinical) to 1.0 (warm) |
| `formality` | `float` | `0.5` | 0.0 (casual) to 1.0 (formal) |
| `pace` | `str` | `"normal"` | "slow" \| "normal" \| "fast" |
| `mirror_intensity` | `float` | `0.0` | 0.0 = no mirroring, 1.0 = full match |

#### `AffectiveMirror`
Computes fulfillment-based tone adjustment. Budget: 1 ms.

| Method | Signature | Returns |
|--------|-----------|---------|
| `mirror` | `async (self, emotional_state: dict, persona: dict) -> ToneAdjustment` | Tone adjustment |

**Fulfillment strategy (NOT mirroring)**:
| User State | warmth | formality | pace | mirror_intensity |
|------------|--------|-----------|------|------------------|
| Crisis (arousal>0.7, valence<-0.5) | base+0.1 | base+0.1 | slow | 0.0 |
| Sad/frustrated (valence<-0.3) | base+0.15 | base-0.1 | slow | 0.0 |
| Excited (valence>0.5) | base+0.1 | base-0.05 | fast | 0.7 |
| Mildly positive (valence>0.2) | base+0.05 | base | normal | 0.3 |
| Neutral | base | base | normal | 0.0 |

**Module-level functions**: `_clamp(value: float, lo: float = 0.0, hi: float = 1.0) -> float`

**Cross-component imports**: None (only `dataclasses`)

---

### 2.4 `experience/emotional_processor.py` (~240 lines)

#### `EmotionalTrajectory` (dataclass)
Output written to `affective_now` SS section.

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `valence` | `float` | `0.0` | -1.0 (negative) to +1.0 (positive) |
| `arousal` | `float` | `0.5` | 0.0 (calm) to 1.0 (excited) |
| `dominance` | `float` | `0.5` | 0.0 (submissive) to 1.0 (dominant) |
| `trend` | `str` | `"stable"` | "rising" \| "falling" \| "stable" |
| `confidence` | `float` | `0.0` | 0.0 = no data, 1.0 = high certainty |

#### Module-level constants:
- `_TREND_THRESHOLD = 0.08` — slope must exceed this for rising/falling
- `_DECAY_FACTOR = 0.7` — exponential weight decay (each older turn = 70% of next)

#### Module-level functions:
| Function | Signature | Returns | Notes |
|----------|-----------|---------|-------|
| `_weighted_average` | `(values: list[float], decay: float) -> float` | Weighted avg | Newest = highest weight |
| `_valence_slope` | `(values: list[float]) -> float` | Linear slope | Least-squares regression |
| `_variance` | `(values: list[float]) -> float` | Variance | Standard variance |
| `_infer_dominance` | `(transcript: str) -> float` | 0.0-1.0 | Command vs question heuristics |

**`_infer_dominance` patterns**:
- Imperative starters: "do ", "make ", "set ", "get ", "find ", "show ", "tell ", "send ", "order ", "book ", "buy ", "call ", "stop ", "start ", "turn ", "open ", "close ", "add ", "remove ", "delete ", "cancel ", "schedule ", "remind "
- Hedges: "maybe", "i think", "not sure", "could you", "would you", "please"
- `?` → question signal; `!` → command signal

#### `EmotionalProcessor`
Computes emotional trajectory from UltraBERT affect history. Budget: 1 ms.

| Method | Signature | Returns | Notes |
|--------|-----------|---------|-------|
| `process` | `async (self, turn_transcript: str, affect_history: list[dict]) -> EmotionalTrajectory` | Smoothed trajectory | Reads UltraBERT output, computes cross-turn trajectory |

**Algorithm**:
1. Extract valence/arousal sequences from affect_history
2. Exponentially weighted averages (decay=0.7)
3. Valence slope → trend (rising/falling/stable)
4. Confidence = exp(-2 * variance) * sample_factor
5. Dominance from transcript patterns

**Cross-component imports**: None (only `math`, `dataclasses`)

---

### 2.5 `experience/narrative_weaver.py` (~55 lines)

#### `NarrativeContext` (dataclass)
Output consumed by DynamicPromptBuilder Session Trajectory.

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `active_threads` | `list[str]` | `[]` | Active narrative threads |
| `thread_salience` | `dict[str, float]` | `{}` | Salience scores per thread |
| `weave_suggestion` | `str` | `""` | Suggested narrative connection |

#### `NarrativeWeaver` — **STUB**
Budget: 10 ms. Fire cadence: every 20th turn.

| Method | Signature | Returns | Notes |
|--------|-----------|---------|-------|
| `weave` | `async (self, conversation_history: list[dict], memory_recalls: list[dict]) -> NarrativeContext` | Empty NarrativeContext | Stub — returns default |

**Cross-component imports**: None

---

### 2.6 `experience/anticipatory_responder.py` (~65 lines)

#### `Anticipation` (dataclass)
Two integration points: DynamicPromptBuilder (hint in prompt) and ReAct loop (pre-warm tool schemas).

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `predicted_intent` | `str` | `""` | What user likely wants next |
| `confidence` | `float` | `0.0` | 0.0 = no prediction (stub) |
| `pre_fetch_capabilities` | `list[str]` | `[]` | Capabilities to pre-warm |
| `suggested_prompt_hint` | `str` | `""` | Hint injected into Front prompt |

#### `AnticipatoryResponder` — **STUB**
Budget: 15 ms. Fire cadence: every 30th turn.

| Method | Signature | Returns | Notes |
|--------|-----------|---------|-------|
| `anticipate` | `async (self, task_state: dict, user_patterns: dict) -> Anticipation` | Empty Anticipation | Stub — returns default |

**Cross-component imports**: None

---

### 2.7 `experience/proactive_agent.py` (~65 lines)

#### `FillMessage` (dataclass)
Emitted as `k1.proactive.fill.v1` on bus. FSM routes to Front for presentation.

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `message` | `str` | `""` | What to say during the wait |
| `style` | `str` | `"informational"` | "informational" \| "reassuring" \| "entertaining" |
| `show_progress` | `bool` | `False` | Whether to show progress indicator |

#### `ProactiveAgent` — **STUB**
Budget: 50 ms. Fire condition: COMPANIONING + wait > 5s.

| Method | Signature | Returns | Notes |
|--------|-----------|---------|-------|
| `generate_fill` | `async (self, task_state: dict, wait_duration_ms: int) -> FillMessage` | Empty FillMessage | Stub — returns default |

**Cross-component imports**: None

---

### 2.8 `experience/rhythm_controller.py` (~175 lines)

#### `TimingParams` (dataclass)
Applied by delivery pipeline before streaming.

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `pre_delay_ms` | `int` | `0` | Pause before response |
| `inter_chunk_ms` | `int` | `0` | Pause between streaming chunks |
| `typing_indicator` | `bool` | `False` | Show typing indicator |
| `beat_pattern` | `str` | `"steady"` | "steady" \| "syncopated" \| "accelerating" |

#### `ResponseStyle` (dataclass)
User communication style learned from conversation patterns.

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `response_length_preference` | `str` | `"balanced"` | "concise" \| "balanced" \| "detailed" |
| `message_style` | `str` | `"single_complete"` | "single_complete" \| "conversational_bursts" |
| `verbosity_level` | `float` | `0.5` | 0.0 (terse) to 1.0 (verbose) |

#### Module-level constants:
- `_SHORT_MSG_THRESHOLD = 30` (chars)
- `_LONG_MSG_THRESHOLD = 100` (chars)
- `_BURST_GAP_THRESHOLD_MS = 5000` (5 seconds)

#### Module-level function:
| Function | Signature | Returns |
|----------|-----------|---------|
| `_compute_response_style` | `(user_cadence: dict, conversation_history: list[dict]) -> ResponseStyle` | Computed style |

**Style adaptation logic**:
- avg msg length < 30 chars → concise (verbosity 0.3)
- avg msg length > 100 chars → detailed (verbosity 0.7)
- avg msg length 30-100 → balanced (linear interpolation 0.3-0.7)
- avg_gap_ms < 5000 + sample_count ≥ 2 → conversational_bursts (verbosity -= 0.1)

#### `RhythmController`
Budget: 0.5 ms. Fire cadence: every output.

| Instance Variable | Type |
|-------------------|------|
| `last_response_style` | `ResponseStyle` |

| Method | Signature | Returns | Notes |
|--------|-----------|---------|-------|
| `__init__` | `(self) -> None` | — | |
| `get_pattern` | `(self, turn_count: int, user_cadence: dict) -> TimingParams` | Default TimingParams | Also updates `last_response_style` |
| `get_beat` | `(self, output_length: int) -> str` | `"steady"` | Placeholder |
| `adjust_timing` | `(self, current: TimingParams, feedback: dict) -> TimingParams` | Same `current` | Placeholder |

**Cross-component imports**: None

---

## 3. IDENTITY/ (2 files, ~223 lines)

### 3.1 `identity/__init__.py` — Empty

---

### 3.2 `identity/dynamic_identity.py` (~223 lines)

#### `ConversationalRole` (str subclass) — Role constants
| Constant | Value |
|----------|-------|
| `EXPERT` | `"expert"` |
| `PEER` | `"peer"` |
| `GUIDE` | `"guide"` |
| `SUPPORTER` | `"supporter"` |
| `EXECUTOR` | `"executor"` |

#### `DynamicIdentityConfig` (dataclass)
Configuration for dynamic identity adaptation.

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `enable_role_adaptation` | `bool` | `True` | Adapt conversational role per turn |
| `enable_expertise_tracking` | `bool` | `True` | Track domain expertise |
| `enable_formality_drift` | `bool` | `True` | Allow formality to drift |
| `default_role` | `str` | `ConversationalRole.PEER` | Starting role |
| `expertise_learning_rate` | `float` | `0.1` | How fast expertise scores update |

#### `IdentitySnapshot` (dataclass)
Dynamic identity state for a single turn. Consumed by PromptBuilder.

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `active_user_id` | `str` | `""` | Active user identifier |
| `active_user_name` | `str` | `""` | Active user display name |
| `conversational_role` | `str` | `ConversationalRole.PEER` | Role this turn |
| `domain_expertise` | `dict[str, float]` | `{}` | Domain → expertise score |
| `formality_level` | `float` | `0.5` | Current formality |
| `relationship_turns` | `int` | `0` | Total turns in relationship |
| `emotional_attunement` | `str` | `""` | Attunement guidance |
| `context_tags` | `list[str]` | `[]` | Tags for prompt enrichment |

| Method | Signature | Returns | Notes |
|--------|-----------|---------|-------|
| `to_prompt_block` | `(self) -> str` | Formatted prompt injection | Includes role, expertise, register, attunement, context |

#### `DynamicIdentityContext`
Generalized kernel primitive. Maintains session-level identity signals, computes fresh IdentitySnapshot each turn.

| Slot | Type |
|------|------|
| `_config` | `DynamicIdentityConfig \| None` |
| `_domain_expertise` | `dict[str, float]` |
| `_turn_count` | `int` |
| `_formality_samples` | `list[float]` |
| `_last_role` | `str` |

| Method | Signature | Returns | Notes |
|--------|-----------|---------|-------|
| `__init__` | `(self, config: DynamicIdentityConfig \| None = None) -> None` | — | |
| `compute` | `(self, user_id: str = "", user_name: str = "", affect_band: str = "neutral", domain: str = "", complexity_tier: str = "LOW", has_inflight_tasks: bool = False) -> IdentitySnapshot` | Fresh snapshot | Main entry; increments turn_count |
| `turn_count` (property) | `-> int` | Total turns | |
| `domain_expertise` (property) | `-> dict[str, float]` | Copy of expertise scores | |
| `_compute_role` | `(self, complexity_tier: str, affect_band: str, has_inflight: bool) -> str` | Role string | Priority: crisis/low→SUPPORTER, HIGH→EXPERT, inflight→EXECUTOR, >10 turns→PEER, else→GUIDE |
| `_update_expertise` | `(self, domain: str) -> None` | — | Increments by learning_rate, capped at 1.0 |
| `_compute_formality` | `(self) -> float` | 0.0-1.0 | Drifts down over turns: ≤3→0.6, >20→0.3, else linear decay |
| `_compute_attunement` | `(self, affect_band: str) -> str` | Guidance string | Maps affect band to guidance |
| `_compute_context_tags` | `(self, has_inflight: bool, domain: str) -> list[str]` | Tag list | Tags: multitasking, extended_session, domain:X, returning_topic |

**Attunement map**:
| Affect Band | Guidance |
|-------------|----------|
| `crisis` | "Be calm and grounding. Lead with action." |
| `low` | "Be gentle and patient. No pressure." |
| `neutral` | "Natural and efficient." |
| `positive` | "Match energy. Celebrate." |
| `elevated` | "Acknowledge feeling, then proceed." |

**Cross-component imports**: None (only `logging`, `dataclasses`)

---

## 4. COMPRESSION/ (2 files, ~253 lines)

### 4.1 `compression/__init__.py` — Empty

---

### 4.2 `compression/episodic_compressor.py` (~253 lines)

#### `CompressionStrategy` (plain class) — Strategy constants
| Constant | Value |
|----------|-------|
| `KEY_FACTS` | `"key_facts"` |
| `EXTRACTIVE` | `"extractive"` |
| `TOPIC_SUMMARY` | `"topic_summary"` |

#### `CompressedEpisode` (dataclass)
Compressed summary of N conversation turns.

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `episode_id` | `str` | (required) | Unique identifier |
| `turn_range` | `tuple[int, int]` | (required) | (start_turn, end_turn) inclusive |
| `summary` | `str` | (required) | Compressed text summary |
| `key_facts` | `list[str]` | `[]` | Facts that must survive compression |
| `topic` | `str` | `""` | Primary topic of the episode |
| `original_count` | `int` | `0` | Number of turns compressed |
| `compressed_at_ns` | `int` | `time.monotonic_ns()` | When compression occurred |

| Method | Signature | Returns | Notes |
|--------|-----------|---------|-------|
| `to_prompt_block` | `(self) -> str` | Formatted prompt block | `[EPISODE: turns X-Y]` format |
| `token_estimate` | `(self) -> int` | Rough token count | `len(text) // 4` |

#### `CompressionConfig` (dataclass)
Configuration for episodic compression.

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `recent_window` | `int` | `10` | Recent turns to keep uncompressed |
| `episode_size` | `int` | `5` | Turns per compressed episode |
| `compression_strategy` | `str` | `CompressionStrategy.KEY_FACTS` | Strategy to use |
| `preserve_hitl_turns` | `bool` | `True` | Keep HITL turns uncompressed |
| `preserve_safety_turns` | `bool` | `True` | Keep safety-flagged turns uncompressed |
| `min_turns_to_compress` | `int` | `15` | Minimum turns before compression activates |

#### `EpisodicCompressor`
Compresses old conversation turns into episodic summaries. Uses extractive heuristics (no LLM calls). Subclass and override `compress_segment()` for LLM-based abstractive compression.

| Slot | Type |
|------|------|
| `_config` | `CompressionConfig` |
| `_episodes` | `list[CompressedEpisode]` |
| `_compression_count` | `int` |

| Method | Signature | Returns | Notes |
|--------|-----------|---------|-------|
| `__init__` | `(self, config: CompressionConfig \| None = None) -> None` | — | |
| `should_compress` | `(self, total_turns: int) -> bool` | Whether to trigger compression | `total_turns >= min_turns_to_compress` |
| `identify_compressible` | `(self, turns: list[dict[str, Any]]) -> list[list[dict[str, Any]]]` | Segments of turns | Keeps recent_window intact; groups older turns; preserves HITL/safety |
| `compress_segment` | `(self, segment: list[dict[str, Any]], episode_id: str = "") -> CompressedEpisode` | Compressed episode | Extractive: user messages (80 chars), intents, entities. Override for LLM |
| `compress_all` | `(self, turns: list[dict[str, Any]]) -> tuple[list[CompressedEpisode], list[dict[str, Any]]]` | (episodes, recent_turns) | Main entry point |
| `build_compressed_context` | `(self, episodes: list[CompressedEpisode], recent_turns: list[dict[str, Any]]) -> str` | Formatted prompt string | Combines episodes + recent turns for prompt injection |

**Token economics** (from docstring):
- 25 raw turns × ~200 tokens = ~5000 tokens
- 5 episodes × ~80 tokens + 10 recent turns × ~200 = ~2400 tokens
- Net savings: ~50% token reduction

**Preservation rules**: Turns with `has_hitl=True` or `safety_band` in ("RED", "AMBER") are never compressed.

**Cross-component imports**: None (only `logging`, `time`, `dataclasses`, `typing`)

---

## 5. CROSS-COMPONENT DEPENDENCY SUMMARY

### Imports FROM other k1.concierge.* subpackages:

| File | Imports From |
|------|-------------|
| `ledger/writer.py` | `k1.concierge.ledger.store` (ILedgerStore, LedgerEntry); TYPE_CHECKING: `k1.concierge.events.base` (CanonicalEventMeta) |
| `ledger/projections.py` | `k1.concierge.protocols.hitl_persistence` (TaskStateEntry, TaskStatus) |
| `ledger/recovery.py` | `k1.concierge.ledger.projections` (project_*); `k1.concierge.protocols.hitl_persistence` (TaskStatus) |
| `experience/layer.py` | `k1.concierge.config` (get_config) |
| All other files | **No cross-component imports** — self-contained |

### External dependencies:
- **All 17 files**: stdlib only (`dataclasses`, `logging`, `typing`, `threading`, `math`, `time`, `collections.deque`, `datetime`)
- **No third-party imports** in any file

### Duck-typed FSM dependencies (recovery.py):
- `fsm._task_bridge.rebuild_from_projection()`
- `fsm._cancel_handler.rebuild_from_events()`
- `fsm._suspension_manager.rebuild_from_events()`
- `fsm._hil_coordinator.rebuild_from_events()`
- `fsm._turn_state.rebuild_from_projection()`

---

## 6. ARCHITECTURAL PATTERNS

### Ledger: Event-Sourced Conversation Timeline
- **What's tracked**: Every domain event in a session (user input, task lifecycle, HIL interactions, weave emissions, dead letters)
- **Persistence model**: Append-only, immutable `LedgerEntry` records with monotonic sequence numbers
- **Idempotency**: `event_id` (UUID4) deduplication in both store and writer
- **Current implementation**: `InMemoryLedgerStore` (POC); `SqliteLedgerStore` planned for M2+
- **State derivation**: All session state is a pure projection from ledger events (zero-state-loss crash recovery)

### Experience: Cadence-Based Processing Pipeline
- **Pattern**: Orchestrator (`ExperienceLayer.tick()`) fires 6 components at configurable cadences
- **Output model**: Dict of component name → typed dataclass output, emitted on bus
- **EP skip rule**: If Front's `refine_affect()` confidence > threshold, EmotionalProcessor is skipped (avoids overwriting high-quality corrections)
- **Implemented**: EmotionalProcessor (full algorithm), AffectiveMirror (full algorithm), RhythmController (full algorithm with ResponseStyleAdapter)
- **Stubs**: NarrativeWeaver, AnticipatoryResponder, ProactiveAgent (return defaults)

### Identity: Dynamic Overlay on Static Persona
- **Pattern**: Static PersonaSection (frozen at session init) + DynamicIdentityContext (recomputed each turn)
- **Adaptation signals**: affect_band, domain, complexity_tier, has_inflight_tasks
- **Role selection**: Priority cascade: crisis→SUPPORTER, HIGH complexity→EXPERT, inflight→EXECUTOR, >10 turns→PEER, else→GUIDE
- **Formality drift**: Starts formal (0.6), drifts casual over turns (→0.3 after 20 turns)
- **Expertise tracking**: Incremental learning rate (0.1 per turn in domain), capped at 1.0
- **Output**: `IdentitySnapshot.to_prompt_block()` injected into LLM prompts

### Compression: Episodic Turn Compression
- **What gets compressed**: Conversation turns older than `recent_window` (default: 10 most recent kept intact)
- **Algorithm**: Extractive key-facts by default (no LLM); subclass for abstractive compression
- **Episode granularity**: Configurable `episode_size` (default: 5 turns per episode)
- **Preservation**: HITL turns and safety-flagged turns (RED/AMBER) are never compressed
- **Activation threshold**: `min_turns_to_compress` (default: 15)
- **Token savings**: ~50% reduction (5000 → 2400 tokens at 25 turns)
