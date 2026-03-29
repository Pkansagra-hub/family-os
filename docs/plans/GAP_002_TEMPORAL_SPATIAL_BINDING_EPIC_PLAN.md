# GAP-002: Temporal & Spatial Binding Model -- Epic Implementation Plan

**Date**: 2026-03-05
**Updated**: 2026-03-05
**Status**: PLANNING
**Priority**: CRITICAL (Architectural)
**Pipeline Scope**: K1 Memory Writer, K0 P02 M08, K0 P03 R0/R2, Bridge, st_hipp_events schema
**Branch**: `k1-Kernel-POC`
**Discovery Source**: `docs/architecture/gaps/GAP_002_TEMPORAL_SPATIAL_MEMORY_MODEL.md`

---

## Implementation Status Summary

| Component | Status | Notes |
|-----------|--------|-------|
| Discovery & Gap Audit (GAP-002 Sections 1-22) | DONE | Full audit: 8 temporal gaps, 5 spatial gaps, 4 cross-cutting gaps |
| Milestone 1: Conversation Anchor Fix (P0) | TODO | M08 refactor + K1 turn timestamp propagation |
| Milestone 2: Multi-Link Temporal Model (P1) | TODO | TemporalLink dataclass + schema v2.1 + LLM prompt |
| Milestone 3: Spatial Identity (P2) | TODO | PlaceResolver + place_id + familiarity |
| Milestone 4: Per-Atom Signal Enrichment (P3) | TODO | Extraction ordering + spatial transitions + hierarchy |
| Milestone 5: Cross-Episode Narrative Linking (P4) | TODO | Cross-episode threads + goal arcs |

---

## Executive Summary

This epic implements the temporal and spatial binding model defined in GAP-002. The current
architecture flattens human memory's multi-dimensional temporal and spatial structure into
single-value columns. M08 overwrites conversation time with referred time, destroying episode
formation. The system supports only one temporal reference per atom, has no stable place
identity, and lacks spatial transitions.

**Critical Dependency**: Milestone 1 (P0) unblocks everything. M08 currently overwrites
`event_time_utc` (conversation anchor) with `temporal_resolved_epoch_ms` (referred time)
when Priority 1 fires. This breaks R2 episode boundaries for any event with a temporal
expression ("yesterday", "next Friday", etc.).

**Architecture Decisions Required**:

- ADR for Option A+C combined approach (M08 refactor + K1 timestamp propagation)
- ADR for MemoryAtom schema v2.1 (additive, backward compatible)
- ADR for temporal_links JSONB storage model

---

## Milestone Overview

```
MILESTONE 1: Conversation Anchor Fix (P0) -- UNBLOCKS ALL
|-- Epic 1.1: K1 Turn Timestamp Propagation (Option C)
|-- Epic 1.2: M08 Normalize Timestamp Refactor (Option A)
|-- Epic 1.3: Race Condition Fix (beliefs_active temporal/spatial in TurnCompletePayload)

MILESTONE 2: Multi-Link Temporal Model (P1)
|-- Epic 2.1: TemporalLink Dataclass and Enum
|-- Epic 2.2: MemoryAtom Schema v2.1 (temporal_links)
|-- Epic 2.3: LLM Prompt Multi-Temporal Extraction
|-- Epic 2.4: K0 Receiver Changes (M08 + M13 + R0)

MILESTONE 3: Spatial Identity (P2)
|-- Epic 3.1: PlaceResolver Implementation
|-- Epic 3.2: st_hipp_events place_id Column
|-- Epic 3.3: Spatial Familiarity Tracking (K0)

MILESTONE 4: Per-Atom Signal Enrichment (P3)
|-- Epic 4.1: Intra-Turn Extraction Ordering
|-- Epic 4.2: Spatial Hierarchy Signal
|-- Epic 4.3: Spatial Transition Signal

MILESTONE 5: Cross-Episode Narrative Linking (P4)
|-- Epic 5.1: Cross-Episode Thread Matching
|-- Epic 5.2: Goal Completion Detection
```

---

## MILESTONE 1: Conversation Anchor Fix (P0)

> **Blocking**: Everything below depends on these fixes.
> **GAP-002 Reference**: Section 2.2 (M08 overwrite), Section 8 (Options A+C), Section 13 (Steps 1+2)
> **Combined approach**: Option C (K1 propagation) + Option A (M08 refactor) together make the
> temporal chain bulletproof. Option C gives K0 the gold-standard conversation anchor. Option A
> prevents M08 from overwriting it.

### Epic 1.1: K1 Turn Timestamp Propagation (Option C)

**Discovery**: GAP-002 Section 11.1 T5, T6, T7
**Effort**: MEDIUM (3-5 days, spans K1 MW types + events + architecture)
**Problem**: MW Envelope Builder uses `now_utc()` instead of `turn.complete.v1.timestamp_ms`.
This creates 200-815ms drift (up to 2-3 seconds under load). The gold-standard conversation
time (`TurnCompletePayload.timestamp_ms`) is available but not propagated through the MW pipeline.

> **Root Cause**: `ExtractionContext` (types.py L382-453) has `session_id` and `conversation_turn`
> but NO `turn_timestamp_ms` field. The Envelope Builder (architecture doc L587) uses `now_utc()`
> at build time instead of the Concierge-emitted timestamp. The turn timestamp is lost between
> event reception and envelope construction.
>
> **Data Flow (current)**:
>
> ```
> K1 Concierge -> turn.complete.v1 { timestamp_ms: 1700000000000 }
>   -> MW Stage 1 (filter)
>   -> MW Stage 2 (context assembly) -- timestamp_ms NOT captured
>   -> MW Stage 3 (LLM extraction)
>   -> MW Stage 4 (envelope builder) -- body.event_time_utc = now_utc() [DRIFT]
>   -> Bridge -> K0
> ```
>
> **Data Flow (target)**:
>
> ```
> K1 Concierge -> turn.complete.v1 { timestamp_ms: 1700000000000 }
>   -> MW Stage 2 -- ExtractionContext.turn_timestamp_ms = 1700000000000
>   -> MW Stage 4 -- body.event_time_utc = turn_timestamp_ms [EXACT]
>   -> body.conversation_anchor_ms = turn_timestamp_ms [NEW FIELD, never overwritten]
>   -> Bridge -> K0
> ```

#### Issues

---

##### Issue 1.1.1 -- Add turn_timestamp_ms to ExtractionContext

**Status**: TODO
**Priority**: P0 -- CRITICAL (foundation for conversation anchor)

**Files Touched**:

| File | Lines | Action |
|------|-------|--------|
| k1/memory_writer/types.py | L382-453 (ExtractionContext) | ADD: `turn_timestamp_ms: int = 0` field |
| k1/memory_writer/types.py | L382-400 (docstring) | EDIT: Document turn_timestamp_ms as gold-standard conversation time |

**Upstream Data Source**:

- k1/memory_writer/events.py L66-77: `TurnCompletePayload.timestamp_ms` (int, unix ms from Concierge)
- This is the ACTUAL conversation time from the K1 system clock when the user's turn completed
- Precision: millisecond, no drift, no approximation

**Current Code** (types.py L382-453):

```python
@dataclass(frozen=True)
class ExtractionContext:
    """Assembled context for LLM extraction.

    Built from 13/15 SessionState sections during Stage 2 (Context Assembly).
    Frozen to prevent mutation after assembly.
    """
    session_id: str = ""
    conversation_turn: int = 0
    active_persons: tuple = ()
    current_affect: Optional[Any] = None
    baseline_affect: Optional[Any] = None
    active_narrative: Optional[Any] = None
    active_goals: tuple = ()
    active_topics: tuple = ()
    control_context: Optional[Any] = None
    device_context: Optional[Any] = None
    persona_context: Optional[Any] = None
    # ... additional fields
```

**What Needs To Be Done**:

1. Add `turn_timestamp_ms: int = 0` field to ExtractionContext.
2. This value comes from `TurnCompletePayload.timestamp_ms`, set during MW Stage 2 context assembly.
3. The field is frozen (immutable) after assembly -- cannot be changed downstream.
4. Update docstring to document the field's purpose and provenance.

**How To Implement**:

```python
@dataclass(frozen=True)
class ExtractionContext:
    """Assembled context for LLM extraction.

    Built from 13/15 SessionState sections during Stage 2 (Context Assembly).
    Frozen to prevent mutation after assembly.
    """
    session_id: str = ""
    conversation_turn: int = 0
    turn_timestamp_ms: int = 0  # Gold-standard conversation time from turn.complete.v1.timestamp_ms
    # ... remaining fields unchanged
```

**Verification**:

- Run: `pytest tests/k1/memory_writer/ -x`
- Verify: ExtractionContext can be constructed with `turn_timestamp_ms=1700000000000`
- Verify: Field is frozen (assignment after construction raises FrozenInstanceError)

**Data Persistence Path**:

```
TurnCompletePayload.timestamp_ms (events.py L73)
  -> MW Stage 2 Context Assembly: ExtractionContext(turn_timestamp_ms=payload.timestamp_ms)
    -> MW Stage 3 LLM Extraction: available in context (NOT passed to LLM -- system field)
      -> MW Stage 4 Envelope Builder: body.event_time_utc = ctx.turn_timestamp_ms (Issue 1.1.2)
        -> body.conversation_anchor_ms = ctx.turn_timestamp_ms (Issue 1.1.3)
```

---

##### Issue 1.1.2 -- Envelope Builder: use turn_timestamp_ms instead of now_utc()

**Status**: TODO
**Priority**: P0 -- CRITICAL (eliminates 200-815ms drift)
**Depends on**: Issue 1.1.1 (turn_timestamp_ms on ExtractionContext)

**Files Touched**:

| File | Lines | Action |
|------|-------|--------|
| k1/memory_writer/memory_writer_architecture.md | L587 | EDIT: Change `now_utc() -> body.event_time_utc` to `turn_timestamp_ms -> body.event_time_utc` |

**Current Behavior** (architecture doc L587):

```
Stage 4: Envelope Builder
  body.event_time_utc = now_utc()    # Processing time, NOT conversation time
```

**Target Behavior**:

```
Stage 4: Envelope Builder
  body.event_time_utc = ctx.turn_timestamp_ms    # Exact conversation time
  # Fallback: now_utc() if turn_timestamp_ms == 0 (defensive)
```

**What Needs To Be Done**:

1. In the Envelope Builder logic, replace `now_utc()` with `ctx.turn_timestamp_ms`.
2. Add defensive fallback: if `turn_timestamp_ms == 0`, use `now_utc()` and log WARNING.
3. Update architecture doc to reflect the change.

**NOTE**: The Envelope Builder is currently a DESIGN concept in the architecture doc.
If a concrete implementation file exists, edit that. If it is embedded in the MW pipeline
runner, locate and modify the envelope construction code.

**How To Implement**:

```python
# In envelope construction logic:
event_time_utc = ctx.turn_timestamp_ms if ctx.turn_timestamp_ms > 0 else int(time.time() * 1000)
if ctx.turn_timestamp_ms == 0:
    logger.warning("MW: turn_timestamp_ms is 0, falling back to now_utc()")

body["event_time_utc"] = event_time_utc
```

**Verification**:

- Run: `pytest tests/k1/memory_writer/ -x`
- Test: Mock TurnCompletePayload with timestamp_ms=1700000000000, verify body.event_time_utc == 1700000000000
- Test: Mock TurnCompletePayload with timestamp_ms=0, verify fallback to now_utc() with WARNING logged

---

##### Issue 1.1.3 -- Add conversation_anchor_ms field to MemoryAtom

**Status**: TODO
**Priority**: P0 -- CRITICAL (gold-standard conversation time that M08 must NEVER overwrite)
**Depends on**: Issue 1.1.1 (turn_timestamp_ms on ExtractionContext)

**Files Touched**:

| File | Lines | Action |
|------|-------|--------|
| k1/memory_writer/types.py | L319-373 (MemoryAtom) | ADD: `conversation_anchor_ms: int = 0` field |
| k1/contracts/schemas/memory_writer/memory_atom.v2.schema.json | Top-level properties | ADD: `conversation_anchor_ms` integer field |

**Purpose**: This field carries the EXACT conversation time from K1 Concierge. It is
populated from `turn.complete.v1.timestamp_ms` and MUST NEVER be overwritten by any
K0 module. It is the authoritative timestamp for R2 episode formation.

**Current State (MemoryAtom temporal fields)**:

```python
# types.py L319-373 (relevant temporal fields):
temporal: Optional[Temporal] = None   # {mentioned_time, resolved_epoch_ms, is_backdated}
temporal_orientation: Optional[TemporalOrientation] = None  # PAST/ONGOING/FUTURE_COMMITMENT
```

**What Needs To Be Done**:

1. Add `conversation_anchor_ms: int = 0` to MemoryAtom dataclass.
2. Add to JSON schema (memory_atom.v2.schema.json) as optional integer.
3. Envelope Builder sets `body.conversation_anchor_ms = ctx.turn_timestamp_ms`.

**How To Implement**:

```python
# types.py -- Add to MemoryAtom fields:
conversation_anchor_ms: int = 0  # K1 Concierge turn timestamp. NEVER overwritten by K0.
```

```json
// memory_atom.v2.schema.json -- Add to properties:
"conversation_anchor_ms": {
  "type": "integer",
  "description": "K1 Concierge conversation timestamp (unix ms). Authoritative for R2 episode formation. NEVER overwritten by K0 M08.",
  "default": 0
}
```

**Verification**:

- Run: `pytest tests/k1/memory_writer/ -x`
- Verify: MemoryAtom can be constructed with `conversation_anchor_ms=1700000000000`
- Verify: Schema validates with `conversation_anchor_ms` present and absent (optional, backward compat)

---

##### Issue 1.1.4 -- Include MentionedTime and MentionedLocation in TurnCompletePayload

**Status**: TODO
**Priority**: P0 -- HIGH (eliminates race condition T7 from GAP-002)
**Depends on**: Nothing

**Files Touched**:

| File | Lines | Action |
|------|-------|--------|
| k1/memory_writer/events.py | L66-77 (TurnCompletePayload) | ADD: `mentioned_time` and `mentioned_location` fields |
| k1/sessionstate/sections/beliefs_active.py | L125-136, L139-152 | READ-ONLY: MentionedTime, MentionedLocation dataclass definitions |

**Current Code** (events.py L66-77):

```python
@dataclass(frozen=True)
class TurnCompletePayload:
    turn_id: str
    session_id: str
    cognitive_trace_id: str
    user_message: str
    assistant_response: str
    timestamp_ms: int
    turn_number: int
```

**Problem**: MW Stage 2 reads `beliefs_active.get_mentioned_time()` from SessionState.
But `beliefs_active.start_new_turn()` clears `_mentioned_time = None` (L742-743).
If the next turn starts before MW reads the snapshot (fast typing), temporal data is lost.

**Required Change**: Concierge includes MentionedTime/MentionedLocation directly in
TurnCompletePayload. MW reads temporal/spatial from the payload FIRST, SessionState fallback.

**How To Implement**:

```python
@dataclass(frozen=True)
class TurnCompletePayload:
    turn_id: str
    session_id: str
    cognitive_trace_id: str
    user_message: str
    assistant_response: str
    timestamp_ms: int
    turn_number: int
    # Temporal/spatial context from beliefs_active (eliminates race condition T7)
    mentioned_time_raw: str = ""           # Raw temporal text ("yesterday evening")
    mentioned_time_resolved_ms: int = 0    # Resolved epoch (ms)
    mentioned_time_confidence: float = 0.0 # Resolution confidence
    mentioned_time_is_relative: bool = True
    mentioned_location_raw: str = ""       # Raw location text ("Olive Garden")
    mentioned_location_type: str = ""      # Location type ("restaurant")
    mentioned_location_entity_id: str = "" # Entity ID if resolved
    mentioned_location_confidence: float = 0.0
```

**Verification**:

- Run: `pytest tests/k1/memory_writer/ -x`
- Test: TurnCompletePayload with temporal/spatial fields populated, verify MW Stage 2 reads them
- Test: TurnCompletePayload with empty temporal/spatial, verify MW falls back to SessionState
- Test: Simulate fast typing (start_new_turn before MW reads) -- payload still has temporal data

**Data Persistence Path**:

