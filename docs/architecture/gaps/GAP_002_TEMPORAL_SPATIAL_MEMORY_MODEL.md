# GAP-002: Temporal & Spatial Memory Model -- Binding Not Flattening

**Status**: Identified
**Severity**: Critical (Architectural)
**Impact**: Episode formation accuracy, temporal retrieval, spatial coherence, memory graph integrity
**Systems Affected**: K1 Memory Writer, Bridge, K0 P02 M08, K0 P03 R0/R2, future K1 retrieval
**Related**: GAP-001 (Cross-Layer Vector Linking), Epic 1.2 (Timestamp Chain Fix)
**Date**: 2026-03-05

---

## 1. Problem Statement

The current architecture flattens human memory's multi-dimensional temporal and spatial
structure into single-value columns. This destroys the associative link structure that
makes episodic memory useful for retrieval, narrative continuity, and life pattern recognition.

**Core insight**: Human memories are not timestamps and locations. They are **webs of
temporal and spatial links** that can be traversed from any entry point. The current
system stores flat values where it needs to store **bindings**.

---

## 2. The Temporal Collapse Problem

### 2.1 Three Temporal Dimensions per Memory Atom

Every memory atom carries three distinct temporal dimensions. The current system conflates
dimension 1 and 2 into a single `event_time_utc` column.

```
DIMENSION 1                    DIMENSION 2                    DIMENSION 3
Conversation Anchor            Referred Time(s)               Temporal Link Direction
─────────────────              ──────────────                 ──────────────────────
WHEN did user say this?        WHAT time does it REFER TO?    Past <-> Present <-> Future

K1 hardcoded: now_utc()        K1 LLM resolved:               orientation + link_type
System clock truth             "yesterday evening" -> epoch
Cannot be LLM-determined       Only LLM can determine         Binds dimension 1 to 2
```

**Example -- single conversation at 10:00am Tuesday:**

| User says | Dim 1: Anchor | Dim 2: Refers to | Dim 3: Direction |
|-----------|---------------|------------------|------------------|
| "Had dinner with Mom yesterday evening" | Tue 10:00am | Mon 7:00pm | RETROSPECTIVE |
| "I feel happy about it" | Tue 10:00am | Tue 10:00am (present) | CONCURRENT |
| "Remind me next Friday to call her" | Tue 10:00am | Fri (future) | PROSPECTIVE |
| "We used to go there every Sunday" | Tue 10:00am | recurring Sundays | HABITUAL |

All four atoms are from the **same conversation** (same episode). But their referred
times span from last Monday to next Friday to every Sunday. Using referred time for
episode grouping would scatter them across the timeline. Using conversation anchor
keeps them together.

### 2.2 Current System: What Breaks

**K0 M08 `normalize_timestamp()`** implements a 5-level fallback chain:

```
Priority 1: body.temporal.resolved_epoch_ms  -> "mw_resolved"   (K1 LLM)
Priority 2: M02 NER temporal + regex         -> "ner_temporal"   (K0 heuristic)
Priority 3: body.event_time (MW now_utc())   -> "event_time"     (conversation time)
Priority 4: envelope.ts (Bridge build time)  -> "envelope_ts"    (metadata)
Priority 5: now() (P02 processing time)      -> "now"            (last resort)
```

**The problem**: When Priority 1 fires (LLM resolved a temporal expression), M08
writes the **referred time** into `st_hipp_events.event_time_utc`, overwriting the
**conversation time**. The conversation anchor is lost.

```
User says "Had dinner yesterday evening" at Tue 10:00am
  -> K1 LLM resolves: resolved_epoch_ms = Mon 7:00pm
  -> M08 Priority 1 fires: event_time_utc = Mon 7:00pm    <-- WRONG for episodes
  -> R0 loads: P03EventState.timestamp = Mon 7:00pm
  -> R2 EpisodeSplitter: This event appears to be from YESTERDAY
  -> Episode grouping: Separated from other Tue 10:00am conversation events
```

**Separately**, the resolved epoch is ALSO stored in `temporal_resolved_epoch_ms`.
So the data is not lost -- but `event_time_utc` (the column R2 trusts) has been
overwritten with the wrong semantic meaning.

### 2.3 What Should Happen

`event_time_utc` must ALWAYS be the conversation anchor (dimension 1).
`temporal_resolved_epoch_ms` carries the referred time (dimension 2).
`temporal_orientation` carries the link direction (dimension 3).

M08 Priority 1 should write to `temporal_resolved_epoch_ms` ONLY, never to `event_time_utc`.
The conversation anchor (`body.event_time` from MW `now_utc()`) should flow straight
through to `event_time_utc` regardless of whether the LLM resolved a temporal expression.

### 2.4 What the System is Missing Beyond the Fix

Even after fixing the collapse, the temporal model has structural gaps:

| Gap | Current State | What Human Memory Does |
|-----|--------------|----------------------|
| **Single temporal reference** | 1 `resolved_epoch_ms` per atom | Multiple: "Yesterday we planned next Friday and Mom mentioned Christmas" = 3 references |
| **No temporal link TYPE** | `orientation` = PAST/PRESENT/FUTURE | Need: RETROSPECTIVE, PROSPECTIVE, HABITUAL, CONTEXTUAL, CONDITIONAL |
| **No precision/uncertainty** | Single epoch point | "yesterday evening" = 6-hour window, "at 7:15pm" = 1-minute window, "last summer" = 3-month window |
| **No intra-conversation order** | All atoms in 250ms batch get same timestamp | "First we ate, then walked to the park, then drove home" = ordered sequence |
| **No temporal chains** | Atoms are independent | Event A (planning) -> Event B (execution) -> Event C (reflection) = goal-directed chain |

### 2.5 Proposed Temporal Link Model

```python
@dataclass
class TemporalLink:
    """One temporal reference from a memory atom.

    A single atom may carry multiple temporal links. Example:
    "Yesterday we planned next Friday's party and Mom reminded me about Christmas"
    -> 3 TemporalLinks: yesterday (RETROSPECTIVE), next Friday (PROSPECTIVE),
       Christmas (PROSPECTIVE).
    """
    mentioned_time: str              # Raw text: "yesterday evening"
    resolved_epoch_ms: int           # Best-guess absolute time
    uncertainty_window_ms: int       # Precision: "7:15pm" = 60_000, "last summer" = 7_776_000_000
    orientation: str                 # PAST / PRESENT / FUTURE / RECURRING / CONDITIONAL
    link_type: str                   # RETROSPECTIVE / PROSPECTIVE / HABITUAL / CONTEXTUAL
    confidence: float                # LLM resolution confidence [0, 1]
```

**On MemoryAtom:**

```python
# Current (broken -- single value, overwritten by M08):
temporal: Optional[Temporal] = None   # {mentioned_time, resolved_epoch_ms, is_backdated}

# Proposed (multi-link, conversation anchor preserved):
conversation_anchor_ms: int                   # ALWAYS = now_utc(), NEVER overwritten
temporal_links: List[TemporalLink] = []       # Zero or more temporal references
```

**Storage**: `temporal_links` serializes to a JSONB column in st_hipp_events. The
conversation anchor remains in `event_time_utc` (BIGINT, NOT NULL).

---

## 3. The Spatial Flattening Problem

### 3.1 Current Spatial Model -- Flat Columns

```
geohash_6: str       -- Physical coordinate (~1.2km precision)
location_name: str   -- "Olive Garden"
location_type: str   -- "restaurant"
```

Each atom gets one location. No hierarchy, no transitions, no identity persistence.

### 3.2 How Human Spatial Memory Actually Works

Human spatial memory is layered, not flat:

```
PHYSICAL ────── coordinates (WHERE exactly: lat/lon, geohash)
    |
SEMANTIC ────── place type (WHAT kind of place: restaurant, home, park)
    |
FUNCTIONAL ──── activity affordance (WHAT you DO there: eat, sleep, work)
    |
SOCIAL ──────── who is associated (WHO you see there: family, coworkers)
    |
EMOTIONAL ───── how it feels (HOW you feel there: safe, anxious, happy)
    |
TRANSITIONAL ── movement between places (HOW you GOT there: drove, walked)
```

### 3.3 What the System is Missing

| Gap | Current State | What Human Memory Does |
|-----|--------------|----------------------|
| **No spatial links** | Each atom has ONE location | "Drove from home to restaurant" = transition link with from/to |
| **No place identity** | `geohash_6` only | "Home" persists as a concept even if you move houses. Need stable `place_id` |
| **No spatial hierarchy** | Flat | "Kitchen at home in Seattle" = room < building < neighborhood < city |
| **No spatial-temporal binding** | Separate columns, no binding | "We always go to Olive Garden on Fridays" = place + recurring time |
| **No spatial familiarity** | No visit tracking | First visit vs regular spot affects memory encoding strength |
| **No spatial transition** | Point only, no movement | "After dinner we walked to the park" = trajectory |

### 3.4 Proposed Spatial Context Model

```python
@dataclass
class SpatialContext:
    """Spatial context for a memory atom.

    Models place identity (stable across visits), physical coordinates,
    semantic type, and transitions between places.
    """
    place_id: Optional[str] = None          # Stable identity: "home", "olive_garden_main_st"
    geohash_6: Optional[str] = None         # Physical coordinate
    location_name: Optional[str] = None     # Human-readable name
    location_type: Optional[str] = None     # Semantic type: restaurant, home, park
    location_function: Optional[str] = None # Activity affordance: eat, sleep, work, play
    transition_from: Optional[str] = None   # Previous place_id (movement link)
    familiarity: str = "unknown"            # FIRST_VISIT / OCCASIONAL / REGULAR / DAILY
```

**Storage**: Core fields remain as columns (geohash_6, location_name, location_type).
Extended fields (place_id, transition_from, familiarity) either become new columns or
serialize into a JSONB spatial_context column.

---

## 4. Cross-Dimensional Bindings

The temporal and spatial models above are per-atom. The real power of human episodic
memory comes from **cross-links between atoms**:

### 4.1 Causal Links

"Because it rained, we cancelled the picnic and went to the movies instead."

```
Event A (rain)  --caused-->  Event B (cancel picnic)  --led to-->  Event C (movies)
```

Current system: zero causal tracking. Every atom is independent. No way to answer
"Why did we go to the movies?" without re-reading the full conversation.

### 4.2 Narrative Goal Arcs

```
NARRATIVE THREAD: "Planning Mom's birthday party"
    |-- Episode 1: "Initial idea"           (Mon conversation)
    |-- Episode 2: "Venue search"           (Wed conversation)
    |-- Episode 3: "Guest list discussion"  (Thu conversation)
    |-- Episode 4: "The actual party"       (Sat lived experience)
```

Current system: `narrative_thread_id` exists but R2 groups by 30-minute conversation
proximity. Episodes 1 and 4 are a week apart -- they will never be in the same R2
episode. There is no cross-episode narrative linking.

### 4.3 Emotional Anchoring as Retrieval Pathway

Emotions are not metadata on memories -- they are a **primary retrieval pathway**.
Humans remember "that really happy day" or "when I was furious" before they remember
dates or locations.

Current system: `affect_valence`, `affect_arousal`, `affect_dominance` exist as flat
floats. There is no "emotional episode" concept (a sequence of events bound by shared
emotional state), and no emotional retrieval pathway in P01 recall.

### 4.4 Rehearsal and Reconsolidation

Every time the user retells a memory, two things happen:

1. A NEW atom is created (the retelling)
2. The ORIGINAL memory is strengthened and potentially modified

"Remember that dinner with Mom?" creates a new atom that **references** the original
dinner atom. The original gets `access_count++` but also reconsolidation (the retelling
may add or change details).

Current system: `access_count` and `decay_score` exist on P03EventState, but there is
no "this atom is a retelling of that atom" link. Rehearsal and reconsolidation are
invisible.

---

## 5. The Full Binding Model

```
                         TEMPORAL WEB
                    past <-- anchor --> future
                    (multiple links per atom)
                              |
                              |
SPATIAL CONTEXT ──────── MEMORY ATOM ──────── SOCIAL GRAPH
place hierarchy              |                who + relationship
transition links             |                intimacy level
familiarity                  |
                              |
                    ┌─────────┼─────────┐
                    |         |         |
              EMOTIONAL    CAUSAL    NARRATIVE
              anchoring    chains    threads
              retrieval    A->B->C   goal arcs
              pathway
```

**What the system currently captures:**

| Dimension | Status | Quality |
|-----------|--------|---------|
| Temporal anchor (conversation time) | Exists but gets overwritten by M08 Priority 1 | Broken |
| Temporal resolution (referred time) | Exists as single value | Partial |
| Temporal links (multiple references) | Missing | Gap |
| Temporal precision/uncertainty | Missing | Gap |
| Spatial coordinates | Exists (geohash_6) | OK |
| Spatial identity (place_id) | Missing | Gap |
| Spatial hierarchy | Missing | Gap |
| Spatial transitions | Missing | Gap |
| Social graph (participants) | Exists | OK |
| Social intimacy | Exists | OK |
| Emotional state | Exists as flat floats | Partial |
| Emotional anchoring (retrieval) | Missing | Gap |
| Narrative thread | Exists (thread_id) | Partial |
| Narrative goal arc (cross-episode) | Missing | Gap |
| Causal chains | Missing | Gap |
| Rehearsal/reconsolidation links | Missing | Gap |

---

## 6. Prioritized Fix Roadmap

### Phase 1: Stop the Bleeding (Epic 1.2 -- IN PROGRESS)

**Goal**: Prevent M08 from overwriting conversation time with resolved time.

- Issue 1.2.2: Harden R0 fallback chain (DONE)
- Issue 1.2.3: Add `temporal_source` provenance to P03EventState (DONE)
- Issue 1.2.4: Timestamp quality observability in R2 (DONE)
- **Future**: M08 Priority 1 should write to `temporal_resolved_epoch_ms` ONLY,
  never overwrite `event_time_utc`. This requires an M08 refactor (not in current scope).

### Phase 2: Preserve Conversation Anchor (New Work)

**Goal**: `event_time_utc` is ALWAYS conversation time, never overwritten.

- M08 `normalize_timestamp()` Priority 1 and 2 write to `temporal_resolved_epoch_ms` only
- `event_time_utc` always comes from Priority 3+ (body.event_time / envelope.ts / now)
- Requires M08 refactor + M13 builder update + migration for existing data

### Phase 3: Multi-Link Temporal Model (New Work)

**Goal**: Support multiple temporal references per atom.

- Add `temporal_links_json JSONB` column to st_hipp_events
- K1 MemoryAtom schema: `temporal_links: List[TemporalLink]`
- K1 WriterAgent extraction: produce multiple temporal references per atom
- M08: parse and store temporal links array
- R0: load into P03EventState

### Phase 4: Spatial Identity and Transitions (New Work)

**Goal**: Stable place identity that persists across visits.

- Place resolver in K1 or K0: maps location_name -> stable place_id
- `place_id` column in st_hipp_events
- Familiarity tracking: visit count per place_id per user
- Spatial transition detection: consecutive atoms at different places

### Phase 5: Cross-Episode Narrative Linking (New Work)

**Goal**: Connect episodes that belong to the same goal arc.

- Narrative thread persistence in st_epi (episode-level thread tracking)
- Cross-episode thread matching: "Planning Mom's birthday" spans Mon-Sat
- Goal completion detection: thread reaches CLIMAX/END arc position

### Phase 6: Causal Chains and Rehearsal (Future)

**Goal**: Track why events happened and how memories are retold.

- Causal link type on MemoryAtom: `caused_by: Optional[str]` (event_id reference)
- Rehearsal detection: atom text references previous memory
- Reconsolidation tracking: link retelling atom to original atom

---

## 7. Relationship to Existing Architecture

### 7.1 K1 Memory Writer

MW currently sets two temporal values per atom:

- `body.event_time_utc = now_utc()` (conversation time proxy)
- `body.temporal = {mentioned_time, resolved_epoch_ms, is_backdated}` (referred time)

