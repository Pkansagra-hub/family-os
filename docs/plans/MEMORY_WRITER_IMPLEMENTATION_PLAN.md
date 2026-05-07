# Memory Writer Implementation Plan

> **Status**: DRAFT
> **Date**: 2026-03-10
> **Module**: `k1/memory_writer/`
> **Design Doc**: `k1/memory_writer/memory_writer_architecture.md` (2,488 lines, 35 sections)
> **Mermaid Diagram**: `k1/memory_writer/memory_writer.mmd` (474 lines)
> **Module Contract**: `k1/contracts/modules/memory_writer/module.contract.yaml`
> **Wiring Contract**: `k1/contracts/modules/memory_writer/wiring.contract.yaml`
> **Test Baseline**: 7 files, 208 tests passing

---

## Table of Contents

1. [Executive Summary](#1-executive-summary)
2. [Current State Assessment](#2-current-state-assessment)
3. [Service Model — Per-Session Attachment](#3-service-model--per-session-attachment)
4. [Input/Output Data Flow — REAL Data Shapes](#4-inputoutput-data-flow--real-data-shapes-from-code)
5. [K0 Output Contract — What P02 + P03 + URE Require From MW](#5-k0-output-contract--what-p02--p03--ure-require-from-mw)
6. [Implementation Phases](#6-implementation-phases)
7. [Phase P — Prerequisite: Tool Call Data Pipeline](#7-phase-p--prerequisite-tool-call-data-pipeline)
8. [Phase 0 — Foundation Fixes](#8-phase-0--foundation-fixes)
9. [Phase 1 — Filter + Context Assembly (No LLM)](#9-phase-1--filter--context-assembly-no-llm)
10. [Phase 2 — LLM Extraction](#10-phase-2--llm-extraction)
11. [Phase 3 — Envelope + Batch + Bridge](#11-phase-3--envelope--batch--bridge)
12. [Phase 4 — Pipeline Assembly + Service Lifecycle](#12-phase-4--pipeline-assembly--service-lifecycle)
13. [Phase 5 — Remaining Adapters + Integration](#13-phase-5--remaining-adapters--integration)
14. [Dependency Map](#14-dependency-map)
15. [Test Strategy](#15-test-strategy)
16. [Risk Register](#16-risk-register)
17. [File Inventory — Exists vs Missing](#17-file-inventory--exists-vs-missing)

---

## 1. Executive Summary

Memory Writer (MW) is K1's episodic memory formation system — a **per-session background service** that converts conversation turns into 37-field MemoryAtom envelopes routed through Bridge to K0 for permanent storage in `st_hipp_events`.

**What exists (26% — 11 of 43 files):**

- All domain types (15 enums, 9 frozen dataclasses, MemoryAtom with 37 fields)
- 5 port Protocols (hexagonal boundary)
- 2 production adapters (SessionReadAdapter, ModelHubAdapter)
- Config, events, invariants (MW-01 through MW-13)
- Context assembly + place resolver (temporal/spatial helpers)
- 208 passing tests across 7 test files

**What is missing (74% — 32 of 43 files):**

- Entire 5-stage pipeline (filter → context → extraction → envelope → batch)
- 3 production adapters (BridgeCommand, EventSubscription, Health)
- Test adapters (mock/fake for integration tests)
- MemoryWriterFactory (service lifecycle)
- Circuit breaker
- `__init__.py` exports (empty)

MW is **not** wired into Fabric or Kernel — no code references MW from outside the module yet.

**K0 output contract (§5):** K0's P02 uses trust-then-fill — when MW provides good signals (~85%),
P02 validates and passes through (~80ms). When MW is missing/bad, P02 falls back to full UltraBERT
inference (~140ms, no regression). UltraBERT v4 (149M params, 12 heads, 20ms) is the safety net.
MW must focus on what LLMs uniquely do: correction detection, temporal reasoning across turns,
and narrative arc understanding. 9 field-level gaps identified (§5.9), mostly solved in FieldMapper.

---

## 2. Current State Assessment

### Existing Source Files (11)

| File | Lines | Purpose | Quality |
|------|-------|---------|---------|
| `__init__.py` | 0 | EMPTY — contract claims 25+ exports | ❌ Gap G-5 |
| `types.py` | ~580 | 15 enums + 9 frozen DCs + MemoryAtom(37) | ✅ Solid |
| `config.py` | ~100 | MWConfig frozen DC, 15 fields, 7 groups | ✅ Solid |
| `events.py` | ~140 | 6 topics + 6 frozen payloads | ✅ Solid |
| `invariants.py` | ~450 | 13 assertion helpers (MW-01–MW-13) | ✅ Solid |
| `context_assembly.py` | ~175 | 4 functions: temporal/spatial resolution | ✅ Solid |
| `place_resolver.py` | ~120 | PlaceResolver (O(1) exact, O(n) prefix) | ✅ Solid |
| `ports/__init__.py` | ~30 | Re-exports 5 ports | ✅ Solid |
| `ports/session_read_port.py` | ~60 | ISessionReadPort Protocol | ✅ Solid |
| `ports/bridge_command_port.py` | ~55 | IBridgeCommandPort Protocol | ✅ Solid |
| `ports/event_subscription_port.py` | ~55 | IEventSubscriptionPort Protocol | ✅ Solid |
| `ports/model_hub_port.py` | ~55 | IModelHubPort Protocol | ✅ Solid |
| `ports/health_port.py` | ~50 | IHealthPort Protocol | ✅ Solid |
| `adapters/__init__.py` | ~10 | Exports 2 adapters | ✅ Solid |
| `adapters/session_read_adapter.py` | ~80 | SessionReadAdapter (E-0.5.6) | ✅ Solid |
| `adapters/model_hub_adapter.py` | ~80 | ModelHubAdapter (E-0.5.3) | ✅ Solid |

### Existing Test Files (7 — 208 tests)

| File | Tests | Coverage |
|------|-------|----------|
| `test_model_hub_adapter_053.py` | ~30 | ModelHubAdapter |
| `test_mw_invariants.py` | ~40 | MW-01 through MW-13 |
| `test_place_resolver.py` | ~25 | PlaceResolver |
| `test_race_condition_fix.py` | ~20 | Race condition T7 |
| `test_session_read_adapter_056.py` | ~30 | SessionReadAdapter |
| `test_temporal_link.py` | ~35 | TemporalLink + MemoryAtom fields |
| `test_turn_timestamp_propagation.py` | ~28 | Turn timestamp through pipeline |

### Architecture Documentation

| Doc | Lines | Status |
|-----|-------|--------|
| `memory_writer_architecture.md` | 2,488 | 35 sections, comprehensive design |
| `memory_writer.mmd` | 474 | Full mermaid diagram (trigger→batch) |
| `ARCHITECTURE.md` | ~600 | Module overview + gap analysis |
| `module.contract.yaml` | ~200 | Exports, deps, invariants |
| `wiring.contract.yaml` | ~350 | 43 required files, capabilities, events |

---

## 3. Service Model — Per-Session Attachment

MW is a **session-bound service** — not a singleton. Key design:

```
Fabric spawns new session
  → SessionState created (any session: new, restored, etc.)
  → MW service instance attached to that session
  → MW subscribes to turn.complete.v1 for that session_id
  → On each turn: filter → context → extract → envelope → batch → bridge
  → On session end: MW instance unsubscribes and is cleaned up
```

### Per-Session Semantics

| Aspect | Design |
|--------|--------|
| **Lifecycle** | Created when SessionState is launched, destroyed on session end |
| **Cardinality** | 1 MW instance per active session |
| **State** | Stateless across turns (no accumulated state). Dedup set cleared per session |
| **Concurrency** | Single-threaded async per session. Queue max 2 turns |
| **Input** | `turn.complete.v1` events from Concierge (via Bus) |
| **Output** | MWEnvelope batches → IBridgeCommandPort → K0 |
| **SS Access** | Read-only via ISessionReadPort (MW-01: NEVER writes) |

### Why Per-Session (Not Singleton)

1. Each session has its own SessionState — MW needs a bound ISessionReadPort
2. Dedup set (processed turn_ids) is session-scoped
3. Circuit breaker state is session-scoped (one bad LLM call doesn't block all sessions)
4. Clean lifecycle: session end = MW cleanup, no dangling references

### Integration Point: Fabric

Fabric is responsible for spawning MW when it creates a session. The `MemoryWriterFactory` will be called by Fabric with the session's port bundle:

```python
# In Fabric session creation:
mw_service = MemoryWriterFactory.create(
    session_read=session_read_adapter,
    bridge_cmd=bridge_command_adapter,
    event_sub=event_subscription_adapter,
    model_hub=model_hub_adapter,
    health=health_adapter,
    config=mw_config,
)
await mw_service.start()  # subscribes to turn.complete.v1
# ... session runs ...
await mw_service.stop()   # unsubscribes, flushes pending batch
```

---

## 4. Input/Output Data Flow — REAL Data Shapes (From Code)

### Design Principle: Section-Agnostic Reading

**Problem:** The original design hardcodes 13 section names in MW config and SS read calls.
Every time a new SS section is added, MW code would need changes.

**Solution:** MW reads ALL available sections dynamically via `ISessionReadPort`.
The port calls `SessionStateManager.get_snapshot()` which already iterates `ALL_SECTIONS`
(derived from `SECTION_BUDGETS.keys()` in `sizetracker.py`). MW should **never** maintain
its own list of section names. New sections automatically become available.

```python
# WRONG (current config.py — hardcodes section names):
session_sections_hot = ["beliefs_active", "history_active", ...]
snapshot = await port.snapshot(config.all_sections)  # 13 hardcoded names

# RIGHT (section-agnostic):
snapshot = await port.snapshot_all()  # reads whatever sections exist
# OR: ask SS what sections it has, then read them
available = await port.list_sections()  # returns frozenset from ALL_SECTIONS
snapshot = await port.snapshot(list(available))
```

MW doesn't need to know section names. It passes the full snapshot dict to the LLM
as context. The LLM extracts memories from whatever data is there.

### The REAL Trigger Problem: Per-Turn LLM Is Wasteful

**Current design flaw:** Every `turn.complete.v1` triggers an LLM extraction.

Why this is bad:

1. **One turn is a narrow window.** User says "ok sounds good" → MW calls LLM → LLM says "nothing to extract" → wasted tokens.
2. **Context builds over turns.** Turn 3 alone: "We went to Olive Garden." Turn 4: "Mom really liked the breadsticks." Turn 5: "Dad wasn't feeling well though." Only after turn 5 do you have the full picture: family dinner at Olive Garden, Mom happy, Dad unwell.
3. **LLM cost.** 2000 tokens × every turn × cheapest model = still adds up fast. If 40% of turns are trivial (greetings, "ok", "thanks"), that's 40% wasted LLM budget even WITH the filter.
4. **Redundant extractions.** Turn 3 extracts "dinner at Olive Garden". Turn 4 extracts "dinner at Olive Garden, Mom liked breadsticks". Turn 5 extracts the full picture. K0 now has 3 overlapping atoms from the same conversation arc.

### Proposed Trigger Model: Conversation-Window Extraction

Instead of per-turn LLM calls, MW should batch conversation windows:

```
Option A: Turn-Count Window (e.g. every 3-5 turns)
  Turn 1,2,3 → accumulate in SS history_active
  Turn 3 triggers MW → reads last 3 turns as a group → 1 LLM call → richer atoms

Option B: Signal-Based Trigger (topic shift / arc completion)
  Concierge detects topic shift or arc position change → emits trigger
  MW reads accumulated turns since last extraction → 1 LLM call

Option C: Hybrid (current filter + window)
  Every turn.complete.v1 arrives → filter runs (no LLM cost)
  If PASS: add to extraction queue
  Every N passes OR 250ms idle: batch extract from accumulated context
```

**Key insight:** SessionState `history_active` already holds the last 10-25 full-fidelity turns with user_message, assistant_response, entities, intents, emotion per turn. MW doesn't need the trigger payload to carry conversation text — it's already accumulated in SS. The trigger just needs to say "time to extract."

### What SessionState ACTUALLY Contains (From Code)

Each section is a **mutable class** (not frozen DC) implementing `ISection` protocol.
Data accessed via methods, returned as dicts/lists. Here's what MW gets:

#### `history_active` — The Primary Input (Last 10-25 full turns)

```python
# HistoryActiveSection (k1/sessionstate/sections/history_active.py)
# Each Turn dataclass:
Turn(
    turn_id: str,              # UUID
    turn_number: int,          # ordinal (1-based)
    user_message: str,         # FULL user text
    assistant_response: str,   # FULL assistant text
    timestamp_ms: int,         # epoch ms
    duration_ms: int,
    metadata: TurnMetadata(    # intent, entities list, emotion, confidence
        intent="request_info",
        entities=["Mom", "Olive Garden"],
        emotion="happy",
        confidence=0.92,
    ),
    entities: ["Mom", "Olive Garden"],
    intents: ["dining", "family_activity"],
    emotion: "happy",
    sub_entries: [TypedHistoryEntry(...)],  # dual-LLM decomposition
)
# Section holds: List[Turn] (max 25), current_turn_number, token counters
```

This is the richest input — full conversation text with pre-extracted entities/intents/emotion per turn.

#### `beliefs_active` — Current Turn Facts (SVO Triples)

```python
# BeliefsActiveSection
Fact(
    id: str,
    subject: str,           # "Mom"
    predicate: str,         # "likes"
    object: str,            # "breadsticks"
    confidence: float,      # 0.85
    privacy_band: str,      # "GREEN"
)
# Also: EntityRef list, MentionedTime, MentionedLocation, pinned_fact_ids
# NOTE: beliefs_active is per-turn overwrite — cleared on start_new_turn()
```

#### `beliefs_history` — Accumulated Facts (WARM, LRU)

```python
# BeliefsHistorySection
ArchivedFact(
    # wraps Fact SVO triple +
    original_turn: int,
    last_accessed_turn: int,
    access_count: int,
    lru_score: float,
    is_stale: bool,
)
# Max 100 facts, LRU-ordered, EntityFactIndex for lookup
```

#### `affective_now` — Emotion State

```python
# AffectiveNowSection
current_emotion: str,           # "happy"
intensity: float,               # 0.8
dimensions: EmotionDimensions(  # Russell's circumplex
    valence: float,   # -1.0 to 1.0
    arousal: float,   # -1.0 to 1.0
    dominance: float, # -1.0 to 1.0
),
trajectory: EmotionTrajectory,  # emotion arc
recent_emotions: List[EmotionSnapshot],  # last 5
empathy_needed: bool,
celebration_appropriate: bool,
```

#### `scoreboard` — Discourse Tracking

```python
# ScoreboardSection
referents: List[Referent],       # discourse entities (who/what is being discussed)
qud_stack: List[Question],       # Questions Under Discussion
topic_stack: List[Topic],        # active topics
salience_map: List[SalienceEntry],  # what's salient right now
commitments: List[Commitment],   # promises made
current_turn: int,
last_user_intent: str,
```

#### `narrative_active` — Conversation Arc

```python
# NarrativeActiveSection
primary_thread: ConversationThread,
paused_threads: List[ConversationThread],  # max 5
arc: NarrativeArc(
    position: str,  # EXPOSITION → RISING_ACTION → CLIMAX → RESOLUTION
),
```

#### `control` — Session Control State

```python
# ControlSection
agent_leases: Dict[str, AgentLease],
flow_state: FlowState,
turn_lock: TurnLock,
intents: IntentClassification,
domains: DomainContext,
safety: SafetyContext,
temporal_anchor: Optional[Dict],
turn_count: int,
current_turn_id: str,
```

#### `persona` — User Personality Profile (WARM, rarely changes)

```python
# PersonaSection
personality: PersonalityProfile(
    warmth=0.7, formality=0.3, verbosity=0.5, humor=0.6, directness=0.8
),
voice: VoicePreferences,
vocabulary: List[VocabularyEntry],  # user_term → system_term
response_preferences: ResponsePreferences,
interaction_style: str,
```

#### `meta` — Session Identity (never evicts)

```python
# MetaSection
identity: SessionIdentity(session_id, user_id, device_id, privacy_band, is_anonymous),
lifecycle: SessionLifecycle(turn_count, is_active, is_expired),
memory_usage: MemoryUsage,  # per-section byte sizes
version: VersionInfo,
```

#### `task_state` — Active Tasks (never evicts)

```python
# TaskStateSection
tasks: Dict[str, TaskStateEntry(
    task_id, action, status,  # pending/dispatched/active/completed/failed
    progress_pct, pending_hil, depends_on, presented_at_turn
)]
```

#### `history_recent` — Compressed Older Turns (WARM)

```python
# HistoryRecentSection
compressed_turns: List[CompressedTurn],  # turns 11-30: entities+intents only, no full text
summarized_turns: List[SummarizedTurn],  # turns 31-40: single sentence LLM summary
session_summary: str,  # ~200 chars
```

#### `task_artifacts` — Task Outputs (HOT)

```python
# TaskArtifactsSection
TaskArtifactEntry(
    task_id: str,
    artifact_type: str,  # TEXT | CONFIRMATION | RECEIPT | SUMMARY | LIST | ERROR | MEDIA_REF
    content: str,        # the actual output
)
```

Task artifacts carry the **output** of tool-mediated actions (gym plan text, restaurant search
results, booking confirmations). MW uses these alongside tool call metadata to build rich
episodic atoms for tool-executed tasks.

#### Sections MW Skips

- `telemetry` — token/cost/latency metrics. Not relevant for memory extraction
- `artifacts_warm` — demoted task artifacts. Low value for episodic memory
- `clarifications` — pending clarification state. Transient, not memorable

### What MW Actually Needs vs What Exists

| Data Need for Extraction | Source Section | What it Provides |
|--------------------------|---------------|-----------------|
| **Conversation text** (primary) | `history_active` | Last 10-25 full turns with user_message + assistant_response |
| **Pre-extracted entities** | `history_active` per Turn | entities list, intents list, emotion per turn |
| **Current beliefs/facts** | `beliefs_active` | SVO triples (subject-predicate-object) with confidence |
| **Historical beliefs** | `beliefs_history` | Accumulated facts for contradiction detection |
| **Emotion context** | `affective_now` | Current emotion, VAD dimensions, empathy/celebration flags |
| **Discourse state** | `scoreboard` | Active referents, topics, QUD stack, commitments |
| **Conversation arc** | `narrative_active` | Primary thread, arc position (EXPOSITION→RESOLUTION) |
| **Person identities** | `persona` | Personality profile, vocabulary mappings |
| **Privacy band** | `meta` | GREEN/AMBER/RED → controls field stripping |
| **Session identity** | `meta` | session_id, user_id, device_id |
| **Temporal anchor** | `control` | temporal_anchor, turn_count |
| **Active tasks** | `task_state` | What tasks are running (for task-related memory) |
| **Tool call history** | `history_active` per Turn | `metadata["tool_calls"]` — tool names, arg summaries, status, result previews (Option D) |
| **Task outputs** | `task_artifacts` | Structured outputs from tool-executed tasks (receipts, plans, search results) |

### Tool Call Data — Enriching Turns with Execution Context (Option D)

**Problem:** When K1 executes tool calls (e.g. user asks "make me a gym plan", tool `plans`
is invoked, or user searches for restaurants, or plans a vacation), these are high-value
episodic memory events. But the rich execution data is **lost** after the ReAct loop ends:

| Data | Location | Survives? |
|------|----------|-----------|
| `DispatchRecord` (tool_name, arguments, result, timestamp_ms, iteration) | `ToolDispatcher.call_history` | ❌ Dies with dispatcher |
| `ToolResult.data` (structured response) | In-memory | ❌ Consumed in loop |
| `TaskComplete.tool_calls` | Bus event payload | ⚠️ Integer count only |
| `TaskStateEntry` | SS `task_state` | ✅ But lifecycle only (action, status) |
| `TaskArtifactEntry` | SS `task_artifacts` | ✅ But output only (content, type) |
| `TelemetrySection.had_tool_call` | SS `telemetry` | ✅ But boolean only |
| Bus `k1.tool.started.v1` / `k1.tool.completed.v1` | Fire-and-forget | ❌ No persistent subscriber |

MW only sees THAT a task happened and its output — not WHICH tools were called, with
what arguments, in what order, or what each tool returned.

**Design Decision: Option D — Hybrid (enrich TaskComplete + Turn annotation)**

The data already exists in `ToolDispatcher.call_history` — it's just thrown away.
Fix: extract tool call summaries before disposal and flow them through existing pipes.

```
ToolDispatcher.call_history (in-memory, complete)
  │
  ▼ (1) BackHandler builds TaskComplete
TaskComplete.tool_call_summaries: list[ToolCallSummary]
  │
  ▼ (2) FrontHandler / HistoryWriter receives TaskComplete
TypedHistoryEntry.metadata["tool_calls"]: list[dict]
  │
  ▼ (3) MW reads history_active turns
ExtractionContext.tool_calls_per_turn: dict[int, list[ToolCallSummary]]
  │
  ▼ (4) LLM sees tool execution context alongside conversation
MemoryAtom with activity_type=TOOL_EXECUTED, richer participants/topics
```

**New dataclass** (lives in `k1/concierge/tools/dispatcher.py`):

```python
@dataclass(frozen=True)
class ToolCallSummary:
    """Lightweight summary of a tool dispatch for persistence."""
    tool_name: str           # e.g. "plans", "search_restaurants", "book_hotel"
    arguments_summary: str   # truncated/redacted arg string (≤200 chars)
    status: str              # "success" | "error" | "timeout"
    result_preview: str      # first ~200 chars of result
    timestamp_ms: int
    duration_ms: int         # how long the tool call took
```

**Changes required** (prerequisite work — E-MW-P.1):

| Component | Change |
|-----------|--------|
| `ToolDispatcher` | Add `get_call_summaries() -> list[ToolCallSummary]` — builds from `call_history` |
| `TaskComplete` | Add `tool_call_summaries: list[dict]` field (serializable, replaces int-only `tool_calls`) |
| `BackHandler` | When building `TaskComplete`, call `dispatcher.get_call_summaries()` |
| `HistoryWriter` | When writing `Turn`, stash summaries in `TypedHistoryEntry.metadata["tool_calls"]` |

**Why this works:**

- Zero new SS sections — tool calls travel with turns in existing `history_active`
- `ToolDispatcher.call_history` already has everything — just need to extract before disposal
- `TypedHistoryEntry.metadata` is a free-form `Dict[str, Any]` — no schema change needed
- MW reads history like normal — just looks for `metadata["tool_calls"]` on each entry
- RelevanceFilter R6 uses `has_tool_calls` as a pass-through override ("this turn is likely memorable")

**Example: "Make me a gym plan"**

```python
# What DispatchRecord has (dies after ReAct loop):
DispatchRecord(
    tool_name="plans",
    arguments={"type": "gym", "duration": "4_weeks", "goal": "strength"},
    result=ToolResult(status="success", data={"plan": [...]}),
    timestamp_ms=1712400000000,
    iteration=1,
)

# What ToolCallSummary preserves:
ToolCallSummary(
    tool_name="plans",
    arguments_summary='{"type": "gym", "duration": "4_weeks", "goal": "strength"}',
    status="success",
    result_preview="4-week strength training plan: Week 1: Full body 3x...",
    timestamp_ms=1712400000000,
    duration_ms=1200,
)

# What MW sees in Turn.sub_entries[i].metadata:
{"tool_calls": [{"tool_name": "plans", "arguments_summary": "...", "status": "success", ...}]}

# What LLM extraction produces:
MemoryAtom(
    text="User requested a 4-week strength-focused gym plan. Plan was generated successfully.",
    activity_type="PLANNING",
    topics=["fitness", "gym", "strength_training"],
    participants=["user"],
    novelty=0.8,  # first gym plan request
    ...
)
```

### Output: Memory Atoms → K0

```
MemoryAtom (37 fields, 12 cognitive dimensions)
  ├── Core: text (≤50 words), participants, topics, activity_type
  ├── Affect: sentiment_label, affect (VAD), emotion_tags
  ├── Cognitive: novelty, elaboration_depth, temporal_orientation
  ├── Social: social_intimacy, social_context, relationship_type
  ├── Identity: identity_domains (multi-select)
  ├── Temporal: temporal_links (0-5 links, typed), conversation_anchor_ms
  ├── Spatial: location_name, location_type, place_id
  ├── Narrative: arc_position, source_type
  ├── Correction (v2.2): correction_signal, contradiction_signal,
  │   supersedes_concept, correction_source, session_context_id
  └── Meta: confidence, turn_id, trace_id
      │
      ▼ (Stage 4: Envelope Builder)
MWEnvelope → IBridgeCommandPort.submit_batch()
      │
      ▼ (Bridge signs Ed25519, POST)
K0 Gate → WAL → P02 → st_hipp_events
```

### Processing: How Extraction Should Actually Work

```
TRIGGER: turn.complete.v1 arrives
  │
  ▼
STAGE 1: Quick Filter (rule-based, 0 LLM cost, <2ms)
  │  R1: Is this a clarification?        → SKIP
  │  R2: Is this system/meta message?    → SKIP
  │  R3: Same turn_id already seen?      → SKIP
  │  R6: Has metadata["tool_calls"]?     → auto-PASS (skip R4/R5)
  │  R4: Trivial (<5 words, no entities)? → SKIP
  │  R5: Pure continuation of prev turn? → SKIP
  │
  │  If SKIP: record FilterDecision, done. No LLM cost.
  │  If PASS: proceed to Stage 2 (every passed turn gets full context)
  │
  ▼
STAGE 2: Context Assembly — Read FULL SS snapshot (section-agnostic, <1ms)
  │
  │  Every turn that passes the filter gets a full SessionState snapshot.
  │  No accumulation, no gating — the LLM sees the FULL conversation
  │  context that SS already maintains (last 10-25 turns in history_active,
  │  all beliefs, affect, scoreboard, narrative arc, etc.).
  │  SS IS the accumulator — it already holds the conversation window.
  │
  │  snapshot = await port.snapshot_all()
  │  # Returns dict of ALL sections — MW doesn't know or care about names
  │  # history_active gives us last 10-25 turns with full text
  │  # beliefs_active/history give facts
  │  # affective_now gives emotion context
  │  # scoreboard gives discourse state
  │  # narrative_active gives conversation arc
  │  # meta gives session_id, privacy_band
  │
  │  Build ExtractionContext:
  │    - conversation_window: last N turns from history_active (full text)
  │    - accumulated_entities: merged from all turns in window
  │    - emotion_trajectory: from affective_now.recent_emotions
  │    - active_facts: from beliefs_active + beliefs_history
  │    - discourse_state: from scoreboard (referents, topics, commitments)
  │    - arc_position: from narrative_active
  │    - privacy_band: from meta
  │    - temporal/spatial: from context_assembly.py helpers
  │    - tool_calls_per_turn: from Turn.sub_entries[i].metadata["tool_calls"]
  │
  ▼
STAGE 4: LLM Extraction (200-500ms, 2000 token budget)
  │
  │  WriterAgent sends ExtractionContext to LLM.
  │  LLM sees MULTIPLE turns in context → extracts 0-6 MemoryAtoms.
  │  Because LLM sees the conversation ARC, it can:
  │    - Identify the key facts across multiple turns (not just one)
  │    - Detect corrections/contradictions across turns
  │    - Understand narrative progression (not just isolated statements)
  │    - Skip redundant information (turn 3 + turn 4 = one atom, not two)
  │
  │  ExtractionValidator: MW-04 (≤50 words), MW-05 (≤6 atoms),
  │  MW-12 (temporal_links), confidence floor, privacy band
  │
  ▼
STAGE 5: Envelope Build (deterministic, <2ms)
  │  MemoryAtom → MWEnvelope (34-field mapping)
  │  Privacy enforcement (GREEN/AMBER/RED band stripping)
  │  trace_id injection
  │
  ▼
STAGE 6: Batch Submit (250ms window)
  │  DeltaAggregator: dedup, causal ordering
  │  BatchEmitter → IBridgeCommandPort.submit_batch()
  │  Fire-and-forget → Bridge → K0
```

### Example: Why Full SS Snapshot Per-Turn Works

```
=== Naive Per-Turn with Minimal Context (BAD) ===

Turn 3: "We went to Olive Garden yesterday"
  → LLM sees ONLY turn 3 → Atom: "Family went to Olive Garden" (missing: who? how was it?)
Turn 4: "Mom really loved the breadsticks"
  → LLM sees ONLY turn 4 → Atom: "Mom enjoyed breadsticks" (missing: where? no restaurant context)
Turn 5: "Dad wasn't feeling great though, might be the pasta"
  → LLM sees ONLY turn 5 → Atom: "Dad felt unwell from pasta" (misses everything else)

Result: 3 LLM calls with no context, 3 fragmentary overlapping atoms.

=== Full SS Snapshot Per-Turn (OUR DESIGN) ===

Turn 3: filter → PASS (entity: Olive Garden)
  → Read full SS snapshot (history_active has turns 1-3, beliefs, scoreboard, etc.)
  → LLM sees entire conversation → Atom: "Family went to Olive Garden yesterday"
Turn 4: filter → PASS (entity: Mom)
  → Read full SS snapshot (history_active now has turns 1-4)
  → LLM sees turns 1-4 + prior atoms → Atom: "Family dinner at Olive Garden.
     Mom loved the breadsticks." (subsumes turn 3 atom — extraction validator handles overlap)
Turn 5: filter → PASS (entity: Dad)
  → Read full SS snapshot (history_active now has turns 1-5)
  → LLM sees turns 1-5 + prior atoms → Atom: "Dinner at Olive Garden. Mom loved breadsticks.
     Dad felt unwell, possibly from pasta."
     participants: [person_mom, person_dad]
     activity_type: DINING
     sentiment_label: mixed

Result: 3 LLM calls but each with FULL context. Later atoms subsume earlier ones.
ExtractionValidator deduplicates overlapping atoms (Phase 2 concern).
SessionState IS the accumulator — history_active grows with each turn.
```

---

## 5. K0 Output Contract — What P02 + P03 + URE Require From MW

> **Sources:** `k0/contracts/pipelines/p02_write.v2.yaml`, `k0/runtime/ultrabert_adapter.py`,
> `docs/pipelines/UNIVERSAL_RECONCILIATION_ENGINE.md`, `architecture_diagrams/k0/p03_file_dependencies.mmd`,
> `docs/pipelines/p03/stage5_refinement_proposal.md`, UltraBERT README (`d:\Modeling_studio\README.md`)

### 5.1 Trust-Then-Fill Architecture (P02 v2)

K0's P02 write pipeline uses a **trust-then-fill** architecture with dual-path latency:

| Path | When | Latency | Behavior |
|------|------|---------|----------|
| **FAST PATH** | MW signals present (~85%) | ~80ms | Validate + passthrough MW fields; safety heads only |
| **FALLBACK PATH** | MW signals absent (~15%) | ~140ms | Full UltraBERT inference (same as P02 v1, no regression) |

**Key insight:** MW does NOT need perfect recall. P02 always produces complete output. When MW
provides good data (~85%), P02 saves ~60ms per event. When MW is bad or missing, P02 falls
back to full UltraBERT — no regression from v1.

### 5.2 UltraBERT: The 12-Head Safety Net (149M params, 20ms)

UltraBERT v4 is a 149M-param ModernBERT-base multi-task encoder running **12 NLP tasks in a
single 20ms forward pass**. It is the ultimate backstop — what MW misses, UltraBERT catches.

| # | Capability | Type | What It Catches If MW Misses |
|---|-----------|------|------|
| 1 | `ner_general` | Span (4 entities) | PERSON, ORG, LOC, DATE extraction |
| 2 | `ner_family` | Span (10 entities) | KINSHIP, FAMILY_EVENT, kinship patterns |
| 3 | `sentiment` | 5-class | Sentiment label + confidence score |
| 4 | `emotions` | 44 multi-label | Emotion tags with intensity scores |
| 5 | `safety_familyos` | 4-band | GREEN/AMBER/RED/CRISIS safety classification |
| 6 | `safety_generic` | Multi-label | Toxicity detection (8 types) |
| 7 | `nli` | 3-class | Natural language inference |
| 8 | `embedding` | 768-dim vector | L2-normalized embeddings for pgvector ANN |
| 9 | `temporal` | Span (6 time types) | DATE_REL, TIME_REL temporal expressions |
| 10 | `relation` | 15 types | parent_of, spouse_of, caretaker_of etc. |
| 11 | `intent` | 8 classes | User intent classification |
| 12 | `ingress` | 12 domains | Message routing category |

**FCCS (holistic coherence): 89.12%** — cross-head consistency ensuring sentiment-emotion
alignment, entity grounding, safety-emotion coupling, temporal completeness.

### 5.3 P02 Trust-Then-Fill Per Stage

6 of 16 P02 stages use trust-then-fill. The remaining 10 are MW-independent:

| P02 Stage | MW Field Used | Fast Path | Fallback Path |
|-----------|---------------|-----------|---------------|
| **M02 (stage_20)** | *Always runs* | Full UltraBERT NER + embedding (150ms) | Same — primary gap-filler |
| **M04 (stage_30)** | `body.affect` | Passthrough VAD, safety only (10ms) | Full UltraBERT sentiment+emotions+safety (70ms) |
| **M07 (stage_32)** | `body.participant_relationships` | Map relationships + write st_kg_edges (3ms) | st_kg_edges READ + NER PER + heuristics (12ms) |
| **M08 (stage_33)** | `body.temporal` | Use MW resolved_epoch_ms (4ms) | NER temporal + event_time + envelope.ts chain (6ms) |
| **M06 (stage_55)** | Cross-validation only | Correct social inputs → proper salience (5ms) | Same formula, whatever upstream produced (5ms) |
| **M13 (stage_60)** | Group 12 (11 MW cols) | All 12 column groups populated (10ms) | Group 12 gets migration defaults (NULL/{}/ []) (10ms) |

**M02 is the primary gap-filler:** It always runs full UltraBERT regardless of MW signal
presence. All other stages can fall back to M02's NER/embedding output.

### 5.4 What P02 Validates (UltraBERT vs MW)

| Field | MW Produces | UltraBERT Validates | On Mismatch |
|-------|-------------|---------------------|-------------|
| `sentiment_label` | 5-class from LLM | 5-class head confirms/corrects | **UltraBERT wins** |
| `emotion_tags` | From LLM prompt | 44-class head enriches | **Union of both** |
| `participants` | Natural names resolved | ner_family kinship check | Flag unresolved |
| `topics` | From LLM prompt | Ingress head validates | May adjust |
| `activity_type` | From LLM prompt | Intent head confirms | **UltraBERT wins** |
| `location_name` | From LLM prompt | ner_general LOC extraction | Confirm/extract |
| `temporal` | LLM temporal_links | Temporal head span extraction | **Merged** |
| `relations` | participant_relationships | Relation head (15 types) | **UltraBERT enriches** |

**Design consequence for MW:** MW should focus on what LLMs are uniquely good at —
understanding conversation context, detecting corrections/contradictions, resolving temporal
references across turns, and narrative arc reasoning. UltraBERT handles the mechanical NLU
tasks (NER, sentiment, safety) as a safety net. **MW does NOT need to be perfect at NER
or sentiment classification** — UltraBERT will catch and correct.

### 5.5 Mandatory Fields K0 Requires Per Event (st_hipp_events)

These are the fields P03 + URE expect. MW produces them in the envelope body;
P02 validates/enriches before writing to st_hipp_events.

| Category | Field | Type | Required For | MW Source |
|----------|-------|------|--------------|-----------|
| **Content** | `text` | str (≤50 words, MW-04) | Consolidation | LLM extraction |
| **Temporal** | `event_time_utc` | ISO 8601 | P03 R0 batch loading | Envelope builder (turn timestamp) |
| **Temporal** | `conversation_anchor_ms` | int | Gold-standard time (MW-13) | Turn.timestamp_ms (NEVER overwritten) |
| **Temporal** | `time_of_day_bucket` | MORNING/AFTERNOON/EVENING/NIGHT | R5 ASU anchor derivation, st_observations | context_assembly.py |
| **Temporal** | `circadian_slot` | enum | st_observations | context_assembly.py |
| **Temporal** | `is_weekend` | bool | st_observations | context_assembly.py |
| **Temporal** | `temporal_links` | array (max 5) | Multi-temporal resolution | LLM extraction |
| **Emotional** | `sentiment_label` | 5-class enum | P02 M04, st_observations | LLM extraction (UltraBERT validates) |
| **Emotional** | `sentiment_score` | float -1.0 to 1.0 | SRE social enrichment | **NEW**: Derive from 5-class label |
| **Emotional** | `affect` | {valence, arousal, dominance} | P02 M04 trust-then-fill | LLM extraction |
| **Emotional** | `dominant_emotion` | enum from 44-class | SRE, st_observations | **NEW**: Map from emotion_tags[0] |
| **Emotional** | `dominant_emotions_json` | JSON objects | M9.4 reconciliation | **NEW**: Reshape from emotion_tags |
| **Spatial** | `location_name` | str (band-stripped) | P02 M08, privacy | LLM extraction |
| **Spatial** | `location_type` | 12-value enum | Location reconciliation | LLM extraction |
| **Spatial** | `geohash_6` | 6-char str | st_observations, proximity | **NEW**: Compute in PlaceResolver |
| **Physical** | `place_id` | str (geohash) | Location reconciliation | **NEW**: Compute in PlaceResolver |
| **Social** | `social_context` | SOLO/FAMILY/FRIENDS/WORK/PUBLIC | Reconciliation identity | LLM extraction |
| **Social** | `num_participants` | int | st_observations | Derive from participants count |
| **Social** | `participants` | person_id[] | P02 M07 social resolve | PersonResolver (natural→ID) |
| **Social** | `participant_relationships` | [{type, target, confidence}] | P02 M07 trust-then-fill, st_kg_edges | LLM extraction |
| **NER** | `ner_entities_json` | [{entity, type, salience, confidence}] | R4 KG extraction | **NEW**: LLM extracts OR UltraBERT fallback |
| **K1 Signal** | `correction_signal` | bool | **M9.4 Tier 1 EVOLVE** | LLM detection |
| **K1 Signal** | `contradiction_signal` | bool | **M9.4 Tier 1 CONTRADICT** | LLM detection |
| **K1 Signal** | `supersedes_concept` | str "domain:value" | M9.4 EVOLVE target | LLM detection |
| **K1 Signal** | `correction_source` | enum | st_observations audit | LLM detection |
| **K1 Signal** | `session_context_id` | str | Audit trail | session_id from meta |
| **Metadata** | `ingress_channel` | CHAT/VOICE/API/SYSTEM | Reconciliation identity | Session meta |
| **Metadata** | `device_kind` | PHONE/TABLET/DESKTOP/WATCH | st_observations | Session meta |

### 5.6 K1 Correction Signals — Tier 1 Overrides (THE Most Critical Contract)

K0's URE (M9.4 ReconciliationFramework) implements a tiered decision system.
**K1 correction signals are Tier 1 — they override ALL similarity-based matching.**

```
IF correction_signal == True:
    → R3 IMMEDIATELY returns EVOLVE
    → Old truth record status → SUPERSEDED
    → New truth record created
    → No similarity check. No identity check. No threshold.
    → User's explicit correction is LAW.

IF contradiction_signal == True:
    → R3 IMMEDIATELY returns CONTRADICT
    → INSERT to st_learning_queue (NOT truth layers)
    → P06 active learning pipeline reviews and resolves
    → Truth NOT modified automatically
```

**Why only K1 can detect these:** K0's embedding distance (cosine) has a similarity floor
of ~0.92 for family-diary data. "I prefer Italian food" and "Actually, I prefer Thai food now"
are cosine-similar (same topic, same entities). Only K1's LLM with full conversation context
can detect that the second statement **corrects** the first.

**MW must set these signals accurately.** False positives cause incorrect truth evolution.
False negatives allow contradictions to persist in truth layers.

### 5.7 The Observation Context Loop

K0's 14 new observation-driven algorithms (replacing CPN + TPN-MCTS) read `st_observations`
(32-column append-only table). This creates a reinforcement loop:

```
Cycle N:
  MW submits event with all observation context fields
  → P02 writes to st_hipp_events
  → P03 R7 commits to truth layer + calls ObservationRecorder.record_for_merge()
  → INSERT st_observations: observation_type='REINFORCEMENT', all 32 columns

Cycle N+1:
  → R5 algorithms read st_observations
  → Episodes with high REINFORCEMENT count get salience boost
  → st_observations feeds ASU anchor derivation, SRE sentiment, etc.
  → Loop closes: More evidence → Stronger updates
```

**MW must provide ALL 32 observation context fields per event for this loop to work.**
Missing fields break downstream algorithms. Key fields grouped by source:

| Group | Fields | MW Source |
|-------|--------|-----------|
| Temporal | time_of_day_bucket, circadian_slot, is_weekend, day_of_week | context_assembly.py (exists ✅) |
| Emotional | sentiment_score, sentiment_label, dominant_emotion, affect_valence | LLM + field mapping (needs work ⚠️) |
| Spatial | location_name, geohash_6, place_id | LLM + PlaceResolver (needs geohash ⚠️) |
| Social | social_context, num_participants | LLM (exists ✅) |
| Metadata | ingress_channel, device_kind | Session meta (exists ✅) |
| K1 Signals | correction_signal, contradiction_signal, supersedes_concept, correction_source | LLM detection (exists ✅) |

### 5.8 Reconciliation Thresholds (Set by K0, Informed by MW Quality)

When MW provides an event, P03 R3 calls M9.4 ReconciliationFramework.decide():

1. **Check K1 signals** → correction/contradiction override ALL (Tier 1)
2. **Fetch candidates** via pgvector ANN (top-10 by cosine on 768-dim)
3. **Filter by identity** (EpisodicIdentity: 11 features, logistic model)
4. **Rank by similarity** (cosine on embeddings)
5. **Apply per-layer thresholds:**

| Truth Layer | REINFORCE | EXTEND | EVOLVE | CREATE |
|-------------|-----------|--------|--------|--------|
| st_epi | ≥0.85 | 0.60–0.85 | 0.40–0.60 | <0.40 |
| st_kg_dom | Exact entity match = 1.0 | — | — | No match |
| st_social | Per-layer config | — | — | — |

MW's embedding_text is set to null — K0 computes embeddings via UltraBERT (768-dim, L2-normalized).

### 5.9 Gaps Identified — MW Fields That Need Work

| # | Gap | Current State | Required State | Fix Phase |
|---|-----|---------------|----------------|-----------|
| G1 | `sentiment_score` missing | MW produces 5-class label only | Need float -1.0 to 1.0 | Phase 3 (FieldMapper) |
| G2 | `dominant_emotion` missing | MW produces `emotion_tags: string[]` | Need single enum from 44-class | Phase 3 (FieldMapper) |
| G3 | `dominant_emotions_json` shape | MW produces flat string array | Need JSON objects with confidence | Phase 3 (FieldMapper) |
| G4 | `affect_valence` flat field | MW bundles in `affect{V,A,D}` object | K0 expects flat `affect_valence` too | Phase 3 (FieldMapper) |
| G5 | `geohash_6` missing | PlaceResolver has O(1) exact + O(n) prefix | Need geohash computation | Phase 0 (PlaceResolver) |
| G6 | `place_id` missing | Not computed | Derive from geohash or location | Phase 0 (PlaceResolver) |
| G7 | `ner_entities_json` | LLM prompt doesn't extract NER | Need [{entity, type, salience}] | Phase 2 (LLM prompt) **OR** let UltraBERT handle entirely |
| G8 | `num_participants` | Not explicitly set | Derive from `len(participants)` | Phase 3 (FieldMapper) |
| G9 | `is_duplicate` flag | Not used | MW can set for high-confidence dedup | Phase 3 (DeltaAggregator) |

**Design decision on G7 (NER):** MW's LLM is optimized for conversation-context reasoning.
NER is a mechanical extraction task that UltraBERT handles with **95.2% F1 (general)** and
**80.0% F1 (family)**. MW should NOT attempt NER extraction in the LLM prompt — let
UltraBERT in P02 M02 handle it. MW can optionally pass NER hints from entities already
in SessionState turns, but the authoritative NER is UltraBERT's.

**Design decision on G1–G4, G8 (field reshaping):** These are pure field mapping transforms.
The data exists in MW's MemoryAtom — it just needs reshaping in the FieldMapper:

```python
# G1: sentiment_score from sentiment_label
SENTIMENT_TO_SCORE = {
    "very_negative": -0.9, "negative": -0.5, "neutral": 0.0,
    "positive": 0.5, "very_positive": 0.9
}

# G2: dominant_emotion from emotion_tags[0]
dominant_emotion = atom.emotion_tags[0] if atom.emotion_tags else "neutral"

# G3: dominant_emotions_json from emotion_tags
dominant_emotions_json = [{"emotion": e, "confidence": 0.8} for e in atom.emotion_tags[:5]]

# G4: affect_valence from affect.valence
affect_valence = atom.affect.valence if atom.affect else 0.0

# G8: num_participants from len(participants)
num_participants = len(atom.participants) if atom.participants else 0
```

### 5.10 End-to-End Latency Budget (MW → K0 → st_hipp_events)

| Segment | Duration | Notes |
|---------|----------|-------|
| MW pipeline (6-stage) | ~815ms P95 | Filter + accumulate + context + LLM + envelope + batch |
| Bridge transport | ~50ms | Ed25519 sign + HTTP POST |
| K0 hot path (Gate → WAL) | ~93ms | Signature verify + schema validate + 3-table atomic write |
| K0 P02 background (FAST) | ~80ms | When MW signals present |
| K0 P02 background (FALLBACK) | ~140ms | When MW signals absent/bad |
| **TOTAL (fast)** | **~1038ms** | |
| **TOTAL (fallback)** | **~1098ms** | No regression from v1 |

---

## 6. Implementation Phases

```
Phase P ─ Prerequisite: Tool Call Data   [1 epic, ~1 session]
  └── ToolCallSummary DC, ToolDispatcher.get_call_summaries(), TaskComplete enrichment,
      HistoryWriter annotation — enables MW to see tool execution context

Phase 0 ─ Foundation Fixes              [3 epics, ~1 session]
  └── __init__.py exports, ARCHITECTURE.md corrections, section-agnostic reading

Phase 1 ─ Filter + Context Assembly      [4 epics, ~2 sessions]
  └── RelevanceFilter, MWSessionReader, ContextBuilder (section-agnostic), PersonResolver

Phase 2 ─ LLM Extraction               [3 epics, ~2 sessions]
  └── WriterAgent (window-based), ExtractionValidator, persona prompt

Phase 3 ─ Envelope + Batch + Bridge     [4 epics, ~2 sessions]
  └── EnvelopeBuilder, FieldMapper, PrivacyEnforcer, DeltaAggregator, BatchEmitter

Phase 4 ─ Pipeline + Service            [3 epics, ~2 sessions]
  └── MemoryWriterPipeline (6-stage), TurnDispatcher, MemoryWriterFactory, lifecycle

Phase 5 ─ Adapters + Integration        [3 epics, ~1 session]
  └── 3 remaining adapters, test adapters, Fabric wiring
```

---

## 7. Phase P — Prerequisite: Tool Call Data Pipeline

**Rationale:** Tool calls are rich episodic memory sources (gym plans, restaurant searches,
vacation bookings). The data already exists in `ToolDispatcher.call_history` but is discarded
after the ReAct loop ends. This phase makes tool call data survive into `history_active`
turns where MW can read it. This is Concierge-side work — not MW code.

### E-MW-P.1: Tool Call Summary Extraction + Turn Annotation

**Modules touched:** `k1/concierge/tools/dispatcher.py`, `k1/concierge/task/dispatch.py`,
Concierge back_handler, HistoryWriter

| Item | File | Work |
|------|------|------|
| I-MW-P.1.1 | `k1/concierge/tools/dispatcher.py` | Add frozen `ToolCallSummary` DC (tool_name, arguments_summary ≤200 chars, status, result_preview ≤200 chars, timestamp_ms, duration_ms). Add `ToolDispatcher.get_call_summaries() -> list[ToolCallSummary]` — iterates `self.call_history`, truncates args/result, returns lightweight summaries |
| I-MW-P.1.2 | `k1/concierge/task/dispatch.py` | Add `tool_call_summaries: list[dict] = field(default_factory=list)` to `TaskComplete`. Update `to_dict()` / `from_dict()` to serialize/deserialize. Keep `tool_calls: int` for backward compat |
| I-MW-P.1.3 | Concierge back_handler | When building `TaskComplete` from `ReactResult`, call `dispatcher.get_call_summaries()` and populate `TaskComplete.tool_call_summaries` |
| I-MW-P.1.4 | HistoryWriter (or FrontHandler) | When writing `TypedHistoryEntry` for a turn that completed a task, copy `TaskComplete.tool_call_summaries` into `entry.metadata["tool_calls"]` |
| I-MW-P.1.5 | `tests/k1/concierge/test_tool_call_summary.py` | Tests: `ToolCallSummary` construction, truncation at 200 chars, `get_call_summaries()` with 0/1/N calls, `TaskComplete` serialization round-trip, `TypedHistoryEntry.metadata["tool_calls"]` populated |

**Truncation rules:**

- `arguments_summary`: JSON-serialize args dict, truncate to 200 chars. Redact any field
  containing "password", "token", "secret", "key" (replace value with "***")
- `result_preview`: stringify result.data, take first 200 chars
- If tool returned error: `status="error"`, `result_preview` = error message (≤200 chars)

**Backward compatibility:**

- `TaskComplete.tool_calls` (int) remains for budget tracking
- `tool_call_summaries` defaults to empty list — old code unaffected
- `TypedHistoryEntry.metadata` is free-form dict — no schema migration needed

---

## 8. Phase 0 — Foundation Fixes

### E-MW-0.1: Populate `__init__.py` Exports

**Problem:** `module.contract.yaml` lists 25 exported symbols from `k1/memory_writer/__init__.py`.
The file is completely empty (0 bytes). Any `from k1.memory_writer import MemoryAtom` fails with
`ImportError`. This blocks every downstream consumer including Fabric's MemoryWriterFactory.

**Actual inventory of exportable symbols (verified via code read):**

| Category | Symbol | Source Module | Exists? |
|----------|--------|---------------|---------|
| **Ports (5)** | `ISessionReadPort` | `ports.session_read_port` | ✅ |
| | `IBridgeCommandPort` | `ports.bridge_command_port` | ✅ |
| | `IEventSubscriptionPort` | `ports.event_subscription_port` | ✅ |
| | `IModelHubPort` | `ports.model_hub_port` | ✅ |
| | `IHealthPort` | `ports.health_port` | ✅ |
| **Core Types (9)** | `MemoryAtom` | `types` | ✅ (37-field frozen DC) |
| | `ExtractionContext` | `types` | ✅ (25+ field frozen DC) |
| | `CompressedTurn` | `types` | ✅ |
| | `FilterDecision` | `types` | ✅ |
| | `PersonResolution` | `types` | ✅ |
| | `MWEnvelope` | `types` | ✅ |
| | `HealthStatus` | `types` | ✅ |
| | `ChatResponse` | `types` | ✅ |
| | `Subscription` | `types` | ✅ |
| **Config (1)** | `MWConfig` | `config` | ✅ |
| **Nested VOs (5)** | `Affect` | `types` | ✅ |
| | `ParticipantRelationship` | `types` | ✅ |
| | `Narrative` | `types` | ✅ |
| | `Temporal` | `types` | ✅ |
| | `TemporalLink` | `types` | ✅ |
| **Enums (15)** | `SentimentLabel` | `types` | ✅ |
| | `NoveltyLevel` | `types` | ✅ |
| | `ElaborationDepth` | `types` | ✅ |
| | `TemporalOrientation` | `types` | ✅ |
| | `TemporalLinkType` | `types` | ✅ |
| | `SourceType` | `types` | ✅ |
| | `ArcPosition` | `types` | ✅ |
| | `SocialIntimacy` | `types` | ✅ |
| | `ActivityType` | `types` | ✅ (20 values) |
| | `RelationshipType` | `types` | ✅ (8 values) |
| | `LocationType` | `types` | ✅ (12 values) |
| | `IdentityDomain` | `types` | ✅ (9 values) |
| | `SkipReason` | `types` | ✅ (5 values) |
| | `IntentType` | `types` | ✅ (8 values) |
| | `SocialContext` | `types` | ✅ (6 values) |
| **Events (6 topics)** | `TOPIC_TURN_COMPLETE` | `events` | ✅ |
| | `TOPIC_FILTER_DECISION` | `events` | ✅ |
| | `TOPIC_EXTRACTION_COMPLETE` | `events` | ✅ |
| | `TOPIC_BATCH_SUBMITTED` | `events` | ✅ |
| | `TOPIC_PIPELINE_ERROR` | `events` | ✅ |
| | `TOPIC_CIRCUIT_OPEN` | `events` | ✅ |
| **Event Payloads (6)** | `TurnCompletePayload` | `events` | ✅ |
| | `FilterDecisionEvent` | `events` | ✅ |
| | `ExtractionCompleteEvent` | `events` | ✅ |
| | `BatchSubmittedEvent` | `events` | ✅ |
| | `PipelineErrorEvent` | `events` | ✅ |
| | `CircuitOpenEvent` | `events` | ✅ |
| **Invariants (1)** | `InvariantViolation` | `invariants` | ✅ |
| **Context (2)** | `PlaceResolver` | `place_resolver` | ✅ |
| | `ResolvedPlace` | `place_resolver` | ✅ |
| **Adapters (2)** | `SessionReadAdapter` | `adapters.session_read_adapter` | ✅ |
| | `ModelHubAdapter` | `adapters.model_hub_adapter` | ✅ |
| **Not-yet-implemented** | `MemoryWriterPipeline` | — | ❌ Phase 4 |
| | `RelevanceFilter` | — | ❌ Phase 1 |
| | `ContextBuilder` | — | ❌ Phase 1 |
| | `ExtractionValidator` | — | ❌ Phase 2 |
| | `EnvelopeBuilder` | — | ❌ Phase 3 |
| | `DeltaAggregator` | — | ❌ Phase 3 |
| | `BatchEmitter` | — | ❌ Phase 3 |
| | `PersonResolver` | — | ❌ Phase 1 |
| | `PrivacyEnforcer` | — | ❌ Phase 3 |

**Total: 46 symbols exist now. 9 service symbols will be added in Phases 1-4.**

**Deliverable:**

| Item | File | Work |
|------|------|------|
| I-MW-0.1.1 | `k1/memory_writer/__init__.py` | Add re-exports for ALL existing symbols organized by category: 5 ports (from `ports`), 15 enums (from `types`), 9 core types + 5 nested VOs (from `types`), 1 config (from `config`), 6 topic constants + 6 event payloads (from `events`), 1 exception (from `invariants`), 2 context helpers (from `place_resolver`), 2 adapters (from `adapters`). Use explicit `__all__` list matching module.contract.yaml symbols. Add `# Phase N: will add X` comments for not-yet-implemented symbols so the file is ready for incremental growth |
| I-MW-0.1.2 | `tests/k1/memory_writer/test_init_exports.py` | New test file: (a) Import every symbol from `k1.memory_writer` — confirms no `ImportError`. (b) Compare `k1.memory_writer.__all__` against module.contract.yaml exports list — confirms contract compliance. (c) Verify each enum has expected member count (SentimentLabel=5, ActivityType=20, LocationType=12, etc.). (d) Verify MemoryAtom has exactly 37 fields. (e) Verify MWConfig defaults match policies.contract.yaml (llm_token_budget=2000, batch_window_ms=250, max_atoms_per_turn=6, max_text_words=50). ~15 tests |

**Implementation detail for `__init__.py`:**

```python
# k1/memory_writer/__init__.py
"""K1 Memory Writer v2 — Episodic Memory Formation.

Exports all public symbols as declared in module.contract.yaml.
"""

# --- Ports (5) ---
from k1.memory_writer.ports import (
    IBridgeCommandPort,
    IEventSubscriptionPort,
    IHealthPort,
    IModelHubPort,
    ISessionReadPort,
)

# --- Core types (9) ---
from k1.memory_writer.types import (
    ChatResponse,
    CompressedTurn,
    ExtractionContext,
    FilterDecision,
    HealthStatus,
    MemoryAtom,
    MWEnvelope,
    PersonResolution,
    Subscription,
)

# --- Nested value objects (5) ---
from k1.memory_writer.types import (
    Affect,
    Narrative,
    ParticipantRelationship,
    Temporal,
    TemporalLink,
)

# --- Enums (15) ---
from k1.memory_writer.types import (
    ActivityType,
    ArcPosition,
    ElaborationDepth,
    IdentityDomain,
    IntentType,
    LocationType,
    NoveltyLevel,
    RelationshipType,
    SentimentLabel,
    SkipReason,
    SocialContext,
    SocialIntimacy,
    SourceType,
    TemporalLinkType,
    TemporalOrientation,
)

# --- Config (1) ---
from k1.memory_writer.config import MWConfig

# --- Events (6 topics + 6 payloads) ---
from k1.memory_writer.events import (
    ALL_CONSUMED_TOPICS,
    ALL_PRODUCED_TOPICS,
    TOPIC_BATCH_SUBMITTED,
    TOPIC_CIRCUIT_OPEN,
    TOPIC_EXTRACTION_COMPLETE,
    TOPIC_FILTER_DECISION,
    TOPIC_PIPELINE_ERROR,
    TOPIC_TURN_COMPLETE,
    BatchSubmittedEvent,
    CircuitOpenEvent,
    ExtractionCompleteEvent,
    FilterDecisionEvent,
    PipelineErrorEvent,
    TurnCompletePayload,
)

# --- Invariants (1) ---
from k1.memory_writer.invariants import InvariantViolation

# --- Context helpers (2) ---
from k1.memory_writer.place_resolver import PlaceResolver, ResolvedPlace

# --- Adapters (2 existing) ---
from k1.memory_writer.adapters import ModelHubAdapter, SessionReadAdapter

# Phase 1: RelevanceFilter, ContextBuilder, PersonResolver
# Phase 2: ExtractionValidator
# Phase 3: EnvelopeBuilder, DeltaAggregator, BatchEmitter, PrivacyEnforcer
# Phase 4: MemoryWriterPipeline

__all__ = [
    # Ports
    "IBridgeCommandPort", "IEventSubscriptionPort", "IHealthPort",
    "IModelHubPort", "ISessionReadPort",
    # Core types
    "ChatResponse", "CompressedTurn", "ExtractionContext", "FilterDecision",
    "HealthStatus", "MemoryAtom", "MWEnvelope", "PersonResolution", "Subscription",
    # Nested VOs
    "Affect", "Narrative", "ParticipantRelationship", "Temporal", "TemporalLink",
    # Enums
    "ActivityType", "ArcPosition", "ElaborationDepth", "IdentityDomain",
    "IntentType", "LocationType", "NoveltyLevel", "RelationshipType",
    "SentimentLabel", "SkipReason", "SocialContext", "SocialIntimacy",
    "SourceType", "TemporalLinkType", "TemporalOrientation",
    # Config
    "MWConfig",
    # Events
    "TOPIC_TURN_COMPLETE", "TOPIC_FILTER_DECISION", "TOPIC_EXTRACTION_COMPLETE",
    "TOPIC_BATCH_SUBMITTED", "TOPIC_PIPELINE_ERROR", "TOPIC_CIRCUIT_OPEN",
    "ALL_CONSUMED_TOPICS", "ALL_PRODUCED_TOPICS",
    "TurnCompletePayload", "FilterDecisionEvent", "ExtractionCompleteEvent",
    "BatchSubmittedEvent", "PipelineErrorEvent", "CircuitOpenEvent",
    # Invariants
    "InvariantViolation",
    # Context
    "PlaceResolver", "ResolvedPlace",
    # Adapters
    "SessionReadAdapter", "ModelHubAdapter",
]
```

**Acceptance criteria:**

- `python -c "from k1.memory_writer import MemoryAtom, MWConfig, ISessionReadPort"` succeeds
- `len(k1.memory_writer.__all__) == 46` (grows as Phases 1-4 add services)
- All 25 symbols from module.contract.yaml are importable
- No circular imports (types.py → stdlib only, verified by import order)

---

### E-MW-0.2: ARCHITECTURE.md Corrections

**Problem:** `ARCHITECTURE.md` §11 claims "0 test files, 0 test functions, 0 test lines" and §10
says adapters directory "does not exist." Both are wrong — there are 7 test files with 208 tests,
and `adapters/` has 3 files (\_\_init\_\_.py, session_read_adapter.py, model_hub_adapter.py).

**Actual state (verified via code read):**

Test files (7 files, 208 test functions):

| File | Tests | What It Tests |
|------|-------|---------------|
| `test_turn_timestamp_propagation.py` | 22 | conversation_anchor_ms flow through MemoryAtom, ExtractionContext, MWEnvelope |
| `test_temporal_link.py` | 38 | TemporalLink DC, MW-12 invariant, 6 link types, uncertainty windows, 0-5 per atom |
| `test_session_read_adapter_056.py` | 28 | SessionReadAdapter snapshot/read_section, phantom sections, SectionNotFoundError |
| `test_race_condition_fix.py` | 20 | context_assembly.py resolve_mentioned_time/location, payload-first pattern, T7 race |
| `test_place_resolver.py` | 47 | PlaceResolver exact/prefix match, _to_place_id slug, ResolvedPlace DC, edge cases |
| `test_mw_invariants.py` | 27 | MW-01 through MW-13 assertion helpers, InvariantViolation exception |
| `test_model_hub_adapter_053.py` | 26 | ModelHubAdapter chat() translation, system prompt handling, budget enforcement |

Adapter files (3 files in `adapters/`):

| File | Lines | What It Does |
|------|-------|---------------|
| `adapters/__init__.py` | ~8 | Re-exports `ModelHubAdapter`, `SessionReadAdapter` |
| `adapters/session_read_adapter.py` | ~120 | `SessionReadAdapter`: wraps SSM, snapshot/read_section, phantom section handling |
| `adapters/model_hub_adapter.py` | ~100 | `ModelHubAdapter`: wraps K1 IModelHubPort, MW chat() → K1 execute(HubRequest) |

Existing files (13 of 43 planned, not 11):

| File | Lines | Content |
|------|-------|---------|
| `__init__.py` | 0 | Empty (E-MW-0.1 will fix) |
| `types.py` | ~580 | 15 enums + 14 dataclasses (MemoryAtom 37f, ExtractionContext 25f+, etc.) |
| `config.py` | ~100 | MWConfig frozen DC, 15 fields |
| `events.py` | ~140 | 6 topic constants + 6 payload DCs (TurnCompletePayload 18f) |
| `invariants.py` | ~450 | MW-01 through MW-13 assertion helpers + InvariantViolation |
| `context_assembly.py` | ~175 | Temporal/spatial resolution, payload-first pattern (T7 race fix) |
| `place_resolver.py` | ~120 | PlaceResolver + ResolvedPlace, O(1) exact + O(n) prefix |
| `ports/__init__.py` | ~35 | Re-exports all 5 port Protocols |
| `ports/session_read_port.py` | ~95 | ISessionReadPort Protocol (snapshot + read_section) |
| `ports/bridge_command_port.py` | ~80 | IBridgeCommandPort Protocol (submit + submit_batch) |
| `ports/event_subscription_port.py` | ~90 | IEventSubscriptionPort Protocol (subscribe + unsubscribe + publish) |
| `ports/model_hub_port.py` | ~60 | IModelHubPort Protocol (chat) |
| `ports/health_port.py` | ~50 | IHealthPort Protocol (is_ready + health_check) |
| `adapters/__init__.py` | ~8 | Re-exports 2 adapters |
| `adapters/session_read_adapter.py` | ~120 | SessionReadAdapter (wraps SSM) |
| `adapters/model_hub_adapter.py` | ~100 | ModelHubAdapter (wraps K1 ModelHub) |

**Total: 16 files exist (not 11). 27 files missing (63%, not 74%).**

**Deliverable:**

| Item | File | Work |
|------|------|------|
| I-MW-0.2.1 | `k1/memory_writer/ARCHITECTURE.md` §11 | Replace "0 test files / 0 test functions / 0 test lines" with table showing 7 files, 208 tests. Add per-file breakdown matching table above |
| I-MW-0.2.2 | `k1/memory_writer/ARCHITECTURE.md` §10 | Update "Files that EXIST" from 11 to 16. Add the 5 missing entries: `adapters/__init__.py`, `adapters/session_read_adapter.py`, `adapters/model_hub_adapter.py` (these 3 were listed as not existing). Update "adapters/ directory does not exist" to "3 of 6 adapter files exist". Update gap percentages: 27 files missing (63%), not 32 (74%) |
| I-MW-0.2.3 | `k1/memory_writer/ARCHITECTURE.md` §12 | Update G-2 from "Zero adapters" to "3 of 6 adapters exist (SessionRead, ModelHub, **init**)". Update G-4 from "Zero tests" to "7 test files, 208 tests — covers types, invariants, adapters, context assembly, place resolver". Update G-5 to note it's being fixed by E-MW-0.1 |
| I-MW-0.2.4 | `k1/memory_writer/ARCHITECTURE.md` §1 | Update the "What Exists vs What's Planned" table: change "Adapters" row status to "⚠️ 2 of 5 production adapters exist" and "Tests" row to "⚠️ 7 files, 208 tests (types+invariants+adapters+context)" |
| I-MW-0.2.5 | `k1/memory_writer/ARCHITECTURE.md` §9 | Update adapter status column: SessionReadAdapter → "✅ Implemented", ModelHubAdapter → "✅ Implemented", others remain ❌ |

**Acceptance criteria:**

- §11 accurately reports 7 test files, 208 tests with per-file breakdown
- §10 accurately reports 16 existing files, 27 missing (63%)
- No remaining "zero tests" or "adapters directory does not exist" claims
- All line counts ±10% of actual (verified by `wc -l`)

---

### E-MW-0.3: Make MW Section-Agnostic (Config + Port)

**Problem:** `config.py` hardcodes 13 section names in `_DEFAULT_HOT_SECTIONS` (10 items) and
`_DEFAULT_WARM_SECTIONS` (3 items). Two phantom sections are listed (`ifl`, `affective_baseline`)
that do not exist in SessionState's `ALL_SECTIONS` (verified: sizetracker.py SECTION_BUDGETS
has 15 sections, none named `ifl` or `affective_baseline`). Every new SS section added in the
future requires MW config.py code changes.

**Root cause:** `ISessionReadPort.snapshot(sections: List[str])` requires the caller to enumerate
section names. `SessionStateManager` has `ALL_SECTIONS: FrozenSet[str]` derived from
`SECTION_BUDGETS.keys()` — the authoritative section registry (15 sections: control,
beliefs_active, scoreboard, history_active, clarifications, affective_now, narrative_active,
meta, task_state, task_artifacts, beliefs_history, history_recent, persona, telemetry,
artifacts_warm).

**Current config.py state:**

```python
# Hardcoded lists (lines 22-45)
_DEFAULT_HOT_SECTIONS: List[str] = [
    "beliefs_active", "beliefs_history", "history_active", "history_recent",
    "affective_now", "affective_baseline",  # ← PHANTOM: does not exist in SS
    "narrative_active", "scoreboard", "control", "persona",
]
_DEFAULT_WARM_SECTIONS: List[str] = [
    "task_state", "ifl", "meta",  # ← "ifl" is PHANTOM: does not exist in SS
]
_SKIPPED_SECTIONS: List[str] = ["telemetry", "artifacts_warm"]

# MWConfig references them:
session_sections_hot: List[str] = field(default_factory=lambda: list(_DEFAULT_HOT_SECTIONS))
session_sections_warm: List[str] = field(default_factory=lambda: list(_DEFAULT_WARM_SECTIONS))

@property
def all_sections(self) -> List[str]:
    return self.session_sections_hot + self.session_sections_warm  # 13 total
```

**Missing from MW's lists:** `clarifications`, `task_artifacts` — both are HOT sections in SS
but MW currently ignores them. If a future section like `habits` is added to SS, MW would
also miss it.

**Solution:** Invert the model. Instead of listing sections TO READ, list sections to SKIP.
MW reads ALL sections from `ALL_SECTIONS` EXCEPT the skip list. New sections are automatically
included.

**Deliverable:**

| Item | File | Work |
|------|------|------|
| I-MW-0.3.1 | `k1/memory_writer/ports/session_read_port.py` | Add two new methods to `ISessionReadPort` Protocol: `async def list_sections() -> frozenset[str]` — returns the authoritative set of all SS section names (delegates to `ALL_SECTIONS` at the adapter level). `async def snapshot_all(exclude: frozenset[str] = frozenset()) -> Dict[str, Any]` — reads ALL sections in one call, optionally excluding named sections. Existing `snapshot(sections)` and `read_section(name)` remain unchanged for backward compatibility |
| I-MW-0.3.2 | `k1/memory_writer/adapters/session_read_adapter.py` | Implement the two new methods: `list_sections()` → imports `ALL_SECTIONS` from `k1.sessionstate.sizetracker` and returns it. `snapshot_all(exclude)` → calls `self.snapshot(list(ALL_SECTIONS - exclude))`. Import is done at method call time (lazy) to avoid circular imports at module load. Note: `ALL_SECTIONS` is a `FrozenSet[str]` at module level in sizetracker.py, already publicly exported in its `__all__` |
| I-MW-0.3.3 | `k1/memory_writer/config.py` | **Remove:** `_DEFAULT_HOT_SECTIONS`, `_DEFAULT_WARM_SECTIONS`, `_SKIPPED_SECTIONS` module-level lists. **Remove:** `session_sections_hot`, `session_sections_warm` fields from `MWConfig`. **Remove:** `all_sections` property. **Add:** `skip_sections: frozenset[str] = frozenset({"telemetry", "artifacts_warm"})` — sections to EXCLUDE from snapshot. MW reads everything else. **Add:** `phantom_sections: frozenset[str] = frozenset({"affective_baseline", "ifl"})` — documented phantom sections that config.py previously listed but do not exist in SS. Kept as documentation only, not used at runtime |
| I-MW-0.3.4 | `tests/k1/memory_writer/test_section_agnostic.py` | New test file (~20 tests): (a) `test_snapshot_all_returns_all_except_skipped` — mock SSM with 15 sections, call `snapshot_all(exclude={"telemetry","artifacts_warm"})`, verify 13 sections returned. (b) `test_list_sections_returns_frozen_set` — verify `list_sections()` returns a `frozenset` matching `ALL_SECTIONS`. (c) `test_new_section_automatically_included` — add "habits" to mock SSM, verify `snapshot_all()` includes it without config changes. (d) `test_phantom_sections_gracefully_skipped` — call `snapshot(["affective_baseline","ifl"])`, verify empty dict returned (no crash). (e) `test_skip_sections_config_default` — verify `MWConfig().skip_sections == frozenset({"telemetry","artifacts_warm"})`. (f) `test_backward_compat_snapshot_still_works` — verify existing `snapshot(["beliefs_active"])` method still works identically. (g) `test_snapshot_all_exclude_override` — verify custom exclude set works |
| I-MW-0.3.5 | `k1/memory_writer/ARCHITECTURE.md` §2 | Update ISessionReadPort table: add `list_sections` and `snapshot_all` methods. Update §5 config table: replace `session_sections_hot`/`session_sections_warm` with `skip_sections`. Note phantom section cleanup |

**Migration note:** The `snapshot(sections: List[str])` method remains on the port for targeted
reads (PersonResolver reads only `beliefs_active`). Pipeline code (ContextBuilder in Phase 1)
will use `snapshot_all(exclude=config.skip_sections)` exclusively.

**Acceptance criteria:**

- `config.py` has zero hardcoded section name lists
- `SessionReadAdapter.snapshot_all(exclude={"telemetry","artifacts_warm"})` returns 13 of 15 sections
- Adding a section to `SECTION_BUDGETS` in sizetracker.py → MW automatically reads it
- Phantom sections (`affective_baseline`, `ifl`) cause no errors (graceful skip)
- All existing 28 tests in `test_session_read_adapter_056.py` still pass (backward compat)

---

### E-MW-0.4: PlaceResolver Geohash + Place ID (K0 Gaps G5/G6)

**Problem:** K0 st_observations requires `geohash_6` (6-char geohash string) and `place_id` for
spatial reconciliation and the 14 observation-driven algorithms. MW's `PlaceResolver` currently
resolves location names to `place_<slug>` IDs (e.g., "Olive Garden" → "place_olive_garden") via
exact + prefix match, but has no geohash computation. K0's `stage_42` (geo_metadata) can enrich
locations with coordinates, but only if MW provides a seed geohash or leaves it as a recognizable
fallback.

**Current PlaceResolver state (verified via code read):**

- `__init__(location_entities)` — builds case-insensitive exact map from EntityRef objects
- `resolve(name) -> Optional[str]` — O(1) exact match → O(n) prefix fallback → None
- `_to_place_id(canonical)` — slug: lowercase, spaces→underscores, punctuation stripped
- `ResolvedPlace` DC: place_id, canonical_name, confidence
- 47 existing tests in `test_place_resolver.py`

**Solution:** Add `resolve_with_geohash()` to PlaceResolver that returns `(place_id, geohash_6)`
tuples. For known locations (configured per-tenant), return exact geohashes. For unknown
locations, return a "000000" sentinel that K0's stage_42 recognizes as "needs enrichment."

**Deliverable:**

| Item | File | Work |
|------|------|------|
| I-MW-0.4.1 | `k1/memory_writer/place_resolver.py` | Add `resolve_with_geohash(name: Optional[str], known_geohashes: dict[str, str] = None) -> tuple[Optional[str], Optional[str]]` method. Returns `(place_id, geohash_6)`. Logic: (1) Call existing `resolve(name)` for place_id. (2) If `known_geohashes` has case-insensitive match for `name` → return that geohash. (3) If place_id resolved but no geohash → return `(place_id, "000000")` as fallback sentinel. (4) If name is None/empty → return `(None, None)`. Also add `_normalize_key(name: str) -> str` helper (strip + lowercase) — extracted from existing resolve() to DRY up. Keep `resolve()` unchanged for backward compat |
| I-MW-0.4.2 | `k1/memory_writer/config.py` | Add `known_location_geohashes: Dict[str, str] = field(default_factory=dict)` to MWConfig. Default empty — populated per-tenant from deployment config. Example values: `{"home": "9q8yyz", "office": "9q8yyk", "school": "9q8yyg"}`. Values are 6-char geohash strings. Document: K0 stage_42 geo_metadata module handles coordinate resolution and geohash refinement for unknown locations; MW only provides seed values for known places |
| I-MW-0.4.3 | `tests/k1/memory_writer/test_place_resolver.py` | Add to existing file (~12 new tests): (a) `test_resolve_with_geohash_known_location` — "home" in known_geohashes → exact geohash. (b) `test_resolve_with_geohash_unknown_location` — "Olive Garden" not in known → ("place_olive_garden", "000000"). (c) `test_resolve_with_geohash_none_input` → (None, None). (d) `test_resolve_with_geohash_empty_string` → (None, None). (e) `test_resolve_with_geohash_case_insensitive` — "HOME" matches "home" key. (f) `test_resolve_with_geohash_no_entity_match` — name not in entities and not in known → (None, None). (g) `test_resolve_with_geohash_entity_match_no_known` — entity match but no known geohash → (place_id, "000000"). (h) `test_resolve_with_geohash_known_overrides_entity` — known geohash takes priority. (i) `test_geohash_format_6_chars` — verify all returned geohashes are exactly 6 chars or None. (j) `test_resolve_still_works` — verify existing `resolve()` is unchanged (backward compat). (k) `test_known_geohashes_empty_dict` — default config, all locations get "000000". (l) `test_known_geohashes_prefix_match` — "Olive Garden on Main St" matches "olive garden" known entry via prefix |

**Geohash sentinel convention:**

- `"000000"` = K0 stage_42 will enrich with real coordinates
- 6-char valid geohash (e.g., `"9q8yyz"`) = K0 stage_42 trusts as-is
- `None` = no location context (MW did not extract location)

**Acceptance criteria:**

- `resolve_with_geohash("home", {"home": "9q8yyz"})` returns `("place_home", "9q8yyz")`
- `resolve_with_geohash("Olive Garden")` returns `("place_olive_garden", "000000")`
- `resolve_with_geohash(None)` returns `(None, None)`
- All 47 existing tests in `test_place_resolver.py` still pass (backward compat)
- New tests verify 6-char geohash format invariant

---

## 9. Phase 1 — Filter + Context Assembly (No LLM)

Stages 1 and 2 of the pipeline. Zero LLM cost. Deterministic, highly testable.

**Per-turn pipeline (matches Architecture §5):** Every `turn.complete.v1` that passes the filter gets a **full SessionState snapshot** → LLM extraction. No accumulation gate, no turn-count gating. SessionState IS the accumulator — `history_active` already holds the last 10-25 full-fidelity turns. The LLM sees the entire conversation window that SS maintains, not a narrow slice.

**Why no accumulation gate:** The original plan discussed an AccumulationGate (T1-T6 triggers). This is wrong. SS already accumulates context across turns — `history_active` holds recent turns, `scoreboard` holds discourse state, `narrative_active` holds arc position. MW doesn't need to re-implement accumulation. Every passed turn gets the full SS snapshot, and the LLM sees everything. The filter's job is to prevent wasting LLM calls on trivial turns ("ok", "thanks", clarifications). If a turn passes the filter, it's worth giving the LLM the full picture.

**FSM payload gap (CRITICAL):** The Concierge FSM `_emit_turn_completed()` in `k1/concierge/fsm/controller.py:3460` currently emits **only `turn_number`** in the `turn.complete.v1` payload. The MW `TurnCompletePayload` dataclass expects 18 fields (`turn_id`, `session_id`, `cognitive_trace_id`, `user_message`, `assistant_response`, `timestamp_ms`, `turn_number`, plus 8 temporal/spatial GAP-002 fields). **Resolution:** Phase 1 does NOT fix the FSM. Instead, the Context Builder (E-MW-1.2) reads all missing fields from the SessionState snapshot. The FSM enrichment is a Phase 4 prerequisite (E-MW-4.2 Turn Dispatcher will validate payload completeness and fall back to SS read for missing fields).

**Dependencies:** Phase 0 must be complete (E-MW-0.1 exports, E-MW-0.3 section-agnostic config with `skip_sections: frozenset`).

---

### E-MW-1.1: Relevance Filter (Stage 1)

**Design ref:** Architecture §6 (`memory_writer_architecture.md` lines 240-398)
**Invariant:** MW-07 (no LLM in filter — enforced by `assert_mw07_filter_no_llm()` in `invariants.py`)

#### Problem Statement

Current state: `types.py` defines `SkipReason` enum with 5 values (`DUPLICATE`, `TRIVIAL`, `SYSTEM_TURN`, `STALE`, `EMPTY`) and `FilterDecision` dataclass (`passed: bool`, `skip_reason: Optional[SkipReason]`, `turn_id: str`, `latency_ms: float`). `events.py` defines `FilterDecisionEvent` and `TOPIC_FILTER_DECISION = "k1.mw.filter.decision.v1"`. `config.py` has `filter_dedup_window_seconds: int = 300` and `filter_trivial_word_threshold: int = 5`. No actual filter implementation exists — only types and events.

The architecture doc (§6) specifies 5 skip rules (R1-R5) evaluated cheapest-first. The plan adds R6 (tool call boost) which is NOT a skip rule but a **pass-through override** that short-circuits R4/R5 for tool-bearing turns. R6 does not need a SkipReason value — it prevents skip decisions, it doesn't create them.

#### SkipReason Enum Reconciliation

The current `SkipReason` enum values map to architecture doc rules as follows:

| SkipReason value | Architecture rule | Current enum docstring mapping | Corrected mapping |
|------------------|-------------------|-------------------------------|-------------------|
| `EMPTY` | R4 (Empty/Trivial) | R5 | R4 — `<5 words` + no entities + trivial patterns |
| `TRIVIAL` | R5 (Pure continuation) | R2 | R5 — continuation phrases ("go on", "what else") |
| `DUPLICATE` | R3 (Recent duplicate) | R1 | R3 — SHA256 hash dedup in 5-min window |
| `SYSTEM_TURN` | R2 (System/Meta talk) | R3 | R2 — about system, not about life |
| `STALE` | R1 (Clarification) | R4 | R1 — user clarification Q + assistant repair |

**Action:** Update `SkipReason` enum docstring in `types.py` to match architecture doc rule IDs. Add new value `CLARIFICATION = "CLARIFICATION"` to replace `STALE` for clarity. Keep `STALE` as deprecated alias for backward compat. The enum becomes:

```python
class SkipReason(str, Enum):
    CLARIFICATION = "CLARIFICATION"  # R1: user clarification + assistant repair
    SYSTEM_TURN = "SYSTEM_TURN"      # R2: system/meta talk, not about life
    DUPLICATE = "DUPLICATE"          # R3: entity+topic hash seen in 5-min window
    EMPTY = "EMPTY"                  # R4: <5 words, no entities, trivial patterns
    TRIVIAL = "TRIVIAL"              # R5: pure continuation ("go on", "what else")
    STALE = "STALE"                  # DEPRECATED: use CLARIFICATION
```

#### Rule Evaluation Order (cheapest-first)

```text
R4 (EMPTY)          →  O(1) word count + set lookup against TRIVIAL_PATTERNS
R5 (TRIVIAL)        →  O(1) pattern match against CONTINUATION_PHRASES
R6 (Tool call boost) →  O(1) key check: "tool_calls" in turn metadata → auto-PASS
R1 (CLARIFICATION)  →  O(n) regex check on user msg + assistant response
R2 (SYSTEM_TURN)    →  O(n) regex check on user msg for system/meta patterns
R3 (DUPLICATE)      →  O(1) SHA256 hash lookup in ring buffer (most expensive due to hash)

ANY match → SKIP (return FilterDecision(passed=False, skip_reason=<rule>))
NONE match → PASS (return FilterDecision(passed=True))
R6 fires before R1 → if turn has tool_calls, skip R4/R5 checks entirely
```

#### Entity Counter-Example Rule

ALL skip rules share one override: if named entities (`PERSON`, `LOC`, `ORG`, `DATE`, `MONEY`) appear in the user message, the turn PASSES regardless of other rule matches. Entity detection uses the entities already extracted by Concierge and stored in `Turn.entities: List[str]` from `history_active`.

**Source:** `TypedHistoryEntry` in `k1/sessionstate/sections/history_active.py:118` has `metadata: Dict[str, Any]` which may carry entities. `Turn` in `history_active.py:180` has `entities: List[str]` directly. The filter reads entities from the `TurnCompletePayload` once the FSM is enriched, or from the most recent `Turn` in the SS snapshot until then.

#### Rule Implementations

**R4 (Empty/Trivial):**

```python
TRIVIAL_PATTERNS: frozenset[str] = frozenset({
    "ok", "sure", "thanks", "thank you", "got it", "yes", "no",
    "yeah", "alright", "cool", "nice", "fine", "good", "right",
    "okay", "yep", "nope", "uh huh", "mm", "hmm", "mhm",
})

def check_r4_empty(user_message: str, entities: list[str],
                   threshold: int = 5) -> Optional[SkipReason]:
    words = user_message.strip().split()
    if len(words) >= threshold:
        return None  # not trivial
    if entities:
        return None  # has entities → pass
    normalized = user_message.strip().lower().rstrip("!?.,")
    if normalized in TRIVIAL_PATTERNS:
        return SkipReason.EMPTY
    return None
```

**R5 (Pure continuation):**

```python
CONTINUATION_PHRASES: frozenset[str] = frozenset({
    "go on", "continue", "what else", "tell me more", "and then",
    "anything else", "keep going", "next", "more", "what else?",
    "and?", "go ahead", "proceed",
})

def check_r5_continuation(user_message: str, entities: list[str],
                          max_words: int = 10) -> Optional[SkipReason]:
    words = user_message.strip().split()
    if len(words) > max_words:
        return None
    if entities:
        return None
    normalized = user_message.strip().lower().rstrip("!?.,")
    if normalized in CONTINUATION_PHRASES:
        return SkipReason.TRIVIAL
    return None
```

**R6 (Tool call boost):**

```python
def check_r6_tool_call_boost(turn_metadata: dict[str, Any]) -> bool:
    """Returns True if turn has tool_calls → skip R4/R5, auto-PASS."""
    tool_calls = turn_metadata.get("tool_calls")
    return bool(tool_calls)
```

**R1 (Clarification):**

```python
_CLARIFICATION_PATTERNS: tuple[re.Pattern, ...] = (
    re.compile(r"\bwhat do you mean\b", re.I),
    re.compile(r"\bcan you (explain|repeat|clarify)\b", re.I),
    re.compile(r"\bi don'?t understand\b", re.I),
    re.compile(r"\bwhich one\b", re.I),
    re.compile(r"\bwhat'?s that\b", re.I),
    re.compile(r"\bhuh\?", re.I),
)

_REPAIR_MARKERS: tuple[re.Pattern, ...] = (
    re.compile(r"\bI meant\b", re.I),
    re.compile(r"\bto clarify\b", re.I),
    re.compile(r"\bin other words\b", re.I),
    re.compile(r"\bwhat I (said|meant)\b", re.I),
)

def check_r1_clarification(user_message: str, assistant_response: str,
                           entities: list[str]) -> Optional[SkipReason]:
    if entities:
        return None  # entity present → pass
    user_is_clarification = any(p.search(user_message) for p in _CLARIFICATION_PATTERNS)
    assistant_has_repair = any(p.search(assistant_response) for p in _REPAIR_MARKERS)
    if user_is_clarification and assistant_has_repair:
        return SkipReason.CLARIFICATION
    return None
```

**R2 (System/Meta):**

```python
_SYSTEM_META_PATTERNS: tuple[re.Pattern, ...] = (
    re.compile(r"\b(change|set|use|switch)\s+(your\s+)?(tone|style|format)\b", re.I),
    re.compile(r"\bwhat (can you do|features|capabilities)\b", re.I),
    re.compile(r"\bstop (asking|using|doing)\b", re.I),
    re.compile(r"\bbe more (concise|brief|formal|casual)\b", re.I),
    re.compile(r"\b(how|what) (do|does) (you|this|the system)\b", re.I),
)

def check_r2_system_meta(user_message: str, entities: list[str]) -> Optional[SkipReason]:
    if entities:
        return None
    if any(p.search(user_message) for p in _SYSTEM_META_PATTERNS):
        return SkipReason.SYSTEM_TURN
    return None
```

**R3 (Recent duplicate):**

```python
import hashlib

class DedupRingBuffer:
    """Bounded ring buffer for SHA256 hashes. Cleared on session end."""
    __slots__ = ("_buffer", "_capacity", "_index", "_lookup")

    def __init__(self, capacity: int = 100) -> None:
        self._buffer: list[tuple[str, int]] = []  # (hash, timestamp_ms)
        self._capacity = capacity
        self._index = 0
        self._lookup: dict[str, int] = {}  # hash → timestamp_ms

    def contains(self, hash_val: str, now_ms: int, window_ms: int) -> bool:
        ts = self._lookup.get(hash_val)
        if ts is None:
            return False
        return (now_ms - ts) < window_ms

    def add(self, hash_val: str, now_ms: int) -> None:
        if len(self._buffer) < self._capacity:
            self._buffer.append((hash_val, now_ms))
        else:
            old_hash, _ = self._buffer[self._index]
            self._lookup.pop(old_hash, None)
            self._buffer[self._index] = (hash_val, now_ms)
            self._index = (self._index + 1) % self._capacity
        self._lookup[hash_val] = now_ms

    def clear(self) -> None:
        self._buffer.clear()
        self._lookup.clear()
        self._index = 0

def check_r3_duplicate(participants: list[str], topics: list[str],
                       now_ms: int, ring: DedupRingBuffer,
                       window_ms: int = 300_000) -> Optional[SkipReason]:
    key = ",".join(sorted(participants)) + "|" + ",".join(sorted(topics))
    hash_val = hashlib.sha256(key.encode()).hexdigest()
    if ring.contains(hash_val, now_ms, window_ms):
        return SkipReason.DUPLICATE
    ring.add(hash_val, now_ms)
    return None
```

#### RelevanceFilter Class

```python
class RelevanceFilter:
    """Evaluates all rules against incoming turns. MW-07: zero LLM dependencies.

    Constructor dependencies: MWConfig only (no ports).
    """

    def __init__(self, config: MWConfig) -> None:
        assert_mw07_filter_no_llm({"config": config})  # no LLM port
        self._config = config
        self._dedup_ring = DedupRingBuffer(capacity=100)

    def evaluate(self, user_message: str, assistant_response: str,
                 entities: list[str], topics: list[str],
                 turn_id: str, timestamp_ms: int,
                 turn_metadata: dict[str, Any] | None = None) -> FilterDecision:
        import time
        start = time.perf_counter_ns()

        meta = turn_metadata or {}

        # R6: tool call boost — auto-PASS if tool_calls present
        if check_r6_tool_call_boost(meta):
            elapsed = (time.perf_counter_ns() - start) / 1_000_000
            return FilterDecision(passed=True, turn_id=turn_id, latency_ms=elapsed)

        # R4: empty/trivial
        reason = check_r4_empty(user_message, entities, self._config.filter_trivial_word_threshold)
        if reason:
            elapsed = (time.perf_counter_ns() - start) / 1_000_000
            return FilterDecision(passed=False, skip_reason=reason, turn_id=turn_id, latency_ms=elapsed)

        # R5: continuation
        reason = check_r5_continuation(user_message, entities)
        if reason:
            elapsed = (time.perf_counter_ns() - start) / 1_000_000
            return FilterDecision(passed=False, skip_reason=reason, turn_id=turn_id, latency_ms=elapsed)

        # R1: clarification
        reason = check_r1_clarification(user_message, assistant_response, entities)
        if reason:
            elapsed = (time.perf_counter_ns() - start) / 1_000_000
            return FilterDecision(passed=False, skip_reason=reason, turn_id=turn_id, latency_ms=elapsed)

        # R2: system/meta
        reason = check_r2_system_meta(user_message, entities)
        if reason:
            elapsed = (time.perf_counter_ns() - start) / 1_000_000
            return FilterDecision(passed=False, skip_reason=reason, turn_id=turn_id, latency_ms=elapsed)

        # R3: duplicate (most expensive — hash computation)
        reason = check_r3_duplicate(
            participants=entities,  # use entity list as proxy for participants
            topics=topics,
            now_ms=timestamp_ms,
            ring=self._dedup_ring,
            window_ms=self._config.filter_dedup_window_seconds * 1000,
        )
        if reason:
            elapsed = (time.perf_counter_ns() - start) / 1_000_000
            return FilterDecision(passed=False, skip_reason=reason, turn_id=turn_id, latency_ms=elapsed)

        # All rules passed
        elapsed = (time.perf_counter_ns() - start) / 1_000_000
        return FilterDecision(passed=True, turn_id=turn_id, latency_ms=elapsed)

    def reset(self) -> None:
        """Clear session-scoped state (dedup ring). Called on session end."""
        self._dedup_ring.clear()
```

#### Implementation Items

| Item | File | Work |
|------|------|------|
| I-MW-1.1.1 | `k1/memory_writer/filter/__init__.py` | Package init. Re-exports: `RelevanceFilter`, `DedupRingBuffer`, all `check_r*` functions, `TRIVIAL_PATTERNS`, `CONTINUATION_PHRASES` |
| I-MW-1.1.2 | `k1/memory_writer/filter/rules.py` | 6 rule functions (`check_r1_clarification`, `check_r2_system_meta`, `check_r3_duplicate`, `check_r4_empty`, `check_r5_continuation`, `check_r6_tool_call_boost`). `DedupRingBuffer` class. Module-level constant frozensets `TRIVIAL_PATTERNS` (21 entries) and `CONTINUATION_PHRASES` (13 entries). Regex pattern tuples `_CLARIFICATION_PATTERNS` (6 patterns) and `_REPAIR_MARKERS` (4 patterns) and `_SYSTEM_META_PATTERNS` (5 patterns). Import: `re`, `hashlib`, `typing`, `k1.memory_writer.types.SkipReason` |
| I-MW-1.1.3 | `k1/memory_writer/filter/relevance_filter.py` | `RelevanceFilter` class as shown above. Import: `time`, `k1.memory_writer.config.MWConfig`, `k1.memory_writer.types.FilterDecision`, `k1.memory_writer.invariants.assert_mw07_filter_no_llm`, all rule functions from `rules.py` |
| I-MW-1.1.4 | `k1/memory_writer/types.py` (modify) | Update `SkipReason` enum: add `CLARIFICATION = "CLARIFICATION"`, update docstring to map to architecture rule IDs |

#### Test Specification: `tests/k1/memory_writer/test_relevance_filter.py`

**34 tests** organized in 7 test classes:

```text
class TestR4EmptyTrivial:           # 6 tests
  test_single_word_trivial          — "ok" → SKIP(EMPTY)
  test_below_threshold_trivial      — "sure thing" → SKIP(EMPTY)
  test_above_threshold_passes       — "We went to the park today" → PASS
  test_entity_overrides_trivial     — "yes, Mom" with entities=["Mom"] → PASS
  test_unknown_short_not_trivial    — "blue car" (not in patterns) → PASS (not in set)
  test_punctuation_normalization    — "thanks!" → SKIP(EMPTY)

class TestR5Continuation:           # 5 tests
  test_exact_continuation_phrase    — "go on" → SKIP(TRIVIAL)
  test_continuation_with_entity     — "tell me more about Mom" + entities → PASS
  test_over_max_words               — 11+ word message matching phrase → PASS
  test_case_insensitive             — "Go On" → SKIP(TRIVIAL)
  test_non_continuation_short       — "I agree" → PASS (not in set)

class TestR6ToolCallBoost:          # 4 tests
  test_tool_call_overrides_trivial  — "ok" + tool_calls in metadata → PASS
  test_tool_call_overrides_cont     — "go on" + tool_calls → PASS
  test_empty_tool_calls             — metadata={"tool_calls": []} → no boost (falsy)
  test_no_metadata                  — None metadata → no boost

class TestR1Clarification:          # 5 tests
  test_clarification_with_repair    — "What do you mean?" + "I meant..." → SKIP(CLARIFICATION)
  test_clarification_no_repair      — "What do you mean?" + "The weather is nice" → PASS
  test_repair_without_clarification — "Hello" + "I meant..." → PASS
  test_entity_overrides             — "What do you mean, Mom?" + entities → PASS
  test_partial_match                — "Can you explain the recipe?" + entities → PASS

class TestR2SystemMeta:             # 5 tests
  test_tone_change                  — "Change your tone to formal" → SKIP(SYSTEM_TURN)
  test_capability_query             — "What can you do?" → SKIP(SYSTEM_TURN)
  test_entity_overrides             — "Help me schedule Mom's appointment" → PASS
  test_life_question                — "How do I make pasta?" → PASS (not system/meta)
  test_stop_pattern                 — "Stop asking questions" → SKIP(SYSTEM_TURN)

class TestR3Duplicate:              # 5 tests
  test_same_hash_within_window      — same participants+topics, <5min apart → SKIP(DUPLICATE)
  test_same_hash_outside_window     — same hash, >5min apart → PASS
  test_different_hash               — different participants → PASS
  test_ring_buffer_capacity         — 101 entries → oldest evicted
  test_clear_on_session_end         — ring.clear() resets state

class TestRelevanceFilterIntegrated: # 4 tests
  test_full_evaluation_pass         — meaningful turn → PASS
  test_full_evaluation_skip_trivial — "ok" → SKIP(EMPTY)
  test_mw07_enforcement             — construct with LLM port → InvariantViolation
  test_filter_decision_event_fields — verify all FilterDecisionEvent fields populated
```

**Acceptance criteria:**

- [x] All 34 tests pass
- [x] `RelevanceFilter` constructor rejects any dict key in `{"IModelHubPort", "model_hub_port", "model_hub", "llm_port"}` (MW-07)
- [x] `FilterDecision.latency_ms` < 5ms on all test cases
- [x] `DedupRingBuffer` is bounded to `capacity` entries (no memory leak)
- [x] Entity counter-example rule: any turn with entities in user message passes R1-R5
- [x] R6 tool call boost: `metadata["tool_calls"]` → auto-PASS regardless of R4/R5

---

### E-MW-1.2: Context Assembly — Full SS Snapshot Read (Stage 2)

**Design ref:** Architecture §5 (per-turn pipeline), §7 (Context Assembly, `memory_writer_architecture.md` lines 400-510)
**Invariant:** MW-02 (<1ms read — enforced by `assert_mw02_read_latency()` in `invariants.py`)

#### Problem Statement

Current state: `context_assembly.py` exists with temporal/spatial resolution (`resolve_mentioned_time`, `resolve_mentioned_location`, `resolve_place_id`, `assemble_temporal_spatial`). `ISessionReadPort` defines `snapshot(sections)` and `read_section(name)`. `ExtractionContext` in `types.py` has 25 fields but is missing `tool_calls_per_turn: Dict[int, List[Dict]]` (needed for the extraction LLM to understand what actions occurred).

No `MWSessionReader` or `ContextBuilder` class exists. The wiring contract specifies:

- `k1/memory_writer/context/session_reader.py` — `MWSessionReader`
- `k1/memory_writer/context/context_builder.py` — `ContextBuilder`

Phase 0's `snapshot_all(exclude)` method on `ISessionReadPort` must be available.

#### Types Modification: Add `tool_calls_per_turn`

Add to `ExtractionContext` in `types.py`:

```python
# Tool calls from Turn.metadata["tool_calls"] (Phase P prerequisite)
tool_calls_per_turn: Dict[int, List[Dict[str, Any]]] = field(default_factory=dict)
```

This maps `turn_number → list of tool call dicts`. Each tool call dict has at minimum `{"name": str, "status": str}`. Source: `Turn.metadata["tool_calls"]` or `TypedHistoryEntry.metadata["tool_calls"]` from `history_active`.

#### MWSessionReader

```python
class MWSessionReader:
    """Reads SessionState sections via ISessionReadPort.

    Section-agnostic: reads all sections except config.skip_sections.
    Returns raw dict. No section-name hardcoding.
    """

    def __init__(self, port: ISessionReadPort, config: MWConfig) -> None:
        self._port = port
        self._config = config

    async def read_snapshot(self) -> dict[str, Any]:
        """Read all non-skipped sections in one atomic snapshot.

        Uses snapshot_all(exclude=config.skip_sections) from Phase 0.
        Measures latency for MW-02 enforcement.
        """
        import time
        start = time.perf_counter_ns()
        snapshot = await self._port.snapshot_all(exclude=self._config.skip_sections)
        elapsed_ms = (time.perf_counter_ns() - start) / 1_000_000
        assert_mw02_read_latency(elapsed_ms)
        return snapshot
```

#### ContextBuilder

The `ContextBuilder` transforms a raw SS snapshot dict into a populated `ExtractionContext`. It reads from whatever sections are present in the snapshot — no hardcoded section names except for the well-known field paths within sections.

**Section field extraction map:**

| SS Section | ExtractionContext Field(s) | Extraction Logic |
|------------|---------------------------|------------------|
| `history_active` | `current_turn`, `recent_turns`, `tool_calls_per_turn` | Last N turns from `Turn` list. `CompressedTurn(turn_id, role, text, timestamp_ms, turn_number)`. Tool calls from `Turn.metadata["tool_calls"]` or sub_entries metadata |
| `beliefs_active` | `active_persons`, temporal/spatial (via `context_assembly.py`) | `mentioned_entities` list, `mentioned_time`, `mentioned_location` dicts |
| `affective_now` | `current_affect` | `Affect(valence, arousal, dominance)` from `dimensions` dict |
| `affective_baseline` | `baseline_affect` | Same pattern as `affective_now` |
| `narrative_active` | `active_narrative` | Dict with `arc_position`, `primary_thread`, `progress` |
| `scoreboard` | `active_topics`, `topic_salience` | `topic_stack` list → names + salience. `referents` → active entity names |
| `control` | `control_context` | `intents`, `active_tool_calls`, `safety_band` |
| `persona` | `persona_context` | `traits`, `preferences`, `identity_domains` |
| `task_state` | (merged into `control_context`) | Active task metadata |
| `ifl` | `device_context` | Device ID, sensor data |
| `meta` | `session_id` | Session UUID, user_id, band |
| `beliefs_history` | (not directly mapped — used by extraction validator for dedup) | Historical beliefs |
| `history_recent` | (merged into `recent_turns` if window extends beyond active) | Older turn summaries |

**Conversation window logic:** Every turn that passes the relevance filter triggers a full SS snapshot read. `history_active` holds the last 10-25 full-fidelity turns — SessionState IS the accumulator. The ContextBuilder reads ALL turns from `history_active` (the full conversation window SS already manages). No turn_id filtering, no accumulation gate. If `history_recent` contains older summaries that extend the window, those are appended for additional context.

**Tool calls extraction:** For each `Turn` in the window, check `turn.metadata` for `"tool_calls"` key. The `Turn` dataclass in `history_active.py:180` has `metadata: Optional[TurnMetadata]` where `TurnMetadata` is a typed object. However, tool_calls may also be in `TypedHistoryEntry.metadata: Dict[str, Any]` (sub-entries). Strategy: check `Turn.sub_entries` for any entry with `metadata.get("tool_calls")`.

```python
class ContextBuilder:
    """Assembles ExtractionContext from SS snapshot + TurnCompletePayload.

    Uses context_assembly.py for temporal/spatial resolution.
    Falls back gracefully if sections are missing.
    """

    def __init__(self, config: MWConfig) -> None:
        self._config = config

    def build(
        self,
        snapshot: dict[str, Any],
        payload: TurnCompletePayload,
    ) -> ExtractionContext:
        """Build ExtractionContext from snapshot and payload.

        Args:
            snapshot: Raw SS snapshot from MWSessionReader.
            payload: TurnCompletePayload for the current turn.

        Every filter-passed turn gets the full SS snapshot.
        SessionState is the accumulator — history_active holds
        10-25 recent turns. We read ALL of them.
        """
        # Temporal/spatial via existing context_assembly.py
        beliefs = snapshot.get("beliefs_active", {})
        ts_fields = assemble_temporal_spatial(payload, beliefs)

        # History window — read ALL turns from history_active
        current_turn, recent_turns, tool_calls = self._extract_history(
            snapshot, payload
        )

        # Affect
        current_affect = self._extract_affect(snapshot.get("affective_now"))
        baseline_affect = self._extract_affect(snapshot.get("affective_baseline"))

        # Topics from scoreboard
        active_topics, topic_salience = self._extract_topics(snapshot.get("scoreboard"))

        # Narrative
        active_narrative = snapshot.get("narrative_active")

        # Control, persona, device
        control_context = snapshot.get("control", {}) or {}
        persona_context = snapshot.get("persona", {}) or {}
        device_context = snapshot.get("ifl", {}) or {}

        # Active persons from beliefs_active
        active_persons = self._extract_persons(beliefs)

        # Goals from task_state
        task = snapshot.get("task_state", {}) or {}
        active_goals = task.get("active_goals", []) if isinstance(task, dict) else []

        # Session metadata
        meta = snapshot.get("meta", {}) or {}
        session_id = meta.get("session_id", payload.session_id)

        return ExtractionContext(
            current_turn=current_turn,
            recent_turns=recent_turns,
            active_persons=active_persons,
            current_affect=current_affect,
            baseline_affect=baseline_affect,
            active_narrative=active_narrative if isinstance(active_narrative, dict) else None,
            active_topics=active_topics,
            topic_salience=topic_salience,
            active_goals=active_goals,
            control_context=control_context,
            device_context=device_context,
            persona_context=persona_context,
            session_id=session_id,
            conversation_turn=payload.turn_number,
            tool_calls_per_turn=tool_calls,
            **ts_fields,
        )

    def _extract_history(self, snapshot, payload):
        """Extract full conversation window from history_active.

        Reads ALL turns — SessionState manages the window size (10-25 turns).
        No turn_id filtering. Every turn in history_active is included.
        """
        history = snapshot.get("history_active", {})
        turns_raw = history.get("turns", []) if isinstance(history, dict) else []

        current_turn = CompressedTurn(
            turn_id=payload.turn_id,
            role="user",
            text=payload.user_message,
            timestamp_ms=payload.timestamp_ms,
            turn_number=payload.turn_number,
        )

        recent_turns: list[CompressedTurn] = []
        tool_calls: dict[int, list[dict]] = {}

        for t in turns_raw:
            tid = t.get("turn_id", "") if isinstance(t, dict) else getattr(t, "turn_id", "")
            ct = CompressedTurn(
                turn_id=tid,
                role="user",
                text=(t.get("user_message", "") if isinstance(t, dict)
                      else getattr(t, "user_message", "")),
                timestamp_ms=(t.get("timestamp_ms", 0) if isinstance(t, dict)
                              else getattr(t, "timestamp_ms", 0)),
                turn_number=(t.get("turn_number", 0) if isinstance(t, dict)
                             else getattr(t, "turn_number", 0)),
            )
            recent_turns.append(ct)

            # Extract tool_calls from turn metadata
            tc = self._extract_tool_calls_from_turn(t)
            if tc:
                tool_calls[ct.turn_number] = tc

        return current_turn, recent_turns, tool_calls

    def _extract_tool_calls_from_turn(self, turn) -> list[dict]:
        """Extract tool_calls from Turn metadata or sub-entries."""
        result = []
        # Check Turn.metadata directly
        if isinstance(turn, dict):
            meta = turn.get("metadata", {})
            if isinstance(meta, dict):
                tc = meta.get("tool_calls", [])
                if tc:
                    result.extend(tc)
            # Check sub_entries
            for entry in turn.get("sub_entries", []):
                if isinstance(entry, dict):
                    entry_meta = entry.get("metadata", {})
                    if isinstance(entry_meta, dict):
                        tc = entry_meta.get("tool_calls", [])
                        if tc:
                            result.extend(tc)
        else:
            # Dataclass Turn object
            meta = getattr(turn, "metadata", None)
            if meta and hasattr(meta, "__dict__"):
                tc = getattr(meta, "tool_calls", None) or []
                if tc:
                    result.extend(tc)
            for entry in getattr(turn, "sub_entries", []):
                entry_meta = getattr(entry, "metadata", {})
                if isinstance(entry_meta, dict):
                    tc = entry_meta.get("tool_calls", [])
                    if tc:
                        result.extend(tc)
        return result

    def _extract_affect(self, section) -> Affect | None:
        if not section or not isinstance(section, dict):
            return None
        dims = section.get("dimensions", section)
        if isinstance(dims, dict):
            return Affect(
                valence=float(dims.get("valence", 0.0)),
                arousal=float(dims.get("arousal", 0.0)),
                dominance=float(dims.get("dominance", 0.5)),
            )
        return None

    def _extract_topics(self, scoreboard) -> tuple[list[str], dict[str, float]]:
        if not scoreboard or not isinstance(scoreboard, dict):
            return [], {}
        topics = []
        salience = {}
        for t in scoreboard.get("topic_stack", []):
            if isinstance(t, dict):
                name = t.get("name", "")
                if name:
                    topics.append(name)
                    salience[name] = float(t.get("salience", 0.0))
        return topics, salience

    def _extract_persons(self, beliefs) -> dict[str, Any]:
        if not beliefs or not isinstance(beliefs, dict):
            return {}
        entities = beliefs.get("mentioned_entities", [])
        persons = {}
        for e in entities:
            if isinstance(e, dict) and e.get("type") == "PERSON":
                name = e.get("display_name", "")
                pid = e.get("person_id", "")
                if name:
                    persons[name] = {"person_id": pid, "type": "PERSON",
                                     "confidence": e.get("confidence", 1.0)}
        return persons
```

#### Implementation Items

| Item | File | Work |
|------|------|------|
| I-MW-1.2.1 | `k1/memory_writer/context/__init__.py` | Package init. Re-exports: `MWSessionReader`, `ContextBuilder` |
| I-MW-1.2.2 | `k1/memory_writer/context/session_reader.py` | `MWSessionReader` class. Imports: `time`, `typing`, `k1.memory_writer.ports.session_read_port.ISessionReadPort`, `k1.memory_writer.config.MWConfig`, `k1.memory_writer.invariants.assert_mw02_read_latency` |
| I-MW-1.2.3 | `k1/memory_writer/context/context_builder.py` | `ContextBuilder` class as shown above. Imports: `typing`, `k1.memory_writer.config.MWConfig`, `k1.memory_writer.types.ExtractionContext`, `k1.memory_writer.types.CompressedTurn`, `k1.memory_writer.types.Affect`, `k1.memory_writer.events.TurnCompletePayload`, `k1.memory_writer.context_assembly.assemble_temporal_spatial` |
| I-MW-1.2.4 | `k1/memory_writer/types.py` (modify) | Add field `tool_calls_per_turn: Dict[int, List[Dict[str, Any]]] = field(default_factory=dict)` to `ExtractionContext` after `place_id` |

#### Test Specification: `tests/k1/memory_writer/test_context_builder.py`

**26 tests** organized in 6 test classes:

```text
class TestMWSessionReader:                  # 4 tests
  test_reads_all_non_skipped_sections       — calls snapshot_all(exclude=skip_sections)
  test_mw02_latency_enforcement             — mock slow read (>1ms) → InvariantViolation
  test_mw02_fast_read_passes                — mock fast read (<1ms) → success
  test_empty_snapshot                       — empty SS → returns {}

class TestContextBuilderHistory:            # 5 tests
  test_extracts_current_turn_from_payload   — payload fields → CompressedTurn
  test_extracts_all_turns_from_history      — 5 turns in history_active → 5 CompressedTurns (full window)
  test_empty_history                        — no turns → empty recent_turns, current_turn still set
  test_turn_ordering_preserved              — turns returned in same order as history_active
  test_large_window_all_included            — 25 turns in history_active → all 25 included

class TestContextBuilderToolCalls:          # 4 tests
  test_extracts_from_turn_metadata          — Turn.metadata["tool_calls"] → tool_calls_per_turn
  test_extracts_from_sub_entries            — TypedHistoryEntry.metadata["tool_calls"] → merged
  test_no_tool_calls                        — no metadata → empty dict
  test_mixed_turns                          — turn 1 has tool_calls, turn 2 does not → {1: [...]}

class TestContextBuilderAffect:             # 3 tests
  test_extracts_affect_from_dimensions      — affective_now.dimensions → Affect(v,a,d)
  test_missing_affective_section            — no affective_now → None
  test_baseline_and_current                 — both sections → both populated

class TestContextBuilderTopics:             # 4 tests
  test_extracts_topic_names                 — scoreboard.topic_stack → active_topics
  test_extracts_salience                    — topic.salience → topic_salience dict
  test_empty_scoreboard                     — no scoreboard → [], {}
  test_missing_scoreboard_section           — scoreboard=None → [], {}

class TestContextBuilderIntegrated:         # 6 tests
  test_full_build_all_sections              — all 13 sections present → fully populated ExtractionContext
  test_missing_sections_graceful            — only history_active + meta → partial context, no error
  test_temporal_spatial_from_payload        — payload-first pattern (context_assembly.py)
  test_temporal_spatial_fallback_to_beliefs — empty payload fields → reads beliefs_active
  test_persons_extraction                   — beliefs_active entities type=PERSON → active_persons
  test_session_id_from_meta_or_payload      — meta.session_id if present, else payload.session_id
```

**Acceptance criteria:**

- [x] All 26 tests pass
- [x] `ContextBuilder.build()` takes `(snapshot, payload)` — no `accumulated_turn_ids` parameter
- [x] `ContextBuilder._extract_history()` reads ALL turns from `history_active` — no filtering
- [x] `ContextBuilder.build()` never raises on missing sections — returns partial ExtractionContext
- [x] `tool_calls_per_turn` populated from `Turn.metadata` and `TypedHistoryEntry.metadata`
- [x] Temporal/spatial fields use `context_assembly.assemble_temporal_spatial()` (payload-first pattern)

---

### E-MW-1.3: Person Resolver (Stage 2 — Part 2)

**Design ref:** Architecture §19 (`memory_writer_architecture.md` lines 1691-1760)
**Pattern reference:** `PlaceResolver` in `k1/memory_writer/place_resolver.py` (O(1) exact + O(n) prefix)

#### Problem Statement

Current state: `PersonResolution` dataclass exists in `types.py` (`natural_name`, `person_id`, `confidence`, `is_provisional`). No `PersonResolver` class exists. The wiring contract places it at `k1/memory_writer/context/person_resolver.py`.

The `PersonResolver` is called by the `ExtractionValidator` (Phase 2) AFTER LLM extraction to resolve natural names in `MemoryAtom.participants` to stable `person_*` IDs. It is NOT called during context building — it's a post-extraction step. However, it's placed in the `context/` package because it reads from the same SS snapshot.

**Data source:** `ExtractionContext.active_persons: Dict[str, Any]` populated by `ContextBuilder._extract_persons()` from `beliefs_active.mentioned_entities`. Each entry: `{"person_id": "person_mom", "type": "PERSON", "confidence": 1.0}`.

**Secondary source:** `scoreboard` referents (`_referents: Dict[str, Referent]` in `ScoreboardSection`) have `entity_id` and `entity_type` fields that may carry `person_*` IDs for in-focus entities.

#### Resolution Algorithm

```
Input:  natural_name: str (e.g., "Mom", "Dr. Smith", "Panda")
        context: ExtractionContext (has active_persons, persona_context)

Step 1: Exact match (case-insensitive)
        beliefs_active.mentioned_entities where display_name.lower() == name.lower()
        → return entity.person_id, confidence=1.0, is_provisional=False

Step 2: Alias match
        persona_context may have alias mappings: {"Mom": ["Mother", "Mama"]}
        Check if name.lower() matches any alias → return primary person_id
        confidence=0.9, is_provisional=False

Step 3: Scoreboard referent match
        active_topics referents where text.lower() == name.lower()
        AND entity_type == "PERSON"
        → return referent.entity_id, confidence=0.8, is_provisional=False

Step 4: Fallback — generate provisional person_id
        sanitized = re.sub(r'[^a-z0-9_]', '_', name.lower()).strip('_')
        → return f"person_{sanitized}", confidence=0.5, is_provisional=True
```

#### PersonResolver Class

```python
_PERSON_ID_SANITIZE = re.compile(r"[^a-z0-9_]")

class PersonResolver:
    """Resolve natural names → stable person_ids.

    Follows PlaceResolver pattern: constructor builds lookup map,
    resolve() returns cached result.

    No port dependencies — reads from ExtractionContext (already built).
    """

    def resolve(self, name: str, context: ExtractionContext) -> PersonResolution:
        if not name or not name.strip():
            return PersonResolution(
                natural_name=name,
                person_id="person_unknown",
                confidence=0.0,
                is_provisional=True,
            )

        key = name.strip().lower()

        # Step 1: Exact match in active_persons
        for display_name, info in context.active_persons.items():
            if display_name.lower() == key:
                pid = info.get("person_id", "") if isinstance(info, dict) else ""
                if pid:
                    return PersonResolution(
                        natural_name=name, person_id=pid,
                        confidence=1.0, is_provisional=False,
                    )

        # Step 2: Alias match from persona_context
        aliases = context.persona_context.get("aliases", {})
        if isinstance(aliases, dict):
            for primary_name, alias_list in aliases.items():
                if isinstance(alias_list, list) and key in [a.lower() for a in alias_list]:
                    # Find person_id for primary_name
                    for dn, info in context.active_persons.items():
                        if dn.lower() == primary_name.lower():
                            pid = info.get("person_id", "") if isinstance(info, dict) else ""
                            if pid:
                                return PersonResolution(
                                    natural_name=name, person_id=pid,
                                    confidence=0.9, is_provisional=False,
                                )

        # Step 3: Scoreboard referent match (from topic_salience or active_topics context)
        # Scoreboard referents are not directly in ExtractionContext,
        # but active_persons already includes in-focus persons.
        # This step is a secondary pass — check partial matches.
        for display_name, info in context.active_persons.items():
            if key in display_name.lower() or display_name.lower() in key:
                pid = info.get("person_id", "") if isinstance(info, dict) else ""
                if pid:
                    return PersonResolution(
                        natural_name=name, person_id=pid,
                        confidence=0.8, is_provisional=False,
                    )

        # Step 4: Fallback — generate provisional person_id
        sanitized = _PERSON_ID_SANITIZE.sub("_", key).strip("_")
        if not sanitized:
            sanitized = "unknown"
        return PersonResolution(
            natural_name=name,
            person_id=f"person_{sanitized}",
            confidence=0.5,
            is_provisional=True,
        )

    def resolve_all(
        self, names: list[str], context: ExtractionContext
    ) -> list[PersonResolution]:
        """Resolve all names. Dedup by person_id, preserving order."""
        seen: set[str] = set()
        results: list[PersonResolution] = []
        for name in names:
            r = self.resolve(name, context)
            if r.person_id not in seen:
                seen.add(r.person_id)
                results.append(r)
        return results
```

#### Implementation Items

| Item | File | Work |
|------|------|------|
| I-MW-1.3.1 | `k1/memory_writer/context/person_resolver.py` | `PersonResolver` class as shown above. Imports: `re`, `typing`, `k1.memory_writer.types.PersonResolution`, `k1.memory_writer.types.ExtractionContext`. Module-level `_PERSON_ID_SANITIZE` regex |
| I-MW-1.3.2 | `k1/memory_writer/context/__init__.py` (modify) | Add re-export: `PersonResolver` |

#### Test Specification: `tests/k1/memory_writer/test_person_resolver.py`

**22 tests** organized in 5 test classes:

```text
class TestExactMatch:                       # 5 tests
  test_exact_match_case_insensitive         — "mom" matches entity "Mom" → person_mom
  test_exact_match_preserves_original_name  — natural_name="Mom" preserved in result
  test_no_match_in_empty_persons            — empty active_persons → provisional
  test_multiple_entities_first_match        — two entities, returns first match
  test_confidence_is_1_0                    — exact match → confidence=1.0

class TestAliasMatch:                       # 4 tests
  test_alias_resolves_to_primary            — "Mother" alias for "Mom" → person_mom
  test_alias_case_insensitive               — "MAMA" alias for "Mom" → person_mom
  test_no_aliases_in_persona                — persona_context has no aliases key → skip
  test_confidence_is_0_9                    — alias match → confidence=0.9

class TestPartialMatch:                     # 4 tests
  test_substring_match                      — "Dr." matches "Dr. Smith" → person_dr_smith
  test_reverse_substring                    — "Smith" partial in "Dr. Smith" → match
  test_confidence_is_0_8                    — partial match → confidence=0.8
  test_no_partial_on_short_names            — "a" should NOT match "Anna" (too short — but current impl would match; document as known behavior)

class TestFallback:                         # 5 tests
  test_unknown_name_generates_provisional   — "Zara" not known → person_zara, provisional=True
  test_sanitizes_special_characters         — "Dr. O'Brien" → person_dr_o_brien
  test_empty_name                           — "" → person_unknown
  test_whitespace_name                      — "  " → person_unknown
  test_confidence_is_0_5                    — fallback → confidence=0.5

class TestResolveAll:                       # 4 tests
  test_resolves_multiple_names              — ["Mom", "Dad"] → [person_mom, person_dad]
  test_dedup_by_person_id                   — ["Mom", "Mother"] both → person_mom → deduped to 1
  test_preserves_order                      — ["Dad", "Mom"] → [person_dad, person_mom]
  test_empty_list                           — [] → []
```

**Acceptance criteria:**

- [x] All 22 tests pass
- [x] `PersonResolver` has zero port dependencies (reads from ExtractionContext only)
- [x] Follows `PlaceResolver` pattern: no async, no I/O, pure lookup
- [x] `person_id` format: `^person_[a-z0-9_]+$` (matches MW-13-like pattern for persons)
- [x] `resolve_all()` deduplicates by `person_id`, preserves insertion order
- [x] Provisional IDs: `is_provisional=True`, `confidence=0.5`

---

### E-MW-1.4: Filter + Context Assembly Integration Test

#### Problem Statement

No end-to-end test exists for the Phase 1 pipeline stages. This integration test verifies the full per-turn flow: turn arrives → filter evaluates → if PASS, read full SS snapshot → context builder assembles ExtractionContext.

**Test adapter requirements:** Uses `FakeSessionReadPort` from `test_adapters.py` (Phase 0 E-MW-0.1 or existing adapter). The fake port returns canned snapshot dicts with `history_active`, `beliefs_active`, `scoreboard`, `narrative_active`, `affective_now`, `meta`.

#### Integration Flow

```text
Turn 1: "ok" → Filter: SKIP(EMPTY) → no SS read, no context assembly
Turn 2: "Mom called about dinner" → Filter: PASS (entity: Mom) → SS snapshot read → ContextBuilder → ExtractionContext
  → recent_turns = ALL turns in history_active (full window SS manages)
  → active_persons = {"Mom": {...}} from beliefs_active
  → tool_calls_per_turn = {} (no tool calls)
Turn 3: "She wants Italian" → Filter: PASS → SS snapshot read → ContextBuilder → ExtractionContext
  → recent_turns = ALL turns in history_active (now includes turn 3)
```

Every filter-PASS turn triggers a full SS read and context assembly. No accumulation. No gating.

#### Implementation Items

| Item | File | Work |
|------|------|------|
| I-MW-1.4.1 | `tests/k1/memory_writer/test_filter_context_integration.py` | End-to-end integration test |

#### Test Specification: `tests/k1/memory_writer/test_filter_context_integration.py`

**12 tests** in 3 test classes:

```text
class TestFilterDecisionFlow:               # 5 tests
  test_trivial_turns_never_trigger_context  — 5 "ok" turns → all SKIP → no ContextBuilder calls
  test_meaningful_turn_triggers_context     — "Mom called" → PASS → ContextBuilder produces ExtractionContext
  test_mixed_trivial_meaningful             — "ok", "Mom called", "ok", "She said yes" → 2 PASS → 2 ExtractionContext builds
  test_tool_call_boost_triggers_context     — "ok" + tool_calls → R6 PASS → ContextBuilder called
  test_dedup_prevents_double_context        — same turn_id twice → second is SKIP(DEDUP) → only 1 context build

class TestContextAssemblyFromSnapshot:      # 4 tests
  test_full_snapshot_all_sections_present   — all 13 sections in snapshot → fully populated ExtractionContext
  test_missing_sections_partial_context     — only history_active + meta → partial ExtractionContext, no error
  test_context_includes_tool_calls          — turn with tool_calls in metadata → tool_calls_per_turn populated
  test_context_includes_persons             — beliefs_active has PERSON entity "Mom" → active_persons contains "Mom"

class TestFullPipelinePhase1:               # 3 tests
  test_pass_turn_produces_full_context      — 1 meaningful turn → ExtractionContext with ALL history_active turns
  test_person_resolution_in_context         — "Mom" in user_message + beliefs_active → PersonResolver resolves → active_persons
  test_temporal_spatial_from_payload        — payload has time/location → ExtractionContext temporal/spatial fields populated
```

**Acceptance criteria:**

- [x] All 12 tests pass
- [x] Full per-turn flow exercised: Filter → MWSessionReader → ContextBuilder (+ PersonResolver)
- [x] No LLM invocations in any test (MW-07 by construction)
- [x] All tests use `FakeSessionReadPort` (no real SS dependency)
- [x] Context builder output is a valid `ExtractionContext` (all required fields present)
- [x] No accumulation gate, no pass_count, no trigger logic — pure per-turn pipeline

---

### Phase 1 Summary

| Epic | Tests | New Files | Modified Files |
|------|-------|-----------|----------------|
| E-MW-1.1 | 34 | `filter/__init__.py`, `filter/rules.py`, `filter/relevance_filter.py` | `types.py` (SkipReason enum) |
| E-MW-1.2 | 26 | `context/__init__.py`, `context/session_reader.py`, `context/context_builder.py` | `types.py` (tool_calls_per_turn field) |
| E-MW-1.3 | 22 | `context/person_resolver.py` | `context/__init__.py` |
| E-MW-1.4 | 12 | — | — |
| **Total** | **94** | **7 new files** | **3 modified files** |

**Phase 1 invariants enforced:**

- MW-01: No write ports (compile-time — no IStateWritePort in any Phase 1 file)
- MW-02: `assert_mw02_read_latency()` called in `MWSessionReader.read_snapshot()`
- MW-07: `assert_mw07_filter_no_llm()` called in `RelevanceFilter.__init__()`
- MW-13: `PersonResolver` generates `person_*` IDs matching `^person_[a-z0-9_]+$`

**Phase 1 prerequisites (from Phase 0):**

- E-MW-0.1: `__init__.py` exports all new symbols
- E-MW-0.3: `MWConfig.skip_sections: frozenset` available for `MWSessionReader`
- E-MW-0.3: `ISessionReadPort.snapshot_all(exclude)` method available

---

## 10. Phase 2 — LLM Extraction

Stage 3 of the pipeline. The **only** stage that uses LLM tokens. Everything before (filter, context assembly) and after (envelope, batch) is deterministic.

**Concurrency model:** Memory Writer is a **session-bound agent** (Architecture §17). Fabric spawns one MW instance per active session. Each instance goes ACTIVE → IDLE → ACTIVE across turns within the same session. Multiple sessions run concurrently — each has its own MW instance, its own `ExtractionContext`, its own `IModelHubPort.chat()` call. The Model Hub is stateless per-call (no semaphore), with per-provider rate limiting (RPM/TPM token buckets) and circuit breakers. The `FabricDispatcher` gates overall concurrency via `asyncio.Semaphore(max_concurrent=10)` with backpressure: MW calls are `Priority.BACKGROUND` and get **shed first** under load (95-100% utilization). This is acceptable — missed extractions are best-effort (Architecture §24).

**What the LLM does (and does NOT do):**

- **DOES:** Extract 0-6 factual statements per turn, tag 12 cognitive dimensions, detect correction/contradiction signals (v2.2), resolve temporal references into `temporal_links`, score confidence
- **DOES NOT:** Extract NER entities (UltraBERT handles with 95.2% F1 in K0 P02 M02), compute embeddings (K0 computes via UltraBERT 768-dim), resolve person_ids (PersonResolver does this post-LLM), enforce privacy bands (PrivacyEnforcer does this in Stage 4)

**Token budget:** 2000 total (MW-06). Breakdown: ~150 system prompt + ~350 context + ~200 turn payload + ~800 output (0-6 atoms × 34 fields) + ~500 headroom.

### E-MW-2.1: Writer Agent (LLM Extraction)

**Design ref:** Architecture §8, §17 (agent contract), §18 (prompt design), §35 (correction signals)
**Invariants:** MW-06 (2000 token budget), MW-10 (trace_id on all operations)

#### Problem Statement

Current state: `IModelHubPort` protocol exists with `chat(messages, budget_tokens, model_hint) -> ChatResponse`. `ModelHubAdapter` exists and translates MW's port to K1's `IModelHubPort.execute()` with `Priority.BACKGROUND`, 60s timeout. `ChatResponse` dataclass exists in `types.py` with `content`, `total_tokens`, `prompt_tokens`, `completion_tokens`, `model`, `latency_ms`. `ExtractionContext` exists with 25+ fields. `MemoryAtom` exists with 37 fields (frozen dataclass).

No `MemoryWriterAgent` class exists. The wiring contract places it at `k1/memory_writer/extraction/writer_agent.py`.

#### Agent Lifecycle (Session-Bound, Pool-Reused)

```text
Session starts
  → Fabric spawns MemoryWriterAgent (PENDING → WARMING → ACTIVE)
  → Turn 1 completes → MW pipeline → WriterAgent.extract() → ACTIVE → IDLE (pool)
  → Turn 2 completes → MW reactivated from pool (IDLE → ACTIVE) → extract() → IDLE
  → Turn 3 completes → MW reactivated from pool → extract() → IDLE
  → ...
  → Session ends → MW drained (IDLE → DRAINING → TERMINATED)
```

The agent stays warm for the entire session. No cold-start overhead after the first turn. `idle_ttl_ms: 300000` (5 minutes). The `AgentPool` in `k1/fabric/providers/agent_provider.py` manages IDLE agents: max 5 per contract name, FIFO reuse, TTL sweep.

**Concurrent sessions:** Each session has its own MW instance. 10 concurrent sessions = 10 MW instances, each calling `IModelHubPort.chat()` independently. Model Hub handles concurrency via per-provider rate limiters (not a global semaphore). FabricDispatcher's `asyncio.Semaphore(10)` is the global concurrency gate — when saturated, BACKGROUND priority MW calls are shed first.

#### MemoryWriterAgent Class

```python
class MemoryWriterAgent:
    """LLM extraction agent — the only LLM-consuming component in MW.

    Session-bound: spawned once per session, reused across turns.
    Pool-reused: goes IDLE between turns, reactivated from AgentPool.

    Invariants:
      MW-06: budget_tokens always <= config.llm_token_budget (2000)
      MW-10: trace_id propagated to every Model Hub call
    """

    def __init__(
        self,
        model_hub: IModelHubPort,
        config: MWConfig,
        prompt_loader: PromptLoader,
    ) -> None:
        self._model_hub = model_hub
        self._config = config
        self._system_prompt: str = prompt_loader.load("memory_writer_persona")

    async def extract(
        self,
        context: ExtractionContext,
        trace_id: str,
    ) -> list[RawExtraction]:
        """Extract 0-6 memory atoms from ExtractionContext via LLM.

        Args:
            context: Full SS snapshot assembled by ContextBuilder.
            trace_id: cognitive_trace_id from TurnCompletePayload (MW-10).

        Returns:
            List of RawExtraction objects (not yet validated).
            Empty list if LLM returns no extractions or errors.

        Raises:
            Nothing — errors are caught, logged, and return empty list.
            Pipeline continues (best-effort extraction per Architecture §24).
        """
        # MW-06: enforce budget before call
        assert_mw06_token_budget(self._config.llm_token_budget, self._config)

        # Serialize ExtractionContext → user prompt
        user_prompt = self._build_user_prompt(context)

        messages = [
            {"role": "system", "content": self._system_prompt},
            {"role": "user", "content": user_prompt},
        ]

        try:
            response: ChatResponse = await self._model_hub.chat(
                messages=messages,
                budget_tokens=self._config.llm_token_budget,
                model_hint=self._config.model_hint,
            )
        except Exception as exc:
            # LLM error → skip turn (best-effort, no retry here — circuit breaker handles)
            log.warning(
                "MW: LLM extraction failed",
                trace_id=trace_id,
                error=str(exc),
                error_type=type(exc).__name__,
            )
            return []

        # Parse LLM JSON output → RawExtraction list
        return self._parse_response(response, context, trace_id)

    def _build_user_prompt(self, context: ExtractionContext) -> str:
        """Serialize ExtractionContext into the user prompt template.

        Token budget: ~350 tokens for context, ~200 for turn payload.
        Compresses recent_turns to (role, text[:100], turn_number) tuples.
        Includes active_topics, current_affect, privacy band hint.
        """
        # Recent turns — compressed to fit budget
        turns_text = ""
        for t in context.recent_turns[-5:]:  # last 5 turns max to fit budget
            turns_text += f"  Turn {t.turn_number} ({t.role}): {t.text[:100]}\n"

        # Active entities from beliefs_active
        entities_text = ", ".join(
            f"{name} ({info.get('type', 'UNKNOWN')})"
            for name, info in context.active_persons.items()
        ) if context.active_persons else "none"

        # Current emotion
        emotion_text = "unknown"
        if context.current_affect:
            emotion_text = (
                f"valence={context.current_affect.valence:.1f}, "
                f"arousal={context.current_affect.arousal:.1f}"
            )

        # Active topics
        topics_text = ", ".join(context.active_topics[:5]) if context.active_topics else "none"

        # Privacy band from control context
        band = context.control_context.get("safety_band", "GREEN") if context.control_context else "GREEN"

        # Current turn
        current = context.current_turn

        return (
            f"CONTEXT:\n"
            f"  Recent turns:\n{turns_text}"
            f"  Known entities: {entities_text}\n"
            f"  Current emotion: {emotion_text}\n"
            f"  Active topics: {topics_text}\n"
            f"  Privacy band: {band}\n\n"
            f"CURRENT TURN:\n"
            f"  User: {current.text}\n"
            f"  Turn #: {current.turn_number}\n\n"
            f"Extract 0-3 factual memories from this turn. Return as JSON array."
        )

    def _parse_response(
        self,
        response: ChatResponse,
        context: ExtractionContext,
        trace_id: str,
    ) -> list[RawExtraction]:
        """Parse LLM JSON output into RawExtraction list.

        Handles:
          - Valid JSON array → list of RawExtraction
          - Empty array [] → empty list (turn had no memorable facts)
          - Malformed JSON → log warning, return empty list
          - Individual item parse failure → skip that item, keep valid ones
        """
        content = response.content.strip()
        if not content:
            return []

        # Strip markdown code fences if LLM wraps in ```json ... ```
        if content.startswith("```"):
            lines = content.split("\n")
            content = "\n".join(
                line for line in lines
                if not line.strip().startswith("```")
            ).strip()

        try:
            raw_list = json.loads(content)
        except json.JSONDecodeError as exc:
            log.warning(
                "MW: LLM returned malformed JSON",
                trace_id=trace_id,
                content_preview=content[:200],
                error=str(exc),
            )
            return []

        if not isinstance(raw_list, list):
            log.warning(
                "MW: LLM returned non-array JSON",
                trace_id=trace_id,
                json_type=type(raw_list).__name__,
            )
            return []

        extractions: list[RawExtraction] = []
        for i, item in enumerate(raw_list[:6]):  # hard cap at 6 (MW-05)
            if not isinstance(item, dict):
                continue
            try:
                ext = RawExtraction(
                    text=str(item.get("text", "")),
                    participants=list(item.get("participants", [])),
                    location_name=item.get("location_name"),
                    location_type=item.get("location_type"),
                    activity_type=item.get("activity_type"),
                    topics=list(item.get("topics", [])),
                    sentiment_label=item.get("sentiment_label", "neutral"),
                    emotion_tags=list(item.get("emotion_tags", [])),
                    categories=list(item.get("categories", [])),
                    confidence=float(item.get("confidence", 0.0)),
                    temporal_links=self._parse_temporal_links(item.get("temporal_links", [])),
                    # v2.2 correction signals
                    correction_signal=bool(item.get("correction_signal", False)),
                    contradiction_signal=bool(item.get("contradiction_signal", False)),
                    supersedes_concept=item.get("supersedes_concept"),
                    correction_source=item.get("correction_source"),
                    # Narrative context
                    narrative=item.get("narrative"),
                    social_context=item.get("social_context"),
                    social_intimacy=item.get("social_intimacy"),
                    intent_type=item.get("intent_type"),
                    identity_domains=list(item.get("identity_domains", [])),
                    # Cognitive dimensions
                    source_type=item.get("source_type", "user_stated"),
                    novelty=item.get("novelty", "EXPECTED"),
                    elaboration_depth=item.get("elaboration_depth", "MENTION"),
                    temporal_orientation=item.get("temporal_orientation", "PAST"),
                    # Affect (VAD triple)
                    affect=item.get("affect"),
                    # Metadata injected from context (not LLM output)
                    session_id=context.session_id,
                    conversation_turn=context.conversation_turn,
                    extraction_sequence=i,
                    trace_id=trace_id,
                )
                extractions.append(ext)
            except (ValueError, TypeError, KeyError) as exc:
                log.warning(
                    "MW: Failed to parse extraction item",
                    trace_id=trace_id,
                    item_index=i,
                    error=str(exc),
                )
                continue

        return extractions

    def _parse_temporal_links(self, raw_links: list) -> list[dict]:
        """Parse temporal_links from LLM output.

        Each link: {mentioned_time, link_type, uncertainty_window_ms, confidence}
        Max 5 per atom (MW-12). Invalid entries silently dropped.
        """
        if not isinstance(raw_links, list):
            return []
        links = []
        for link in raw_links[:5]:  # MW-12 cap
            if isinstance(link, dict) and link.get("mentioned_time"):
                links.append({
                    "mentioned_time": str(link.get("mentioned_time", "")),
                    "link_type": str(link.get("link_type", "CONCURRENT")),
                    "uncertainty_window_ms": int(link.get("uncertainty_window_ms", 0)),
                    "confidence": float(link.get("confidence", 1.0)),
                })
        return links
```

#### RawExtraction Dataclass

The intermediate representation between LLM output parsing and validation. NOT frozen — the validator may mutate fields (truncate text, resolve participants).

```python
@dataclass
class RawExtraction:
    """Mutable intermediate between LLM parse and validation.

    NOT frozen — ExtractionValidator may:
      - Truncate text to 50 words (MW-04)
      - Replace participants with PersonResolution results
      - Strip location under RED band
    """

    # Core content
    text: str = ""
    topics: list[str] = field(default_factory=list)
    categories: list[str] = field(default_factory=list)
    activity_type: str | None = None

    # Participants (natural names — not yet resolved)
    participants: list[str] = field(default_factory=list)
    social_context: str | None = None
    social_intimacy: str | None = None

    # Location
    location_name: str | None = None
    location_type: str | None = None

    # Emotion
    sentiment_label: str = "neutral"
    emotion_tags: list[str] = field(default_factory=list)
    affect: dict | None = None  # {"valence": float, "arousal": float, "dominance": float}

    # Temporal
    temporal_links: list[dict] = field(default_factory=list)
    temporal_orientation: str = "PAST"

    # Cognitive dimensions
    source_type: str = "user_stated"
    novelty: str = "EXPECTED"
    elaboration_depth: str = "MENTION"
    intent_type: str | None = None
    identity_domains: list[str] = field(default_factory=list)
    confidence: float = 0.0

    # Narrative
    narrative: dict | None = None

    # v2.2 correction signals
    correction_signal: bool = False
    contradiction_signal: bool = False
    supersedes_concept: str | None = None
    correction_source: str | None = None

    # Metadata (injected from context, not LLM output)
    session_id: str = ""
    conversation_turn: int = 0
    extraction_sequence: int = 0
    trace_id: str = ""
```

#### PromptLoader

```python
class PromptLoader:
    """Load prompt templates from the extraction/prompts/ directory.

    Templates are markdown files with the system prompt text.
    Loaded once at agent creation, cached for session lifetime.
    """

    def __init__(self, prompts_dir: Path) -> None:
        self._dir = prompts_dir
        self._cache: dict[str, str] = {}

    def load(self, name: str) -> str:
        """Load a named prompt template. Cached after first load."""
        if name not in self._cache:
            path = self._dir / f"{name}.md"
            self._cache[name] = path.read_text(encoding="utf-8")
        return self._cache[name]
```

#### System Prompt: `memory_writer_persona.md`

The full prompt content per Architecture §18. Key sections:

1. **Identity:** "You are KO's Memory Writer" — extraction role statement
2. **Rules (8 rules):** Extract 1-3 per turn, max 50 words, self-contained, factual only, natural names for people, past/present tense
3. **12 cognitive dimensions:** sentiment_label (5-class), affect (VAD triple), novelty (4-level), elaboration_depth (4-level), temporal_orientation (3-class), source_type (4-class), arc_position (4-class via narrative), social_intimacy (3-level), social_context (6-class), intent_type (8-class), activity_type (20-class), identity_domains (9-class multi-select)
4. **temporal_links instructions:** 6 link types (RETROSPECTIVE, PROSPECTIVE, CONCURRENT, HABITUAL, CONTEXTUAL, CONDITIONAL), uncertainty_window_ms examples, max 5 per atom
5. **Correction signal detection (v2.2):** 3 detection patterns — explicit correction ("Actually X is now Y"), implicit correction (behavior change), context change ("We moved to Portland"). Set `correction_signal: true`, `supersedes_concept: "domain:value"`, `correction_source`. Err on NOT flagging (false positive is worse than false negative — Architecture §35)
6. **Output JSON schema:** Array of objects matching MemoryAtom field names. Empty `[]` for turns with no memorable facts
7. **NER exclusion (§5.9 G7):** "Do NOT extract named entities. Use natural names for people. The system resolves person_ids. UltraBERT handles NER downstream."
8. **Few-shot examples:** 2-3 examples showing single-fact and multi-fact extraction with correction signals

**Design decision on NER (§5.9 G7):** MW's LLM does NOT extract NER entities — UltraBERT in P02 M02 handles NER with 95.2% F1 (general) and 80.0% F1 (family). MW focuses on what LLMs uniquely do: correction detection, temporal reasoning, narrative arc understanding. MW passes entities pre-extracted by Concierge in SS turns as hints only (via `ExtractionContext.active_persons`).

#### Implementation Items

| Item | File | Work |
|------|------|------|
| I-MW-2.1.1 | `k1/memory_writer/extraction/__init__.py` | Package init. Re-exports: `MemoryWriterAgent`, `RawExtraction`, `PromptLoader` |
| I-MW-2.1.2 | `k1/memory_writer/extraction/writer_agent.py` | `MemoryWriterAgent` class as shown above. Imports: `json`, `logging`, `k1.memory_writer.ports.model_hub_port.IModelHubPort`, `k1.memory_writer.config.MWConfig`, `k1.memory_writer.types.ChatResponse`, `k1.memory_writer.types.ExtractionContext`, `k1.memory_writer.invariants.assert_mw06_token_budget` |
| I-MW-2.1.3 | `k1/memory_writer/extraction/raw_extraction.py` | `RawExtraction` dataclass (mutable). `PromptLoader` class. Imports: `dataclasses`, `pathlib`, `typing` |
| I-MW-2.1.4 | `k1/memory_writer/extraction/prompts/memory_writer_persona.md` | System prompt (~150 tokens): 8 extraction rules, 12 cognitive dimensions, temporal_links spec, correction signal detection, few-shot examples, JSON output schema |
| I-MW-2.1.5 | `tests/k1/memory_writer/test_writer_agent.py` | 32 tests (see test specification below) |

#### Test Specification: `tests/k1/memory_writer/test_writer_agent.py`

**32 tests** organized in 7 test classes:

```text
class TestWriterAgentExtract:                       # 6 tests
  test_single_extraction_from_meaningful_turn        — "Had dinner with Mom" → 1 RawExtraction with text, participants, topics
  test_multi_extraction_from_complex_turn             — "Dinner with Mom + dentist tomorrow" → 2 RawExtractions
  test_empty_extraction_for_trivial_response         — LLM returns [] → empty list (turn had no memorable facts)
  test_extraction_has_session_metadata               — session_id, conversation_turn, extraction_sequence injected from context
  test_extraction_has_trace_id                       — trace_id propagated to every RawExtraction (MW-10)
  test_max_6_extractions_enforced                    — LLM returns 8 items → capped at 6 (MW-05)

class TestWriterAgentBudget:                        # 4 tests
  test_mw06_budget_enforced                          — budget_tokens=2000 passed to IModelHubPort.chat()
  test_mw06_violation_raises                         — config.llm_token_budget=3000 → InvariantViolation
  test_model_hint_from_config                        — config.model_hint="cheapest" passed to chat()
  test_response_token_usage_captured                 — ChatResponse.total_tokens available for logging

class TestWriterAgentErrorHandling:                 # 5 tests
  test_llm_exception_returns_empty                   — IModelHubPort.chat() raises → empty list, no propagation
  test_llm_timeout_returns_empty                     — chat() raises TimeoutError → empty list (best-effort)
  test_circuit_breaker_open_returns_empty             — chat() raises circuit breaker error → empty list
  test_malformed_json_returns_empty                  — LLM returns "not json" → empty list, warning logged
  test_non_array_json_returns_empty                  — LLM returns {"text": "..."} → empty list

class TestWriterAgentParsing:                       # 5 tests
  test_parses_all_34_fields                          — LLM returns full atom → all fields populated in RawExtraction
  test_missing_optional_fields_use_defaults          — LLM omits location_name → None, omits emotion_tags → []
  test_markdown_code_fence_stripped                   — LLM wraps in ```json ... ``` → fences stripped before parse
  test_partial_array_keeps_valid_items               — 3 items, item 2 malformed → returns item 1 and 3
  test_confidence_parsed_as_float                    — "confidence": "0.95" (string) → float(0.95)

class TestWriterAgentTemporalLinks:                 # 4 tests
  test_parses_temporal_links_array                   — temporal_links with 3 entries → 3 link dicts
  test_caps_at_5_links                               — 7 temporal_links → only first 5 kept (MW-12)
  test_invalid_link_dropped                          — link missing mentioned_time → silently dropped
  test_empty_temporal_links                          — temporal_links: [] or absent → empty list

class TestWriterAgentCorrectionSignals:             # 4 tests
  test_correction_signal_parsed                      — correction_signal: true → RawExtraction.correction_signal=True
  test_contradiction_signal_parsed                   — contradiction_signal: true → parsed
  test_supersedes_concept_parsed                     — "cuisine_preference:italian" → RawExtraction.supersedes_concept
  test_correction_defaults_to_false                  — no correction fields in LLM output → all False/None

class TestWriterAgentPromptBuilding:                # 4 tests
  test_prompt_includes_recent_turns                  — 5 recent turns → last 5 in CONTEXT section
  test_prompt_includes_active_entities               — active_persons → "Known entities: Mom (PERSON), ..."
  test_prompt_includes_current_turn                  — current_turn.text in CURRENT TURN section
  test_prompt_truncates_long_turn_text               — turn text 500 chars → truncated to 100 in prompt
```

**Acceptance criteria:**

- [x] All 32 tests pass
- [x] `MemoryWriterAgent` calls `IModelHubPort.chat()` with `budget_tokens=config.llm_token_budget`
- [x] MW-06 enforced via `assert_mw06_token_budget()` before every call
- [x] MW-10: `trace_id` propagated to every RawExtraction and logged on every call
- [x] LLM errors caught and return empty list — never propagated (best-effort extraction)
- [x] RawExtraction is mutable (not frozen) — validator will mutate fields
- [x] `PromptLoader` caches system prompt for session lifetime (no re-read per turn)
- [x] Correction signals (v2.2) parsed: `correction_signal`, `contradiction_signal`, `supersedes_concept`, `correction_source`
- [x] `temporal_links` capped at 5 per extraction (MW-12)
- [x] Session metadata (`session_id`, `conversation_turn`, `extraction_sequence`) injected from `ExtractionContext`, not from LLM output

---

### E-MW-2.2: Extraction Validator (Post-LLM, Deterministic)

**Design ref:** Architecture §8 (validator section), §19 (Person Resolver integration), §20 (privacy band), §35 (correction signal flow)
**Invariants:** MW-04 (≤50 words), MW-05 (≤6 atoms), MW-12 (temporal_links ≤5 per atom)

#### Problem Statement

Current state: Invariant assertion functions exist in `invariants.py` — `assert_mw04_text_length()`, `assert_mw05_atom_count()`, `assert_mw12_temporal_links()`. `PersonResolver` exists (Phase 1 E-MW-1.3) with `resolve_all(names, context) -> list[PersonResolution]`. `RawExtraction` is mutable (Phase 2 E-MW-2.1).

No `ExtractionValidator` class exists. The wiring contract places it at `k1/memory_writer/extraction/extraction_validator.py`.

The validator is the **deterministic post-LLM cleanup** — it takes raw LLM output and produces validated `MemoryAtom` objects ready for envelope building. No LLM cost. No I/O.

#### Validation Pipeline (5 checks, in order)

| # | Check | Invariant | Action on Failure |
|---|-------|-----------|-------------------|
| 1 | **Text length** | MW-04 (≤50 words) | Truncate to 50 words (warn, don't drop) |
| 2 | **Required fields** | — | Drop extraction if `text` or `topics` empty |
| 3 | **Participant resolution** | MW-13 (person_id format) | PersonResolver: natural names → `person_*` IDs. Provisional IDs for unknowns |
| 4 | **Confidence threshold** | config.confidence_floor (0.30) | Drop extraction below threshold |
| 5 | **temporal_links validation** | MW-12 (≤5 links, valid types) | Truncate to 5 links, drop links with invalid link_type |

After all checks: cap at 6 atoms total (MW-05). Return `list[MemoryAtom]` (frozen).

#### ExtractionValidator Class

```python
class ExtractionValidator:
    """Post-LLM deterministic validation. Produces validated MemoryAtom list.

    No LLM cost. No I/O. Pure validation + field normalization.
    PersonResolver called here (not in extraction stage).
    """

    def __init__(
        self,
        person_resolver: PersonResolver,
        config: MWConfig,
    ) -> None:
        self._person_resolver = person_resolver
        self._config = config

    def validate(
        self,
        extractions: list[RawExtraction],
        context: ExtractionContext,
    ) -> list[MemoryAtom]:
        """Validate and convert RawExtractions → MemoryAtom list.

        Args:
            extractions: Mutable RawExtractions from WriterAgent.
            context: ExtractionContext for PersonResolver and metadata.

        Returns:
            List of validated, frozen MemoryAtom objects.
            May be empty if all extractions fail validation.
        """
        validated: list[MemoryAtom] = []

        for ext in extractions:
            # Check 1: Text length (MW-04) — truncate, don't drop
            if len(ext.text.split()) > self._config.max_text_words:
                words = ext.text.split()[:self._config.max_text_words]
                ext.text = " ".join(words)
                log.warning(
                    "MW: truncated extraction to max words",
                    turn_id=ext.trace_id,
                    max_words=self._config.max_text_words,
                )

            # Check 2: Required fields — drop if missing
            if not ext.text or not ext.text.strip():
                log.warning("MW: dropped extraction, empty text", trace_id=ext.trace_id)
                continue
            if not ext.topics:
                log.warning("MW: dropped extraction, no topics", trace_id=ext.trace_id)
                continue

            # Check 3: Participant resolution (PersonResolver from Phase 1)
            resolved_participants: list[str] = []
            if ext.participants:
                resolutions = self._person_resolver.resolve_all(
                    ext.participants, context
                )
                resolved_participants = [r.person_id for r in resolutions]

            # Check 4: Confidence threshold
            if ext.confidence < self._config.confidence_floor:
                log.info(
                    "MW: dropped low-confidence extraction",
                    trace_id=ext.trace_id,
                    confidence=ext.confidence,
                    floor=self._config.confidence_floor,
                )
                continue

            # Check 5: temporal_links validation (MW-12)
            validated_links = self._validate_temporal_links(ext.temporal_links)

            # Convert to frozen MemoryAtom
            atom = self._build_atom(ext, resolved_participants, validated_links, context)
            validated.append(atom)

        # MW-05: cap at max atoms per turn
        if len(validated) > self._config.max_atoms_per_turn:
            log.warning(
                "MW: capping atoms to max per turn",
                count=len(validated),
                max=self._config.max_atoms_per_turn,
            )
            validated = validated[:self._config.max_atoms_per_turn]

        return validated

    def _validate_temporal_links(self, raw_links: list[dict]) -> tuple[TemporalLink, ...]:
        """Validate and convert temporal_links. MW-12: max 5, valid types."""
        valid_types = {t.value for t in TemporalLinkType}
        links: list[TemporalLink] = []
        for link in raw_links[:self._config.max_temporal_links_per_atom]:
            link_type = link.get("link_type", "CONCURRENT")
            if link_type not in valid_types:
                continue  # drop invalid link_type
            links.append(TemporalLink(
                mentioned_time=str(link.get("mentioned_time", "")),
                resolved_epoch_ms=int(link.get("resolved_epoch_ms", 0)),
                uncertainty_window_ms=int(link.get("uncertainty_window_ms", 0)),
                link_type=link_type,
                confidence=float(link.get("confidence", 1.0)),
            ))
        return tuple(links)

    def _build_atom(
        self,
        ext: RawExtraction,
        resolved_participants: list[str],
        validated_links: tuple[TemporalLink, ...],
        context: ExtractionContext,
    ) -> MemoryAtom:
        """Convert validated RawExtraction → frozen MemoryAtom.

        Normalizes enum values (str → Enum), injects session metadata,
        builds nested frozen dataclasses (Affect, Narrative).
        """
        # Normalize enums with safe fallbacks
        sentiment = _safe_enum(SentimentLabel, ext.sentiment_label, SentimentLabel.NEUTRAL)
        source_type = _safe_enum(SourceType, ext.source_type, SourceType.USER_STATED)
        novelty = _safe_enum(NoveltyLevel, ext.novelty, NoveltyLevel.EXPECTED)
        elaboration = _safe_enum(ElaborationDepth, ext.elaboration_depth, ElaborationDepth.MENTION)
        temporal_orient = _safe_enum(TemporalOrientation, ext.temporal_orientation, TemporalOrientation.PAST)
        activity = _safe_enum(ActivityType, ext.activity_type, None) if ext.activity_type else None
        location_type = _safe_enum(LocationType, ext.location_type, None) if ext.location_type else None
        social_ctx = _safe_enum(SocialContext, ext.social_context, None) if ext.social_context else None
        social_int = _safe_enum(SocialIntimacy, ext.social_intimacy, None) if ext.social_intimacy else None
        intent = _safe_enum(IntentType, ext.intent_type, None) if ext.intent_type else None

        # Build Affect from dict
        affect = Affect(0.0, 0.0, 0.5)
        if isinstance(ext.affect, dict):
            affect = Affect(
                valence=float(ext.affect.get("valence", 0.0)),
                arousal=float(ext.affect.get("arousal", 0.0)),
                dominance=float(ext.affect.get("dominance", 0.5)),
            )

        # Build Narrative from dict
        narrative = None
        if isinstance(ext.narrative, dict):
            arc_pos = _safe_enum(ArcPosition, ext.narrative.get("arc_position"), ArcPosition.EXPOSITION)
            narrative = Narrative(
                thread_id=str(ext.narrative.get("thread_id", "")),
                arc_position=arc_pos,
                is_goal_event=bool(ext.narrative.get("is_goal_event", False)),
            )

        return MemoryAtom(
            text=ext.text,
            topics=ext.topics,
            categories=ext.categories,
            activity_type=activity,
            participants=resolved_participants,
            location_name=ext.location_name,
            location_type=location_type,
            sentiment_label=sentiment,
            emotion_tags=ext.emotion_tags,
            affect=affect,
            narrative=narrative,
            temporal_links=validated_links,
            temporal_orientation=temporal_orient,
            source_type=source_type,
            novelty=novelty,
            elaboration_depth=elaboration,
            identity_domains=ext.identity_domains,
            intent_type=intent,
            social_context=social_ctx,
            social_intimacy=social_int,
            confidence=ext.confidence,
            session_id=ext.session_id,
            conversation_turn=ext.conversation_turn,
            extraction_sequence=ext.extraction_sequence,
            language="en",
            conversation_anchor_ms=context.turn_timestamp_ms,
            # v2.2 correction signals — pass through unchanged
            correction_signal=ext.correction_signal,
            contradiction_signal=ext.contradiction_signal,
            supersedes_concept=ext.supersedes_concept,
            correction_source=ext.correction_source,
            session_context_id=ext.session_id,  # audit trail
        )


def _safe_enum(enum_cls, value, default):
    """Safely convert a string to an enum value. Returns default on failure."""
    if value is None:
        return default
    try:
        return enum_cls(value)
    except (ValueError, KeyError):
        return default
```

#### Implementation Items

| Item | File | Work |
|------|------|------|
| I-MW-2.2.1 | `k1/memory_writer/extraction/extraction_validator.py` | `ExtractionValidator` class as shown above. `_safe_enum()` helper. Imports: `logging`, `k1.memory_writer.config.MWConfig`, `k1.memory_writer.types.*` (MemoryAtom, Affect, Narrative, TemporalLink, all enums), `k1.memory_writer.context.person_resolver.PersonResolver` |
| I-MW-2.2.2 | `k1/memory_writer/extraction/__init__.py` (modify) | Add re-export: `ExtractionValidator` |
| I-MW-2.2.3 | `tests/k1/memory_writer/test_extraction_validator.py` | 30 tests (see test specification below) |

#### Test Specification: `tests/k1/memory_writer/test_extraction_validator.py`

**30 tests** organized in 7 test classes:

```text
class TestTextLengthCheck:                          # 4 tests
  test_short_text_passes                             — 10 words → unchanged
  test_50_words_passes                               — exactly 50 words → unchanged
  test_51_words_truncated                            — 51 words → truncated to 50
  test_100_words_truncated                           — 100 words → truncated to 50, warning logged

class TestRequiredFieldsCheck:                      # 4 tests
  test_empty_text_dropped                            — text="" → dropped, not in output
  test_whitespace_text_dropped                       — text="   " → dropped
  test_empty_topics_dropped                          — topics=[] → dropped
  test_valid_text_and_topics_passes                  — text="fact", topics=["family"] → passes

class TestParticipantResolution:                    # 5 tests
  test_natural_names_resolved_to_person_ids          — ["Mom", "Dad"] → ["person_mom", "person_dad"]
  test_unknown_name_gets_provisional_id              — ["Zara"] → ["person_zara"] (provisional)
  test_empty_participants_stays_empty                 — [] → []
  test_dedup_after_resolution                        — ["Mom", "Mother"] both → person_mom → deduped
  test_person_resolver_receives_context              — PersonResolver.resolve_all() called with correct ExtractionContext

class TestConfidenceThreshold:                      # 4 tests
  test_above_floor_passes                            — confidence=0.5 > 0.3 → passes
  test_at_floor_passes                               — confidence=0.3 → passes
  test_below_floor_dropped                           — confidence=0.2 < 0.3 → dropped
  test_zero_confidence_dropped                       — confidence=0.0 → dropped

class TestTemporalLinksValidation:                  # 5 tests
  test_valid_links_preserved                         — 3 valid links → 3 TemporalLink objects
  test_caps_at_5_links                               — 7 links → only first 5 (MW-12)
  test_invalid_link_type_dropped                     — link_type="INVALID" → dropped
  test_missing_mentioned_time_kept_with_default      — mentioned_time="" → kept (empty is valid)
  test_links_converted_to_frozen_tuple               — returns tuple[TemporalLink, ...] (immutable)

class TestAtomConstruction:                         # 4 tests
  test_all_fields_populated                          — full RawExtraction → MemoryAtom with all 37 fields
  test_invalid_enum_values_use_defaults              — sentiment_label="INVALID" → SentimentLabel.NEUTRAL
  test_affect_from_dict                              — {"valence": 0.7, "arousal": 0.3} → Affect(0.7, 0.3, 0.5)
  test_correction_signals_passed_through             — correction_signal=True → MemoryAtom.correction_signal=True

class TestValidatorIntegrated:                      # 4 tests
  test_mixed_valid_invalid_extractions               — 5 extractions, 2 invalid → 3 MemoryAtom
  test_mw05_cap_at_6_atoms                           — 8 valid extractions → 6 MemoryAtom (MW-05)
  test_empty_input_returns_empty                     — [] → []
  test_all_dropped_returns_empty                     — 3 extractions all below confidence → []
```

**Acceptance criteria:**

- [x] All 30 tests pass
- [x] MW-04: Text truncated to `config.max_text_words` (50), never dropped for length
- [x] MW-05: Output capped at `config.max_atoms_per_turn` (6)
- [x] MW-12: `temporal_links` capped at `config.max_temporal_links_per_atom` (5), invalid types dropped
- [x] `PersonResolver.resolve_all()` called with `ExtractionContext` — not with snapshot dict
- [x] Output is `list[MemoryAtom]` (frozen dataclasses) — immutable after validation
- [x] `RawExtraction` fields mutated in-place (text truncation) before atom construction
- [x] Enum normalization: invalid enum string values fall back to safe defaults, never raise
- [x] v2.2 correction signals passed through unchanged to MemoryAtom
- [x] `conversation_anchor_ms` set from `context.turn_timestamp_ms` — never from LLM output

---

### E-MW-2.3: Extraction Integration Test

**Design ref:** Full Phase 2 pipeline: ExtractionContext → MemoryWriterAgent → ExtractionValidator → validated `list[MemoryAtom]`

#### Problem Statement

No end-to-end test exists for Phase 2. This integration test verifies:

1. WriterAgent calls `IModelHubPort.chat()` with correct messages and budget
2. LLM response parsed into `RawExtraction` list
3. ExtractionValidator applies all 5 checks
4. PersonResolver resolves natural names
5. Output is valid `list[MemoryAtom]` with all fields populated

**Test adapter requirements:** Uses `FakeModelHubPort` that returns canned `ChatResponse` objects with pre-written JSON content. `FakeSessionReadPort` for snapshot. `PersonResolver` with canned `active_persons`.

#### Integration Flow

```text
ExtractionContext (from Phase 1):
  current_turn: CompressedTurn("t1", "user", "Had dinner with Mom at Olive Garden", 1000, 5)
  recent_turns: [turn 3, turn 4, turn 5]
  active_persons: {"Mom": {"person_id": "person_mom", "type": "PERSON"}}
  active_topics: ["family", "dining"]
  session_id: "session-abc"
  conversation_turn: 5

WriterAgent.extract(context, trace_id="trace-xyz"):
  → Builds user prompt with CONTEXT + CURRENT TURN sections
  → Calls IModelHubPort.chat(messages, budget_tokens=2000, model_hint="cheapest")
  → FakeModelHubPort returns ChatResponse with:
    [{"text": "Had dinner with Mom at Olive Garden",
      "participants": ["Mom"], "location_name": "Olive Garden",
      "activity_type": "MEAL", "topics": ["family", "dining"],
      "sentiment_label": "positive", "emotion_tags": ["contentment"],
      "confidence": 0.95}]

ExtractionValidator.validate(raw_extractions, context):
  → Check 1: text 7 words ≤ 50 → OK
  → Check 2: text non-empty, topics non-empty → OK
  → Check 3: PersonResolver: "Mom" → person_mom (confidence=1.0)
  → Check 4: confidence 0.95 ≥ 0.30 → OK
  → Check 5: temporal_links=[] → OK

Output: [MemoryAtom(text="Had dinner with Mom at Olive Garden",
         participants=["person_mom"], location_name="Olive Garden",
         activity_type=ActivityType.MEAL, ...)]
```

#### Concurrent Session Test Scenario

```text
Session A (trace_id="trace-a"):
  ExtractionContext: "Had dinner with Mom"
  → WriterAgent-A.extract() → IModelHubPort.chat() → ChatResponse-A
  → Validator-A → [MemoryAtom-A]

Session B (trace_id="trace-b"):  (concurrent, separate MW instance)
  ExtractionContext: "Went to dentist tomorrow"
  → WriterAgent-B.extract() → IModelHubPort.chat() → ChatResponse-B
  → Validator-B → [MemoryAtom-B]

Verify: trace_ids don't leak between sessions.
Verify: Each session gets its own ExtractionContext with correct session_id.
```

#### Implementation Items

| Item | File | Work |
|------|------|------|
| I-MW-2.3.1 | `tests/k1/memory_writer/test_extraction_integration.py` | End-to-end integration test. 16 tests (see below) |

#### Test Specification: `tests/k1/memory_writer/test_extraction_integration.py`

**16 tests** in 4 test classes:

```text
class TestSingleSessionExtraction:                  # 5 tests
  test_single_atom_end_to_end                        — 1 extraction: context → agent → validator → 1 MemoryAtom
  test_multi_atom_end_to_end                         — LLM returns 3 items → 3 MemoryAtom with resolved participants
  test_empty_extraction_end_to_end                   — LLM returns [] → empty list, no MemoryAtom
  test_partial_valid_end_to_end                      — 3 raw, 1 below confidence → 2 MemoryAtom
  test_correction_signal_end_to_end                  — LLM returns correction_signal=true → MemoryAtom has correction_signal=True

class TestConcurrentSessionExtraction:              # 3 tests
  test_two_sessions_concurrent                       — asyncio.gather(agent_a.extract(), agent_b.extract()) → separate results
  test_trace_ids_isolated_between_sessions           — session A trace_id != session B trace_id in output
  test_session_ids_isolated                           — session A session_id != session B session_id in MemoryAtom

class TestExtractionErrorRecovery:                  # 4 tests
  test_llm_failure_produces_empty                    — FakeModelHub raises → empty list, no crash
  test_llm_malformed_json_produces_empty             — FakeModelHub returns invalid JSON → empty list
  test_validator_drops_all_produces_empty             — all extractions below confidence → empty list
  test_llm_timeout_produces_empty                    — FakeModelHub raises TimeoutError → empty list

class TestExtractionMetrics:                        # 4 tests
  test_token_usage_available_after_extraction         — ChatResponse.total_tokens accessible for metrics
  test_latency_available_after_extraction             — ChatResponse.latency_ms accessible
  test_extraction_count_matches_output               — 2 extractions → 2 MemoryAtom
  test_budget_enforcement_in_integration              — MW-06: budget_tokens=2000 passed in the actual chat() call
```

**Acceptance criteria:**

- [x] All 16 tests pass
- [x] Full pipeline exercised: ExtractionContext → MemoryWriterAgent → ExtractionValidator → MemoryAtom
- [x] Concurrent session test proves trace_id/session_id isolation
- [x] FakeModelHubPort used — no real LLM calls
- [x] PersonResolver integration verified (natural names → person_ids in output)
- [x] Error scenarios return empty list — never crash the pipeline
- [x] All MemoryAtom objects in output are frozen (immutable)

---

### Phase 2 Summary

| Epic | Tests | New Files | Modified Files |
|------|-------|-----------|----------------|
| E-MW-2.1 | 32 | `extraction/__init__.py`, `extraction/writer_agent.py`, `extraction/raw_extraction.py`, `extraction/prompts/memory_writer_persona.md` | — |
| E-MW-2.2 | 30 | `extraction/extraction_validator.py` | `extraction/__init__.py` |
| E-MW-2.3 | 16 | — | — |
| **Total** | **78** | **5 new files** | **1 modified file** |

**Phase 2 invariants enforced:**

- MW-04: `assert_mw04_text_length()` — text truncated to 50 words in ExtractionValidator
- MW-05: `assert_mw05_atom_count()` — output capped at 6 atoms in ExtractionValidator
- MW-06: `assert_mw06_token_budget()` — budget enforced before every IModelHubPort.chat() call
- MW-10: `trace_id` propagated from TurnCompletePayload through all RawExtractions and MemoryAtoms
- MW-12: `assert_mw12_temporal_links()` — links capped at 5 per atom, invalid types dropped

**Phase 2 prerequisites (from Phase 1):**

- E-MW-1.2: `ExtractionContext` with all SS sections populated (input to WriterAgent)
- E-MW-1.3: `PersonResolver.resolve_all()` (called by ExtractionValidator)

**Phase 2 outputs (consumed by Phase 3):**

- `list[MemoryAtom]` — frozen, validated, with resolved person_ids and temporal_links
- Ready for EnvelopeBuilder (Stage 4) field mapping and PrivacyEnforcer band stripping

---

## 11. Phase 3 — Envelope + Batch + Bridge

Stages 4 and 5. **Deterministic, zero LLM cost.** Pure field mapping, privacy enforcement, batching, and Bridge submission. These stages take the validated `list[MemoryAtom]` from Phase 2 and produce the final K0-compatible command envelopes.

**Stage 4 (Envelope)** has two substages:

1. **FieldMapper + EnvelopeBuilder:** MemoryAtom → K0 body dict (34-field mapping + 7 derived fields + 9 headers). Includes K0 gap fixes G1-G4, G8 (§5.9).
2. **PrivacyEnforcer:** Band-based field stripping (GREEN/AMBER/RED) before Bridge submission. Defense-in-depth — K0 Gate also enforces, but MW strips early to minimize in-transit exposure.

**Stage 5 (Batch + Bridge)** collects envelopes into a 250ms time window, deduplicates within the batch, then submits to Bridge via `IBridgeCommandPort.submit_batch()`. Fire-and-forget — Bridge handles signing, `idem_key`, SHA-256, and offline queueing (LocalOutbox, MW-09).

**K1 never handles cryptographic signing.** Headers set by MW: `cognitive_trace_id`, `tenant_id`, `space_id`, `topic`, `schema_uri`, `schema_version`, `actor`, `device_id`, `band`. Headers set by Bridge: `sig_alg`, `sig_kid`, `envelope_sha256`, `sig`, `idem_key` (Architecture §12).

**Dependencies:** Phase 2 must be complete (validated `list[MemoryAtom]` with resolved person_ids). Phase 0 E-MW-0.4 (PlaceResolver with `resolve_with_geohash()`) needed for G5/G6 geohash + place_id.

---

### E-MW-3.1: Envelope Builder + FieldMapper (Stage 4 — Part 1)

**Design ref:** Architecture §9 (field mapping table), §11 (K0 body contract, 37 fields), §12 (headers)
**Invariants:** MW-10 (trace_id on all envelopes), MW-13 (place_id format)

#### Problem Statement

Current state: `MWEnvelope` frozen dataclass exists in `types.py` with `topic`, `schema_uri`, `trace_id`, `atom`. `IBridgeCommandPort` protocol exists with `submit()` and `submit_batch()` — both accept body dicts, not typed `MWEnvelope` objects. The Bridge expects a JSON body dict conforming to `memory_atom.v2.schema.json` (37 fields) plus 7 K0-required derived fields.

No `FieldMapper` or `EnvelopeBuilder` class exists. The wiring contract places them at `k1/memory_writer/envelope/`.

**Key complexity:** The FieldMapper must:

1. Map all 37 MemoryAtom fields to K0 body dict keys (some renames, some direct copies)
2. Derive 7 K0-required observation fields that are NOT in MemoryAtom (K0 gaps G1-G4, G5-G6, G8)
3. Serialize frozen dataclasses (Affect, Narrative, TemporalLink) to plain dicts
4. Handle None/empty values gracefully — K0 Gate rejects malformed bodies

#### FieldMapper Class

```python
class FieldMapper:
    """Map MemoryAtom → K0 envelope body dict.

    34 direct field mappings + 7 derived observation fields.
    All transformations are deterministic. No LLM, no I/O.

    K0 gap fixes (§5.9):
      G1: sentiment_score from sentiment_label (SENTIMENT_TO_SCORE)
      G2: dominant_emotion from emotion_tags[0]
      G3: dominant_emotions_json from emotion_tags with confidence
      G4: affect_valence from affect.valence (flattened)
      G5: geohash_6 from PlaceResolver.resolve_with_geohash()
      G6: place_id from PlaceResolver.resolve_with_geohash()
      G8: num_participants from len(participants)
    """

    # G1: Same mapping as k0/runtime/ultrabert_adapter.py SENTIMENT_TO_VALENCE
    # Note: K0 uses 0-1 range (valence), not -1 to 1. We provide BOTH:
    #   sentiment_score: -1.0 to 1.0 (for SRE social enrichment)
    #   affect_valence:  -1.0 to 1.0 (from affect.valence — NOT the sentiment map)
    SENTIMENT_TO_SCORE: dict[str, float] = {
        "very_negative": -0.9,
        "negative": -0.5,
        "neutral": 0.0,
        "positive": 0.5,
        "very_positive": 0.9,
    }

    def __init__(self, place_resolver: PlaceResolver, config: MWConfig) -> None:
        self._place_resolver = place_resolver
        self._config = config

    def map_atom_to_body(
        self,
        atom: MemoryAtom,
        context: ExtractionContext,
        trace_id: str,
    ) -> dict:
        """Convert MemoryAtom → K0-compatible body dict.

        Returns a plain dict ready for JSON serialization.
        All frozen dataclass fields are unpacked to plain dicts.
        """
        # Resolve place_id and geohash_6 (G5/G6)
        place_id, geohash_6 = self._place_resolver.resolve_with_geohash(
            atom.location_name,
            self._config.known_location_geohashes,
        )

        body: dict = {
            # --- Core content ---
            "text": atom.text,
            "operation": "UPSERT",
            "topics": list(atom.topics),
            "categories": list(atom.categories) if atom.categories else [],
            "activity_type": atom.activity_type.value if atom.activity_type else None,

            # --- Participants (already resolved to person_ids) ---
            "participants": list(atom.participants) if atom.participants else [],
            "participant_relationships": [],  # Phase 2 does not extract relationships

            # --- Location ---
            "location_name": atom.location_name,
            "location_type": atom.location_type.value if atom.location_type else None,
            "place_id": place_id,  # G6

            # --- Emotion ---
            "sentiment_label": atom.sentiment_label.value if atom.sentiment_label else "neutral",
            "emotion_tags": list(atom.emotion_tags) if atom.emotion_tags else [],
            "affect": self._serialize_affect(atom.affect),

            # --- Narrative ---
            "narrative": self._serialize_narrative(atom.narrative),

            # --- Temporal ---
            "temporal": self._build_temporal(context),
            "temporal_links": self._serialize_temporal_links(atom.temporal_links),
            "temporal_orientation": atom.temporal_orientation.value if atom.temporal_orientation else "PAST",
            "conversation_anchor_ms": atom.conversation_anchor_ms,

            # --- Social ---
            "social_context": atom.social_context.value if atom.social_context else None,
            "social_intimacy": atom.social_intimacy.value if atom.social_intimacy else None,

            # --- Cognitive dimensions ---
            "source_type": atom.source_type.value if atom.source_type else "user_stated",
            "novelty": atom.novelty.value if atom.novelty else "EXPECTED",
            "elaboration_depth": atom.elaboration_depth.value if atom.elaboration_depth else "MENTION",
            "intent_type": atom.intent_type.value if atom.intent_type else None,
            "identity_domains": list(atom.identity_domains) if atom.identity_domains else [],

            # --- Confidence + metadata ---
            "confidence": atom.confidence,
            "session_id": atom.session_id,
            "conversation_turn": atom.conversation_turn,
            "language": atom.language or "en",
            "cognitive_trace_id": trace_id,
            "embedding_text": None,  # K0 P02 computes embeddings, not K1

            # --- v2.2 correction signals ---
            "correction_signal": atom.correction_signal,
            "contradiction_signal": atom.contradiction_signal,
            "supersedes_concept": atom.supersedes_concept,
            "correction_source": atom.correction_source,
            "session_context_id": atom.session_context_id,

            # --- K0-required derived fields (gaps G1-G8) ---
            "sentiment_score": self.SENTIMENT_TO_SCORE.get(
                atom.sentiment_label.value if atom.sentiment_label else "neutral", 0.0
            ),  # G1
            "dominant_emotion": (
                atom.emotion_tags[0] if atom.emotion_tags else "neutral"
            ),  # G2
            "dominant_emotions_json": [
                {"emotion": e, "confidence": 0.8} for e in (atom.emotion_tags or [])[:5]
            ],  # G3
            "affect_valence": (
                atom.affect.valence if atom.affect else 0.0
            ),  # G4
            "geohash_6": geohash_6,  # G5
            "num_participants": len(atom.participants) if atom.participants else 0,  # G8

            # --- Event time ---
            "event_time_utc": self._resolve_event_time(context),
        }

        return body

    def _serialize_affect(self, affect: Affect | None) -> dict | None:
        if affect is None:
            return None
        return {
            "valence": affect.valence,
            "arousal": affect.arousal,
            "dominance": affect.dominance,
        }

    def _serialize_narrative(self, narrative: Narrative | None) -> dict | None:
        if narrative is None:
            return None
        return {
            "arc_label": narrative.thread_id,
            "arc_position": narrative.arc_position.value if narrative.arc_position else "EXPOSITION",
            "arc_salience": 0.5,  # Default; LLM does not score salience
        }

    def _serialize_temporal_links(self, links: tuple) -> list[dict]:
        return [
            {
                "mentioned_time": link.mentioned_time,
                "resolved_epoch_ms": link.resolved_epoch_ms,
                "uncertainty_window_ms": link.uncertainty_window_ms,
                "link_type": link.link_type,
                "confidence": link.confidence,
            }
            for link in (links or ())
        ]

    def _build_temporal(self, context: ExtractionContext) -> dict | None:
        """Build temporal object from ExtractionContext.

        day_of_week and time_of_day derived from turn_timestamp_ms.
        """
        ts = context.turn_timestamp_ms
        if not ts or ts <= 0:
            return None
        from datetime import datetime, timezone
        dt = datetime.fromtimestamp(ts / 1000.0, tz=timezone.utc)
        return {
            "day_of_week": dt.strftime("%A"),
            "time_of_day": self._time_of_day(dt.hour),
            "is_recurring": False,  # MW does not detect recurrence
        }

    @staticmethod
    def _time_of_day(hour: int) -> str:
        if hour < 6:
            return "night"
        if hour < 12:
            return "morning"
        if hour < 18:
            return "afternoon"
        return "evening"

    @staticmethod
    def _resolve_event_time(context: ExtractionContext) -> str:
        """ISO 8601 UTC from turn_timestamp_ms. Fallback: now_utc()."""
        from datetime import datetime, timezone
        ts = context.turn_timestamp_ms
        if ts and ts > 0:
            dt = datetime.fromtimestamp(ts / 1000.0, tz=timezone.utc)
        else:
            dt = datetime.now(timezone.utc)
        return dt.strftime("%Y-%m-%dT%H:%M:%SZ")
```

#### EnvelopeBuilder Class

```python
class EnvelopeBuilder:
    """Build MWEnvelopes from MemoryAtom list.

    Uses FieldMapper for body construction.
    Injects headers from ExtractionContext metadata.

    MW-10: Every envelope carries cognitive_trace_id (asserted).
    """

    TOPIC = "memory.delta"
    SCHEMA_URI = "schema://memory.delta"
    SCHEMA_VERSION = "1.0"

    def __init__(self, field_mapper: FieldMapper) -> None:
        self._field_mapper = field_mapper

    def build(
        self,
        atoms: list[MemoryAtom],
        context: ExtractionContext,
        trace_id: str,
    ) -> list[dict]:
        """Build envelope dicts from validated MemoryAtom list.

        Each envelope is a dict with: topic, schema_uri, body, trace_id, headers.
        Ready for IBridgeCommandPort.submit_batch().

        Args:
            atoms: Validated MemoryAtom list from ExtractionValidator.
            context: ExtractionContext for header metadata.
            trace_id: cognitive_trace_id (MW-10).

        Returns:
            List of envelope dicts. Empty if atoms is empty.
        """
        # MW-10: trace_id required
        assert_mw10_trace_id(trace_id)

        envelopes: list[dict] = []

        for atom in atoms:
            body = self._field_mapper.map_atom_to_body(atom, context, trace_id)

            envelope = {
                "topic": self.TOPIC,
                "schema_uri": self.SCHEMA_URI,
                "body": body,
                "trace_id": trace_id,
                "headers": self._build_headers(context, trace_id),
            }
            envelopes.append(envelope)

        return envelopes

    def _build_headers(self, context: ExtractionContext, trace_id: str) -> dict:
        """Build MW-side headers. Bridge adds crypto headers later."""
        meta = context.control_context or {}
        return {
            "cognitive_trace_id": trace_id,
            "tenant_id": meta.get("tenant_id", ""),
            "space_id": meta.get("space_id", ""),
            "topic": self.TOPIC,
            "schema_uri": self.SCHEMA_URI,
            "schema_version": self.SCHEMA_VERSION,
            "actor": meta.get("user_id", ""),
            "device_id": meta.get("device_id", ""),
            "band": meta.get("safety_band", "GREEN"),
        }
```

#### Implementation Items

| Item | File | Work |
|------|------|------|
| I-MW-3.1.1 | `k1/memory_writer/envelope/__init__.py` | Package init. Re-exports: `FieldMapper`, `EnvelopeBuilder`, `PrivacyEnforcer` |
| I-MW-3.1.2 | `k1/memory_writer/envelope/field_mapper.py` | `FieldMapper` class as shown above. Imports: `datetime`, `k1.memory_writer.types.*` (MemoryAtom, Affect, Narrative, TemporalLink, all enums), `k1.memory_writer.config.MWConfig`, `k1.memory_writer.place_resolver.PlaceResolver` |
| I-MW-3.1.3 | `k1/memory_writer/envelope/envelope_builder.py` | `EnvelopeBuilder` class as shown above. Imports: `k1.memory_writer.envelope.field_mapper.FieldMapper`, `k1.memory_writer.types.MemoryAtom`, `k1.memory_writer.types.ExtractionContext`, `k1.memory_writer.invariants.assert_mw10_trace_id` |
| I-MW-3.1.4 | `tests/k1/memory_writer/test_field_mapper.py` | 28 tests (see test specification below) |
| I-MW-3.1.5 | `tests/k1/memory_writer/test_envelope_builder.py` | 14 tests (see test specification below) |

#### Test Specification: `tests/k1/memory_writer/test_field_mapper.py`

**28 tests** organized in 6 test classes:

```text
class TestFieldMapperDirectCopy:                    # 6 tests
  test_text_copied                                   — atom.text → body["text"] unchanged
  test_topics_copied_as_list                         — atom.topics → body["topics"] (list, not tuple)
  test_participants_copied                           — atom.participants → body["participants"]
  test_confidence_copied                             — atom.confidence → body["confidence"]
  test_session_metadata_copied                       — session_id, conversation_turn, language copied
  test_operation_always_upsert                       — body["operation"] == "UPSERT" regardless of atom

class TestFieldMapperEnumSerialization:              # 5 tests
  test_sentiment_label_to_string                     — SentimentLabel.POSITIVE → "positive"
  test_activity_type_to_string                       — ActivityType.MEAL → "MEAL"
  test_location_type_to_string                       — LocationType.RESTAURANT → "restaurant"
  test_none_enum_to_null                             — activity_type=None → body["activity_type"]=None
  test_temporal_orientation_to_string                 — TemporalOrientation.PAST → "PAST"

class TestFieldMapperDerivedFields:                 # 7 tests (K0 gaps)
  test_g1_sentiment_score                            — POSITIVE → 0.5, VERY_NEGATIVE → -0.9
  test_g2_dominant_emotion                           — emotion_tags=["joy", "contentment"] → "joy"
  test_g2_dominant_emotion_empty                     — emotion_tags=[] → "neutral"
  test_g3_dominant_emotions_json                     — 3 emotion_tags → [{"emotion": ..., "confidence": 0.8}, ...]
  test_g4_affect_valence_flattened                   — affect.valence=0.8 → body["affect_valence"]=0.8
  test_g5_geohash_from_place_resolver                — PlaceResolver returns ("place_x", "9q8yyz") → body["geohash_6"]="9q8yyz"
  test_g8_num_participants                           — 3 participants → body["num_participants"]=3

class TestFieldMapperNestedSerialization:            # 4 tests
  test_affect_to_dict                                — Affect(0.8, 0.5, 0.6) → {"valence": 0.8, "arousal": 0.5, "dominance": 0.6}
  test_narrative_to_dict                             — Narrative → {"arc_label": ..., "arc_position": ..., "arc_salience": 0.5}
  test_temporal_links_to_list                        — 3 TemporalLink objects → list of 3 dicts
  test_temporal_from_timestamp                       — turn_timestamp_ms=1700000000000 → {"day_of_week": ..., "time_of_day": ..., "is_recurring": false}

class TestFieldMapperCorrectionSignals:             # 3 tests
  test_correction_signal_passed                      — correction_signal=True → body["correction_signal"]=True
  test_supersedes_concept_passed                     — "cuisine_preference:italian" → body["supersedes_concept"]
  test_correction_defaults_false                     — no signals → body["correction_signal"]=False, body["contradiction_signal"]=False

class TestFieldMapperEdgeCases:                     # 3 tests
  test_none_location_no_geohash                      — location_name=None → place_id=None, geohash_6=None
  test_empty_emotion_tags                            — emotion_tags=[] → dominant_emotion="neutral", dominant_emotions_json=[]
  test_embedding_text_always_null                    — body["embedding_text"] is always None (K0 P02 computes embeddings)
```

#### Test Specification: `tests/k1/memory_writer/test_envelope_builder.py`

**14 tests** organized in 3 test classes:

```text
class TestEnvelopeBuilderBuild:                     # 6 tests
  test_single_atom_produces_one_envelope              — 1 MemoryAtom → 1 envelope dict
  test_multi_atom_produces_multiple_envelopes         — 3 MemoryAtom → 3 envelope dicts
  test_empty_atoms_produces_empty                     — [] → []
  test_envelope_has_topic                             — envelope["topic"] == "memory.delta"
  test_envelope_has_schema_uri                        — envelope["schema_uri"] == "schema://memory.delta"
  test_envelope_has_trace_id                          — envelope["trace_id"] == trace_id (MW-10)

class TestEnvelopeBuilderHeaders:                   # 5 tests
  test_headers_include_cognitive_trace_id              — headers["cognitive_trace_id"] == trace_id
  test_headers_include_tenant_id                       — headers["tenant_id"] from context.control_context
  test_headers_include_band                            — headers["band"] == "GREEN" (or context value)
  test_headers_schema_version                          — headers["schema_version"] == "1.0"
  test_mw10_missing_trace_id_raises                    — trace_id="" → InvariantViolation (MW-10)

class TestEnvelopeBuilderIntegration:               # 3 tests
  test_body_has_all_required_fields                    — body contains all 14 required K0 fields
  test_body_has_derived_fields                         — body contains sentiment_score, dominant_emotion, affect_valence, num_participants, geohash_6
  test_body_serializable_as_json                       — json.dumps(body) succeeds — no frozen dataclasses leak
```

**Acceptance criteria:**

- [x] All 42 tests pass (28 FieldMapper + 14 EnvelopeBuilder)
- [x] All 37 MemoryAtom fields mapped to body dict
- [x] 7 K0-required derived fields present: `sentiment_score` (G1), `dominant_emotion` (G2), `dominant_emotions_json` (G3), `affect_valence` (G4), `geohash_6` (G5), `place_id` (G6), `num_participants` (G8)
- [x] `SENTIMENT_TO_SCORE` mapping matches K0's `SENTIMENT_TO_VALENCE` in `k0/runtime/ultrabert_adapter.py` (note: different range — score is -1..1, valence is 0..1)
- [x] MW-10: `assert_mw10_trace_id()` called on every `build()` — `InvariantViolation` on empty trace_id
- [x] MW-13: `place_id` from PlaceResolver matches `place_<slug>` format
- [x] All enum values serialized to strings (not Enum objects)
- [x] All frozen dataclasses (Affect, Narrative, TemporalLink) serialized to plain dicts
- [x] `embedding_text` always `None` — K0 P02 M02 computes embeddings via UltraBERT
- [x] `event_time_utc` from `context.turn_timestamp_ms`, fallback to `now_utc()`
- [x] `conversation_anchor_ms` from `atom.conversation_anchor_ms` — NEVER overwritten by K0 M08

---

### E-MW-3.2: Privacy Enforcer (Stage 4 — Part 2)

**Design ref:** Architecture §20 (band rules), §12 (band header)
**Bands:** GREEN (full passthrough), AMBER (location generalized), RED (location stripped + participants masked)

#### Problem Statement

Current state: No `PrivacyEnforcer` class exists. The privacy band value (`GREEN`/`AMBER`/`RED`) is available in `ExtractionContext.control_context["safety_band"]` and in the envelope header `band`. Architecture §20 defines the stripping rules.

The enforcer operates on **body dicts** (output of FieldMapper), NOT on MemoryAtom objects. It runs after FieldMapper, before batching. This is defense-in-depth — K0 Gate also enforces band policies, but MW strips early to minimize data exposure in transit (over Bridge).

**Key design decisions:**

- GREEN: No modifications. All fields pass through.
- AMBER: `location_name` generalized to its `location_type` category (e.g., "Olive Garden" → "Restaurant"). If `location_type` is None, use fallback "Location".
- RED: `location_name` set to `None`. `location_type` set to `None`. `place_id` set to `None`. `geohash_6` set to `None`. `participants` replaced with `["person_redacted_0", "person_redacted_1", ...]`. `num_participants` preserved (count is non-identifying).

#### PrivacyEnforcer Class

```python
class PrivacyEnforcer:
    """Band-based field stripping on envelope body dicts.

    Runs AFTER FieldMapper, BEFORE DeltaAggregator.
    Defense-in-depth: K0 Gate also enforces band policies.

    Bands:
      GREEN: No modifications
      AMBER: location_name generalized to location_type category
      RED:   location stripped entirely, participants masked
    """

    # AMBER generalization: location_type → user-friendly label
    _LOCATION_TYPE_LABELS: dict[str, str] = {
        "home": "Home",
        "restaurant": "Restaurant",
        "hospital": "Hospital",
        "school": "School",
        "office": "Office",
        "gym": "Gym",
        "store": "Store",
        "park": "Park",
        "church": "Church",
        "airport": "Airport",
        "hotel": "Hotel",
        "other": "Location",
    }

    def enforce(self, body: dict, band: str) -> dict:
        """Apply band-based field stripping to an envelope body dict.

        Args:
            body: Mutable body dict from FieldMapper.
            band: Privacy band (GREEN/AMBER/RED).

        Returns:
            The same body dict (modified in place for AMBER/RED).
        """
        if band == "GREEN":
            return body

        if band == "AMBER":
            return self._enforce_amber(body)

        if band == "RED":
            return self._enforce_red(body)

        # Unknown band → treat as RED (fail-secure)
        log.warning("MW: unknown privacy band, treating as RED", band=band)
        return self._enforce_red(body)

    def _enforce_amber(self, body: dict) -> dict:
        """AMBER: generalize location_name to category label."""
        loc_type = body.get("location_type")
        if body.get("location_name"):
            if loc_type:
                body["location_name"] = self._LOCATION_TYPE_LABELS.get(
                    loc_type, "Location"
                )
            else:
                body["location_name"] = "Location"
        return body

    def _enforce_red(self, body: dict) -> dict:
        """RED: strip all location, mask participants."""
        # Strip location entirely
        body["location_name"] = None
        body["location_type"] = None
        body["place_id"] = None
        body["geohash_6"] = None

        # Mask participants (preserve count for analytics)
        participants = body.get("participants", [])
        body["participants"] = [
            f"person_redacted_{i}" for i in range(len(participants))
        ]
        # num_participants preserved — count is non-identifying

        return body
```

#### Implementation Items

| Item | File | Work |
|------|------|------|
| I-MW-3.2.1 | `k1/memory_writer/envelope/privacy_enforcer.py` | `PrivacyEnforcer` class as shown above. Imports: `logging` |
| I-MW-3.2.2 | `k1/memory_writer/envelope/__init__.py` (modify) | Add re-export: `PrivacyEnforcer` |
| I-MW-3.2.3 | `tests/k1/memory_writer/test_privacy_enforcer.py` | 22 tests (see test specification below) |

#### Test Specification: `tests/k1/memory_writer/test_privacy_enforcer.py`

**22 tests** organized in 5 test classes:

```text
class TestGreenBand:                                # 3 tests
  test_green_no_modifications                        — all fields unchanged
  test_green_location_preserved                      — location_name="Olive Garden" → unchanged
  test_green_participants_preserved                   — participants=["person_mom"] → unchanged

class TestAmberBand:                                # 6 tests
  test_amber_location_generalized_restaurant         — "Olive Garden" + type="restaurant" → "Restaurant"
  test_amber_location_generalized_hospital           — "Stanford Hospital" + type="hospital" → "Hospital"
  test_amber_location_no_type_fallback               — location_name="Custom Place" + type=None → "Location"
  test_amber_no_location_noop                        — location_name=None → unchanged
  test_amber_participants_preserved                   — participants not modified under AMBER
  test_amber_other_fields_preserved                   — text, topics, sentiment unchanged

class TestRedBand:                                  # 7 tests
  test_red_location_name_stripped                     — location_name=None
  test_red_location_type_stripped                     — location_type=None
  test_red_place_id_stripped                          — place_id=None
  test_red_geohash_stripped                           — geohash_6=None
  test_red_participants_masked                        — ["person_mom", "person_dad"] → ["person_redacted_0", "person_redacted_1"]
  test_red_num_participants_preserved                 — num_participants still equals original count
  test_red_text_preserved                             — text field NOT stripped (not identifying)

class TestUnknownBand:                              # 2 tests
  test_unknown_band_treated_as_red                   — band="INVALID" → RED stripping applied
  test_empty_band_treated_as_red                     — band="" → RED stripping applied

class TestPrivacyEdgeCases:                         # 4 tests
  test_empty_participants_red                         — participants=[] → [] (empty stays empty)
  test_all_location_types_generalize                  — each of 12 LocationType values → correct label
  test_body_modified_in_place                         — returns same dict object (not a copy)
  test_no_location_fields_green_noop                  — body without location fields → no KeyError
```

**Acceptance criteria:**

- [x] All 22 tests pass
- [x] GREEN: zero modifications to any field
- [x] AMBER: `location_name` generalized to `location_type` label. All other fields preserved
- [x] RED: `location_name`, `location_type`, `place_id`, `geohash_6` all set to `None`. `participants` masked to `person_redacted_{i}`. `num_participants` preserved
- [x] Unknown/empty band treated as RED (fail-secure)
- [x] Body dict modified in-place (no copy — performance)
- [x] All 12 `LocationType` values have a generalization label
- [x] No LLM call, no I/O — pure deterministic field mutation

---

### E-MW-3.3: Delta Aggregator + Batch Emitter (Stage 5)

**Design ref:** Architecture §10 (batch aggregation, DeltaAggregator, BatchEmitter code)
**Invariants:** MW-08 (250ms batch window), MW-09 (offline-safe)

#### Problem Statement

Current state: `IBridgeCommandPort.submit_batch(envelopes: list[dict])` exists. `MWConfig.batch_window_ms = 250` exists. `assert_mw08_batch_window()` and `assert_mw09_offline_capable()` exist in `invariants.py`.

No `DeltaAggregator` or `BatchEmitter` class exists. The wiring contract places them at `k1/memory_writer/batch/`.

**Concurrency note:** Each MW session instance has its own DeltaAggregator and BatchEmitter. Multiple sessions batching concurrently is safe — each has its own `pending` list and `seen_hashes` set. No shared state between sessions.

**Why 250ms batch window (Architecture §10):**

- LLM extraction takes 200-500ms → most extractions from one turn complete within one window
- One Bridge POST vs 3 POSTs saves ~40ms overhead
- K0 Gate prefers batch-sized work from the outbox
- 250ms delay is imperceptible for background episodic memory writes

#### DeltaAggregator Class

```python
class DeltaAggregator:
    """Time-window batching for K0 command envelopes.

    Collects envelopes during the batch window (MW-08: 250ms default),
    deduplicates by participants+topics hash, sorts by causal order.

    Each MW session instance has its own DeltaAggregator.
    No shared state between sessions.
    """

    def __init__(self, config: MWConfig) -> None:
        # MW-08: validate batch window
        assert_mw08_batch_window(config)
        self._window_ms = config.batch_window_ms
        self._pending: list[dict] = []
        self._seen_hashes: set[str] = set()

    @property
    def window_ms(self) -> int:
        return self._window_ms

    @property
    def pending_count(self) -> int:
        return len(self._pending)

    def add(self, envelope: dict) -> bool:
        """Add envelope to current batch. Dedup by participants+topics hash.

        Args:
            envelope: Envelope dict from EnvelopeBuilder.

        Returns:
            True if added, False if deduplicated (skipped).

        K0 gap G9: Deduplicated envelopes are skipped entirely.
        K0 R3 reconciliation is saved a DB query per dedup.
        """
        hash_key = self._compute_hash(envelope)
        if hash_key in self._seen_hashes:
            log.info("MW: dedup within batch window", hash=hash_key[:8])
            return False
        self._seen_hashes.add(hash_key)
        self._pending.append(envelope)
        return True

    def flush(self) -> list[dict]:
        """Flush the current batch. Returns envelopes in causal order.

        Called after the batch window timer expires (250ms).
        Clears the pending list and seen hashes for the next window.

        Returns:
            List of envelope dicts sorted by conversation_turn, then
            extraction_sequence. Empty list if nothing pending.
        """
        batch = sorted(
            self._pending,
            key=lambda e: (
                e.get("body", {}).get("conversation_turn", 0),
                e.get("body", {}).get("extraction_sequence", 0),
            ),
        )
        self._pending = []
        self._seen_hashes = set()
        return batch

    @staticmethod
    def _compute_hash(envelope: dict) -> str:
        """Dedup key: sorted participants + sorted topics.

        Catches duplicate extractions from the same turn that describe
        the same event with the same people and topics.
        """
        body = envelope.get("body", {})
        parts = sorted(body.get("participants", []))
        topics = sorted(body.get("topics", []))
        raw = f"{parts}:{topics}"
        return hashlib.sha256(raw.encode()).hexdigest()[:16]
```

#### BatchEmitter Class

```python
class BatchEmitter:
    """Flush batched envelopes to Bridge via IBridgeCommandPort.

    One submit_batch() call per flush — not one call per envelope.
    Fire-and-forget: Bridge handles signing, idem_key, offline queuing.

    MW-03: This is the ONLY output path to K0.
    MW-09: Adapter queues locally when Bridge is offline.
    """

    def __init__(self, bridge_port: IBridgeCommandPort) -> None:
        self._bridge_port = bridge_port

    async def emit(self, batch: list[dict]) -> int:
        """Submit all envelopes in the batch to Bridge.

        Args:
            batch: List of envelope dicts from DeltaAggregator.flush().

        Returns:
            Number of envelopes submitted. 0 if batch is empty.

        Raises:
            Nothing — errors are caught and logged. Best-effort.
            If Bridge is offline, adapter queues via LocalOutbox (MW-09).
        """
        if not batch:
            return 0

        try:
            await self._bridge_port.submit_batch(batch)
            return len(batch)
        except Exception as exc:
            log.warning(
                "MW: Bridge submit_batch failed",
                batch_size=len(batch),
                error=str(exc),
                error_type=type(exc).__name__,
            )
            return 0
```

#### Implementation Items

| Item | File | Work |
|------|------|------|
| I-MW-3.3.1 | `k1/memory_writer/batch/__init__.py` | Package init. Re-exports: `DeltaAggregator`, `BatchEmitter` |
| I-MW-3.3.2 | `k1/memory_writer/batch/delta_aggregator.py` | `DeltaAggregator` class as shown above. Imports: `hashlib`, `logging`, `k1.memory_writer.config.MWConfig`, `k1.memory_writer.invariants.assert_mw08_batch_window` |
| I-MW-3.3.3 | `k1/memory_writer/batch/batch_emitter.py` | `BatchEmitter` class as shown above. Imports: `logging`, `k1.memory_writer.ports.bridge_command_port.IBridgeCommandPort` |
| I-MW-3.3.4 | `tests/k1/memory_writer/test_delta_aggregator.py` | 20 tests (see test specification below) |
| I-MW-3.3.5 | `tests/k1/memory_writer/test_batch_emitter.py` | 10 tests (see test specification below) |

#### Test Specification: `tests/k1/memory_writer/test_delta_aggregator.py`

**20 tests** organized in 5 test classes:

```text
class TestDeltaAggregatorAdd:                       # 5 tests
  test_add_single_envelope                           — 1 envelope → pending_count=1, returns True
  test_add_multiple_envelopes                        — 3 unique → pending_count=3, all return True
  test_dedup_same_participants_topics                 — same participants+topics → second add returns False
  test_different_topics_not_deduped                   — same participants, different topics → both added
  test_different_participants_not_deduped             — same topics, different participants → both added

class TestDeltaAggregatorFlush:                     # 5 tests
  test_flush_returns_all_pending                     — 3 envelopes → flush returns 3
  test_flush_clears_pending                          — after flush, pending_count=0
  test_flush_clears_seen_hashes                      — after flush, previously deduped envelope now accepted
  test_flush_empty_returns_empty                     — nothing added → flush returns []
  test_flush_sorts_by_turn_then_sequence             — envelopes from turn 5 seq 1, turn 3 seq 0 → sorted correctly

class TestDeltaAggregatorDedup:                     # 4 tests
  test_dedup_hash_deterministic                      — same envelope → same hash every time
  test_dedup_ignores_body_text                       — different text, same participants+topics → deduped
  test_dedup_is_case_sensitive                        — ["person_mom"] vs ["PERSON_MOM"] → NOT deduped (different sort)
  test_dedup_empty_participants_topics                — participants=[], topics=[] → still computes hash

class TestDeltaAggregatorConfig:                    # 3 tests
  test_mw08_valid_window                             — config.batch_window_ms=250 → no error
  test_mw08_zero_window_raises                       — config.batch_window_ms=0 → InvariantViolation
  test_window_ms_property                            — aggregator.window_ms == config.batch_window_ms

class TestDeltaAggregatorConcurrency:               # 3 tests
  test_separate_instances_no_shared_state            — aggregator_a and aggregator_b → adding to A doesn't affect B
  test_concurrent_add_flush_cycle                    — add 3 → flush → add 2 → flush → both batches correct
  test_pending_count_tracks_correctly                — add 3, dedup 1 → pending_count=2
```

#### Test Specification: `tests/k1/memory_writer/test_batch_emitter.py`

**10 tests** organized in 3 test classes:

```text
class TestBatchEmitterEmit:                         # 4 tests
  test_emit_calls_submit_batch                       — batch of 3 → bridge_port.submit_batch() called with 3 envelopes
  test_emit_returns_count                            — 3 envelopes → returns 3
  test_emit_empty_batch_returns_zero                 — [] → returns 0, submit_batch NOT called
  test_emit_single_envelope                          — 1 envelope → submit_batch called with [envelope]

class TestBatchEmitterErrorHandling:                # 3 tests
  test_bridge_error_returns_zero                     — submit_batch raises → returns 0, no propagation
  test_bridge_timeout_returns_zero                   — submit_batch raises TimeoutError → returns 0
  test_bridge_error_logged                           — submit_batch raises → warning logged with batch_size

class TestBatchEmitterIntegration:                  # 3 tests
  test_emit_with_real_envelope_dicts                  — envelope dicts from EnvelopeBuilder format → accepted
  test_emit_preserves_envelope_order                  — envelopes passed in same order to submit_batch
  test_mw09_offline_adapter_capability               — adapter with supports_offline=True → accepted
```

**Acceptance criteria:**

- [x] All 30 tests pass (20 DeltaAggregator + 10 BatchEmitter)
- [x] MW-08: `assert_mw08_batch_window()` called in DeltaAggregator constructor. Invalid window → `InvariantViolation`
- [x] MW-03: `BatchEmitter` is the ONLY output path — calls `IBridgeCommandPort.submit_batch()`
- [x] MW-09: Bridge adapter offline capability is assumed (enforced at adapter level, not emitter)
- [x] Dedup by `sorted(participants) + sorted(topics)` hash — prevents duplicate envelopes for same event
- [x] Causal ordering: `flush()` sorts by `(conversation_turn, extraction_sequence)`
- [x] `flush()` clears both `pending` and `seen_hashes` — fresh state for next window
- [x] Each session has its own DeltaAggregator instance — no shared state between sessions
- [x] Bridge errors caught and return 0 — never propagated (best-effort, MW-03/§24)
- [x] K0 gap G9: Deduped envelopes silently skipped (not submitted), saving K0 R3 reconciliation cost

---

### E-MW-3.4: Envelope + Batch Integration Test

**Design ref:** Full Phase 3 pipeline: `list[MemoryAtom]` → FieldMapper → EnvelopeBuilder → PrivacyEnforcer → DeltaAggregator → BatchEmitter → mock Bridge

#### Problem Statement

No end-to-end test exists for Phase 3. This integration test verifies:

1. FieldMapper maps all MemoryAtom fields + derives K0 observation fields (G1-G8)
2. EnvelopeBuilder produces properly structured envelope dicts with headers
3. PrivacyEnforcer applies correct band-based stripping
4. DeltaAggregator deduplicates and orders envelopes
5. BatchEmitter submits the batch to `IBridgeCommandPort`
6. Full pipeline: validated atoms in → Bridge receives correct envelope dicts

**Test adapter requirements:** Uses `FakeBridgeCommandPort` that captures `submit_batch()` calls. `PlaceResolver` with canned location entities. `MWConfig` with default values.

#### Integration Flow

```text
Input: [MemoryAtom(text="Had dinner with Mom at Olive Garden",
        participants=["person_mom"], location_name="Olive Garden",
        location_type=LocationType.RESTAURANT, sentiment_label=SentimentLabel.POSITIVE,
        affect=Affect(0.8, 0.5, 0.6), ...)]

FieldMapper.map_atom_to_body(atom, context, trace_id):
  → body["text"] = "Had dinner with Mom at Olive Garden"
  → body["sentiment_score"] = 0.5 (G1)
  → body["dominant_emotion"] = "joy" (G2)
  → body["affect_valence"] = 0.8 (G4)
  → body["place_id"] = "place_olive_garden" (G6)
  → body["geohash_6"] = "000000" (G5, sentinel)
  → body["num_participants"] = 1 (G8)

EnvelopeBuilder.build([atom], context, trace_id="trace-xyz"):
  → [{topic: "memory.delta", schema_uri: ..., body: {...}, trace_id: "trace-xyz",
      headers: {cognitive_trace_id: "trace-xyz", band: "GREEN", ...}}]

PrivacyEnforcer.enforce(body, band="GREEN"):
  → No modifications (GREEN)

DeltaAggregator.add(envelope):
  → Added (not deduped)

DeltaAggregator.flush():
  → [envelope] sorted by (turn, seq)

BatchEmitter.emit(batch):
  → FakeBridgeCommandPort.submit_batch([envelope]) called
```

#### Multi-Band Test Scenario

```text
Same MemoryAtom processed under 3 different bands:

GREEN: location_name="Olive Garden", participants=["person_mom"]
AMBER: location_name="Restaurant", participants=["person_mom"]
RED:   location_name=None, participants=["person_redacted_0"]

Verify each band produces correct body mutations.
```

#### Implementation Items

| Item | File | Work |
|------|------|------|
| I-MW-3.4.1 | `tests/k1/memory_writer/test_envelope_batch_integration.py` | 18 tests (see below) |

#### Test Specification: `tests/k1/memory_writer/test_envelope_batch_integration.py`

**18 tests** in 4 test classes:

```text
class TestFullPipelineGreenBand:                    # 5 tests
  test_single_atom_to_bridge                         — 1 atom → 1 envelope submitted to FakeBridge
  test_multi_atom_to_bridge                          — 3 atoms → 3 envelopes submitted
  test_derived_fields_present                        — body has sentiment_score, dominant_emotion, affect_valence, num_participants
  test_headers_complete                              — headers have cognitive_trace_id, tenant_id, band, topic, schema_uri
  test_body_json_serializable                        — json.dumps(body) for every envelope succeeds

class TestFullPipelinePrivacyBands:                 # 4 tests
  test_amber_location_generalized                    — "Olive Garden" → "Restaurant" in final body
  test_red_location_stripped                          — location_name=None, place_id=None, geohash_6=None in final body
  test_red_participants_masked                        — ["person_mom"] → ["person_redacted_0"] in final body
  test_unknown_band_fails_secure                     — band="INVALID" → RED stripping in final body

class TestFullPipelineBatching:                     # 5 tests
  test_dedup_within_batch                            — 2 atoms same participants+topics → 1 envelope submitted
  test_causal_ordering                               — atoms from turn 5 and turn 3 → flush returns turn 3 first
  test_flush_then_reuse                              — add 2, flush → add 1, flush → 2 separate submit_batch calls
  test_empty_batch_not_submitted                     — 0 atoms → submit_batch NOT called
  test_batch_window_config                           — aggregator.window_ms == 250 (from MWConfig)

class TestFullPipelineErrorRecovery:                # 4 tests
  test_bridge_error_no_crash                         — FakeBridge raises on submit_batch → no exception propagated
  test_mw10_missing_trace_id_raises                  — trace_id="" → InvariantViolation before any batching
  test_field_mapper_null_atom_fields                  — atom with many None fields → body still valid dict
  test_place_resolver_no_match                       — unknown location → place_id=None, geohash_6=None
```

**Acceptance criteria:**

- [x] All 18 tests pass
- [x] Full pipeline exercised: MemoryAtom → FieldMapper → EnvelopeBuilder → PrivacyEnforcer → DeltaAggregator → BatchEmitter → FakeBridge
- [x] All 3 privacy bands tested end-to-end (GREEN, AMBER, RED)
- [x] K0 gap derived fields verified in submitted bodies
- [x] Dedup verified: duplicate atoms produce fewer envelopes
- [x] Causal ordering verified: flush returns envelopes sorted by (turn, seq)
- [x] Bridge errors don't crash the pipeline
- [x] All submitted bodies are JSON-serializable (no frozen dataclasses leak through)

---

### Phase 3 Summary

| Epic | Tests | New Files | Modified Files |
|------|-------|-----------|----------------|
| E-MW-3.1 | 42 | `envelope/__init__.py`, `envelope/field_mapper.py`, `envelope/envelope_builder.py` | — |
| E-MW-3.2 | 22 | `envelope/privacy_enforcer.py` | `envelope/__init__.py` |
| E-MW-3.3 | 30 | `batch/__init__.py`, `batch/delta_aggregator.py`, `batch/batch_emitter.py` | — |
| E-MW-3.4 | 18 | — | — |
| **Total** | **112** | **6 new files** | **1 modified file** |

**Phase 3 invariants enforced:**

- MW-03: `BatchEmitter` is the ONLY output path to K0 — all writes go through `IBridgeCommandPort`
- MW-08: `assert_mw08_batch_window()` — batch window validated at DeltaAggregator construction
- MW-09: Bridge adapter offline capability assumed — `LocalOutbox` queueing is adapter responsibility
- MW-10: `assert_mw10_trace_id()` — every envelope carries `cognitive_trace_id`, validated in EnvelopeBuilder
- MW-13: `place_id` from PlaceResolver matches `place_<slug>` format

**Phase 3 K0 gaps resolved:**

- G1: `sentiment_score` — float -1.0 to 1.0 from `SENTIMENT_TO_SCORE` map
- G2: `dominant_emotion` — `emotion_tags[0]` or `"neutral"`
- G3: `dominant_emotions_json` — reshaped `emotion_tags` with `confidence: 0.8`
- G4: `affect_valence` — flattened from `affect.valence`
- G5: `geohash_6` — from `PlaceResolver.resolve_with_geohash()` (Phase 0 E-MW-0.4)
- G6: `place_id` — from `PlaceResolver.resolve_with_geohash()` (Phase 0 E-MW-0.4)
- G8: `num_participants` — `len(atom.participants)`
- G9: `is_duplicate` — DeltaAggregator deduplicates; K0 R3 saved reconciliation cost

**Phase 3 prerequisites (from earlier phases):**

- Phase 2: `list[MemoryAtom]` — validated, frozen, with resolved person_ids (input to FieldMapper)
- Phase 0 E-MW-0.4: `PlaceResolver.resolve_with_geohash()` for G5/G6
- Phase 1 E-MW-1.2: `ExtractionContext` for header metadata and temporal derivation

**Phase 3 outputs (consumed by Phase 4):**

- Envelope dicts submitted to Bridge via `IBridgeCommandPort.submit_batch()`
- `DeltaAggregator` and `BatchEmitter` instances wired into `MemoryWriterPipeline` (Phase 4)

---

## 12. Phase 4 — Pipeline Assembly + Service Lifecycle

Wires all 5 stages (Phases 1-3) into a single `MemoryWriterPipeline`, adds the `TurnDispatcher` for event-driven activation, and wraps everything in a `MemoryWriterService` with proper lifecycle management (start/stop).

**What this phase does NOT create:** No new pipeline stages. No new extraction logic. No new ports or adapters. Phase 4 is pure **orchestration** — composing the components built in Phases 1-3 into a working pipeline, and wiring the event subscription that triggers it.

**Session-bound lifecycle (Architecture §17):** The entire MW subsystem is session-bound. Fabric spawns one `MemoryWriterService` per session. It goes ACTIVE → IDLE → ACTIVE across turns. On session end, it drains pending batches and terminates. Multiple sessions have independent MW instances — no shared state.

**Error handling (Architecture §24):** Best-effort. Each stage catches its own errors. Pipeline never crashes — it returns empty/partial results on failure. Circuit breaker protects LLM calls. All errors logged with `cognitive_trace_id` (MW-10).

**Init-time invariant validation:** `validate_init_invariants()` in `invariants.py` runs MW-01, MW-03, MW-07, MW-08, MW-09, MW-11 at pipeline construction. Any violation → `InvariantViolation` → service refuses to start.

---

### E-MW-4.1: Pipeline Orchestration

**Design ref:** Architecture §5 (pipeline overview), §24 (error handling), §25 (observability), §26 (performance budget)
**Invariants:** MW-01 (no write port), MW-03 (Bridge only), MW-07 (no LLM in filter), MW-08 (batch window), MW-09 (offline-safe), MW-10 (trace_id), MW-11 (no UltraBERT)

#### Problem Statement

Current state: All 5 stages exist independently:

- Stage 1: `RelevanceFilter` (Phase 1 E-MW-1.1) — `filter(payload) -> FilterDecision`
- Stage 2: `MWSessionReader` + `ContextBuilder` + `PersonResolver` (Phase 1 E-MW-1.2, 1.3, 1.4) — `build(payload) -> ExtractionContext`
- Stage 3: `MemoryWriterAgent` + `ExtractionValidator` (Phase 2 E-MW-2.1, 2.2) — `extract(context) -> list[MemoryAtom]`
- Stage 4: `FieldMapper` + `EnvelopeBuilder` + `PrivacyEnforcer` (Phase 3 E-MW-3.1, 3.2) — `build(atoms) -> list[dict]`, `enforce(body, band) -> dict`
- Stage 5: `DeltaAggregator` + `BatchEmitter` (Phase 3 E-MW-3.3) — `add(envelope)`, `flush() -> list[dict]`, `emit(batch) -> int`

No `MemoryWriterPipeline` class exists that wires these stages together. The wiring contract places it at `k1/memory_writer/pipeline/pipeline.py`.

#### Pipeline Flow (per turn)

```text
async process(payload: TurnCompletePayload) -> PipelineResult:

  ┌─────────────────────────────────────────────────────────────┐
  │ Stage 1: Filter                                             │
  │   decision = filter.filter(payload)                         │
  │   if decision.action == SKIP → return PipelineResult(       │
  │     skipped=True, skip_reason=decision.rule_id)             │
  │   publish("k1.mw.filter.decision.v1", {action, rule_id})   │
  └─────────────────────┬───────────────────────────────────────┘
                        │ PASS
  ┌─────────────────────▼───────────────────────────────────────┐
  │ Stage 2: Context Assembly                                   │
  │   snapshot = session_reader.read_snapshot(payload.session_id)│
  │   context = context_builder.build(payload, snapshot)         │
  │   person_resolver = PersonResolver(context.active_persons)   │
  │   if snapshot fails → log warning, return empty result       │
  └─────────────────────┬───────────────────────────────────────┘
                        │
  ┌─────────────────────▼───────────────────────────────────────┐
  │ Stage 3: LLM Extraction                                     │
  │   if circuit_breaker.is_open → skip, return empty result     │
  │   raw = await writer_agent.extract(context, trace_id)       │
  │   atoms = extraction_validator.validate(raw, context)        │
  │   if LLM error → circuit_breaker.record_failure()           │
  │   if LLM success → circuit_breaker.record_success()         │
  │   publish("k1.mw.extraction.complete.v1", {count, tokens})  │
  └─────────────────────┬───────────────────────────────────────┘
                        │
  ┌─────────────────────▼───────────────────────────────────────┐
  │ Stage 4: Envelope + Privacy                                 │
  │   envelopes = envelope_builder.build(atoms, context, trace) │
  │   band = context.control_context.get("safety_band", "GREEN")│
  │   for env in envelopes:                                     │
  │     privacy_enforcer.enforce(env["body"], band)             │
  └─────────────────────┬───────────────────────────────────────┘
                        │
  ┌─────────────────────▼───────────────────────────────────────┐
  │ Stage 5: Batch + Submit                                     │
  │   for env in envelopes:                                     │
  │     aggregator.add(env)                                     │
  │   # Timer: after batch_window_ms (250ms)                    │
  │   batch = aggregator.flush()                                │
  │   count = await batch_emitter.emit(batch)                   │
  │   publish("k1.mw.batch.submitted.v1", {count, batch_size})  │
  └─────────────────────────────────────────────────────────────┘
```

#### MemoryWriterPipeline Class

```python
@dataclass(frozen=True)
class PipelineResult:
    """Result of a single turn through the pipeline."""

    skipped: bool = False
    skip_reason: str = ""
    atoms_extracted: int = 0
    envelopes_submitted: int = 0
    llm_tokens_used: int = 0
    llm_latency_ms: float = 0.0
    trace_id: str = ""
    error: str | None = None


class MemoryWriterPipeline:
    """5-stage linear pipeline for memory extraction.

    Wires: Filter → Context → Extraction → Envelope → Batch.
    One instance per session (session-bound). No shared state.

    Each stage catches its own errors. Pipeline never crashes.
    Returns PipelineResult with summary of what happened.
    """

    def __init__(
        self,
        # Stage 1
        relevance_filter: RelevanceFilter,
        # Stage 2
        session_reader: MWSessionReader,
        context_builder: ContextBuilder,
        # Stage 3
        writer_agent: MemoryWriterAgent,
        extraction_validator: ExtractionValidator,
        circuit_breaker: CircuitBreaker,
        # Stage 4
        envelope_builder: EnvelopeBuilder,
        privacy_enforcer: PrivacyEnforcer,
        # Stage 5
        delta_aggregator: DeltaAggregator,
        batch_emitter: BatchEmitter,
        # Observability
        event_port: IEventSubscriptionPort,
        config: MWConfig,
    ) -> None:
        self._filter = relevance_filter
        self._session_reader = session_reader
        self._context_builder = context_builder
        self._writer_agent = writer_agent
        self._validator = extraction_validator
        self._circuit_breaker = circuit_breaker
        self._envelope_builder = envelope_builder
        self._privacy_enforcer = privacy_enforcer
        self._aggregator = delta_aggregator
        self._emitter = batch_emitter
        self._event_port = event_port
        self._config = config

    async def process(self, payload: TurnCompletePayload) -> PipelineResult:
        """Process a single turn through the 5-stage pipeline.

        Args:
            payload: TurnCompletePayload from turn.complete.v1 event.

        Returns:
            PipelineResult with extraction summary. Never raises.
        """
        trace_id = payload.cognitive_trace_id or ""

        # ── Stage 1: Filter ──
        try:
            decision = self._filter.filter(payload)
        except Exception as exc:
            log.warning("MW: filter error, allowing turn", trace_id=trace_id, error=str(exc))
            decision = FilterDecision(action="PASS", rule_id="error_fallback")

        if decision.action == "SKIP":
            await self._publish_safe("k1.mw.filter.decision.v1", {
                "trace_id": trace_id, "action": "SKIP", "rule_id": decision.rule_id,
            })
            return PipelineResult(skipped=True, skip_reason=decision.rule_id, trace_id=trace_id)

        await self._publish_safe("k1.mw.filter.decision.v1", {
            "trace_id": trace_id, "action": "PASS",
        })

        # ── Stage 2: Context Assembly ──
        try:
            snapshot = await self._session_reader.read_snapshot(payload.session_id)
            context = self._context_builder.build(payload, snapshot)
        except Exception as exc:
            log.warning("MW: context assembly failed", trace_id=trace_id, error=str(exc))
            await self._publish_safe("k1.mw.pipeline.error.v1", {
                "trace_id": trace_id, "stage": "context_assembly", "error": str(exc),
            })
            return PipelineResult(trace_id=trace_id, error="context_read_failed")

        # ── Stage 3: LLM Extraction ──
        if self._circuit_breaker.is_open:
            log.info("MW: circuit breaker open, skipping extraction", trace_id=trace_id)
            await self._publish_safe("k1.mw.circuit.open.v1", {"trace_id": trace_id})
            return PipelineResult(trace_id=trace_id, error="circuit_breaker_open")

        raw_extractions = await self._writer_agent.extract(context, trace_id)

        if raw_extractions:
            self._circuit_breaker.record_success()
        else:
            # Empty could be legitimate (trivial turn) or LLM failure.
            # Writer agent already handles errors internally.
            pass

        atoms = self._validator.validate(raw_extractions, context)

        if not atoms:
            await self._publish_safe("k1.mw.extraction.complete.v1", {
                "trace_id": trace_id, "atom_count": 0,
            })
            return PipelineResult(atoms_extracted=0, trace_id=trace_id)

        await self._publish_safe("k1.mw.extraction.complete.v1", {
            "trace_id": trace_id, "atom_count": len(atoms),
        })

        # ── Stage 4: Envelope + Privacy ──
        envelopes = self._envelope_builder.build(atoms, context, trace_id)

        band = "GREEN"
        if context.control_context:
            band = context.control_context.get("safety_band", "GREEN")

        for env in envelopes:
            self._privacy_enforcer.enforce(env["body"], band)

        # ── Stage 5: Batch + Submit ──
        for env in envelopes:
            self._aggregator.add(env)

        batch = self._aggregator.flush()
        submitted = await self._emitter.emit(batch)

        await self._publish_safe("k1.mw.batch.submitted.v1", {
            "trace_id": trace_id, "submitted_count": submitted, "batch_size": len(batch),
        })

        return PipelineResult(
            atoms_extracted=len(atoms),
            envelopes_submitted=submitted,
            trace_id=trace_id,
        )

    async def flush_pending(self) -> int:
        """Flush any pending envelopes in the aggregator.

        Called during service shutdown to drain incomplete batches.
        """
        batch = self._aggregator.flush()
        if batch:
            return await self._emitter.emit(batch)
        return 0

    async def _publish_safe(self, topic: str, payload: dict) -> None:
        """Publish observability event. Never raises (best-effort telemetry)."""
        try:
            await self._event_port.publish(topic, payload)
        except Exception:
            pass  # Telemetry failure is non-critical
```

#### PipelineResult Dataclass

```python
@dataclass(frozen=True)
class PipelineResult:
    """Outcome of processing a single turn.

    Used by TurnDispatcher for logging and metrics.
    All fields have safe defaults — empty result is valid.
    """

    skipped: bool = False
    skip_reason: str = ""
    atoms_extracted: int = 0
    envelopes_submitted: int = 0
    llm_tokens_used: int = 0
    llm_latency_ms: float = 0.0
    trace_id: str = ""
    error: str | None = None
```

#### Batch Window Timer Strategy

The 250ms batch window (MW-08) is handled by **immediate flush** in this implementation. Each `process()` call adds envelopes to the aggregator and immediately flushes. This is correct because:

1. **Single turn per process() call.** Each turn produces 1-6 envelopes from one LLM call.
2. **No overlapping turns within a session.** MW is session-bound — Turn N+1 doesn't start until Turn N's `turn.complete.v1` fires.
3. **The 250ms window's original purpose** (Architecture §10) was to catch stragglers from overlapping processing. With session-bound single-turn processing, there are no stragglers.
4. **Cross-session batching is NOT desired.** Each session has its own aggregator instance.

The `flush_pending()` method exists for shutdown — if the service is stopped mid-batch, it drains.

**Future optimization:** If MW ever processes multiple turns concurrently within a session (currently not the case), the aggregator's timer can be introduced with `asyncio.call_later(window_ms/1000, flush)`.

#### Implementation Items

| Item | File | Work |
|------|------|------|
| I-MW-4.1.1 | `k1/memory_writer/pipeline/__init__.py` | Package init. Re-exports: `MemoryWriterPipeline`, `PipelineResult`, `TurnDispatcher` |
| I-MW-4.1.2 | `k1/memory_writer/pipeline/pipeline.py` | `MemoryWriterPipeline` class + `PipelineResult` dataclass as shown above. Imports: all Phase 1-3 classes, `k1.memory_writer.ports.event_subscription_port.IEventSubscriptionPort`, `k1.memory_writer.config.MWConfig`, `k1.memory_writer.types.TurnCompletePayload`, `k1.memory_writer.types.FilterDecision` |
| I-MW-4.1.3 | `tests/k1/memory_writer/test_pipeline.py` | 34 tests (see test specification below) |

#### Test Specification: `tests/k1/memory_writer/test_pipeline.py`

**34 tests** organized in 7 test classes:

All tests use mock/fake adapters for every dependency. `FakeRelevanceFilter`, `FakeSessionReader`, `FakeContextBuilder`, `FakeWriterAgent`, `FakeExtractionValidator`, `FakeCircuitBreaker`, `FakeEnvelopeBuilder`, `FakePrivacyEnforcer`, `FakeDeltaAggregator`, `FakeBatchEmitter`, `FakeEventPort`.

```text
class TestPipelineHappyPath:                        # 5 tests
  test_single_turn_full_pipeline                     — 1 turn → filter PASS → 2 atoms → 2 envelopes → 2 submitted
  test_pipeline_result_has_all_fields                — result.atoms_extracted, envelopes_submitted, trace_id populated
  test_pipeline_result_trace_id                      — result.trace_id == payload.cognitive_trace_id
  test_observability_events_published                — filter.decision + extraction.complete + batch.submitted events published
  test_privacy_enforcer_called_with_correct_band     — band from context.control_context["safety_band"] used

class TestPipelineFilterSkip:                       # 4 tests
  test_filter_skip_returns_skipped_result            — filter returns SKIP → result.skipped=True, result.skip_reason set
  test_filter_skip_no_context_read                   — filter SKIP → session_reader.read_snapshot NOT called
  test_filter_skip_no_llm_call                       — filter SKIP → writer_agent.extract NOT called
  test_filter_error_falls_through                    — filter raises → treated as PASS (allow turn)

class TestPipelineContextErrors:                    # 3 tests
  test_snapshot_read_fails_returns_error              — session_reader raises → result.error="context_read_failed"
  test_snapshot_read_fails_no_extraction              — session_reader raises → writer_agent.extract NOT called
  test_context_build_fails_returns_error              — context_builder raises → result.error="context_read_failed"

class TestPipelineExtractionErrors:                 # 5 tests
  test_writer_agent_returns_empty                    — extract() returns [] → result.atoms_extracted=0
  test_validator_drops_all                           — raw extractions all invalid → result.atoms_extracted=0
  test_llm_empty_no_envelope_build                   — 0 atoms → envelope_builder.build NOT called
  test_llm_empty_no_bridge_submit                    — 0 atoms → batch_emitter.emit NOT called
  test_extraction_partial_valid                      — 3 raw, 1 valid → result.atoms_extracted=1

class TestPipelineCircuitBreaker:                   # 4 tests
  test_circuit_open_skips_extraction                 — circuit_breaker.is_open=True → result.error="circuit_breaker_open"
  test_circuit_open_no_llm_call                      — circuit_breaker.is_open=True → writer_agent.extract NOT called
  test_circuit_open_publishes_event                  — circuit_breaker.is_open → "k1.mw.circuit.open.v1" published
  test_circuit_closed_allows_extraction              — circuit_breaker.is_open=False → normal extraction flow

class TestPipelineBatchFlush:                       # 5 tests
  test_envelopes_added_to_aggregator                 — 3 envelopes → aggregator.add called 3 times
  test_flush_called_after_add                        — aggregator.flush called after all adds
  test_emitter_receives_flush_result                 — emitter.emit receives the list from aggregator.flush
  test_flush_pending_drains_aggregator               — pipeline.flush_pending() → aggregator.flush + emitter.emit
  test_flush_pending_empty_returns_zero              — nothing pending → flush_pending returns 0

class TestPipelineObservability:                    # 8 tests
  test_filter_pass_publishes_decision                — PASS → "k1.mw.filter.decision.v1" with action="PASS"
  test_filter_skip_publishes_decision                — SKIP → "k1.mw.filter.decision.v1" with action="SKIP", rule_id
  test_extraction_complete_publishes_count            — 2 atoms → "k1.mw.extraction.complete.v1" with atom_count=2
  test_batch_submitted_publishes_count                — 3 submitted → "k1.mw.batch.submitted.v1" with submitted_count=3
  test_error_publishes_pipeline_error                 — context read failed → "k1.mw.pipeline.error.v1"
  test_publish_failure_ignored                        — event_port.publish raises → pipeline continues (best-effort)
  test_all_events_carry_trace_id                      — every published event has "trace_id" in payload
  test_zero_atoms_still_publishes_extraction_complete — 0 atoms → extraction.complete.v1 with atom_count=0
```

**Acceptance criteria:**

- [x] All 34 tests pass
- [x] Pipeline wires all 5 stages in correct order
- [x] Filter SKIP short-circuits — no context read, no LLM call, no Bridge submit
- [x] Circuit breaker OPEN short-circuits — no LLM call
- [x] Context read failure returns error result — no extraction attempted
- [x] Empty extraction (0 atoms) → no envelope build, no Bridge submit
- [x] `PipelineResult` populated for every code path (happy, skip, error, empty, partial)
- [x] `flush_pending()` drains aggregator on shutdown
- [x] All observability events published with `trace_id` (MW-10)
- [x] `_publish_safe()` never raises — telemetry failure is non-critical
- [x] Privacy enforcer receives correct band from context

---

### E-MW-4.2: Turn Dispatcher

**Design ref:** Architecture §23 (trigger mechanism, TurnDispatcher code), §24 (error handling)

#### Problem Statement

Current state: `IEventSubscriptionPort` protocol exists with `subscribe()`, `unsubscribe()`, `publish()`. `TurnCompletePayload` dataclass exists in `types.py` (18 fields). `Subscription` dataclass exists with `subscription_id` and `topic`.

No `TurnDispatcher` class exists. The wiring contract places it at `k1/memory_writer/pipeline/turn_dispatcher.py`.

The dispatcher is the **glue between the K1 Bus and the pipeline**. It:

1. Subscribes to `turn.complete.v1` via `IEventSubscriptionPort`
2. Deserializes raw event payloads into `TurnCompletePayload`
3. Deduplicates by `turn_id` (at-most-once guarantee)
4. Routes to `MemoryWriterPipeline.process()`
5. Provides backpressure: queue depth max 2 (current + 1 queued). If queue full, drop oldest — MW is best-effort

**Why at-most-once (not at-least-once):** MW extraction is idempotent in terms of correctness (same turn → same atoms), but each extraction costs LLM tokens. Dedup prevents wasting tokens on re-delivered events. K0's own idempotency layer (`idem_key`) handles Bridge-level dedup, so even a rare double-extraction produces no harm at the K0 level.

#### TurnDispatcher Class

```python
class TurnDispatcher:
    """Routes turn.complete.v1 events to MemoryWriterPipeline.

    Guarantees at-most-once processing per turn_id within a session.
    In-memory dedup set cleared on session end (stop).

    Backpressure: max 1 concurrent process() call + 1 queued.
    If a third turn arrives while processing, the queued turn is
    replaced (newest wins — older context is stale anyway).
    """

    TOPIC = "turn.complete.v1"
    MAX_QUEUE_DEPTH = 2  # processing + 1 queued

    def __init__(
        self,
        pipeline: MemoryWriterPipeline,
        event_port: IEventSubscriptionPort,
    ) -> None:
        self._pipeline = pipeline
        self._event_port = event_port
        self._subscription: Subscription | None = None
        self._processed_ids: set[str] = set()
        self._processing: bool = False
        self._queued_payload: TurnCompletePayload | None = None

    async def start(self) -> None:
        """Subscribe to turn.complete.v1 on the K1 Bus."""
        self._subscription = await self._event_port.subscribe(
            self.TOPIC, self._on_turn_complete
        )
        log.info("MW: TurnDispatcher started", topic=self.TOPIC)

    async def stop(self) -> None:
        """Unsubscribe + flush pending + clear dedup set."""
        if self._subscription:
            await self._event_port.unsubscribe(self._subscription.subscription_id)
            self._subscription = None

        # Flush any pending pipeline work
        await self._pipeline.flush_pending()

        self._processed_ids.clear()
        self._queued_payload = None
        log.info("MW: TurnDispatcher stopped")

    async def _on_turn_complete(self, raw_payload: dict) -> None:
        """Event handler called by K1 Bus on turn.complete.v1.

        Deserializes, deduplicates, and routes to pipeline.
        """
        try:
            payload = self._deserialize(raw_payload)
        except Exception as exc:
            log.warning("MW: failed to deserialize turn event", error=str(exc))
            return

        # At-most-once dedup
        if payload.turn_id in self._processed_ids:
            log.info("MW: duplicate turn_id, skipping", turn_id=payload.turn_id)
            return

        # Backpressure: if already processing, queue (replace if full)
        if self._processing:
            self._queued_payload = payload  # newest wins
            log.info("MW: turn queued (processing in progress)", turn_id=payload.turn_id)
            return

        await self._process_turn(payload)

        # Process queued turn if one arrived during processing
        if self._queued_payload:
            queued = self._queued_payload
            self._queued_payload = None
            if queued.turn_id not in self._processed_ids:
                await self._process_turn(queued)

    async def _process_turn(self, payload: TurnCompletePayload) -> None:
        """Process a turn through the pipeline with dedup tracking."""
        self._processing = True
        try:
            self._processed_ids.add(payload.turn_id)
            result = await self._pipeline.process(payload)
            log.info(
                "MW: turn processed",
                turn_id=payload.turn_id,
                trace_id=result.trace_id,
                skipped=result.skipped,
                atoms=result.atoms_extracted,
                submitted=result.envelopes_submitted,
            )
        except Exception as exc:
            # Pipeline should never raise, but safety net
            log.error("MW: pipeline process error", turn_id=payload.turn_id, error=str(exc))
        finally:
            self._processing = False

    @staticmethod
    def _deserialize(raw: dict) -> TurnCompletePayload:
        """Convert raw K1 Bus event dict → TurnCompletePayload.

        Maps event fields to the typed dataclass.
        Missing optional fields get safe defaults.
        """
        return TurnCompletePayload(
            turn_id=str(raw.get("turn_id", "")),
            session_id=str(raw.get("session_id", "")),
            cognitive_trace_id=str(raw.get("cognitive_trace_id", "")),
            user_message=str(raw.get("user_message", "")),
            assistant_response=str(raw.get("assistant_response", "")),
            timestamp_ms=int(raw.get("timestamp_ms", 0)),
            turn_number=int(raw.get("turn_number", 0)),
            tier=str(raw.get("tier", "LOW")),
            # GAP-002 temporal/spatial fields — from event if present, else 0/None
            mentioned_time_text=raw.get("mentioned_time_text"),
            mentioned_time_epoch_ms=int(raw.get("mentioned_time_epoch_ms", 0)),
            mentioned_time_link_type=raw.get("mentioned_time_link_type"),
            mentioned_time_uncertainty_ms=int(raw.get("mentioned_time_uncertainty_ms", 0)),
            mentioned_location_name=raw.get("mentioned_location_name"),
            mentioned_location_type=raw.get("mentioned_location_type"),
            place_id=raw.get("place_id"),
            location_hierarchy=raw.get("location_hierarchy"),
            transition_from_place=raw.get("transition_from_place"),
            transition_mode=raw.get("transition_mode"),
        )
```

#### Implementation Items

| Item | File | Work |
|------|------|------|
| I-MW-4.2.1 | `k1/memory_writer/pipeline/turn_dispatcher.py` | `TurnDispatcher` class as shown above. Imports: `logging`, `k1.memory_writer.pipeline.pipeline.MemoryWriterPipeline`, `k1.memory_writer.ports.event_subscription_port.IEventSubscriptionPort`, `k1.memory_writer.types.TurnCompletePayload`, `k1.memory_writer.types.Subscription` |
| I-MW-4.2.2 | `k1/memory_writer/pipeline/__init__.py` (modify) | Add re-export: `TurnDispatcher` |
| I-MW-4.2.3 | `tests/k1/memory_writer/test_turn_dispatcher.py` | 24 tests (see test specification below) |

#### Test Specification: `tests/k1/memory_writer/test_turn_dispatcher.py`

**24 tests** organized in 6 test classes:

```text
class TestTurnDispatcherLifecycle:                  # 4 tests
  test_start_subscribes_to_topic                     — start() → event_port.subscribe("turn.complete.v1", handler)
  test_stop_unsubscribes                             — stop() → event_port.unsubscribe(subscription_id)
  test_stop_flushes_pending                          — stop() → pipeline.flush_pending() called
  test_stop_clears_dedup_set                         — stop() → subsequent same turn_id accepted again

class TestTurnDispatcherDedup:                      # 5 tests
  test_first_delivery_processed                      — turn_id="t1" → pipeline.process called
  test_duplicate_turn_id_skipped                     — same turn_id twice → pipeline.process called once
  test_different_turn_ids_both_processed              — turn_id="t1" then "t2" → both processed
  test_dedup_cleared_on_stop                         — stop + start → same turn_id processed again
  test_dedup_set_grows                               — 5 unique turns → 5 in processed_ids set

class TestTurnDispatcherDeserialization:             # 4 tests
  test_full_payload_deserialized                     — all 18 fields populated → TurnCompletePayload correct
  test_missing_optional_fields_use_defaults          — raw dict missing temporal fields → defaults to 0/None
  test_malformed_payload_skipped                     — non-dict or missing turn_id → warning logged, skipped
  test_turn_number_converted_to_int                  — "turn_number": "5" (string) → int(5)

class TestTurnDispatcherBackpressure:               # 5 tests
  test_concurrent_turn_queued                        — turn arrives during processing → queued
  test_queued_turn_processed_after                   — queued turn processed after current completes
  test_queue_replaced_newest_wins                    — 2 turns arrive during processing → only newest processed
  test_queued_turn_dedup_checked                     — queued turn_id already processed → skipped when dequeued
  test_no_queue_when_idle                            — turn arrives when not processing → processed immediately

class TestTurnDispatcherPipelineIntegration:        # 3 tests
  test_pipeline_result_logged                        — PipelineResult summary logged after process
  test_pipeline_exception_caught                     — pipeline.process raises → no crash, error logged
  test_pipeline_called_with_typed_payload            — pipeline.process receives TurnCompletePayload (not raw dict)

class TestTurnDispatcherObservability:              # 3 tests
  test_dedup_skip_logged                             — duplicate → "duplicate turn_id, skipping" logged
  test_queue_logged                                  — queued turn → "turn queued" logged
  test_deserialization_error_logged                   — bad payload → "failed to deserialize" logged
```

**Acceptance criteria:**

- [x] All 24 tests pass
- [x] Subscribes to exactly `"turn.complete.v1"` topic
- [x] At-most-once dedup: same `turn_id` never processed twice
- [x] Deserialization: raw dict → `TurnCompletePayload` with safe defaults for missing fields
- [x] Backpressure: max 1 processing + 1 queued. Newest turn replaces queued (stale context discarded)
- [x] `stop()` unsubscribes, flushes pipeline, clears dedup set
- [x] Pipeline exceptions caught — dispatcher never crashes
- [x] All GAP-002 temporal/spatial fields deserialized from event payload

---

### E-MW-4.3: Memory Writer Factory + Service

**Design ref:** Architecture §17 (agent contract, lifecycle), module.contract.yaml pattern
**Invariants:** All init-time invariants via `validate_init_invariants()`

#### Problem Statement

Current state: All pipeline components exist (Phases 1-3). `TurnDispatcher` exists (E-MW-4.2). `MWConfig` exists. All 5 ports exist. `validate_init_invariants()` exists in `invariants.py`.

No `MemoryWriterFactory` or `MemoryWriterService` exists. The wiring contract places them at `k1/memory_writer/factory.py` and `k1/memory_writer/service.py`.

**Factory pattern:** Matches Fabric's `AgentFactory` 8-step spawn pattern. `MemoryWriterFactory.create()` is the single entry point that:

1. Validates all required ports are present
2. Runs init-time invariant checks
3. Constructs all pipeline components
4. Wires them into `MemoryWriterPipeline`
5. Creates `TurnDispatcher`
6. Returns `MemoryWriterService` (the lifecycle wrapper)

**Service pattern:** `MemoryWriterService` is the top-level object that Fabric holds. It exposes `start()` and `stop()` for lifecycle management, and `health_check()` for Fabric agent status probes.

#### MemoryWriterFactory Class

```python
class MemoryWriterFactory:
    """Factory for creating MemoryWriterService instances.

    Single entry point for MW subsystem construction.
    Validates all required ports and runs init-time invariants.

    Called by Fabric when spawning a session-bound MW agent.
    """

    @staticmethod
    def create(
        session_read_port: ISessionReadPort,
        model_hub_port: IModelHubPort,
        bridge_command_port: IBridgeCommandPort,
        event_subscription_port: IEventSubscriptionPort,
        health_port: IHealthPort,
        config: MWConfig | None = None,
    ) -> "MemoryWriterService":
        """Create a fully wired MemoryWriterService.

        Args:
            session_read_port: SS snapshot reader.
            model_hub_port: LLM extraction calls.
            bridge_command_port: K0 envelope submission.
            event_subscription_port: K1 Bus subscription.
            health_port: Readiness/liveness probes.
            config: MWConfig. Defaults to MWConfig() if None.

        Returns:
            MemoryWriterService ready to start().

        Raises:
            InvariantViolation: If init-time invariant checks fail.
            TypeError: If required ports are missing or wrong type.
        """
        config = config or MWConfig()

        # ── Validate required ports ──
        required_ports = {
            "session_read_port": (session_read_port, ISessionReadPort),
            "model_hub_port": (model_hub_port, IModelHubPort),
            "bridge_command_port": (bridge_command_port, IBridgeCommandPort),
            "event_subscription_port": (event_subscription_port, IEventSubscriptionPort),
            "health_port": (health_port, IHealthPort),
        }
        for name, (port, protocol) in required_ports.items():
            if port is None:
                raise TypeError(f"Required port {name} is None")
            if not isinstance(port, protocol):
                raise TypeError(f"{name} does not implement {protocol.__name__}")

        # ── Run init-time invariant checks ──
        dependencies = {
            "session_read_port": session_read_port,
            "model_hub_port": model_hub_port,
            "bridge_command_port": bridge_command_port,
            "event_subscription_port": event_subscription_port,
            "health_port": health_port,
        }
        # Filter deps: only non-LLM deps passed to filter (MW-07)
        filter_deps = {"session_read_port": session_read_port}
        validate_init_invariants(dependencies, filter_deps, bridge_command_port, config)

        # ── Construct pipeline components ──
        # Stage 1
        relevance_filter = RelevanceFilter(config)

        # Stage 2
        session_reader = MWSessionReader(session_read_port, config)
        place_resolver = PlaceResolver([])  # populated per-turn from SS
        context_builder = ContextBuilder(config)

        # Stage 3
        prompt_loader = PromptLoader(
            Path(__file__).parent / "extraction" / "prompts"
        )
        writer_agent = MemoryWriterAgent(model_hub_port, config, prompt_loader)
        person_resolver = PersonResolver()  # populated per-turn from SS
        extraction_validator = ExtractionValidator(person_resolver, config)
        circuit_breaker = CircuitBreaker(
            failure_threshold=config.circuit_breaker_failure_threshold,
            recovery_probe_seconds=config.circuit_breaker_recovery_probe_seconds,
        )

        # Stage 4
        field_mapper = FieldMapper(place_resolver, config)
        envelope_builder = EnvelopeBuilder(field_mapper)
        privacy_enforcer = PrivacyEnforcer()

        # Stage 5
        delta_aggregator = DeltaAggregator(config)
        batch_emitter = BatchEmitter(bridge_command_port)

        # ── Wire pipeline ──
        pipeline = MemoryWriterPipeline(
            relevance_filter=relevance_filter,
            session_reader=session_reader,
            context_builder=context_builder,
            writer_agent=writer_agent,
            extraction_validator=extraction_validator,
            circuit_breaker=circuit_breaker,
            envelope_builder=envelope_builder,
            privacy_enforcer=privacy_enforcer,
            delta_aggregator=delta_aggregator,
            batch_emitter=batch_emitter,
            event_port=event_subscription_port,
            config=config,
        )

        # ── Create dispatcher + service ──
        dispatcher = TurnDispatcher(pipeline, event_subscription_port)

        return MemoryWriterService(
            pipeline=pipeline,
            dispatcher=dispatcher,
            circuit_breaker=circuit_breaker,
            health_port=health_port,
            config=config,
        )
```

#### MemoryWriterService Class

```python
class MemoryWriterService:
    """Top-level lifecycle wrapper for Memory Writer.

    Held by Fabric per session. Manages start/stop lifecycle.
    Session-bound: one instance per session, reused across turns.

    Lifecycle:
      create → start() → [turn.complete.v1 events → pipeline] → stop()

    Fabric lifecycle mapping:
      PENDING → create()
      WARMING → start()
      ACTIVE  → processing turns
      IDLE    → between turns (no action needed — dispatcher stays subscribed)
      DRAINING → stop() called
      TERMINATED → garbage collected
    """

    def __init__(
        self,
        pipeline: MemoryWriterPipeline,
        dispatcher: TurnDispatcher,
        circuit_breaker: CircuitBreaker,
        health_port: IHealthPort,
        config: MWConfig,
    ) -> None:
        self._pipeline = pipeline
        self._dispatcher = dispatcher
        self._circuit_breaker = circuit_breaker
        self._health_port = health_port
        self._config = config
        self._started: bool = False

    async def start(self) -> None:
        """Start the MW service. Subscribe to events.

        Called by Fabric during WARMING phase.
        Idempotent — safe to call multiple times.
        """
        if self._started:
            return
        await self._dispatcher.start()
        self._started = True
        log.info("MW: MemoryWriterService started")

    async def stop(self) -> None:
        """Stop the MW service. Flush pending + unsubscribe.

        Called by Fabric during DRAINING phase.
        Idempotent — safe to call multiple times.
        """
        if not self._started:
            return
        await self._dispatcher.stop()
        self._started = False
        log.info("MW: MemoryWriterService stopped")

    @property
    def is_started(self) -> bool:
        return self._started

    @property
    def circuit_breaker(self) -> CircuitBreaker:
        """Expose circuit breaker for health checks."""
        return self._circuit_breaker

    async def health_check(self) -> HealthStatus:
        """Health check for Fabric agent lifecycle probes.

        Returns:
            HealthStatus with circuit state and pipeline readiness.
        """
        return HealthStatus(
            is_healthy=self._started and not self._circuit_breaker.is_open,
            llm_circuit_open=self._circuit_breaker.is_open,
            pending_batch_count=self._pipeline._aggregator.pending_count,
            last_extraction_ms=0.0,  # tracked via metrics, not here
            detail="running" if self._started else "stopped",
        )
```

#### Implementation Items

| Item | File | Work |
|------|------|------|
| I-MW-4.3.1 | `k1/memory_writer/factory.py` | `MemoryWriterFactory` class as shown above. Imports: `pathlib.Path`, all 5 port protocols, `MWConfig`, `validate_init_invariants`, all Phase 1-3 classes (RelevanceFilter, MWSessionReader, ContextBuilder, MemoryWriterAgent, ExtractionValidator, FieldMapper, EnvelopeBuilder, PrivacyEnforcer, DeltaAggregator, BatchEmitter, PlaceResolver, PersonResolver, PromptLoader, CircuitBreaker), `MemoryWriterPipeline`, `TurnDispatcher` |
| I-MW-4.3.2 | `k1/memory_writer/service.py` | `MemoryWriterService` class as shown above. Imports: `logging`, `k1.memory_writer.pipeline.pipeline.MemoryWriterPipeline`, `k1.memory_writer.pipeline.turn_dispatcher.TurnDispatcher`, `k1.memory_writer.health.circuit_breaker.CircuitBreaker`, `k1.memory_writer.ports.health_port.IHealthPort`, `k1.memory_writer.types.HealthStatus`, `k1.memory_writer.config.MWConfig` |
| I-MW-4.3.3 | `tests/k1/memory_writer/test_factory.py` | 18 tests (see test specification below) |
| I-MW-4.3.4 | `tests/k1/memory_writer/test_service.py` | 16 tests (see test specification below) |

#### Test Specification: `tests/k1/memory_writer/test_factory.py`

**18 tests** organized in 4 test classes:

```text
class TestFactoryCreate:                            # 5 tests
  test_create_returns_service                        — all ports provided → returns MemoryWriterService
  test_create_with_default_config                    — config=None → uses MWConfig() defaults
  test_create_with_custom_config                     — custom MWConfig → used by pipeline
  test_service_not_started_after_create              — factory.create() → service.is_started == False
  test_service_has_circuit_breaker                    — service.circuit_breaker is not None

class TestFactoryPortValidation:                    # 6 tests
  test_none_session_read_port_raises                 — session_read_port=None → TypeError
  test_none_model_hub_port_raises                    — model_hub_port=None → TypeError
  test_none_bridge_command_port_raises               — bridge_command_port=None → TypeError
  test_none_event_subscription_port_raises           — event_subscription_port=None → TypeError
  test_none_health_port_raises                       — health_port=None → TypeError
  test_wrong_type_port_raises                        — session_read_port=object() → TypeError

class TestFactoryInvariantValidation:               # 4 tests
  test_mw01_checked                                  — dependencies passed to assert_mw01_no_write_port
  test_mw03_checked                                  — dependencies passed to assert_mw03_bridge_only
  test_mw08_checked                                  — config passed to assert_mw08_batch_window
  test_invariant_failure_raises                      — invalid config → InvariantViolation propagated

class TestFactoryWiring:                            # 3 tests
  test_pipeline_has_all_stages                       — service internals: pipeline has filter, reader, agent, builder, emitter
  test_dispatcher_has_event_port                     — dispatcher wired with event_subscription_port
  test_circuit_breaker_config_applied                — CB uses config.circuit_breaker_failure_threshold
```

#### Test Specification: `tests/k1/memory_writer/test_service.py`

**16 tests** organized in 4 test classes:

```text
class TestServiceLifecycle:                         # 5 tests
  test_start_subscribes_dispatcher                   — start() → dispatcher.start() called
  test_start_idempotent                              — start() twice → dispatcher.start() called once
  test_stop_unsubscribes_dispatcher                  — stop() → dispatcher.stop() called
  test_stop_idempotent                               — stop() twice → dispatcher.stop() called once
  test_stop_before_start_noop                        — stop() without start() → no error

class TestServiceHealthCheck:                       # 5 tests
  test_healthy_when_started_circuit_closed            — started + circuit closed → is_healthy=True
  test_unhealthy_when_stopped                        — not started → is_healthy=False
  test_unhealthy_when_circuit_open                   — started + circuit open → is_healthy=False
  test_health_includes_circuit_state                  — health_check().llm_circuit_open matches CB state
  test_health_includes_pending_count                  — health_check().pending_batch_count from aggregator

class TestServiceProperties:                        # 3 tests
  test_is_started_false_initially                    — before start() → is_started=False
  test_is_started_true_after_start                   — after start() → is_started=True
  test_is_started_false_after_stop                   — after stop() → is_started=False

class TestServiceIntegration:                       # 3 tests
  test_full_lifecycle_start_process_stop              — start → send turn → pipeline processes → stop → flushed
  test_multiple_turns_processed                      — start → 3 turns → 3 PipelineResults
  test_stop_flushes_pending_batches                   — envelopes in aggregator → stop() flushes to Bridge
```

**Acceptance criteria:**

- [x] All 34 tests pass (18 Factory + 16 Service)
- [x] `MemoryWriterFactory.create()` validates all 5 ports (None → TypeError, wrong type → TypeError)
- [x] `validate_init_invariants()` called with correct arguments
- [x] All Phase 1-3 components wired correctly in pipeline
- [x] `MemoryWriterService.start()` subscribes dispatcher. Idempotent.
- [x] `MemoryWriterService.stop()` unsubscribes, flushes pending, clears dedup. Idempotent.
- [x] `health_check()` reflects: started state, circuit breaker state, pending batch count
- [x] Factory creates `CircuitBreaker` with config values (failure_threshold=3, recovery_probe_seconds=30)
- [x] Service holds no shared state — one instance per session

---

### E-MW-4.4: Phase 4 Integration Test

**Design ref:** Full MW lifecycle: create → start → turn events → pipeline → Bridge submission → stop

#### Problem Statement

No end-to-end lifecycle test exists. This integration test verifies the complete MW lifecycle using test adapters for all 5 ports.

#### Implementation Items

| Item | File | Work |
|------|------|------|
| I-MW-4.4.1 | `tests/k1/memory_writer/test_lifecycle_integration.py` | 14 tests (see below) |

#### Test Specification: `tests/k1/memory_writer/test_lifecycle_integration.py`

**14 tests** in 3 test classes:

```text
class TestFullLifecycle:                            # 6 tests
  test_create_start_process_stop                     — factory.create → start → send turn → atoms extracted → stop
  test_multi_turn_session                            — 5 turns → each processed, dedup set grows, envelopes submitted
  test_trivial_turn_skipped                          — "ok" → filter SKIP → no LLM call → no Bridge submit
  test_meaningful_turn_extracted                     — "Had dinner with Mom" → 1+ atoms → envelopes → Bridge
  test_stop_flushes_then_cleans                      — pending envelopes flushed on stop → Bridge receives batch
  test_restart_after_stop                            — stop → start → new turns processed (dedup cleared)

class TestLifecycleErrorResilience:                 # 5 tests
  test_llm_failure_skip_turn                         — FakeModelHub raises → turn skipped, next turn OK
  test_circuit_breaker_opens_after_threshold          — 3 LLM failures → circuit opens → next turn skipped
  test_circuit_breaker_half_open_probe               — circuit open → wait recovery → probe turn succeeds → circuit closed
  test_context_read_failure_skip_turn                 — FakeSessionReader raises → turn skipped, next turn OK
  test_bridge_failure_no_crash                       — FakeBridge raises → pipeline continues, next turn OK

class TestLifecycleObservability:                   # 3 tests
  test_all_observability_events_published             — full turn → filter.decision + extraction.complete + batch.submitted events
  test_metrics_trace_ids_consistent                  — all events carry same cognitive_trace_id
  test_health_check_reflects_state                   — started + healthy → True, circuit open → False
```

**Acceptance criteria:**

- [x] All 14 tests pass
- [x] Full lifecycle exercised: factory.create → start → turns → pipeline → Bridge → stop
- [x] Multi-turn session works — dedup tracks turn_ids, pipeline reused
- [x] Error resilience: LLM failure, context read failure, Bridge failure → service continues
- [x] Circuit breaker lifecycle tested: CLOSED → OPEN (after threshold) → HALF_OPEN → CLOSED
- [x] Stop flushes pending envelopes before unsubscribing
- [x] Observability events published at each stage with consistent trace_id

---

### Phase 4 Summary

| Epic | Tests | New Files | Modified Files |
|------|-------|-----------|----------------|
| E-MW-4.1 | 34 | `pipeline/__init__.py`, `pipeline/pipeline.py` | — |
| E-MW-4.2 | 24 | `pipeline/turn_dispatcher.py` | `pipeline/__init__.py` |
| E-MW-4.3 | 34 | `factory.py`, `service.py` | — |
| E-MW-4.4 | 14 | — | — |
| **Total** | **106** | **4 new files** | **1 modified file** |

**Phase 4 invariants enforced:**

- All init-time invariants run via `validate_init_invariants()`: MW-01, MW-03, MW-07, MW-08, MW-09, MW-11
- MW-10: All observability events carry `cognitive_trace_id`
- Circuit breaker: `failure_threshold=3` failures → OPEN, `recovery_probe_seconds=30` → HALF_OPEN probe

**Phase 4 prerequisites (from earlier phases):**

- Phase 1: `RelevanceFilter`, `MWSessionReader`, `ContextBuilder`, `PersonResolver`
- Phase 2: `MemoryWriterAgent`, `ExtractionValidator`, `RawExtraction`, `PromptLoader`
- Phase 3: `FieldMapper`, `EnvelopeBuilder`, `PrivacyEnforcer`, `DeltaAggregator`, `BatchEmitter`
- `CircuitBreaker` (Phase 5 E-MW-5.3 — **NOTE:** circular dep resolved by having Phase 4 define the `CircuitBreaker` interface, Phase 5 provides the implementation. For Phase 4 tests, a `FakeCircuitBreaker` is used.)

**Phase 4 outputs (consumed by Phase 5):**

- `MemoryWriterFactory.create()` — entry point for Fabric to spawn MW
- `MemoryWriterService` — top-level lifecycle object Fabric holds per session
- `MemoryWriterPipeline` — internal, not exposed outside MW module

---

## 13. Phase 5 — Remaining Adapters + Integration

Completes the MW subsystem by providing: (a) the 3 remaining production adapters that bridge MW ports to real K1 infrastructure, (b) a complete test adapter suite for fast integration tests, (c) the LLM circuit breaker implementation, and (d) Fabric wiring so MW is spawned per session.

**What this phase does NOT create:** No new business logic. No new pipeline stages. Phase 5 is pure **infrastructure plumbing** — connecting the ports (defined in Phase 0) through adapters to the concrete implementations that already exist (K1 Bus, Bridge KernelCommandPort, Fabric AgentPool).

**Adapter pattern:** Every adapter follows the same pattern used by the 2 existing adapters (`SessionReadAdapter`, `ModelHubAdapter`):

1. Constructor takes the concrete dependency (typed as `Any` to avoid import coupling)
2. Async methods translate MW protocol → concrete API
3. Error mapping: concrete errors → MW-level semantics (log + continue / raise `AdapterError`)
4. No business logic in adapters — pure translation

**Existing adapter reference implementations:**

- `SessionReadAdapter` (exists): wraps `SessionStateManager` → `ISessionReadPort`. Lock-free reads, `to_dict()` translation, `SectionNotFoundError` → omit.
- `ModelHubAdapter` (exists): wraps `K1 IModelHubPort` → MW `IModelHubPort`. `chat()` → `execute(HubRequest)`, MW-06 token cap, MH-15 `Priority.BACKGROUND`.

---

### E-MW-5.1: Production Adapters (3 remaining)

**Design ref:** Architecture §24 (error handling), existing adapter patterns (`SessionReadAdapter`, `ModelHubAdapter`)

#### Problem Statement

Three production adapters are missing. Without them, `MemoryWriterFactory.create()` (Phase 4) can only be tested with fakes — the real K1 infrastructure is unreachable.

| Adapter | Wraps | Port | Key Translation |
|---------|-------|------|-----------------|
| `BridgeCommandAdapter` | `KernelCommandPort` (Bridge) | `IBridgeCommandPort` | `submit(topic, schema_uri, body)` → `kcp.submit(topic, body, schema_uri=, trace_id=)`. `submit_batch(envelopes)` → `kcp.submit_batch([CommandEnvelope(...)])` |
| `EventSubscriptionAdapter` | `FabricBusAdapter` (K1 Bus) | `IEventSubscriptionPort` | `subscribe(topic, handler)` → `bus.subscribe(topic, wrapper) → Subscription`. `publish(topic, payload)` → `bus.emit(topic, payload)` |
| `HealthAdapter` | `CircuitBreaker` + `MemoryWriterPipeline` | `IHealthPort` | `is_ready()` → `not circuit_breaker.is_open`. `health_check()` → `HealthStatus(...)` |

#### BridgeCommandAdapter Class

```python
class BridgeCommandAdapter:
    """Implements IBridgeCommandPort by wrapping Bridge's KernelCommandPort.

    Translation:
        submit(topic, schema_uri, body)
        -> kcp.submit(topic, body, schema_uri=schema_uri, trace_id=body.get("trace_id"))

        submit_batch(envelopes)
        -> kcp.submit_batch([CommandEnvelope(topic, body, schema_uri, trace_id) ...])

    MW-03: This is the ONLY output path from MW to K0.
    MW-09: KernelCommandPort already handles offline queueing via LocalOutbox.
    MW-10: trace_id extracted from envelope body and passed to Bridge.

    Constructor Args:
        command_port: Bridge's KernelCommandPort instance (typed as Any
            to avoid import coupling, matching SessionReadAdapter pattern).
    """

    __slots__ = ("_command_port",)

    def __init__(self, command_port: Any) -> None:
        self._command_port = command_port

    async def submit(
        self,
        topic: str,
        schema_uri: str,
        body: dict,
    ) -> None:
        """Submit a single command envelope to K0 via Bridge.

        Delegates to KernelCommandPort.submit() with trace_id
        extracted from the body (MW-10).
        """
        trace_id = body.get("trace_id", "")
        await self._command_port.submit(
            topic=topic,
            body=body,
            schema_uri=schema_uri,
            trace_id=trace_id,
        )

    async def submit_batch(
        self,
        envelopes: list[dict],
    ) -> None:
        """Submit a batch of command envelopes to K0 via Bridge.

        Each envelope dict must contain: topic, schema_uri, body, trace_id.
        Translates to Bridge's CommandEnvelope format.
        """
        if not envelopes:
            return
        # Lazy import to avoid coupling (same pattern as ModelHubAdapter)
        from bridge.core.envelope_builder import CommandEnvelope

        commands = [
            CommandEnvelope(
                topic=env["topic"],
                body=env["body"],
                schema_uri=env.get("schema_uri", ""),
                trace_id=env.get("trace_id", ""),
            )
            for env in envelopes
        ]
        await self._command_port.submit_batch(commands)
```

#### EventSubscriptionAdapter Class

```python
class EventSubscriptionAdapter:
    """Implements IEventSubscriptionPort by wrapping FabricBusAdapter.

    Translation:
        subscribe(topic, async_handler)
        -> bus.subscribe(topic, sync_wrapper) -> Subscription

        unsubscribe(subscription_id)
        -> bus.unsubscribe(FabricSubscriptionHandle(subscription_id, topic))

        publish(topic, payload)
        -> bus.emit(topic, payload)

    Key differences from FabricBusAdapter directly:
      - MW handlers are async (bus handlers are sync) → wrapper creates asyncio task
      - MW subscribe returns Subscription (not FabricSubscriptionHandle)
      - MW unsubscribe takes subscription_id string (not handle object)

    Constructor Args:
        bus_adapter: FabricBusAdapter instance (typed as Any to avoid
            import coupling).
    """

    __slots__ = ("_bus", "_subscriptions")

    def __init__(self, bus_adapter: Any) -> None:
        self._bus = bus_adapter
        self._subscriptions: dict[str, Any] = {}  # sub_id -> (handle, topic)

    async def subscribe(
        self,
        topic: str,
        handler: Callable[..., Coroutine[Any, Any, None]],
    ) -> Subscription:
        """Subscribe to a K1 Bus topic with an async handler.

        FabricBusAdapter.subscribe() expects sync handlers.
        This adapter wraps the async handler in asyncio.create_task().
        """
        import asyncio

        def _sync_wrapper(event_topic: str, payload: dict) -> None:
            try:
                loop = asyncio.get_running_loop()
                loop.create_task(handler(payload))
            except RuntimeError:
                # No running loop (unlikely in production)
                logger.warning("MW: no event loop for handler, topic=%s", topic)

        handle = self._bus.subscribe(topic, _sync_wrapper)
        sub_id = handle.subscription_id
        self._subscriptions[sub_id] = (handle, topic)

        return Subscription(subscription_id=sub_id, topic=topic)

    async def unsubscribe(
        self,
        subscription_id: str,
    ) -> None:
        """Remove a subscription by ID."""
        entry = self._subscriptions.pop(subscription_id, None)
        if entry:
            handle, _topic = entry
            self._bus.unsubscribe(handle)

    async def publish(
        self,
        topic: str,
        payload: dict,
    ) -> None:
        """Publish an observability event to the K1 Bus.

        Delegates to FabricBusAdapter.emit() (fire-and-forget).
        """
        self._bus.emit(topic, payload)
```

#### HealthAdapter Class

```python
class HealthAdapter:
    """Implements IHealthPort by composing CircuitBreaker + pipeline state.

    This adapter does NOT wrap an external dependency — it composes
    MW-internal state into the IHealthPort protocol.

    Constructor Args:
        circuit_breaker: CircuitBreaker instance (from Phase 5 E-MW-5.3).
        get_pending_count: Callable returning pending batch count.
        get_started: Callable returning whether service is started.
    """

    __slots__ = ("_circuit_breaker", "_get_pending_count", "_get_started")

    def __init__(
        self,
        circuit_breaker: Any,
        get_pending_count: Callable[[], int],
        get_started: Callable[[], bool],
    ) -> None:
        self._circuit_breaker = circuit_breaker
        self._get_pending_count = get_pending_count
        self._get_started = get_started

    async def is_ready(self) -> bool:
        """MW is ready if started and circuit breaker is not open."""
        return self._get_started() and not self._circuit_breaker.is_open

    async def health_check(self) -> HealthStatus:
        """Detailed health status for Fabric probes."""
        started = self._get_started()
        cb_open = self._circuit_breaker.is_open

        return HealthStatus(
            is_healthy=started and not cb_open,
            llm_circuit_open=cb_open,
            pending_batch_count=self._get_pending_count(),
            last_extraction_ms=0.0,  # tracked via metrics, not here
            detail="running" if started else "stopped",
        )
```

#### Implementation Items

| Item | File | Work |
|------|------|------|
| I-MW-5.1.1 | `k1/memory_writer/adapters/bridge_command_adapter.py` | `BridgeCommandAdapter` class as shown above. Imports: `typing.Any`, `logging`. Lazy import of `bridge.core.envelope_builder.CommandEnvelope` in `submit_batch()` |
| I-MW-5.1.2 | `k1/memory_writer/adapters/event_subscription_adapter.py` | `EventSubscriptionAdapter` class as shown above. Imports: `asyncio`, `logging`, `typing.Any`, `typing.Callable`, `typing.Coroutine`, `k1.memory_writer.types.Subscription` |
| I-MW-5.1.3 | `k1/memory_writer/adapters/health_adapter.py` | `HealthAdapter` class as shown above. Imports: `typing.Any`, `typing.Callable`, `k1.memory_writer.types.HealthStatus` |
| I-MW-5.1.4 | `k1/memory_writer/adapters/__init__.py` (modify) | Add re-exports: `BridgeCommandAdapter`, `EventSubscriptionAdapter`, `HealthAdapter` |
| I-MW-5.1.5 | `tests/k1/memory_writer/test_adapters_prod.py` | 28 tests (see test specification below) |

#### Test Specification: `tests/k1/memory_writer/test_adapters_prod.py`

**28 tests** organized in 6 test classes:

All tests use mock/stub objects for the wrapped dependencies (`FakeKernelCommandPort`, `FakeFabricBusAdapter`). No real HTTP, no real Bus.

```text
class TestBridgeCommandAdapterSubmit:               # 5 tests
  test_submit_delegates_to_command_port              — submit(topic, schema, body) → kcp.submit called with matching args
  test_submit_extracts_trace_id_from_body            — body has trace_id → passed to kcp.submit(trace_id=)
  test_submit_missing_trace_id_uses_empty            — body has no trace_id → kcp.submit(trace_id="")
  test_submit_propagates_contract_violation           — kcp raises ContractViolationError → propagated
  test_submit_propagates_generic_error                — kcp raises RuntimeError → propagated

class TestBridgeCommandAdapterBatch:                # 5 tests
  test_submit_batch_translates_to_command_envelopes  — 3 envelope dicts → 3 CommandEnvelope objects
  test_submit_batch_empty_list_noop                  — empty list → kcp.submit_batch NOT called
  test_submit_batch_extracts_trace_ids               — each envelope's trace_id passed to CommandEnvelope
  test_submit_batch_propagates_contract_violation     — kcp batch raises → propagated
  test_submit_batch_all_fields_mapped                — topic, body, schema_uri, trace_id all mapped correctly

class TestEventSubscriptionAdapterSubscribe:        # 5 tests
  test_subscribe_returns_subscription                — subscribe(topic, handler) → Subscription with sub_id and topic
  test_subscribe_delegates_to_bus                    — bus.subscribe called with topic and sync wrapper
  test_handler_invoked_on_event                      — bus fires event → async handler called with payload dict
  test_handler_receives_payload_only                 — handler gets payload (not topic) per MW protocol
  test_multiple_subscriptions_tracked                — 3 subscribe calls → 3 entries in internal map

class TestEventSubscriptionAdapterUnsubscribe:      # 3 tests
  test_unsubscribe_removes_subscription              — unsubscribe(sub_id) → bus.unsubscribe called with handle
  test_unsubscribe_unknown_id_noop                   — unknown sub_id → no error, bus.unsubscribe NOT called
  test_unsubscribe_clears_internal_tracking          — after unsubscribe → sub_id no longer in _subscriptions

class TestEventSubscriptionAdapterPublish:          # 3 tests
  test_publish_delegates_to_bus_emit                 — publish(topic, payload) → bus.emit(topic, payload)
  test_publish_fire_and_forget                       — bus.emit raises → publish does NOT raise (best-effort)
  test_publish_carries_all_fields                    — payload dict passed unchanged to bus.emit

class TestHealthAdapter:                            # 7 tests
  test_is_ready_true_when_started_circuit_closed     — started=True, cb.is_open=False → True
  test_is_ready_false_when_stopped                   — started=False → False
  test_is_ready_false_when_circuit_open              — started=True, cb.is_open=True → False
  test_health_check_healthy                          — started + closed → is_healthy=True, detail="running"
  test_health_check_unhealthy_stopped                — not started → is_healthy=False, detail="stopped"
  test_health_check_circuit_open                     — cb.is_open=True → llm_circuit_open=True
  test_health_check_pending_count                    — get_pending_count returns 5 → pending_batch_count=5
```

**Acceptance criteria:**

- [x] All 28 tests pass
- [x] `BridgeCommandAdapter.submit()` extracts `trace_id` from body (MW-10)
- [x] `BridgeCommandAdapter.submit_batch()` translates envelope dicts → `CommandEnvelope` objects
- [x] `EventSubscriptionAdapter.subscribe()` wraps async handler for sync bus
- [x] `EventSubscriptionAdapter` returns MW `Subscription` (not Fabric handle)
- [x] `EventSubscriptionAdapter.publish()` delegates to `bus.emit()` (fire-and-forget)
- [x] `HealthAdapter.is_ready()` requires started AND circuit not open
- [x] `HealthAdapter.health_check()` returns `HealthStatus` with all fields populated
- [x] All adapters use `Any` constructor typing (no import coupling)

---

### E-MW-5.2: Test Adapters

**Design ref:** Integration testing support for Phases 4 lifecycle tests

#### Problem Statement

Phase 4 integration tests (E-MW-4.4) and Phase 5 Fabric integration tests require complete fake implementations of all 5 ports. These must be co-located in a single module for easy test setup.

**Design goals:**

1. **In-memory everything** — no real I/O, no real LLM, no real Bridge
2. **Capture + assert** — test code can inspect what MW submitted to Bridge, what events were published
3. **Configurable failures** — each fake can be told to raise errors for error-path testing
4. **Canned responses** — `FakeModelHub` returns configured extraction responses

#### Test Adapter Classes

```python
class FakeSessionReadPort:
    """In-memory session state for testing.

    Accepts a dict of section_name -> section_data at construction.
    snapshot() returns configured sections. read_section() returns by name.
    Optionally raises on configured section names (for error testing).
    """

    def __init__(
        self,
        sections: dict[str, dict] | None = None,
        *,
        fail_on: set[str] | None = None,
    ) -> None:
        self._sections = sections or {}
        self._fail_on = fail_on or set()

    async def snapshot(self, sections: list[str]) -> dict[str, Any]:
        result = {}
        for name in sections:
            data = await self.read_section(name)
            if data is not None:
                result[name] = data
        return result

    async def read_section(self, name: str) -> dict | None:
        if name in self._fail_on:
            raise RuntimeError(f"FakeSessionReadPort: configured failure for {name}")
        return self._sections.get(name)


class FakeModelHubPort:
    """Canned LLM responses for testing.

    Returns pre-configured ChatResponse. Can be set to raise
    for error-path testing.
    """

    def __init__(
        self,
        response_content: str = "[]",
        *,
        fail: bool = False,
        fail_count: int = 0,
    ) -> None:
        self._response_content = response_content
        self._fail = fail
        self._fail_count = fail_count
        self._call_count = 0
        self.calls: list[dict] = []  # capture for assertions

    async def chat(
        self,
        messages: list[dict[str, str]],
        budget_tokens: int,
        model_hint: str,
    ) -> ChatResponse:
        self._call_count += 1
        self.calls.append({
            "messages": messages,
            "budget_tokens": budget_tokens,
            "model_hint": model_hint,
        })

        if self._fail or (self._fail_count > 0 and self._call_count <= self._fail_count):
            raise RuntimeError("FakeModelHubPort: configured LLM failure")

        return ChatResponse(
            content=self._response_content,
            token_usage=len(self._response_content),
            model="fake-model",
            latency_ms=10.0,
        )


class FakeBridgeCommandPort:
    """Captures Bridge submissions for test assertions.

    All submitted envelopes stored in .submitted list.
    Can be set to raise for error-path testing.
    """

    def __init__(self, *, fail: bool = False) -> None:
        self._fail = fail
        self.submitted: list[dict] = []
        self.batches: list[list[dict]] = []

    async def submit(self, topic: str, schema_uri: str, body: dict) -> None:
        if self._fail:
            raise RuntimeError("FakeBridgeCommandPort: configured failure")
        self.submitted.append({"topic": topic, "schema_uri": schema_uri, "body": body})

    async def submit_batch(self, envelopes: list[dict]) -> None:
        if self._fail:
            raise RuntimeError("FakeBridgeCommandPort: configured failure")
        self.batches.append(envelopes)
        self.submitted.extend(envelopes)


class FakeEventSubscriptionPort:
    """In-memory K1 Bus for testing.

    subscribe() stores handlers. publish() dispatches to matching handlers.
    Captured events stored in .published for assertions.
    """

    def __init__(self) -> None:
        self._handlers: dict[str, list[Callable]] = {}
        self._next_id: int = 0
        self._subscriptions: dict[str, str] = {}  # sub_id -> topic
        self.published: list[tuple[str, dict]] = []  # (topic, payload) capture

    async def subscribe(
        self,
        topic: str,
        handler: Callable[..., Coroutine[Any, Any, None]],
    ) -> Subscription:
        self._next_id += 1
        sub_id = f"fake-sub-{self._next_id}"
        self._handlers.setdefault(topic, []).append(handler)
        self._subscriptions[sub_id] = topic
        return Subscription(subscription_id=sub_id, topic=topic)

    async def unsubscribe(self, subscription_id: str) -> None:
        self._subscriptions.pop(subscription_id, None)

    async def publish(self, topic: str, payload: dict) -> None:
        self.published.append((topic, payload))
        for handler in self._handlers.get(topic, []):
            await handler(payload)


class FakeHealthPort:
    """Configurable health port for testing."""

    def __init__(
        self,
        *,
        ready: bool = True,
        healthy: bool = True,
        circuit_open: bool = False,
    ) -> None:
        self._ready = ready
        self._healthy = healthy
        self._circuit_open = circuit_open

    async def is_ready(self) -> bool:
        return self._ready

    async def health_check(self) -> HealthStatus:
        return HealthStatus(
            is_healthy=self._healthy,
            llm_circuit_open=self._circuit_open,
            pending_batch_count=0,
            last_extraction_ms=0.0,
            detail="fake",
        )
```

#### Implementation Items

| Item | File | Work |
|------|------|------|
| I-MW-5.2.1 | `k1/memory_writer/adapters/test_adapters.py` | All 5 fake port classes as shown above. Imports: `typing`, `k1.memory_writer.types.ChatResponse`, `k1.memory_writer.types.HealthStatus`, `k1.memory_writer.types.Subscription` |
| I-MW-5.2.2 | `tests/k1/memory_writer/test_adapters_test.py` | 20 tests (see test specification below) |

#### Test Specification: `tests/k1/memory_writer/test_adapters_test.py`

**20 tests** organized in 5 test classes:

```text
class TestFakeSessionReadPort:                      # 4 tests
  test_snapshot_returns_configured_sections           — 3 sections → all returned
  test_read_section_missing_returns_none              — unknown section → None
  test_fail_on_raises                                — fail_on={"plan"} → read_section("plan") raises
  test_empty_snapshot                                — no sections configured → empty dict

class TestFakeModelHubPort:                         # 4 tests
  test_chat_returns_canned_response                  — response_content="[{...}]" → ChatResponse.content matches
  test_chat_captures_calls                           — 2 calls → .calls has 2 entries with messages/budget/hint
  test_fail_raises                                   — fail=True → chat raises RuntimeError
  test_fail_count_temporary                          — fail_count=2 → first 2 calls fail, 3rd succeeds

class TestFakeBridgeCommandPort:                    # 4 tests
  test_submit_captures                               — submit(topic, schema, body) → .submitted has 1 entry
  test_submit_batch_captures                         — submit_batch([3 envs]) → .batches has 1, .submitted has 3
  test_fail_raises                                   — fail=True → submit raises RuntimeError
  test_empty_batch_ok                                — submit_batch([]) → no error

class TestFakeEventSubscriptionPort:                # 5 tests
  test_subscribe_returns_subscription                — subscribe → Subscription with id and topic
  test_publish_dispatches_to_handler                 — subscribe + publish → handler called with payload
  test_publish_captures                              — publish → .published has (topic, payload)
  test_unsubscribe_removes                           — unsubscribe → handler no longer called
  test_multiple_handlers_same_topic                  — 2 handlers on same topic → both called

class TestFakeHealthPort:                           # 3 tests
  test_is_ready_default_true                         — default construction → is_ready returns True
  test_health_check_default_healthy                  — default → is_healthy=True
  test_configurable_circuit_open                     — circuit_open=True → llm_circuit_open=True
```

**Acceptance criteria:**

- [x] All 20 tests pass
- [x] Each fake implements the corresponding MW port protocol
- [x] `FakeModelHubPort` captures all call args for assertion
- [x] `FakeBridgeCommandPort` captures all submitted envelopes
- [x] `FakeEventSubscriptionPort` captures published events AND dispatches to handlers
- [x] All fakes support configurable failure injection
- [x] Fakes usable by Phase 4 integration tests (E-MW-4.4) and Phase 5 Fabric tests (E-MW-5.4)

---

### E-MW-5.3: Circuit Breaker

**Design ref:** Architecture §24 (circuit breaker spec), `MWConfig` (failure_threshold=3, recovery_probe_seconds=30)

#### Problem Statement

Phase 4 `MemoryWriterPipeline` references `circuit_breaker.is_open`, `circuit_breaker.record_success()`, `circuit_breaker.record_failure()`. Phase 4 tests use `FakeCircuitBreaker`. No real implementation exists.

The circuit breaker protects the LLM call path. Architecture §24 specifies:

```yaml
circuit_breaker:
  timeout_ms: 5000           # Per LLM call (enforced by ModelHub, not CB)
  failure_threshold: 5       # Architecture spec: 5 failures/minute
  failure_window_ms: 60000   # 1 minute sliding window
  half_open_after_ms: 60000  # Try one request after 1 minute
  fallback: "skip_turn"
```

**MWConfig values** (from `config.py`):

- `circuit_breaker_failure_threshold = 3` (stricter than architecture spec — config overrides)
- `circuit_breaker_recovery_probe_seconds = 30` (faster recovery probe than architecture spec)

**State machine:**

```text
              record_failure (count < threshold)
         ┌──────────────────────┐
         │                      │
         ▼                      │
      CLOSED ─────record_failure (count >= threshold)────→ OPEN
         ▲                                                   │
         │                                                   │
  record_success                            after recovery_probe_seconds
         │                                                   │
         │                                                   ▼
      CLOSED ◄────record_success──────────────────── HALF_OPEN
                                                        │
                                        record_failure  │
                                             │          │
                                             └──→ OPEN ─┘
```

#### CircuitBreaker Class

```python
class CircuitBreakerState(str, Enum):
    CLOSED = "CLOSED"
    OPEN = "OPEN"
    HALF_OPEN = "HALF_OPEN"


class CircuitBreaker:
    """LLM circuit breaker for Memory Writer.

    Three states:
      CLOSED:    Normal operation. Tracks consecutive failures.
      OPEN:      All calls blocked. Timer running for recovery probe.
      HALF_OPEN: One probe call allowed. Success → CLOSED, failure → OPEN.

    Uses consecutive failure count (not sliding window) for simplicity.
    This matches the MWConfig model which provides a simple threshold integer.

    Thread-safe: single-session MW means single-threaded access,
    but uses properties for safe state reads.
    """

    def __init__(
        self,
        failure_threshold: int = 3,
        recovery_probe_seconds: float = 30.0,
        *,
        clock: Callable[[], float] | None = None,
    ) -> None:
        self._failure_threshold = failure_threshold
        self._recovery_probe_seconds = recovery_probe_seconds
        self._clock = clock or time.monotonic

        self._state = CircuitBreakerState.CLOSED
        self._consecutive_failures: int = 0
        self._last_failure_time: float = 0.0
        self._total_trips: int = 0  # lifetime counter for metrics

    @property
    def is_open(self) -> bool:
        """Check if calls should be blocked.

        Returns True for OPEN state.
        For OPEN state, also checks if recovery probe time has elapsed
        → transitions to HALF_OPEN and returns False (allow one probe).
        """
        if self._state == CircuitBreakerState.CLOSED:
            return False

        if self._state == CircuitBreakerState.HALF_OPEN:
            return False  # Allow one probe call

        # OPEN: check if recovery time elapsed
        elapsed = self._clock() - self._last_failure_time
        if elapsed >= self._recovery_probe_seconds:
            self._state = CircuitBreakerState.HALF_OPEN
            return False  # Allow probe

        return True  # Still OPEN

    @property
    def state(self) -> CircuitBreakerState:
        """Current circuit breaker state (for observability)."""
        # Trigger potential OPEN → HALF_OPEN transition
        _ = self.is_open
        return self._state

    @property
    def consecutive_failures(self) -> int:
        return self._consecutive_failures

    @property
    def total_trips(self) -> int:
        """Total number of CLOSED → OPEN transitions (lifetime)."""
        return self._total_trips

    def record_success(self) -> None:
        """Record a successful LLM call.

        CLOSED: reset failure count.
        HALF_OPEN: transition to CLOSED (recovery confirmed).
        OPEN: should not happen (is_open returns True, pipeline skips).
        """
        if self._state == CircuitBreakerState.HALF_OPEN:
            log.info("MW: circuit breaker HALF_OPEN → CLOSED (probe succeeded)")
        self._state = CircuitBreakerState.CLOSED
        self._consecutive_failures = 0

    def record_failure(self) -> None:
        """Record a failed LLM call.

        CLOSED: increment failure count. If >= threshold → OPEN.
        HALF_OPEN: probe failed → back to OPEN.
        OPEN: should not happen (calls blocked).
        """
        self._consecutive_failures += 1
        self._last_failure_time = self._clock()

        if self._state == CircuitBreakerState.HALF_OPEN:
            self._state = CircuitBreakerState.OPEN
            log.info("MW: circuit breaker HALF_OPEN → OPEN (probe failed)")
            return

        if self._consecutive_failures >= self._failure_threshold:
            self._state = CircuitBreakerState.OPEN
            self._total_trips += 1
            log.warning(
                "MW: circuit breaker CLOSED → OPEN",
                consecutive_failures=self._consecutive_failures,
                threshold=self._failure_threshold,
            )

    def reset(self) -> None:
        """Force reset to CLOSED state (for testing/admin)."""
        self._state = CircuitBreakerState.CLOSED
        self._consecutive_failures = 0
```

#### Implementation Items

| Item | File | Work |
|------|------|------|
| I-MW-5.3.1 | `k1/memory_writer/health/__init__.py` | Package init. Re-exports: `CircuitBreaker`, `CircuitBreakerState` |
| I-MW-5.3.2 | `k1/memory_writer/health/circuit_breaker.py` | `CircuitBreaker` class + `CircuitBreakerState` enum as shown above. Imports: `enum.Enum`, `time`, `logging`, `typing.Callable` |
| I-MW-5.3.3 | `tests/k1/memory_writer/test_circuit_breaker.py` | 22 tests (see test specification below) |

#### Test Specification: `tests/k1/memory_writer/test_circuit_breaker.py`

**22 tests** organized in 5 test classes:

All tests use a fake clock (`lambda: fake_time`) injected via the `clock` parameter for deterministic time control.

```text
class TestCircuitBreakerInitialState:               # 3 tests
  test_initial_state_closed                          — new CB → state == CLOSED
  test_initial_is_open_false                         — new CB → is_open == False
  test_initial_consecutive_failures_zero             — new CB → consecutive_failures == 0

class TestCircuitBreakerClosedState:                # 4 tests
  test_success_keeps_closed                          — record_success → still CLOSED
  test_single_failure_stays_closed                   — 1 failure (threshold=3) → still CLOSED
  test_threshold_minus_one_stays_closed              — 2 failures (threshold=3) → still CLOSED
  test_success_resets_failure_count                  — 2 failures + 1 success → consecutive_failures=0

class TestCircuitBreakerOpenState:                  # 6 tests
  test_threshold_failures_opens                      — 3 failures (threshold=3) → OPEN
  test_is_open_true_when_open                        — OPEN state → is_open == True
  test_total_trips_incremented                       — CLOSED → OPEN → total_trips == 1
  test_open_blocks_within_recovery_window            — OPEN + 10s elapsed (probe=30s) → still is_open=True
  test_open_allows_probe_after_recovery              — OPEN + 31s elapsed → is_open=False (HALF_OPEN)
  test_consecutive_failures_tracked                  — 3 failures → consecutive_failures == 3

class TestCircuitBreakerHalfOpenState:              # 6 tests
  test_half_open_allows_one_call                     — HALF_OPEN → is_open=False
  test_probe_success_closes                          — HALF_OPEN + record_success → CLOSED
  test_probe_success_resets_failures                 — HALF_OPEN + success → consecutive_failures=0
  test_probe_failure_reopens                         — HALF_OPEN + record_failure → OPEN
  test_reopen_restarts_recovery_timer                — HALF_OPEN → OPEN → must wait full recovery_probe_seconds again
  test_multiple_trips_counted                        — CLOSED→OPEN→HALF_OPEN→OPEN → total_trips==2

class TestCircuitBreakerReset:                      # 3 tests
  test_reset_from_open                               — OPEN + reset() → CLOSED, consecutive_failures=0
  test_reset_from_half_open                          — HALF_OPEN + reset() → CLOSED
  test_reset_idempotent                              — CLOSED + reset() → still CLOSED
```

**Acceptance criteria:**

- [x] All 22 tests pass
- [x] CLOSED → OPEN after `failure_threshold` consecutive failures
- [x] OPEN → HALF_OPEN after `recovery_probe_seconds` elapsed
- [x] HALF_OPEN → CLOSED on `record_success()`
- [x] HALF_OPEN → OPEN on `record_failure()`
- [x] `record_success()` resets consecutive failure count to 0
- [x] `is_open` returns True only in OPEN state (within recovery window)
- [x] `is_open` auto-transitions OPEN → HALF_OPEN when recovery time elapsed
- [x] `total_trips` counts lifetime CLOSED → OPEN transitions
- [x] Fake clock injection enables deterministic testing
- [x] `reset()` force-returns to CLOSED (for testing/admin)

---

### E-MW-5.4: Fabric Integration

**Design ref:** Architecture §17 (agent contract, lifecycle), Fabric `AgentFactory` spawn pattern, `AgentPool` (idle_pool, idle_ttl)

#### Problem Statement

`MemoryWriterFactory.create()` (Phase 4) produces a `MemoryWriterService`, but nothing wires it to Fabric's session lifecycle. When Fabric creates a session, it must:

1. Call `MemoryWriterFactory.create(ports)` to build a `MemoryWriterService`
2. Call `service.start()` to subscribe to `turn.complete.v1`
3. On session end, call `service.stop()` to flush pending + unsubscribe

**Fabric integration point:** This is a thin registration layer. MW registers itself as a session-bound agent via Fabric's `AgentFactory` pattern:

```python
# Pseudocode — what Fabric session creation calls:
mw_service = MemoryWriterFactory.create(
    session_read_port=session_read_adapter,
    model_hub_port=model_hub_adapter,
    bridge_command_port=bridge_command_adapter,
    event_subscription_port=event_subscription_adapter,
    health_port=health_adapter,
    config=mw_config,
)
await mw_service.start()
# Session runs... turns processed via event subscription...
await mw_service.stop()
```

**AgentPool reuse:** Per Architecture §17, MW has `idle_pool: true, idle_ttl_ms: 300000` (5 minutes). Between sessions, the service sits in the pool. On reuse:

- `MemoryWriterService` is reattached to a new session's ports
- `start()` re-subscribes to events for the new session
- Dedup set was cleared by previous `stop()`, so no stale state

**This epic creates:**

1. `MemoryWriterFabricRegistration` — a registration class that Fabric calls to create MW for a session
2. Integration tests verifying the full lifecycle with test adapters

#### MemoryWriterFabricRegistration Class

```python
class MemoryWriterFabricRegistration:
    """Registers Memory Writer with Fabric's agent lifecycle.

    Called by Fabric during session initialization to create and
    wire a MemoryWriterService for the session.

    This class is the bridge between Fabric's generic agent lifecycle
    and MW's specific creation requirements.
    """

    @staticmethod
    async def create_for_session(
        session_read_adapter: Any,
        model_hub_adapter: Any,
        bridge_command_adapter: Any,
        event_subscription_adapter: Any,
        config: MWConfig | None = None,
    ) -> MemoryWriterService:
        """Create and start a MemoryWriterService for a session.

        Args:
            session_read_adapter: SessionReadAdapter instance.
            model_hub_adapter: ModelHubAdapter instance.
            bridge_command_adapter: BridgeCommandAdapter instance.
            event_subscription_adapter: EventSubscriptionAdapter instance.
            config: MWConfig (optional, defaults to MWConfig()).

        Returns:
            Started MemoryWriterService.

        Raises:
            InvariantViolation: If init-time invariant checks fail.
        """
        config = config or MWConfig()

        # Circuit breaker created here (Phase 5 E-MW-5.3)
        circuit_breaker = CircuitBreaker(
            failure_threshold=config.circuit_breaker_failure_threshold,
            recovery_probe_seconds=config.circuit_breaker_recovery_probe_seconds,
        )

        # Health adapter composes CB + service state
        health_adapter = HealthAdapter(
            circuit_breaker=circuit_breaker,
            get_pending_count=lambda: 0,  # Updated after pipeline creation
            get_started=lambda: service.is_started,
        )

        service = MemoryWriterFactory.create(
            session_read_port=session_read_adapter,
            model_hub_port=model_hub_adapter,
            bridge_command_port=bridge_command_adapter,
            event_subscription_port=event_subscription_adapter,
            health_port=health_adapter,
            config=config,
        )

        await service.start()
        return service

    @staticmethod
    async def teardown_session(service: MemoryWriterService) -> None:
        """Stop and clean up a MemoryWriterService.

        Called by Fabric during session termination / DRAINING phase.
        Flushes pending batches and unsubscribes from events.
        """
        await service.stop()
```

#### Implementation Items

| Item | File | Work |
|------|------|------|
| I-MW-5.4.1 | `k1/memory_writer/fabric_registration.py` | `MemoryWriterFabricRegistration` class as shown above. Imports: `typing.Any`, `k1.memory_writer.factory.MemoryWriterFactory`, `k1.memory_writer.service.MemoryWriterService`, `k1.memory_writer.config.MWConfig`, `k1.memory_writer.health.circuit_breaker.CircuitBreaker`, `k1.memory_writer.adapters.health_adapter.HealthAdapter` |
| I-MW-5.4.2 | `k1/memory_writer/__init__.py` (modify) | Add public API exports: `MemoryWriterFabricRegistration`, `MemoryWriterFactory`, `MemoryWriterService`, `MWConfig` |
| I-MW-5.4.3 | `tests/k1/memory_writer/test_fabric_integration.py` | 18 tests (see test specification below) |

#### Test Specification: `tests/k1/memory_writer/test_fabric_integration.py`

**18 tests** organized in 4 test classes:

All tests use the test adapters from E-MW-5.2 (`FakeSessionReadPort`, `FakeModelHubPort`, `FakeBridgeCommandPort`, `FakeEventSubscriptionPort`).

```text
class TestFabricRegistrationCreate:                 # 5 tests
  test_create_for_session_returns_started_service    — create_for_session → service.is_started == True
  test_create_for_session_with_default_config        — config=None → uses MWConfig() defaults
  test_create_for_session_with_custom_config         — custom MWConfig → passed through to factory
  test_create_for_session_invariant_failure           — bad config → InvariantViolation propagated
  test_create_for_session_subscribes_to_events       — after create → dispatcher subscribed to turn.complete.v1

class TestFabricRegistrationTeardown:               # 3 tests
  test_teardown_stops_service                        — teardown_session → service.is_started == False
  test_teardown_flushes_pending                      — pending envelopes → teardown submits to Bridge
  test_teardown_idempotent                           — teardown twice → no error

class TestFabricSessionLifecycle:                   # 6 tests
  test_full_session_create_process_teardown          — create → publish turn → atoms extracted → teardown
  test_multi_turn_session_with_fabric                — create → 5 turns → all processed → teardown
  test_trivial_turns_filtered                        — "ok" turns → filter skips → no LLM call
  test_llm_failure_handled                           — FakeModelHub fails → turn skipped, next turn OK
  test_circuit_breaker_integration                   — 3 LLM failures → circuit opens → turns skipped → recovery → turns processed
  test_bridge_failure_handled                        — FakeBridge fails → no crash → next turn OK

class TestFabricPoolReuse:                          # 4 tests
  test_teardown_clears_dedup_state                   — teardown → same turn_id accepted in new session
  test_create_after_teardown                         — teardown → create_for_session again → works
  test_independent_sessions                          — 2 concurrent sessions → each has own service → no shared state
  test_health_check_after_create                     — create → health_check → is_healthy=True
```

**Acceptance criteria:**

- [x] All 18 tests pass
- [x] `create_for_session()` returns a started `MemoryWriterService`
- [x] `teardown_session()` stops service, flushes pending, clears state
- [x] Full session lifecycle works: create → turns → teardown
- [x] Error resilience: LLM failures, Bridge failures handled gracefully
- [x] Circuit breaker integration: opens after threshold, recovers on probe
- [x] No shared state between sessions (MW is session-bound)
- [x] Teardown clears dedup state → same turn_id accepted in new session
- [x] Invariant violations propagated from factory

---

### Phase 5 Summary

| Epic | Tests | New Files | Modified Files |
|------|-------|-----------|----------------|
| E-MW-5.1 | 28 | `adapters/bridge_command_adapter.py`, `adapters/event_subscription_adapter.py`, `adapters/health_adapter.py` | `adapters/__init__.py` |
| E-MW-5.2 | 20 | `adapters/test_adapters.py` | — |
| E-MW-5.3 | 22 | `health/__init__.py`, `health/circuit_breaker.py` | — |
| E-MW-5.4 | 18 | `fabric_registration.py` | `__init__.py` |
| **Total** | **88** | **6 new files** | **2 modified files** |

**Phase 5 invariants enforced:**

- MW-03: `BridgeCommandAdapter` is the ONLY output path to K0 (via Bridge `KernelCommandPort`)
- MW-09: Offline queueing delegated to Bridge's `LocalOutbox` (KernelCommandPort already handles this)
- MW-10: `BridgeCommandAdapter` extracts `trace_id` from body and passes to Bridge
- Circuit breaker: `failure_threshold=3` (from MWConfig), `recovery_probe_seconds=30` (from MWConfig)
- All adapters use `Any` constructor typing to avoid import coupling

**Phase 5 prerequisites (from earlier phases):**

- Phase 0: All 5 port protocols (`ISessionReadPort`, `IModelHubPort`, `IBridgeCommandPort`, `IEventSubscriptionPort`, `IHealthPort`)
- Phase 4: `MemoryWriterFactory`, `MemoryWriterService`, `MemoryWriterPipeline`, `TurnDispatcher`
- Existing: `SessionReadAdapter` (Phase 0 E-0.5.6), `ModelHubAdapter` (Phase 0 E-0.5.3)
- External: `KernelCommandPort` (Bridge), `FabricBusAdapter` (K1 Bus), `AgentPool` (Fabric)

**Phase 5 outputs (MW subsystem complete):**

- `MemoryWriterFabricRegistration` — Fabric calls this to create MW per session
- 3 production adapters — connect MW ports to real K1 infrastructure
- 5 test adapters — enable fast integration testing
- `CircuitBreaker` — protects LLM call path with CLOSED/OPEN/HALF_OPEN state machine

---

## 14. Dependency Map

```
Phase P ──── no deps (Concierge-side changes, independent of MW)
   │
Phase 0 ──── no deps (foundation fixes)
   │
Phase 1 ──── depends on: Phase P (tool call data in Turn.metadata),
   │         types.py, ports/, config.py, events.py,
   │         context_assembly.py, place_resolver.py (all exist ✅)
   │
Phase 2 ──── depends on: Phase 1 (ExtractionContext with tool_calls),
   │         IModelHubPort (exists ✅), ModelHubAdapter (exists ✅)
   │
Phase 3 ──── depends on: Phase 2 (MemoryAtom output), IBridgeCommandPort
   │         (exists ✅)
   │
Phase 4 ──── depends on: Phases 1-3 (all stages), IEventSubscriptionPort
   │         (exists ✅)
   │
Phase 5 ──── depends on: Phase 4 (factory/service), Fabric, Bridge
             connector, Bus concrete
```

**Note:** Phase P and Phase 0 can run in parallel — Phase P touches Concierge code,
Phase 0 touches MW code. No overlap.

### External Dependencies

| Dependency | Module | Status | Required For |
|-----------|--------|--------|--------------|
| SessionStateManager | `k1/sessionstate/` | ✅ Exists | ISessionReadPort adapter (exists) |
| ModelHub execute() | `k1/model_hub/` | ✅ Exists | IModelHubPort adapter (exists) |
| Bridge connector | `bridge/connector/` | ✅ Exists | IBridgeCommandPort adapter (Phase 5) |
| K1 Bus | `k1/bus/` | ✅ Exists | IEventSubscriptionPort adapter (Phase 5) |
| Fabric session spawn | `k1/fabric/` | ⚠️ Needs wiring | Phase 5 integration |
| ToolCallSummary in Turn | `k1/concierge/tools/` | ⚠️ Phase P | Filter R6, Trigger T6, ContextBuilder tool extraction |

---

## 15. Test Strategy

### Test Pyramid

| Level | Count (est.) | Scope |
|-------|-------------|-------|
| Unit | ~340 new | Each class/function in isolation (Phases 1-5) |
| Integration | ~106 new | Stage-to-stage, pipeline, lifecycle (Phases 4-5) |
| End-to-end | ~32 new | Full pipeline + Fabric integration (E-MW-4.4, E-MW-5.4) |
| **New tests total** | **478** | Phase 1: 94, Phase 2: 78, Phase 3: 112, Phase 4: 106, Phase 5: 88 |
| **Existing** | **208** | Types, invariants, adapters, place resolver |
| **Projected total** | **~686** | |

### Testing Patterns

1. **Frozen dataclass tests**: Construction, field access, immutability, defaults
2. **Invariant enforcement**: Each MW-XX has dedicated violation + pass tests
3. **Stage isolation**: Each stage tested with mock input/output, no real ports
4. **Pipeline integration**: Test adapters provide canned responses, verify envelope output
5. **Timing assertions**: MW-02 (<1ms read), MW-08 (250ms batch window)
6. **Privacy band tests**: GREEN/AMBER/RED field stripping verification

---

## 16. Risk Register

| # | Risk | Impact | Mitigation |
|---|------|--------|-----------|
| R1 | LLM output parsing failures | Extraction drops | Validator drops invalid, logs. Few-shot examples in prompt |
| R2 | Person resolver ambiguity | Wrong person_id | Fallback to generated ID. Open design Q#2 |
| R3 | ModelHub not available | No extraction | Circuit breaker (3 failures → OPEN). Turn skipped, retryable next turn |
| R4 | Bridge offline | Envelopes lost | MW-09: LocalOutbox (offline-safe). Eventually delivered |
| R5 | Token budget exceeded | LLM error | MW-06: hard 2000 token cap. Context builder truncates |
| R6 | Filter too aggressive | Missed memories | Filter rule thresholds configurable. Open design Q#7 |
| R7 | Batch window timing | Stale envelopes | 250ms is conservative. Configurable via MWConfig |
| R8 | Tool call data missing | MW misses tool-mediated episodic events | Phase P is prerequisite. If not done, MW still works (degrades gracefully — tool calls appear as plain conversation, no structured tool context). Filter R6 and trigger T6 simply never fire |
| R9 | Tool call arg redaction | Sensitive data in tool arguments leaks to memory | ToolCallSummary truncation redacts fields containing "password", "token", "secret", "key". Privacy enforcer (Stage 5) applies band-level stripping |
| R10 | Correction signal false positives | K0 URE incorrectly EVOLVEs truth records | LLM prompt must include few-shot correction examples. Require high confidence (≥0.85) for correction_signal=true. UltraBERT NLI head can cross-validate |
| R11 | Observation context fields incomplete | K0 R5 observation-driven algorithms get partial data | FieldMapper explicitly maps ALL 32 st_observations fields. Integration test validates field completeness against K0 schema |
| R12 | Sentiment label→score mapping drift | MW's 5-class→float mapping doesn't match UltraBERT's weighted sum | Use same SENTIMENT_TO_VALENCE mapping as `k0/runtime/ultrabert_adapter.py` (0.1/0.3/0.5/0.7/0.9). P02 M04 validates anyway |
| R13 | Geohash computation accuracy | Wrong geohash_6 causes spatial reconciliation errors | PlaceResolver geocoding is best-effort. K0 stage_42 (geo_metadata) handles fallback. MW sets geohash only when confidence ≥0.8 |

---

## 17. File Inventory — Exists vs Missing

### ✅ Exists (16 files)

```
k1/memory_writer/__init__.py                      (EMPTY — needs Phase 0)
k1/memory_writer/types.py
k1/memory_writer/config.py
k1/memory_writer/events.py
k1/memory_writer/invariants.py
k1/memory_writer/context_assembly.py
k1/memory_writer/place_resolver.py
k1/memory_writer/ports/__init__.py
k1/memory_writer/ports/session_read_port.py
k1/memory_writer/ports/bridge_command_port.py
k1/memory_writer/ports/event_subscription_port.py
k1/memory_writer/ports/model_hub_port.py
k1/memory_writer/ports/health_port.py
k1/memory_writer/adapters/__init__.py
k1/memory_writer/adapters/session_read_adapter.py
k1/memory_writer/adapters/model_hub_adapter.py
```

### ❌ Missing (29 files — to be created)

```
# Phase 1: Filter + Context Assembly
k1/memory_writer/filter/__init__.py
k1/memory_writer/filter/rules.py
k1/memory_writer/filter/relevance_filter.py
k1/memory_writer/context/__init__.py
k1/memory_writer/context/session_reader.py
k1/memory_writer/context/context_builder.py
k1/memory_writer/context/person_resolver.py

# Phase 2: Extraction
k1/memory_writer/extraction/__init__.py
k1/memory_writer/extraction/writer_agent.py
k1/memory_writer/extraction/extraction_validator.py
k1/memory_writer/extraction/prompts/memory_writer_persona.md

# Phase 3: Envelope + Batch
k1/memory_writer/envelope/__init__.py
k1/memory_writer/envelope/envelope_builder.py
k1/memory_writer/envelope/field_mapper.py
k1/memory_writer/envelope/privacy_enforcer.py
k1/memory_writer/batch/__init__.py
k1/memory_writer/batch/delta_aggregator.py
k1/memory_writer/batch/batch_emitter.py

# Phase 4: Pipeline + Service
k1/memory_writer/pipeline/__init__.py
k1/memory_writer/pipeline/pipeline.py
k1/memory_writer/pipeline/turn_dispatcher.py
k1/memory_writer/factory.py
k1/memory_writer/service.py

# Phase 5: Adapters + Health + Fabric
k1/memory_writer/adapters/bridge_command_adapter.py
k1/memory_writer/adapters/event_subscription_adapter.py
k1/memory_writer/adapters/health_adapter.py
k1/memory_writer/adapters/test_adapters.py
k1/memory_writer/health/__init__.py
k1/memory_writer/health/circuit_breaker.py
k1/memory_writer/fabric_registration.py
```

---

*This plan is derived from the deep dive of all MW source files (16), architecture docs (5), contracts (2), tests (7 files, 208 passing), and the mermaid diagram. Implementation order follows the 6-phase pipeline: prerequisite (tool call data) → foundation → filter/context → extraction → envelope/batch → pipeline/service → integration.*