```
K1 Concierge:
  mentioned_time = beliefs_active.get_mentioned_time()
  mentioned_location = beliefs_active.get_mentioned_location()
  emit turn.complete.v1 {
    timestamp_ms, ...,
    mentioned_time_raw: mentioned_time.raw_text,
    mentioned_time_resolved_ms: mentioned_time.resolved_ms,
    mentioned_location_raw: mentioned_location.raw_text,
    ...
  }
  start_new_turn()  # Now safe to clear -- data is in the payload

MW Stage 2:
  # Read from payload first (race-free)
  temporal = payload.mentioned_time_raw or session_state.beliefs_active.get_mentioned_time()
```

---

##### Issue 1.1.5 -- Add integration tests for K1 turn timestamp propagation

**Status**: TODO
**Priority**: P0 -- CRITICAL (validates Issues 1.1.1 through 1.1.4)
**Depends on**: Issues 1.1.1, 1.1.2, 1.1.3, 1.1.4

**Files Touched**:

| File | Lines | Action |
|------|-------|--------|
| tests/k1/memory_writer/test_turn_timestamp_propagation.py | NEW FILE | CREATE: Integration tests |

**What Needs To Be Done**:

1. Test ExtractionContext.turn_timestamp_ms is populated from TurnCompletePayload.timestamp_ms.
2. Test Envelope Builder uses turn_timestamp_ms (not now_utc()) for body.event_time_utc.
3. Test MemoryAtom.conversation_anchor_ms is populated from turn_timestamp_ms.
4. Test TurnCompletePayload carries mentioned_time/mentioned_location.
5. Test that when TurnCompletePayload has temporal data AND SessionState has been cleared,
   MW still has the temporal data from the payload (race condition eliminated).
6. Test fallback: turn_timestamp_ms=0 -> Envelope Builder uses now_utc() with WARNING.

**How To Implement**:

```python
# tests/k1/memory_writer/test_turn_timestamp_propagation.py

"""Tests for K1 turn timestamp propagation (Epic 1.1).

Validates that turn.complete.v1.timestamp_ms flows through the MW pipeline
to body.event_time_utc and body.conversation_anchor_ms, replacing now_utc().
Also validates that MentionedTime/MentionedLocation in TurnCompletePayload
eliminates the race condition where start_new_turn() clears beliefs_active
before MW reads the snapshot.
"""

import pytest
from k1.memory_writer.types import ExtractionContext, MemoryAtom
from k1.memory_writer.events import TurnCompletePayload


class TestExtractionContextTimestamp:
    """Verify turn_timestamp_ms on ExtractionContext."""

    def test_turn_timestamp_ms_field_exists(self):
        ctx = ExtractionContext(turn_timestamp_ms=1700000000000)
        assert ctx.turn_timestamp_ms == 1700000000000

    def test_turn_timestamp_ms_default_zero(self):
        ctx = ExtractionContext()
        assert ctx.turn_timestamp_ms == 0

    def test_frozen_after_construction(self):
        ctx = ExtractionContext(turn_timestamp_ms=1700000000000)
        with pytest.raises(AttributeError):
            ctx.turn_timestamp_ms = 9999


class TestMemoryAtomConversationAnchor:
    """Verify conversation_anchor_ms on MemoryAtom."""

    def test_conversation_anchor_ms_field_exists(self):
        atom = MemoryAtom(conversation_anchor_ms=1700000000000)
        assert atom.conversation_anchor_ms == 1700000000000

    def test_conversation_anchor_ms_default_zero(self):
        atom = MemoryAtom()
        assert atom.conversation_anchor_ms == 0


class TestTurnCompletePayloadTemporalSpatial:
    """Verify TurnCompletePayload carries temporal/spatial context."""

    def test_mentioned_time_fields(self):
        payload = TurnCompletePayload(
            turn_id="t1", session_id="s1", cognitive_trace_id="ct1",
            user_message="Had dinner yesterday", assistant_response="Nice!",
            timestamp_ms=1700000000000, turn_number=1,
            mentioned_time_raw="yesterday",
            mentioned_time_resolved_ms=1699920000000,
            mentioned_time_confidence=0.9,
        )
        assert payload.mentioned_time_raw == "yesterday"
        assert payload.mentioned_time_resolved_ms == 1699920000000

    def test_mentioned_location_fields(self):
        payload = TurnCompletePayload(
            turn_id="t1", session_id="s1", cognitive_trace_id="ct1",
            user_message="At Olive Garden", assistant_response="How was it?",
            timestamp_ms=1700000000000, turn_number=1,
            mentioned_location_raw="Olive Garden",
            mentioned_location_type="restaurant",
        )
        assert payload.mentioned_location_raw == "Olive Garden"
        assert payload.mentioned_location_type == "restaurant"

    def test_default_empty_when_no_temporal_spatial(self):
        payload = TurnCompletePayload(
            turn_id="t1", session_id="s1", cognitive_trace_id="ct1",
            user_message="Hello", assistant_response="Hi!",
            timestamp_ms=1700000000000, turn_number=1,
        )
        assert payload.mentioned_time_raw == ""
        assert payload.mentioned_location_raw == ""
```

**Verification**:

- All tests must pass: `pytest tests/k1/memory_writer/test_turn_timestamp_propagation.py -v`

---

### Epic 1.2: M08 Normalize Timestamp Refactor (Option A)

**Discovery**: GAP-002 Section 2.2, 2.3, Section 8 Option A
**Effort**: MEDIUM (3-5 days, K0 M08 + M13 + migration)
**Problem**: M08 `normalize_timestamp()` overwrites `event_time_utc` with `temporal_resolved_epoch_ms`
when Priority 1 fires. After this refactor, Priority 1 and 2 write to `temporal_resolved_epoch_ms`
ONLY. `event_time_utc` always comes from conversation time (Priority 3+).

> **Root Cause**: The 5-level fallback chain at temporal_profile.py L480+ treats all timestamp
> sources as equivalent and writes the winning value to `event_time_utc`. But Priority 1
> (MW resolved epoch) and Priority 2 (NER temporal) are REFERRED TIMES (what date the event
> talks about), not CONVERSATION TIMES (when the user chatted). Writing them to `event_time_utc`
> destroys the conversation anchor that R2 needs for episode formation.
>
> **Example**: User says "Had dinner yesterday evening" at Tue 10:00am.
>
> - Priority 1 fires: resolved_epoch_ms = Mon 7:00pm
> - M08 writes event_time_utc = Mon 7:00pm (WRONG for episodes)
> - R2 sees this event as happening YESTERDAY, separates from other Tue 10:00am events
>
> **After fix**: M08 writes:
>
> - temporal_resolved_epoch_ms = Mon 7:00pm (referred time, for temporal queries)
> - event_time_utc = Tue 10:00am (conversation time, from body.event_time or conversation_anchor_ms)

#### Issues

---

##### Issue 1.2.1 -- Refactor normalize_timestamp() to separate conversation time from referred time

**Status**: TODO
**Priority**: P0 -- CRITICAL (the core fix for temporal collapse)

**Files Touched**:

| File | Lines | Action |
|------|-------|--------|
| k0/modules/context/temporal_profile.py | L480-580 (normalize_timestamp) | EDIT: Split into two output chains |

**Current Code** (temporal_profile.py, normalize_timestamp 5-level fallback):

```
Priority 1: body.temporal.resolved_epoch_ms  -> "mw_resolved"   -> event_time_utc  [BUG: referred time]
Priority 2: M02 NER temporal + regex         -> "ner_temporal"   -> event_time_utc  [BUG: referred time]
Priority 3: body.event_time (MW now_utc())   -> "event_time"     -> event_time_utc  [CORRECT: conversation time]
Priority 4: envelope.ts (Bridge build time)  -> "envelope_ts"    -> event_time_utc  [OK: approximate]
Priority 5: now() (P02 processing time)      -> "now"            -> event_time_utc  [OK: last resort]
```

**Target Code** (two separate output chains):

```
CHAIN A -- event_time_utc (conversation time, for R2 episodes):
  1. body.conversation_anchor_ms (K1 turn timestamp, gold standard) -> "conversation_anchor"
  2. body.event_time (MW now_utc(), approximate)                    -> "event_time"
  3. envelope.ts (Bridge build time)                                -> "envelope_ts"
  4. now() (P02 processing time)                                    -> "now"

CHAIN B -- temporal_resolved_epoch_ms (referred time, for temporal queries):
  1. body.temporal.resolved_epoch_ms (K1 LLM resolved)    -> "mw_resolved"
  2. M02 NER temporal + regex resolution                   -> "ner_temporal"
  3. null (no temporal reference in this event)             -> "none"
```

**What Needs To Be Done**:

1. Split `normalize_timestamp()` into two methods:
   - `_resolve_conversation_time(body, envelope) -> (int, str)` -- returns (epoch_seconds, source_tag)
   - `_resolve_referred_time(body, ner_result) -> (Optional[int], str)` -- returns (epoch_ms_or_None, source_tag)
2. The public `normalize_timestamp()` calls both and returns a combined result.
3. `event_time_utc` output ALWAYS comes from Chain A (conversation time).
4. `temporal_resolved_epoch_ms` output comes from Chain B (referred time).
5. Both chains produce a `temporal_source` provenance tag.
6. Add `conversation_time_source: str` field to the output (tracks Chain A provenance).

**How To Implement**:

```python
def _resolve_conversation_time(
    self, body: dict, envelope: dict
) -> tuple[int, str]:
    """Chain A: Resolve conversation time for R2 episode formation.

    Priority:
      1. body.conversation_anchor_ms (K1 turn timestamp, gold standard)
      2. body.event_time (MW now_utc(), approximate conversation time)
      3. envelope.ts (Bridge build time)
      4. now() (P02 processing time, last resort)

    Returns: (epoch_seconds, source_tag)
    """
    # Priority 1: K1 conversation anchor (milliseconds -> seconds)
    anchor_ms = body.get("conversation_anchor_ms", 0)
    if anchor_ms and anchor_ms > 0:
        return int(anchor_ms / 1000), "conversation_anchor"

    # Priority 2: MW event_time (already seconds or ISO)
    event_time = body.get("event_time") or body.get("event_time_utc")
    if event_time:
        parsed = self._parse_timestamp(event_time)
        if parsed and parsed > 0:
            return parsed, "event_time"

    # Priority 3: Bridge envelope timestamp
    envelope_ts = envelope.get("ts")
    if envelope_ts:
        parsed = self._parse_timestamp(envelope_ts)
        if parsed and parsed > 0:
            return parsed, "envelope_ts"

    # Priority 4: now() fallback
    return int(time.time()), "now"


def _resolve_referred_time(
    self, body: dict, ner_temporal_result: Optional[dict]
) -> tuple[Optional[int], str]:
    """Chain B: Resolve referred time for temporal queries.

    Priority:
      1. body.temporal.resolved_epoch_ms (K1 LLM resolution)
      2. M02 NER temporal + regex resolution
      3. None (no temporal reference)

    Returns: (epoch_ms_or_None, source_tag)
    """
    # Priority 1: K1 LLM resolved temporal
    temporal = body.get("temporal")
    if temporal and isinstance(temporal, dict):
        resolved_ms = temporal.get("resolved_epoch_ms", 0)
        if resolved_ms and resolved_ms > 0:
            return int(resolved_ms), "mw_resolved"

    # Priority 2: M02 NER temporal extraction
    if ner_temporal_result:
        ner_epoch = ner_temporal_result.get("resolved_epoch_ms", 0)
        if ner_epoch and ner_epoch > 0:
            return int(ner_epoch), "ner_temporal"

    # No temporal reference
    return None, "none"
```

**Verification**:

- Run: `pytest tests/k0/modules/context/test_m08_temporal_profile.py -x`
- Test: Event with body.temporal.resolved_epoch_ms=1699920000000 (yesterday):
  - event_time_utc = body.event_time (conversation time, NOT yesterday)
  - temporal_resolved_epoch_ms = 1699920000000 (referred time)
- Test: Event with NO temporal reference:
  - event_time_utc = body.event_time (conversation time)
  - temporal_resolved_epoch_ms = None
- Test: Event with body.conversation_anchor_ms populated:
  - event_time_utc = conversation_anchor_ms / 1000 (gold standard)

**Data Persistence Path (after fix)**:

```
K1 Concierge emits turn.complete.v1 { timestamp_ms: 1700000000000 }
  -> MW sets body.conversation_anchor_ms = 1700000000000
  -> MW sets body.event_time_utc = 1700000000000 (from turn_timestamp_ms)
  -> MW sets body.temporal = { mentioned_time: "yesterday", resolved_epoch_ms: 1699920000000 }
  -> Bridge -> K0 P02 M08:
    Chain A: event_time_utc = body.conversation_anchor_ms / 1000 = 1700000000
    Chain B: temporal_resolved_epoch_ms = 1699920000000 (from body.temporal)
  -> M13 writes BOTH to st_hipp_events (separate columns, separate purposes)
  -> R0 reads event_time_utc = 1700000000 -> P03EventState.timestamp = 1700000000000
  -> R2 episode formation uses conversation time (CORRECT)
```

---

##### Issue 1.2.2 -- Add conversation_anchor_ms column to st_hipp_events

**Status**: TODO
**Priority**: P0 -- CRITICAL (stores the gold-standard conversation timestamp)
**Depends on**: Issue 1.1.3 (field on MemoryAtom), Issue 1.2.1 (M08 refactor)

**Files Touched**:

| File | Lines | Action |
|------|-------|--------|
| k0/contracts/schemas/st_hipp_events_v2.columns.yaml | After event_time_utc (L333-340) | ADD: conversation_anchor_ms column |
| k0/db/alembic/versions/ | NEW FILE | CREATE: Migration to add column |

**Schema Addition**:

```yaml
# st_hipp_events_v2.columns.yaml -- Add after event_time_utc:
conversation_anchor_ms:
  type: BIGINT
  nullable: true
  description: >
    Gold-standard conversation timestamp from K1 Concierge turn.complete.v1.timestamp_ms.
    NEVER overwritten by M08 temporal resolution. Used by P03 R0 as primary timestamp
    for R2 episode formation when available. Unit: Unix milliseconds.
  owner: K1 MW (passthrough)
  migration: "0075"
```

**Migration SQL**:

```sql
-- Migration 0075: Add conversation_anchor_ms to st_hipp_events
-- GAP-002 Phase 2: Preserve conversation anchor
ALTER TABLE st_hipp_events
  ADD COLUMN IF NOT EXISTS conversation_anchor_ms BIGINT;

-- Index for R0 batch selector time-range queries
CREATE INDEX IF NOT EXISTS idx_hipp_conversation_anchor
  ON st_hipp_events (conversation_anchor_ms)
  WHERE conversation_anchor_ms IS NOT NULL;

-- Backfill from event_time_utc for existing rows (seconds -> ms)
-- event_time_utc is in SECONDS, conversation_anchor_ms is in MILLISECONDS
UPDATE st_hipp_events
  SET conversation_anchor_ms = event_time_utc * 1000
  WHERE conversation_anchor_ms IS NULL
    AND event_time_utc IS NOT NULL
    AND event_time_utc > 0;
```

**Verification**:

- Run migration on dev database
- Verify: `SELECT count(*) FROM st_hipp_events WHERE conversation_anchor_ms IS NOT NULL` = row count
- Verify: All backfilled values are event_time_utc * 1000

---

##### Issue 1.2.3 -- Update M13 Builder to write conversation_anchor_ms

**Status**: TODO
**Priority**: P0 -- CRITICAL
**Depends on**: Issue 1.2.2 (column exists)

**Files Touched**:

| File | Lines | Action |
|------|-------|--------|
| k0/modules/context/hipp_events_row.py | L310-320 (event_time_utc storage) | ADD: conversation_anchor_ms field in row dict |

**What Needs To Be Done**:

1. M13 builder reads `body.conversation_anchor_ms` from the envelope.
2. Writes it to `st_hipp_events.conversation_anchor_ms` column.
3. If `conversation_anchor_ms` is 0 or missing, writes NULL (do not write 0).

**Verification**:

- Run: `pytest tests/k0/modules/context/ -x`
- Test: Envelope with conversation_anchor_ms=1700000000000 -> stored in DB
- Test: Envelope without conversation_anchor_ms -> NULL in DB

---

##### Issue 1.2.4 -- Update R0 to prefer conversation_anchor_ms for P03EventState.timestamp

**Status**: TODO
**Priority**: P0 -- CRITICAL
**Depends on**: Issue 1.2.2 (column), Issue 1.2.3 (M13 writes it)

**Files Touched**:

| File | Lines | Action |
|------|-------|--------|
| k0/pipelines/p03/phases/r0_batch_selector.py | L557-558 (SQL SELECT) | ADD: conversation_anchor_ms to SELECT |
| k0/pipelines/p03/phases/r0_batch_selector.py | L664-677 (timestamp loading) | EDIT: Prefer conversation_anchor_ms |

**Current Timestamp Chain (R0)**:

```
event_time_utc -> created_at -> now()
```

**New Timestamp Chain (R0)**:

```
conversation_anchor_ms (gold standard, milliseconds, never overwritten)
  -> event_time_utc * 1000 (M08 conversation time, seconds -> ms)
    -> created_at * 1000 (K0 insert time, degraded during offline drain)
      -> now() * 1000 (last resort)
```

**How To Implement**:

```python
# r0_batch_selector.py -- Updated timestamp chain:
_anchor_ms = row.get("conversation_anchor_ms")
_event_time_raw = row.get("event_time_utc")
_created_at_raw = row.get("created_at")

if _anchor_ms is not None and _anchor_ms > 0:
    # Gold standard: K1 conversation timestamp (already in ms)
    event_time_ms = int(_anchor_ms)
    temporal_source = "conversation_anchor"
elif _event_time_raw is not None and _event_time_raw > 0:
    # M08 conversation time (seconds -> ms)
    event_time_ms = (
        int(_event_time_raw * 1000) if _event_time_raw < 1e12 else int(_event_time_raw)
    )
    temporal_source = "event_time"
elif _created_at_raw is not None and _created_at_raw > 0:
    event_time_ms = (
        int(_created_at_raw * 1000) if _created_at_raw < 1e12 else int(_created_at_raw)
    )
    temporal_source = "created_at"
    logger.warning(
        "R0: conversation_anchor_ms and event_time_utc missing, using created_at",
        extra={"event_id": row.get("event_id")},
    )
else:
    event_time_ms = int(time.time() * 1000)
    temporal_source = "now"
    logger.error(
        "R0: All timestamp sources missing, using now()",
        extra={"event_id": row.get("event_id")},
    )
```

**Verification**:

- Run: `pytest tests/k0/pipelines/p03/test_p03_r0_batch_selector.py -x`
- Test: Row with conversation_anchor_ms=1700000000000 -> timestamp=1700000000000
- Test: Row with conversation_anchor_ms=NULL, event_time_utc=1700000000 -> timestamp=1700000000000
- Test: Row with both NULL, created_at=1700000000 -> WARNING, timestamp=1700000000000

---

##### Issue 1.2.5 -- Add temporal_source persistence to st_hipp_events

**Status**: TODO
**Priority**: P1 -- HIGH (enables R2 to know timestamp quality)
**Depends on**: Issue 1.2.1 (M08 refactor produces temporal_source)

**Files Touched**:

| File | Lines | Action |
|------|-------|--------|
| k0/contracts/schemas/st_hipp_events_v2.columns.yaml | After temporal_orientation | ADD: temporal_source TEXT NULLABLE |
| k0/db/alembic/versions/ | NEW FILE | Migration to add column |
| k0/modules/context/hipp_events_row.py | After temporal_orientation write | ADD: temporal_source write |
| k0/pipelines/p03/phases/r0_batch_selector.py | SQL SELECT, mapping | ADD: temporal_source load |
| k0/pipelines/p03/event_state.py | After temporal_orientation | ADD: temporal_source field (already exists per code audit) |

**What Needs To Be Done**:

1. Add `temporal_source TEXT NULLABLE` column to st_hipp_events.
2. M08 populates it with the provenance tag from `_resolve_conversation_time()`.
3. M13 writes it to the DB.
4. R0 reads it into P03EventState.temporal_source.
5. R2 can use it for timestamp quality observability (already designed in R2 Epic 1.2.4).

**Verification**:

- Migration succeeds
- M08 writes "conversation_anchor" or "event_time" or "envelope_ts" or "now"
- R0 loads into P03EventState.temporal_source

---

##### Issue 1.2.6 -- Backfill migration for existing overwritten event_time_utc rows

**Status**: TODO
**Priority**: P1 -- HIGH (corrects historical data)
**Depends on**: Issue 1.2.2 (conversation_anchor_ms column)

**Files Touched**:

| File | Lines | Action |
|------|-------|--------|
| k0/db/alembic/versions/ | NEW FILE or extend 0075 | Backfill logic |

**Problem**: Existing rows where M08 Priority 1 fired have `event_time_utc` set to
the REFERRED TIME, not conversation time. `conversation_anchor_ms` backfill in Issue 1.2.2
copies `event_time_utc * 1000`, which propagates the wrong value.

**Required**: For rows where `temporal_resolved_epoch_ms > 0` AND
`event_time_utc * 1000 ~= temporal_resolved_epoch_ms` (within 1 hour tolerance),
the `event_time_utc` was likely overwritten. These rows need special handling.

**Strategy**:

```sql
-- Identify potentially overwritten rows
-- If event_time_utc (seconds) * 1000 is close to temporal_resolved_epoch_ms (ms),
-- then M08 likely overwrote event_time_utc with referred time.
-- In that case, conversation_anchor_ms should NOT be set from event_time_utc.
-- Set it to NULL and let R0 use created_at fallback.
UPDATE st_hipp_events
  SET conversation_anchor_ms = NULL
  WHERE temporal_resolved_epoch_ms IS NOT NULL
    AND temporal_resolved_epoch_ms > 0
    AND ABS(event_time_utc * 1000 - temporal_resolved_epoch_ms) < 3600000; -- within 1 hour
```

**Verification**:

- Count rows affected by backfill
- Verify conversation_anchor_ms is NULL for overwritten rows
- Verify R0 falls back to created_at for these rows (with WARNING)

---

##### Issue 1.2.7 -- Integration tests for M08 refactor + conversation anchor chain

**Status**: TODO
**Priority**: P0 -- CRITICAL (validates all of Epic 1.2)
**Depends on**: Issues 1.2.1 through 1.2.5

**Files Touched**:

| File | Lines | Action |
|------|-------|--------|
| tests/k0/modules/context/test_m08_conversation_anchor.py | NEW FILE | CREATE: Integration tests |

**Test Cases**:

1. **Event with temporal expression**: body.temporal.resolved_epoch_ms=yesterday.
   Verify event_time_utc = conversation time (NOT yesterday).
   Verify temporal_resolved_epoch_ms = yesterday epoch.

2. **Event without temporal expression**: No body.temporal.
   Verify event_time_utc = body.event_time (conversation time).
   Verify temporal_resolved_epoch_ms = NULL.

3. **Event with conversation_anchor_ms**: body.conversation_anchor_ms=1700000000000.
   Verify event_time_utc = 1700000000 (anchor/1000).
   Verify conversation_anchor_ms column = 1700000000000.

4. **Backfill scenario**: Old row where event_time_utc was overwritten.
   Verify conversation_anchor_ms is NULL (not propagated from wrong value).

5. **R0 full chain**: conversation_anchor_ms -> P03EventState.timestamp.
   Verify R2 uses conversation time for episode formation.

---

### Epic 1.3: Race Condition Fix (beliefs_active temporal/spatial in TurnCompletePayload)

**Discovery**: GAP-002 Section 11.1 T7
**Effort**: LOW (1-2 days, K1 Concierge + MW Stage 2)
**Problem**: `beliefs_active.start_new_turn()` clears `_mentioned_time` and `_mentioned_location`
before MW may have read them. Including temporal/spatial in TurnCompletePayload eliminates this race.

> **NOTE**: The payload fields were added in Epic 1.1 Issue 1.1.4. This epic handles the
> CONSUMPTION side: MW Stage 2 (Context Assembly) must read from payload first, SessionState fallback.

#### Issues

---

##### Issue 1.3.1 -- MW Stage 2 reads temporal/spatial from TurnCompletePayload first

**Status**: TODO
**Priority**: P0 -- HIGH
**Depends on**: Epic 1.1 Issue 1.1.4 (payload fields exist)

**Files Touched**:

| File | Lines | Action |
|------|-------|--------|
| MW pipeline / context assembly logic | Context Assembly section | EDIT: Read from payload first |

**What Needs To Be Done**:

1. MW Stage 2 receives TurnCompletePayload.
2. If payload has `mentioned_time_raw != ""`, use it (race-free source).
3. Else, read `beliefs_active.get_mentioned_time()` from SessionState (fallback).
4. Same pattern for spatial: payload `mentioned_location_raw` first, SessionState fallback.

**How To Implement**:

```python
# MW Stage 2: Context Assembly (pseudocode)
def _assemble_context(self, payload: TurnCompletePayload, session: ISessionReadPort) -> ExtractionContext:
    # Temporal: prefer payload (race-free) over SessionState
    if payload.mentioned_time_raw:
        mentioned_time = MentionedTime(
            raw_text=payload.mentioned_time_raw,
            resolved_ms=payload.mentioned_time_resolved_ms,
            confidence=payload.mentioned_time_confidence,
            is_relative=payload.mentioned_time_is_relative,
        )
    else:
        mentioned_time = session.beliefs_active.get_mentioned_time()

    # Spatial: prefer payload (race-free) over SessionState
    if payload.mentioned_location_raw:
        mentioned_location = MentionedLocation(
            raw_text=payload.mentioned_location_raw,
            location_type=payload.mentioned_location_type,
            entity_id=payload.mentioned_location_entity_id,
            confidence=payload.mentioned_location_confidence,
        )
    else:
        mentioned_location = session.beliefs_active.get_mentioned_location()

    return ExtractionContext(
        turn_timestamp_ms=payload.timestamp_ms,
        # ... other fields from SessionState sections
    )
```

**Verification**:

- Test: Payload has temporal, SessionState cleared -> MW gets temporal from payload
- Test: Payload empty, SessionState has temporal -> MW gets temporal from SessionState
- Test: Both have temporal -> payload wins (more reliable)

---

##### Issue 1.3.2 -- Integration test for race condition elimination

**Status**: TODO
**Priority**: P0 -- HIGH
**Depends on**: Issue 1.3.1

**Files Touched**:

| File | Lines | Action |
|------|-------|--------|
| tests/k1/memory_writer/test_race_condition_fix.py | NEW FILE | CREATE: Race condition test |

**Key Test**: Simulate fast typing where `start_new_turn()` fires before MW Stage 2 reads.
Verify MW still has temporal/spatial data from the payload.

---

## MILESTONE 2: Multi-Link Temporal Model (P1)

> **Depends on**: Milestone 1 (conversation anchor is correct and stable)
> **GAP-002 Reference**: Section 2.4, 2.5, Section 11.1 T1-T4, Section 13 Step 2

### Epic 2.1: TemporalLink Dataclass and Enum

**Discovery**: GAP-002 Section 11.1 T1, T2, T3
**Effort**: LOW (1-2 days)
**Problem**: Current MemoryAtom.temporal supports only ONE temporal reference per atom.
"Yesterday we planned next Friday and Mom mentioned Christmas" has 3 temporal references
but MW can only capture 1.

#### Issues

---

##### Issue 2.1.1 -- Create TemporalLinkType enum

**Status**: TODO
**Priority**: P1

**Files Touched**:

| File | Lines | Action |
|------|-------|--------|
| k1/memory_writer/types.py | After TemporalOrientation (L86) | ADD: TemporalLinkType enum |

**How To Implement**:

```python
class TemporalLinkType(str, Enum):
    """Classification of how a memory atom references a time.

    Per-link type (one atom may have multiple links with different types).
    Replaces the binary `is_backdated: bool` which could only distinguish
    past vs not-past.
    """
    RETROSPECTIVE = "RETROSPECTIVE"      # Past reference ("yesterday", "last week")
    PROSPECTIVE = "PROSPECTIVE"          # Future reference ("next Friday", "tomorrow")
    CONCURRENT = "CONCURRENT"            # Happening now ("right now", "currently")
    HABITUAL = "HABITUAL"                # Recurring pattern ("every Sunday", "usually")
    CONTEXTUAL = "CONTEXTUAL"            # Life period ("in college", "when I was young")
    CONDITIONAL = "CONDITIONAL"          # Contingent ("if it rains", "when I get home")
```

**Verification**:

- `TemporalLinkType.RETROSPECTIVE.value == "RETROSPECTIVE"`
- All 6 values are valid str enum members

---

##### Issue 2.1.2 -- Create TemporalLink frozen dataclass

**Status**: TODO
**Priority**: P1
**Depends on**: Issue 2.1.1 (TemporalLinkType exists)

**Files Touched**:

| File | Lines | Action |
|------|-------|--------|
| k1/memory_writer/types.py | After Temporal dataclass (L269) | ADD: TemporalLink dataclass |

**How To Implement**:

```python
@dataclass(frozen=True)
class TemporalLink:
    """One temporal reference from a memory atom.

    A single atom may carry 0-5 temporal links. Example:
    "Yesterday we planned next Friday's party and Mom reminded me about Christmas"
    -> 3 TemporalLinks: yesterday (RETROSPECTIVE), next Friday (PROSPECTIVE),
       Christmas (PROSPECTIVE).

    Fields:
      mentioned_time: Raw text from conversation ("yesterday evening")
      resolved_epoch_ms: Best-guess absolute time (Unix ms)
      uncertainty_window_ms: Precision window (60_000 for "7:15pm", 14_400_000 for "yesterday evening")
      link_type: Classification (RETROSPECTIVE, PROSPECTIVE, HABITUAL, etc.)
      confidence: LLM resolution confidence [0.0, 1.0]
    """
    mentioned_time: str
    resolved_epoch_ms: int = 0
    uncertainty_window_ms: int = 0
    link_type: str = "CONCURRENT"  # TemporalLinkType value
    confidence: float = 1.0
```

**Verification**:

- TemporalLink is frozen (immutable)
- All fields have sensible defaults
- Can construct with just `mentioned_time="yesterday"`

---

##### Issue 2.1.3 -- Add temporal_links and conversation_anchor_ms to MemoryAtom

**Status**: TODO
**Priority**: P1
**Depends on**: Issue 2.1.2 (TemporalLink exists), Issue 1.1.3 (conversation_anchor_ms)

**Files Touched**:

| File | Lines | Action |
|------|-------|--------|
| k1/memory_writer/types.py | L319-373 (MemoryAtom) | ADD: `temporal_links` field |

**How To Implement**:

```python
# On MemoryAtom:
temporal_links: tuple = ()  # Tuple[TemporalLink, ...] -- 0-5 temporal references per atom
# conversation_anchor_ms: int = 0  -- Already added in Issue 1.1.3

# DEPRECATED (keep for backward compat, stop populating in new code):
# temporal: Optional[Temporal] = None  -- Replaced by temporal_links
```

**Note**: Use `tuple` instead of `List` because MemoryAtom is frozen.

**Verification**:

- MemoryAtom(temporal_links=(TemporalLink(mentioned_time="yesterday"),)) works
- Empty tuple is default

---

##### Issue 2.1.4 -- Tests for TemporalLink and TemporalLinkType

**Status**: TODO
**Priority**: P1

**Files Touched**:

| File | Lines | Action |
|------|-------|--------|
| tests/k1/memory_writer/test_temporal_link.py | NEW FILE | CREATE: Unit tests |

**Test Cases**:

1. TemporalLinkType enum values are correct strings
2. TemporalLink construction with all fields
3. TemporalLink frozen (immutable)
4. MemoryAtom with multiple temporal_links
5. MemoryAtom backward compat: temporal field still works alongside temporal_links
6. Edge case: empty temporal_links tuple

---

### Epic 2.2: MemoryAtom Schema v2.1 (temporal_links)

**Discovery**: GAP-002 Section 14
**Effort**: LOW (1-2 days)
**Problem**: JSON schema must be updated to include temporal_links, conversation_anchor_ms, and TemporalLink $def.

#### Issues

---

##### Issue 2.2.1 -- Update memory_atom.v2.schema.json to v2.1

**Status**: TODO
**Priority**: P1

**Files Touched**:

| File | Lines | Action |
|------|-------|--------|
| k1/contracts/schemas/memory_writer/memory_atom.v2.schema.json | $defs section | ADD: TemporalLink $def |
| k1/contracts/schemas/memory_writer/memory_atom.v2.schema.json | properties section | ADD: temporal_links, conversation_anchor_ms |

**Schema Changes** (all additive, backward compatible):