MW intentionally separated these (architecture doc L2148, open question #6 RESOLVED).
The separation is correct. The problem is M08 re-merging them.

### 7.2 Bridge

Bridge adds `envelope.ts` (build time) and handles offline queuing. Bridge is not
responsible for temporal or spatial semantics -- it is a transport layer.

### 7.3 K0 P02 M08 (Temporal Profiler)

M08 owns the `normalize_timestamp()` fallback chain. The fix must happen here:
Priority 1 and 2 should populate `temporal_resolved_epoch_ms`, not `event_time_utc`.

### 7.4 K0 P03 R0 (Batch Selector)

R0 reads `event_time_utc` from st_hipp_events and sets `P03EventState.timestamp`.
Epic 1.2 hardened this chain (explicit None/0 checks, WARNING logging on fallback).

### 7.5 K0 P03 R2 (Episodic Integrator)

R2 uses `P03EventState.timestamp` for all temporal decisions. R2 trusts that this
value represents conversation time. If M08 has overwritten it with referred time,
R2 episode boundaries are wrong.

---

## 8. Decision Required

The M08 Priority 1 overwrite is the most impactful fix. It requires a decision:

**Option A: M08 refactor (clean, requires migration)**

- M08 `normalize_timestamp()` never writes Priority 1/2 results to `event_time_utc`
- `event_time_utc` always = Priority 3+ (conversation time)
- `temporal_resolved_epoch_ms` = Priority 1/2 result when available
- Requires: backfill migration for existing rows where event_time_utc was overwritten

**Option B: R0 compensation (pragmatic, no migration)**

- R0 detects when `event_time_utc` was overwritten: if `temporal_source == "mw_resolved"`
  AND `temporal_resolved_epoch_ms > 0` AND `event_time_utc ~= resolved_epoch_ms`,
  then fall back to a secondary conversation-time source
- Problem: no reliable secondary source exists after M08 has overwritten it

**Option C: K1 propagation (gold standard, largest change)**

- K1 propagates `turn.complete.v1.timestamp_ms` all the way through to a new
  `conversation_timestamp_ms` field on MemoryAtom
- M08 writes this to a new `conversation_time_utc` column in st_hipp_events
- R0 uses `conversation_time_utc` (never null, K1 system clock)
- `event_time_utc` becomes "best available event time" (M08 resolved, for retrieval)
- Cleanest separation but largest schema change

**Recommendation**: Option A for immediate fix, Option C as target architecture.

---

## 9. References

- Epic 1.2: Timestamp Chain Fix (R2_EPISODIC_INTEGRATION_EPIC_PLAN.md L694-1350)
- Discovery Section 16: Timestamp Chain Analysis (P03_R2_EPISODIC_INTEGRATION_DISCOVERY.md)
- K1 MW Architecture: memory_writer_architecture.md L587 (event_time mapping), L2148 (open question #6)
- K1 MW Types: types.py L259-269 (Temporal dataclass), L319 (MemoryAtom.temporal)
- K1 SessionState: beliefs_active.py L640-672 (set_mentioned_time)
- K0 M08: temporal_profile.py L480-580 (normalize_timestamp 5-level chain)
- K0 M13: hipp_events_row.py L310-320 (event_time_utc storage)
- K0 R0: r0_batch_selector.py L666-710 (timestamp loading, Epic 1.2 hardening)
- Tulving, E. (1972). Episodic and semantic memory. Organization of Memory.
- Zacks & Swallow (2007). Event segmentation. Current Directions in Psychological Science.

---

# PART II: Memory Writer Alignment Exploration

**Exploration Date**: 2026-03-05
**Scope**: K1 Memory Writer architecture deep-dive -- what exists, what is missing,
and what specific changes are required to align MW with the temporal/spatial binding model.

---

## 10. MW Exploration Summary

### 10.1 What Was Read

| Artifact | Location | Lines | Content |
|----------|----------|-------|---------|
| MW Architecture Doc | `k1/memory_writer/memory_writer_architecture.md` | 2195 | Complete 32-section design: 5-stage pipeline, 34-field schema, all invariants |
| MW Types | `k1/memory_writer/types.py` | 490 | 12 enums, 11 frozen dataclasses (MemoryAtom, Temporal, ExtractionContext) |
| MW Events | `k1/memory_writer/events.py` | 148 | 6 topic constants, 6 frozen payload dataclasses |
| MW Config | `k1/memory_writer/config.py` | 97 | MWConfig frozen dataclass, 13 SessionState sections |
| MW Invariants | `k1/memory_writer/invariants.py` | 366 | MW-01 through MW-11 machine-checkable assertions |
| MW Ports | `k1/memory_writer/ports/` | 5 files | IBridgeCommandPort, ISessionReadPort, IModelHubPort, IEventSubscriptionPort, IHealthPort |
| MemoryAtom v2 Schema | `k1/contracts/schemas/memory_writer/memory_atom.v2.schema.json` | 420 | JSON Schema with 34 fields, 4 $defs (Affect, ParticipantRelationship, Narrative, Temporal) |
| SessionState beliefs_active | `k1/sessionstate/sections/beliefs_active.py` | 1066 | MentionedTime, MentionedLocation dataclasses, set/get/clear methods |

### 10.2 What MW Architecture IS (Current State)

MW is a 5-stage linear pipeline triggered by `turn.complete.v1`:

```
Stage 1: Relevance Filter (rule-based, 5 skip rules, <2ms)
Stage 2: Context Assembly (reads 13/15 SessionState sections, <1ms)
Stage 3: LLM Extraction (GPT-4o-mini, 2000 tokens, 200-500ms)
Stage 4: Envelope Builder (deterministic field mapping, <2ms)
Stage 5: Batch Aggregation + Bridge Submit (250ms window, fire-and-forget)
```

MW produces 0-6 `MemoryAtom` objects per turn. Each atom has 34 fields organized as
12 cognitive dimensions. The atom is wrapped in an `MWEnvelope` and submitted to K0
via the Bridge Command Port.

### 10.3 Current Temporal Data Flow (K1 to K0)

```
K1 Concierge
  |  User speaks at TIME_A
  |  LLM processes, Concierge delivers response
  |  Concierge writes beliefs_active.set_mentioned_time(raw_text, resolved_ms)
  |  Concierge emits turn.complete.v1 { timestamp_ms: TIME_A }
  |
  v
K1 MW Stage 2 (Context Assembly)
  |  Reads SessionState snapshot
  |  Gets MentionedTime { raw_text, resolved_ms, confidence, is_relative } -- IF SET
  |  ** WARNING: beliefs_active.start_new_turn() clears mentioned_time **
  |  ** Race condition: if Concierge clears before MW reads, temporal is None **
  |
  v
K1 MW Stage 3 (LLM Extraction)
  |  LLM sees ExtractionContext (includes beliefs_active data)
  |  LLM produces MemoryAtom.temporal = Temporal(mentioned_time, resolved_epoch_ms, is_backdated)
  |  LLM produces MemoryAtom.temporal_orientation = PAST | ONGOING | FUTURE_COMMITMENT
  |  ** Only ONE Temporal object per atom **
  |  ** LLM has no instruction to extract MULTIPLE temporal references **
  |
  v
K1 MW Stage 4 (Envelope Builder)
  |  body.event_time_utc = now_utc()          <-- conversation time PROXY (not exact turn time)
  |  body.temporal = { mentioned_time, resolved_epoch_ms, is_backdated }
  |  body.temporal_orientation = PAST | ONGOING | FUTURE_COMMITMENT
  |  body.location_name = "Olive Garden"
  |  body.location_type = "restaurant"
  |  ** event_time_utc is now_utc() at ENVELOPE BUILD TIME, not turn.complete.v1.timestamp_ms **
  |  ** Drift: typically 200-815ms, worst case 2-3 seconds **
  |
  v
Bridge
  |  Adds envelope.ts (bridge build time), signs, POSTs to K0
  |
  v
K0 P02 M08 (Temporal Profiler)
  |  normalize_timestamp() 5-level fallback:
  |  Priority 1: body.temporal.resolved_epoch_ms -> OVERWRITES event_time_utc  <-- BUG
  |  Priority 2: NER temporal + regex -> OVERWRITES event_time_utc
  |  Priority 3: body.event_time (MW now_utc()) -> correct
  |  ** When Priority 1 fires: conversation anchor is DESTROYED **
  |
  v
K0 M13 (Builder)
  |  Writes to st_hipp_events:
  |    event_time_utc = M08 output (potentially overwritten referred time)
  |    temporal_resolved_epoch_ms = body.temporal.resolved_epoch_ms (separate column, preserved)
  |
  v
K0 P03 R0 (Batch Selector)
  |  Reads event_time_utc -> P03EventState.timestamp
  |  ** Trusts this is conversation time. If overwritten, episodes break. **
```

### 10.4 Current Spatial Data Flow (K1 to K0)

```
K1 Concierge
  |  Writes beliefs_active.set_mentioned_location(raw_text, location_type, entity_id, confidence)
  |  ** Also cleared by start_new_turn() -- same race condition as temporal **
  |
  v
K1 MW Stage 3 (LLM Extraction)
  |  LLM extracts:
  |    location_name: Optional[str]    -- "Olive Garden"
  |    location_type: Optional[enum]   -- 12 values (home, restaurant, hospital, ...)
  |  ** No place_id, no hierarchy, no transitions, no familiarity **
  |
  v
K1 MW Stage 4 (Envelope Builder)
  |  Direct copy to body (Privacy Enforcer strips in AMBER/RED)
  |
  v
K0 P02 M02 (Semantic Projection)
  |  NER extracts LOC entities from text
  |  May add/confirm location information
  |
  v
K0 M13 (Builder)
  |  Writes to st_hipp_events:
  |    location_name, location_type, geohash_6
  |  ** Three flat columns, no linking, no identity persistence **
```

---

## 11. Gap Inventory: What K1 MW Must Change

### 11.1 TEMPORAL GAPS (8 items)

#### T1: MemoryAtom.temporal is OPTIONAL and SINGLE-VALUE

**Current** (types.py L319):

```python
temporal: Optional[Temporal] = None   # {mentioned_time, resolved_epoch_ms, is_backdated}
```

**Problem**: Only supports ONE temporal reference per atom.
"Yesterday we planned next Friday's party and Mom mentioned Christmas" has 3 temporal
references but MW can only capture 1.

**Required Change**:

```python
# Replace Optional[Temporal] with multi-link:
conversation_anchor_ms: int = 0                          # ALWAYS from turn.complete.v1.timestamp_ms
temporal_links: List[TemporalLink] = field(default_factory=list)  # 0-N temporal references
```

**Files**: `types.py`, `memory_atom.v2.schema.json`
**Severity**: Critical

---

#### T2: Temporal dataclass lacks precision/uncertainty

**Current** (types.py L259):

```python
@dataclass(frozen=True)
class Temporal:
    mentioned_time: str           # "yesterday evening"
    resolved_epoch_ms: int        # single epoch point
    is_backdated: bool
```

**Problem**: "yesterday evening" is a ~4-hour window, "at 7:15pm" is a ~1-minute window,
"last summer" is a ~3-month window. A single `resolved_epoch_ms` point misrepresents all
of these. Downstream clustering (R2 HDBSCAN) treats them as equal-precision points.

**Required Change**: Add `uncertainty_window_ms: int` to the new TemporalLink model.

```python
@dataclass(frozen=True)
class TemporalLink:
    mentioned_time: str
    resolved_epoch_ms: int
    uncertainty_window_ms: int    # NEW: precision window
    link_type: str                # NEW: RETROSPECTIVE, PROSPECTIVE, HABITUAL, ...
    confidence: float             # NEW: resolution confidence
```

**Files**: `types.py`, `memory_atom.v2.schema.json`
**Severity**: Medium (improves quality, not blocking)

---

#### T3: Temporal dataclass lacks link type

**Current**: `is_backdated: bool` (binary flag).

**Problem**: Need to distinguish RETROSPECTIVE ("yesterday"), PROSPECTIVE ("next Friday"),
HABITUAL ("every Sunday"), CONTEXTUAL ("during college"), CONDITIONAL ("if it rains").
A boolean cannot express this.

**Required Change**: Replace `is_backdated` with `link_type: TemporalLinkType` enum.

```python
class TemporalLinkType(str, Enum):
    RETROSPECTIVE = "RETROSPECTIVE"      # Past reference
    PROSPECTIVE = "PROSPECTIVE"          # Future reference
    CONCURRENT = "CONCURRENT"            # Happening now
    HABITUAL = "HABITUAL"                # Recurring pattern
    CONTEXTUAL = "CONTEXTUAL"            # Life period ("in college")
    CONDITIONAL = "CONDITIONAL"          # Contingent ("if it rains")
```

**Files**: `types.py`, `memory_atom.v2.schema.json`
**Severity**: Critical (directly needed for proper temporal classification)

---

#### T4: TemporalOrientation enum is too coarse

**Current** (types.py L82):

```python
class TemporalOrientation(str, Enum):
    PAST = "PAST"
    ONGOING = "ONGOING"
    FUTURE_COMMITMENT = "FUTURE_COMMITMENT"
```

**Problem**: Missing HABITUAL (recurring events), CONDITIONAL ("if..."), EPOCHAL
("back when I was in college"). 3 values cannot classify the temporal richness of
human conversation.

**Decision Required**: If we move to TemporalLinkType (T3), TemporalOrientation
may become redundant -- or it could remain as an ATOM-LEVEL orientation while
link_type is PER-LINK. The atom-level orientation would be the DOMINANT temporal
direction of the atom as a whole.

**Files**: `types.py`, `memory_atom.v2.schema.json`
**Severity**: Low (subsumed by T3 if TemporalLinkType is adopted)

---

#### T5: ExtractionContext does NOT carry turn timestamp

**Current** (types.py L382-410): `ExtractionContext` has `session_id` and `conversation_turn`
but NO `turn_timestamp_ms` field.

**Problem**: The LLM has no explicit conversation timestamp to anchor against. The Envelope
Builder uses `now_utc()` instead of `turn.complete.v1.timestamp_ms`. This creates drift
(typically 200-815ms, up to 2-3 seconds under load).

**Required Change**:

```python
@dataclass(frozen=True)
class ExtractionContext:
    # ...existing fields...
    turn_timestamp_ms: int = 0    # NEW: from TurnCompletePayload.timestamp_ms
```

And in Envelope Builder: `body.event_time_utc = turn_timestamp_ms` instead of `now_utc()`.

**Files**: `types.py`, envelope builder design, `events.py` (TurnCompletePayload already has timestamp_ms)
**Severity**: Medium (correctness improvement)

---

#### T6: Envelope Builder uses now_utc() instead of turn timestamp

**Current** (architecture doc L587):

```
now_utc() -> body.event_time_utc
```

**Problem**: `now_utc()` at envelope build time is NOT the conversation time. It is
the time MW finished processing (200-815ms after the turn). For episodic grouping,
this creates microsecond-level jitter between atoms from the same turn.

**Required Change**: Propagate `TurnCompletePayload.timestamp_ms` through the pipeline
and use it as `body.event_time_utc`.

```
turn.complete.v1.timestamp_ms -> ExtractionContext.turn_timestamp_ms
  -> EnvelopeBuilder: body.event_time_utc = turn_timestamp_ms
```

**Files**: Pipeline, context builder, envelope builder
**Severity**: Medium (Option C from GAP-002 Section 8)

---

#### T7: Race condition -- beliefs_active clears temporal on start_new_turn()

**Current** (beliefs_active.py L742-743):

```python
def start_new_turn(self, ...):
    self._mentioned_time = None
    self._mentioned_location = None
```

**Problem**: MW is a BACKGROUND process (Stage 2 reads happen after turn.complete.v1).
If Concierge calls `start_new_turn()` for the NEXT turn before MW Stage 2 reads the
snapshot for the CURRENT turn, MW will see `mentioned_time = None`.

**Impact Assessment**: This is mitigated by two factors:

1. SessionState uses snapshot isolation (MW gets a consistent point-in-time read)
2. turn.complete.v1 is emitted BEFORE Concierge moves to the next turn

However, if the user types quickly and the next turn starts before MW completes its
200-815ms pipeline, the race is real.

**Required Change**: Two options:

- **Option A**: Include MentionedTime and MentionedLocation directly in
  `TurnCompletePayload` (guarantees MW has the data regardless of SessionState state)
- **Option B**: MW reads snapshot within 1ms of receiving turn.complete.v1 (Stage 2
  runs immediately, before start_new_turn can fire for next turn). This is the current
  design intent but is not formally guaranteed.

**Recommendation**: Option A (include temporal/spatial in turn payload). It is cheap
(<100 bytes), eliminates the race entirely, and aligns with Option C from GAP-002.

**Files**: `events.py` (TurnCompletePayload), Concierge turn emission, MW Stage 2
**Severity**: High (data loss under fast typing)

---

#### T8: No intra-turn extraction ordering

**Current**: All atoms from a single turn share the same `conversation_turn: int` and
are batched in the 250ms window with no ordering.

**Problem**: "First we ate dinner, then walked to the park, then drove home" produces
3 atoms. Their chronological order within the turn is lost.

**Required Change**: Add `extraction_sequence: int` to MemoryAtom (0-indexed ordinal
within a turn's extractions).

```python
extraction_sequence: int = 0    # NEW: ordinal within turn (0 = first extraction)
```

**BOUNDARY NOTE**: This is a per-atom signal, NOT consolidation. Only MW knows the
extraction order within a turn (P03 cannot infer this from timestamps alone since all
atoms in a turn share the same conversation_anchor_ms). MW records the ordinal as a
fact about the atom. P03 may optionally use this signal for intra-episode ordering
during narrative chain construction, but the ordering decision remains P03's.

**Files**: `types.py`, `memory_atom.v2.schema.json`, extraction validator
**Severity**: Low (useful for narrative chains, not blocking)

---

### 11.2 SPATIAL GAPS (5 items)

#### S1: No stable place identity (place_id)

**Current**: `location_name: Optional[str]` and `location_type: Optional[LocationType]`.

**Problem**: "Olive Garden" visited 20 times creates 20 independent strings.
"Olive Garden on Main St" vs "Olive Garden" vs "that Italian place" all refer to the
same physical location but are stored as unlinked strings.

**Required Change**: Add a PlaceResolver (analogous to PersonResolver):

```python
class PlaceResolver:
    """Resolve location names to stable place_ids.
    Source: SessionState beliefs_active.entities (type=LOCATION)."""

    def resolve(self, name: str, context: ExtractionContext) -> str:
        # "Olive Garden" -> "place_olive_garden_main_st"
        # "that Italian place" -> "place_olive_garden_main_st" (via alias)
        ...
```

And on MemoryAtom:

```python
place_id: Optional[str] = None    # NEW: stable place identity
```

**Files**: `types.py`, new `context/place_resolver.py`, `memory_atom.v2.schema.json`
**Severity**: Medium (important for spatial coherence, not immediately blocking)

---

#### S2: No spatial hierarchy

**Current**: One location_name, one location_type per atom. Flat.

**Problem**: "Kitchen at home" has room (kitchen) < building (home) < neighborhood < city.
Current model cannot represent nesting. "In Seattle" and "at home" cannot be linked
hierarchically.

**Required Change**: Add `location_hierarchy: List[str]` or structured context:

```python
location_hierarchy: List[str] = field(default_factory=list)
# Example: ["kitchen", "home", "Capitol Hill", "Seattle"]
```

**BOUNDARY NOTE**: This is a per-atom signal extracted from the conversation text by
MW's LLM. The hierarchy describes THIS atom's spatial context ("kitchen at home in
Seattle"), not a cross-atom inference. K0 does NOT have access to the original
conversation text and cannot extract this hierarchy. MW provides the raw hierarchy
signal; K0 P02/P03 may enrich or normalize it (e.g., resolving to canonical place_ids
at each level), but the initial extraction is MW's job.

**Files**: `types.py`, `memory_atom.v2.schema.json`
**Severity**: Low (enrichment, not blocking core flow)

---

#### S3: No spatial transitions

**Current**: Point-only model -- each atom has one location.

**Problem**: "After dinner we drove to the movies" has from=restaurant, to=cinema,
mode=drove. Current model captures only one of these locations.

**Required Change**: Add transition fields to spatial context:

```python
@dataclass(frozen=True)
class SpatialContext:
    place_id: Optional[str] = None
    location_name: Optional[str] = None
    location_type: Optional[str] = None
    transition_from: Optional[str] = None     # NEW: origin place name/id
    transition_mode: Optional[str] = None     # NEW: drove, walked, flew, ...
```

**BOUNDARY NOTE**: `transition_from` references a PLACE (name or place_id), not another
atom. "After dinner we drove to the movies" = this atom's location is "movies",
transition_from is "restaurant", transition_mode is "drove". This is per-atom spatial
context extracted from the conversation text — the LLM is describing WHERE this memory
happened and HOW the user got there. P03 builds spatial NARRATIVES across atoms;
MW provides the per-atom spatial signals that P03 consumes.

**Files**: `types.py`, `memory_atom.v2.schema.json`
**Severity**: Low (future enrichment)

---

#### S4: No spatial familiarity tracking

**Current**: No visit counting or familiarity metric.

**Problem**: "Our usual Friday spot" vs "we tried a new restaurant" encode differently
in human memory. First visits are more memorable (novelty). Regular spots form place
identity. The system has no way to distinguish these.

**Required Change**: Two approaches:

- **K1 approach**: Add `familiarity: str` enum to SpatialContext (FIRST_VISIT, OCCASIONAL, REGULAR, DAILY)
- **K0 approach**: K0 P02 computes familiarity from historical visit count per place_id

**Recommendation**: K0 approach (requires place_id first, computed from st_hipp_events
history). MW does not need to track this -- K0 has the long-term data.

**Files**: K0 P02 module (not MW)
**Severity**: Low (K0 enrichment concern)

---

#### S5: MentionedLocation lacks functional dimension

**Current** (beliefs_active.py L194-208):

```python
@dataclass
class MentionedLocation:
    raw_text: str
    location_type: str = ""       # Physical type: "room", "address", "zone"
    entity_id: str = ""
    confidence: float = 1.0
```

**Problem**: `location_type` captures physical classification but not WHAT YOU DO THERE.
"Restaurant" implies eating, "gym" implies exercise. This is partially covered by
`activity_type` on MemoryAtom but the spatial-to-activity link is implicit, not explicit.

**Required Change**: Either:

- Link `activity_type` and `location_type` in the LLM prompt (instruct the LLM to
  produce consistent pairs)
- Add `location_function: Optional[str]` to MentionedLocation

**Recommendation**: LLM prompt approach (simpler, no schema change, leverage existing fields).

**Files**: `memory_writer_persona.md` (prompt update)
**Severity**: Low

---

### 11.3 CROSS-CUTTING GAPS (4 items)

#### X1: No temporal-spatial binding

**Current**: Temporal and spatial are independent field groups on MemoryAtom.

**Problem**: "We go to Olive Garden every Friday" binds a place to a recurring time.
Current model stores `location_name = "Olive Garden"` and `temporal_orientation = ONGOING`
as unlinked fields. The binding "this place at this recurring time" is lost.

**Required Change**: TemporalLink can carry an optional `place_id` reference,
and SpatialContext can carry temporal pattern info. But this may be over-engineering
for v3 -- the binding can be inferred by K0 P03 when it sees multiple atoms with
the same place_id and HABITUAL temporal links.

**Recommendation**: Defer to K0 P03 inference (no MW change needed for v3).

**Files**: None (K0 concern)
**Severity**: Low

---

#### X2: No causal link field

**Current**: MemoryAtom has no causal reference.

**Problem**: "Because it rained, we cancelled the picnic" produces 2 atoms with no
causal chain. "Why did we go to the movies?" cannot be answered from atom metadata.

**BOUNDARY NOTE — DEFERRED TO K0 P03**:
This gap proposes an inter-atom link (`caused_by: trace_id`), which is consolidation
work, not signal extraction. MW provides per-atom signals; P03 discovers inter-atom
relationships during episode consolidation. Causal chain discovery — even intra-turn —
is P03's responsibility.

If MW needs to surface a causal HINT, it should be a free-text signal on the atom
(e.g., `causal_context: Optional[str] = "because it rained"`) rather than an explicit
reference to another atom's trace_id. P03 would then use this text hint during
narrative chain construction.

**Owner**: K0 P03 (consolidation phase — causal chain inference)
**MW action**: None. Do not add `caused_by` to MemoryAtom.
**Severity**: Low (narrative enhancement, deferred)

---

#### X3: No rehearsal/retelling detection

**Current**: MemoryAtom has no `references_event` field.

**Problem**: "Remember that dinner with Mom?" creates a new atom that should link to
the original dinner atom. Currently they are independent.

**BOUNDARY NOTE — DEFERRED TO K0 P03**:
Rehearsal/retelling detection is cross-turn pattern recognition — the system must
search past atoms to find what is being referenced. This is consolidation work:
P03 already does cross-atom analysis during episode formation. MW does not have access
to st_hipp_events and CANNOT resolve references to past atoms.

MW CAN provide a per-atom signal: `is_recall: bool` (the LLM can detect "Remember
when..." language). But the actual linking — finding the original atom, creating
reconsolidation relationships — belongs to P03.

**Owner**: K0 P03 (reconsolidation / rehearsal detection during consolidation)
**MW action**: Optionally tag `is_recall: bool` signal on MemoryAtom. Do NOT add
`references_event_text` or any cross-atom reference field.
**Severity**: Low (future reconsolidation feature, deferred)

---

#### X4: LLM prompt does not instruct multi-temporal extraction

**Current** (architecture doc Section 18): System prompt instructs LLM to extract
text, participants, location, topics, sentiment, emotion, etc. There is NO instruction
to identify multiple temporal references per atom.

**Problem**: Without explicit instruction, the LLM will produce at most one Temporal
object per atom (matching the current schema). Even if we extend the schema to
TemporalLink[], the LLM will not produce multiple links unless prompted.

**Required Change**: Update `memory_writer_persona.md`:

```
For each memory, identify ALL temporal references:
  - "Yesterday we planned next Friday's party" = 2 temporal references
  - For each reference: extract mentioned_time, estimate uncertainty, classify link type
  - Link types: RETROSPECTIVE (past), PROSPECTIVE (future), HABITUAL (recurring),
    CONTEXTUAL (life period), CONDITIONAL (if...)
```

**Files**: `memory_writer_persona.md` (or equivalent prompt template)
**Severity**: Critical (schema changes are useless without LLM instruction)

---

## 12. Priority Matrix

### Must-Have for v3 (Blocks temporal/spatial alignment)

| ID | Gap | Files Changed | Schema Change | LLM Prompt Change |
|----|-----|---------------|---------------|-------------------|
| T1 | Multi-link temporal | types.py, schema.json | YES (temporal_links) | YES |
| T3 | Temporal link type enum | types.py, schema.json | YES (TemporalLinkType) | YES |
| T5 | Turn timestamp in ExtractionContext | types.py | No | No |
| T6 | Envelope Builder: turn timestamp not now_utc() | architecture, envelope builder | No | No |
| T7 | Race condition: temporal cleared before MW reads | events.py, Concierge | No | No |
| X4 | LLM prompt: multi-temporal instruction | persona.md | No | YES |

### Should-Have for v3 (Significant quality improvement)

| ID | Gap | Files Changed | Schema Change | LLM Prompt Change |
|----|-----|---------------|---------------|-------------------|
| T2 | Temporal precision/uncertainty | types.py, schema.json | YES (uncertainty_window_ms) | YES |
| S1 | Stable place_id (PlaceResolver) | types.py, schema.json, new resolver | YES (place_id) | No |
| T8 | Intra-turn extraction ordering | types.py, schema.json | YES (extraction_sequence) | No |

### Could-Have for v3 (Enrichment, deferrable)

| ID | Gap | Files Changed | Schema Change | LLM Prompt Change |
|----|-----|---------------|---------------|-------------------|
| T4 | TemporalOrientation expansion | types.py, schema.json | Maybe | No |
| S2 | Spatial hierarchy (per-atom signal) | types.py, schema.json | YES | YES |
| S3 | Spatial transitions (per-atom signal) | types.py, schema.json | YES | YES |
| S5 | Location functional dimension | persona.md | No | YES |

### Defer to K0 (Not MW responsibility)

| ID | Gap | Owner | Reason |
|----|-----|-------|--------|
| S4 | Spatial familiarity tracking | K0 P02 (needs place_id first) | Historical visit count = K0 data |
| X1 | Temporal-spatial binding inference | K0 P03 (cross-atom analysis) | Cross-atom pattern = consolidation |
| X2 | Causal chain linking | K0 P03 (consolidation phase) | Inter-atom links = consolidation work. MW may provide free-text `causal_context` signal only. |
| X3 | Rehearsal/retelling detection | K0 P03 (reconsolidation) | Cross-turn pattern recognition = consolidation work. MW may tag `is_recall: bool` signal only. |

---

## 13. Implementation Sequence

### Step 1: Fix the foundation (T5 + T6 + T7)

**Goal**: Conversation time anchor is correct and race-free.

1. Add `turn_timestamp_ms: int` to ExtractionContext (T5)
2. Add `mentioned_time: Optional[MentionedTime]` and `mentioned_location: Optional[MentionedLocation]` to TurnCompletePayload (T7)
3. Change Envelope Builder from `now_utc()` to `turn_timestamp_ms` for event_time_utc (T6)
4. Context Assembly reads temporal from TurnCompletePayload first, SessionState fallback

**Affected files**:

- `k1/memory_writer/types.py` (ExtractionContext)
- `k1/memory_writer/events.py` (TurnCompletePayload)
- Envelope builder design (architecture doc Section 9)
- Context assembly design (architecture doc Section 7)

**Risk**: Low -- additive fields, backward compatible.
**Depends on**: Nothing.

---

### Step 2: Multi-link temporal model (T1 + T3 + T2 + X4)

**Goal**: MemoryAtom supports multiple temporal references with type and precision.

1. Create `TemporalLinkType` enum (T3)
2. Create `TemporalLink` frozen dataclass (T1 + T2 + T3)
3. Replace `temporal: Optional[Temporal]` with `temporal_links: List[TemporalLink]` on MemoryAtom
4. Add `conversation_anchor_ms: int` to MemoryAtom (always from turn_timestamp_ms)
5. Update `memory_atom.v2.schema.json` -> bump to v3
6. Update LLM prompt to instruct multi-temporal extraction (X4)
7. Update ExtractionValidator to validate TemporalLink list

**Affected files**:

- `k1/memory_writer/types.py` (new enum, new dataclass, MemoryAtom changes)
- `k1/contracts/schemas/memory_writer/memory_atom.v2.schema.json` -> v3
- `memory_writer_persona.md` (prompt)
- Extraction validator design

**Risk**: Medium -- schema version bump, K0 P02 M08 must be updated to receive v3 atoms.
**Depends on**: Step 1 (turn_timestamp_ms exists).

---

### Step 3: Spatial identity (S1)

**Goal**: Locations have stable identity across visits.

1. Add `place_id: Optional[str]` to MemoryAtom
2. Create `PlaceResolver` (analogous to `PersonResolver`)
3. PlaceResolver resolves names to place_ids from beliefs_active entities (type=LOCATION)
4. Update schema.json with place_id field

**Affected files**:

- `k1/memory_writer/types.py` (MemoryAtom)
- New: `k1/memory_writer/context/place_resolver.py`
- `k1/contracts/schemas/memory_writer/memory_atom.v2.schema.json` (or v3)

**Risk**: Low -- additive field, PlaceResolver follows existing PersonResolver pattern.
**Depends on**: Nothing (can run parallel to Step 2).

---

### Step 4: Per-atom signal enrichment (T8 + S2 + S3)

**Goal**: Intra-turn ordering, spatial hierarchy, spatial transitions — all per-atom signals.

1. Add `extraction_sequence: int` to MemoryAtom (T8)
2. Add `location_hierarchy: List[str]` to SpatialContext (S2)
3. Add `transition_from: Optional[str]` and `transition_mode: Optional[str]` (S3)
4. Update LLM prompt for hierarchy and transitions

**BOUNDARY NOTE**: All items in this step are per-atom signals extracted from
conversation text. None create inter-atom links. X2 (causal chain linking) and
X3 (rehearsal/retelling detection) were originally considered here but have been
moved to "Defer to K0 P03" — they involve cross-atom/cross-turn pattern recognition
that belongs to the consolidation pipeline, not MW signal extraction.

**Risk**: Low -- enrichment, not core flow.
**Depends on**: Step 3 (place_id for transition_from).

---

## 14. Schema Migration Plan (v2 to v3)

### New Fields (all optional, backward compatible)

| Field | Type | Default | Source |
|-------|------|---------|--------|
| `conversation_anchor_ms` | int | 0 | turn.complete.v1.timestamp_ms |
| `temporal_links` | TemporalLink[] | [] | LLM extraction |
| `place_id` | string or null | null | PlaceResolver |
| `extraction_sequence` | int | 0 | Validator ordinal |
| `location_hierarchy` | string[] | [] | LLM extraction |

### Deprecated Fields (keep for backward compat, stop populating)

| Field | Reason |
|-------|--------|
| `temporal` (single Temporal object) | Replaced by `temporal_links` list |
| `temporal_orientation` (atom-level) | Derived from dominant link_type in temporal_links |

### K0 Receiver Changes Required

| K0 Component | Change Required |
|--------------|----------------|
| K0 Gate | Accept schema_version "3.0" alongside "2.0" |
| K0 P02 M08 | Parse temporal_links array; use conversation_anchor_ms as authoritative event_time_utc |
| K0 P02 M13 | Write temporal_links to JSONB column; write conversation_anchor_ms |
| K0 st_hipp_events | New columns: temporal_links_json (JSONB), conversation_anchor_ms (BIGINT), place_id (TEXT) |
| K0 P03 R0 | Load conversation_anchor_ms as P03EventState.timestamp (preferred over event_time_utc) |
| K0 P03 R2 | No change needed (uses P03EventState.timestamp which R0 will set correctly) |

---

## 15. Relationship to GAP-002 Options A/B/C

GAP-002 Section 8 proposed three options for the M08 overwrite fix:

| Option | What | MW Exploration Finding |
|--------|------|------------------------|
| A | M08 refactor (never overwrite event_time_utc) | Still needed but INSUFFICIENT alone -- does not solve multi-temporal or race condition |
| B | R0 compensation | Rejected -- no reliable secondary source |
| C | K1 propagation (conversation_timestamp_ms field) | **RECOMMENDED** -- Section 13 Step 1 implements exactly this |

**Combined recommendation**: Option C (Step 1) + Option A (M08 refactor) together.
Step 1 gives K0 the gold-standard conversation anchor. Option A prevents M08 from
overwriting it. Together they make the temporal chain bulletproof.

---

## 16. Open Questions for Decision

| # | Question | Options | Recommendation |
|---|----------|---------|----------------|
| Q1 | Schema version: increment to "3.0" or use "2.1"? | 3.0 (breaking), 2.1 (additive) | 2.1 -- all changes are additive, v2 atoms are valid v2.1 |
| Q2 | Where does PlaceResolver get place registry? | beliefs_active entities, new place table, K0 lookup | beliefs_active entities (same as PersonResolver) |
| Q3 | Should temporal_links be extracted by K1 LLM or K0 M08? | K1 LLM (has context), K0 M08 (has NER), both | K1 LLM primary, K0 M08 validates/enriches (same pattern as sentiment) |
| Q4 | Max temporal_links per atom? | Unbounded, cap at 3, cap at 5 | Cap at 5 (budget constraint: each link is ~30 tokens in LLM output) |
| Q5 | Include MentionedTime in TurnCompletePayload? | Yes (Option A for T7), No (rely on snapshot timing) | Yes -- eliminates race, <100 bytes |

---

## 17. MW Exploration References

- MW Architecture: `k1/memory_writer/memory_writer_architecture.md` (2195 lines, 32 sections)
- MW Types: `k1/memory_writer/types.py` (490 lines, 12 enums, 11 dataclasses)
- MW Events: `k1/memory_writer/events.py` (148 lines, 6 events)
- MW Config: `k1/memory_writer/config.py` (97 lines, MWConfig frozen dataclass)
- MW Invariants: `k1/memory_writer/invariants.py` (366 lines, MW-01 through MW-11)
- MW Schema: `k1/contracts/schemas/memory_writer/memory_atom.v2.schema.json` (420 lines)
- SessionState beliefs_active: `k1/sessionstate/sections/beliefs_active.py` L640-750 (temporal/spatial methods)
- K0 M08: `k0/modules/context/temporal_profile.py` L480-580 (normalize_timestamp)
- K0 R0: `k0/pipelines/p03/phases/r0_batch_selector.py` L666-710 (timestamp chain)

---

# PART III: st_hipp_events Table Audit

*Added: 2026-03-05*
*Source: Live PostgreSQL (k0-postgres container), all migrations 0022-0074, column contract YAML*

---

## 18. Table Overview

**st_hipp_events** is the central episodic memory store in K0. Every memory atom that
passes through the P02 Write pipeline lands here as a single row. P03 Consolidation
reads from this table, enriches it, and writes reconciliation decisions back.

| Metric | Value |
|--------|-------|
| Total columns | 142 |
| Total rows (live) | 78 |
| Migrations touching table | 7 (0022, 0034, 0046, 0051, 0052, 0053, 0060, 0073, 0074) |
| Indexes | 22 |
| CHECK constraints | 13 |
| Foreign key references | 4 tables (st_anchor_observations, st_embedding_queue x2, st_vec, st_learning_queue) |
| Column contract | `k0/contracts/schemas/st_hipp_events_v2.columns.yaml` |

---

## 19. Column Taxonomy by Owner

Every column in st_hipp_events has exactly ONE owner -- the component responsible for
populating it. The column lifecycle is:

```
K1 MW --> Bridge (passthrough) --> K0 Gate --> P02 Modules --> M13 Builder --> INSERT
                                                                   |
P03 Consolidation (R0-R8) --> UPDATE (consolidation/reconciliation columns)
```

### 19.1 IDENTITY and TRACE (9 columns) -- Owner: K1 Envelope (passthrough)

| # | Column | Type | Nullable | Owner | Source | Status |
|---|--------|------|----------|-------|--------|--------|
| 1 | event_id | TEXT | PK | K1/Bridge | envelope.cognitive_trace_id | OK |
| 2 | wal_pos | BIGINT | NOT NULL | K0 WAL | K0 write-ahead log | OK |
| 3 | cognitive_trace_id | TEXT | NOT NULL | K1/Bridge | envelope.cognitive_trace_id | DUPLICATE of event_id |
| 4 | tenant_id | TEXT | NOT NULL | K1/Bridge | envelope.tenant_id | OK |
| 5 | space_id | TEXT | NOT NULL | K1/Bridge | envelope.space_id | OK |
| 6 | effective_space_id | TEXT | nullable | K0 M05 | space resolution | OK |
| 7 | topic | TEXT | NOT NULL | K1/Bridge | envelope.topic | OK |
| 8 | uow_id | TEXT | nullable | K0 UoW | unit of work | OK |
| 9 | schema_version | TEXT | NOT NULL | K1/Bridge | envelope.schema_version | OK |

**Issues**: `cognitive_trace_id` is always identical to `event_id` -- pure duplication.

### 19.2 INTEGRITY and AUDIT (6 columns) -- Owner: K1 Envelope (passthrough)

| # | Column | Type | Nullable | Owner | Source | Status |
|---|--------|------|----------|-------|--------|--------|
| 10 | envelope_sha256 | TEXT | NOT NULL | K1/Bridge | envelope hash | OK |
| 11 | sig_alg | TEXT | NOT NULL | K1/Bridge | signature algorithm | OK |
| 12 | sig_kid | TEXT | NOT NULL | K1/Bridge | signing key ID | OK |
| 13 | idem_key | TEXT | NOT NULL | K1/Bridge | idempotency key | OK |
| 14 | ingested_at | BIGINT | NOT NULL | K0 Gate | K0 ingestion time | OK |
| 15 | clock_skew_ms | INTEGER | nullable | K0 M08 | clock drift detection | OK |

**Issues**: None. Clean group.

### 19.3 POLICY and VISIBILITY (10 columns) -- Owner: K1 Policy + K0 M03/M05

| # | Column | Type | Nullable | Owner | Source | Status |
|---|--------|------|----------|-------|--------|--------|
| 16 | policy_decision | TEXT | NOT NULL | K1 Policy | ALLOW/DENY | OK |
| 17 | policy_band | TEXT | NOT NULL | K1 Policy | GREEN/AMBER/RED | OK |
| 18 | policy_version | TEXT | NOT NULL | K1 Policy | policy rules version | OK |
| 19 | obligations_json | TEXT | nullable | K0 M03 | policy obligations | OK |
| 20 | visible_to_json | TEXT | nullable | K0 M05 | actor visibility list | OK |
| 21 | visibility_scope | TEXT | nullable | K0 M05 | scope classification | OK |
| 22 | owner_id | TEXT | NOT NULL | K0 M05 | event owner | OK |
| 23 | co_owners_json | TEXT | nullable | K0 M05 | co-owners | OK |
| 24 | retention_policy_id | TEXT | NOT NULL | K0 M11 | retention policy | OK |
| 25 | retention_bucket | TEXT | NOT NULL | K0 M11 | STANDARD/SENSITIVE/EPHEMERAL | OK |

**Issues**: None. Clean group.

### 19.4 ACTOR and DEVICE (6 columns) -- Owner: K1 Envelope + K0 M09/M10

| # | Column | Type | Nullable | Owner | Source | Status |
|---|--------|------|----------|-------|--------|--------|
| 26 | actor_id | TEXT | NOT NULL | K1/Bridge | envelope.actor | OK |
| 27 | actor_role | TEXT | nullable | K1/Bridge | SELF/AGENT/SYSTEM/DELEGATE | OK |
| 28 | device_id | TEXT | NOT NULL | K1/Bridge | envelope.device_id | OK |
| 29 | device_kind | TEXT | NOT NULL | K0 M09 | phone/tablet/desktop | OK |
| 30 | device_os | TEXT | nullable | K0 M09 | iOS/Android/etc | OK |
| 31 | ingress_channel | TEXT | nullable | K0 M10 | write/import/etc | OK |

**Issues**: None. Clean group.

### 19.5 TEMPORAL (14 columns) -- Owner: K0 M08 + K1 MW signals

| # | Column | Type | Nullable | Owner | Source | Status |
|---|--------|------|----------|-------|--------|--------|
| 32 | event_time_utc | BIGINT | NOT NULL | K0 M08 | normalized timestamp (SECONDS) | PROBLEM: M08 overwrites MW temporal |
| 33 | write_time_utc | BIGINT | NOT NULL | K0 M08 | write timestamp | OK |
| 34 | write_lag_ms | INTEGER | nullable | K0 M08 | write_time - event_time delta | OK |
| 35 | local_date | TEXT | nullable | K0 M08 | YYYY-MM-DD local | OK |
| 36 | local_time | TEXT | nullable | K0 M08 | HH:MM:SS local | OK |
| 37 | day_of_week | TEXT | nullable | K0 M08 | Monday-Sunday | OK |
| 38 | is_weekend | BOOLEAN | nullable | K0 M08 | derived from day_of_week | OK |
| 39 | time_of_day_bucket | TEXT | nullable | K0 M08 | MORNING/AFTERNOON/EVENING/NIGHT | OK |
| 40 | circadian_slot | TEXT | nullable | K0 M08 | fine-grained circadian | OK |
| 41 | is_backdated | BOOLEAN | nullable | K0 M08 | event_time << write_time | OK |
| 42 | created_at | BIGINT | NOT NULL | K0 System | row creation time | OK |
| 43 | temporal_mentioned_time | TEXT | nullable | K1 MW | raw temporal text ("yesterday evening") | OK (MW signal) |
| 44 | temporal_resolved_epoch_ms | BIGINT | nullable | K1 MW | MW-resolved epoch MILLISECONDS | OK (MW signal) |
| 45 | temporal_orientation | TEXT | nullable | K1 MW | PAST/ONGOING/FUTURE_COMMITMENT | OK (MW signal) |

**Issues**:

- `event_time_utc` is in SECONDS but `temporal_resolved_epoch_ms` is in MILLISECONDS -- unit mismatch
- M08 overwrites `event_time_utc` from its own resolution, ignoring MW's `temporal_resolved_epoch_ms`
- No `conversation_anchor_ms` column (proposed in GAP-002 Section 13 Step 1)
- `circadian_slot` is populated but semantics are undocumented (sample: empty strings)

### 19.6 SPATIAL and PLACE (5 columns) -- Owner: K0 M12/M15 + K1 MW

| # | Column | Type | Nullable | Owner | Source | Status |
|---|--------|------|----------|-------|--------|--------|
| 46 | location_name | TEXT | nullable | K0 M15/M12 | human-readable location | OK |
| 47 | location_type | TEXT | nullable | K0 M15/M12 | restaurant/home/park/etc | OK |
| 48 | geohash_6 | TEXT | nullable | K0 M12 | 6-char geohash | OK |
| 49 | geo_precision_external | TEXT | nullable | K0 M12 | precision level | OK |
| 50 | geo_masking_reason | TEXT | nullable | K0 M12 | privacy masking reason | OK |

**Issues**:

- No `place_id` column (proposed in GAP-002 Section 13 Step 3)
- No `location_hierarchy` (proposed in GAP-002 S2)
- `location_name` has no stable identity -- "Olive Garden" vs "Olive Garden on Main St"

### 19.7 SOCIAL and RELATIONSHIPS (9 columns) -- Owner: K0 M07 + K1 MW

| # | Column | Type | Nullable | Owner | Source | Status |
|---|--------|------|----------|-------|--------|--------|
| 51 | participants_json | TEXT | nullable | K1 MW | body.participants array | OK |
| 52 | num_participants | INTEGER | nullable | K0 M07 | derived count | OK |
| 53 | has_partner_present | BOOLEAN | nullable | K0 M07 | family graph check | OK |
| 54 | has_parent_present | BOOLEAN | nullable | K0 M07 | family graph check | OK |
| 55 | is_solo_event | BOOLEAN | nullable | K0 M07 | single participant | OK |
| 56 | participant_roles_json | TEXT | nullable | K0 M07 | role mapping JSON | OK |
| 57 | social_context | TEXT | nullable | K0 M07 | nuclear_family/friends/etc | OK |
| 58 | social_intimacy | TEXT | nullable | K0 M07 | HIGH/MED/LOW | OK |
| 59 | participant_relationships_json | TEXT | NOT NULL | K1 MW (v2) | MW relationship signals | OK (MW signal) |

**Issues**: None. Clean group.

### 19.8 SEMANTIC and ACTIVITY (10 columns) -- Owner: K1 MW + K0 M10

| # | Column | Type | Nullable | Owner | Source | Status |
|---|--------|------|----------|-------|--------|--------|
| 60 | text | TEXT | nullable | K1 MW | memory atom text | OK |
| 61 | text_normalized | TEXT | nullable | K0 M02 | normalized text | OK |
| 62 | char_count | INTEGER | nullable | K0 M02 | len(text) | OK |
| 63 | token_count | INTEGER | nullable | K0 M02 | token estimate | OK |
| 64 | language | TEXT | nullable | K1 MW | detected language | OK |
| 65 | activity_type | TEXT | nullable | K0 M10 | LEGACY 7-type: meal/routine/etc | SUPERSEDED |
| 66 | activity_category | TEXT | nullable | K0 M10 | episodic/semantic/procedural | OK |
| 67 | is_meal | BOOLEAN | nullable | K1 MW | body.is_meal | OK |
| 68 | is_outing | BOOLEAN | nullable | K1 MW | body.is_outing | OK |
| 69 | ingress_source | TEXT | nullable | K0 M10 | mobile_app/web/etc | OK |

**Issues**:

- `activity_type` is SUPERSEDED by `activity_type_ultrabert` (12 types vs 7)

### 19.9 HIPPOCAMPUS: Pattern Separation and Novelty (8 columns) -- Owner: K0 M01

| # | Column | Type | Nullable | Owner | Source | Status |
|---|--------|------|----------|-------|--------|--------|
| 70 | simhash_hex | TEXT | NOT NULL | K0 M01 | simhash fingerprint | OK |
| 71 | minhash32 | TEXT | NOT NULL | K0 M01 | minhash signature | OK |
| 72 | novelty_score | FLOAT | nullable | K0 M01 | pattern separation novelty | OK |
| 73 | near_duplicates_json | TEXT | nullable | K0 M01 | near-duplicate event_ids | OK |
| 74 | is_near_duplicate | BOOLEAN | nullable | K0 M01 | dedup flag | OK |
| 75 | episode_cluster_id | TEXT | nullable | K0 P03 | cluster assignment | OK (P03 writes) |
| 76 | cluster_confidence | FLOAT | nullable | K0 P03 | cluster confidence | OK (P03 writes) |
| 77 | clustering_version | TEXT | nullable | K0 P03 | clustering algo version | OK (P03 writes) |

**Issues**: None. Clean group.

### 19.10 EMBEDDINGS and KNOWLEDGE GRAPH (4 columns) -- Owner: K0 M02

| # | Column | Type | Nullable | Owner | Source | Status |
|---|--------|------|----------|-------|--------|--------|
| 78 | embedding_id | TEXT | NOT NULL, UNIQUE | K0 M02 | embedding job ID | OK |
| 79 | embedding_status | TEXT | NOT NULL | K0 P08 | PENDING/IN_PROGRESS/READY/FAILED | OK |
| 80 | entities_json | TEXT | nullable | K0 M02/P03 R4 | resolved entities | OK |
| 81 | kg_triples_json | TEXT | nullable | K0 M02 | knowledge graph triples | OK |

**Issues**: None.

### 19.11 AFFECT and SALIENCE (9 columns) -- Owner: K0 M04/M06

| # | Column | Type | Nullable | Owner | Source | Status |
|---|--------|------|----------|-------|--------|--------|
| 82 | sentiment_score | FLOAT | nullable | K0 M04 | sentiment [-1, 1] | OK |
| 83 | sentiment_label | TEXT | nullable | K0 M04 | positive/negative/neutral | OK |
| 84 | dominant_emotions_json | TEXT | nullable | K0 M04 | emotion array | OK |
| 85 | affect_valence | FLOAT | nullable | K0 M04 | VAD valence | OK |
| 86 | affect_arousal | FLOAT | nullable | K0 M04 | VAD arousal | OK |
| 87 | affect_band | TEXT | nullable | K0 M04 | GREEN/AMBER/RED | OK |
| 88 | salience_score | FLOAT | NOT NULL | K0 M06 | importance score | OK |
| 89 | salience_reasons_json | TEXT | nullable | K0 M06 | reason array | OK |
| 90 | salience_band | TEXT | nullable | K0 M06 | HIGH/MED/LOW | OK |

**Issues**: None. Clean group.

### 19.12 METADATA and VERSIONING (4 columns) -- Owner: K0 System

| # | Column | Type | Nullable | Owner | Source | Status |
|---|--------|------|----------|-------|--------|--------|
| 91 | hippocampus_api_version | TEXT | nullable | K0 System | API version | OK |
| 92 | space_resolver_version | TEXT | nullable | K0 M05 | resolver version | OK |
| 93 | schema_uri | TEXT | nullable | K1/Bridge | schema URI | OK |
| 94 | updated_at | BIGINT | NOT NULL | K0 System | last update time | OK |

**Issues**: None.

### 19.13 P03 CONSOLIDATION (13 columns) -- Owner: K0 P03

| # | Column | Type | Nullable | Owner | Source | Status |
|---|--------|------|----------|-------|--------|--------|
| 95 | consolidation_status | TEXT | nullable | K0 P03 | PENDING/CONSOLIDATED/DUPLICATE/PRUNED | OK |
| 96 | consolidation_cycle_id | TEXT | nullable | K0 P03 | cycle identifier | OK |
| 97 | consolidated_at | BIGINT | nullable | K0 P03 | consolidation timestamp (0034) | DUPLICATE |
| 98 | reconciliation_decision | TEXT | nullable | K0 P03 | CREATE/REINFORCE/etc (0034) | SUPERSEDED |
| 99 | truth_match_id | TEXT | nullable | K0 P03 | matched truth ID (0034) | SUPERSEDED |
| 100 | truth_match_similarity | FLOAT | nullable | K0 P03 | match similarity (0034) | SUPERSEDED |
| 101 | reconciliation_action | TEXT | nullable | K0 P03 R6/R7 | REINFORCE/EXTEND/CREATE/etc (0052) | OK |
| 102 | best_match_id | TEXT | nullable | K0 P03 R6/R7 | matched truth ID (0052) | OK |
| 103 | best_match_layer | TEXT | nullable | K0 P03 R6/R7 | st_epi/st_sem/st_kg (0052) | OK |
| 104 | similarity_score | FLOAT | nullable | K0 P03 R6/R7 | cosine similarity (0052) | OK |
| 105 | confidence | FLOAT | nullable | K0 P03 R6/R7 | decision confidence (0052) | OK |
| 106 | reconciliation_reason | TEXT | nullable | K0 P03 R6/R7 | human-readable reason (0052) | OK |
| 107 | consolidated_at_ms | BIGINT | nullable | K0 P03 R6/R7 | consolidation time MS (0052) | DUPLICATE of #97 |
| 108 | archival_status | TEXT | nullable | K0 P03 R0 | archival filter | OK |

**Issues** (MAJOR -- duplicate columns from successive migrations):

- `reconciliation_decision` (#98, migration 0034) SUPERSEDED by `reconciliation_action` (#101, migration 0052). Both populated: all 78 rows have `reconciliation_decision=CREATE`, 0 rows have `reconciliation_action`.
- `truth_match_id` (#99, 0034) SUPERSEDED by `best_match_id` (#102, 0052). 0 rows use either.
- `truth_match_similarity` (#100, 0034) SUPERSEDED by `similarity_score` (#104, 0052). 78 rows have `similarity_score=0`, 0 rows have `truth_match_similarity`.
- `consolidated_at` (#97, 0034) DUPLICATES `consolidated_at_ms` (#107, 0052). Both are BIGINT. 78 rows have `consolidated_at` populated, 0 rows have `consolidated_at_ms`.
- **Net effect**: 4 zombie columns consuming space and causing confusion.

### 19.14 P02 UltraBERT NER (5 columns) -- Owner: K0 P02 UltraBERT

| # | Column | Type | Nullable | Owner | Source | Status |
|---|--------|------|----------|-------|--------|--------|
| 109 | ner_entities_json | TEXT | nullable | K0 P02 | UltraBERT NER output | OK |
| 110 | temporal_json | TEXT | nullable | K0 P02 | UltraBERT temporal head | OK |
| 111 | intent_category | TEXT | nullable | K0 P02 | UltraBERT intent | DUPLICATE |
| 112 | ingress_category | TEXT | nullable | K0 P02 | UltraBERT ingress | DUPLICATE |
| 113 | ultrabert_version | TEXT | nullable | K0 P02 | model version | OK |

**Issues**:

- `intent_category` (#111) DUPLICATES `intent_ultrabert` (#125) and `intent_type` (#135). THREE intent columns.
- `ingress_category` (#112) DUPLICATES `activity_type_ultrabert` (#123). Same UltraBERT INGRESS head output stored twice.

### 19.15 UltraBERT Full Capability (8 columns) -- Owner: K0 P02 UltraBERT

| # | Column | Type | Nullable | Owner | Source | Status |
|---|--------|------|----------|-------|--------|--------|
| 114 | extracted_relations_json | TEXT | nullable | K0 P02 | UltraBERT relations head | OK |
| 115 | safety_familyos_band | TEXT | nullable | K0 P02 | UltraBERT safety 4-band | OK |
| 116 | safety_familyos_subcategory | TEXT | nullable | K0 P02 | safety subcategory | OK |
| 117 | effective_safety_band | TEXT | nullable | K0 P02 | MAX(policy_band, safety_familyos_band) | OK |
| 118 | nli_label | TEXT | nullable | K0 P02 | entailment/neutral/contradiction | OK |
| 119 | nli_confidence | FLOAT | nullable | K0 P02 | NLI confidence | OK |
| 120 | sentiment_confidence | FLOAT | nullable | K0 P02 | UltraBERT sentiment confidence | OK |

**Issues**: None. Clean group.

### 19.16 UltraBERT Activity and Intent (4 columns) -- Owner: K0 P02 UltraBERT

| # | Column | Type | Nullable | Owner | Source | Status |
|---|--------|------|----------|-------|--------|--------|
| 121 | activity_type_ultrabert | TEXT | nullable | K0 P02 | 12-type classification | OK (canonical) |
| 122 | activity_type_confidence | FLOAT | nullable | K0 P02 | confidence score | OK |
| 123 | intent_ultrabert | TEXT | nullable | K0 P02 | 8-type intent | DUPLICATE of #111 |
| 124 | intent_confidence | FLOAT | nullable | K0 P02 | intent confidence | OK |

**Issues**: See 19.14 -- intent/ingress duplication.

### 19.17 MW v2 Signals (16 columns) -- Owner: K1 MW (passthrough via Bridge)

| # | Column | Type | Nullable | Owner | Source | Status |
|---|--------|------|----------|-------|--------|--------|
| 125 | narrative_thread_id | TEXT | nullable | K1 MW | conversation thread | OK (MW signal) |
| 126 | narrative_arc_position | TEXT | nullable | K1 MW | EXPOSITION/RISING/CLIMAX/RESOLUTION | OK (MW signal) |
| 127 | narrative_is_goal_event | BOOLEAN | NOT NULL | K1 MW | goal-related memory | OK (MW signal) |
| 128 | affect_dominance | FLOAT | nullable | K1 MW | VAD dominance dimension | OK (MW signal) |
| 129 | entity_salience_json | TEXT | NOT NULL | K1 MW | per-entity salience | OK (MW signal) |
| 130 | temporal_mentioned_time | TEXT | nullable | K1 MW | DUPLICATE: already in 19.5 #43 | SEE 19.5 |
| 131 | temporal_resolved_epoch_ms | BIGINT | nullable | K1 MW | DUPLICATE: already in 19.5 #44 | SEE 19.5 |
| 132 | temporal_orientation | TEXT | nullable | K1 MW | DUPLICATE: already in 19.5 #45 | SEE 19.5 |
| 133 | intent_type | TEXT | nullable | K1 MW | MW intent classification | TRIPLE DUPLICATE |
| 134 | goal_context | TEXT | nullable | K1 MW | goal/aspiration context | OK (MW signal) |
| 135 | source_type | TEXT | nullable | K1 MW | user_stated/implied/observed/inferred | OK (MW signal) |
| 136 | novelty | TEXT | nullable | K1 MW | ROUTINE/EXPECTED/NOVEL/SURPRISING | OK (MW signal) |
| 137 | elaboration_depth | TEXT | nullable | K1 MW | MENTION/DISCUSSED/ELABORATED/DEEPLY | OK (MW signal) |
| 138 | identity_domains_json | TEXT | NOT NULL | K1 MW | identity domain array | OK (MW signal) |
| 139 | participant_relationships_json | TEXT | NOT NULL | K1 MW | relationship signals | SEE 19.7 |
| 140 | k1_signal_version | TEXT | NOT NULL | K1 MW | signal schema version | OK (MW signal) |

**Issues**:

- Temporal columns 130-132 are grouped here but logically belong with 19.5 Temporal. Not duplicated in DB -- same physical columns, just listed in this migration group. No actual duplication.
- `intent_type` (#133) is the THIRD intent column alongside `intent_category` (#111) and `intent_ultrabert` (#123).

### 19.18 M5A Cognitive Signals (5 columns) -- Owner: K1 MW / K0 P02

| # | Column | Type | Nullable | Owner | Source | Status |
|---|--------|------|----------|-------|--------|--------|
| 141 | surprise_level | REAL | DEFAULT 0.0 | K1 MW | surprise/unexpectedness | OK (MW signal) |
| 142 | identity_relevance | REAL | DEFAULT 0.0 | K1 MW | self-identity relevance | OK (MW signal) |
| 143 | source_reliability | REAL | DEFAULT 1.0 | K1 MW | source trustworthiness | OK (MW signal) |
| 144 | memory_tier | VARCHAR(20) | DEFAULT 'routine' | K1 MW | routine/notable/significant/landmark | OK (MW signal) |
| 145 | temporal_anchor_json | TEXT | DEFAULT '{}' | K1 MW | resolved temporal anchor JSON | OK (MW signal) |

**Issues**: None. Clean group.

### 19.19 ORPHAN COLUMN

| # | Column | Type | Nullable | Owner | Source | Status |
|---|--------|------|----------|-------|--------|--------|
| 146 | merge_cascade_id | VARCHAR(36) | nullable | K0 P03 | merge cascade tracking | OK |

**Issues**: Added by an untracked migration. Indexed but no CHECK constraint.

---

## 20. Trash Audit: Duplicate and Superseded Columns

### 20.1 Confirmed Duplicates (same data, multiple columns)

| Zombie Column | Superseded By | Migration | Evidence | Action |
|---------------|---------------|-----------|----------|--------|
| `reconciliation_decision` | `reconciliation_action` | 0034 vs 0052 | 78 rows use old, 0 use new | DEPRECATE old, migrate data to new |
| `truth_match_id` | `best_match_id` | 0034 vs 0052 | 0 rows in either | DEPRECATE old |
| `truth_match_similarity` | `similarity_score` | 0034 vs 0052 | 78 rows use new, 0 use old | DEPRECATE old |
| `consolidated_at` | `consolidated_at_ms` | 0034 vs 0052 | 78 rows use old (seconds), 0 use new (ms) | DEPRECATE one, standardize unit |

### 20.2 Triple-Duplicate Intent Columns

| Column | Migration | Source | Sample Value | Action |
|--------|-----------|--------|--------------|--------|
| `intent_category` | 0046 | UltraBERT INTENT head | "log_memory" | DEPRECATE |
| `intent_ultrabert` | 0060 | UltraBERT INTENT head | "log_memory" | KEEP as canonical UltraBERT intent |
| `intent_type` | 0073 | K1 MW intent signal | "log_memory" | KEEP as MW signal (different source) |

All three hold "log_memory" in live data. `intent_category` was the first attempt (0046),
`intent_ultrabert` was the do-over with confidence (0060), `intent_type` is from MW (0073).
**Canonical**: `intent_ultrabert` (UltraBERT) + `intent_type` (MW). Drop `intent_category`.

### 20.3 Double-Duplicate Activity/Ingress Columns

| Column | Migration | Source | Sample Value | Action |
|--------|-----------|--------|--------------|--------|
| `ingress_category` | 0046 | UltraBERT INGRESS head | "PLANNING" | DEPRECATE |
| `activity_type_ultrabert` | 0060 | UltraBERT INGRESS head | "PLANNING" | KEEP as canonical |
| `activity_type` | 0022 | Legacy K0 M10 (7 types) | "routine" | KEEP (backward compat, different source) |

`ingress_category` and `activity_type_ultrabert` are the same UltraBERT INGRESS output.
`activity_type` is legacy 7-type from M10. Drop `ingress_category`.

### 20.4 Timestamp Unit Inconsistency

| Column | Unit | Example Value |
|--------|------|---------------|
| `event_time_utc` | SECONDS | 1771978659 |
| `write_time_utc` | SECONDS | 1772687878 |
| `ingested_at` | SECONDS | 1772687878 |
| `created_at` | SECONDS | 1772687878 |
| `consolidated_at` | MIXED (milliseconds stored) | 1772687889456 |
| `temporal_resolved_epoch_ms` | MILLISECONDS | 1771978659169 |
| `consolidated_at_ms` | MILLISECONDS (0 rows) | null |
| `updated_at` | SECONDS | 1772687878 |

**Problem**: `consolidated_at` was defined as "seconds" in migration 0034 but actually
stores milliseconds (13-digit values). `consolidated_at_ms` was added in 0052 to fix
this but is never populated. Meanwhile `event_time_utc` is true seconds (10-digit).

---

## 21. Cleanup Plan

### Phase 1: Deprecate zombie columns (migration required)

Add `-- DEPRECATED` comments and stop populating. Do NOT drop yet (backward compat).

| Column to Deprecate | Replacement | Migration |
|---------------------|-------------|-----------|
| `cognitive_trace_id` | `event_id` (identical) | future |
| `reconciliation_decision` | `reconciliation_action` | future |
| `truth_match_id` | `best_match_id` | future |
| `truth_match_similarity` | `similarity_score` | future |
| `consolidated_at` | `consolidated_at_ms` (standardize to ms) | future |
| `intent_category` | `intent_ultrabert` + `intent_type` | future |
| `ingress_category` | `activity_type_ultrabert` | future |

**Total deprecated**: 7 columns
**Remaining after cleanup**: 135 active columns

### Phase 2: Standardize timestamp units

All timestamps should be MILLISECONDS (13-digit). Currently mixed:

- Convert `event_time_utc` from seconds to ms (multiply by 1000)
- Convert `write_time_utc`, `ingested_at`, `created_at`, `updated_at` similarly
- OR: Keep seconds columns as-is, add new `_ms` variants for new consumers

**Recommendation**: Keep existing seconds columns for backward compat, but all NEW
temporal columns MUST use milliseconds. Document the convention.

### Phase 3: New columns needed (from GAP-002 proposals)

| Column | Type | Owner | Source | GAP-002 Ref | Priority |
|--------|------|-------|--------|-------------|----------|
| `conversation_anchor_ms` | BIGINT | K1 MW | turn.complete.v1.timestamp_ms | Step 1 (T5/T6) | MUST-HAVE |
| `temporal_links_json` | TEXT (JSONB) | K1 MW | LLM multi-temporal extraction | Step 2 (T1/T3) | MUST-HAVE |
| `place_id` | TEXT | K1 MW | PlaceResolver | Step 3 (S1) | SHOULD-HAVE |
| `extraction_sequence` | INTEGER | K1 MW | atom ordinal within turn | Step 4 (T8) | COULD-HAVE |
| `location_hierarchy_json` | TEXT | K1 MW | LLM spatial hierarchy | Step 4 (S2) | COULD-HAVE |

**Note**: `transition_from` and `transition_mode` (S3) can be encoded inside
`temporal_links_json` or a new `spatial_context_json` JSONB column rather than
adding 2 more scalar columns.

---

## 22. Column Ownership Matrix (Complete)

Summary of who fills what across the full 142-column table.

| Owner | Columns Owned | Role |
|-------|---------------|------|
| **K1 MW (via Bridge passthrough)** | 26 | Memory atom signals: text, participants, temporal refs, narrative, affect dominance, cognitive signals, identity domains, MW version |
| **K1 Envelope (via Bridge passthrough)** | 15 | Identity, integrity, policy stamp, actor, device_id, schema |
| **K0 Gate / System** | 5 | ingested_at, created_at, updated_at, wal_pos, hippocampus_api_version |
| **K0 P02 M01 (Pattern Separate)** | 5 | simhash, minhash, novelty, near_duplicates, is_near_duplicate |
| **K0 P02 M02 (Semantic Project)** | 5 | embedding_id, text_normalized, char_count, token_count, entities_json (initial) |
| **K0 P02 M03 (Policy Stamp)** | 1 | obligations_json |
| **K0 P02 M04 (Affect Analyze)** | 6 | sentiment_score/label, affect_valence/arousal/band, dominant_emotions_json |
| **K0 P02 M05 (Space Resolve)** | 5 | effective_space_id, visible_to_json, visibility_scope, owner_id, co_owners_json, space_resolver_version |
| **K0 P02 M06 (Salience Score)** | 3 | salience_score, salience_reasons_json, salience_band |
| **K0 P02 M07 (Family Graph)** | 7 | num_participants, participant_roles_json, has_partner/parent_present, is_solo, social_context/intimacy |
| **K0 P02 M08 (Temporal Profile)** | 10 | event_time_utc, write_time_utc, write_lag_ms, local_date/time, day_of_week, is_weekend, time_of_day_bucket, circadian_slot, is_backdated |
| **K0 P02 M09 (Device Profile)** | 2 | device_kind, device_os |
| **K0 P02 M10 (Ingress Classify)** | 4 | ingress_channel, activity_type, activity_category, ingress_source |
| **K0 P02 M11 (Retention)** | 2 | retention_policy_id, retention_bucket |
| **K0 P02 M12/M15 (Geo)** | 3 | geohash_6, geo_precision_external, geo_masking_reason |
| **K0 P02 UltraBERT** | 15 | ner_entities_json, temporal_json, ultrabert_version, extracted_relations_json, safety bands (3), nli (2), sentiment_confidence, activity_type_ultrabert, activity_type_confidence, intent_ultrabert, intent_confidence |
| **K0 P03 (Consolidation)** | 14 | consolidation_status/cycle_id, consolidated_at/_ms, reconciliation_decision/action, truth_match_id/similarity, best_match_id/layer, similarity_score, confidence, reconciliation_reason, archival_status, episode_cluster_id, cluster_confidence, clustering_version, merge_cascade_id |
| **K0 P08 (Embedding)** | 1 | embedding_status |
| **DEPRECATED (zombie)** | 7 | cognitive_trace_id, reconciliation_decision, truth_match_id, truth_match_similarity, consolidated_at, intent_category, ingress_category |

### Bridge Role

Bridge is a **transparent passthrough**. It does not transform, enrich, or filter any
column data. It serializes K1 MemoryAtom fields into envelope format and forwards to K0.
Adding new MW signal columns requires:

1. K1 MW: Add field to MemoryAtom
2. Bridge: Map new field to envelope body (trivial -- already maps all body fields)
3. K0 M13: Map envelope body field to st_hipp_events column
4. K0 migration: Add column to PostgreSQL

No Bridge code change is needed for new columns -- Bridge already forwards all body fields
---

## 23. P02 Module Deep Dive: What Each Module Actually Does

This section walks through every P02 pipeline module, documenting:

- What the module does (algorithm, logic)
- What st_hipp_events columns it populates
- The complete fallback chain
- MW dependency (yes/no)
- Latency budget

Modules are documented in pipeline execution order (stage_10 through stage_80).

### P02 Pipeline Architecture Reminder

```
stage_10  M01  hippocampus.pattern_separate:v1     (DG fingerprinting)
stage_20  M02  hippocampus.semantic_project:v2      (CA1 semantic projection, PRIMARY GAP-FILLER)
stage_22  M22  embedding.extract_from_cache:v1      (embedding cache extraction)
stage_30  M04  affect.analyze:v2                    (affect scoring, TRUST-THEN-FILL)
stage_31  M05  space.resolve_visibility:v1          (family visibility)
stage_32  M07  social.family_graph_resolve:v2       (social graph, TRUST-THEN-FILL)
stage_33  M08  context.temporal_profile:v2          (temporal resolution, TRUST-THEN-FILL)
stage_40  M09  context.device_profile:v1            (device metadata)
stage_41  M10  context.ingress_classify:v1          (ingress/activity classification)
stage_42  M12  context.geo_metadata:v1              (geohash/geo precision)
stage_43  M15  context.spatial_minimal:v1           (spatial resolution)
stage_50  M11  context.retention_lookup:v1          (retention policy)
stage_55  M06  salience.score:v2                    (salience scoring, TRUST-THEN-FILL)
stage_60  M13  builders.hipp_events_row:v2          (row assembly)
stage_70  core.hipp_events_writer:v1                (atomic write)
stage_80  core.event_emitter:v1                     (event emission)
```

Trust-Then-Fill modules: M04, M07, M08, M06
Primary gap-filler: M02 (ALWAYS runs, NEVER skipped)

---

### 23.1 M01: hippocampus.pattern_separate:v1 (stage_10)

**Pipeline Role**: DG (Dentate Gyrus) Pattern Separation
**Contract**: `k0/contracts/modules/hippocampus.pattern_separate.v1.yaml`
**Source**: `k0/modules/hippocampus/pattern_separate.py` (260 lines)
**Latency Budget**: 15ms P95
**MW Dependency**: NONE
**Idempotent**: Yes

#### What It Does

Computes two fingerprints for near-duplicate detection and LSH bucketing:

1. **SimHash (64-bit Charikar)**: Locality-sensitive hash for coarse similarity
   - 3-gram word shingles from concatenated text
   - Each shingle hashed with SHA-256 (seeded, first 64 bits)
   - Bit vector: +1 if bit set, -1 if unset across all shingles
   - Threshold: fingerprint bit = 1 if aggregate > 0

2. **MinHash (32-permutation Broder)**: Signature for LSH bucket assignment
   - Same 3-gram shingles
   - 32 independent hash functions (SHA-256 with permutation index seed)
   - Per-permutation: take minimum hash value across all shingles
   - Result: 32-element integer array (BIGINT compatible)

#### Text Input Assembly

`_extract_text_for_fingerprinting(envelope)` concatenates these components:

| # | Component | Source | Normalization |
|---|-----------|--------|---------------|
| 1 | text | `body.text` | `.strip().lower()` |
| 2 | participants | `body.participants` | sorted list (determinism) |
| 3 | location | `body.location_name` | `.strip().lower()` |
| 4 | activity_type | `body.activity_type` | `.strip().lower()` |
| 5 | event_time | `body.event_time` | hour bucket: `%Y-%m-%dT%H` |

Note: Reads from `envelope.body.*` (MW passthrough fields). NOT from top-level envelope.

#### Empty Text Handling

If concatenated text is empty:

- `simhash_hex` = `"0000000000000000"` (16 hex zeros)
- `minhash32` = `[0, 0, ..., 0]` (32 zeros, JSON string)
- Returns immediately, no computation

#### Columns Populated

| Column | Type | Value | Notes |
|--------|------|-------|-------|
| `simhash_hex` | TEXT(16) | 16-char hex string | 64-bit fingerprint |
| `minhash32` | JSONB | JSON array of 32 BIGINT | MinHash signature |
| `fingerprint_computed_at_utc` | TIMESTAMPTZ | ISO 8601 UTC | Computation timestamp |

#### What M01 Does NOT Do

- Does NOT compute `novelty_score` (deferred to P03 -- requires neighbor queries across entire corpus)
- Does NOT compute `near_duplicates` or `is_near_duplicate` (deferred to P03)
- Does NOT access st_hipp_events or any database table
- Does NOT use MW signals in any way (pure text extraction from envelope body)

#### Fallback Chain

```
body.text present?
  YES --> extract text + participants + location + activity + event_time(hour) --> fingerprint
  NO  --> "0000000000000000" simhash, [0]*32 minhash (graceful degradation)
```

No MW fallback needed. M01 is a pure function on envelope body fields.

#### Output Shape

Returns enriched envelope with:

```python
{
    **envelope,                                    # passthrough
    "simhash_hex": "a3f7...",                      # flat (backward compat)
    "minhash32": "[123, 456, ...]",                # JSON string (flat)
    "fingerprint_computed_at_utc": "2025-...Z",    # flat
    "enrichments": {
        **envelope.enrichments,
        "hippocampus_pattern_separate": {
            "simhash_hex": "a3f7...",
            "minhash32": [123, 456, ...],          # array (not JSON string)
            "fingerprint_computed_at_utc": "...",
            "module_version": "v1",
            "execution_time_ms": 0.0               # set by PipelineRunner
        }
    }
}
```

---

### 23.2 M02: hippocampus.semantic_project:v2 (stage_20)

**Pipeline Role**: CA1 Semantic Projection -- PRIMARY GAP-FILLER for ALL downstream modules
**Contract**: `k0/contracts/modules/hippocampus.semantic_project.v2.yaml`
**Source**: `k0/modules/hippocampus/semantic_project.py` (1276 lines -- largest P02 module)
**Latency Budget**: 150ms P95
**MW Dependency**: NONE for core function. MW `participant_relationships` ENHANCE KG quality when present.
**Idempotent**: Yes (except embedding_id UUID allocation)

#### What It Does

M02 is the LINCHPIN of trust-then-fill. It runs UltraBERT 3-head NER on body.text and
produces structured outputs that every downstream module can fall back to. Five phases:

1. **Entity Extraction** (NER): Extracts PERSON, ORG, GPE, DATE, TIME entities
2. **P03 NER Storage**: Packages raw UltraBERT output for P03 consolidation algorithms
3. **NER Categorization**: Splits entities into temporal/location/person buckets for M08/M07
4. **Entity Resolution**: Matches detected names against `body.participants` (fuzzy)
5. **KG Triple Generation**: Template-based knowledge graph triples with optional MW enhancement

#### Entity Extraction Fallback Chain (CRITICAL)

```
Tier 1: UltraBERT 3-head (PREFERRED)
  |  ner_family head: KINSHIP, TRADITION, ACTIVITY
  |  ner_general head: PER, ORG, LOC, DATE, TIME
  |  temporal head: temporal expressions
  |  Label mapping: KINSHIP->PERSON, PER->PERSON, LOC->GPE, DATE_REL->DATE
  |
  +--FAIL--> Tier 2: Transformer model (DEPRECATED, will be removed)
  |             spaCy pipeline with sentence-transformers
  |
  +--FAIL--> Tier 3: spaCy Large (en_core_web_lg)
  |             Standard NER: PERSON, ORG, GPE, DATE, TIME
  |             confidence = 0.7 fixed
  |
  +--FAIL--> Tier 4: spaCy Small (en_core_web_sm)
  |             Same labels, lower quality
  |             confidence = 0.6 fixed
  |
  +--FAIL--> Tier 5: Rule-based family terms (last resort)
                Regex: "mom|dad|brother|sister|grandma|..." -> PERSON
                No DATE/TIME/GPE extraction
                confidence = 0.5 fixed
```

UltraBERT is NEVER removed. If UltraBERT fails, it demotes to spaCy. spaCy fail = rule-based.
The chain ALWAYS produces some output. Empty result only on empty input text.

#### P03 NER Storage (`_extract_ner_for_p03_storage`)

Packages raw UltraBERT 3-head output into columns that P03 R4 enrichers consume:

| Column | Type | Source | Description |
|--------|------|--------|-------------|
| `ner_entities_json` | JSONB | UltraBERT ner_family + ner_general | `{"ner_family": [...], "ner_general": [...]}` |
| `temporal_json` | JSONB | UltraBERT temporal head | `{"temporal": [...]}` |
| `intent_category` | TEXT | UltraBERT intent head | DEPRECATED (zombie column) |
| `ingress_category` | TEXT | UltraBERT ingress head | DEPRECATED (zombie column) |
| `ultrabert_version` | TEXT | Model metadata | e.g., "ultrabert-familyos-v2.1" |
| `extracted_relations_json` | JSONB | UltraBERT relation head | `[{subject, predicate, object, confidence}]` |
| `safety_familyos_band` | TEXT | UltraBERT safety head | GREEN / AMBER / RED / CRISIS |
| `safety_familyos_subcategory` | TEXT | UltraBERT safety head | Subcategory detail |
| `nli_label` | TEXT | UltraBERT NLI head | entailment / contradiction / neutral |
| `nli_confidence` | FLOAT | UltraBERT NLI head | 0.0-1.0 |
| `sentiment_confidence` | FLOAT | UltraBERT sentiment head | 0.0-1.0 (separate from M04 affect) |

Total: 11 columns for P03 consumption

#### NER Categorization for Downstream Modules

`_categorize_ner_entities(entities)` splits all extracted entities into three lists:

| Output Field | Entity Types Included | Consumer | Purpose |
|---|---|---|---|
| `ner_temporal_entities` | DATE, TIME, TEMPORAL | M08 (temporal_profile) | Fallback when MW `resolved_epoch_ms` missing |
| `ner_loc_entities` | GPE, LOC, FAC, LOCATION | M08, M13 (spatial) | Fallback when MW `location_name` missing |
| `ner_per_entities` | PERSON, PER, KINSHIP | M07 (social) | Fallback when MW `participant_relationships` missing |

Each entry: `{text, type, confidence, start, end, source}`

#### Entity Resolution (`_resolve_entities`)

Three sub-resolvers:

- `_resolve_person(entities, participants)`: Fuzzy-match NER PERSON against `body.participants`
- `_resolve_place(entities, envelope_place)`: Match NER LOC/GPE against `body.location_name`
- `_resolve_temporal(entities)`: Pass through temporal entities (no resolution needed)

Result: `entities_json` -- JSON array of canonical entity IDs (e.g., `["person_mom", "place_olive_garden"]`)

#### KG Triple Generation

`extract_kg_triples()`: Template-based rule engine:

- activity_type maps to predicate (e.g., MEAL -> "ate_at", SPORTS -> "played_at")
- Participants become subjects, locations become objects
- Max 10 triples per event (configurable `max_triples_per_event`)
- Format: `[[subject, predicate, object], ...]`

**MW Enhancement** (`_enhance_kg_triples_with_mw_relationships`):

```
WITHOUT MW: ["person_mom", "mentioned_with", "person_actor"]
WITH MW:    ["person_mom", "PARENT_OF", "person_actor"]
```

- Reads `body.participant_relationships` (list of `{person, relationship_type, confidence}`)
- Replaces generic predicates (`mentioned_with`, `interacted_with`, `mentions`) with typed ones
- Failure: silently falls back to original triples (MW_RELATIONSHIPS_MALFORMED policy: ignore)

#### Embedding Allocation

- Generates `embedding_id = uuid4()` for P08 vector generation
- Does NOT generate the actual embedding vector -- that happens in P08 via st_embedding_queue
- embedding_id is a reference key linking st_hipp_events to st_vec

#### All Columns Populated by M02

| # | Column | Type | Always? | Notes |
|---|--------|------|---------|-------|
| 1 | `embedding_id` | UUID | Yes | Reference for P08 vector generation |
| 2 | `entities_json` | JSONB | Yes | Resolved canonical entity IDs |
| 3 | `kg_triples_json` | JSONB | Yes | KG triples (quality varies with MW) |
| 4 | `semantic_projected_at_utc` | TIMESTAMPTZ | Yes | Module completion timestamp |
| 5 | `ner_entities_json` | JSONB | Yes | Raw UltraBERT 3-head NER for P03 |
| 6 | `temporal_json` | JSONB | Yes | UltraBERT temporal entities for P03 |
| 7 | `intent_category` | TEXT | Yes | DEPRECATED zombie (still written) |
| 8 | `ingress_category` | TEXT | Yes | DEPRECATED zombie (still written) |
| 9 | `ultrabert_version` | TEXT | Yes | Model version string |
| 10 | `extracted_relations_json` | JSONB | Yes | UltraBERT relation head output |
| 11 | `safety_familyos_band` | TEXT | Yes | GREEN/AMBER/RED/CRISIS |
| 12 | `safety_familyos_subcategory` | TEXT | Yes | Safety detail |
| 13 | `nli_label` | TEXT | Yes | entailment/contradiction/neutral |
| 14 | `nli_confidence` | FLOAT | Yes | 0.0-1.0 |
| 15 | `sentiment_confidence` | FLOAT | Yes | 0.0-1.0 |

Plus 3 structured lists passed in enrichments (not stored directly, consumed by M08/M07/M13):

- `ner_temporal_entities` (list of dicts)
- `ner_loc_entities` (list of dicts)
- `ner_per_entities` (list of dicts)

**Total**: 15 st_hipp_events columns + 3 enrichment lists for downstream modules

#### Empty Text Handling

If `body.text` is empty/null:

- `embedding_id` = fresh UUID (still allocated)
- `entities_json` = `"[]"`
- `kg_triples_json` = `"[]"`
- All NER fields = empty arrays/null
- Returns immediately, no NER/KG computation

#### Output Shape

Returns enriched envelope with:

```python
{
    **envelope,                                 # passthrough
    # Flat fields (backward compat):
    "embedding_id": "uuid...",
    "entities_json": "[...]",
    "kg_triples_json": "[[...], ...]",
    "semantic_projected_at_utc": "2025-...Z",
    "ner_entities_json": "{ner_family: [...], ner_general: [...]}",
    "temporal_json": "{temporal: [...]}",
    "intent_category": "...",                   # zombie, still written
    "ingress_category": "...",                  # zombie, still written
    "ultrabert_version": "...",
    "extracted_relations_json": "[...]",
    "safety_familyos_band": "GREEN",
    "safety_familyos_subcategory": "...",
    "nli_label": "neutral",
    "nli_confidence": 0.85,
    "sentiment_confidence": 0.72,
    # Structured NER for downstream fallback:
    "ner_temporal_entities": [{text, type, confidence, start, end, source}, ...],
    "ner_loc_entities": [...],
    "ner_per_entities": [...],
    # Nested enrichments:
    "enrichments": {
        **envelope.enrichments,
        "semantic_projector": {
            "embedding_id": "...",
            "entities_json": "...",
            "kg_triples_json": "...",
            "semantic_projected_at_utc": "...",
            "module_version": "v2",
            "execution_time_ms": 0.0,
            "ner_entities_json": "...",
            "temporal_json": "...",
            "extracted_relations_json": "...",
            "safety_familyos_band": "...",
            "safety_familyos_subcategory": "...",
            "nli_label": "...",
            "nli_confidence": 0.85,
            "sentiment_confidence": 0.72,
            "ner_temporal_entities": [...],
            "ner_loc_entities": [...],
            "ner_per_entities": [...]
        }
    }
}
```

#### Architectural Significance

M02 is the single most important P02 module because:

1. It is the PRIMARY GAP-FILLER -- every other module can fall back to M02 output
2. It ALWAYS runs full NER+embedding regardless of MW availability
3. It produces the structured NER buckets that M08, M07, M13 consume as fallback
4. It allocates embedding_id that links st_hipp_events to st_vec (P08)
5. It packages raw UltraBERT output for P03 consolidation algorithms
6. It is the only module that writes to st_kg_edges (via KG triple generation)

If M02 fails, the entire P02 pipeline effectively fails (no fallback for the fallback provider)
---

### 23.3 M22: embedding.extract_from_cache:v1 (stage_22)

**Pipeline Role**: Extract 768-dim UltraBERT embedding from single-pass cache
**Contract**: `k0/contracts/modules/embedding.extract_from_cache.v1.yaml` (DEPRECATED, v2 exists)
**Source**: `k0/modules/embedding/extract_from_cache.py` (165 lines)
**Latency Budget**: 1ms P95 (cache read only, no GPU inference)
**MW Dependency**: NONE
**Idempotent**: Yes (except embedding_id UUID allocation)

#### What It Does

M22 is a lightweight cache-reader. It does NOT run UltraBERT inference. It reads the embedding
vector from UltraBERT's single-pass cache that was already warmed by M02 (semantic_project),
M04 (affect.analyze), and M10 (ingress_classify). All three modules share ONE cached forward
pass controlled by `K0_ULTRABERT_SINGLE_PASS=1`.

Architecture (ADR-K003):

```
M02 calls UltraBERT (NER)         --\
M04 calls UltraBERT (affect)       --> Single cached forward pass
M10 calls UltraBERT (intent)      --/
         |
         v
M22 reads .embedding from cache   --> <1ms, no inference
```

#### Fallback Chain

```
1. Cache read: _get_full_analysis_result(text) -> result.embedding
   |
   +-- HIT (~95%): Return embedding immediately (<1ms)
   |
   +-- MISS: fallback_to_direct_call=True?
       |
       +-- YES: Call get_embedding(text) directly (~30ms penalty)
       |        (rare: cache eviction, unusual stage ordering, SINGLE_PASS=0)
       |
       +-- NO: Return source="failed"
              embedding_status=PENDING in st_hipp_events
              P08 M25 (backfill) retries later
```

Cache misses are rare (<5%). They happen when:

- M02/M04/M10 haven't run yet (unusual stage ordering)
- Cache evicted (TTL expired or LRU eviction, TTL=30s)
- `K0_ULTRABERT_SINGLE_PASS=0` (single-pass disabled)

#### Columns Populated

M22 does NOT directly write st_hipp_events columns. It produces an output dict under the
`extract_from_cache` key that M13 (builder) or M23 (embedding_write) consumes:

| Field | Type | Value | Notes |
|-------|------|-------|-------|
| `embedding` | list[float] | 768-dim vector | None if failed |
| `embedding_id` | UUID | Fresh uuid4 | None if failed |
| `vector_dim` | int | 768 | Always 768 |
| `model_id` | str | "ultrabert_v2.1.0" | Model version |
| `source` | str | cache_hit / direct_call / failed / no_text | Provenance |

These map to st_vec columns (NOT st_hipp_events):

- `st_vec.embedding_id` = embedding_id
- `st_vec.vector` = embedding (VECTOR(768))
- `st_vec.model_id` = model_id

The only st_hipp_events impact:

- `embedding_status` = "READY" if source in (cache_hit, direct_call), "PENDING" if failed

#### Empty Text Handling

If `body.text` is empty/null:

- Returns `source="no_text"`, `embedding=None`, `embedding_id=None`
- No cache lookup attempted

#### Output Shape

```python
{
    "extract_from_cache": {
        "embedding": [0.123, -0.456, ...],   # 768 floats or None
        "embedding_id": "uuid...",            # or None
        "vector_dim": 768,
        "model_id": "ultrabert_v2.1.0",
        "source": "cache_hit"                 # provenance
    }
}
```

Note: M22 wraps its output under `extract_from_cache` key (not flat like M01/M02).
This is consumed by M23 (builders.embedding_write) for st_vec INSERT.

#### Benefits vs Legacy P08 Async Pattern

| Metric | Legacy (P08 MiniLM) | New (M22 cache) |
|--------|---------------------|------------------|
| Latency | ~250ms async | <1ms sync |
| Model | MiniLM 384-dim | UltraBERT 768-dim |
| Memory | +250MB (separate model) | 0 (shared cache) |
| P03 availability | PENDING (async) | Immediate |
| Quality | Lower (384-dim) | Higher (768-dim) |

#### What M22 Does NOT Do

- Does NOT run UltraBERT inference (cache read only)
- Does NOT write to st_hipp_events (writes to st_vec via M23)
- Does NOT compute entity/NER/sentiment (that's M02/M04)
- Does NOT have any MW dependency

---

### 23.4 M04: affect.analyze:v2 (stage_30)

**Pipeline Role**: Amygdala / Affect System -- Emotional content and risk analysis
**Contract**: `k0/contracts/modules/affect.analyze.v2.yaml`
**Source**: `k0/modules/affect/analyze.py` (1516 lines -- second largest P02 module)
**Latency Budget**: 70ms P95 (worst-case UltraBERT fallback path)
**MW Dependency**: YES -- TRUST-THEN-FILL module
**Idempotent**: Yes

#### What It Does

M04 classifies the emotional content of an event: valence (positive/negative), arousal
(calm/excited), dominance (3rd VAD dimension), dominant emotions (up to 5 labels from
44-class taxonomy), and affect band (GREEN/AMBER/RED risk level).

**Critical invariant**: Safety heads (clinical_safety_risk, safety_familyos_band) ALWAYS
run on body.text regardless of which tier produces affect values. Content-level safety
classification is safety-critical -- never trust LLM alone for safety.

#### Trust-Then-Fill Waterfall (CRITICAL)

```
TIER 0: MW v2 Affect Passthrough (~85%, <10ms)
  |  body.affect.valence present AND valid float in [0.0, 1.0]?
  |  YES --> Passthrough valence, arousal, dominance, dominant_emotions from MW
  |          Run safety heads ONLY on body.text (~10ms)
  |          affect_source = "mw_v2"
  |          confidence = 0.9 (MW sees full 2000-token conversation context)
  |
  +--MW ABSENT/MALFORMED--> TIER 1: Full UltraBERT Inference (~10%, <70ms)
  |  UltraBERT sentiment + emotion + safety on body.text
  |  Emotion→valence/arousal via Russell's Circumplex (44 emotion map)
  |  affect_source = "ultrabert"
  |  Note: UltraBERT sees only 15-30 token text body (lower quality than MW)
  |
  +--ULTRABERT FAILS--> TIER 2: VADER Fallback (~5%, <20ms)
  |  VADER compound score mapped to valence: (compound+1)/2 = [0,1]
  |  VADER arousal: pos + neg proportions
  |  Domain lexicon adjustments (quality_time +0.15, meltdown -0.20, etc.)
  |  Emoji valence adjustments (max 30% influence)
  |  affect_source = "vader"
  |  Note: No dominance from VADER (null)
  |
  +--VADER FAILS--> TIER 3: Safe Defaults (<1%)
     valence = 0.5, arousal = 0.3, dominance = null
     dominant_emotions = ("neutral",)
     affect_band = "GREEN"
     affect_source = "default"
     confidence = 0.2
```

#### MW Affect Validation (`_extract_mw_affect`)

MW affect is accepted ONLY if:

1. `body.affect` exists and is a dict
2. `body.affect.valence` is a valid float in [0.0, 1.0]

If malformed → `MW_AFFECT_MALFORMED` → falls to Tier 1.

Validated fields:

| Field | Required | Default | Notes |
|-------|----------|---------|-------|
| `body.affect.valence` | YES | -- | Must be float [0.0, 1.0] |
| `body.affect.arousal` | no | 0.5 | Clamped to [0.0, 1.0] |
| `body.affect.dominance` | no | null | New in v2, 3rd VAD dimension |
| `body.affect.dominant_emotions` | no | circumplex-derived | Max 5 labels |

#### Safety Heads (ALWAYS RUN)

`_run_safety_heads_only(text)` runs independently of the affect tier:

```
Safety Fallback Chain:
1. UltraBERT check_safety(text)  --> safety_familyos: GREEN/AMBER/RED/CRISIS
   |
   +--FAIL--> 2. clinical_safety.assess_safety(text)  --> risk_detected, severity
   |
   +--FAIL--> 3. Keyword-based safety (SAFETY_KEYWORDS tuple)
                  "suicide", "kill myself", "self harm", "hurt myself",
                  "end it all", "abuse", "hitting", "screaming at"
```

Safety override logic (applied AFTER affect tier completes):

- If safety_severity in (CRITICAL, HIGH) → force `affect_band = "RED"`
- If safety_severity == MEDIUM and affect_band == GREEN → upgrade to AMBER
- Safety detection appends reason to `band_reasons`

#### VADER Tier-0 Classification Details

VADER is the Tier-2 fallback but also the internal engine for Tier-0 (when MW absent + UltraBERT
fails). `tier0_classify()` algorithm:

1. **Input truncation**: Max 10,000 chars (prevent DoS)
2. **Clinical safety check**: `check_clinical_safety(text)` → if HIGH/CRITICAL → immediate RED
3. **Safety keywords**: Force RED for "suicide", "kill myself", etc.
4. **Complexity check** (`should_fallback_to_tier1`):
   - Text > 50 words → complex
   - Mixed emotion keywords ("bittersweet", "conflicted") → complex
   - Sarcasm indicators ("yeah right", "sure buddy") → complex
   - Complex negation regex (double negatives: "not unhappy") → complex
   - If complex and `allow_low_confidence=False` → return None (trigger Tier 1)
5. **VADER scores**: `polarity_scores(text)` → compound, pos, neg, neu
6. **Valence mapping**: `(compound + 1) / 2` → [0, 1] scale
7. **Arousal mapping**: `pos + neg` → emotional intensity
8. **Domain lexicon**: FamilyOS-specific phrase adjustments:
   - "quality time" +0.15, "milestone" +0.15, "big day" +0.10
   - "meltdown" -0.20, "tantrum" -0.15, "exhausted" -0.10
9. **Emoji adjustments**: Weighted blend (max 30% influence)
10. **Circumplex mapping**: Russell (1980) quadrants → emotion tags
11. **Affect band**: GREEN (valence >= 0.5), AMBER (>= 0.4, low arousal), RED (< 0.25)
12. **Confidence scoring**: Based on valence distance from neutral, arousal, complexity

#### UltraBERT Classification Details

`ultrabert_classify(text)` is Tier-1 (used when MW absent):

1. Call `analyze_affect(text)` from UltraBERT adapter
2. Get `dominant_emotions` (top emotions from 44-class taxonomy)
3. Map each emotion to valence/arousal via psychologically-grounded lookup tables:
   - Valence map: 44 emotions → [0.0, 1.0] (based on Warriner et al. 2013 ANEW)
   - Arousal map: 44 emotions → [0.0, 1.0] (based on Bradley & Lang 1999 IAPS)
   - Family-specific entries: nostalgia=0.65, protectiveness=0.70, togetherness=0.80,
     parental_pride=0.90, parental_guilt=0.25, worry=0.35, bittersweet=0.50
4. Average valence/arousal across detected emotions
5. Apply emotional complexity factor (mixed emotions → moderate values)
6. Return with tier="ULTRABERT", affect_source="ultrabert"

Note: UltraBERT does NOT produce dominance (3rd VAD dimension). Only MW provides dominance.

#### All Columns Populated by M04

| # | Column | Type | Always? | Source | Notes |
|---|--------|------|---------|--------|-------|
| 1 | `affect_valence` | FLOAT | Yes | MW / UltraBERT / VADER / 0.5 | 0.0-1.0 |
| 2 | `affect_arousal` | FLOAT | Yes | MW / UltraBERT / VADER / 0.3 | 0.0-1.0 |
| 3 | `affect_dominance` | FLOAT | Sometimes | MW only | null from UltraBERT/VADER/default |
| 4 | `dominant_emotions` | JSONB | Yes | MW / UltraBERT / circumplex / [] | Max 5 labels |
| 5 | `affect_band` | TEXT | Yes | Derived from valence + safety | GREEN/AMBER/RED |
| 6 | `band_reasons` | JSONB | Yes | Classification reasons | Array of reason codes |
| 7 | `model_version` | TEXT | Yes | Tier identifier | mw_v2_passthrough / ultrabert / vader / safe_defaults_v2.0 |
| 8 | `affect_tier` | TEXT | Yes | Tier that ran | MW_V2 / ULTRABERT / TIER_0 / FALLBACK |
| 9 | `confidence` | FLOAT | Yes | Varies by tier | 0.9 MW, varies UltraBERT/VADER, 0.2 default |
| 10 | `affect_source` | TEXT | Yes | Provenance | mw_v2 / ultrabert / vader / default |
| 11 | `raw_vader_compound` | FLOAT | Sometimes | VADER only | null if MW/UltraBERT path |
| 12 | `raw_vader_pos` | FLOAT | Sometimes | VADER only | null if MW/UltraBERT path |
| 13 | `raw_vader_neg` | FLOAT | Sometimes | VADER only | null if MW/UltraBERT path |
| 14 | `raw_vader_neu` | FLOAT | Sometimes | VADER only | null if MW/UltraBERT path |
| 15 | `clinical_safety_risk` | BOOL | Yes | Safety heads (ALWAYS) | Content-level risk flag |
| 16 | `clinical_safety_severity` | TEXT | Yes | Safety heads | NONE/LOW/MEDIUM/HIGH/CRITICAL |
| 17 | `clinical_safety_summary` | TEXT | Sometimes | Safety heads | Human-readable risk summary |

**Total**: 17 columns populated by M04

#### What M04 Does NOT Do

- Does NOT compute sentiment_confidence (that's M02 via UltraBERT sentiment head)
- Does NOT compute safety_familyos_band for st_hipp_events (M02 stores that from UltraBERT)
  - M04 computes safety_band for its own affect override logic, stored in `affect_band`
- Does NOT generate embeddings (that's M02+M22)
- Does NOT modify NER outputs (that's M02)

#### Output Shape

```python
{
    **envelope,
    # Flat fields (backward compat):
    "affect_valence": 0.72,
    "affect_arousal": 0.45,
    "affect_dominance": 0.6,              # null if not MW path
    "dominant_emotions": ["joy", "contentment"],
    "affect_band": "GREEN",
    "band_reasons": ["positive_affect"],
    "model_version": "mw_v2_passthrough",
    "affect_tier": "MW_V2",
    "confidence": 0.9,
    "affect_source": "mw_v2",
    "raw_vader_compound": null,            # null if MW/UltraBERT path
    "raw_vader_pos": null,
    "raw_vader_neg": null,
    "raw_vader_neu": null,
    "clinical_safety_risk": false,
    "clinical_safety_severity": "NONE",
    "clinical_safety_summary": null,
    # Nested enrichments:
    "enrichments": {
        **envelope.enrichments,
        "affect_analyzer": {
            "valence": 0.72,
            "arousal": 0.45,
            "dominance": 0.6,
            "dominant_emotions": ["joy", "contentment"],
            "band": "GREEN",
            "band_reasons": ["positive_affect"],
            "model_version": "mw_v2_passthrough",
            "tier": "MW_V2",
            "confidence": 0.9,
            "affect_source": "mw_v2",
            "raw_vader_compound": null,
            "raw_vader_pos": null,
            "raw_vader_neg": null,
            "raw_vader_neu": null,
            "clinical_safety_risk": false,
            "clinical_safety_severity": "NONE",
            "clinical_safety_summary": null,
            "module_version": "v2",
            "execution_time_ms": 0.0
        }
    }
}
```

#### Architectural Significance

M04 is the FIRST trust-then-fill module in the pipeline (stage_30). It establishes the pattern:

1. Check MW signal → if valid, passthrough + safety heads only (fast path)
2. MW absent/malformed → full inference (UltraBERT fallback)
3. Inference fails → lexicon-based fallback (VADER)
4. All fail → safe defaults (never crash)

Safety heads ALWAYS run independently of the affect tier. This is a safety-critical invariant:
the LLM (MW) should never be the sole arbiter of safety classification. UltraBERT safety
heads provide content-level validation at 96.2% accuracy.

M04's affect_valence and affect_band are consumed by M06 (salience.score) downstream.
The clinical_safety_risk flag can boost salience for safety-relevant events.

---

### 23.5 M05: space.resolve_visibility:v1 (stage_31)

**Pipeline Role**: Prefrontal Context / ACL System -- Space ownership and visibility resolution
**Contract**: `k0/contracts/modules/space.resolve_visibility.v1.yaml`
**Source**: `k0/modules/space/resolve_visibility.py` (526 lines)
**Latency Budget**: 3ms P95 (cache hit), 10ms P99 (cold cache)
**MW Dependency**: NONE
**Idempotent**: Yes

#### What It Does

M05 resolves WHO can see an event based on space ownership policies. It implements
Lampson-style ACL intersection: the final `visible_to` list is ALWAYS the intersection
of the envelope's policy and the space's allowed viewers. Visibility is NEVER expanded
beyond what the envelope policy allows (security guarantee).

5-step algorithm:

1. **Space metadata lookup** (cache-first, LRU 1000 entries, 5-min TTL)
2. **Author role determination**: OWNER / CO_OWNER / GUEST
3. **Visibility intersection**: `policy_visible_to ∩ space_allowed_viewers`
4. **Scope classification**: OWNER_ONLY / SPACE_DEFAULT / HOUSEHOLD_ALL / CUSTOM_SUBSET / EXTERNAL_SHARE
5. **Build output**: SpaceResolution dataclass

#### Inputs

| Field | Source | Required | Notes |
|-------|--------|----------|-------|
| `actor` | envelope.actor | YES | Person who created the event |
| `space_id` | envelope.space_id | YES | Space where event occurred |
| `policy_stamp.visible_to` | envelope.policy_stamp | NO | Policy-allowed viewers (default: []) |

#### Fail-Secure Behavior

If space metadata lookup fails (cache miss + DB error, or space not found):

- `owner_id` = actor_id (assume author owns)
- `co_owners_json` = `"[]"`
- `author_role` = `"OWNER"`
- `visible_to_json` = `[actor_id]` (AUTHOR-ONLY -- most restrictive)
- `visibility_scope` = `"OWNER_ONLY"`

This is the security guarantee: on failure, default to MOST RESTRICTIVE visibility.

#### Visibility Intersection Algorithm

```
visible_to = sorted(set(policy_visible_to) & set(space_allowed_viewers))
```

- Security property: `len(result) <= len(policy_visible_to)` (NEVER expand)
- Empty intersection → falls back to `[actor_id]` (author-only)
- O(n + m) complexity where n, m are list sizes (typically <20 items)

#### Scope Classification (Analytics Only, NOT ACL)

| Scope | Condition |
|-------|-----------|
| `OWNER_ONLY` | Only 1 person in visible_to |
| `SPACE_DEFAULT` | Exactly {owner + all co_owners} |
| `EXTERNAL_SHARE` | Any person_id starts with `person_external_` |
| `HOUSEHOLD_ALL` | >= 4 people (heuristic) |
| `CUSTOM_SUBSET` | Everything else |

#### Columns Populated

| # | Column | Type | Always? | Notes |
|---|--------|------|---------|-------|
| 1 | `owner_id` | TEXT | Yes | Space owner person_id |
| 2 | `co_owners_json` | JSONB | Yes | JSON array of co-owner person_ids |
| 3 | `author_role` | TEXT | Yes | OWNER / CO_OWNER / GUEST |
| 4 | `visible_to_json` | JSONB | Yes | Authoritative ACL list (sorted) |
| 5 | `visibility_scope` | TEXT | Yes | Analytics classification |
| 6 | `space_policy_version` | TEXT | Yes | Policy version string |
| 7 | `space_resolved_at_utc` | TIMESTAMPTZ | Yes | Resolution timestamp |

**Total**: 7 columns

#### Fallback Chain

```
Space metadata in cache?
  YES (>95%) --> resolve roles + compute intersection (<3ms)
  NO  --> query DB for space metadata
          |
          +--FOUND--> cache + resolve (<10ms)
          |
          +--NOT FOUND--> fail-secure: author-only visibility
```

No MW dependency. No fallback tiers. Pure cache-first lookup + set intersection.

#### What M05 Does NOT Do

- Does NOT modify any data (pure read + compute)
- Does NOT write to st_kg_edges or any persistent store
- Does NOT use MW signals
- Does NOT use M02 NER output
- Does NOT enforce ACLs at query time (that's done by query layer)

---

### 23.6 M07: social.family_graph_resolve:v2 (stage_32)

**Pipeline Role**: Social Context Attribution -- Family graph and relationship resolution
**Contract**: `k0/contracts/modules/social.family_graph_resolve.v2.yaml`
**Source**: `k0/modules/social/family_graph_resolve.py` (1125 lines)
**Latency Budget**: 3ms P95 (MW fast path), 12ms P95 (fallback)
**MW Dependency**: YES -- TRUST-THEN-FILL module
**Idempotent**: Yes (except st_kg_edges write side effect)

#### What It Does

M07 resolves WHO is involved in an event and WHAT their relationships are to the actor.
It determines social_context (solo/nuclear_family/extended_family/friends/colleagues),
boolean family flags (has_partner_present, has_parent_present), participant roles, and
social intimacy level.

**Critical v1 bug fix**: v1 always returned `social_context="friends"` because st_kg_edges
was empty. MW v2 provides typed relationships that immediately fix this.

#### Trust-Then-Fill Waterfall (CRITICAL)

```
TIER 0: MW participant_relationships (~85%, <3ms)
  |  body.participant_relationships present AND valid?
  |  Supports 2 formats:
  |    Object map (canonical): {person_id: {type, target, confidence}}
  |    List format (legacy):   [{person, relationship_type, confidence}]
  |  YES --> Map relationships to roles + derive social_context
  |          Write relationships to st_kg_edges (progressive KG seeding, non-blocking)
  |          social_source = "mw_v2"
  |
  +--MW ABSENT/MALFORMED--> TIER 1: st_kg_edges READ (~8%)
  |  Query st_relationships via syscalls (cached, 5-min TTL)
  |  May have data from previous MW writes (progressive seeding)
  |  Map relationships to participant_roles
  |  social_source = "kg_edges"
  |
  +--KG EMPTY--> TIER 2: NER + Name-Pattern Heuristics (~5%)
  |  Use M02's ner_per_entities (person entities from UltraBERT)
  |  _infer_from_name_pattern(): regex-based role inference
  |    "mom/dad/mother/father" → PARENT
  |    "wife/husband/spouse" → SPOUSE
  |    "brother/sister" → SIBLING
  |    etc., with confidence >= 0.5 threshold
  |  social_source = "ner_heuristic"
  |
  +--NO INFERENCE POSSIBLE--> TIER 3: Defaults (~2%)
     Multiple participants: social_context = "unknown", intimacy = "LOW"
     Solo: social_context = "solo", intimacy = "LOW"
     social_source = "default"
```

#### Social Context Derivation (MW Path)

When MW relationships are present, social_context is derived by PRIORITY:

| Relationship Type | Maps To | Priority |
|---|---|---|
| PARENT_OF, CHILD_OF, SPOUSE_OF, SIBLING_OF, CAREGIVER_OF | nuclear_family | 7 (highest) |
| GRANDPARENT_OF, AUNT_UNCLE_OF, COUSIN_OF | extended_family | 6 |
| FRIEND_OF | friends | 5 |
| COLLEAGUE_OF | colleagues | 4 |

When multiple participants have different types, **highest priority wins**.

#### Family Boolean Flags

| Flag | Condition |
|------|-----------|
| `has_partner_present` | Any participant has relationship_type == SPOUSE_OF |
| `has_parent_present` | Any participant has PARENT_OF or CHILD_OF |

#### Social Intimacy Scoring

| Social Context | Intimacy |
|---|---|
| nuclear_family | HIGH |
| extended_family, friends | MED |
| colleagues, community, unknown, solo | LOW |

#### st_kg_edges Progressive Seeding (Side Effect)

When Tier 0 runs (MW relationships present), M07 writes relationships to st_kg_edges:

- Non-blocking: if write fails, log and continue (social output still valid)
- Only writes relationships with confidence >= threshold (default 0.5)
- Source tagged as `"mw_v2"` for provenance
- Uses `syscalls.kg_edges_upsert()` (graceful if syscall not yet available)

This progressively seeds the KG so Tier 1 has data for future events.

#### Participant Role Mapping

9 supported relationship types mapped to roles:

| MW Relationship | Participant Role | Notes |
|---|---|---|
| SPOUSE_OF | SPOUSE | |
| PARENT_OF | CHILD | Actor is parent → participant is child |
| CHILD_OF | PARENT | Actor is child → participant is parent |
| SIBLING_OF | SIBLING | |
| CAREGIVER_OF | CAREGIVER | |
| GRANDPARENT_OF | GRANDCHILD | |
| GRANDCHILD_OF | GRANDPARENT | |
| FRIEND_OF | FRIEND | |
| COLLEAGUE_OF | COLLEAGUE | |

#### Columns Populated

| # | Column | Type | Always? | Notes |
|---|--------|------|---------|-------|
| 1 | `num_participants` | INT | Yes | Count of all participants |
| 2 | `participant_roles_json` | JSONB | Yes | `{person_id: role}` mapping |
| 3 | `has_partner_present` | BOOL | Yes | Spouse/partner detected |
| 4 | `has_parent_present` | BOOL | Yes | Parent/child relationship detected |
| 5 | `is_solo_event` | BOOL | Yes | True if <= 1 participant |
| 6 | `social_context` | TEXT | Yes | solo/nuclear_family/extended_family/friends/colleagues/unknown |
| 7 | `social_intimacy` | TEXT | Yes | HIGH/MED/LOW |
| 8 | `social_resolved_at_utc` | TIMESTAMPTZ | Yes | Resolution timestamp |
| 9 | `participant_relationships_json` | JSONB | Yes | MW passthrough (v2), empty [] if non-MW path |
| 10 | `social_source` | TEXT | Yes | mw_v2/kg_edges/ner_heuristic/default |

**Total**: 10 columns

#### Solo Event Handling

Detected when:

- `body.participants` is empty or missing
- Only actor_id in participants list

Returns: social_context="solo", is_solo_event=true, social_intimacy="LOW", all flags false

#### Error Handling

On any exception during tier 1/2/3 processing:

- Falls back to default values (social_context from config, intimacy="LOW")
- Returns all participants with role="OTHER"
- Logs error, does NOT crash the pipeline

---

### 23.7 M08: context.temporal_profile:v2 (stage_33)

**Pipeline Role**: Temporal and Circadian Profiler -- Single source of truth for ALL temporal enrichment
**Contract**: `k0/contracts/modules/context.temporal_profile.v2.yaml`
**Source**: `k0/modules/context/temporal_profile.py` (1109 lines)
**Latency Budget**: 4ms P95 (fast path), 6ms P95 (NER fallback)
**MW Dependency**: YES -- TRUST-THEN-FILL module (temporal chain + spatial chain)
**Idempotent**: Yes

#### What It Does

M08 is the SINGLE AUTHORITY for temporal enrichment. No other P02 module should compute or
mutate temporal fields. It produces exactly 20 columns (14 temporal + 3 spatial + 3 metadata)
covering:

- Canonical event time resolution (via temporal fallback chain)
- UTC→local timezone conversion (cached per tenant)
- Temporal bucket classification (morning/afternoon/evening/night)
- Write lag computation and QoS band classification
- Backdated event detection
- MW temporal signal passthrough (mentioned_time, resolved_epoch, orientation)
- Spatial fallback chain (location_name, location_type, location_source)

#### Temporal Fallback Chain (THE MOST CRITICAL CHAIN IN P02)

event_time_utc is NEVER null. This chain guarantees a value.

```
PRIORITY 1: MW body.temporal.resolved_epoch_ms (K1-resolved, highest fidelity)
  |  K1 LLM resolved "yesterday evening" to epoch milliseconds
  |  Handles ms/s normalization (>1e12 = ms, divide by 1000)
  |  Clamp future timestamps beyond tolerance window
  |  temporal_source = "mw_resolved"
  |
  +--MISSING--> PRIORITY 2: M02 NER temporal + regex resolution
  |  Reads enrichments.semantic_projector.ner_temporal_entities
  |  Takes FIRST entity, applies regex patterns:
  |    "yesterday evening" → now - 24h + 19:00
  |    "yesterday morning" → now - 24h + 09:00
  |    "last week" → now - 7 days
  |    "two days ago" → now - 2 days
  |    "this morning" → today 09:00
  |    "earlier today" → now - 4h
  |    "a few hours ago" → now - 3h
  |    "last month" → now - 30 days
  |    "over the weekend" → previous Saturday
  |    "noon" → today 12:00
  |    ... (22 total patterns)
  |  NOTE: HEURISTIC fallback -- lower fidelity than K1's LLM resolution
  |  temporal_source = "ner_temporal"
  |
  +--NO MATCH--> PRIORITY 3: body.event_time (ISO 8601 or Unix seconds/ms/us)
  |  Parse raw timestamp: ISO string, Unix int/float
  |  Auto-detect unit: >1e15=microseconds, >1e12=milliseconds, else seconds
  |  temporal_source = "event_time"
  |
  +--MISSING--> PRIORITY 4: envelope.ts (Bridge timestamp -- ALWAYS PRESENT)
  |  Hard backstop from Bridge serialization
  |  temporal_source = "envelope_ts"
  |
  +--MISSING--> PRIORITY 5: now() (Ultimate fallback -- should NEVER reach here)
     temporal_source = "now"
```

#### Spatial Fallback Chain

M08 also resolves location via `resolve_location()`:

```
PRIORITY 1: MW body.location_name + body.location_type
  |  LLM-extracted location (highest quality)
  |  location_source = "mw_location"
  |
  +--MISSING--> PRIORITY 2: M02 NER LOC entities
  |  From enrichments.semantic_projector.ner_loc_entities
  |  Takes FIRST entity text
  |  Classifies type via regex (restaurant/park/school/medical/etc.)
  |  location_source = "ner_location"
  |
  +--EMPTY--> PRIORITY 3: Text heuristic
  |  Regex: "at|in|near|from|to|visited" + Capitalized_Words
  |  e.g., "dinner at Olive Garden" → "Olive Garden"
  |  Filters false positives (pronouns, day names, month names)
  |  location_source = "text_heuristic"
  |
  +--NO MATCH--> PRIORITY 4: null (acceptable, not all events have location)
     location_source = "none"
```

Location type classification (10 categories via regex patterns):
restaurant, park, school, medical, worship, retail, workplace, home, fitness, transit

#### Temporal Bucket Classification

After resolving event_time_utc, M08 converts to tenant local timezone and classifies:

| Dimension | Algorithm | Values |
|---|---|---|
| `local_date` | dt_local.strftime("%Y-%m-%d") | ISO date |
| `local_time` | dt_local.strftime("%H:%M:%S") | ISO time |
| `day_of_week` | dt_local.strftime("%A") | Monday-Sunday |
| `is_weekend` | weekday() in (5, 6) | true/false |
| `time_of_day_bucket` | Time range check | morning (06-12), afternoon (12-17), evening (17-22), night (22-06) |
| `circadian_slot` | ALWAYS None | Removed: culturally biased. Should be learned from user behavior. |

#### Write Lag and QoS Classification

```python
write_lag_ms = (write_time_utc - event_time_utc) * 1000
```

| QoS Band | Condition | Signal Quality |
|---|---|---|
| `realtime` | write_lag < 5 seconds | High (live capture) |
| `delayed` | 5 seconds to 24 hours | Medium (async) |
| `backdated` | > 24 hours | Low (bulk import) |

`is_backdated = write_lag_ms > 86,400,000` (24 hours)

Used by: P06 (Learning Loop) weights realtime higher, P17 (QoS) tracks latency distribution.

#### Timestamp Safety

- **Future timestamp clamping**: Timestamps beyond year 2100 or beyond 24h future tolerance → clamped to now
- **Unit auto-detection**: >1e15 = microseconds, >1e12 = milliseconds, else seconds
- **Invariant validation**: If `ingested_at` provided, validates `ingested_at <= write_time_utc`
- **DST-safe**: Uses `ZoneInfo` for daylight saving transitions
- **Deterministic**: Captures `now_ts` ONCE at module start, no repeated `datetime.now()` calls

#### MW Signal Passthrough (3 Columns)

These are LLM-extracted temporal signals from K1 that M08 passes through to st_hipp_events:

| Column | Type | Source | Example |
|--------|------|--------|---------|
| `temporal_mentioned_time` | TEXT | body.temporal.mentioned_time | "yesterday evening" |
| `temporal_resolved_epoch_ms` | BIGINT | body.temporal.resolved_epoch_ms | 1709654400000 |
| `temporal_orientation` | TEXT | body.temporal_orientation or body.temporal.orientation | PAST / ONGOING / FUTURE_COMMITMENT |

Validated: temporal_orientation must be in {PAST, ONGOING, FUTURE_COMMITMENT} or null.

#### All Columns Populated by M08

| # | Column | Type | Always? | Notes |
|---|--------|------|---------|-------|
| 1 | `event_time_utc` | INT | Yes | Unix seconds, NEVER null (chain guarantees) |
| 2 | `write_time_utc` | INT | Yes | P02 commit time |
| 3 | `write_lag_ms` | INT | Yes | Milliseconds |
| 4 | `local_date` | TEXT | Yes | ISO date in tenant TZ |
| 5 | `local_time` | TEXT | Yes | ISO time in tenant TZ |
| 6 | `timezone_used` | TEXT | Yes | e.g., "America/Los_Angeles" |
| 7 | `day_of_week` | TEXT | Yes | Monday-Sunday |
| 8 | `is_weekend` | BOOL | Yes | Sat/Sun |
| 9 | `time_of_day_bucket` | TEXT | Yes | morning/afternoon/evening/night |
| 10 | `circadian_slot` | TEXT | Always null | Removed (culturally biased) |
| 11 | `is_backdated` | BOOL | Yes | write_lag > 24h |
| 12 | `created_at` | INT | Yes | = write_time_utc |
| 13 | `temporal_mentioned_time` | TEXT | Sometimes | MW passthrough (null if MW absent) |
| 14 | `temporal_resolved_epoch_ms` | BIGINT | Sometimes | MW resolved epoch (null if MW absent) |
| 15 | `temporal_orientation` | TEXT | Sometimes | PAST/ONGOING/FUTURE_COMMITMENT (null if MW absent) |
| 16 | `temporal_source` | TEXT | Yes | mw_resolved/ner_temporal/event_time/envelope_ts/now |
| 17 | `location_name` | TEXT | Sometimes | Resolved via spatial chain (null acceptable) |
| 18 | `location_type` | TEXT | Sometimes | restaurant/park/school/etc. (null acceptable) |
| 19 | `location_source` | TEXT | Yes | mw_location/ner_location/text_heuristic/none |

**Total**: 19 columns (12 always populated + 4 MW-dependent + 3 spatial)

#### What M08 Does NOT Do

- Does NOT generate NER entities (consumes M02's ner_temporal_entities and ner_loc_entities)
- Does NOT modify affect/social/fingerprint fields (temporal authority only)
- Does NOT write to any persistent store (pure computation)
- Does NOT produce embeddings or KG triples

#### Output Shape

```python
{
    **envelope,
    # Flat temporal fields:
    "event_time_utc": 1709654400,
    "write_time_utc": 1709654401,
    "write_lag_ms": 1000,
    "local_date": "2025-03-05",
    "local_time": "14:30:00",
    "day_of_week": "Wednesday",
    "is_weekend": false,
    "time_of_day_bucket": "afternoon",
    "circadian_slot": null,
    "is_backdated": false,
    "created_at": 1709654401,
    "timezone_used": "America/Los_Angeles",
    # v2 MW temporal:
    "temporal_mentioned_time": "yesterday evening",
    "temporal_resolved_epoch_ms": 1709568000000,
    "temporal_orientation": "PAST",
    "temporal_source": "mw_resolved",
    # v2 spatial:
    "location_name": "Olive Garden",
    "location_type": "restaurant",
    "location_source": "mw_location",
    # Nested enrichments:
    "enrichments": {
        **envelope.enrichments,
        "temporal_profiler": {
            ...all 19 fields above...,
            "module_version": "v2",
            "execution_time_ms": 0.0
        }
    }
}
```

#### Architectural Significance

M08 is the SINGLE SOURCE OF TRUTH for temporal data. Key design properties:

1. **Zero drift**: No other P02 stage recomputes or mutates temporal fields
2. **Deterministic**: `now_ts` captured ONCE, no repeated `datetime.now()` calls
3. **DST-safe**: Uses `ZoneInfo` for all timezone conversions
4. **Schema authority**: 19 columns map 1:1 to st_hipp_events temporal columns
5. **Dual fallback chains**: Both temporal AND spatial resolution with 4-5 priority levels
6. **QoS-aware**: Write lag bands feed P06 (learning) and P17 (monitoring)
7. **Invariant validation**: Checks `ingested_at <= write_time_utc` property

M08 consumes M02's NER output (ner_temporal_entities, ner_loc_entities) as FALLBACK when
MW temporal/spatial signals are missing. This is the trust-then-fill pattern: MW preferred,
M02 NER as safety net, heuristic as last resort.

---

### 23.8 M09: context.device_profile:v1 (stage_40)

**Pipeline Role**: Device and Client Metadata Extraction -- Multi-device family support
**Contract**: `k0/contracts/modules/context.device_profile.v1.yaml`
**Source**: `k0/modules/context/device_profile.py` (320 lines)
**Latency Budget**: 2ms P95 (pure string parsing, zero I/O)
**MW Dependency**: NONE
**Idempotent**: Yes

#### What It Does

M09 classifies WHAT DEVICE submitted the event. Pure string parsing against device_id,
user_agent, and metadata fields. No DB queries, no ML, no MW dependency. Stateless and
deterministic: same device_id always produces the same classification.

4-step algorithm:

1. **Device kind classification**: Regex against device_id (5 categories)
2. **Platform detection**: String-contains against device_id + user_agent (4 platforms)
3. **Client version parsing**: Semantic version extraction (version + build)
4. **Input method mapping**: Keyword matching against metadata.input_source (6 methods)

#### Inputs

| Field | Source | Required | Notes |
|-------|--------|----------|-------|
| `device_id` | envelope.device_id | YES | e.g., "device-dad-phone" |
| `user_agent` | envelope.metadata.user_agent | NO | Browser/client UA string |
| `client_version` | envelope.metadata.client_version | NO | e.g., "2.3.1+20250115.1" |
| `input_source` | envelope.metadata.input_source | NO | e.g., "voice_memo" |

#### Device Kind Classification (Priority-Ordered Regex)

Checked MOST SPECIFIC first to avoid false positives:

| Priority | Kind | Regex Pattern | Example device_id |
|----------|------|---------------|-------------------|
| 1 | watch | `watch\|wearable` | "device-mom-watch" |
| 2 | tablet | `tablet\|ipad` | "device-kid-tablet" |
| 3 | phone | `phone\|iphone\|android` | "device-dad-phone" |
| 4 | web | `web-\|mozilla\|chrome\|safari` | "web-dashboard-001" |
| 5 | api | `api-\|connector-\|server-` | "api-gcal-sync" |
| default | phone | (no match) | "unknown-device-xyz" |

Default is "phone" (most common device in family context).

#### Platform Detection

| Platform | Keywords | Notes |
|----------|----------|-------|
| iOS | ios, iphone, ipad, ipod, watch | Apple ecosystem |
| Android | android | Google ecosystem |
| web | mozilla, chrome, safari, firefox, edge, opera | Browser clients |
| unknown | (no match) | Fallback |

Combines device_id + user_agent for matching (either field can trigger detection).

#### Input Method Mapping

| Method | Keywords | Notes |
|--------|----------|-------|
| voice | voice, audio, transcription, speech | Voice memos |
| photo | photo, image, camera, picture | Photo capture |
| scan | scan, ocr, document | Document scanning |
| import | import, bulk, sync, batch | Bulk imports |
| api | api, connector, scheduled, automation | Programmatic |
| text | (default) | Manual text entry |

#### Columns Populated

| # | Column | Type | Always? | Notes |
|---|--------|------|---------|-------|
| 1 | `device_id` | TEXT | Yes | Preserved as-is from envelope |
| 2 | `device_kind` | TEXT | Yes | phone/tablet/watch/web/api |
| 3 | `device_platform` | TEXT | Yes | iOS/Android/web/unknown |
| 4 | `client_version` | TEXT | Sometimes | Semantic version (null if not provided) |
| 5 | `client_build` | TEXT | Sometimes | Build number after "+" (null if absent) |
| 6 | `input_method` | TEXT | Yes | voice/text/photo/scan/import/api |
| 7 | `device_profiled_at_utc` | TEXT | Yes | ISO 8601 timestamp |

**Total**: 7 columns (5 always, 2 sometimes)

#### Fallback Chain

No waterfall. No tiers. Single-pass string parsing:

```
device_id present?
  YES --> regex classify kind + detect platform (<0.5ms)
  NO  --> device_kind="phone", device_platform="unknown"

metadata.input_source present?
  YES --> keyword map to method (<0.1ms)
  NO  --> input_method="text"

metadata.client_version present?
  YES --> parse "2.3.1+build" into version + build
  NO  --> client_version=null, client_build=null
```

#### What M09 Does NOT Do

- Does NOT query any database (pure string parsing)
- Does NOT use MW signals
- Does NOT use M02 NER output
- Does NOT write to any persistent store
- Does NOT do device fingerprinting or tracking (privacy by design)
- Does NOT validate client version compatibility (just parses)

#### Downstream Consumers

- **M11 (retention_lookup)**: `device_kind` is part of retention policy key: `(band, topic, device_kind) -> retention_policy_id`
- **Analytics**: Device distribution metrics (80% phone, 15% web, 5% other)
- **P17 (QoS)**: Input method distribution (voice vs text latency differences)

---

### 23.9 M10: context.ingress_classify:v1 (stage_41)

**Pipeline Role**: Channel Attribution and Activity Classification
**Contract**: `k0/contracts/modules/context.ingress_classify.v1.yaml`
**Source**: `k0/modules/context/ingress_classify.py` (995 lines)
**Latency Budget**: 3ms P95 (rule-based), 30ms P95 (UltraBERT path)
**MW Dependency**: NONE (but uses body.activity_type if provided by K1)
**Idempotent**: Yes

#### What It Does

M10 answers THREE questions about each event:

1. **HOW did it arrive?** (ingress_topic: write/photo/voice/import)
2. **WHAT kind of activity?** (activity_type: meal/milestone/work/social/conversation/routine/unknown)
3. **WHAT kind of memory?** (content_type: episodic/semantic/procedural)

Plus metadata: ingress_source, is_structured, is_user_initiated.

#### Activity Classification: 3-Tier Waterfall

```
TIER 0: body.activity_type provided? (K1 pre-classified)
  |  Maps uppercase K1 types to legacy 7-type:
  |    FAMILY->social, WORK->work, HEALTH->routine,
  |    CELEBRATION->milestone, MEAL->meal, etc.
  |  Also accepts lowercase legacy types directly
  |
  +--NOT PROVIDED--> TIER 1: UltraBERT unified model
  |  classify_activity_ultrabert(text):
  |    INGRESS classification (12 types):
  |      DIARY, TASK, HEALTH, FINANCE, RELATIONSHIP, WORK,
  |      META, MEMORY, PLANNING, CELEBRATION, CONCERN, GRATITUDE
  |    INTENT classification (8 types):
  |      log_memory, query_memory, set_reminder, express_feeling,
  |      seek_advice, share_news, reflect, other
  |  Maps 12-type to legacy 7-type for backward compat
  |  Returns confidence score (0.0-1.0)
  |
  +--ULTRABERT UNAVAILABLE--> TIER 1b: ZeroShotActivityClassifier
  |  BART-MNLI zero-shot classification (20+ activity types)
  |  Multi-label support (e.g., "birthday dinner" = celebration + meal)
  |  Maps to legacy 7-type
  |
  +--CLASSIFIER UNAVAILABLE--> TIER 2: Rule-based keyword matching
     Priority-ordered keyword scan (high-specificity first):
       1. meal: breakfast, lunch, dinner, ate, food, restaurant...
       2. milestone: birthday, anniversary, graduation, wedding...
       3. work: meeting, project, deadline, presentation...
       4. social: party, gathering, reunion, celebration...
       5. conversation: chat, talked, discussed, call...
       6. routine: shower, brushed, bedtime, woke up, commute...
       7. unknown: (no keyword match)
     Word-boundary matching to avoid false positives
     (e.g., "celebrated" does NOT match "ate")
```

#### Ingress Topic Classification

Maps event topic string to channel:

| Topic | Channel |
|-------|---------|
| `cognitive.memory.write.committed.v1` | write |
| `cognitive.memory.photo` / `.v1` | photo |
| `cognitive.memory.voice` / `.v1` | voice |
| `cognitive.memory.import` / `.v1` | import |
| (unknown) | write (default) |

Fuzzy matching: if exact lookup fails, checks for "photo"/"voice"/"import" substring.

#### Content Type Classification

| Type | Condition | Prevalence |
|------|-----------|------------|
| episodic | Default (time-bound personal experience) | ~95% of P02 |
| semantic | `body.is_fact` or `body.is_knowledge_base_entry` or text contains "fact/definition/knowledge" | ~4% |
| procedural | `body.is_recipe` or `body.is_how_to` or text contains "recipe/how to/instructions" | ~1% |

#### Ingress Source Inference

| Source | Keywords (in user_agent + metadata.source + device_id) | Priority |
|--------|--------------------------------------------------------|----------|
| connector | connector, sync, import, integration, fitbit, gcal | 1 (highest) |
| api | api, automation, scheduled, batch, bulk | 2 |
| mobile_app | iphone, android, mobile, ios | 3 |
| web_app | mozilla, chrome, safari, firefox, edge, opera | 4 |
| mobile_app | (default) | fallback |

#### Boolean Flags

| Flag | Condition |
|------|-----------|
| `is_structured` | `metadata.is_structured == true` OR `body.schema_version` exists |
| `is_user_initiated` | ingress_topic NOT in ["import"] AND ingress_source NOT in ["api", "connector"] |

#### Columns Populated

| # | Column | Type | Always? | Notes |
|---|--------|------|---------|-------|
| 1 | `ingress_topic` | TEXT | Yes | write/photo/voice/import |
| 2 | `activity_type` | TEXT | Yes | meal/milestone/work/social/conversation/routine/unknown |
| 3 | `content_type` | TEXT | Yes | episodic/semantic/procedural |
| 4 | `ingress_source` | TEXT | Yes | mobile_app/web_app/api/connector |
| 5 | `is_structured` | BOOL | Yes | Schema-conformant input? |
| 6 | `is_user_initiated` | BOOL | Yes | Human vs automated? |
| 7 | `ingress_classified_at_utc` | TEXT | Yes | ISO 8601 timestamp |
| 8 | `activity_type_ultrabert` | TEXT | Sometimes | 12-type UltraBERT classification (null if unavailable) |
| 9 | `activity_type_confidence` | FLOAT | Sometimes | UltraBERT confidence 0.0-1.0 |
| 10 | `intent_ultrabert` | TEXT | Sometimes | 8-type intent classification (null if unavailable) |
| 11 | `intent_confidence` | FLOAT | Sometimes | Intent confidence 0.0-1.0 |

**Total**: 11 columns (7 always, 4 UltraBERT-dependent)

**Enhanced mode** (when `FEATURE_ENHANCED_CLASSIFICATION=True`, currently ON):
Additional enrichment fields in `enrichments.ingress_classifier`:

- `activity_type_enhanced`: Full 20+ type classification
- `activity_confidence`: Classification confidence
- `secondary_activities`: Multi-label list (e.g., ["celebration", "meal"])
- `is_multi_activity`: Boolean
- `activity_hierarchy_path`: e.g., "sustenance.meal.dinner"
- `activity_parent_category`: Parent in hierarchy

#### What M10 Does NOT Do

- Does NOT generate embeddings (uses text only for keyword matching or ML classification)
- Does NOT query any database (pure computation)
- Does NOT write to any persistent store
- Does NOT use M02 NER output (independent classification)
- Does NOT modify temporal/spatial/affect fields

#### Downstream Consumers

- **M11 (retention_lookup)**: `activity_type` is part of retention policy key
- **M06 (salience)**: `activity_type` may influence salience scoring
- **M13 (row builder)**: All 11 columns assembled into st_hipp_events row
- **P03 (consolidation)**: `activity_type` used for consolidation grouping
- **Analytics**: Activity type distribution dashboard

---

### 23.10 M12: context.geo_metadata:v1 (stage_42)

**Pipeline Role**: Privacy-Preserving Spatial Metadata Extraction
**Contract**: `k0/contracts/modules/context.geo_metadata.v1.yaml`
**Source**: `k0/modules/context/geo_metadata.py` (310 lines)
**Latency Budget**: 2ms P95 (pure field copy/parse, zero external APIs)
**MW Dependency**: NONE
**Idempotent**: Yes

#### What It Does

M12 is a PRIVACY-PRESERVING spatial metadata extractor. It reads pre-masked location
data from the envelope (Gate Stage 3 already applied band-level masking) and copies
it to structured fields. It does NO re-masking, NO enrichment, NO reverse geocoding,
NO place lookups. Pure field copy with validation.

3-step algorithm:

1. **Geohash extraction**: Read `body.location_geohash`, validate base32 format, truncate to 6 chars
2. **Location copy**: Copy `body.location_name` and `body.location_type` as-is
3. **Privacy metadata**: Map `policy_stamp.band` to precision level, extract masking reason from obligations

#### Privacy Model

P02 NEVER sees raw lat/lon coordinates. Gate Stage 3 strips them before WAL write.

| Privacy Band | What M12 Receives | Precision | Radius |
|---|---|---|---|
| GREEN | Full geohash (up to 12 chars, truncated to 6) | geohash-6 | ~1.2km |
| AMBER | Coarse geohash (6 chars) | geohash-6 | ~1.2km |
| RED | Very coarse geohash (4 chars) | geohash-4 | ~39km |
| (no band) | Whatever is in envelope | unknown | varies |

Critical: M12 stores `geohash_6` (always truncated to max 6 characters) regardless
of what precision was in the envelope. This is a FLOOR, not a ceiling.

#### Geohash Validation

Base32 alphabet: `0-9, b-h, j-k, m-n, p-z` (excludes a, i, l, o to avoid ambiguity).

```
location_geohash present?
  YES --> valid base32 format?
          YES --> truncate to 6 chars, store as geohash_6
          NO  --> geohash_6 = null (invalid format logged)
  NO  --> geohash_6 = null
```

#### Geo Precision Mapping

| Band | geo_precision_external | Meaning |
|------|----------------------|---------|
| GREEN | "full" | Full precision available |
| AMBER | "geohash-6" | Neighborhood level |
| RED | "geohash-4" | City level |
| (missing) | "unknown" | Band not set |

#### Geo Masking Reason

Derived from `policy_stamp.obligations` list:

| Obligation Contains | Masking Reason |
|---|---|
| "mask.location" | "band_policy" |
| "user.privacy.location" | "user_preference" |
| (none/empty) | "none" |

#### Columns Populated

| # | Column | Type | Always? | Notes |
|---|--------|------|---------|-------|
| 1 | `geohash_6` | TEXT | Sometimes | 6-char geohash (null if no location or invalid) |
| 2 | `location_name` | TEXT | Sometimes | Human-readable place name (null if not provided) |
| 3 | `location_type` | TEXT | Sometimes | Place category (null if not provided) |
| 4 | `geo_precision_external` | TEXT | Yes | full/geohash-6/geohash-4/unknown |
| 5 | `geo_masking_reason` | TEXT | Yes | band_policy/user_preference/none |
| 6 | `geo_metadata_extracted_at_utc` | TEXT | Yes | ISO 8601 timestamp |

**Total**: 6 columns (3 always, 3 sometimes)

#### Relationship to M08 Spatial Chain

M12 and M08 BOTH produce location fields but from DIFFERENT sources:

| Field | M08 Source | M12 Source | Authority |
|-------|-----------|-----------|-----------|
| `location_name` | MW / NER / heuristic (resolved) | `body.location_name` (raw copy) | M08 (resolved) |
| `location_type` | MW / regex classification | `body.location_type` (raw copy) | M08 (classified) |
| `geohash_6` | NOT produced | `body.location_geohash` (truncated) | M12 (only source) |
| `geo_precision_external` | NOT produced | `policy_stamp.band` mapping | M12 (only source) |
| `geo_masking_reason` | NOT produced | `policy_stamp.obligations` | M12 (only source) |

M08 resolves location through a multi-tier fallback chain (MW -> NER -> heuristic).
M12 copies raw envelope fields with privacy metadata. They are complementary:

- M08 = RESOLVED location (best-effort intelligent extraction)
- M12 = RAW location + PRIVACY metadata (what the envelope actually contained)

M13 (row builder) must decide which `location_name`/`location_type` to use for st_hipp_events.

#### What M12 Does NOT Do

- Does NOT perform reverse geocoding (no address from coordinates)
- Does NOT do place enrichment (no POI lookup, no place chain detection)
- Does NOT do geofence resolution (no home/work/school zone detection)
- Does NOT re-mask data (Gate Stage 3 already did that)
- Does NOT access raw lat/lon (stripped before P02)
- Does NOT use MW signals or M02 NER output
- Does NOT query any database

#### Architectural Significance

M12 is the PRIVACY AUDIT TRAIL for spatial data. Key properties:

1. **Privacy-preserving**: Never sees raw coordinates (Gate strips them)
2. **Audit-ready**: Records WHY masking was applied (band_policy vs user_preference)
3. **Precision-tracked**: Records WHAT precision level was used (full/geohash-6/geohash-4)
4. **Complementary to M08**: M08 = resolved location, M12 = raw location + privacy metadata
5. **Zero side effects**: Pure copy + validate + timestamp (no writes, no external calls)
6. **Geofence-deferred**: Complex geo enrichment deferred to P09 (Connector Ingestion)

---

### 23.11 M15: context.spatial_minimal:v1 (stage_43)

**Pipeline Role**: Band-Based Spatial Minimization -- Privacy-enforced geohash truncation
**Contract**: `k0/contracts/modules/context.spatial_minimal.v1.yaml`
**Source**: `k0/modules/context/spatial_minimal.py` (260 lines)
**Latency Budget**: 1ms P95 (copy + truncate, zero computation)
**MW Dependency**: NONE
**Idempotent**: Yes

#### What It Does

M15 applies FINAL band-based geohash truncation before storage. Gate Stage 3 already
masked the raw coordinates, and M12 already copied the geohash. M15 is the LAST PASS
that enforces privacy-band precision limits on the geohash before it reaches st_hipp_events.

3-step algorithm:

1. **Read** `envelope.location_geohash` (pre-computed by Gate Stage 3)
2. **Truncate** based on privacy band: GREEN=6 chars, AMBER=4 chars, RED=NULL
3. **Copy** `body.location_name` and `body.location_type` as-is

#### Band-Based Geohash Truncation

| Band | Precision Chars | Geohash Output | Spatial Precision |
|------|-----------------|----------------|-------------------|
| GREEN | 6 | Full geohash_6 | ~1.2km x 0.6km |
| AMBER | 4 | Truncated to 4 chars | ~20km x 20km |
| RED | 0 | NULL (omitted entirely) | Maximum privacy |
| (missing) | 6 (default GREEN) | Full geohash_6 | ~1.2km x 0.6km |

```
location_geohash present?
  YES --> band == RED?
          YES --> geohash_6 = NULL (privacy override)
          NO  --> band == AMBER?
                  YES --> geohash_6 = geohash[:4] (coarse)
                  NO  --> geohash_6 = geohash[:6] (GREEN, full)
  NO  --> geohash_6 = NULL
```

#### Columns Populated

| # | Column | Type | Always? | Notes |
|---|--------|------|---------|-------|
| 1 | `geohash_6` | TEXT | Sometimes | NULL for RED band or missing geohash |
| 2 | `location_name` | TEXT | Sometimes | Raw copy from body (null if absent) |
| 3 | `location_type` | TEXT | Sometimes | Raw copy from body (null if absent) |
| 4 | `spatial_minimized_at_utc` | TEXT | Yes | ISO 8601 timestamp |

**Total**: 4 columns (1 always, 3 sometimes)

#### Relationship to M12 (geo_metadata)

M15 and M12 overlap significantly -- both read location fields from the envelope:

| Concern | M12 (geo_metadata) | M15 (spatial_minimal) |
|---------|--------------------|-----------------------|
| Geohash | Truncate to 6 chars always | Band-based: 6/4/NULL |
| location_name | Copy from body | Copy from body |
| location_type | Copy from body | Copy from body |
| Privacy metadata | geo_precision_external, geo_masking_reason | NOT tracked |
| Band enforcement | NOT enforced (always geohash-6) | ENFORCED (RED=NULL, AMBER=4) |

**Key difference**: M12 stores AUDIT METADATA (precision level, masking reason).
M15 enforces FINAL PRIVACY TRUNCATION (RED band → NULL geohash).
M12 always stores geohash_6 (truncated to 6). M15 may further truncate or null it.

#### What M15 Does NOT Do

- Does NOT access raw lat/lon (Gate strips them)
- Does NOT perform reverse geocoding or place enrichment
- Does NOT query any database
- Does NOT use MW signals or M02 NER output
- Does NOT compute location_name or location_type (just copies)

---

### 23.12 M11: context.retention_lookup:v1 (stage_50)

**Pipeline Role**: Memory Decay Scheduler -- Retention policy resolution at write time
**Contract**: `k0/contracts/modules/context.retention_lookup.v1.yaml`
**Source**: `k0/modules/context/retention_lookup.py` (310 lines)
**Latency Budget**: 3ms P95 (cache-optimized, <1ms cache hit)
**MW Dependency**: NONE
**Idempotent**: Yes

#### What It Does

M11 resolves HOW LONG to keep an event before it becomes eligible for archival or deletion.
It uses a 3-axis matrix lookup: `(band, topic, device_kind) -> retention_policy`. This is
the write-time retention decision -- once stored in st_hipp_events, retention workers use
the stored policy_id without recomputation.

#### 3-Axis Retention Matrix

| Axis | Source | Values |
|------|--------|--------|
| **band** | `envelope.policy_stamp.band` | GREEN / AMBER / RED |
| **topic** | `envelope.topic` (stripped of version) | cognitive.memory.write / photo / voice / import |
| **device_kind** | M09 output (`envelope.metadata.device_kind`) | phone / tablet / watch / web / api |

#### Fallback Chain (4 tiers, always succeeds)

```
TIER 1: Exact match (band, topic, device_kind)
  |  e.g., ("RED", "cognitive.memory.write", "phone")
  |
  +--NOT FOUND--> TIER 2: Wildcard device (band, topic, "*")
  |  e.g., ("RED", "cognitive.memory.write", "*")
  |
  +--NOT FOUND--> TIER 3: Wildcard topic + device (band, "*", "*")
  |  e.g., ("RED", "*", "*")
  |
  +--NOT FOUND--> TIER 4: System default
     retention_policy_id = "pol-default-standard"
     retention_bucket = "STANDARD"
     retention_days = 365
```

LRU cache (maxsize=500) wraps the lookup chain. Cache hit = <1ms.

#### Retention Buckets (3 types)

| Bucket | Description | Typical Days | Use Case |
|--------|-------------|--------------|----------|
| STANDARD | Normal retention | 365-2555 | GREEN band routine events |
| SENSITIVE | Extended with audit trail | 30-90 | AMBER/RED band, requires deletion audit |
| EPHEMERAL | Short-lived | 7 | Watch fitness data, voice transcripts |

#### Policy Examples (from embedded policy DB)

| Band | Topic | Device | Policy ID | Bucket | Days |
|------|-------|--------|-----------|--------|------|
| GREEN | write | * | pol-green-write-all | STANDARD | 2555 (7 years) |
| GREEN | photo | * | pol-green-photo-all | STANDARD | 2555 |
| GREEN | voice | * | pol-green-voice-all | STANDARD | 365 |
| AMBER | write | * | pol-amber-write-all | STANDARD | 90 |
| AMBER | voice | * | pol-amber-voice-all | SENSITIVE | 30 |
| RED | write | phone | pol-red-write-phone | STANDARD | 30 |
| RED | write | watch | pol-red-write-watch | EPHEMERAL | 7 |
| RED | voice | * | pol-red-voice-all | SENSITIVE | 7 |

Key pattern: GREEN = long retention (years), AMBER = medium (months), RED = short (days/weeks).
Voice is always shorter retention than write/photo (transcription privacy).

#### Topic Normalization

Before lookup, M11 strips version suffixes:

- `cognitive.memory.write.committed.v1` → `cognitive.memory.write`
- `cognitive.memory.photo.v1` → `cognitive.memory.photo`

#### Columns Populated

| # | Column | Type | Always? | Notes |
|---|--------|------|---------|-------|
| 1 | `retention_policy_id` | TEXT | Yes | FK to retention policy (e.g., "pol-green-write-all") |
| 2 | `retention_bucket` | TEXT | Yes | STANDARD / SENSITIVE / EPHEMERAL |
| 3 | `retention_resolved_at_utc` | TEXT | Yes | ISO 8601 timestamp |

**Total**: 3 columns (all always populated)

Note: `retention_days` is computed internally but NOT written to st_hipp_events output.
Retention workers look up days from the policy_id when scheduling deletion.

#### Upstream Dependencies

- **M09 (device_profile)**: Provides `device_kind` (pipeline order: M09 at stage_40, M11 at stage_50)
- **Gate**: Provides `policy_stamp.band`
- **Envelope**: Provides `topic`

#### What M11 Does NOT Do

- Does NOT compute deletion_eligible_at (retention workers do that)
- Does NOT perform actual deletion or archival
- Does NOT use MW signals or M02 NER output
- Does NOT modify any other enrichment fields
- Does NOT write to any persistent store (pure lookup + cache)

---

### 23.13 M06: salience.score:v2 (stage_55)

**Pipeline Role**: Attention Network / Priority Ranking -- Determines event importance
**Contract**: `k0/contracts/modules/salience.score.v2.yaml`
**Source**: `k0/modules/salience/score.py` (787 lines)
**Latency Budget**: 5ms P95 (pure computation, zero I/O)
**MW Dependency**: YES -- TRUST-THEN-FILL module (via upstream inputs, not direct MW read)
**Idempotent**: Yes

#### What It Does

M06 computes a single importance score (0-1) for each event, classifies it into a band
(HIGH/MED/LOW), and provides interpretable reasons. This score drives:

- P08 consolidation priority (HIGH events consolidated first)
- P03 retrieval ranking (salience-weighted search results)
- P06 learning loop (salience distribution as system health metric)

#### The Formula (UNCHANGED from v1)

```
salience_score = 0.50 x social + 0.40 x affect + 0.10 x recency
```

| Weight | Component | Source Module | Score Range |
|--------|-----------|---------------|-------------|
| 0.50 | Social importance | M07 (social_context) | 0.0 - 1.0 |
| 0.40 | Affect amplification | M04 (affect_intensity) | 0.0 - 1.0 |
| 0.10 | Recency decay | M08 (event_time_utc) | 0.0 - 1.0 |

**v2 fix**: The formula is identical. The fix is CORRECT INPUTS:

- v1: social_context was always "friends" (0.5) because st_kg_edges was empty → 60% of rows stuck at 0.41
- v2: M07 now produces correct social_context from MW relationships → proper distribution

#### Social Importance Scoring (Hash Lookup)

| Social Context | Score | Rationale |
|---|---|---|
| nuclear_family | 1.0 | Kin selection theory (Hamilton 1964) |
| family (legacy alias) | 1.0 | Backward compat |
| extended_family | 0.7 | Grandparents, aunts, uncles |
| close_friends | 0.6 | Strong bond confidants |
| friends | 0.5 | Regular social contacts |
| colleagues | 0.4 | Professional contacts (v2 NEW) |
| community | 0.3 | Neighbors, group affiliations (v2 NEW) |
| acquaintance | 0.3 | Casual contacts |
| solo | 0.2 | Self-reflection |
| unknown | 0.4 | Safe default (between solo and friends) |

#### Affect Amplification (Non-Linear)

```python
amplified = affect + (affect ** 2) * 0.2
# Examples:
#   affect=0.2 → 0.208 (minimal boost)
#   affect=0.5 → 0.550 (10% boost)
#   affect=0.9 → 1.062 → clamped to 1.0 (16% boost at top end)
```

Research: Cahill & McGaugh (1998) -- emotional arousal enhances memory consolidation.
High-arousal events get nonlinear amplification (amygdala-hippocampus interaction).
Missing affect_intensity defaults to 0.5 (neutral baseline).

#### Recency Decay (Piecewise Exponential)

```
0-1 hour:   score = max(0.8, 2^(-t/1h))   → Working memory range (0.8-1.0)
1-24 hours: score = max(0.3, 0.8 * 2^(-(t-1)/24h))  → Fresh episodic (0.3-0.8)
1-7 days:   score = max(0.1, 0.3 * 2^(-(t-24)/168h)) → Older episodic (0.1-0.3)
7+ days:    score = 0.1   → Long-term baseline
```

Research: Ebbinghaus forgetting curve (1885), Atkinson & Shiffrin multi-store model (1968).
Future timestamps (clock skew) treated as maximally recent (score=1.0).

#### Salience Bands

| Band | Threshold | Expected Distribution | Downstream |
|------|-----------|----------------------|------------|
| HIGH | >= 0.7 | 15-25% | P08 consolidation priority |
| MED | 0.4 - 0.7 | 50-60% | Normal processing |
| LOW | < 0.4 | 20-30% | Background retention |

v1 problem: 100% MED band (no discrimination). v2 target: proper HIGH/MED/LOW distribution.

#### v2 Addition: Entity Salience Cross-Validation

When MW provides `body.entity_salience` (per-entity importance map):

1. Compute mean of MW entity salience values
2. Compare with M06 computed salience_score
3. If `abs(m06_score - mw_mean) > 0.3` → log discrepancy warning

This is OBSERVABILITY ONLY -- does NOT change the formula or the output score.
Used to detect systematic disagreement between K1's LLM salience and K0's formula.

#### Graceful Failure

On ANY exception during scoring:

- salience_score = 0.5 (neutral default)
- salience_band = "MED"
- salience_reasons = ["Scoring failed, using default"]
- component_scores = {social: 0.4, affect: 0.5, recency: 0.5}
- Pipeline continues (M06 failure NEVER crashes P02)

#### Columns Populated

| # | Column | Type | Always? | Notes |
|---|--------|------|---------|-------|
| 1 | `salience_score` | REAL | Yes | 0.0 - 1.0 weighted sum |
| 2 | `salience_band` | TEXT | Yes | HIGH / MED / LOW |
| 3 | `salience_reasons_json` | TEXT | Yes | JSON array of human-readable reasons |
| 4 | `component_scores_json` | TEXT | Yes | JSON: {social, affect, recency} |
| 5 | `salience_computed_at_utc` | TEXT | Yes | ISO 8601 timestamp |
| 6 | `entity_salience_discrepancy` | REAL | Sometimes | v2: MW cross-validation delta (null if no MW entity_salience) |

**Total**: 6 columns (5 always, 1 v2-dependent)

#### DAG Position (Critical)

M06 runs at stage_55, AFTER all three input producers:

- stage_30 (M04 affect) → provides affect_intensity
- stage_32 (M07 social) → provides social_context
- stage_33 (M08 temporal) → provides event_time_utc

This is the CONVERGENCE POINT where social + affect + temporal merge into a single score.
The trust-then-fill architecture ensures M06 always gets SOME value from each upstream
module (either MW-sourced or fallback-computed), so M06 never sees all-null inputs.

#### What M06 Does NOT Do

- Does NOT directly read MW signals (consumes upstream module outputs only)
- Does NOT generate embeddings or NER entities
- Does NOT write to any persistent store
- Does NOT modify upstream enrichment fields
- Does NOT perform I/O of any kind (pure computation)

#### Architectural Significance

M06 is the QUALITY SIGNAL for the entire memory system. Key properties:

1. **Same formula, fixed inputs**: v2 changes zero formula code, only upstream modules
2. **Research-validated weights**: Social(0.50) + Affect(0.40) + Recency(0.10) backed by memory consolidation literature
3. **Convergence point**: Only module that reads outputs from 3 upstream trust-then-fill chains
4. **Interpretable**: Every score has structured reasons (transparency for debugging + user queries)
5. **Cross-validated**: MW entity_salience comparison detects systematic K0/K1 disagreement
6. **Fail-safe**: Always produces a score (0.5 default on error), never blocks pipeline

---

### 23.14 M13 `builders.hipp_events_row` — Row Assembly (stage_60)

| Property | Value |
|---|---|
| **Contract** | `builders.hipp_events_row.v2.yaml` |
| **Source** | `k0/modules/builders/hipp_events_row.py` (1232 lines) |
| **Stage** | 60 (depends on ALL prior stages: 10-55) |
| **Latency Budget** | <10ms P95 (pure assembly, zero I/O) |
| **MW Dependency** | Group 12 (11 cols) pure passthrough from `envelope.body`; Group 13 (5 cols) M5A passthrough |
| **UltraBERT Dependency** | None direct (consumes upstream module outputs) |
| **Idempotent** | Yes |
| **Side Effects** | None |

#### What It Does

M13 is the CONVERGENCE POINT for the entire P02 pipeline. Every prior enrichment module (M01-M15, M22) feeds into M13, which assembles a single dictionary representing one complete st_hipp_events row. There is no I/O, no ML, no DB access — pure in-memory dictionary assembly with JSON serialization and validation.

The module operates in 5 phases:

1. **Extract** — Reads 14 enrichment outputs from `envelope.enrichments{}` (nested) with flat-envelope fallback
2. **Map** — Calls 13 column-group mappers (Groups 1-13) to produce column dictionaries
3. **Arbitrate** — Computes `effective_safety_band` (most restrictive of K1 policy_band vs UltraBERT safety_familyos_band)
4. **Validate** — Checks 17 required NOT NULL fields, value ranges, and enum constraints
5. **Return** — Returns `{"hipp_events_row": row}` to pipeline runner

#### Column Groups (13 groups, ~116 columns)

| Group | Name | Cols | Source Modules | Key Columns |
|---|---|---|---|---|
| 1 | Identity & Trace | 9 | envelope, M05 | event_id, wal_pos, cognitive_trace_id, tenant_id, space_id |
| 2 | Integrity & Audit | 6 | envelope | envelope_sha256, idem_key, ingested_at, clock_skew_ms |
| 3 | Policy & Visibility | 10 | M03, M05, M11 | policy_decision, policy_band, visible_to_json, co_owners_json, retention_bucket |
| 4 | Actor & Device | 6 | envelope, M09, M10 | actor_id, device_kind, device_os, ingress_channel |
| 5 | Temporal | 14 | M08 | event_time_utc, write_time_utc, local_date, circadian_slot, temporal_orientation (+3 v2) |
| 6 | Spatial & Place | 5 | M12, M15 | geohash_6, location_name, location_type, geo_precision_external |
| 7 | Social & Relationships | 9 | envelope.body, M07 | participants_json, social_context, social_intimacy, participant_relationships_json (+1 v2) |
| 8 | Semantic & Activity | 14 | envelope.body, M10 | text, activity_type, activity_type_ultrabert, intent_ultrabert (+4 Issue 0060) |
| 9 | Hippocampus DG/CA1 | 8 | M01, M02 | simhash_hex, minhash32, novelty_score=NULL (deferred to P03) |
| 10 | Embeddings & KG | 15 | M02, M22 | embedding_id, embedding_status, entities_json, ner_entities_json, safety_familyos_band |
| 11 | Affect & Salience | 10 | M04, M06 | affect_valence, affect_arousal, affect_dominance (+1 v2), salience_score, salience_band |
| 12 | MW v2 Signals | 11 | envelope.body | narrative_thread_id, intent_type, source_type, novelty, elaboration_depth, entity_salience_json |
| 13 | MW v2a Signals (M5A) | 5 | envelope.body | surprise_level, identity_relevance, source_reliability, memory_tier, temporal_anchor_json |

#### Safety Band Arbitration (Issue 0053)

```
K1 policy_band (from envelope.band)
  |
  |  SAFETY_BAND_ORDER: GREEN(0) < AMBER(1) < RED(2) < CRISIS(3)
  |
UltraBERT safety_familyos_band (from M02/CA1)
  |
  +--COMPARE severity scores-->  MOST RESTRICTIVE WINS
     effective_safety_band = max(k1_score, ub_score)
```

Example: K1 says GREEN, UltraBERT says AMBER → effective_safety_band = AMBER.

#### Clinical Safety Salience Boost (embedded in Group 11 mapper)

When M04 sets `clinical_safety_risk=True`:

- Salience reasons gain `clinical_safety_{severity}` entry
- Salience score boosted: CRITICAL→1.0, HIGH→min 0.9, MEDIUM→min 0.7, LOW→min 0.5
- Salience band upgraded for CRITICAL/HIGH → "HIGH", MEDIUM+LOW → "MED"
- Dominant emotions appended with "distress" for CRITICAL/HIGH

#### Double-Encoding Protection

M13 contains explicit guards against double-encoding JSON columns. For `visible_to_json`, `co_owners_json`, `participants_json`, `participant_roles_json`:

- If value is already `str` → use as-is
- If value is `list`/`dict` → serialize via `json.dumps`
- If value is `None` → use empty JSON literal (`"[]"` or `"{}"`)

This prevents `"[\"alice\"]"` → `"\"[\\\"alice\\\"]\""` corruption.

#### Validation (3 layers)

| Layer | Check | Failure Policy |
|---|---|---|
| **Required fields** | 17 NOT NULL columns (event_id, wal_pos, tenant_id, etc.) | `ValueError` → drop event |
| **Value ranges** | affect_valence [-1,1], arousal [0,1], salience [0,1], dominance [0,1] | `ValueError` → drop event |
| **Enum constraints** | policy_band, affect_band, salience_band, narrative_arc_position, source_type, novelty, elaboration_depth, temporal_orientation | `ValueError` → drop event |

#### CA3 Deferred Columns (set to NULL by M13)

These columns are populated by P03 consolidation, never by P02:

- `is_near_duplicate` — P03 near-dup detection
- `novelty_score` — P03 novelty analysis (FLOAT, distinct from `novelty` TEXT in Group 12)
- `episode_cluster_id` — P03 clustering
- `cluster_confidence` — P03 clustering confidence
- `clustering_version` — P03 algorithm version
- `near_duplicates_json` — P03 neighbor list

#### What M13 Does NOT Do

- Does NOT perform any I/O (no DB, no network, no filesystem)
- Does NOT run any ML models
- Does NOT transform MW signals (Groups 12-13 are pure passthrough)
- Does NOT compute anything novel (all values come from upstream modules)
- Does NOT write to st_hipp_events (that is M16's job)
- Does NOT handle embeddings/vectors (M22 provides, M16 writes)

#### Architectural Significance

M13 is the single point where all P02 enrichment converges into a storage-ready row. Key properties:

1. **Assembly-only**: Zero computation, zero I/O — fastest possible latency (<10ms)
2. **13 column-group mappers**: Each mapper is independently testable and traceable
3. **Dual extraction**: Prefers `enrichments.{module}` (nested), falls back to flat envelope — enables gradual migration
4. **Arbitration logic**: `effective_safety_band` is the only computed field (most-restrictive-wins)
5. **Contract-enforced**: v2 contract specifies 111 actively-mapped columns across 12 groups (13th group added in code)
6. **P03 boundary**: Explicitly nullifies CA3 columns that belong to consolidation pipeline

---

### 23.15 M16 `core.hipp_events_writer` — Atomic 3-Table Writer (stage_70)

| Property | Value |
|---|---|
| **Contract** | `core.hipp_events_writer.v1.yaml` (internal revision 1.2) |
| **Source** | `k0/modules/core/hipp_events_writer.py` (254 lines) |
| **Stage** | 70 (depends on stage_60 / M13 row assembly) |
| **Latency Budget** | <30ms P95 (3-table INSERT with B-tree indexes) |
| **MW Dependency** | None (writes whatever M13 assembled) |
| **UltraBERT Dependency** | None (embedding comes from M22 via envelope) |
| **Idempotent** | Yes (event_id PK + st_pipeline_processed check) |
| **Side Effects** | write:st_hipp_events, write:st_vec, write:st_pipeline_processed |

#### What It Does

M16 is the STORAGE COMMIT point for P02. It takes the complete row dictionary assembled by M13, extracts the embedding vector from M22, and performs a 3-table atomic write:

```
M13 output (hipp_events_row)
  |
  +--1. st_hipp_events INSERT (parent row, 70+ columns)
  |    via syscalls.hipp_events_upsert(**row)
  |
  +--2. st_vec INSERT (child row, FK to event_id)
  |    via syscalls.vec_write(embedding_id, event_id, vector, ...)
  |    768-dim float list → pgvector VECTOR(768) native
  |    ONLY if M22 provided embedding; else skip (PENDING for P08)
  |
  +--3. st_pipeline_processed INSERT (tracking)
       via syscalls.pipeline_processed_upsert(pipeline_id="P02_WRITE", wal_pos, ...)
```

#### Transaction Boundary (ADR-K003 v1.2)

Critical ordering enforced by ADR-K003 v1.2:

- **st_hipp_events FIRST** — parent row (PK: event_id)
- **st_vec SECOND** — child row (FK: event_id → st_hipp_events.event_id)
- **st_pipeline_processed LAST** — completion tracking

M23 (`builders.embedding_write`) was MERGED into M16 to guarantee atomic FK ordering. Stage 61 was removed from P02 DAG.

#### Embedding Handling (ADR-K003)

```
M22 extract_from_cache output in envelope:
  |
  +--HAS embedding + embedding_id?
  |    YES → syscalls.vec_write(768-dim, model_id="ultrabert_v2.1.0", status="READY")
  |           _metrics.embeddings_written++
  |    NO  → Skip st_vec write, log debug "embedding_status=PENDING"
  |           _metrics.embeddings_skipped++
  |           P08 backfill will generate and store later
  |
  +--vec_write FAILS?
       Non-fatal: log warning, continue
       Event still stored in st_hipp_events (embedding_status=PENDING)
       P08 backfill handles recovery
```

#### Idempotency (2 layers)

| Layer | Mechanism | Behavior |
|---|---|---|
| **event_id PK** | INSERT OR IGNORE on st_hipp_events | Duplicate event_id → skip (returns `inserted=false`, `status=SKIPPED_DUPLICATE`) |
| **st_pipeline_processed** | Checked before write | Already-processed wal_pos → skip entire pipeline (dedup at pipeline level) |

#### Input Assembly

M16 does NOT build the row — it reads it:

- `envelope["hipp_events_row"]` → complete 70+ column dictionary from M13
- `envelope["extract_from_cache"]` → embedding data from M22 (embedding, embedding_id, model_id)
- Validates 3 required fields: `event_id` (not null), `wal_pos` (not null), `embedding_id` (not null)

#### Metrics Tracked

| Metric | Meaning |
|---|---|
| `events_written` | Successful st_hipp_events INSERTs |
| `duplicates_skipped` | Idempotent skips (already exists) |
| `pipeline_tracked` | st_pipeline_processed INSERTs |
| `embeddings_written` | Successful st_vec INSERTs |
| `embeddings_skipped` | No embedding data (PENDING for P08) |
| `write_failures` | Any storage operation failure |

#### What M16 Does NOT Do

- Does NOT assemble or transform the row (M13 does that)
- Does NOT compute embeddings (M22 extracts from UltraBERT cache)
- Does NOT emit events to the bus (M17 does that)
- Does NOT batch writes (single event per call for transactional atomicity)
- Does NOT retry on ValueError/TypeError (these are structural bugs, not transient)
- Does NOT use FAISS (ADR-K003: all vectors stored in pgvector VECTOR(768) natively)

#### Architectural Significance

M16 is the DURABILITY BOUNDARY for P02. Key properties:

1. **3-table atomic**: st_hipp_events + st_vec + st_pipeline_processed in correct FK order
2. **M23 merged**: ADR-K003 v1.2 eliminated the separate embedding write stage for FK safety
3. **Graceful embedding degradation**: Missing embedding → PENDING status, P08 backfill recovers
4. **Syscall-mediated**: All storage via `context.syscalls.*` — no direct SQL, enforces capability security
5. **Idempotent by design**: PK constraints + pipeline_processed dedup → safe for retry/replay
6. **pgvector native**: 768-dim float list passed directly to VECTOR(768) column (no FAISS, no binary encoding)

---

### 23.16 M17 `core.event_emitter` — Outbox Event Emission (stage_80)

| Property | Value |
|---|---|
| **Contract** | `core.event_emitter.v1.yaml` |
| **Source** | `k0/modules/core/event_emitter.py` (536 lines) |
| **Stage** | 80 (depends on stage_70 / M16 storage commit) |
| **Latency Budget** | <10ms P95 (batch outbox write, no external I/O) |
| **MW Dependency** | None (reads enrichments assembled by prior stages) |
| **UltraBERT Dependency** | None |
| **Idempotent** | Yes (SHA256 fingerprint per event per envelope) |
| **Side Effects** | write:st_outbox (6 event rows) |

#### What It Does

M17 is the FINAL stage of P02. After M16 commits the memory to storage, M17 publishes 6 downstream events to `st_outbox` using the transactional outbox pattern. These events fan out to 5 downstream pipelines and observability.

#### Events Emitted (6 types)

| # | Topic | op_kind | Consumer | Payload Summary |
|---|---|---|---|---|
| 1 | `workspace.wm.updated` | WORKSPACE_WM_UPDATED | P04 (Working Memory) | envelope_id, working_memory snapshot |
| 2 | `affect.analyzed` | AFFECT_ANALYZED | P06 (Learning Pipeline) | valence, arousal, dominant_emotions, band |
| 3 | `space.resolution` | SPACE_RESOLVED | P07 (Access Control) | space_id, visibility_scope, owner_id |
| 4 | `embedding.enqueue` | EMBEDDING_QUEUED | P08 (Vector Generation) | embedding_id, embedding_status |
| 5 | `hippocampus.pattern_separated` | PATTERN_SEPARATED | P03 (Consolidation) | event_id, simhash_hex, embedding_id, entities_count |
| 6 | `write.complete` | PIPELINE_COMPLETED | Observability | pipeline="p02_write", modules_executed list |

#### Event Construction Flow

```
envelope.enrichments (from prior stages)
  |
  +--extract_flat_enrichments() if no nested enrichments
  |    (Phase 1 migration fallback)
  |
  +--Build 6 events, each with:
  |    tenant_id, space_id, driver="outbox_sse"
  |    op_kind (event type for SSE topic mapping)
  |    payload (event-specific data from enrichments)
  |    fingerprint = SHA256(space_id::topic::envelope_id)
  |    wal_pos = 0
  |
  +--syscalls.outbox_emit_batch(events)
  |    Single batch write to st_outbox
  |    Returns {events_inserted: N}
  |
  +--Return enriched envelope with event_emitter result
```

#### Fingerprint-Based Idempotency

Each event gets a SHA256 fingerprint computed as:

```
fingerprint = SHA256("{space_id}::{topic}::{envelope_id}")
```

This ensures:

- Same envelope processed twice → same fingerprints → st_outbox dedup
- Different events for same envelope → different topics → different fingerprints
- 64-character hex string per event

#### Enrichment Extraction (Phase 1 Migration)

M17 supports two enrichment layouts:

1. **Nested** (target): `envelope.enrichments.{module_name}.{field}`
2. **Flat** (Phase 1 fallback): `extract_flat_enrichments(envelope)` from `k0.runtime.enrichment_helpers`

If neither is available, M17 logs a warning and returns the envelope unmodified (no events emitted, no error).

#### Error Handling

| Error | Policy | Behavior |
|---|---|---|
| Outbox write failed | Retry (3 attempts) | Retry with backoff, then re-raise for pipeline error handler |
| Serialization failed | Drop | Log error, but individual event failure → other events still emitted |
| Topic not registered | Alert + drop | Ops alert if BusDispatcher lacks topic registration |
| Missing enrichments | Warn + partial | Emits events with partial data (non-fatal) |

#### What M17 Does NOT Do

- Does NOT write to st_hipp_events (M16 already did that)
- Does NOT modify the memory row
- Does NOT call external APIs (purely local st_outbox writes)
- Does NOT control downstream pipeline execution (events are async, consumers poll st_outbox)
- Does NOT guarantee downstream processing order (topics are independent)
- Does NOT emit telemetry by default (`enable_telemetry_event` defaults to False in code, True in contract)

#### Architectural Significance

M17 is the EVENT FAN-OUT point for P02. Key properties:

1. **Transactional outbox**: Events written to st_outbox, not directly to bus — guarantees at-least-once delivery
2. **6-event fan-out**: Single P02 completion triggers 5 downstream pipelines + observability
3. **Fingerprint idempotency**: SHA256(space::topic::envelope) prevents duplicate event emission on replay
4. **Batch emission**: All 6 events in single `outbox_emit_batch` syscall for efficiency
5. **Phase 1 migration aware**: Falls back to flat enrichment extraction when nested structure unavailable
6. **Non-blocking terminal**: If M17 fails, the memory is already stored (M16 committed) — worst case is delayed downstream processing

---
---

## Part V — End-to-End Action Map (MW + P02 + P08 + P03)

> Synthesized from Parts I-IV. Every action is traceable to a gap ID (T1-T8, S1-S5, X1-X4) from Section 11.

---

### 24. Cross-System Dependency Graph

```
K1 Memory Writer                    Bridge                     K0 P02 Pipeline                      K0 P08        K0 P03
================                    ======                     ===============                      ======        ======

[T5] ExtractionContext              [T6] EnvelopeBuilder       [M08] temporal_profile               [M25]         [R2]
  current_turn.timestamp_ms  --->     ts = turn_timestamp  -->   conversation_anchor_ms (NEW)        backfill      episode
  (already exists, unused)            (currently now_utc())      STOP overwriting event_time_utc     (no change)   grouping
                                                                                                                  (uses fixed
[T1] MemoryAtom.temporal_links      body.temporal_links  --->  [M02] parse temporal_links[]                        event_time)
  List[TemporalLink] (NEW)            passthrough                temporal_links_json (NEW)
                                                                                                    [M28]
[T3] TemporalLinkType enum                                    [M08] link type propagation            integrity
  CONVERSATION | MENTIONED |                                     write link_type per temporal ref     (add col
  INFERRED | DEADLINE                                                                                 checks)
                                                               [M13] builders.hipp_events_row
[S1] PlaceResolver (NEW)           body.place_id  --------->    Group 5 +conversation_anchor_ms
  location_name+type -> place_id                                 Group 5 +temporal_links_json
                                                                 Group 6 +place_id
[X4] LLM prompt update
  ask for multiple temporal refs                               [M16] hipp_events_writer
                                                                 writes new columns (schema migr.)
[T7] Temporal=None safety
  envelope.ts always present                                   [M17] event_emitter
                                                                 Event#5 payload +conversation_anchor_ms --> P03
```

---

### 25. Memory Writer (K1) — Exact Actions

#### 25.1 STEP 1 — Foundation (T5 + T6 + T7) — MUST

| # | Gap | File | Change | Detail |
|---|-----|------|--------|--------|
| MW-A1 | T5 | `k1/memory_writer/types.py` | **No change** | `ExtractionContext.current_turn.timestamp_ms` already exists. Verify it is populated from `TurnCompletePayload.timestamp_ms`. |
| MW-A2 | T5 | `k1/memory_writer/pipeline/envelope_stage.py` (or equivalent envelope builder in MW) | **Add** `turn_timestamp_ms` to MWEnvelope body | Currently `MWEnvelope` wraps `MemoryAtom` but does NOT include the turn's `timestamp_ms`. Add `turn_timestamp_ms: int` field to envelope body dict so K0 P02 can read it. |
| MW-A3 | T6 | `bridge/core/envelope_builder.py` | **Fix** `EnvelopeBuilder.build()` | Line: `ts = datetime.now(timezone.utc).isoformat()`. Change to accept optional `event_time_ms: int | None` parameter. When provided, convert to ISO 8601 UTC. When None, fall back to `now_utc()`. This ensures`envelope.ts` reflects conversation time, not bridge processing time. |
| MW-A4 | T6 | `bridge/core/envelope_builder.py` | **Wire** turn timestamp through | `BridgeCommandPort.submit_batch()` (or similar caller) must pass `turn_timestamp_ms` from the MW batch to `EnvelopeBuilder.build(event_time_ms=...)`. |
| MW-A5 | T7 | `k1/memory_writer/pipeline/envelope_stage.py` | **Guard** Temporal=None | When `MemoryAtom.temporal is None`, the envelope body must still carry `turn_timestamp_ms` so M08 has a conversation anchor. Currently if temporal is None, resolved_epoch_ms is absent and M08 falls through to `envelope.ts` — which is `now_utc()` (broken by T6-current). After MW-A3 fix, `envelope.ts` will be correct, so this guard becomes: verify that envelope body ALWAYS contains `turn_timestamp_ms` regardless of whether `MemoryAtom.temporal` is populated. |

#### 25.2 STEP 2 — Multi-Link Temporal (T1 + T3 + T2 + X4) — MUST/SHOULD

| # | Gap | File | Change | Detail |
|---|-----|------|--------|--------|
| MW-B1 | T3 | `k1/memory_writer/types.py` | **Add** `TemporalLinkType` enum | `class TemporalLinkType(str, Enum): CONVERSATION_TIME = "CONVERSATION_TIME"; MENTIONED_TIME = "MENTIONED_TIME"; INFERRED_TIME = "INFERRED_TIME"; DEADLINE = "DEADLINE"` |
| MW-B2 | T1 | `k1/memory_writer/types.py` | **Add** `TemporalLink` dataclass | `@dataclass(frozen=True) class TemporalLink: link_type: TemporalLinkType; epoch_ms: int; text_mention: Optional[str] = None; precision: Optional[str] = None; is_backdated: bool = False` |

> **Reconciliation Note — TemporalLinkType Taxonomy (MW-B1 vs Section 11 T3 vs Section 2.5)**
>
> Three taxonomies appear in this document:
>
> | Source | Values | Perspective |
> |--------|--------|-------------|
> | Section 2.5 (orientation field) | PAST, PRESENT, FUTURE, RECURRING, CONDITIONAL | Atom-level temporal direction |
> | Section 11 T3 (link_type field) | RETROSPECTIVE, PROSPECTIVE, CONCURRENT, HABITUAL, CONTEXTUAL, CONDITIONAL | Memory-science per-link classification |
> | Part V MW-B1 (authoritative) | CONVERSATION_TIME, MENTIONED_TIME, INFERRED_TIME, DEADLINE | K0-pipeline-facing per-link classification |
>
> **Resolution**: Part V MW-B1 is authoritative for implementation. The Section 11/T3 taxonomy
> (RETROSPECTIVE, PROSPECTIVE, etc.) was the initial gap analysis using memory-science terminology.
> MW-B1 reframes these into pipeline-actionable categories:
>
> - **CONVERSATION_TIME** = when the turn happened (always present, epoch_ms = conversation_anchor_ms)
> - **MENTIONED_TIME** = explicit past/future reference ("yesterday", "next Friday") — covers RETROSPECTIVE + PROSPECTIVE
> - **INFERRED_TIME** = NER-extracted or heuristic-resolved temporal reference — covers CONTEXTUAL ("during college")
> - **DEADLINE** = future commitment with accountability — covers PROSPECTIVE subset with obligation semantics
>
> HABITUAL ("every Friday") is represented as multiple MENTIONED_TIME links with a
> `precision: "RECURRING"` marker, not a separate link_type. CONDITIONAL ("if it rains")
> is captured via `text_mention` context, not a separate link_type — conditionals are
> low-confidence temporal references whose epoch_ms is speculative.
>
> Section 2.5 `orientation` remains as the atom-level dominant direction (see T4 resolution
> in Section 26.7).
| MW-B3 | T1 | `k1/memory_writer/types.py` | **Add** field to `MemoryAtom` | Add `temporal_links: List[TemporalLink] = field(default_factory=list)` to MemoryAtom. Keep existing `temporal: Optional[Temporal]` for backward compatibility during migration. |
| MW-B4 | T2 | MW-B2 above | **Included** | `precision` field on TemporalLink covers T2 (values: "DAY", "HOUR", "MINUTE", "APPROXIMATE"). |
| MW-B5 | X4 | `k1/memory_writer/pipeline/writer_agent.py` (LLM prompt) | **Update** extraction prompt | Instruct LLM to extract multiple temporal references per atom. Each reference yields a TemporalLink with link_type + epoch_ms + text_mention. Example prompt addition: "For each temporal reference mentioned (e.g., 'yesterday', 'next Tuesday', 'last Christmas'), return a separate temporal_link with the resolved time and the type of reference." |
| MW-B6 | T1 | `k1/contracts/schemas/memory_writer/memory_atom.v2.schema.json` | **Add** `temporal_links` schema | Add JSON Schema definition for `temporal_links` array of objects, each with `link_type`, `epoch_ms`, `text_mention`, `precision`, `is_backdated`. |
| MW-B7 | T1 | `k1/memory_writer/invariants.py` | **Add** validation | Validate each TemporalLink: epoch_ms > 0, link_type in enum, precision in allowed set. Max 8 links per atom. |

> **Deprecation Timeline for `temporal` and `temporal_orientation` (from Section 14)**
>
> Section 14 specifies that `temporal: Optional[Temporal]` and `temporal_orientation`
> are deprecated by `temporal_links`. Deprecation phases:
>
> - **Phase 2 (this scope)**: MW-B3 adds `temporal_links` alongside existing `temporal`.
>   Both are populated during transition. `temporal_orientation` continues to be set
>   from dominant link_type. K0 P02 M08 reads `temporal_links` when present, falls back
>   to `temporal` for pre-migration envelopes.
> - **Phase 2 + 1 release**: Stop populating `temporal` on new MemoryAtoms. Set
>   `temporal = None`. Keep field on dataclass for backward compat (old atoms in
>   st_hipp_events still have it serialized). `temporal_orientation` stops being set;
>   derive from `temporal_links[0].link_type` if needed.
> - **Phase 2 + 2 releases**: Remove `temporal: Optional[Temporal]` and
>   `temporal_orientation` from `MemoryAtom` dataclass. Bump schema to v4 or remove
>   from v3 with `additionalProperties: true` tolerance. K0 P02 M08 stops checking
>   for `temporal` fallback.

#### 25.3 STEP 3 — Place Identity (S1) — SHOULD

| # | Gap | File | Change | Detail |
|---|-----|------|--------|--------|
| MW-C1 | S1 | `k1/memory_writer/types.py` | **Add** `place_id: Optional[str] = None` to MemoryAtom | Stable place identifier derived from location_name + location_type. Format: `place_{hash8}` where hash8 = first 8 chars of SHA256(normalized_location_name + "::" + location_type). |
| MW-C2 | S1 | `k1/memory_writer/pipeline/writer_agent.py` or new `place_resolver.py` | **Add** PlaceResolver | Service that takes `(location_name, location_type)` and returns stable `place_id`. Uses normalized lowercase + stripped whitespace for deterministic hashing. |
| MW-C3 | S1 | `k1/memory_writer/pipeline/envelope_stage.py` | **Wire** place_id | After LLM extraction, if `atom.location_name` is not None, call `PlaceResolver.resolve(atom.location_name, atom.location_type)` and set `atom.place_id`. Include in envelope body. |
| MW-C4 | S1 | `k1/contracts/schemas/memory_writer/memory_atom.v2.schema.json` | **Add** `place_id` field | `"place_id": {"type": "string", "pattern": "^place_[a-f0-9]{8}$", "description": "Stable place identifier"}` |

#### 25.4 STEP 4 — Enrichment (T8 + S2 + S3) — SHOULD/COULD

| # | Gap | File | Change | Detail |
|---|-----|------|--------|--------|
| MW-D1 | T8 | `k1/memory_writer/pipeline/writer_agent.py` | **Add** extraction_sequence | When LLM returns multiple atoms per turn, assign `extraction_sequence: int` (0-based) to preserve ordering. Set on each MemoryAtom before envelope stage. |
| MW-D2 | T8 | `k1/memory_writer/types.py` | **Add** field to MemoryAtom | `extraction_sequence: Optional[int] = None` |
| MW-D3 | S2 | `k1/memory_writer/types.py` | **Add** `location_hierarchy: Optional[Dict[str, str]] = None` to MemoryAtom | Dict with keys like `room`, `building`, `neighborhood`, `city`, `region`. Populated when LLM extracts hierarchical location context. |
| MW-D4 | S3 | `k1/memory_writer/types.py` | **No new field needed** | Spatial transitions are detected by P03 by comparing consecutive events' place_id. MW only needs to consistently emit place_id (covered by MW-C1). |

#### 25.5 Bridge — Exact Actions (T6)

MW-A3 and MW-A4 target the Bridge layer specifically. Extracted here for clarity since
the Bridge is a separate codebase (`bridge/`) from the K1 Memory Writer (`k1/`).

| # | Gap | File | Change | Detail |
|---|-----|------|--------|--------|
| MW-A3 | T6 | `bridge/core/envelope_builder.py` | **Fix** `EnvelopeBuilder.build()` | **Current code** (line ~142): `ts = datetime.now(timezone.utc).isoformat()`. Add optional `event_time_ms: Optional[int]` parameter to `build()`. When provided, convert to ISO 8601 UTC. When None, fall back to `now_utc()`. This ensures `envelope.ts` reflects conversation time, not bridge processing time. |
| MW-A4 | T6 | `bridge/core/envelope_builder.py` | **Wire** turn timestamp | The caller of `build()` (BridgeCommandPort or equivalent) must pass `turn_timestamp_ms` from the MW batch to `EnvelopeBuilder.build(event_time_ms=...)`. |

**Current `build()` signature** (verified from source):

```python
def build(self, *, topic: str, body: dict, schema_uri: str,
          band: str | None = None, trace_id: str | None = None) -> dict:
```

**After fix**:

```python
def build(self, *, topic: str, body: dict, schema_uri: str,
          band: str | None = None, trace_id: str | None = None,
          event_time_ms: int | None = None) -> dict:
    if event_time_ms is not None:
        ts = datetime.fromtimestamp(event_time_ms / 1000, tz=timezone.utc).isoformat().replace("+00:00", "Z")
    else:
        ts = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
```

---

### 26. P02 Pipeline Modules — Exact Actions

#### 26.1 M08 `temporal_profile` — CRITICAL BUG FIX (T5 + T6 + T7)

| # | Gap | Source | Change | Detail |
|---|-----|--------|--------|--------|
| P02-A1 | T7 | `k0/modules/temporal/temporal_profile.py` | **REMOVE** Priority 1 overwrite | Priority 1 currently: `if resolved_epoch_ms: event_time_utc = resolved_epoch_ms / 1000`. **DELETE THIS LINE.** `event_time_utc` must ALWAYS reflect conversation anchor time, never referred time. This is THE critical bug fix. |
| P02-A2 | T5 | Same file | **ADD** conversation_anchor_ms output | New output field: `conversation_anchor_ms = int(envelope.ts_parsed * 1000)` where `ts_parsed` is the ISO 8601 `envelope.ts` converted to epoch seconds. If `envelope.body.turn_timestamp_ms` is available (from MW-A2), prefer that. Fallback chain: `body.turn_timestamp_ms` -> `envelope.ts` -> `now_utc()`. |
| P02-A3 | T5 | Same file | **ENSURE** event_time_utc = conversation anchor | `event_time_utc` = conversation_anchor_ms / 1000 (seconds). This replaces the old Priority 1 logic. The field now ALWAYS reflects when the conversation happened, not what time was mentioned. |
| P02-A4 | T1 | Same file | **PROPAGATE** temporal_links | If `envelope.body.temporal_links` exists (from MW-B3), read and propagate as `temporal_links_json = json.dumps(temporal_links)`. If absent, set `temporal_links_json = "[]"`. |
| P02-A5 | — | Same file | **KEEP** resolved_epoch_ms logic | The existing resolved_epoch_ms fallback chain (body.temporal.resolved_epoch_ms -> NER temporal -> event_time -> envelope.ts -> now) remains for the `temporal_resolved_epoch_ms` column. This column stores referred-to time. Just stop it from overwriting `event_time_utc`. |

**Before/After data flow for M08:**

```
BEFORE (buggy):
  event_time_utc     = resolved_epoch_ms / 1000   <-- WRONG (referred time)
  temporal_resolved   = resolved_epoch_ms           <-- referred time (correct)
  conversation_anchor = (did not exist)

AFTER (fixed):
  event_time_utc     = conversation_anchor_ms / 1000  <-- conversation time (correct)
  temporal_resolved   = resolved_epoch_ms              <-- referred time (unchanged)
  conversation_anchor = turn_timestamp_ms OR envelope.ts  <-- NEW column, explicit anchor
```

#### 26.2 M02 `semantic_project` — Multi-Temporal Parsing (T1)

| # | Gap | Source | Change | Detail |
|---|-----|--------|--------|--------|
| P02-B1 | T1 | `k0/modules/semantic/semantic_project.py` | **ADD** temporal_links extraction | Currently reads `body.temporal.resolved_epoch_ms` (single value). Add: if `body.temporal_links` exists and is a list, extract all links. Each link has `{link_type, epoch_ms, text_mention, precision, is_backdated}`. |
| P02-B2 | T1 | Same file | **ADD** NER temporal multi-link | Current NER already extracts DATE/TIME entities. When `body.temporal_links` is absent (legacy path), convert NER temporal entities into TemporalLink-shaped dicts with `link_type="INFERRED_TIME"`. This maintains backward compatibility for pre-MW-v2.1 envelopes. |
| P02-B3 | S1 | Same file | **PASSTHROUGH** place_id | If `body.place_id` exists, include in M02 output as `place_id`. M02 already passes through location_name and location_type; add place_id to that set. |

#### 26.3 M13 `builders.hipp_events_row` — New Column Mapping

| # | Gap | Source | Change | Detail |
|---|-----|--------|--------|--------|
| P02-C1 | T5 | `k0/modules/builders/hipp_events_row.py` | **Group 5 mapper**: Add `conversation_anchor_ms` | Read from M08 enrichment output. Map to new `conversation_anchor_ms BIGINT` column. Required NOT NULL — add to validation list. |
| P02-C2 | T1 | Same file | **Group 5 mapper**: Add `temporal_links_json` | Read from M08 enrichment output (or M02 if M08 delegates). Map to new `temporal_links_json JSONB` column. Default `"[]"`. |
| P02-C3 | S1 | Same file | **Group 6 mapper**: Add `place_id` | Read from M02 enrichment output (passthrough from MW). Map to new `place_id VARCHAR(64)` column. Nullable. |
| P02-C4 | T8 | Same file | **Group 12 mapper**: Add `extraction_sequence` | Read from `envelope.body.extraction_sequence`. Map to new `extraction_sequence SMALLINT` column. Nullable. |
| P02-C5 | S2 | Same file | **Group 6 mapper**: Add `location_hierarchy_json` | Read from `envelope.body.location_hierarchy`. Map to new `location_hierarchy_json JSONB` column. Nullable, default NULL. |
| P02-C6 | — | Same file | **Validation**: Update required fields | Add `conversation_anchor_ms` to the 17 required NOT NULL fields list (becomes 18). |

#### 26.4 M16 `core.hipp_events_writer` — No Logic Changes

| # | Gap | Source | Change | Detail |
|---|-----|--------|--------|--------|
| P02-D1 | — | `k0/modules/core/hipp_events_writer.py` | **No code change** | M16 writes whatever M13 assembles. New columns flow through automatically once M13 maps them and the schema migration is applied. |
| P02-D2 | — | `k0/kernel/syscalls.py` | **Verify** `hipp_events_upsert` | Confirm the syscall uses `**row` spread or dynamically builds INSERT columns from the dict keys. If it uses a hardcoded column list, add new columns. |

#### 26.5 M17 `core.event_emitter` — P03 Event Enrichment

| # | Gap | Source | Change | Detail |
|---|-----|--------|--------|--------|
| P02-E1 | T5 | `k0/modules/core/event_emitter.py` | **Enrich** Event #5 payload | Event #5 (`hippocampus.pattern_separated` -> P03) currently carries: `event_id, simhash_hex, embedding_id, entities_count`. ADD: `conversation_anchor_ms` to payload. This gives P03 R2 the correct temporal anchor for episode clustering without re-querying st_hipp_events. |
| P02-E2 | T1 | Same file | **Optionally** add temporal_links_json | If P03 R2 needs temporal link data for multi-temporal episode assignment, include in Event #5 payload. Otherwise P03 reads from st_hipp_events directly. Decision: DEFER (P03 can query). |

#### 26.6 M05 / M07 / M09 / M10 / M11 / M12 / M15 / M01 / M22 — No Changes

| Module | Reason |
|--------|--------|
| M01 pattern_separate | SimHash/MinHash — no temporal/spatial dependency |
| M05 resolve_visibility | ACL intersection — no temporal/spatial dependency |
| M07 family_graph_resolve | Social resolution — could optionally receive place_id for contextual resolution, but NOT required for this scope |
| M09 device_profile | Pure string parser — no temporal/spatial dependency |
| M10 ingress_classify | Activity classification — no temporal/spatial dependency |
| M11 retention_lookup | Matrix lookup — no temporal/spatial dependency |
| M12 geo_metadata | Privacy-preserving field copy — no change (place_id comes from MW, not geo) |
| M15 spatial_minimal | Geohash truncation — no change (operates on existing geo fields) |
| M22 extract_from_cache | UltraBERT cache — no temporal/spatial dependency |
| M04 affect.analyze | Trust-then-fill affect — no temporal/spatial dependency |
| M06 salience.score | Convergence formula — no temporal/spatial dependency |

#### 26.7 Explicitly Resolved/Deferred Gaps Not Covered by Action Items Above

The following gaps from Section 11 are NOT represented by explicit action IDs in Part V
because they are resolved by other actions, subsumed, or consciously deferred. Listed
here for traceability so no gap is silently dropped.

| Gap | Title | Resolution | Rationale |
|-----|-------|------------|-----------|
| T4 | TemporalOrientation enum too coarse | **Subsumed by T3 (MW-B1)** | `TemporalOrientation` (PAST / ONGOING / FUTURE_COMMITMENT) remains as the atom-level dominant temporal direction. Per-link typing via `TemporalLinkType` (MW-B1) replaces the need for an expanded atom-level enum. The atom-level orientation is derived from the dominant `link_type` across all `temporal_links`. No schema or code change needed for T4 specifically — it is covered by T3's implementation. |
| S3 | No spatial transitions | **Deferred to P03 inference (MW-D4)** | Section 13 Step 4 lists S3 as an MW enrichment (add `transition_from`, `transition_mode` to `SpatialContext`). Part V MW-D4 instead resolves S3 as a P03 concern: consecutive events with different `place_id` values (provided by MW-C1) allow P03 to infer spatial transitions without MW emitting explicit transition fields. No new MW fields needed. If future requirements demand per-atom transition metadata (e.g., "drove" vs "walked"), MW-D4 can be promoted to add `transition_from: Optional[str]` to `MemoryAtom`. |
| S4 | No spatial familiarity tracking | **Deferred to K0 P02** | Spatial familiarity (FIRST_VISIT / OCCASIONAL / REGULAR / DAILY) requires counting past visits to a `place_id` in `st_hipp_events`. MW has no access to the events table and cannot compute visit counts. This is a K0 P02 or P03 enrichment that depends on S1 (`place_id`) being implemented first. Phase 3+ scope. |
| S5 | No location functional dimension | **Deferred to LLM prompt update** | `location_function` ("eat", "sleep", "work", "play") is an activity affordance that the LLM can infer from context. Addressed indirectly by MW-B5 (multi-temporal prompt expansion) which already instructs the LLM to provide richer spatial context. A dedicated prompt instruction for `location_function` can be added as a COULD in a future MW prompt revision. No schema or code change needed — the field would be a new optional on `MemoryAtom` if/when implemented. |

---

### 27. P08 Pipeline — Exact Actions

#### 27.1 Impact Assessment

P08 is **minimally impacted** by temporal/spatial enhancements because:

- P08 M25 (backfill) reads `text` + `event_id` from st_hipp_events to generate embeddings. New temporal/spatial columns are irrelevant to embedding generation.
- P08 M27 (cleanup) deletes orphaned st_vec rows by FK check. No column dependency.
- P08 trigger condition remains `embedding_status = 'PENDING'` — unchanged.
- P08 is scheduler-driven, not affected by new event payloads.

#### 27.2 Actions

| # | Gap | Source | Change | Detail |
|---|-----|--------|--------|--------|
| P08-A1 | — | `k0/contracts/pipelines/p08_embedding_management.v3.yaml` | **No contract change** | 3-stage DAG (M25 backfill, M27 cleanup, M28 integrity) unchanged. Triggers unchanged. |
| P08-A2 | — | M25 backfill module | **No code change** | Backfill reads `text`, `event_id`, `embedding_status` from st_hipp_events. New columns are not inputs to embedding generation. |
| P08-A3 | — | M27 cleanup module | **No code change** | Orphan detection uses FK relationship (st_vec.event_id -> st_hipp_events.event_id). Column additions don't affect this. |
| P08-A4 | T5 | M28 integrity module | **OPTIONAL**: Add column validation | Add optional check: `conversation_anchor_ms > 0` for all events with `embedding_status = 'READY'`. This catches events that were written before the migration and have `conversation_anchor_ms = 0` (default). These can be flagged for temporal backfill. |
| P08-A5 | — | `k0/pipelines/p03/ops/p08_circuit.py` | **No code change** | P08 circuit breaker for P03 R4 entity embedding is independent of temporal/spatial columns. |

---

### 28. Schema Migration — st_hipp_events

#### 28.1 New Columns

| Column | Type | Nullable | Default | Gap | Owner Module | Purpose |
|--------|------|----------|---------|-----|-------------|---------|
| `conversation_anchor_ms` | BIGINT | NOT NULL | 0 | T5 | M08 -> M13 | Turn timestamp in epoch_ms. The authoritative "when did this conversation happen" anchor. |
| `temporal_links_json` | JSONB | NOT NULL | '[]' | T1 | M08/M02 -> M13 | Array of `{link_type, epoch_ms, text_mention, precision, is_backdated}` objects. |
| `place_id` | VARCHAR(64) | YES | NULL | S1 | MW -> M02 -> M13 | Stable place identifier `place_{hash8}`. Enables spatial grouping without string matching. |
| `extraction_sequence` | SMALLINT | YES | NULL | T8 | MW -> M13 | Ordering of multiple atoms extracted from a single turn. |
| `location_hierarchy_json` | JSONB | YES | NULL | S2 | MW -> M13 | Hierarchical location context `{room, building, city, ...}`. |

#### 28.2 Zombie Column Deprecation (from Section 20)

| Column | Issue | Action |
|--------|-------|--------|
| `cognitive_trace_id` (alias col) | Issue 0046 duplicate of `cognitive_trace_id` PK-adjacent field | DROP after confirming no active readers |
| `reconciliation_decision` | P03 reconciliation removed in M4 | DROP |
| `truth_match_id` | P03 reconciliation removed in M4 | DROP |
| `truth_match_similarity` | P03 reconciliation removed in M4 | DROP |
| `consolidated_at` | P03 reconciliation removed in M4 | DROP |
| `intent_category` | Issue 0046 duplicate — `intent_ultrabert` (0060) and `intent_type` (0073) are authoritative | DROP |
| `ingress_category` | Issue 0046 duplicate — `activity_type_ultrabert` (0060) is authoritative | DROP |

#### 28.3 Migration SQL (forward)

```sql
-- Step 1: Add new columns
ALTER TABLE st_hipp_events
  ADD COLUMN conversation_anchor_ms BIGINT NOT NULL DEFAULT 0,
  ADD COLUMN temporal_links_json JSONB NOT NULL DEFAULT '[]'::jsonb,
  ADD COLUMN place_id VARCHAR(64) DEFAULT NULL,
  ADD COLUMN extraction_sequence SMALLINT DEFAULT NULL,
  ADD COLUMN location_hierarchy_json JSONB DEFAULT NULL;

-- Step 2: Backfill conversation_anchor_ms from event_time_utc for existing rows
-- (event_time_utc is in SECONDS, conversation_anchor_ms is MILLISECONDS)
UPDATE st_hipp_events
SET conversation_anchor_ms = (event_time_utc * 1000)::BIGINT
WHERE conversation_anchor_ms = 0
  AND event_time_utc > 0;

-- Step 3: Create index for place_id grouping
CREATE INDEX CONCURRENTLY idx_hipp_place_id
ON st_hipp_events (place_id)
WHERE place_id IS NOT NULL;

-- Step 4: Create index for conversation_anchor_ms range queries (P03 R2 episode grouping)
CREATE INDEX CONCURRENTLY idx_hipp_conversation_anchor
ON st_hipp_events (conversation_anchor_ms);
```

#### 28.4 Migration SQL (zombie cleanup — separate migration)

```sql
-- ONLY after confirming zero active readers via grep/usage analysis
ALTER TABLE st_hipp_events
  DROP COLUMN IF EXISTS reconciliation_decision,
  DROP COLUMN IF EXISTS truth_match_id,
  DROP COLUMN IF EXISTS truth_match_similarity,
  DROP COLUMN IF EXISTS consolidated_at,
  DROP COLUMN IF EXISTS intent_category,
  DROP COLUMN IF EXISTS ingress_category;
```

#### 28.5 Unit Convention Fix (Documentation)

| Column | Current Unit | Correct Convention | Action |
|--------|-------------|-------------------|--------|
| `event_time_utc` | SECONDS (epoch float) | Suffix `_utc` implies ISO/seconds | **Document**: "epoch seconds as DOUBLE PRECISION" |
| `temporal_resolved_epoch_ms` | MILLISECONDS | Suffix `_ms` implies milliseconds | **Document**: "epoch milliseconds as BIGINT" |
| `conversation_anchor_ms` | MILLISECONDS | Suffix `_ms` implies milliseconds | New column, correct by design |

---

### 29. P03 Downstream Impact

P03 consolidation pipeline is the primary CONSUMER of P02 outputs. Key impacts:

#### 29.1 R2 Episode Grouping — MAJOR IMPROVEMENT

| Aspect | Before (buggy) | After (fixed) |
|--------|----------------|---------------|
| **Clustering anchor** | `event_time_utc` = referred time (e.g., "last Christmas" → Dec 25) | `event_time_utc` = conversation time (when user said it) |
| **Episode coherence** | Memories about past events scattered across wrong time clusters | Memories group by conversation session, with `temporal_links_json` preserving referred times |
| **Multi-temporal** | Single resolved_epoch_ms (latest overwrite wins) | Array of TemporalLinks, each with type + epoch + precision |

#### 29.2 P03 R0 Batch Selector — PROMOTED TO PHASE 1

P03-F4 from the original deferred list is promoted to Phase 1 because **V10 verification
("Events from same conversation session cluster together") requires R0 to load
`conversation_anchor_ms` and map it to `P03EventState.timestamp`**. Without this, R2
HDBSCAN still clusters on `event_time_utc` (which, after the M08 bug fix, IS the
conversation anchor in seconds) — so clustering improves passively. However, explicit
loading of the millisecond-precision `conversation_anchor_ms` column is needed for:

1. **Precision**: `event_time_utc` is DOUBLE PRECISION seconds (floating point drift).
   `conversation_anchor_ms` is BIGINT milliseconds (exact).
2. **Semantic clarity**: R0 code currently maps `event_time_utc -> timestamp`. After the
   fix, this works, but the intent is unclear. Explicitly loading `conversation_anchor_ms`
   makes the data flow self-documenting.
3. **Future P03-F1 readiness**: Temporal-spatial binding (X1) needs `conversation_anchor_ms`
   in `P03EventState` to correlate with `place_id`. Loading it now avoids a second R0 change.

**Source verification** (current code state):

- `k0/pipelines/p03/event_state.py`: `P03EventState` has `timestamp: int = 0` (used by R2)
  and `temporal_resolved_epoch_ms: float = 0.0`. No `conversation_anchor_ms` field exists.
- `k0/pipelines/p03/phases/r0_batch_selector.py`: SQL SELECT does NOT include
  `conversation_anchor_ms`. `_row_to_event_state()` maps
  `timestamp = event_time_utc * 1000` (with seconds-to-ms conversion).

| # | Gap | File | Change | Detail |
|---|-----|------|--------|--------|
| P03-G1 | T5 | `k0/pipelines/p03/event_state.py` | **Add** `conversation_anchor_ms: int = 0` field | New field on P03EventState dataclass. BIGINT epoch milliseconds. R2 will use this for episode clustering when available (non-zero), falling back to `timestamp` for pre-migration events. |
| P03-G2 | T5 | `k0/pipelines/p03/phases/r0_batch_selector.py` | **Add** `conversation_anchor_ms` to SQL SELECT | Add column to the R0 batch query (line ~540). Column exists after Schema 28.3 Step 1 migration. |
| P03-G3 | T5 | `k0/pipelines/p03/phases/r0_batch_selector.py` | **Map** in `_row_to_event_state()` | In the row-to-state mapping (line ~680+), add: `conversation_anchor_ms = row["conversation_anchor_ms"]`. When non-zero, also set `timestamp = conversation_anchor_ms` to override the event_time_utc-derived value. Fallback: if `conversation_anchor_ms == 0` (pre-migration row), keep existing `timestamp = event_time_utc * 1000` logic. |

#### 29.3 P03 Actions (DEFERRED — not in this scope but noted for coherence)

| # | Gap | Detail |
|---|-----|--------|
| P03-F1 | X1 | Temporal-spatial binding: Use `place_id` + `conversation_anchor_ms` to detect "same place, same time" episode clusters. |
| P03-F2 | X2 | Causal chains: Use `temporal_links_json` link_type=CONVERSATION_TIME ordering + entity overlap to infer cause-effect. |
| P03-F3 | X3 | Rehearsal detection: Compare `temporal_links_json` across events — if same `epoch_ms` with MENTIONED_TIME appears multiple times across different `conversation_anchor_ms`, it is rehearsal. |

---

### 30. Implementation Phasing

#### Phase 1: Foundation (MUST — blocks everything else)

| Order | Action IDs | System | Description |
|-------|-----------|--------|-------------|
| 1.1 | MW-A1..MW-A5 | K1 MW + Bridge | Turn timestamp propagation: ExtractionContext -> envelope body -> envelope.ts |
| 1.2 | P02-A1..P02-A3 | K0 P02 M08 | CRITICAL BUG FIX: Stop overwriting event_time_utc, add conversation_anchor_ms |
| 1.3 | P02-C1, P02-C6 | K0 P02 M13 | Map conversation_anchor_ms in Group 5, add to required fields |
| 1.4 | Schema 28.3 Step 1+2 | K0 DB | Add conversation_anchor_ms column + backfill existing rows |
| 1.5 | P02-D2 | K0 syscalls | Verify hipp_events_upsert handles new column |
| 1.6 | P02-E1 | K0 P02 M17 | Add conversation_anchor_ms to Event #5 payload |
| 1.7 | P03-G1..G3 | K0 P03 R0 | Add conversation_anchor_ms to P03EventState, R0 SQL SELECT, and _row_to_event_state() mapping (Section 29.2) |

**Verification**: After Phase 1, `event_time_utc` NEVER equals referred time. `conversation_anchor_ms` is populated for all new events. P03 R2 episode grouping immediately improves because R0 maps `conversation_anchor_ms` to `P03EventState.timestamp`.

#### Phase 2: Multi-Temporal (MUST)

| Order | Action IDs | System | Description |
|-------|-----------|--------|-------------|
| 2.1 | MW-B1..MW-B7 | K1 MW | TemporalLinkType enum, TemporalLink dataclass, MemoryAtom.temporal_links, schema, validation, LLM prompt |
| 2.2 | P02-B1..P02-B2 | K0 P02 M02 | Parse temporal_links array, NER multi-link fallback |
| 2.3 | P02-A4 | K0 P02 M08 | Propagate temporal_links_json |
| 2.4 | P02-C2 | K0 P02 M13 | Map temporal_links_json in Group 5 |
| 2.5 | Schema 28.3 Step 1 (temporal_links_json) | K0 DB | Add temporal_links_json column |

**Verification**: Envelopes carry multiple temporal references. M08 writes them to temporal_links_json. P03 can read multi-temporal data for X1/X2/X3 (deferred).

#### Phase 3: Place Identity (SHOULD)

| Order | Action IDs | System | Description |
|-------|-----------|--------|-------------|
| 3.1 | MW-C1..MW-C4 | K1 MW | PlaceResolver, place_id on MemoryAtom, schema update |
| 3.2 | P02-B3 | K0 P02 M02 | Passthrough place_id |
| 3.3 | P02-C3 | K0 P02 M13 | Map place_id in Group 6 |
| 3.4 | Schema 28.3 Step 1+3 (place_id) | K0 DB | Add place_id column + index |

**Verification**: Events with location data get stable place_id. P03 can group by place for X1 spatial binding.

#### Phase 4: Enrichment (SHOULD/COULD)

| Order | Action IDs | System | Description |
|-------|-----------|--------|-------------|
| 4.1 | MW-D1..MW-D3 | K1 MW | extraction_sequence, location_hierarchy |
| 4.2 | P02-C4..P02-C5 | K0 P02 M13 | Map extraction_sequence and location_hierarchy_json |
| 4.3 | Schema 28.3 Step 1 (remaining cols) | K0 DB | Add extraction_sequence + location_hierarchy_json |
| 4.4 | P08-A4 | K0 P08 M28 | Optional: conversation_anchor_ms integrity check |

#### Phase 5: Cleanup (COULD — independent, no blocker)

| Order | Action IDs | System | Description |
|-------|-----------|--------|-------------|
| 5.1 | Schema 28.4 | K0 DB | Drop 7 zombie columns after reader audit |
| 5.2 | P02-C6 update | K0 P02 M13 | Remove zombie column mappers from M13 |

---

### 31. Verification Checklist

| # | Check | Phase | Pass Criteria |
|---|-------|-------|---------------|
| V1 | event_time_utc reflects conversation time | 1 | Insert event mentioning "last Christmas". event_time_utc is today's timestamp, NOT Dec 25. |
| V2 | conversation_anchor_ms populated | 1 | All new events have conversation_anchor_ms > 0 and matching event_time_utc * 1000. |
| V3 | temporal_resolved_epoch_ms preserved | 1 | Event mentioning "last Christmas" has temporal_resolved_epoch_ms ~ Dec 25 epoch_ms. |
| V4 | envelope.ts = turn time | 1 | Bridge envelope `ts` field matches TurnCompletePayload.timestamp_ms (not now_utc()). |
| V5 | temporal_links_json populated | 2 | Event mentioning "yesterday and next Tuesday" has 2 entries in temporal_links_json with different link_types. |
| V6 | NER fallback multi-link | 2 | Legacy envelope (no body.temporal_links) generates inferred links from NER DATE entities. |
| V7 | place_id stable | 3 | Two events at "Mom's house" (restaurant) get identical place_id. |
| V8 | place_id deterministic | 3 | Same location_name + location_type always produces same place_id hash. |
| V9 | extraction_sequence ordering | 4 | Turn with 3 atoms has extraction_sequence 0, 1, 2 on stored events. |
| V10 | P03 R2 episode grouping | 1 | Events from same conversation session cluster together even when referring to different past times. |
| V11 | P08 backfill unaffected | 1 | PENDING events still get backfilled correctly. New columns don't break M25. |
| V12 | Zombie columns dropped | 5 | After migration, `SELECT reconciliation_decision FROM st_hipp_events` returns error. |

---

### 32. Summary Matrix — All Actions by System

| System | Actions | MUST | SHOULD | COULD | DEFER |
|--------|---------|------|--------|-------|-------|
| **K1 Memory Writer** | MW-A1..A5, MW-B1..B7, MW-C1..C4, MW-D1..D3 | 12 (A1-A5, B1-B7) | 6 (C1-C4, D1-D2) | 1 (D3) | 0 |
| **Bridge** | MW-A3, MW-A4 (Section 25.5) | 2 (A3-A4) | 0 | 0 | 0 |
| **K0 P02 M08** | P02-A1..A5 | 5 | 0 | 0 | 0 |
| **K0 P02 M02** | P02-B1..B3 | 2 (B1-B2) | 1 (B3) | 0 | 0 |
| **K0 P02 M13** | P02-C1..C6 | 2 (C1, C6) | 2 (C2, C3) | 2 (C4, C5) | 0 |
| **K0 P02 M16** | P02-D1..D2 | 1 (D2 verify) | 0 | 0 | 0 |
| **K0 P02 M17** | P02-E1..E2 | 1 (E1) | 0 | 0 | 1 (E2) |
| **K0 P08** | P08-A1..A5 | 0 | 0 | 1 (A4) | 0 |
| **K0 Schema** | Sec 28 | 2 (28.3 anchor + links) | 2 (28.3 place_id + idx) | 2 (28.3 seq + hier) | 1 (28.4 zombies) |
| **K0 P03** | P03-G1..G3 (Phase 1), P03-F1..F3 (deferred) | 3 (G1-G3) | 0 | 0 | 3 (F1-F3) |
| **TOTAL** | | **28** | **11** | **6** | **5** |

> **Note on Bridge row**: MW-A3 and MW-A4 are counted under K1 Memory Writer totals
> (since they share the MW-A prefix) AND listed separately under Bridge for visibility.
> They are NOT double-counted in the TOTAL row. The Bridge row is informational — it
> shows which MW actions target bridge code specifically.
>
> **Changes from original matrix**: P03-F4 promoted to P03-G1..G3 (3 MUST actions).
> P03-F1..F3 remain DEFERRED (3 items, down from 4). TOTAL MUST: 25 + 3 = 28.
> TOTAL DEFER: 6 - 1 = 5.