```json
{
  "$defs": {
    "TemporalLink": {
      "type": "object",
      "properties": {
        "mentioned_time": { "type": "string" },
        "resolved_epoch_ms": { "type": "integer", "default": 0 },
        "uncertainty_window_ms": { "type": "integer", "default": 0 },
        "link_type": {
          "type": "string",
          "enum": ["RETROSPECTIVE", "PROSPECTIVE", "CONCURRENT", "HABITUAL", "CONTEXTUAL", "CONDITIONAL"],
          "default": "CONCURRENT"
        },
        "confidence": { "type": "number", "minimum": 0, "maximum": 1, "default": 1.0 }
      },
      "required": ["mentioned_time"]
    }
  },
  "properties": {
    "conversation_anchor_ms": {
      "type": "integer",
      "description": "K1 conversation timestamp (unix ms). NEVER overwritten by K0.",
      "default": 0
    },
    "temporal_links": {
      "type": "array",
      "items": { "$ref": "#/$defs/TemporalLink" },
      "maxItems": 5,
      "default": [],
      "description": "0-5 temporal references per atom. Replaces single Temporal object."
    }
  }
}
```

**Decision**: Schema version bumps from "2.0" to "2.1" (additive, not breaking).
All v2.0 atoms are valid v2.1 atoms (new fields have defaults).

**Verification**:

- Validate schema with jsonschema library
- v2.0 atom (no temporal_links, no conversation_anchor_ms) validates against v2.1 schema
- v2.1 atom with temporal_links validates
- v2.1 atom with >5 temporal_links fails validation (maxItems)

---

##### Issue 2.2.2 -- Update K0 Gate to accept schema_version "2.1"

**Status**: TODO
**Priority**: P1

**Files Touched**:

| File | Lines | Action |
|------|-------|--------|
| k0/gate/ (schema validation logic) | Version check | ADD: Accept "2.1" alongside "2.0" |

**What Needs To Be Done**:

1. K0 Gate currently accepts `schema_version: "2.0"`.
2. Add "2.1" to the accepted versions list.
3. Both "2.0" and "2.1" atoms pass through Gate.

---

### Epic 2.3: LLM Prompt Multi-Temporal Extraction

**Discovery**: GAP-002 Section 11.3 X4
**Effort**: MEDIUM (2-3 days)
**Problem**: LLM prompt does not instruct multi-temporal extraction. Schema changes are
useless without LLM instruction. Even with the new schema, the LLM will produce at most
one temporal reference unless explicitly prompted.

#### Issues

---

##### Issue 2.3.1 -- Update MW persona prompt for multi-temporal extraction

**Status**: TODO
**Priority**: P1 -- CRITICAL (schema changes useless without this)

**Files Touched**:

| File | Lines | Action |
|------|-------|--------|
| k1/memory_writer/ (persona prompt file) | Temporal extraction section | EDIT: Add multi-temporal instructions |

**Prompt Addition** (to be inserted in the temporal extraction section):

```
TEMPORAL REFERENCES:
For each memory atom, identify ALL temporal references mentioned or implied:

Examples:
  "Yesterday we planned next Friday's party and Mom mentioned Christmas"
  -> 3 temporal_links:
    1. { mentioned_time: "yesterday", link_type: "RETROSPECTIVE", uncertainty_window_ms: 86400000 }
    2. { mentioned_time: "next Friday", link_type: "PROSPECTIVE", uncertainty_window_ms: 86400000 }
    3. { mentioned_time: "Christmas", link_type: "PROSPECTIVE", uncertainty_window_ms: 86400000 }

  "We go to Olive Garden every Friday"
  -> 1 temporal_link:
    1. { mentioned_time: "every Friday", link_type: "HABITUAL", uncertainty_window_ms: 0 }

  "I feel happy right now"
  -> 0 temporal_links (no explicit temporal reference, CONCURRENT is implicit)

Link types:
  RETROSPECTIVE: Past reference ("yesterday", "last week", "when I was young")
  PROSPECTIVE: Future reference ("tomorrow", "next month", "someday")
  CONCURRENT: Happening now ("right now", "at the moment") -- usually implicit
  HABITUAL: Recurring pattern ("every Sunday", "usually", "always")
  CONTEXTUAL: Life period ("in college", "during my 20s", "back then")
  CONDITIONAL: Contingent ("if it rains", "when we get home")

Maximum 5 temporal_links per atom.
For each link, estimate uncertainty_window_ms:
  "at 7:15pm" -> 60000 (1 minute)
  "yesterday evening" -> 14400000 (4 hours)
  "last week" -> 604800000 (7 days)
  "last summer" -> 7776000000 (90 days)

If no temporal expression is mentioned, temporal_links should be an empty array.
```

**Verification**:

- Test with LLM: "Had dinner yesterday" -> 1 temporal_link (RETROSPECTIVE)
- Test with LLM: "We always go there on Fridays" -> 1 temporal_link (HABITUAL)
- Test with LLM: "Hello how are you" -> 0 temporal_links

---

##### Issue 2.3.2 -- Update MW Extraction Validator for temporal_links

**Status**: TODO
**Priority**: P1

**Files Touched**:

| File | Lines | Action |
|------|-------|--------|
| k1/memory_writer/invariants.py | Extraction validation section | ADD: temporal_links validation |

**Validation Rules**:

1. `temporal_links` is a list/tuple of TemporalLink objects.
2. Maximum 5 items (budget constraint: ~30 tokens per link in LLM output).
3. Each link has non-empty `mentioned_time`.
4. Each link has valid `link_type` (one of 6 enum values).
5. `confidence` is in [0.0, 1.0].
6. `uncertainty_window_ms >= 0`.

---

### Epic 2.4: K0 Receiver Changes (M08 + M13 + R0)

**Discovery**: GAP-002 Section 14 (K0 Receiver Changes Required)
**Effort**: MEDIUM (3-5 days)
**Problem**: K0 must parse temporal_links array from v2.1 atoms, store as JSONB in
st_hipp_events, and load into P03EventState for R0/R2 consumption.

#### Issues

---

##### Issue 2.4.1 -- Add temporal_links_json JSONB column to st_hipp_events

**Status**: TODO
**Priority**: P1

**Files Touched**:

| File | Lines | Action |
|------|-------|--------|
| k0/contracts/schemas/st_hipp_events_v2.columns.yaml | After temporal_orientation | ADD: temporal_links_json column |
| k0/db/alembic/versions/ | NEW FILE | Migration to add JSONB column |

**Schema**:

```yaml
temporal_links_json:
  type: JSONB
  nullable: true
  description: >
    Array of temporal references per atom. Each element:
    {mentioned_time, resolved_epoch_ms, uncertainty_window_ms, link_type, confidence}.
    From K1 MW v2.1 MemoryAtom.temporal_links. Stored as JSONB for flexible querying.
  owner: K1 MW (passthrough via M08)
  migration: "0076"
```

---

##### Issue 2.4.2 -- M08 parses temporal_links from v2.1 envelope

**Status**: TODO
**Priority**: P1

**Files Touched**:

| File | Lines | Action |
|------|-------|--------|
| k0/modules/context/temporal_profile.py | After normalize_timestamp | ADD: temporal_links parsing |

**What Needs To Be Done**:

1. M08 reads `body.temporal_links` from the envelope.
2. If present (v2.1 atom), validates each link and passes through.
3. If absent (v2.0 atom), constructs a single-element list from `body.temporal` (backward compat):

   ```python
   if body.get("temporal") and not body.get("temporal_links"):
       temporal_links = [{
           "mentioned_time": body["temporal"]["mentioned_time"],
           "resolved_epoch_ms": body["temporal"]["resolved_epoch_ms"],
           "uncertainty_window_ms": 0,
           "link_type": "RETROSPECTIVE" if body["temporal"]["is_backdated"] else "CONCURRENT",
           "confidence": 1.0,
       }]
   ```

4. Output: `temporal_links_json` (serialized JSON string for M13).

---

##### Issue 2.4.3 -- M13 writes temporal_links_json to st_hipp_events

**Status**: TODO
**Priority**: P1

**Files Touched**:

| File | Lines | Action |
|------|-------|--------|
| k0/modules/context/hipp_events_row.py | Row construction | ADD: temporal_links_json field |

---

##### Issue 2.4.4 -- R0 loads temporal_links into P03EventState

**Status**: TODO
**Priority**: P1

**Files Touched**:

| File | Lines | Action |
|------|-------|--------|
| k0/pipelines/p03/phases/r0_batch_selector.py | SQL SELECT, mapping | ADD: temporal_links_json |
| k0/pipelines/p03/event_state.py | Fields | ADD: temporal_links_json: str = "[]" |

---

##### Issue 2.4.5 -- Integration tests for multi-link temporal end-to-end

**Status**: TODO
**Priority**: P1

**Files Touched**:

| File | Lines | Action |
|------|-------|--------|
| tests/k0/modules/context/test_m08_temporal_links.py | NEW FILE | CREATE: Tests |
| tests/k0/pipelines/p03/test_r0_temporal_links.py | NEW FILE | CREATE: Tests |

**Test Cases**:

1. v2.1 atom with 3 temporal_links -> stored as JSONB -> loaded by R0
2. v2.0 atom with single temporal -> backward compat -> single-element list
3. v2.1 atom with empty temporal_links -> stored as empty array
4. v2.1 atom with 6 temporal_links -> validation error (max 5)
5. R0 loads temporal_links_json into P03EventState

---

## MILESTONE 3: Spatial Identity (P2)

> **Depends on**: Milestone 1 (clean temporal chain)
> **GAP-002 Reference**: Section 3, Section 11.2 S1-S5, Section 13 Step 3
> **Can run in parallel with Milestone 2** (no dependencies between temporal and spatial work)

### Epic 3.1: PlaceResolver Implementation

**Discovery**: GAP-002 Section 11.2 S1
**Effort**: MEDIUM (3-5 days)
**Problem**: "Olive Garden" visited 20 times creates 20 independent strings.
No stable place identity across visits. "Olive Garden on Main St" vs "Olive Garden" vs
"that Italian place" all refer to the same physical location but are stored as unlinked strings.

> **Pattern Reference**: PersonResolver in MW already resolves person names to stable person_ids
> using beliefs_active entities (type=PERSON). PlaceResolver follows the same architecture.

#### Issues

---

##### Issue 3.1.1 -- Create PlaceResolver following PersonResolver pattern

**Status**: TODO
**Priority**: P2

**Files Touched**:

| File | Lines | Action |
|------|-------|--------|
| k1/memory_writer/context/place_resolver.py | NEW FILE (~80 lines) | CREATE: PlaceResolver class |

**Upstream Data Source**:

- k1/sessionstate/sections/beliefs_active.py: `mentioned_entities` list contains EntityRef objects with `type="LOCATION"`
- Each EntityRef has: `id`, `type`, `display_name`, `confidence`, plus optional `aliases`
- MentionedLocation (beliefs_active.py L139-152): `raw_text`, `location_type`, `entity_id`, `confidence`
- PersonResolver pattern (memory_writer_architecture.md L1498+): reads entities during Stage 2, builds alias map, resolves natural names to stable IDs

**Current Code** (PersonResolver pattern from architecture doc):

```python
# PersonResolver pattern (what PlaceResolver must mirror):
# Stage 2 (Context Assembly):
#   snapshot = session_read_port.snapshot()
#   persons = [e for e in snapshot.beliefs_active.mentioned_entities if e.type == "PERSON"]
#   person_resolver = PersonResolver(persons)
# Stage 3 (LLM Extraction):
#   for participant in extraction.participants:
#       person_id = person_resolver.resolve(participant.name)  # "Mom" -> "person_mom"
```

**What Needs To Be Done**:

1. Create `k1/memory_writer/context/place_resolver.py` following PersonResolver architecture.
2. PlaceResolver reads beliefs_active entities where `type == "LOCATION"`.
3. Builds a case-insensitive alias map: canonical name + aliases -> stable `place_id`.
4. `place_id` format: `place_<slug>` where slug = lowercase, spaces to underscores, stripped of punctuation.
5. Fuzzy match support: "Olive Garden" matches "Olive Garden on Main St" via prefix/substring match.
6. Return `None` if no match found (defensive -- no hallucinated place_ids).

**How To Implement**:

```python
import re
from dataclasses import dataclass
from typing import Optional


@dataclass(frozen=True)
class ResolvedPlace:
    place_id: str
    canonical_name: str
    confidence: float


class PlaceResolver:
    """Resolve location names to stable place_ids.

    Follows the PersonResolver pattern: reads entities (type=LOCATION) from
    beliefs_active, builds an alias map, resolves raw location strings to
    stable identifiers.
    """

    def __init__(self, location_entities: list) -> None:
        self._alias_map: dict[str, ResolvedPlace] = {}
        for entity in location_entities:
            if getattr(entity, "type", None) != "LOCATION":
                continue
            canonical = getattr(entity, "display_name", "") or ""
            if not canonical.strip():
                continue
            place_id = self._to_place_id(canonical)
            resolved = ResolvedPlace(
                place_id=place_id,
                canonical_name=canonical.strip(),
                confidence=getattr(entity, "confidence", 1.0),
            )
            self._alias_map[canonical.strip().lower()] = resolved
            for alias in getattr(entity, "aliases", []):
                if alias and alias.strip():
                    self._alias_map[alias.strip().lower()] = resolved

    def resolve(self, name: str) -> Optional[str]:
        if not name or not name.strip():
            return None
        key = name.strip().lower()
        # Exact match first
        resolved = self._alias_map.get(key)
        if resolved:
            return resolved.place_id
        # Prefix match fallback ("Olive Garden" matches "olive garden on main st")
        for alias_key, alias_resolved in self._alias_map.items():
            if alias_key.startswith(key) or key.startswith(alias_key):
                return alias_resolved.place_id
        return None

    @staticmethod
    def _to_place_id(canonical_name: str) -> str:
        slug = re.sub(r"[^a-z0-9]+", "_", canonical_name.strip().lower()).strip("_")
        return f"place_{slug}"
```

**Verification**:

- Run: `pytest tests/k1/memory_writer/ -x -k place_resolver`
- Verify: `PlaceResolver([entity(type="LOCATION", display_name="Olive Garden")]).resolve("Olive Garden")` returns `"place_olive_garden"`
- Verify: `PlaceResolver([]).resolve("anything")` returns `None` (empty entities = no resolution)
- Verify: Alias match: entity with aliases=["that Italian place"] resolves to same place_id
- Verify: Case insensitive: "olive garden" matches "Olive Garden"

**Data Persistence Path**:

```
beliefs_active.mentioned_entities (type=LOCATION)
  -> MW Stage 2: PlaceResolver(location_entities) constructed
    -> MW Stage 4: place_id = resolver.resolve(extraction.location_name)
      -> body.place_id = place_id (on MWEnvelope)
        -> K0 M13: st_hipp_events.place_id = body.place_id
```

---

##### Issue 3.1.2 -- Add place_id to MemoryAtom

**Status**: TODO
**Priority**: P2
**Depends on**: Issue 3.1.1 (PlaceResolver exists)

**Files Touched**:

| File | Lines | Action |
|------|-------|--------|
| k1/memory_writer/types.py | L319-373 (MemoryAtom) | ADD: `place_id: Optional[str] = None` |
| k1/contracts/schemas/memory_writer/memory_atom.v2.schema.json | properties section | ADD: place_id string property |

**Upstream Data Source**:

- PlaceResolver.resolve() output (Issue 3.1.1)
- Must be Optional because PlaceResolver may return None (no matching entity)

**Current Code** (types.py MemoryAtom spatial fields):

```python
@dataclass(frozen=True)
class MemoryAtom:
    # ... 34 fields ...
    location_name: Optional[str] = None
    location_type: Optional[LocationType] = None
    # No place_id field
```

**How To Implement**:

```python
# types.py -- MemoryAtom, after location_type:
place_id: Optional[str] = None  # Stable place identity from PlaceResolver
```

```json
// memory_atom.v2.schema.json -- properties section:
"place_id": {
    "type": ["string", "null"],
    "description": "Stable place identity resolved by PlaceResolver. Pattern: place_<slug>.",
    "pattern": "^place_[a-z0-9_]+$"
}
```

**Verification**:

- Run: `pytest tests/k1/memory_writer/ -x`
- Verify: `MemoryAtom(place_id="place_olive_garden")` constructs without error
- Verify: `MemoryAtom()` has `place_id=None` (backward compatible)
- Verify: Schema validation passes with and without place_id

**Data Persistence Path**:

```
MemoryAtom.place_id (types.py)
  -> Envelope Builder: body.place_id = atom.place_id
    -> Bridge passthrough: envelope.body.place_id
      -> K0 M13: st_hipp_events.place_id
```

---

##### Issue 3.1.3 -- Wire PlaceResolver into MW Stage 2 and Stage 4

**Status**: TODO
**Priority**: P2
**Depends on**: Issue 3.1.1 (PlaceResolver), Issue 3.1.2 (place_id on MemoryAtom)

**Files Touched**:

| File | Lines | Action |
|------|-------|--------|
| k1/memory_writer/ (context assembly) | Stage 2 | ADD: Build PlaceResolver from snapshot.beliefs_active entities |
| k1/memory_writer/ (envelope builder) | Stage 4 | ADD: Resolve place_id from extraction.location_name |
| k1/memory_writer/config.py | MWConfig | VERIFY: beliefs_active is in session_sections_hot (already is) |

**Upstream Data Source**:

- Stage 2 reads `session_read_port.snapshot().beliefs_active.mentioned_entities` (same as PersonResolver)
- Stage 4 reads `extraction.location_name` (LLM-extracted location string)

**Current Code** (config.py -- beliefs_active already in HOT sections):

```python
session_sections_hot = [
    "beliefs_active",  # Already read -- contains mentioned_entities
    "beliefs_history", "history_active", "history_recent",
    # ...
]
```

**What Needs To Be Done**:

1. In Stage 2 (Context Assembly), construct PlaceResolver from snapshot:

   ```python
   location_entities = [
       e for e in snapshot.beliefs_active.mentioned_entities
       if e.type == "LOCATION"
   ]
   place_resolver = PlaceResolver(location_entities)
   ```

2. Pass `place_resolver` through to Stage 4 (same pattern as `person_resolver`).
3. In Stage 4 (Envelope Builder), after LLM extraction produces `location_name`:

   ```python
   body["place_id"] = place_resolver.resolve(extraction.location_name)
   ```

4. If extraction.location_name is None, place_id stays None (no resolution attempted).

**How To Implement**:

```python
# Stage 2 (Context Assembly) -- alongside PersonResolver:
from k1.memory_writer.context.place_resolver import PlaceResolver

location_entities = [
    e for e in snapshot.beliefs_active.mentioned_entities
    if getattr(e, "type", None) == "LOCATION"
]
place_resolver = PlaceResolver(location_entities)

# Stage 4 (Envelope Builder) -- after extraction:
for atom in extraction.atoms:
    place_id = place_resolver.resolve(atom.location_name) if atom.location_name else None
    # Set on envelope body:
    body["place_id"] = place_id
```

**Verification**:

- Run: `pytest tests/k1/memory_writer/ -x`
- Integration test: Turn with "Had dinner at Olive Garden" where beliefs_active has LOCATION entity "Olive Garden" -> envelope.body.place_id = "place_olive_garden"
- Integration test: Turn with "Had dinner somewhere" and no LOCATION entity -> envelope.body.place_id = None
- Verify: PlaceResolver construction does not exceed 1ms (MW-02 invariant: lock-free read)

**Data Persistence Path**:

```
beliefs_active.mentioned_entities (type=LOCATION)
  -> Stage 2: PlaceResolver(location_entities)
    -> Stage 4: place_id = resolver.resolve(atom.location_name)
      -> body.place_id on MWEnvelope
        -> Bridge passthrough
          -> K0 M13 -> st_hipp_events.place_id
```

---

### Epic 3.2: st_hipp_events place_id Column

**Discovery**: GAP-002 Section 19.6 (spatial columns)
**Effort**: LOW (1-2 days)

#### Issues

---

##### Issue 3.2.1 -- Add place_id column to st_hipp_events

**Status**: TODO
**Priority**: P2

**Files Touched**:

| File | Lines | Action |
|------|-------|--------|
| k0/contracts/schemas/st_hipp_events_v2.columns.yaml | After geohash_6 (Section 19.6) | ADD: place_id TEXT NULLABLE |
| k0/db/alembic/versions/0077_st_hipp_events_place_id.py | NEW FILE | CREATE: Migration |

**Upstream Data Source**:

- body.place_id from MWEnvelope (resolved by K1 PlaceResolver, Issue 3.1.3)
- Nullable: not all atoms have a resolved place identity
- Format: `place_<slug>` (regex: `^place_[a-z0-9_]+$`)

**Current Schema** (st_hipp_events Section 19.6 -- Spatial columns):

```
# 46: location_name  TEXT nullable  (K0 M15/M12)
# 47: location_type  TEXT nullable  (K0 M15/M12)
# 48: geohash_6      TEXT nullable  (K0 M12)
# 49: geo_precision_external TEXT nullable (K0 M12)
# 50: geo_masking_reason TEXT nullable (K0 M12)
# -- No place_id column --
```

**How To Implement**:

```python
# k0/db/alembic/versions/0077_st_hipp_events_place_id.py

revision = "0077"
down_revision = "0076"  # After temporal_links_json from M2

def upgrade():
    op.add_column(
        "st_hipp_events",
        sa.Column("place_id", sa.Text(), nullable=True,
                  comment="Stable place identity from K1 PlaceResolver. Pattern: place_<slug>.")
    )
    # Index for familiarity queries (count by place_id per tenant)
    op.create_index(
        "ix_st_hipp_events_place_id",
        "st_hipp_events",
        ["tenant_id", "place_id"],
        postgresql_where=sa.text("place_id IS NOT NULL")
    )

def downgrade():
    op.drop_index("ix_st_hipp_events_place_id")
    op.drop_column("st_hipp_events", "place_id")
```

**Column Contract Update** (st_hipp_events_v2.columns.yaml):

```yaml
place_id:
  type: TEXT
  nullable: true
  owner: K1_MW
  source: PlaceResolver
  description: "Stable place identity. Pattern: place_<slug>."
  migration: "0077"
  section: "19.6 SPATIAL and PLACE"
```

**Verification**:

- Run: migration against local postgres (`alembic upgrade head`)
- Verify: `\d st_hipp_events` shows `place_id TEXT` column
- Verify: Index `ix_st_hipp_events_place_id` exists with partial WHERE clause
- Verify: `SELECT place_id FROM st_hipp_events LIMIT 1` returns NULL (no data yet)

---

##### Issue 3.2.2 -- M13 writes place_id from envelope body

**Status**: TODO
**Priority**: P2
**Depends on**: Issue 3.2.1 (column exists)

**Files Touched**:

| File | Lines | Action |
|------|-------|--------|
| k0/modules/builders/hipp_events_row.py | L338-347 (map_spatial_group) | ADD: place_id mapping |

**Upstream Data Source**:

- `envelope.body.place_id` (string or null, from K1 PlaceResolver via Bridge passthrough)
- Falls through M15 (spatial_minimal) and M12 (geo_metadata) unchanged -- they do not touch place_id

**Current Code** (hipp_events_row.py L338-347):

```python
def map_spatial_group(geo_output: Dict[str, Any], spatial_output: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "location_name": spatial_output.get("location_name") or geo_output.get("location_name"),
        "location_type": spatial_output.get("location_type") or geo_output.get("location_type"),
        "geohash_6": spatial_output.get("geohash_6") or geo_output.get("geohash_6"),
        "geo_precision_external": geo_output.get("geo_precision_external"),
        "geo_masking_reason": geo_output.get("geo_masking_reason"),
    }
```

**How To Implement**:

```python
def map_spatial_group(geo_output: Dict[str, Any], spatial_output: Dict[str, Any],
                      envelope: Dict[str, Any] = None) -> Dict[str, Any]:
    result = {
        "location_name": spatial_output.get("location_name") or geo_output.get("location_name"),
        "location_type": spatial_output.get("location_type") or geo_output.get("location_type"),
        "geohash_6": spatial_output.get("geohash_6") or geo_output.get("geohash_6"),
        "geo_precision_external": geo_output.get("geo_precision_external"),
        "geo_masking_reason": geo_output.get("geo_masking_reason"),
    }
    # place_id is a K1 MW passthrough -- not enriched by M12/M15
    if envelope:
        body = envelope.get("body", {})
        result["place_id"] = body.get("place_id")
    return result
```

**Verification**:

- Run: `pytest tests/k0/modules/builders/ -x`
- Verify: Envelope with `body.place_id = "place_olive_garden"` produces row with `place_id = "place_olive_garden"`
- Verify: Envelope without body.place_id produces row with `place_id = None`

**Data Persistence Path**:

```
envelope.body.place_id
  -> M13 map_spatial_group(envelope=envelope)
    -> row["place_id"] = "place_olive_garden"
      -> INSERT INTO st_hipp_events (..., place_id, ...) VALUES (..., 'place_olive_garden', ...)
```

---

##### Issue 3.2.3 -- R0 loads place_id into P03EventState

**Status**: TODO
**Priority**: P2
**Depends on**: Issue 3.2.1 (column exists)

**Files Touched**:

| File | Lines | Action |
|------|-------|--------|
| k0/pipelines/p03/event_state.py | L130-160 (Spatial fields) | ADD: `place_id: str = ""` |
| k0/pipelines/p03/phases/r0_batch_selector.py | SQL SELECT (~L557-594) | ADD: place_id to SELECT |
| k0/pipelines/p03/phases/r0_batch_selector.py | Row mapping (~L664-677) | ADD: place_id assignment |

**Current Code** (event_state.py spatial fields):

```python
location_name: str = ""              # Resolved place name
location_type: str = ""              # Category
geohash_6: str = ""                  # 6-char geohash
```

**How To Implement**:

```python
# event_state.py -- after geohash_6:
place_id: str = ""  # Stable place identity from K1 PlaceResolver

# r0_batch_selector.py -- SQL SELECT:
# Add "place_id" to the SELECT column list

# r0_batch_selector.py -- row mapping:
event.place_id = row["place_id"] or ""
```

**Verification**:

- Run: `pytest tests/k0/pipelines/p03/ -x`
- Verify: P03EventState().place_id defaults to `""`
- Verify: R0 loads place_id from st_hipp_events into P03EventState
- Verify: R2 EventAdapter can access event.place_id for spatial episode boundary detection

---

### Epic 3.3: Spatial Familiarity Tracking (K0)

**Discovery**: GAP-002 Section 11.2 S4
**Effort**: LOW (2-3 days)
**Problem**: No visit counting or familiarity metric. "Our usual Friday spot" vs
"we tried a new restaurant" encode differently in human memory.

> **Owner**: K0 P02 (not MW). Familiarity is computed from historical visit count per
> place_id per user in st_hipp_events. MW does not need to track this.

#### Issues

---

##### Issue 3.3.1 -- Add spatial_familiarity column to st_hipp_events

**Status**: TODO
**Priority**: P3 (enrichment, not blocking)
**Depends on**: Issue 3.2.1 (place_id column exists)

**Files Touched**:

| File | Lines | Action |
|------|-------|--------|
| k0/contracts/schemas/st_hipp_events_v2.columns.yaml | After place_id | ADD: spatial_familiarity TEXT NULLABLE |
| k0/db/alembic/versions/0078_st_hipp_events_spatial_familiarity.py | NEW FILE | CREATE: Migration |

**Upstream Data Source**:

- Computed by K0 P02 from historical visit count per (tenant_id, place_id) in st_hipp_events
- NOT from K1 MW -- MW has no access to historical visit data
- Values: `FIRST_VISIT` / `OCCASIONAL` (2-5 visits) / `REGULAR` (6-20) / `DAILY` (21+)

**How To Implement**:

```python
# Migration: 0078_st_hipp_events_spatial_familiarity.py
def upgrade():
    op.add_column(
        "st_hipp_events",
        sa.Column("spatial_familiarity", sa.Text(), nullable=True,
                  comment="Visit familiarity: FIRST_VISIT/OCCASIONAL/REGULAR/DAILY")
    )
    op.create_check_constraint(
        "ck_spatial_familiarity",
        "st_hipp_events",
        sa.text("spatial_familiarity IS NULL OR spatial_familiarity IN "
                "('FIRST_VISIT', 'OCCASIONAL', 'REGULAR', 'DAILY')")
    )
```

**Verification**:

- Run: migration against local postgres
- Verify: Column exists with CHECK constraint
- Verify: NULL is valid (most existing rows will be NULL)

---

##### Issue 3.3.2 -- P02 module computes familiarity from visit history

**Status**: TODO
**Priority**: P3
**Depends on**: Issue 3.3.1 (column exists), Issue 3.2.1 (place_id column)

**Files Touched**:

| File | Lines | Action |
|------|-------|--------|
| k0/modules/context/spatial_minimal.py | After location resolution | ADD: familiarity lookup query |
| k0/modules/builders/hipp_events_row.py | map_spatial_group | ADD: spatial_familiarity field |

**Upstream Data Source**:

- SQL query: `SELECT COUNT(*) FROM st_hipp_events WHERE tenant_id = $1 AND place_id = $2 AND place_id IS NOT NULL`
- place_id from envelope.body.place_id (K1 PlaceResolver output, passthrough)

**What Needs To Be Done**:

1. In M15 (spatial_minimal.py) or a new dedicated P02 module, query st_hipp_events for visit count.
2. Map count to familiarity band:
   - 0 previous visits = `FIRST_VISIT`
   - 1-4 = `OCCASIONAL`
   - 5-19 = `REGULAR`
   - 20+ = `DAILY`
3. If place_id is NULL, spatial_familiarity = NULL (cannot compute without identity).
4. M13 writes the computed familiarity to st_hipp_events.

**How To Implement**:

```python
# In spatial_minimal.py or a new familiarity module:
async def compute_familiarity(tenant_id: str, place_id: Optional[str], conn) -> Optional[str]:
    if not place_id:
        return None
    row = await conn.fetchrow(
        "SELECT COUNT(*) as cnt FROM st_hipp_events "
        "WHERE tenant_id = $1 AND place_id = $2",
        tenant_id, place_id
    )
    count = row["cnt"] if row else 0
    if count == 0:
        return "FIRST_VISIT"
    elif count < 5:
        return "OCCASIONAL"
    elif count < 20:
        return "REGULAR"
    else:
        return "DAILY"
```

**Verification**:

- Run: `pytest tests/k0/modules/context/ -x`
- Verify: First event with place_id="place_olive_garden" -> `FIRST_VISIT`
- Verify: After 5 events with same place_id -> `REGULAR`
- Verify: Event without place_id -> `NULL` (no familiarity computed)

**Data Persistence Path**:

```
envelope.body.place_id = "place_olive_garden"
  -> M15 spatial_minimal: query st_hipp_events for visit count
    -> count = 3 -> "OCCASIONAL"
      -> M13 map_spatial_group: row["spatial_familiarity"] = "OCCASIONAL"
        -> INSERT INTO st_hipp_events (..., spatial_familiarity, ...) VALUES (..., 'OCCASIONAL', ...)
```

---

## MILESTONE 4: Per-Atom Signal Enrichment (P3)

> **Depends on**: Milestone 3 (place_id for transition_from)
> **GAP-002 Reference**: Section 11.1 T8, Section 11.2 S2, S3

### Epic 4.1: Intra-Turn Extraction Ordering

**Discovery**: GAP-002 Section 11.1 T8
**Effort**: LOW (1 day)

#### Issues

---

##### Issue 4.1.1 -- Add extraction_sequence to MemoryAtom and schema

**Status**: TODO
**Priority**: P3

**Files Touched**:

| File | Lines | Action |
|------|-------|--------|
| k1/memory_writer/types.py | L319-373 (MemoryAtom) | ADD: `extraction_sequence: int = 0` |
| k1/contracts/schemas/memory_writer/memory_atom.v2.schema.json | properties | ADD: extraction_sequence integer |

**BOUNDARY NOTE**: This is a per-atom signal, NOT consolidation. Only MW knows the
extraction order within a turn (P03 cannot infer this from timestamps alone since all
atoms in a turn share the same `conversation_anchor_ms`). MW records the ordinal as a
fact about the atom. P03 may optionally use this signal for intra-episode ordering
during narrative chain construction, but the ordering decision remains P03's.

**Upstream Data Source**:

- MW Stage 3 (LLM Extraction) produces 0-6 atoms per turn (MW-05 invariant: max_atoms_per_turn=6)
- The LLM returns atoms in the order they appear in the conversation text
- Ordinal is the 0-based index of each atom within a single turn's extraction batch

**Current Code** (types.py MemoryAtom -- no extraction ordering):

```python
@dataclass(frozen=True)
class MemoryAtom:
    # ... 34+ fields ...
    conversation_turn: int = 0       # Turn number (across conversation)
    # No within-turn ordering
```

**How To Implement**:

```python
# types.py -- MemoryAtom, after conversation_turn:
extraction_sequence: int = 0  # 0-based ordinal within turn's extraction batch
```

```json
// memory_atom.v2.schema.json -- properties:
"extraction_sequence": {
    "type": "integer",
    "minimum": 0,
    "maximum": 5,
    "default": 0,
    "description": "0-based ordinal of this atom within the turn's extraction batch. First atom = 0."
}
```

**Verification**:

- Run: `pytest tests/k1/memory_writer/ -x`
- Verify: `MemoryAtom(extraction_sequence=2)` constructs without error
- Verify: `MemoryAtom()` has `extraction_sequence=0` (backward compatible)
- Verify: Schema validation accepts values 0-5 and rejects negative values

**Data Persistence Path**:

```
MW Stage 3: LLM produces [atom_0, atom_1, atom_2]
  -> Stage 5 Batch Aggregation: atom_0.extraction_sequence = 0, atom_1 = 1, atom_2 = 2
    -> Envelope Builder: body.extraction_sequence = atom.extraction_sequence
      -> K0 M13 -> st_hipp_events.extraction_sequence
```

---

##### Issue 4.1.2 -- MW assigns extraction_sequence during Stage 5 batch aggregation

**Status**: TODO
**Priority**: P3
**Depends on**: Issue 4.1.1 (extraction_sequence on MemoryAtom)

**Files Touched**:

| File | Lines | Action |
|------|-------|--------|
| k1/memory_writer/ (batch aggregation) | Stage 5 | EDIT: Assign ordinal to each atom in batch |
| k0/modules/builders/hipp_events_row.py | Body field mapping (~L362-423) | ADD: extraction_sequence |
| k0/contracts/schemas/st_hipp_events_v2.columns.yaml | After temporal_links_json | ADD: extraction_sequence INTEGER |
| k0/db/alembic/versions/0079_st_hipp_events_extraction_seq.py | NEW FILE | CREATE: Migration |
| k0/pipelines/p03/event_state.py | Fields | ADD: `extraction_sequence: int = 0` |
| k0/pipelines/p03/phases/r0_batch_selector.py | SQL SELECT, mapping | ADD: extraction_sequence |

**Upstream Data Source**:

- MW Stage 5 (Batch Aggregation) collects 0-6 atoms from Stage 3 in the 250ms window
- Each atom gets a 0-based ordinal in emission order (first extracted = 0)
- The ordinal is set BEFORE envelope construction, on the MemoryAtom itself

**What Needs To Be Done**:

1. In MW Stage 5 batch aggregation, enumerate atoms and set `extraction_sequence`:

   ```python
   for i, atom in enumerate(batch_atoms):
       atom = dataclasses.replace(atom, extraction_sequence=i)
   ```

   Note: MemoryAtom is frozen, so must use `dataclasses.replace()` to set the ordinal.
2. Envelope Builder maps `body.extraction_sequence = atom.extraction_sequence`.
3. K0 migration adds `extraction_sequence INTEGER DEFAULT 0` to st_hipp_events.
4. M13 maps `body.extraction_sequence` to `row["extraction_sequence"]`.
5. R0 loads `extraction_sequence` into P03EventState.

**How To Implement**:

```python
# MW Stage 5 -- batch aggregation:
import dataclasses

ordered_atoms = []
for i, atom in enumerate(batch_atoms):
    ordered_atoms.append(dataclasses.replace(atom, extraction_sequence=i))
# Submit ordered_atoms to envelope builder
```

```python
# K0 migration: 0079_st_hipp_events_extraction_seq.py
def upgrade():
    op.add_column(
        "st_hipp_events",
        sa.Column("extraction_sequence", sa.Integer(), nullable=True, server_default="0",
                  comment="0-based ordinal within turn extraction batch")
    )

def downgrade():
    op.drop_column("st_hipp_events", "extraction_sequence")
```

**Verification**:

- Run: `pytest tests/k1/memory_writer/ tests/k0/modules/builders/ tests/k0/pipelines/p03/ -x`
- Verify: Turn producing 3 atoms -> atoms have extraction_sequence 0, 1, 2
- Verify: Single-atom turn -> extraction_sequence = 0
- Verify: R0 loads extraction_sequence into P03EventState
- Verify: Migration applies cleanly, existing rows get default 0

---

### Epic 4.2: Spatial Hierarchy Signal

**Discovery**: GAP-002 Section 11.2 S2
**Effort**: LOW (1-2 days)

#### Issues

---

##### Issue 4.2.1 -- Add location_hierarchy to MemoryAtom and schema

**Status**: TODO
**Priority**: P3

**Files Touched**:

| File | Lines | Action |
|------|-------|--------|
| k1/memory_writer/types.py | L319-373 (MemoryAtom) | ADD: `location_hierarchy: tuple = ()` |
| k1/contracts/schemas/memory_writer/memory_atom.v2.schema.json | properties | ADD: location_hierarchy string array |
| k0/modules/builders/hipp_events_row.py | Body field mapping | ADD: location_hierarchy_json |
| k0/contracts/schemas/st_hipp_events_v2.columns.yaml | After place_id | ADD: location_hierarchy_json TEXT |
| k0/db/alembic/versions/0079_st_hipp_events_extraction_seq.py | Same migration | ADD: location_hierarchy_json TEXT column |

**BOUNDARY NOTE**: This is a per-atom signal extracted from the conversation text by
MW's LLM. The hierarchy describes THIS atom's spatial context ("kitchen at home in
Seattle"), not a cross-atom inference. K0 does NOT have access to the original
conversation text and cannot extract this hierarchy. MW provides the raw hierarchy
signal; K0 P02/P03 may enrich or normalize it (e.g., resolving to canonical place_ids
at each level), but the initial extraction is MW's job.

**Upstream Data Source**:

- LLM extraction during Stage 3 (prompted to extract spatial hierarchy)
- Example: "cooking in the kitchen at home" -> `("kitchen", "home")`
- Example: "walking in Capitol Hill, Seattle" -> `("Capitol Hill", "Seattle")`
- Ordered from most specific (room/area) to most general (city/region)
- Empty tuple if no hierarchy can be extracted (single-level location)

**Current Code** (types.py -- no hierarchy):

```python
@dataclass(frozen=True)
class MemoryAtom:
    location_name: Optional[str] = None    # "Olive Garden"
    location_type: Optional[LocationType] = None  # restaurant
    # No hierarchy: "kitchen at home in Seattle" = flat "home"
```

**How To Implement**:

```python
# types.py -- MemoryAtom, after place_id:
location_hierarchy: tuple = ()  # Most specific -> most general: ("kitchen", "home", "Seattle")
```

```json
// memory_atom.v2.schema.json -- properties:
"location_hierarchy": {
    "type": "array",
    "items": {"type": "string"},
    "default": [],
    "maxItems": 5,
    "description": "Spatial hierarchy from most specific to most general. Example: ['kitchen', 'home', 'Capitol Hill', 'Seattle']."
}
```

```python
# hipp_events_row.py -- in body field extraction:
import json
hierarchy = body.get("location_hierarchy", [])
row["location_hierarchy_json"] = json.dumps(hierarchy) if hierarchy else None
```

**Verification**:

- Run: `pytest tests/k1/memory_writer/ -x`
- Verify: `MemoryAtom(location_hierarchy=("kitchen", "home"))` constructs correctly
- Verify: `MemoryAtom()` has `location_hierarchy=()` (backward compatible)
- Verify: Schema validates arrays of 0-5 strings, rejects 6+ items
- Verify: M13 serializes to JSON string in st_hipp_events

**Data Persistence Path**:

```
MW Stage 3 LLM: "cooking in the kitchen at home" -> hierarchy=["kitchen", "home"]
  -> MemoryAtom(location_hierarchy=("kitchen", "home"))
    -> Envelope Builder: body.location_hierarchy = ["kitchen", "home"]
      -> K0 M13: row["location_hierarchy_json"] = '["kitchen", "home"]'
        -> st_hipp_events.location_hierarchy_json
```

---

##### Issue 4.2.2 -- Update LLM prompt for spatial hierarchy extraction

**Status**: TODO
**Priority**: P3
**Depends on**: Issue 4.2.1 (location_hierarchy on MemoryAtom)

**Files Touched**:

| File | Lines | Action |
|------|-------|--------|
| k1/memory_writer/ (persona prompt) | Spatial extraction section | ADD: Hierarchy extraction instructions |

**Upstream Data Source**:

- LLM (GPT-4o-mini) during MW Stage 3
- Budget: ~30 extra tokens per atom for hierarchy (within MW-06 2000 token limit)

**What Needs To Be Done**:

1. Add hierarchy extraction instructions to the MW persona prompt.
2. The instruction must tell the LLM to identify nested spatial levels.
3. Order: most specific (room/area) to most general (city/region).
4. Max 5 levels (schema constraint).
5. If only one level identifiable, return single-element array.

**How To Implement**:

Add to `memory_writer_persona.md` (or equivalent prompt template):

```
For each memory, if a location is mentioned, extract the spatial hierarchy:
  - Identify nested spatial levels from most specific to most general
  - "cooking in the kitchen at home" -> ["kitchen", "home"]
  - "walking in Capitol Hill, Seattle" -> ["Capitol Hill", "Seattle"]
  - "at the office" -> ["office"] (single level)
  - Maximum 5 levels
  - Omit if no location context is present
```

**Verification**:

- Manual test: Feed "had lunch in the kitchen at home in Seattle" to MW pipeline
- Verify: LLM output includes `location_hierarchy: ["kitchen", "home", "Seattle"]`
- Verify: Atom without location context has empty hierarchy
- Verify: Token budget stays within MW-06 2000 token limit

---

### Epic 4.3: Spatial Transition Signal

**Discovery**: GAP-002 Section 11.2 S3
**Effort**: LOW (1-2 days)

#### Issues

---

##### Issue 4.3.1 -- Add transition fields to MemoryAtom and schema

**Status**: TODO
**Priority**: P3
**Depends on**: Issue 3.1.2 (place_id exists on MemoryAtom for transition_from referencing)

**Files Touched**:

| File | Lines | Action |
|------|-------|--------|
| k1/memory_writer/types.py | L319-373 (MemoryAtom) | ADD: `transition_from_place` and `transition_mode` |
| k1/contracts/schemas/memory_writer/memory_atom.v2.schema.json | properties | ADD: transition_from_place, transition_mode |
| k0/modules/builders/hipp_events_row.py | Body field mapping | ADD: spatial_context_json (bundled JSONB) |
| k0/contracts/schemas/st_hipp_events_v2.columns.yaml | After location_hierarchy_json | ADD: spatial_context_json TEXT |

**BOUNDARY NOTE**: `transition_from_place` references a PLACE (name or place_id), not
another atom. "After dinner we drove to the movies" = this atom's location is "movies",
transition_from is "restaurant", transition_mode is "drove". This is per-atom spatial
context extracted from the conversation text -- the LLM is describing WHERE this memory
happened and HOW the user got there. P03 builds spatial NARRATIVES across atoms;
MW provides the per-atom spatial signals that P03 consumes.

**Upstream Data Source**:

- LLM extraction during Stage 3 (prompted to detect movement between places)
- `transition_from_place`: origin place name (raw text or resolved place_id if available)
- `transition_mode`: mode of movement -- one of: walked, drove, flew, took_bus, took_train, biked, other
- Both are Optional -- most atoms have no transition (static location)

**Current Code** (types.py -- no transition fields):

```python
@dataclass(frozen=True)
class MemoryAtom:
    location_name: Optional[str] = None    # Current location
    location_type: Optional[LocationType] = None
    # No transition_from or transition_mode
```

**How To Implement**:

```python
# types.py -- MemoryAtom, after location_hierarchy:
transition_from_place: Optional[str] = None  # Origin place name/id: "restaurant", "place_olive_garden"
transition_mode: Optional[str] = None        # Movement mode: walked/drove/flew/took_bus/took_train/biked/other
```

```json
// memory_atom.v2.schema.json -- properties:
"transition_from_place": {
    "type": ["string", "null"],
    "description": "Origin place for spatial transition. Raw place name or resolved place_id."
},
"transition_mode": {
    "type": ["string", "null"],
    "enum": [null, "walked", "drove", "flew", "took_bus", "took_train", "biked", "other"],
    "description": "Mode of movement from transition_from_place to current location."
}
```

For K0 storage, bundle transition fields into a JSONB column rather than adding 2 more
scalar columns (per GAP-002 Section 21 Phase 3 note):

```python
# hipp_events_row.py -- bundled spatial context:
spatial_ext = {}
if body.get("transition_from_place"):
    spatial_ext["transition_from_place"] = body["transition_from_place"]
if body.get("transition_mode"):
    spatial_ext["transition_mode"] = body["transition_mode"]
if body.get("location_hierarchy"):
    spatial_ext["location_hierarchy"] = body["location_hierarchy"]
row["spatial_context_json"] = json.dumps(spatial_ext) if spatial_ext else None
```

**Alternative**: Use the already-proposed `location_hierarchy_json` column for hierarchy
and add `transition_from_place` + `transition_mode` as separate scalar columns. Decision
should be captured in ADR. The JSONB bundle approach (spatial_context_json) is recommended
to avoid column proliferation.

**Verification**:

- Run: `pytest tests/k1/memory_writer/ -x`
- Verify: `MemoryAtom(transition_from_place="restaurant", transition_mode="drove")` constructs
- Verify: `MemoryAtom()` has both fields as `None` (backward compatible)
- Verify: Schema validates transition_mode enum values, rejects invalid modes
- Verify: K0 spatial_context_json stores bundled transitions correctly

**Data Persistence Path**:

```
MW Stage 3 LLM: "After dinner we drove to the movies"
  -> MemoryAtom(location_name="movies", transition_from_place="restaurant", transition_mode="drove")
    -> Envelope Builder: body.transition_from_place, body.transition_mode
      -> K0 M13: spatial_context_json = '{"transition_from_place": "restaurant", "transition_mode": "drove"}'
        -> st_hipp_events.spatial_context_json
```

---

##### Issue 4.3.2 -- Update LLM prompt for spatial transition extraction

**Status**: TODO
**Priority**: P3
**Depends on**: Issue 4.3.1 (transition fields on MemoryAtom)

**Files Touched**:

| File | Lines | Action |
|------|-------|--------|
| k1/memory_writer/ (persona prompt) | Spatial extraction section | ADD: Transition extraction instructions |

**Upstream Data Source**:

- LLM (GPT-4o-mini) during MW Stage 3
- Budget: ~20 extra tokens per atom for transition (within MW-06 2000 token limit)

**What Needs To Be Done**:

1. Add transition detection instructions to the MW persona prompt.
2. The instruction must tell the LLM to identify movement between places.
3. Only extract transitions when explicitly mentioned in conversation text.
4. Do NOT infer transitions that are not stated (no hallucinated movements).

**How To Implement**:

Add to `memory_writer_persona.md` (or equivalent prompt template):

```
For each memory, if movement between places is mentioned, extract the transition:
  - "After dinner we drove to the movies" -> transition_from_place: "restaurant", transition_mode: "drove"
  - "Walked home from the park" -> transition_from_place: "park", transition_mode: "walked"
  - "At the office" -> no transition (static location, omit both fields)
  - Only extract transitions explicitly mentioned in the text
  - Do not infer transitions that are not stated
  - Modes: walked, drove, flew, took_bus, took_train, biked, other
```

**Verification**:

- Manual test: "We drove from the restaurant to the cinema" -> transition_from_place="restaurant", mode="drove"
- Manual test: "Had dinner at home" -> no transition fields (both null)
- Verify: Token budget stays within MW-06 2000 token limit

---

##### Issue 4.3.3 -- K0 migration for spatial_context_json column

**Status**: TODO
**Priority**: P3
**Depends on**: Issue 4.3.1 (transition fields defined)

**Files Touched**:

| File | Lines | Action |
|------|-------|--------|
| k0/db/alembic/versions/0079_st_hipp_events_extraction_seq.py | Same migration | ADD: spatial_context_json TEXT column |
| k0/pipelines/p03/event_state.py | Fields | ADD: `spatial_context_json: str = ""` |
| k0/pipelines/p03/phases/r0_batch_selector.py | SQL SELECT, mapping | ADD: spatial_context_json |

**How To Implement**:

```python
# In migration 0079 (bundled with extraction_sequence):
op.add_column(
    "st_hipp_events",
    sa.Column("spatial_context_json", sa.Text(), nullable=True,
              comment="Bundled spatial context: transition_from_place, transition_mode, location_hierarchy")
)
```

```python
# event_state.py:
spatial_context_json: str = ""  # Bundled: transition, hierarchy

# r0_batch_selector.py -- SQL SELECT:
# Add "spatial_context_json" to SELECT
# Row mapping:
event.spatial_context_json = row["spatial_context_json"] or ""
```

**Verification**:

- Run: migration against local postgres
- Verify: Column exists, accepts JSON text
- Verify: R0 loads spatial_context_json into P03EventState
- Verify: R2 EventAdapter can parse transition fields from JSON for spatial boundary detection

---

## MILESTONE 5: Cross-Episode Narrative Linking (P4)

> **Depends on**: Milestone 1 and 2 (temporal chain is correct, temporal_links available)
> **GAP-002 Reference**: Section 4.2 (narrative goal arcs), Section 6 Phase 5

### Epic 5.1: Cross-Episode Thread Matching

**Discovery**: GAP-002 Section 4.2
**Effort**: HIGH (5-7 days)
**Problem**: `narrative_thread_id` exists but R2 groups by 30-minute conversation proximity.
Episodes 1 and 4 of "Planning Mom's birthday party" are a week apart -- they will never
be in the same R2 episode. No cross-episode narrative linking exists.

#### Issues

---

##### Issue 5.1.1 -- Add narrative_thread_id and narrative_arc_position to st_epi

**Status**: TODO
**Priority**: P4

**Files Touched**:

| File | Lines | Action |
|------|-------|--------|
| k0/db/alembic/versions/008xx_st_epi_narrative_columns.py | NEW FILE | CREATE: Migration adding narrative columns to st_epi |
| k0/contracts/schemas/ | st_epi contract (if exists) | ADD: narrative_thread_id, narrative_thread_ids_json, narrative_arc_position |

**Upstream Data Source**:

- P03EventState.narrative_thread_id (loaded from st_hipp_events, populated by K1 MW via M13)
- P03EventState.narrative_arc_position (loaded from st_hipp_events, MW v2 signal)
- R2 EpisodeSplitter already has access to narrative_thread_id via EventAdapter (r2_episodic_integrator.py L187-190)
- Currently: narrative_thread_id exists on events but is NOT persisted at episode level in st_epi

**Current Schema** (st_epi -- 0027_st_epi.py, 37 columns total after 0061):

```
-- Episode identity:
episode_id (PK), tenant_id, space_id, version, supersedes_id, is_canonical
-- Content:
episode_summary, episode_type
-- Temporal:
start_time_utc, end_time_utc, duration_minutes, temporal_bucket, day_of_week, is_recurring, recurrence_pattern
-- Sources:
source_events_json, source_event_count
-- Location:
primary_location, location_type
-- Participants:
participants_json, participant_count
-- NO narrative_thread_id, NO narrative_arc_position
```

**What Needs To Be Done**:

1. Add `narrative_thread_id TEXT NULLABLE` -- the DOMINANT thread_id for this episode (majority vote from source events).
2. Add `narrative_thread_ids_json TEXT NULLABLE` -- JSON array of ALL distinct thread_ids from source events (for multi-thread episodes).
3. Add `narrative_arc_position TEXT NULLABLE` -- the DOMINANT arc position (majority vote: EXPOSITION/RISING_ACTION/CLIMAX/RESOLUTION).
4. Index on (tenant_id, narrative_thread_id) for cross-episode thread queries.

**How To Implement**:

```python
# k0/db/alembic/versions/0080_st_epi_narrative_columns.py

revision = "0080"
down_revision = "0079"

def upgrade():
    # Dominant narrative thread for this episode
    op.add_column(
        "st_epi",
        sa.Column("narrative_thread_id", sa.Text(), nullable=True,
                  comment="Dominant narrative thread_id from source events (majority vote)")
    )
    # All distinct thread_ids for multi-thread episodes
    op.add_column(
        "st_epi",
        sa.Column("narrative_thread_ids_json", sa.Text(), nullable=True,
                  comment="JSON array of all distinct narrative thread_ids from source events")
    )
    # Dominant arc position
    op.add_column(
        "st_epi",
        sa.Column("narrative_arc_position", sa.Text(), nullable=True,
                  comment="Dominant arc position: EXPOSITION/RISING_ACTION/CLIMAX/RESOLUTION")
    )
    # Index for cross-episode thread queries
    op.create_index(
        "ix_st_epi_narrative_thread",
        "st_epi",
        ["tenant_id", "narrative_thread_id"],
        postgresql_where=sa.text("narrative_thread_id IS NOT NULL")
    )

def downgrade():
    op.drop_index("ix_st_epi_narrative_thread")
    op.drop_column("st_epi", "narrative_arc_position")
    op.drop_column("st_epi", "narrative_thread_ids_json")
    op.drop_column("st_epi", "narrative_thread_id")
```

**Verification**:

- Run: migration against local postgres (`alembic upgrade head`)
- Verify: `\d st_epi` shows 3 new columns
- Verify: Index `ix_st_epi_narrative_thread` exists with partial WHERE clause
- Verify: Existing episodes have NULL for all 3 new columns (backward compatible)

---

##### Issue 5.1.2 -- R7 truth writer persists narrative columns to st_epi

**Status**: TODO
**Priority**: P4
**Depends on**: Issue 5.1.1 (columns exist on st_epi)

**Files Touched**:

| File | Lines | Action |
|------|-------|--------|
| k0/modules/consolidation/truth_writer/layers/episodic.py | L249-309 (_insert SQL) | ADD: narrative_thread_id, narrative_thread_ids_json, narrative_arc_position to INSERT |

**Upstream Data Source**:

- R2 produces episode clusters. Each cluster has N source events.
- Each source event (P03EventState) has `narrative_thread_id` and `narrative_arc_position`.
- R7 receives the episode object with aggregated source event data.

**Current Code** (episodic.py L249-309 -- INSERT into st_epi):

```sql
INSERT INTO st_epi (
    episode_id, tenant_id, space_id, cluster_id,
    source_events_json, source_event_count, start_time_utc, end_time_utc,
    duration_minutes, temporal_bucket, day_of_week, is_recurring, recurrence_pattern,
    confidence_score, observation_count,
    created_at, updated_at, valid_from, version,
    archival_status,
    source_texts_json, embedding_text, embedding_vector, embedding_model,
    episode_summary, episode_type, primary_location, location_type,
    participants_json, participant_count, embedding_id,
    cluster_confidence, consolidation_cycle_id, last_observed_at
) VALUES ($1, $2, $3, ..., $30)
-- NO narrative_thread_id, NO narrative_thread_ids_json, NO narrative_arc_position
```

**What Needs To Be Done**:

1. Before INSERT, compute narrative columns from source events:

   ```python
   # Collect thread_ids from source events
   thread_ids = [e.narrative_thread_id for e in source_events if e.narrative_thread_id]
   # Dominant = most common (majority vote)
   dominant_thread = Counter(thread_ids).most_common(1)[0][0] if thread_ids else None
   # All distinct
   all_threads = list(set(thread_ids)) if thread_ids else None
   # Arc positions
   arc_positions = [e.narrative_arc_position for e in source_events if e.narrative_arc_position]
   dominant_arc = Counter(arc_positions).most_common(1)[0][0] if arc_positions else None
   ```

2. Add 3 columns to INSERT statement and parameter list.
3. For UPDATE (REINFORCE action), merge thread_ids from new events with existing episode.

**How To Implement**:

```python
# In episodic.py _insert method -- compute narrative aggregation:
from collections import Counter
import json

thread_ids = [
    ev.narrative_thread_id
    for ev in source_events
    if ev.narrative_thread_id
]
dominant_thread_id = (
    Counter(thread_ids).most_common(1)[0][0] if thread_ids else None
)
all_thread_ids_json = (
    json.dumps(sorted(set(thread_ids))) if thread_ids else None
)
arc_positions = [
    ev.narrative_arc_position
    for ev in source_events
    if ev.narrative_arc_position
]
dominant_arc = (
    Counter(arc_positions).most_common(1)[0][0] if arc_positions else None
)

# Add to INSERT:
# ..., narrative_thread_id, narrative_thread_ids_json, narrative_arc_position
# VALUES (..., $31, $32, $33)
# Params: ..., dominant_thread_id, all_thread_ids_json, dominant_arc
```

```python
# For REINFORCE (update existing episode):
# Merge new thread_ids with existing:
existing_threads = json.loads(existing_episode.narrative_thread_ids_json or "[]")
new_threads = sorted(set(existing_threads + thread_ids))
# Re-compute dominant from merged list
```

**Verification**:

- Run: `pytest tests/k0/modules/consolidation/ -x`
- Verify: Episode with 3 events (all thread_id="planning_birthday") -> `narrative_thread_id = "planning_birthday"`
- Verify: Episode with mixed threads -> dominant is most common, all_threads has both
- Verify: Episode with no narrative events -> all 3 columns NULL
- Verify: REINFORCE merges new thread_ids with existing

**Data Persistence Path**:

```
P03EventState[0..N].narrative_thread_id
  -> R2 clusters events into episodes
    -> R7 _insert: majority_vote(thread_ids) -> narrative_thread_id
    -> R7 _insert: set(thread_ids) -> narrative_thread_ids_json
    -> R7 _insert: majority_vote(arc_positions) -> narrative_arc_position
      -> INSERT INTO st_epi (..., narrative_thread_id, ...) VALUES (..., 'planning_birthday', ...)
```

---

##### Issue 5.1.3 -- Cross-episode thread matching query in P03

**Status**: TODO
**Priority**: P4
**Depends on**: Issue 5.1.2 (narrative columns persisted to st_epi)

**Files Touched**:

| File | Lines | Action |
|------|-------|--------|
| k0/pipelines/p03/phases/r2_episodic_integrator.py | After episode formation | ADD: Cross-episode thread scan |

**Upstream Data Source**:

- st_epi.narrative_thread_id (from Issue 5.1.1)
- Current episode's dominant thread_id (computed during R2 clustering)
- Query window: last 30 days of episodes for same tenant_id

**What Needs To Be Done**:

1. After R2 creates episode clusters, for each new episode with a narrative_thread_id:
   a. Query st_epi for existing episodes with the same narrative_thread_id.
   b. If matches found, these are CONTINUATION episodes (same goal arc, different time windows).
   c. Record the continuation relationship.
2. The query is READ-ONLY during R2. The actual linking is written by R7.
3. Matches are stored in a new field on the episode object: `continuation_of_episode_id`.

**How To Implement**:

```python
# In R2 episodic integrator -- after clustering:
async def find_thread_continuations(
    conn, tenant_id: str, thread_id: str, exclude_episode_id: str
) -> list[dict]:
    """Find existing episodes with the same narrative thread."""
    if not thread_id:
        return []
    rows = await conn.fetch(
        """
        SELECT episode_id, narrative_arc_position, start_time_utc, end_time_utc,
               episode_summary
        FROM st_epi
        WHERE tenant_id = $1
          AND narrative_thread_id = $2
          AND episode_id != $3
          AND archival_status = 'ACTIVE'
        ORDER BY start_time_utc DESC
        LIMIT 10
        """,
        tenant_id, thread_id, exclude_episode_id
    )
    return [dict(r) for r in rows]
```

```python
# On the episode object (or P03 intermediate state):
continuation_of_episode_id: Optional[str] = None  # Most recent prior episode with same thread
thread_continuation_count: int = 0                  # How many prior episodes share this thread
```

**Verification**:

- Run: `pytest tests/k0/pipelines/p03/ -x`
- Verify: Episode with thread_id="planning_birthday" finds 2 prior episodes with same thread
- Verify: Episode with no thread_id returns empty continuation list
- Verify: Query excludes the current episode itself (no self-match)
- Verify: Query limited to ACTIVE episodes (not archived)
- Verify: Performance: indexed query, <5ms on partial index

---

##### Issue 5.1.4 -- Add continuation_of_episode_id to st_epi and persist

**Status**: TODO
**Priority**: P4
**Depends on**: Issue 5.1.3 (thread matching query exists)

**Files Touched**:

| File | Lines | Action |
|------|-------|--------|
| k0/db/alembic/versions/0080_st_epi_narrative_columns.py | Same migration | ADD: continuation_of_episode_id TEXT NULLABLE |
| k0/modules/consolidation/truth_writer/layers/episodic.py | _insert | ADD: continuation_of_episode_id to INSERT |

**Upstream Data Source**:

- R2 `find_thread_continuations()` result (Issue 5.1.3)
- Most recent prior episode_id with same narrative_thread_id

**How To Implement**:

```python
# In migration 0080 (bundled with narrative columns):
op.add_column(
    "st_epi",
    sa.Column("continuation_of_episode_id", sa.Text(), nullable=True,
              comment="Previous episode_id with same narrative_thread_id (continuation link)")
)
```

```python
# R7 _insert -- add to INSERT:
# ..., continuation_of_episode_id
# VALUES (..., $34)
# Param: continuation_of_episode_id (from R2 thread matching)
```

**Verification**:

- Run: `pytest tests/k0/modules/consolidation/ -x`
- Verify: New episode with thread continuation writes continuation_of_episode_id
- Verify: Episode without continuation writes NULL
- Verify: Can traverse continuation chain: episode_C -> episode_B -> episode_A

**Data Persistence Path**:

```
R2: find_thread_continuations("planning_birthday")
  -> [episode_B (Wed), episode_A (Mon)]
    -> continuation_of_episode_id = episode_B.episode_id (most recent)
      -> R7 INSERT INTO st_epi (..., continuation_of_episode_id) VALUES (..., 'epi_B_uuid')
```

---

### Epic 5.2: Goal Completion Detection

**Discovery**: GAP-002 Section 4.2
**Effort**: MEDIUM (3-5 days)

#### Issues

---

##### Issue 5.2.1 -- Detect narrative arc completion from thread history

**Status**: TODO
**Priority**: P4
**Depends on**: Issue 5.1.2 (narrative columns persisted to st_epi)

**Files Touched**:

| File | Lines | Action |
|------|-------|--------|
| k0/pipelines/p03/phases/r2_episodic_integrator.py | After thread matching | ADD: Arc completion detection logic |
| k0/pipelines/p03/event_state.py | Fields | ADD: `narrative_thread_completed: bool = False` |

**Upstream Data Source**:

- st_epi.narrative_arc_position across episodes with same thread_id (Issue 5.1.1)
- MW v2 signal: narrative_arc_position (EXPOSITION / RISING_ACTION / CLIMAX / RESOLUTION)
- MW v2 signal: narrative_is_goal_event (bool, from P03EventState)

**Problem**:

Goal arcs like "Planning Mom's birthday party" span multiple conversations:

```
Episode 1 (Mon): "Let's plan Mom's birthday" -> arc_position = EXPOSITION
Episode 2 (Wed): "Looking at venues" -> arc_position = RISING_ACTION
Episode 3 (Thu): "Finalized guest list" -> arc_position = RISING_ACTION
Episode 4 (Sat): "The party was amazing!" -> arc_position = CLIMAX or RESOLUTION
```

Currently, each episode's arc position is computed independently by MW. There is no
detection that the overall goal arc has reached completion.

**What Needs To Be Done**:

1. After R2 thread matching (Issue 5.1.3), if continuation episodes exist:
   a. Load `narrative_arc_position` history from prior episodes with same thread_id.
   b. Check if the current episode's dominant arc_position is CLIMAX or RESOLUTION.
   c. If yes AND prior episodes exist with EXPOSITION or RISING_ACTION, mark thread as completing.
2. Set `narrative_thread_completed = True` on the episode object.
3. Emit observability event: `narrative.thread.completed.v1` with thread_id and episode chain.

**How To Implement**:

```python
# In R2 -- after find_thread_continuations:
def detect_arc_completion(
    current_arc_position: str,
    prior_episodes: list[dict]
) -> bool:
    """Detect if this episode completes a narrative goal arc."""
    if not prior_episodes:
        return False
    if current_arc_position not in ("CLIMAX", "RESOLUTION"):
        return False
    # Check if any prior episode has EXPOSITION or RISING_ACTION
    prior_arcs = {ep.get("narrative_arc_position") for ep in prior_episodes}
    has_buildup = bool(prior_arcs & {"EXPOSITION", "RISING_ACTION"})
    return has_buildup
```

```python
# On P03EventState or episode intermediate state:
narrative_thread_completed: bool = False

# Emit observability:
if thread_completed:
    logger.info(
        "NARRATIVE_THREAD_COMPLETED",
        thread_id=thread_id,
        episode_count=len(prior_episodes) + 1,
        arc_sequence=[ep["narrative_arc_position"] for ep in prior_episodes] + [current_arc],
    )
```

**Verification**:

- Run: `pytest tests/k0/pipelines/p03/ -x`
- Verify: Thread with [EXPOSITION, RISING_ACTION, CLIMAX] -> completed = True
- Verify: Thread with [EXPOSITION, RISING_ACTION] only -> completed = False (no climax yet)
- Verify: Single episode with CLIMAX but no prior episodes -> completed = False (need buildup)
- Verify: Thread with [EXPOSITION, RESOLUTION] -> completed = True (skipped rising/climax)

**Data Persistence Path**:

```
R2: find_thread_continuations("planning_birthday")
  -> [episode_B (RISING_ACTION), episode_A (EXPOSITION)]
    -> current episode: CLIMAX
      -> detect_arc_completion: has_buildup = True -> completed = True
        -> R7: st_epi.narrative_thread_completed = True (if column exists)
        -> Observability: NARRATIVE_THREAD_COMPLETED event emitted
```

---

##### Issue 5.2.2 -- Persist thread completion state and add st_epi column

**Status**: TODO
**Priority**: P4
**Depends on**: Issue 5.2.1 (completion detection logic)

**Files Touched**:

| File | Lines | Action |
|------|-------|--------|
| k0/db/alembic/versions/0080_st_epi_narrative_columns.py | Same migration | ADD: narrative_thread_completed BOOLEAN DEFAULT FALSE |
| k0/modules/consolidation/truth_writer/layers/episodic.py | _insert | ADD: narrative_thread_completed to INSERT |

**Upstream Data Source**:

- R2 `detect_arc_completion()` output (Issue 5.2.1)
- Boolean: True if this episode completes a goal arc, False otherwise

**How To Implement**:

```python
# In migration 0080 (bundled with all narrative columns):
op.add_column(
    "st_epi",
    sa.Column("narrative_thread_completed", sa.Boolean(), nullable=False,
              server_default="false",
              comment="True if this episode completes a narrative goal arc (CLIMAX/RESOLUTION after buildup)")
)
```

```python
# R7 _insert -- add to INSERT:
# ..., narrative_thread_completed
# VALUES (..., $35)
# Param: narrative_thread_completed (bool, from R2 detection)
```

**Verification**:

- Run: migration against local postgres
- Verify: Column exists with DEFAULT false
- Verify: Existing episodes have `narrative_thread_completed = false`
- Verify: New completed episode writes `true`
- Verify: Query for completed threads: `SELECT * FROM st_epi WHERE narrative_thread_completed = true`

---

##### Issue 5.2.3 -- Observability event for goal completion

**Status**: TODO
**Priority**: P4
**Depends on**: Issue 5.2.1 (completion detection)

**Files Touched**:

| File | Lines | Action |
|------|-------|--------|
| k0/pipelines/p03/phases/r2_episodic_integrator.py | After completion detection | ADD: Emit structured observability event |
| k0/bus/ or k0/obs/ | Event definition | ADD: narrative.thread.completed.v1 event schema |

**Upstream Data Source**:

- R2 detect_arc_completion() returning True
- Thread metadata: thread_id, episode chain, arc positions, start/end times

**What Needs To Be Done**:

1. Define `narrative.thread.completed.v1` event schema.
2. When arc completion is detected, emit the event via K0 bus.
3. Event payload includes the full thread history for downstream consumers.
4. Consumers may include: K1 retrieval (for answering "what goals did we complete?"),
   future notification system, learning loop.

**How To Implement**:

```python
# Event schema:
{
    "topic": "narrative.thread.completed.v1",
    "payload": {
        "thread_id": "planning_birthday",
        "tenant_id": "family_abc",
        "completed_episode_id": "epi_4_uuid",
        "episode_chain": [
            {"episode_id": "epi_1_uuid", "arc_position": "EXPOSITION", "start_time_utc": 1700000000},
            {"episode_id": "epi_2_uuid", "arc_position": "RISING_ACTION", "start_time_utc": 1700200000},
            {"episode_id": "epi_3_uuid", "arc_position": "RISING_ACTION", "start_time_utc": 1700300000},
            {"episode_id": "epi_4_uuid", "arc_position": "CLIMAX", "start_time_utc": 1700500000}
        ],
        "total_episodes": 4,
        "span_days": 6,
        "completed_at_utc": 1700500000
    }
}
```

```python
# In R2 -- after detect_arc_completion returns True:
await bus.emit("narrative.thread.completed.v1", {
    "thread_id": thread_id,
    "tenant_id": tenant_id,
    "completed_episode_id": current_episode_id,
    "episode_chain": [
        {
            "episode_id": ep["episode_id"],
            "arc_position": ep["narrative_arc_position"],
            "start_time_utc": ep["start_time_utc"],
        }
        for ep in sorted(prior_episodes, key=lambda e: e["start_time_utc"])
    ] + [{
        "episode_id": current_episode_id,
        "arc_position": current_arc_position,
        "start_time_utc": current_start_time,
    }],
    "total_episodes": len(prior_episodes) + 1,
    "completed_at_utc": int(time.time()),
})
```

**Verification**:

- Run: `pytest tests/k0/pipelines/p03/ -x`
- Verify: Completion event emitted with correct schema
- Verify: Episode chain is chronologically ordered
- Verify: Event not emitted when arc is incomplete
- Verify: span_days correctly calculated from first to last episode

---

## Appendix A: Column Impact Summary

| New Column | Table | Type | Migration | Milestone |
|------------|-------|------|-----------|-----------|
| conversation_anchor_ms | st_hipp_events | BIGINT | 0075 | M1 |
| temporal_source | st_hipp_events | TEXT | 0075 | M1 |
| temporal_links_json | st_hipp_events | JSONB | 0076 | M2 |
| place_id | st_hipp_events | TEXT | 0077 | M3 |
| spatial_familiarity | st_hipp_events | TEXT | 0078 | M3 |
| extraction_sequence | st_hipp_events | INTEGER | 0079 | M4 |
| spatial_context_json | st_hipp_events | TEXT | 0079 | M4 |
| narrative_thread_id | st_epi | TEXT | 0080 | M5 |
| narrative_thread_ids_json | st_epi | TEXT | 0080 | M5 |
| narrative_arc_position | st_epi | TEXT | 0080 | M5 |
| continuation_of_episode_id | st_epi | TEXT | 0080 | M5 |
| narrative_thread_completed | st_epi | BOOLEAN | 0080 | M5 |

## Appendix B: Schema Changes Summary

| Field | Schema Version | Type | Location | Milestone |
|-------|---------------|------|----------|-----------|
| conversation_anchor_ms | 2.1 | integer | MemoryAtom | M1 |
| temporal_links | 2.1 | TemporalLink[] | MemoryAtom | M2 |
| place_id | 2.1 | string | MemoryAtom | M3 |
| extraction_sequence | 2.1 | integer | MemoryAtom | M4 |
| location_hierarchy | 2.1 | string[] | MemoryAtom | M4 |
| transition_from_place | 2.1 | string | MemoryAtom | M4 |
| transition_mode | 2.1 | string | MemoryAtom | M4 |
| narrative_thread_id | N/A | string | st_epi | M5 |
| narrative_thread_ids_json | N/A | string | st_epi | M5 |
| narrative_arc_position | N/A | string | st_epi | M5 |
| continuation_of_episode_id | N/A | string | st_epi | M5 |
| narrative_thread_completed | N/A | boolean | st_epi | M5 |

## Appendix C: Deprecated Fields

| Field | Replacement | When |
|-------|-------------|------|
| MemoryAtom.temporal (Optional[Temporal]) | temporal_links: List[TemporalLink] | M2 |
| MemoryAtom.temporal_orientation (atom-level) | Derived from dominant link_type in temporal_links | M2 |
| Temporal.is_backdated (bool) | TemporalLink.link_type (6-value enum) | M2 |

## Appendix D: Files Modified by Milestone

### Milestone 1 (Conversation Anchor Fix)

| File | Epics | Changes |
|------|-------|---------|
| k1/memory_writer/types.py | 1.1 | ExtractionContext.turn_timestamp_ms, MemoryAtom.conversation_anchor_ms |
| k1/memory_writer/events.py | 1.1 | TurnCompletePayload temporal/spatial fields |
| k1/contracts/schemas/memory_writer/memory_atom.v2.schema.json | 1.1 | conversation_anchor_ms property |
| k0/modules/context/temporal_profile.py | 1.2 | normalize_timestamp() split into Chain A + Chain B |
| k0/modules/context/hipp_events_row.py | 1.2 | conversation_anchor_ms, temporal_source writes |
| k0/contracts/schemas/st_hipp_events_v2.columns.yaml | 1.2 | conversation_anchor_ms, temporal_source columns |
| k0/pipelines/p03/phases/r0_batch_selector.py | 1.2 | Prefer conversation_anchor_ms in timestamp chain |
| k0/pipelines/p03/event_state.py | 1.2 | temporal_source field (verify exists) |
| k0/db/alembic/versions/0075_*.py | 1.2 | Migration: conversation_anchor_ms + temporal_source |

### Milestone 2 (Multi-Link Temporal)

| File | Epics | Changes |
|------|-------|---------|
| k1/memory_writer/types.py | 2.1 | TemporalLinkType enum, TemporalLink dataclass, MemoryAtom.temporal_links |
| k1/contracts/schemas/memory_writer/memory_atom.v2.schema.json | 2.2 | TemporalLink $def, temporal_links array |
| k1/memory_writer/ (persona prompt) | 2.3 | Multi-temporal extraction instructions |
| k1/memory_writer/invariants.py | 2.3 | temporal_links validation |
| k0/modules/context/temporal_profile.py | 2.4 | Parse temporal_links from v2.1 atoms |
| k0/modules/context/hipp_events_row.py | 2.4 | temporal_links_json write |
| k0/contracts/schemas/st_hipp_events_v2.columns.yaml | 2.4 | temporal_links_json column |
| k0/pipelines/p03/phases/r0_batch_selector.py | 2.4 | Load temporal_links_json |
| k0/pipelines/p03/event_state.py | 2.4 | temporal_links_json field |
| k0/db/alembic/versions/0076_*.py | 2.4 | Migration: temporal_links_json JSONB |

### Milestone 3 (Spatial Identity)

| File | Epics | Changes |
|------|-------|--------|
| k1/memory_writer/context/place_resolver.py | 3.1 | NEW FILE: PlaceResolver class (alias map, resolve, to_place_id) |
| k1/memory_writer/types.py | 3.1 | MemoryAtom.place_id: Optional[str] |
| k1/contracts/schemas/memory_writer/memory_atom.v2.schema.json | 3.1 | place_id property |
| k1/memory_writer/ (context assembly) | 3.1 | Build PlaceResolver in Stage 2, wire in Stage 4 |
| k0/contracts/schemas/st_hipp_events_v2.columns.yaml | 3.2 | place_id, spatial_familiarity columns |
| k0/db/alembic/versions/0077_*.py | 3.2 | Migration: place_id TEXT + partial index |
| k0/db/alembic/versions/0078_*.py | 3.3 | Migration: spatial_familiarity TEXT + CHECK |
| k0/modules/builders/hipp_events_row.py | 3.2 | map_spatial_group: place_id from envelope.body |
| k0/pipelines/p03/event_state.py | 3.2 | place_id: str = "" |
| k0/pipelines/p03/phases/r0_batch_selector.py | 3.2 | place_id in SELECT + mapping |
| k0/modules/context/spatial_minimal.py | 3.3 | compute_familiarity() from visit count |

### Milestone 4 (Per-Atom Signal Enrichment)

| File | Epics | Changes |
|------|-------|--------|
| k1/memory_writer/types.py | 4.1, 4.2, 4.3 | extraction_sequence, location_hierarchy, transition_from_place, transition_mode |
| k1/contracts/schemas/memory_writer/memory_atom.v2.schema.json | 4.1, 4.2, 4.3 | extraction_sequence, location_hierarchy, transition fields |
| k1/memory_writer/ (batch aggregation) | 4.1 | Assign extraction_sequence ordinals in Stage 5 |
| k1/memory_writer/ (persona prompt) | 4.2, 4.3 | Spatial hierarchy + transition extraction instructions |
| k0/db/alembic/versions/0079_*.py | 4.1, 4.3 | Migration: extraction_sequence INTEGER + spatial_context_json TEXT |
| k0/modules/builders/hipp_events_row.py | 4.1, 4.2, 4.3 | extraction_sequence, spatial_context_json mapping |
| k0/pipelines/p03/event_state.py | 4.1, 4.3 | extraction_sequence, spatial_context_json fields |
| k0/pipelines/p03/phases/r0_batch_selector.py | 4.1, 4.3 | extraction_sequence, spatial_context_json in SELECT |

### Milestone 5 (Cross-Episode Narrative Linking)

| File | Epics | Changes |
|------|-------|--------|
| k0/db/alembic/versions/0080_*.py | 5.1, 5.2 | Migration: narrative_thread_id, narrative_thread_ids_json, narrative_arc_position, continuation_of_episode_id, narrative_thread_completed on st_epi |
| k0/modules/consolidation/truth_writer/layers/episodic.py | 5.1, 5.2 | INSERT/UPDATE with narrative columns + completion state |
| k0/pipelines/p03/phases/r2_episodic_integrator.py | 5.1, 5.2 | find_thread_continuations() query, detect_arc_completion() |
| k0/pipelines/p03/event_state.py | 5.2 | narrative_thread_completed: bool = False |
| k0/bus/ or k0/obs/ | 5.2 | narrative.thread.completed.v1 event schema |

## Appendix E: ADR Requirements

| ADR | Title | Decision | Milestone |
|-----|-------|----------|-----------|
| ADR-K0XX | Conversation Anchor: Combined Option A+C | M08 refactor + K1 turn timestamp propagation | M1 |
| ADR-K0XX | MemoryAtom Schema v2.1 | Additive schema bump, backward compatible | M2 |
| ADR-K0XX | temporal_links JSONB Storage | JSONB column in st_hipp_events for multi-link temporal | M2 |
| ADR-K0XX | PlaceResolver Stable Identity | PlaceResolver follows PersonResolver pattern | M3 |
| ADR-K0XX | spatial_context_json Bundled Storage | Transitions + hierarchy in single JSONB column | M4 |
| ADR-K0XX | Cross-Episode Narrative Linking | Thread matching + continuation chain + arc completion | M5 |

## Appendix F: Risk Matrix

| Risk | Likelihood | Impact | Mitigation |
|------|-----------|--------|------------|
| M08 refactor breaks existing temporal resolution | Medium | High | Chain B preserves all existing behavior. Only Chain A changes routing. |
| Schema v2.1 breaks K0 Gate | Low | High | Additive changes only. v2.0 atoms valid under v2.1. Gate accepts both. |
| LLM hallucinated temporal_links | Medium | Medium | Extraction validator caps at 5 links. Confidence thresholding. |
| Backfill migration slow on large tables | Low | Medium | 78 rows currently. Will scale with data growth. Use batch updates. |
| PlaceResolver alias collisions | Medium | Low | Same approach as PersonResolver. Canonical name normalization. |
| Race condition fix changes Concierge behavior | Low | Medium | Additive fields on TurnCompletePayload. No Concierge logic change. |
| PlaceResolver fails on unknown locations | Low | Low | Returns None (graceful). M13 writes NULL. No data loss. |
| Familiarity query slow on large tables | Low | Low | Partial index on (tenant_id, place_id WHERE NOT NULL). |
| Cross-episode thread matching false positives | Medium | Medium | Thread IDs are MW-generated (LLM), may be inconsistent across sessions. Validate with embedding similarity. |
| Arc completion detection too aggressive | Low | Low | Requires both buildup (EXPOSITION/RISING) and climax. Conservative by design. |
| spatial_context_json schema drift | Low | Low | JSONB is schemaless. Contract enforces known keys. Unknown keys ignored. |

---

**End of Implementation Plan**

> All 5 milestones fully detailed with issue-level specifications.
> Priority: Milestone 1 (P0) should begin implementation immediately.
> Milestone 3 can run in parallel with Milestone 2 (no dependencies between temporal and spatial work).
