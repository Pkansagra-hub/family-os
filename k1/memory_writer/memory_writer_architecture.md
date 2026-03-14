# Memory Writer -- K1 Kernel Design Document

> **Status**: Design Discussion
> **Date**: 2026-02-06
> **Layer**: L4 Background Agent in K1 Cognitive Architecture Skeleton
> **Location**: `k1/memory_writer/`
> **Diagram**: `k1/memory_writer/memory_writer.mmd`
> **Skeleton Ref**: `architecture_diagrams/k1/k1_cognitive_architecture_skeleton.mmd` (subgraph `MEMORY_WRITER_SYSTEM`)
> **Related ADRs**: ADR-0017 (Single Writer), ADR-0005 (Agent Lifecycle)

---

## Table of Contents

1. [What is Memory Writer](#1-what-is-memory-writer)
2. [Where Memory Writer Sits in K1](#2-where-memory-writer-sits-in-k1)
3. [The Translation Problem](#3-the-translation-problem)
4. [Memory Writer Invariants (Non-Negotiable)](#4-memory-writer-invariants-non-negotiable)
5. [Pipeline Overview (5 Stages)](#5-pipeline-overview-5-stages)
6. [Stage 1: Relevance Filter (Rule-Based)](#6-stage-1-relevance-filter-rule-based)
7. [Stage 2: Context Assembly (SessionState Reader)](#7-stage-2-context-assembly-sessionstate-reader)
8. [Stage 3: LLM Memory Extraction](#8-stage-3-llm-memory-extraction)
9. [Stage 4: Envelope Builder (Deterministic)](#9-stage-4-envelope-builder-deterministic)
10. [Stage 5: Batch Aggregation and Bridge Submit](#10-stage-5-batch-aggregation-and-bridge-submit)
11. [K0 Envelope Body Contract](#11-k0-envelope-body-contract)
12. [Envelope Headers (Bridge-Injected)](#12-envelope-headers-bridge-injected)
13. [Extraction Output Schema (LLM -> Validator)](#13-extraction-output-schema-llm---validator)
14. [UltraBERT Role (K0 P02, NOT K1)](#14-ultrabert-role-k0-p02-not-k1)
15. [Bridge Command Path (Complete Data Flow)](#15-bridge-command-path-complete-data-flow)
16. [K0 Processing After Receipt](#16-k0-processing-after-receipt)
17. [Agent Contract (memory_writer.yaml)](#17-agent-contract-memory_writeryaml)
18. [LLM Prompt Design (memory_writer_persona.md)](#18-llm-prompt-design-memory_writer_personamd)
19. [Person Resolver](#19-person-resolver)
20. [Privacy Enforcer (Band-Based)](#20-privacy-enforcer-band-based)
21. [Eviction Writes (NOT Memory Writer)](#21-eviction-writes-not-memory-writer)
22. [Memory Writer vs Learning Extractor](#22-memory-writer-vs-learning-extractor)
23. [Trigger Mechanism (turn.complete.v1)](#23-trigger-mechanism-turncompletev1)
24. [Error Handling and Failure Modes](#24-error-handling-and-failure-modes)
25. [Observability and Metrics](#25-observability-and-metrics)
26. [Performance Budget](#26-performance-budget)
27. [Event Bus Integration](#27-event-bus-integration)
28. [Cross-Diagram Integration Points](#28-cross-diagram-integration-points)
29. [Dependency Graph and Build Order](#29-dependency-graph-and-build-order)
30. [Directory Structure (Target)](#30-directory-structure-target)
31. [Worked Examples (End-to-End)](#31-worked-examples-end-to-end)
32. [Open Design Questions](#32-open-design-questions)
33. [v2 Cross-Reference (stage5_proposal_corrections.md)](#33-v2-cross-reference-stage5_proposal_correctionsmd)
34. [Implementation Sync Addendum (GAP-002, 2026-03-05)](#34-implementation-sync-addendum-gap-002-2026-03-05)
35. [K1 Correction Signal Fields (R2 Epic 7.2)](#35-k1-correction-signal-fields-r2-epic-72)

---

## 1. What is Memory Writer

Memory Writer is K1's episodic memory formation system. It converts conversation turns into short, factual K0 command envelopes that flow through the Bridge Command Port to K0's P02 pipeline, where they are enriched and stored permanently in `st_hipp_events`.

**One-sentence definition**: Memory Writer observes every completed conversation turn, determines if it contains memorable facts, extracts 0-6 short factual statements via LLM (2000-token budget, 12 cognitive dimensions), builds K0-compatible 37-field command envelopes, and submits them through the Bridge for permanent storage.

**The core insight**: K1 thinks in conversations. K0 thinks in events. Memory Writer is the TRANSLATOR between these two cognitive models.

**What Memory Writer is NOT**:

- It is NOT the Learning Loop. Memory Writer extracts **facts** from every turn. Learning Loop extracts **meta-signals** (gaps, feedback, quality patterns) from specific trigger events.
- It is NOT a SessionState writer. Memory Writer NEVER writes to SessionState (ADR-0017, MW-01). The single writer is Concierge.
- It is NOT UltraBERT. UltraBERT runs in K0 P02 as a validation safety net AFTER Memory Writer has already produced its output. Memory Writer produces tags via LLM. UltraBERT validates them.
- It is NOT the Orchestrator. Memory Writer does not walk a DAG. It runs a simple linear 5-stage pipeline per turn.
- It is NOT user-facing. Memory Writer runs in background AFTER the turn is delivered. It has zero impact on TTFT or user-perceived latency.

**Why it exists**: Without Memory Writer, K0 would have no episodic memories from conversations. SessionState is ephemeral (single session). K0's `st_hipp_events` is permanent. Someone needs to move the important bits from the ephemeral conversation into the permanent store. That someone is Memory Writer.

---

## 2. Where Memory Writer Sits in K1

K1 is a layered cognitive kernel. Memory Writer is a background agent at L4, spawned by Fabric, triggered by turn completion events from Concierge.

```text

L0  External Interfaces (Web, Mobile, Voice) -- detached, TBD
L1  Concierge (FSM, UltraBERT, Single Writer) -- user-facing intelligence
L2  Orchestrator (Blind DAG Executor, NO LLM)
L2.5  Capability Fabric (Resolution + Retrieval + Execution)
L3  Planner (LLM-powered, 4-stage pipeline, read-only discovery tools)
L4  Spawned Sub-Agents (created by Fabric)
       |
       |-- MemoryWriterAgent            <-- THIS SYSTEM
       |-- LearningExtractorAgent       (separate, in learning.mmd)
       |-- invitation_sender, etc.      (task agents, in fabric.mmd)
L5  SessionState (12-section, Single Writer, Multi-Reader)
L6  Cross-Kernel Bridge (K0 communication gateway)

```

### Position in the Turn Lifecycle

```text

User says something
  -> L1 Concierge LISTENING -> ACKING -> DISPATCHING
       |
       |-- (task processing happens here, any tier)
       |
  -> L1 Concierge DELIVERING -> sends response to user
       |
       |-- Concierge emits turn.complete.v1 on DeltaBus
       |
       v
  -> L4 Memory Writer receives turn.complete.v1 (BACKGROUND)
       |
       |-- Stage 1: Filter (is this worth remembering?)
       |-- Stage 2: Read SessionState (context assembly)
       |-- Stage 3: LLM extraction (1-3 factual memories)
       |-- Stage 4: Build K0 envelopes (deterministic)
       |-- Stage 5: Batch submit to Bridge Command Port
       |
       v
  -> Bridge signs and POSTs to K0 -> K0 Gate -> WAL -> P02 -> st_hipp_events

```

Memory Writer runs AFTER the user has already received their response. It is invisible to the user.

### Skeleton Diagram Reference

In `k1_cognitive_architecture_skeleton.mmd`, Memory Writer is the subgraph `MEMORY_WRITER_SYSTEM` containing:

| Node | Maps To (in memory_writer.mmd) |
| --- | --- |
| `MEMORY_WRITER_AGENTS` | `WRITER_AGENT` (the LLM extraction agent) |
| `STATE_DELTA_EMITTER` | `BATCH_EMITTER` (flushes batch to Bridge) |
| `DELTA_AGGREGATOR` | `DELTA_AGG` (250ms time-window batching) |
| `DELTA_BUS` | `TURN_COMPLETE_EVENT` (turn.complete.v1 trigger) |

---

## 3. The Translation Problem

K1 and K0 have fundamentally different data models:

| Aspect | K1 (Conversation) | K0 (Events) |
| --- | --- | --- |
| **Data shape** | Turns (user said X, assistant said Y) | Envelopes (event with metadata tags) |
| **Lifespan** | Ephemeral (single session) | Permanent (st_hipp_events) |
| **Granularity** | Full conversation with chain of thought | Discrete factual statements (1-2 sentences) |
| **Tagging** | Not tagged (raw text) | Fully tagged (sentiment, emotion, participants, topics, etc.) |
| **Identification** | Natural names ("Mom", "Panda") | Resolved person_ids ("person_mom", "person_panda") |
| **Storage** | SessionState (in-memory, 96KB) | PostgreSQL tables (WAL + hipp_events) |
| **Access pattern** | Single writer, multi-reader | Command envelope via Bridge |

Memory Writer must bridge ALL of these gaps in a single pipeline:

1. **Identify** what is worth remembering in a turn (filter)
2. **Read** the conversation context from SessionState (context assembly)
3. **Extract** discrete factual statements from the conversation (LLM)
4. **Tag** each statement with the full K0 metadata schema (LLM + mapping)
5. **Resolve** natural names to person_ids (person resolver)
6. **Build** K0 command envelopes with correct body + headers (deterministic)
7. **Submit** through the Bridge Command Port (batch, fire-and-forget)

---

## 4. Memory Writer Invariants (Non-Negotiable)

These are hard constraints. Violation of any invariant is a bug.

| ID | Invariant | Enforcement Point |
| --- | --- | --- |
| MW-01 | Memory Writer NEVER writes to SessionState. Single writer = Concierge only (ADR-0017). | No IStateWritePort dependency. Multi-reader only. |
| MW-02 | Memory Writer reads SessionState lock-free (<1ms). Snapshot isolation per read. | SessionState multi-reader interface. |
| MW-03 | All K0 writes go through Bridge Command Port. K1 and K0 do NOT communicate directly. | IKernelCommandPort.submit() is the only output path. |
| MW-04 | Envelope body text MUST be <= 50 words (short factual statement). UltraBERT optimized for <=512 tokens. | Extraction Validator post-LLM check. Truncate if over. |
| MW-05 | Per turn: 0-6 memory extractions max. 0 = not worth remembering. 6 = rich multi-fact turn. | LLM prompt constraint + Validator cap. |
| MW-06 | LLM budget: 2000 tokens total (input context + output). Uses cheapest model (GPT-4o-mini or equivalent). | Agent contract llm_budget_tokens. Model Hub routing. |
| MW-07 | Relevance filter is rule-based (no LLM cost for skip decisions). | Filter Engine runs BEFORE any LLM call. |
| MW-08 | Batch window: 250ms aggregation before Bridge submit. | Delta Aggregator timer. |
| MW-09 | Offline-safe: queued in LocalOutbox when K0 unavailable. No data loss. | Bridge LocalOutbox + K0HealthChecker. |
| MW-10 | All envelopes carry cognitive_trace_id from the originating turn. | Envelope Builder injects from turn event payload. |
| MW-11 | UltraBERT in K0 P02 validates MW output (safety net, not primary). If LLM forgot a tag, UltraBERT catches it. | K0 P02 module M04 (affect analysis). |

---

## 5. Pipeline Overview (5 Stages)

Memory Writer runs a simple linear pipeline per turn. No DAG, no branching, no parallelism within a single turn.

```text

turn.complete.v1 (from DeltaBus)
  |
  v
[Stage 1] Relevance Filter (Rule-Based, <2ms)
  |  Is this turn worth remembering?
  |  Any skip rule matches? -> SKIP (no LLM cost)
  |  All rules pass? -> PASS to Stage 2
  |
  v
[Stage 2] Context Assembly (SessionState Read, <1ms)
  |  Read: 15 SessionState sections (13 read, 2 skipped: telemetry, artifacts_warm)
  |  10 hot sections + 3 warm sections via ISessionReadPort.snapshot()
  |  Build ExtractionContext (token-budgeted for 2000 token LLM window)
  |  Resolve natural names to person_ids
  |
  v
[Stage 3] LLM Memory Extraction (200-500ms)
  |  Writer Agent: "Extract 0-6 discrete factual memories"
  |  Budget: 2000 tokens total
  |  12 cognitive dimensions per atom (34 fields)
  |  Output: MemoryAtom[] (validated)
  |
  v
[Stage 4] Envelope Builder (Deterministic, <2ms)
  |  MemoryExtraction -> K0 CommandEnvelope body
  |  Pure field mapping + header injection
  |  Privacy enforcement (band-based field stripping)
  |
  v
[Stage 5] Batch Aggregation + Bridge Submit
  |  250ms batch window (Delta Aggregator)
  |  One Bridge call per batch (not per memory)
  |  IKernelCommandPort.submit() -> fire-and-forget
  |
  v
Bridge signs (Ed25519) -> POST /k0/command.submit -> K0 Gate -> WAL -> P02 -> st_hipp_events

```

### Stage Cost Summary

| Stage | Compute | LLM Cost | I/O | Total Budget |
| --- | --- | --- | --- | --- |
| 1. Relevance Filter | Rule evaluation | None | None | 2ms |
| 2. Context Assembly | Field reads | None | SessionState read | 1ms |
| 3. LLM Extraction | LLM inference | ~2000 tokens (cheapest model) | Model Hub call | 500ms |
| 4. Envelope Builder | Field mapping | None | None | 2ms |
| 5. Batch + Submit | Timer + HTTP | None | Bridge POST | 310ms |
| **TOTAL** | | | | **815ms P95** |

---

## 6. Stage 1: Relevance Filter (Rule-Based)

### Purpose: Context Assembly

Determine if a turn is worth remembering BEFORE spending LLM tokens. The filter is entirely rule-based -- zero LLM cost for skip decisions. This means if 40% of turns are trivial (greetings, confirmations, clarifications), we save 40% of Memory Writer LLM budget.

### Skip Rules

Every turn is checked against all 5 rules. If ANY rule matches, the turn is SKIPPED. Rules are evaluated in order (cheapest first).

```text

Rule evaluation order:
  R4 (Empty/Trivial)     -> cheapest: word count + regex
  R5 (Pure continuation)  -> pattern match against continuation phrases
  R1 (Clarification)      -> check both user + assistant for repair patterns
  R2 (System/Meta talk)   -> classify: about the system, not about life
  R3 (Recent duplicate)   -> most expensive: entity+topic hash lookup

```

### Rule R1: Pure Clarification

```text

Pattern: No new facts, just conversational repair.

Matches when:
  - User message is a clarification question ("What do you mean?", "Can you explain?",
    "I don't understand", "Which one?")
  - AND assistant response contains explanation/repair markers without new facts
  - AND no entities (PERSON, LOC, ORG, DATE) appear in the user message

Examples (SKIP):
  User: "What do you mean by that?"
  Assistant: "I meant that we should schedule the meeting for Tuesday."

  User: "Can you repeat that?"
  Assistant: "Sure, I said Mom's appointment is at 3pm."

Counter-example (PASS -- new fact in clarification):
  User: "You mean the dentist on Oak Street?"     <-- LOC entity = new fact
  Assistant: "Yes, Dr. Smith on Oak Street."       <-- PERSON + LOC entities

```

### Rule R2: System/Meta Talk

```text

Pattern: Conversation about the system itself, not about the user's life.

Matches when:
  - User message is about system behavior ("Be more concise", "Use formal tone",
    "Stop using emojis", "What can you do?")
  - AND no life-relevant entities appear

Examples (SKIP):
  User: "Change your tone to be more formal"
  User: "What features do you have?"
  User: "Stop asking so many questions"

Counter-example (PASS):
  User: "Can you help me schedule Mom's dentist appointment?"  <-- PERSON + TASK

```

### Rule R3: Recent Duplicate

```text

Pattern: Same entities + same topic within the last 5 minutes.

Implementation:
  - Hash: SHA256(sorted(participants) + sorted(topics))
  - Sliding window: last 5 minutes of processed turns
  - If hash exists in window: SKIP (duplicate)
  - If hash is new: PASS (add to window)

Purpose: Prevent storing "Had dinner with Mom" twice when the user
mentions it in turn 3 and references it again in turn 5.

Window storage: In-memory ring buffer (bounded, ~100 entries max).
Cleared on session end.

```

### Rule R4: Empty/Trivial

```text

Pattern: Too short to contain meaningful information.

Matches when:
  - User message has < 5 words
  - AND contains no named entities (PERSON, LOC, ORG, DATE, MONEY)
  - AND matches common trivial patterns:
    "ok", "sure", "thanks", "thank you", "got it", "yes", "no",
    "yeah", "alright", "cool", "nice", "fine", "good"

Examples (SKIP):
  User: "ok"
  User: "thanks"
  User: "sure, go ahead"

Counter-example (PASS -- entity in short message):
  User: "yes, Mom"          <-- PERSON entity
  User: "ok, Tuesday"       <-- DATE entity

```

### Rule R5: Pure Continuation

```text

Pattern: User is prompting the system to continue, no new information.

Matches when:
  - User message matches continuation patterns:
    "go on", "continue", "what else?", "tell me more", "and then?",
    "anything else?", "keep going", "next"
  - AND message has < 10 words
  - AND no entities present

Examples (SKIP):
  User: "go on"
  User: "what else?"
  User: "tell me more about that"

Counter-example (PASS):
  User: "tell me more about Mom's recipe"  <-- PERSON entity + topic

```

### Filter Decision Event

Every filter decision emits a lightweight event (no LLM cost):

```yaml

k1.mw.filter.decision.v1:
  turn_id: "uuid"
  session_id: "uuid"
  decision: "SKIP" | "PASS"
  skip_reason: "R1" | "R2" | "R3" | "R4" | "R5" | null
  rule_eval_time_ms: 0.8
  cognitive_trace_id: "uuid"

```

---

## 7. Stage 2: Context Assembly (SessionState Reader)

### Purpose: LLM Extraction

After the filter passes a turn, Memory Writer needs context to produce accurate extractions. This stage reads from SessionState (lock-free, multi-reader) and assembles a compact `ExtractionContext` for the LLM.

### What Memory Writer Reads

Memory Writer reads 13 of 15 SessionState sections (skipping telemetry and artifacts_warm).

**Hot sections** (10 -- always read):

| SessionState Section | What MW Takes | Why Needed | Size |
| --- | --- | --- | --- |
| `beliefs_active` | Current facts and entity list | Entity resolution, known person_ids | ~30-50 tokens |
| `beliefs_history` | Historical beliefs (evicted) | Context for known-fact dedup | ~20-30 tokens |
| `history_active` | Last 2-3 turns (compressed) | Contextual understanding for extraction | ~50-80 tokens |
| `history_recent` | Recent turn summaries | Broader conversation arc | ~20-30 tokens |
| `affective_now` | Current emotional state (VAD triple) | Sentiment/emotion tag accuracy | ~10-15 tokens |
| `affective_baseline` | User baseline affect | Novelty detection vs baseline | ~5-10 tokens |
| `narrative_active` | Active story arcs | Arc position tagging | ~15-20 tokens |
| `scoreboard` | Active referents, topics, salience | Topic tag accuracy | ~20-30 tokens |
| `control` | Intents, active tool calls | Intent classification | ~10-15 tokens |
| `persona` | User persona traits | Identity domain tagging | ~10-15 tokens |

**Warm sections** (3 -- read for enrichment):

| SessionState Section | What MW Takes | Why Needed | Size |
| --- | --- | --- | --- |
| `task_state` | Active task context | Activity type classification | ~10-20 tokens |
| `ifl` | Device/IFL sensor data | Location, device context | ~5-10 tokens |
| `meta` | session_id, user_id, band, device_id | Envelope header fields | ~10 tokens |

**Skipped sections** (2 -- not relevant for memory extraction):

| SessionState Section | Why Skipped |
| --- | --- |
| `telemetry` | System metrics, not relevant to episodic memory |
| `artifacts_warm` | Temporary artifacts, not memory-worthy |

**Total context from 13 sections**: ~215-345 tokens (well within the 2000 token budget for input + output).

### ExtractionContext Schema

```python

@dataclass
class ExtractionContext:
    """Assembled from SessionState, passed to LLM Writer Agent."""

    # From history_active (last 2-3 turns)
    recent_turns: list[CompressedTurn]   # [{role: "user", text: "..."}, ...]

    # From beliefs_active
    active_entities: list[Entity]         # [{name: "Mom", person_id: "person_mom", type: "PERSON"}, ...]
    known_facts: list[str]                # ["Mom prefers Italian food", ...] (top 5 by confidence)

    # From affective_now
    current_emotion: str                  # "joy", "neutral", "anxiety", etc.
    emotion_intensity: float              # 0.0-1.0

    # From scoreboard
    active_topics: list[str]              # ["family", "dining", ...] (current QUD topics)
    active_referents: list[str]           # ["Mom", "Olive Garden", ...] (in focus)

    # From meta
    privacy_band: str                     # "GREEN" | "AMBER" | "RED"
    actor_id: str                         # User ID (for envelope headers)
    space_id: str                         # Space ID (for envelope headers)
    device_id: str                        # Device ID (for envelope headers)
    session_id: str                       # Session ID

```

### CompressedTurn Schema

```python

@dataclass
class CompressedTurn:
    """Minimal turn representation for extraction context."""
    role: str           # "user" or "assistant"
    text: str           # Original message text (truncated to 100 words max)
    turn_number: int    # Ordinal within session
    timestamp_ms: int   # Epoch milliseconds

```

### SessionState Reader Implementation

```python

class MWSessionStateReader:
    """
    Lock-free multi-reader for Memory Writer.
    Uses snapshot isolation: reads a consistent view of all sections at once.
    """

    async def read_extraction_context(self, session_id: str) -> ExtractionContext:
        """
        Single atomic read of all needed sections.
        Returns ExtractionContext or raises ContextReadError.

        Performance: <1ms (in-memory, no I/O, no locks).

        Reads are safe because:
        - SessionState uses lock-free multi-reader (ADR-0017)
        - Snapshot isolation guarantees consistency within the read
        - Memory Writer never writes (MW-01)
        """
        snapshot = self.sessionstate.snapshot(
            sections=["beliefs_active", "beliefs_history", "history_active",
                      "history_recent", "affective_now", "affective_baseline",
                      "narrative_active", "scoreboard", "control", "persona",
                      "task_state", "ifl", "meta"]
        )
        return self._build_context(snapshot)

```

---

## 8. Stage 3: LLM Memory Extraction

### Purpose: Envelope Building

This is the only stage that uses an LLM. The Memory Writer Agent receives the ExtractionContext and produces 1-3 discrete factual `MemoryExtraction` objects.

### Writer Agent Characteristics

| Property | Value | Rationale |
| --- | --- | --- |
| Model | GPT-4o-mini (or cheapest available) | Memory extraction is simple; no need for expensive models |
| Token budget | 2000 total (input + output) | Context ~350 tokens + output ~500 tokens + headroom |
| Max tool calls | 6 | One tool call per extraction (max 6 per turn) |
| Max execution time | 5000ms | Hard timeout; abort if exceeded |
| Prompt template | `memory_writer_persona.md` | Stable persona with extraction instructions |
| Lifecycle | Spawned per session by Fabric | Reused across turns within the same session (IDLE pool) |

### LLM Token Budget Breakdown

```text

+----------------------------+--------+
| Component                  | Tokens |
+----------------------------+--------+
| System prompt (persona)    | ~150   |
| ExtractionContext (13 secs)| ~350   |
| Turn payload (user + asst) | ~200   |
| Output (0-6 atoms, 34fld)  | ~800   |
| Headroom                   | ~500   |
+----------------------------+--------+
| TOTAL                      | ~2000  |
+----------------------------+--------+

```

**12 cognitive dimensions** extracted per atom:
sentiment, affect (VAD triple), novelty, elaboration depth, temporal orientation,
source type, arc position, social intimacy, social context, identity domains,
activity type, and intent type.

### Extraction Validator (Post-LLM)

After the LLM produces raw extractions, the Extraction Validator applies deterministic checks:

```python

class ExtractionValidator:
    """
    Post-LLM validation. Deterministic, no LLM cost.
    Drops invalid extractions with logged reason.
    """

    def validate(self, extractions: list[RawExtraction], context: ExtractionContext) -> list[MemoryExtraction]:
        validated = []
        for ext in extractions:
            # Check 1: Text length
            if word_count(ext.text) > 50:
                ext.text = truncate_to_words(ext.text, 50)
                log.warn("MW: truncated extraction to 50 words", turn_id=ext.turn_id)

            # Check 2: Required fields
            if not ext.text or not ext.topics:
                log.warn("MW: dropped extraction, missing text or topics", turn_id=ext.turn_id)
                continue

            # Check 3: Participant resolution
            ext.participants = self.person_resolver.resolve_all(ext.participants, context)

            # Check 4: Confidence threshold
            if ext.confidence < 0.3:
                log.info("MW: dropped low-confidence extraction", confidence=ext.confidence)
                continue

            # Check 5: Privacy band
            if context.privacy_band == "RED":
                ext.location_name = None  # Strip location in RED band
                ext.participants = mask_participants(ext.participants)

            validated.append(ext)

        # Cap at 6 extractions max (MW-05)
        return validated[:6]

```

---

## 9. Stage 4: Envelope Builder (Deterministic)

### Purpose: Batch Submit

Convert validated `MemoryExtraction` objects into K0-compatible `CommandEnvelope` bodies. This stage is entirely deterministic -- no LLM, no UltraBERT, no external calls. Pure field mapping and header injection.

### Field Mapping Table

| Source (MemoryExtraction) | Target (K0 Envelope Body) | Transformation |
| --- | --- | --- |
| `extraction.text` | `body.text` | Direct copy (already validated <= 50 words) |
| `"UPSERT"` (constant) | `body.operation` | Always UPSERT for new memories |
| `extraction.participants` | `body.participants` | Already resolved to person_ids |
| `extraction.location_name` | `body.location_name` | Direct copy (null if absent or RED band) |
| `extraction.activity_type` | `body.activity_type` | Direct copy (null if absent) |
| `extraction.topics` | `body.topics` | Direct copy (1-3 topics) |
| `extraction.sentiment_label` | `body.sentiment_label` | Direct copy (5-class) |
| `extraction.emotion_tags` | `body.emotion_tags` | Direct copy (from 44-class) |
| `extraction.categories` | `body.categories` | Direct copy |
| `ctx.turn_timestamp_ms` | `body.event_time_utc` | K1 Concierge turn timestamp (unix ms). Fallback: `now_utc()` if 0. GAP-002 Epic 1.1 |
| `ctx.turn_timestamp_ms` | `body.conversation_anchor_ms` | Gold-standard conversation anchor. NEVER overwritten by K0 M08. GAP-002 Epic 1.1 |
| `context.session_id` | `body.session_id` | From ExtractionContext |
| Turn ordinal | `body.conversation_turn` | From turn event payload |
| `"en"` (constant) | `body.language` | Default; future: detect from SessionState |

### Header Injection Table

| Source | Target (Envelope Header) | Notes |
| --- | --- | --- |
| Turn event | `cognitive_trace_id` | Unifies causality across the entire request |
| SessionState.meta | `tenant_id` | Multi-tenant identifier |
| SessionState.meta | `space_id` | Space/family identifier |
| Constant | `topic` | Always `"memory.delta"` |
| Constant | `schema_uri` | Always `"schema://memory.delta"` |
| Constant | `schema_version` | `"1.0"` |
| SessionState.meta | `actor` | User ID |
| SessionState.meta | `device_id` | Device that submitted the turn |
| SessionState.meta | `band` | Privacy band (GREEN/AMBER/RED) |

**Critical note**: The following headers are NOT set by Memory Writer. They are added by the Bridge CommandBuilder:

- `sig_alg` (Ed25519SHA512)
- `sig_kid` (device key ID)
- `envelope_sha256` (content hash)
- `sig` (cryptographic signature)
- `idem_key` (idempotency key derived from payload hash)

K1 NEVER handles cryptographic signing. That is the Bridge's job.

---

## 10. Stage 5: Batch Aggregation and Bridge Submit

### Purpose: Person Resolution

Collect all envelopes from a turn (1-3) into a single batch, then submit to the Bridge in one HTTP call. The 250ms batch window also catches stragglers from overlapping processing.

### Delta Aggregator

```python

class DeltaAggregator:
    """
    Time-window batching for K0 command envelopes.
    Collects envelopes, deduplicates, merges compatible operations.
    """

    BATCH_WINDOW_MS = 250  # MW-08

    def __init__(self):
        self.pending: list[CommandEnvelope] = []
        self.seen_hashes: set[str] = set()  # entity+topic dedup within window

    def add(self, envelope: CommandEnvelope) -> None:
        """Add envelope to current batch. Dedup by entity+topic hash."""
        hash_key = self._compute_hash(envelope)
        if hash_key in self.seen_hashes:
            log.info("MW: dedup within batch window", hash=hash_key)
            return
        self.seen_hashes.add(hash_key)
        self.pending.append(envelope)

    async def flush(self) -> list[CommandEnvelope]:
        """
        Called after 250ms window expires.
        Returns all pending envelopes in causal order.
        Clears the batch.
        """
        batch = sorted(self.pending, key=lambda e: e.headers.turn_sequence)
        self.pending = []
        self.seen_hashes = set()
        return batch

    def _compute_hash(self, envelope: CommandEnvelope) -> str:
        """Dedup key: sorted participants + sorted topics."""
        parts = sorted(envelope.body.get("participants", []))
        topics = sorted(envelope.body.get("topics", []))
        return hashlib.sha256(f"{parts}:{topics}".encode()).hexdigest()[:16]

```

### Batch Emitter (State Delta Emitter)

```python

class BatchEmitter:
    """
    Flushes batched envelopes to Bridge Command Port.
    One HTTP call per batch (not per envelope).
    """

    def __init__(self, cmd_port: IKernelCommandPort):
        self.cmd_port = cmd_port

    async def emit(self, batch: list[CommandEnvelope]) -> None:
        """
        Submit all envelopes in the batch via Bridge.
        Fire-and-forget: does not wait for K0 response.
        If Bridge detects K0 offline: envelopes queued in LocalOutbox.
        """
        if not batch:
            return

        for envelope in batch:
            await self.cmd_port.submit(
                topic="memory.delta",
                schema_uri="schema://memory.delta",
                body=envelope.body,
                headers=envelope.headers
            )
            # NOTE: submit() is fire-and-forget (MW-03)
            # Bridge handles signing, idem_key, sha256, offline queuing

        emit_metric("k1.mw.bridge.submit_count", len(batch))
        emit_metric("k1.mw.bridge.batch_size", len(batch))

```

### Why 250ms Batch Window?

| Consideration | Impact |
| --- | --- |
| LLM extraction takes 200-500ms | Most extractions complete within one window |
| Bridge HTTP overhead | One POST vs 3 POSTs saves ~40ms in overhead |
| K0 Gate throughput | K0 prefers batch-sized work from the outbox |
| User-visible latency | None (background process, MW-08) |
| Data freshness | 250ms delay is imperceptible for episodic memory |

---

## 11. K0 Envelope Body Contract

This is the exact JSON body that Memory Writer v2 sends to K0. It must conform to the 37-field MemoryAtom v2.2 schema defined in `k1/contracts/schemas/memory_writer/memory_atom.v2.schema.json`.

```json

{
  "text": "Had dinner with Mom at Olive Garden for Emma's birthday",
  "topics": ["family", "dining", "celebration"],
  "sentiment_label": "positive",
  "affect": {
    "valence": 0.8,
    "arousal": 0.5,
    "dominance": 0.6
  },
  "source_type": "user_stated",
  "novelty": "NOVEL",
  "elaboration_depth": "DISCUSSED",
  "temporal_orientation": "PAST",
  "confidence": 0.95,
  "session_id": "session-abc123",
  "conversation_turn": 5,
  "language": "en",
  "person_id": "person_user_001",
  "event_time_utc": "2026-02-06T19:00:00Z",
  "participants": ["person_mom", "person_emma"],
  "participant_relationships": [
    {"type": "PARENT_OF", "target": "person_emma", "confidence": 0.9}
  ],
  "location_name": "Olive Garden",
  "location_type": "restaurant",
  "activity_type": "MEAL",
  "emotion_tags": ["joy", "contentment"],
  "categories": ["social", "meal"],
  "narrative": {
    "arc_label": "family_celebrations",
    "arc_position": "RISING_ACTION",
    "arc_salience": 0.7
  },
  "temporal": {
    "day_of_week": "Thursday",
    "time_of_day": "evening",
    "is_recurring": false
  },
  "social_context": "nuclear_family",
  "social_intimacy": "HIGH",
  "intent_type": "log_memory",
  "identity_domains": ["parent", "social_self"],
  "cognitive_trace_id": "trace-uuid-abc",
  "embedding_text": null,
  "operation": "UPSERT"
}

```

### Field Reference (34 fields -- v2 MemoryAtom)

| # | Field | Type | Required | Constraints | Source |
| --- | --- | --- | --- | --- | --- |
| 1 | `text` | string | YES | 1-50 words, factual statement | LLM extraction |
| 2 | `topics` | string[] | YES | 1-5 topic tags | LLM extraction |
| 3 | `sentiment_label` | enum | YES | 5-class: very_negative..very_positive | LLM extraction |
| 4 | `affect` | object | YES | {valence: -1..1, arousal: 0..1, dominance: 0..1} | LLM from affective_now |
| 5 | `source_type` | enum | YES | user_stated, user_implied, device_observed, system_inferred | LLM + context |
| 6 | `novelty` | enum | YES | ROUTINE, EXPECTED, NOVEL, SURPRISING | LLM vs beliefs |
| 7 | `elaboration_depth` | enum | YES | MENTION, DISCUSSED, ELABORATED, DEEPLY_PROCESSED | LLM + turn count |
| 8 | `temporal_orientation` | enum | YES | PAST, ONGOING, FUTURE_COMMITMENT | LLM extraction |
| 9 | `confidence` | float | YES | 0.0-1.0, floor 0.30 | Agent self-score |
| 10 | `session_id` | string | YES | Originating session | Context.session_id |
| 11 | `conversation_turn` | int | YES | Turn ordinal (>=1) | Turn event payload |
| 12 | `language` | string | YES | ISO 639-1 code | Default "en" |
| 13 | `person_id` | string | YES | Pattern: ^person_[a-z0-9_]+$ | Person Resolver |
| 14 | `event_time_utc` | string | YES | ISO 8601 UTC | now_utc() or resolved |
| 15 | `participants` | string[] | NO | person_ids, max 10 | LLM + Person Resolver |
| 16 | `participant_relationships` | object[] | NO | {type, target, confidence} | LLM + context |
| 17 | `location_name` | string | NO | Place name (stripped in RED band) | LLM extraction |
| 18 | `location_type` | enum | NO | 12 values: home, restaurant, hospital, etc. | LLM extraction |
| 19 | `activity_type` | enum | NO | 20 values: MEAL, TASK, TRAVEL, etc. | LLM extraction |
| 20 | `emotion_tags` | string[] | NO | From 44-class emotion set | LLM extraction |
| 21 | `categories` | string[] | NO | Activity categories | LLM extraction |
| 22 | `narrative` | object | NO | {arc_label, arc_position, arc_salience} | From narrative_active |
| 23 | `temporal` | object | NO | {day_of_week, time_of_day, is_recurring} | LLM + temporal analysis |
| 24 | `social_context` | enum | NO | solo, friends, colleagues, nuclear_family, etc. | LLM + relationships |
| 25 | `social_intimacy` | enum | NO | LOW, MEDIUM, HIGH | Derived from relationships |
| 26 | `intent_type` | enum | NO | 8 values: log_memory, query_memory, etc. | From control.intents |
| 27 | `identity_domains` | string[] | NO | 9 domains: parent, spouse, professional, etc. | LLM + persona |
| 28 | `cognitive_trace_id` | string | NO | UUID from originating turn | MW-10 enforcement |
| 29 | `embedding_text` | string | NO | Null in v2 (K0 computes embeddings) | Always null |
| 30 | `operation` | string | NO | Default "UPSERT" | Constant |

### Constraints Summary (v2)

- `text` is the PRIMARY field. All other fields are cognitive dimensions or metadata.
- `text` must be self-contained (readable without context) and max 50 words (MW-04).
- `participants` must use resolved `person_*` IDs, not natural names.
- `topics` must be 1-5 items.
- `sentiment_label` is 5-class (not binary, not 3-class).
- `affect` triple is ALWAYS required -- sourced from affective_now VAD dimensions.
- 12 cognitive dimensions provide rich metadata for K0 P02 enrichment and P03 consolidation.
- `embedding_text` is always null -- K0 P02 computes embeddings, not K1.
- Authoritative schema: `k1/contracts/schemas/memory_writer/memory_atom.v2.schema.json`

---

## 12. Envelope Headers (Bridge-Injected)

Headers are NOT part of the body. They wrap the body in the command envelope. Some are set by Memory Writer, others by the Bridge CommandBuilder.

### Headers Set by Memory Writer

| Header | Value | Source |
| --- | --- | --- |
| `cognitive_trace_id` | UUID | From turn.complete.v1 event payload |
| `tenant_id` | string | From SessionState.meta |
| `space_id` | string | From SessionState.meta |
| `topic` | `"memory.delta"` | Constant (Memory Writer's topic) |
| `schema_uri` | `"schema://memory.delta"` | Constant |
| `schema_version` | `"1.0"` | Constant |
| `actor` | string | From SessionState.meta.user_id |
| `device_id` | string | From SessionState.meta.device_id |
| `band` | `"GREEN"` / `"AMBER"` / `"RED"` | From SessionState.meta.privacy_band |

### Headers Set by Bridge CommandBuilder

These are NEVER set by K1 code. The Bridge handles all cryptographic operations:

| Header | Value | How Computed |
| --- | --- | --- |
| `sig_alg` | `"Ed25519SHA512"` | Constant (Bridge signing algorithm) |
| `sig_kid` | string | Device key ID from Bridge key store |
| `envelope_sha256` | hex string | SHA-256 of canonical JSON body |
| `sig` | hex string | Ed25519 signature of the envelope |
| `idem_key` | hex string | Derived from payload hash (idempotency) |

This separation ensures K1 code never touches private keys, signing algorithms, or cryptographic operations.

---

## 13. Extraction Output Schema (LLM -> Validator)

The LLM produces structured output matching the 37-field MemoryAtom v2.2 schema. The Extraction Validator then validates and cleans it. The authoritative schema is `k1/contracts/schemas/memory_writer/memory_atom.v2.schema.json` and the Python types are in `k1/memory_writer/types.py`.

### MemoryAtom v2 Schema (34 fields, 12 cognitive dimensions)

```yaml

MemoryAtom:
  # --- Required fields (14) ---
  text:
    type: string
    required: true
    description: "Short factual statement (1-2 sentences, <=50 words)"
    constraints:
      - Must be self-contained (readable without conversation context)
      - Must be factual (no opinions, no speculation, no chain-of-thought)
      - Must be in past tense or present tense (not future-conditional)

  topics:
    type: array[string]
    required: true
    description: "1-5 topic tags describing the memory's domain"

  sentiment_label:
    type: string
    required: true
    enum: ["very_negative", "negative", "neutral", "positive", "very_positive"]

  affect:
    type: object {valence: float, arousal: float, dominance: float}
    required: true
    description: "VAD triple from affective_now dimensions"

  source_type:
    type: string
    required: true
    enum: ["user_stated", "user_implied", "device_observed", "system_inferred"]

  novelty:
    type: string
    required: true
    enum: ["ROUTINE", "EXPECTED", "NOVEL", "SURPRISING"]

  elaboration_depth:
    type: string
    required: true
    enum: ["MENTION", "DISCUSSED", "ELABORATED", "DEEPLY_PROCESSED"]

  temporal_orientation:
    type: string
    required: true
    enum: ["PAST", "ONGOING", "FUTURE_COMMITMENT"]

  confidence:
    type: float
    required: true
    description: "Agent self-score (0.0-1.0). Floor: 0.30."

  session_id:
    type: string
    required: true

  conversation_turn:
    type: integer
    required: true
    minimum: 1

  language:
    type: string
    required: true
    description: "ISO 639-1 code"

  person_id:
    type: string
    required: true
    pattern: "^person_[a-z0-9_]+$"

  event_time_utc:
    type: string (ISO 8601)
    required: true

  # --- Optional fields (16) ---
  participants:
    type: array[string]
    description: "Person IDs (resolved by Person Resolver)"

  participant_relationships:
    type: array[{type, target, confidence}]
    description: "Typed relationships between participants"

  location_name:
    type: string | null
    description: "Place name (stripped in RED band)"

  location_type:
    type: string | null
    enum: ["home", "restaurant", "hospital", "school", "office", "gym",
           "store", "park", "church", "airport", "hotel", "other"]

  activity_type:
    type: string | null
    enum: 20 values (MEAL, TASK, TRAVEL, HEALTH, SOCIAL, WORK, etc.)

  emotion_tags:
    type: array[string]
    description: "From 44-class emotion set (matches UltraBERT)"

  categories:
    type: array[string]
    description: "Activity categories"

  narrative:
    type: object {arc_label, arc_position, arc_salience}
    description: "Story arc context from narrative_active"

  temporal:
    type: object {day_of_week, time_of_day, is_recurring}
    description: "Temporal patterns"

  social_context:
    type: string
    enum: ["solo", "friends", "colleagues", "nuclear_family", "extended_family", "community"]

  social_intimacy:
    type: string
    enum: ["LOW", "MEDIUM", "HIGH"]

  intent_type:
    type: string
    enum: ["log_memory", "query_memory", "set_reminder", "express_feeling",
           "seek_advice", "share_news", "reflect", "other"]

  identity_domains:
    type: array[string]
    description: "9 identity domains activated by this memory"

  cognitive_trace_id:
    type: string
    description: "UUID from originating turn (MW-10)"

  embedding_text:
    type: string | null
    description: "Always null in v2 (K0 computes embeddings)"

  operation:
    type: string
    description: "Default UPSERT"

```

### Multi-Extraction Example (v2 format)

A single turn can produce 0-6 extractions. Each extraction is a full 34-field MemoryAtom:

```text

User: "Had dinner with Mom at Olive Garden yesterday, and she mentioned she
       needs to see Dr. Smith about her knee next week"

Extraction 1 (MemoryAtom):
  text: "Had dinner with Mom at Olive Garden"
  participants: ["person_mom"]
  location_name: "Olive Garden"
  location_type: "restaurant"
  activity_type: "MEAL"
  topics: ["family", "dining"]
  sentiment_label: "positive"
  affect: {valence: 0.7, arousal: 0.4, dominance: 0.6}
  source_type: "user_stated"
  novelty: "NOVEL"
  elaboration_depth: "MENTION"
  temporal_orientation: "PAST"
  emotion_tags: ["contentment"]
  categories: ["social", "meal"]
  confidence: 0.95
  social_context: "nuclear_family"
  social_intimacy: "HIGH"

Extraction 2 (MemoryAtom):
  text: "Mom needs to see Dr. Smith about her knee next week"
  participants: ["person_mom"]
  location_name: null
  activity_type: "HEALTH"
  topics: ["health", "family"]
  sentiment_label: "neutral"
  affect: {valence: -0.2, arousal: 0.3, dominance: 0.4}
  source_type: "user_stated"
  novelty: "NOVEL"
  elaboration_depth: "MENTION"
  temporal_orientation: "FUTURE_COMMITMENT"
  emotion_tags: ["concern"]
  categories: ["health", "appointment"]
  confidence: 0.88
  intent_type: "log_memory"

```

---

## 14. UltraBERT Role (K0 P02, NOT K1)

UltraBERT does NOT run in K1. It runs exclusively in K0's P02 pipeline AFTER receiving the Memory Writer's envelope. Memory Writer's LLM is the primary tagger. UltraBERT is the validation safety net.

### Architecture Boundary

```text

K1 (Memory Writer LLM):
  Produces: text, sentiment_label, emotion_tags, participants, topics,
            activity_type, location_name, categories
  Via: GPT-4o-mini (cheapest model, 500 token budget)
  Quality: Good but not perfect. LLMs occasionally miss tags or hallucinate.

          ---- BRIDGE BOUNDARY (Ed25519 signed envelope) ----

K0 (P02 Pipeline, Module M04: Affect Analysis):
  Receives: MW envelope body
  Runs: UltraBERT (familyos-ultrabert v4.0.1, max_length=512 tokens)
  Role: VALIDATION safety net
  On MW body text (~15-30 tokens): well within UltraBERT sweet spot

```

### UltraBERT Validation Matrix

| Field | LLM Writer Produces | UltraBERT Validates | If Mismatch |
| --- | --- | --- | --- |
| `sentiment_label` | `"positive"` | Sentiment head confirms or corrects | UltraBERT value wins |
| `emotion_tags` | `["joy"]` | Emotions 44-class enriches (may add missing) | Union of both |
| `participants` | `["person_mom", "person_emma"]` | ner_family KINSHIP check | Flag unresolved |
| `topics` | `["family", "dining"]` | Ingress head validates topic relevance | UltraBERT may adjust |
| `activity_type` | `"MEAL"` | Intent head confirms | UltraBERT value wins |
| `location_name` | `"Olive Garden"` | ner_general LOC extraction | Confirm or extract |
| `safety` | (inferred from band) | safety_familyos head validates | Block if unsafe |

### UltraBERT Model Details

- Package: `familyos-ultrabert` v4.0.1
- Installed: editable from `D:\Modeling_studio\familyos_ultrabert`
- Backends: ONNX (`onnx_inference.py`) and PyTorch (`pytorch_inference.py`)
- Max length: 512 tokens in both backends
- Embedding dim: 768
- Heads: sentiment (5-class), emotions (44-class), safety_familyos, ner_family (KINSHIP), ner_general, ingress, intent, and more (12 capabilities total)

### Why UltraBERT is Safety Net (Not Primary)

1. **LLM is better at context**: Memory Writer LLM sees the full conversation context (history, beliefs, scoreboard). UltraBERT sees only the extracted text body (~15-30 tokens without context).
2. **LLM handles ambiguity**: "Panda" in a family context = person_panda. UltraBERT might classify it as ANIMAL without conversation context.
3. **UltraBERT fills gaps**: If LLM forgot an emotion tag, UltraBERT's 44-class head catches it.
4. **UltraBERT catches hallucination**: If LLM tags sentiment as "positive" but the text says "hospital emergency", UltraBERT corrects it.
5. **Defense in depth**: Two independent classifiers (LLM + UltraBERT) are more reliable than either alone.

---

## 15. Bridge Command Path (Complete Data Flow)

This is the complete path from Memory Writer's `BATCH_EMITTER` to K0's `st_hipp_events`. Every hop is documented.

```text

K1: Memory Writer
  |
  |  BatchEmitter flushes N envelopes (N = 1-6)
  |  For each envelope:
  |    IKernelCommandPort.submit(topic="memory.delta", schema_uri="schema://memory.delta", body={...})
  |
  v
Bridge: IKernelCommandPort (adapter)
  |
  |  [1] Receive raw body + headers from K1
  |  [2] Check K0 health (K0HealthChecker)
  |        ONLINE -> proceed to CommandBuilder
  |        OFFLINE -> enqueue in LocalOutbox (SQLite), return immediately
  |
  v
Bridge: CommandBuilder
  |
  |  [3] Canonicalize envelope JSON (deterministic serialization)
  |  [4] Compute envelope_sha256 = SHA-256(canonical_json)
  |  [5] Compute idem_key = derive(envelope_sha256)  [idempotency]
  |  [6] Sign with device key:
  |        sig = Ed25519.sign(private_key, canonical_json)
  |        sig_kid = device_key_id
  |        sig_alg = "Ed25519SHA512"
  |  [7] Build complete envelope with all headers
  |
  v
Bridge: HTTP Transport
  |
  |  [8] POST /k0/command.submit
  |      Body: signed envelope (JSON)
  |      Headers: Content-Type: application/json
  |
  v
K0: Gate (PEP + Signature Verification)
  |
  |  [9] PEP validation (policy engine point)
  |  [10] Ed25519 signature verification
  |  [11] Policy enforcement (band obligations)
  |  [12] Schema validation against schema://memory.delta
  |  Result: ALLOW or DENY
  |    DENY -> 403, logged, never reaches WAL
  |    ALLOW -> proceed to hot path
  |
  v
K0: Hot Path (93ms P95)
  |
  |  [13] Begin atomic transaction
  |  [14] Write to st_wal (primary durable store)
  |  [15] Write to idem_ledger (idempotency guard)
  |  [16] Write to st_outbox (P02 work queue)
  |  [17] Write to st_receipts (audit trail)
  |  [18] Commit transaction
  |  [19] Return 202 Accepted + receipt_id
  |
  v
K0: P02 Background Pipeline (50-100ms)
  |
  |  [20] Dequeue from st_outbox
  |  [21] Read envelope from st_wal via wal_pos
  |  [22] Run module DAG (18 stages):
  |         M01: DG pattern separation (fingerprints)
  |         M02: Semantic projection (entities, KG triples)
  |         M04: Affect analysis (UltraBERT safety net) <-- validates MW output
  |         M06: Salience scoring
  |         M07: Social graph resolve (st_relationships)
  |         M08: Temporal profiling
  |         M16: Atomic writer
  |  [23] Write enriched event to st_hipp_events (permanent memory)
  |  [24] Emit cognitive.memory.write.completed.v1
  |
  v
K0: st_hipp_events (PERMANENT EPISODIC MEMORY)

```

### Offline Path

When K0 is unavailable:

```text

K1: BatchEmitter -> Bridge: IKernelCommandPort.submit()
  |
  v
Bridge: K0HealthChecker returns OFFLINE
  |
  v
Bridge: LocalOutbox (K1 SQLite)
  |  Enqueue envelope with priority=NORMAL
  |  No data loss (MW-09)
  |
  |  ... K0 comes back online ...
  |
  v
Bridge: LocalOutbox Drain
  |  FIFO order
  |  Resume at CommandBuilder step [3]
  |
  v
(Normal path continues from CommandBuilder -> K0)

```

---

## 16. K0 Processing After Receipt

From Memory Writer's perspective, K0 processing is a black box. But understanding P02 is important for validating MW output quality.

### P02 Module Pipeline (18 Stages)

After K0's hot path commits the envelope to `st_wal` and queues it in `st_outbox`, P02 processes it:

| Stage | Module | What It Does | MW Field Used |
| --- | --- | --- | --- |
| M01 | DG Pattern Separation | Computes fingerprints for dedup | `text` |
| M02 | Semantic Projection | Extracts entities, KG triples | `text`, `participants` |
| M04 | Affect Analysis (UltraBERT) | Validates sentiment, emotions, safety | `text`, `sentiment_label`, `emotion_tags` |
| M06 | Salience Scoring | Computes importance score | All fields |
| M07 | Social Graph Resolve | Maps to `st_relationships` | `participants` |
| M08 | Temporal Profiling | Extracts time patterns | `event_time_utc` |
| M16 | Atomic Writer | Writes to `st_hipp_events` | Complete enriched event |

### P02 Performance (Background, NOT Hot Path)

| Metric | P50 | P95 |
| --- | --- | --- |
| Total P02 pipeline | ~50ms | ~100ms |
| UltraBERT inference | ~20ms | ~40ms |
| Atomic write | ~10ms | ~20ms |

P02 adds ~50-100ms AFTER the hot path's 93ms. Total K0 time from receipt to permanent storage: ~143-193ms.

### Total End-to-End: Turn to Permanent Memory

```text

Turn delivery (user sees response)
  + MW background pipeline:   ~815ms (P95)
  + Bridge transport:         ~50ms
  + K0 hot path:              ~93ms
  + K0 P02 background:        ~100ms
  -----------------------------------------------
  = ~1058ms from turn delivery to st_hipp_events

Memory is permanently stored within ~1 second of the user receiving their response.

```

---

## 17. Agent Contract (memory_writer.yaml)

The Memory Writer Agent is defined as a standard K1 agent contract, stored in `k1/contracts/agents/memory_writer.yaml`.

```yaml

agent_contract:
  # ---- Identity ----
  name: "agent.execute.memory_writer"
  version: "1.0.0"
  domain:
    - "MEMORY"
    - "EPISODIC"

  # ---- Description ----
  description: "Extracts discrete factual memories from conversation turns"
  capabilities:
    - "extract_episodic_memory"
    - "tag_memory_metadata"
    - "resolve_participants"
  limitations:
    - "Max 6 extractions per turn"
    - "Max 50 words per extraction"
    - "Does not handle eviction/archival (separate concern)"

  # ---- Input Requirements ----
  required_inputs:
    - name: "turn_payload"
      type: "OBJECT"
      description: "turn.complete.v1 event payload"
    - name: "extraction_context"
      type: "OBJECT"
      description: "ExtractionContext from Context Assembly stage"

  # ---- Context Requirements (SessionState sections) ----
  required_context:
    - "history_active"
    - "beliefs_active"
    - "affective_now"
    - "scoreboard"
    - "meta"

  # ---- Agent-Specific Fields ----
  prompt_template: "memory_writer_persona"
  tools_granted:
    - "memory.delta"                             # Only tool: emit K0 memory envelope
  llm_budget_tokens: 2000
  max_tool_calls: 6                              # One per extraction (max 6)
  max_execution_time_ms: 5000

  # ---- Output Schema ----
  output:
    type: "array"
    items:
      type: "object"
      properties:
        text: { type: "string", maxLength: 250 }
        participants: { type: "array", items: { type: "string" } }
        location_name: { type: "string" }
        activity_type: { type: "string" }
        topics: { type: "array", items: { type: "string" }, minItems: 1, maxItems: 3 }
        sentiment_label: { type: "string", enum: ["very_negative", "negative", "neutral", "positive", "very_positive"] }
        emotion_tags: { type: "array", items: { type: "string" } }
        categories: { type: "array", items: { type: "string" } }
        confidence: { type: "number", minimum: 0.0, maximum: 1.0 }

  # ---- Provider Metadata ----
  provider_type: "AGENT"
  template_file: "memory_writer.yaml"

  # ---- Policy Metadata ----
  safety_band_min: "GREEN"
  cost_per_call: 0.001                           # Cheapest model, minimal tokens
  avg_latency_ms: 300
  max_latency_ms: 5000
  availability: "ONLINE"

  # ---- Lifecycle ----
  lifecycle: "session-bound"                     # Spawned per session, reused across turns
  idle_pool: true                                # Goes to IDLE after each turn, reactivated next turn
  idle_ttl_ms: 300000                            # 5 minutes idle TTL (session typically active)

  # ---- Audit Fields ----
  registered_at: "2026-02-06T00:00:00Z"
  last_updated: "2026-02-06T00:00:00Z"
  success_rate_30d: null                         # New agent, no data yet
  total_invocations_30d: 0

```

### Lifecycle: Session-Bound Agent

Unlike task agents (invitation_sender, etc.) that are one-shot, Memory Writer Agent is session-bound:

```text

Session starts
  -> Fabric spawns MemoryWriterAgent (PENDING -> WARMING -> ACTIVE)
  -> Turn 1 completes -> MW processes -> ACTIVE -> IDLE (pool)
  -> Turn 2 completes -> MW reactivated from pool (IDLE -> ACTIVE) -> IDLE
  -> Turn 3 completes -> MW reactivated from pool -> IDLE
  -> ...
  -> Session ends -> MW drained (IDLE -> DRAINING -> TERMINATED)

```

The agent stays warm for the entire session. No cold-start overhead after the first turn.

---

## 18. LLM Prompt Design (memory_writer_persona.md)

### System Prompt

```text

You are KO's Memory Writer. Your job is to extract discrete, factual memories
from conversation turns.

RULES:
1. Extract 1-3 memories per turn. Each memory is a SHORT, factual statement
   (1-2 sentences, max 50 words).
2. Each memory must be self-contained (readable without the conversation).
3. ONLY extract facts about the user's life, people, places, events, tasks,
   preferences, and activities. Do NOT extract:
   - System instructions or meta-commentary
   - Your own responses or reasoning
   - Speculative or uncertain information (unless user stated it)
4. Tag each memory with ALL fields K0 expects:
   - text (the factual statement)
   - participants (people mentioned, use natural names -- Person Resolver will convert)
   - location_name (if a place is mentioned)
   - activity_type (MEAL, TASK, TRAVEL, HEALTH, SOCIAL, WORK, EDUCATION, etc.)
   - topics (1-3 topic tags: family, dining, health, travel, work, etc.)
   - sentiment_label (very_negative, negative, neutral, positive, very_positive)
   - emotion_tags (from: joy, contentment, anxiety, concern, sadness, anger, surprise, etc.)
   - categories (activity categories)
   - confidence (your confidence in this extraction, 0.0-1.0)
5. If the turn contains NO memorable facts (greetings, confirmations, etc.),
   return an empty array [].
6. Use natural names for people ("Mom", "Emma", "Dr. Smith"). The system will
   resolve them to person_ids.
7. Keep text in past tense or present tense. No future-conditional.
8. TEMPORAL REFERENCES:
   For each memory atom, identify ALL temporal references mentioned or implied.
   Return them in "temporal_links" (array, max 5 per atom).

   Each temporal_link has:
     mentioned_time: Raw text from conversation (e.g. "yesterday evening")
     link_type: One of RETROSPECTIVE, PROSPECTIVE, CONCURRENT, HABITUAL, CONTEXTUAL, CONDITIONAL
     uncertainty_window_ms: Precision estimate in milliseconds
     confidence: Your confidence in this temporal reference (0.0-1.0)

   Link types:
     RETROSPECTIVE: Past reference ("yesterday", "last week", "when I was young")
     PROSPECTIVE: Future reference ("tomorrow", "next month", "someday")
     CONCURRENT: Happening now ("right now", "at the moment") -- usually implicit
     HABITUAL: Recurring pattern ("every Sunday", "usually", "always")
     CONTEXTUAL: Life period ("in college", "during my 20s", "back then")
     CONDITIONAL: Contingent ("if it rains", "when we get home")

   Uncertainty window examples:
     "at 7:15pm" -> 60000 (1 minute)
     "yesterday evening" -> 14400000 (4 hours)
     "last week" -> 604800000 (7 days)
     "last summer" -> 7776000000 (90 days)

   Examples:
     "Yesterday we planned next Friday's party and Mom mentioned Christmas"
     -> 3 temporal_links:
       { mentioned_time: "yesterday", link_type: "RETROSPECTIVE", uncertainty_window_ms: 86400000, confidence: 0.95 }
       { mentioned_time: "next Friday", link_type: "PROSPECTIVE", uncertainty_window_ms: 86400000, confidence: 0.90 }
       { mentioned_time: "Christmas", link_type: "PROSPECTIVE", uncertainty_window_ms: 86400000, confidence: 0.85 }

     "We go to Olive Garden every Friday"
     -> 1 temporal_link:
       { mentioned_time: "every Friday", link_type: "HABITUAL", uncertainty_window_ms: 0, confidence: 0.95 }

     "I feel happy right now"
     -> 0 temporal_links (no explicit temporal reference, CONCURRENT is implicit)

   If no temporal expression is mentioned, temporal_links should be an empty array [].

```

### User Prompt Template

```text

CONTEXT:
  Recent turns: {recent_turns}
  Known entities: {active_entities}
  Current emotion: {current_emotion}
  Active topics: {active_topics}
  Privacy band: {privacy_band}

CURRENT TURN:
  User: {user_message}
  Assistant: {assistant_response}
  Turn #: {conversation_turn}

Extract 0-3 factual memories from this turn. Return as JSON array.

```

### Output Format

```json

[
  {
    "text": "Had dinner with Mom at Olive Garden to celebrate Emma's birthday",
    "participants": ["Mom", "Emma"],
    "location_name": "Olive Garden",
    "activity_type": "MEAL",
    "topics": ["family", "dining", "celebration"],
    "sentiment_label": "positive",
    "emotion_tags": ["joy", "contentment"],
    "categories": ["social", "meal"],
    "confidence": 0.95,
    "temporal_links": [
      {
        "mentioned_time": "yesterday",
        "link_type": "RETROSPECTIVE",
        "uncertainty_window_ms": 86400000,
        "confidence": 0.95
      }
    ]
  }
]

```

---

## 19. Person Resolver

### Purpose: Privacy Enforcement

Convert natural names (as produced by the LLM) to stable `person_*` identifiers (as required by K0).

### Resolution Process

```python

class PersonResolver:
    """
    Resolves natural names to person_ids.
    Source: SessionState beliefs_active + scoreboard.
    """

    def resolve(self, name: str, context: ExtractionContext) -> str:
        """
        'Mom'    -> 'person_mom'
        'Panda'  -> 'person_panda'
        'Emma'   -> 'person_emma'
        'Dr. Smith' -> 'person_dr_smith' (if known) or pass-through

        Resolution order:
        1. Exact match in beliefs_active.entities (name -> person_id)
        2. Alias match in beliefs_active (e.g., "Mother" -> person_mom)
        3. Scoreboard referent match (active in conversation)
        4. Fallback: sanitize name to person_id format (person_<lowercase_name>)
        """
        # Step 1: Exact match
        for entity in context.active_entities:
            if entity.name.lower() == name.lower():
                return entity.person_id

        # Step 2: Alias match
        for entity in context.active_entities:
            if name.lower() in [a.lower() for a in entity.aliases]:
                return entity.person_id

        # Step 3: Scoreboard referent
        for ref in context.active_referents:
            if ref.lower() == name.lower() and hasattr(ref, 'person_id'):
                return ref.person_id

        # Step 4: Fallback -- generate person_id from name
        sanitized = re.sub(r'[^a-z0-9_]', '_', name.lower()).strip('_')
        return f"person_{sanitized}"

    def resolve_all(self, names: list[str], context: ExtractionContext) -> list[str]:
        """Resolve all names, preserving order. Dedup by person_id."""
        seen = set()
        resolved = []
        for name in names:
            pid = self.resolve(name, context)
            if pid not in seen:
                seen.add(pid)
                resolved.append(pid)
        return resolved

```

### Why Not Do This in K0?

K0 receives person_ids, not natural names. K1 has the conversation context (beliefs_active with the family graph, aliases, nicknames). K0 only has `st_relationships` (structured graph without nickname resolution). The LLM in K1 understands that "Panda" is a family member. K0's UltraBERT ner_family head might classify it as ANIMAL without conversation context.

---

## 20. Privacy Enforcer (Band-Based)

### Purpose

Strip or generalize sensitive fields BEFORE the envelope reaches the Bridge. Defense-in-depth: K0 Gate also enforces band policies, but Memory Writer strips early to minimize exposure in transit.

### Band Rules

| Band | Action | Fields Affected |
| --- | --- | --- |
| `GREEN` | All fields pass through | None stripped |
| `AMBER` | Location generalized | `location_name`: "Olive Garden" -> "Restaurant" |
| `RED` | Location stripped, participants masked | `location_name`: null, `participants`: ["person_redacted_1", ...] |

### Privacy Enforcer Implementation

```python

class PrivacyEnforcer:
    """
    Pre-submit field stripping based on privacy band.
    Runs BEFORE Bridge submit (defense-in-depth).
    """

    def enforce(self, envelope: CommandEnvelope, band: str) -> CommandEnvelope:
        if band == "GREEN":
            return envelope  # No modifications

        if band == "AMBER":
            # Generalize location (keep type, remove specifics)
            loc = envelope.body.get("location_name")
            if loc:
                envelope.body["location_name"] = self._generalize_location(loc)
            return envelope

        if band == "RED":
            # Strip location entirely
            envelope.body["location_name"] = None
            # Mask participants
            participants = envelope.body.get("participants", [])
            envelope.body["participants"] = [
                f"person_redacted_{i}" for i in range(len(participants))
            ]
            return envelope

        return envelope

    def _generalize_location(self, location: str) -> str:
        """
        'Olive Garden' -> 'Restaurant'
        'Stanford Hospital' -> 'Hospital'
        'Central Park' -> 'Park'

        Uses a simple category lookup. Not an LLM call.
        """
        categories = {
            "restaurant": ["olive garden", "mcdonalds", "chez panisse", ...],
            "hospital": ["stanford hospital", "kaiser", ...],
            "school": ["stanford", "berkeley", ...],
            # ... category mappings
        }
        for category, keywords in categories.items():
            if any(kw in location.lower() for kw in keywords):
                return category.title()
        return "Location"  # Generic fallback

```

---

## 21. Eviction Writes (NOT Memory Writer)

This section exists to prevent confusion. Eviction writes and Memory Writer writes are completely separate concerns.

### What Eviction Writes Are

When SessionState's WARM tier sections (beliefs_history, history_recent, etc.) exceed their budget, the EvictionEngine archives them to K0. This is SessionState's own housekeeping, NOT Memory Writer.

### Comparison Table: Eviction vs Memory Writer

| Property | Memory Writer | Eviction Writes |
| --- | --- | --- |
| **Trigger** | turn.complete.v1 (every turn) | k1.sessionstate.eviction.v1 (budget exceeded) |
| **Source data** | Current turn conversation | WARM tier sections being evicted |
| **Bridge topic** | `memory.delta` | `beliefs.archive`, `history.archive` |
| **Frequency** | Every substantive turn | Infrequent (when sections overflow) |
| **LLM involved** | Yes (extraction) | No (raw archival) |
| **Output** | Short factual statements | Raw section data |
| **K0 destination** | P02 -> st_hipp_events | P02 -> st_hipp_events (different schema) |
| **Owner** | Memory Writer system | SessionState EvictionEngine |

### Rule

Memory Writer uses topic `memory.delta` ONLY. Eviction uses `beliefs.archive` and `history.archive`. No overlap. No confusion.

---

## 22. Memory Writer vs Learning Extractor

Both agents observe conversation turns. Both run after turn.complete.v1. But they have completely different purposes.

### Comparison Table: Memory Writer vs Learning Extractor

| Property | Memory Writer Agent | Learning Extractor Agent |
| --- | --- | --- |
| **System** | Memory Writer (k1/memory_writer/) | Learning Loop (k1/learning/) |
| **Diagram** | memory_writer.mmd | learning.mmd |
| **Purpose** | Extract FACTS from conversations | Extract META-SIGNALS for system improvement |
| **Trigger** | turn.complete.v1 (every turn) | turn.complete.v1 + gap signals + feedback |
| **Runs** | Every substantive turn (after filter) | Only on specific learning signals |
| **Output** | MemoryExtraction[] -> K0 envelopes | LearningSignal[] -> Feedback Envelope Builder |
| **LLM budget** | 500 tokens (cheapest model) | Higher budget (analysis model) |
| **Example output** | "Had dinner with Mom at Olive Garden" | "User asked about restaurant booking but system had no tool for it -- gap signal" |
| **K0 destination** | st_hipp_events (via P02) | st_learning_signals (via feedback port) |
| **Frequency** | High (most turns produce extractions) | Low (only when learning-relevant signals appear) |

### Why Separate

1. **Different frequency**: MW runs on every turn. LE runs only on specific signals.
2. **Different output schemas**: MW produces K0 memory envelopes. LE produces learning signals.
3. **Different LLM budgets**: MW is cost-optimized (500 tokens). LE needs more budget for meta-analysis.
4. **Different purposes**: MW stores facts. LE improves the system.
5. **Clean ownership**: MW is in memory_writer/. LE is in learning/. Each has its own diagram, contract, and lifecycle.

---

## 23. Trigger Mechanism (turn.complete.v1)

### Event Source

Concierge emits `turn.complete.v1` on the DeltaBus immediately after the DELIVERING state (after the user receives their response). This is the ONLY trigger for Memory Writer.

### Event Payload

```yaml

turn.complete.v1:
  turn_id: "uuid"                                # Unique turn identifier
  session_id: "uuid"                             # Session this turn belongs to
  cognitive_trace_id: "uuid"                     # Causality trace (spans entire request)
  user_message: "Had dinner with Mom..."         # Original user input
  assistant_response: "That sounds lovely..."    # System's response
  timestamp_ms: 1738857600000                    # Epoch milliseconds
  turn_number: 5                                 # Ordinal within session (1-based)
  tier: "LOW"                                    # Complexity tier that processed this turn

```

### Turn Dispatcher (Idempotency)

The Turn Dispatcher sits between the DeltaBus subscription and the pipeline:

```python

class TurnDispatcher:
    """
    Routes turn.complete.v1 events to Memory Writer pipeline.
    Guarantees at-most-once processing per turn_id.
    """

    def __init__(self):
        self.processed_turn_ids: set[str] = set()  # In-memory dedup (cleared on session end)

    async def dispatch(self, event: TurnCompleteEvent) -> None:
        if event.turn_id in self.processed_turn_ids:
            log.info("MW: duplicate turn_id, skipping", turn_id=event.turn_id)
            return

        self.processed_turn_ids.add(event.turn_id)
        await self.pipeline.process(event)

```

---

## 24. Error Handling and Failure Modes

### Error Categories

| Error | Source | Handling | Impact |
| --- | --- | --- | --- |
| `context_read_failed` | SessionState reader | Retry once, then skip turn | Turn not extracted |
| `llm_timeout` | Model Hub (>5000ms) | Abort extraction, log, skip turn | Turn not extracted |
| `llm_error` | Model Hub (API error) | Retry once, then skip turn | Turn not extracted |
| `llm_invalid_output` | LLM returned malformed JSON | Validator drops, log | Partial extraction (valid ones kept) |
| `bridge_submit_failed` | Bridge (non-offline) | Retry once, then log | Envelopes lost (rare) |
| `bridge_offline` | K0 unavailable | Queue in LocalOutbox (MW-09) | Eventually delivered |
| `extraction_all_dropped` | Validator dropped all extractions | Log, no submit | No memory from this turn |
| `person_resolve_failed` | Person Resolver | Fallback to generated ID | Less accurate person_id |

### Failure Philosophy

Memory Writer is a **best-effort** system. If extraction fails for a turn, the turn is skipped. No retry loop, no dead-letter queue (except for Bridge offline). This is acceptable because:

1. Most turns repeat information across the conversation.
2. Missed facts can be extracted from future turns that reference the same topic.
3. The user never sees Memory Writer failures (background process).
4. K0's P02 UltraBERT provides additional safety net.

### Circuit Breaker

```yaml

circuit_breaker:
  name: "CB: Memory Writer LLM"
  timeout_ms: 5000                               # 5 seconds per LLM call
  failure_threshold: 5                           # 5 failures per minute
  failure_window_ms: 60000                       # 1 minute sliding window
  half_open_after_ms: 60000                      # Try one request after 1 minute
  fallback: "skip_turn"                          # Skip extraction, log

```

When the LLM circuit breaker is open, Memory Writer silently skips extraction for all turns until the breaker enters half-open state. No impact on the user.

---

## 25. Observability and Metrics

### Cognitive Trace ID

Every Memory Writer operation carries the `cognitive_trace_id` from the originating turn. This unifies causality across the entire chain:

```text

User input -> Concierge (trace_id=X) -> turn.complete.v1 (trace_id=X)
  -> Memory Writer (trace_id=X) -> Bridge submit (trace_id=X)
  -> K0 Gate (trace_id=X) -> K0 P02 (trace_id=X) -> st_hipp_events (trace_id=X)

```

### Metrics Emitted

| Metric | Type | Labels | Purpose |
| --- | --- | --- | --- |
| `k1.mw.turns.total` | Counter | session_id | Total turns received |
| `k1.mw.turns.skipped` | Counter | skip_reason (R1-R5) | Turns skipped by filter |
| `k1.mw.turns.extracted` | Counter | session_id | Turns with successful extractions |
| `k1.mw.extractions.count` | Histogram | session_id | Extractions per turn (0-6) |
| `k1.mw.extractions.avg_words` | Histogram | -- | Average word count per extraction |
| `k1.mw.extractions.confidence` | Histogram | -- | Confidence distribution |
| `k1.mw.llm.tokens_used` | Histogram | -- | Tokens consumed per extraction call |
| `k1.mw.llm.latency_ms` | Histogram | -- | LLM call latency (P50, P95) |
| `k1.mw.llm.errors` | Counter | error_type | LLM errors by type |
| `k1.mw.bridge.submit_count` | Counter | -- | Envelopes submitted to Bridge |
| `k1.mw.bridge.batch_size` | Histogram | -- | Envelopes per batch |
| `k1.mw.bridge.offline_queued` | Counter | -- | Envelopes queued for offline delivery |

### Structured Logging

Every stage logs a structured entry:

```json

{
  "timestamp": "2026-02-06T19:00:00.123Z",
  "level": "INFO",
  "component": "memory_writer.extraction",
  "trace_id": "cognitive-trace-uuid",
  "turn_id": "turn-uuid",
  "session_id": "session-uuid",
  "phase": "llm_extraction",
  "extractions_count": 2,
  "tokens_used": 387,
  "latency_ms": 285,
  "success": true
}

```

Phases logged: `filter`, `context_read`, `llm_extraction`, `validation`, `envelope_build`, `batch_submit`.

---

## 26. Performance Budget

### End-to-End Latency Breakdown

```text

+-----------------------------+----------+----------+---------+
| Stage                       | P50      | P95      | Budget  |
+-----------------------------+----------+----------+---------+
| Turn Dispatch               | <1ms     | <1ms     | 1ms     |
| Relevance Filter            | <1ms     | <2ms     | 2ms     |
| SessionState Read           | <1ms     | <1ms     | 1ms     |
| Context Builder             | <1ms     | <1ms     | 1ms     |
| Person Resolver             | <1ms     | <1ms     | 1ms     |
| LLM Extraction (Model Hub)  | ~200ms   | ~500ms   | 500ms   |
| Extraction Validator        | <1ms     | <1ms     | 1ms     |
| Envelope Builder            | <1ms     | <1ms     | 1ms     |
| Privacy Enforcer            | <1ms     | <1ms     | 1ms     |
| Delta Aggregation (250ms)   | 250ms    | 260ms    | 260ms   |
| Bridge Submit               | ~20ms    | ~50ms    | 50ms    |
+-----------------------------+----------+----------+---------+
| TOTAL MW Pipeline           | ~475ms   | ~815ms   | 815ms   |
+-----------------------------+----------+----------+---------+
| Bridge -> K0 Hot Path        |          | ~93ms    |         |
| K0 P02 Background           |          | ~100ms   |         |
+-----------------------------+----------+----------+---------+
| TOTAL (Turn -> st_hipp)     |          | ~1008ms  |         |
+-----------------------------+----------+----------+---------+

```

### Critical Performance Note

Memory Writer runs AFTER turn delivery (background). It does NOT affect:

- **TTFT** (Time to First Token): Concierge already delivered the response.
- **User-perceived latency**: Zero impact. Background process.
- **Session throughput**: MW processes turns concurrently with the next user input.

The 815ms budget is generous because there is no user waiting.

### Memory and Resource Budget

| Resource | Budget | Notes |
| --- | --- | --- |
| Memory (per session) | ~4KB | ExtractionContext (13 sections) + batch buffer + dedup ring |
| LLM tokens (per turn) | 2000 | Cheapest model (GPT-4o-mini: ~$0.002/turn) |
| LLM cost (per 1000 turns) | ~$2.00 | At 2000 tokens/turn, $0.15/1M input + $0.60/1M output |
| Bridge HTTP (per batch) | 1 POST | Batch window reduces HTTP overhead |
| SessionState reads (per turn) | 1 snapshot (13 sections) | Lock-free, <1ms |

---

## 27. Event Bus Integration

### Events Emitted by Memory Writer

| Event Topic | When | Payload |
| --- | --- | --- |
| `k1.mw.filter.decision.v1` | After relevance filter runs | turn_id, decision (PASS/SKIP), skip_reason, trace_id |
| `k1.mw.extraction.completed.v1` | After successful extraction + validation | turn_id, extraction_count, tokens_used, latency_ms, trace_id |
| `k1.mw.extraction.failed.v1` | After extraction failure | turn_id, error_code, error_message, trace_id |
| `k1.mw.batch.submitted.v1` | After batch submitted to Bridge | batch_size, session_id, trace_id |
| `k1.mw.batch.offline_queued.v1` | When envelopes queued in LocalOutbox | batch_size, session_id, trace_id |

### Events Consumed by Memory Writer

| Event Topic | From | Action |
| --- | --- | --- |
| `turn.complete.v1` | Concierge (via DeltaBus) | Trigger MW pipeline for the turn |
| `k1.sessionstate.eviction.v1` | SessionState Eviction Engine | NOT consumed by MW (separate concern, logged for clarity) |

---

## 28. Cross-Diagram Integration Points

Memory Writer integrates with 6 other K1/Bridge/K0 components. Each integration point is documented in both the MW diagram and the target diagram.

### Concierge (concierge.mmd)

| Direction | What | Notes |
| --- | --- | --- |
| Concierge -> MW | `turn.complete.v1` event on DeltaBus | Trigger for MW pipeline |
| Concierge -> SessionState | Single writer (ADR-0017) | MW reads what Concierge writes |
| MW -> Concierge | Nothing | MW never sends data to Concierge |

### Fabric (fabric.mmd)

| Direction | What | Notes |
| --- | --- | --- |
| Fabric -> MW | Agent Factory spawns MemoryWriterAgent | Per-session lifecycle |
| Fabric -> MW | Agent Registry holds memory_writer.yaml | Contract for agent configuration |
| MW -> Fabric | Nothing directly | MW uses Model Hub (via Fabric Agent runtime) |

### SessionState (sessionstate diagram)

| Direction | What | Notes |
| --- | --- | --- |
| SS -> MW | Multi-reader access (lock-free) | MW reads 5 sections |
| MW -> SS | Nothing. Ever. | MW-01 invariant |

### Model Hub (not yet designed)

| Direction | What | Notes |
| --- | --- | --- |
| MW -> Hub | LLM extraction calls | 500 token budget, cheapest model |
| Hub -> MW | MemoryExtraction[] (structured output) | JSON array from LLM |

### Bridge (bridge_architecture.mmd)

| Direction | What | Notes |
| --- | --- | --- |
| MW -> Bridge | IKernelCommandPort.submit(topic, schema_uri, body) | Fire-and-forget |
| Bridge -> K0 | POST /k0/command.submit (signed envelope) | ONE-WAY |
| Bridge -> LocalOutbox | Queue when K0 offline | MW-09 |

### K0 (k0_source_of_truth_v2.mmd)

| Direction | What | Notes |
| --- | --- | --- |
| K0 receives | Signed envelope via Bridge | MW never talks to K0 directly (MW-03) |
| K0 processes | P02 pipeline (DG + UltraBERT + Social + Embed) | UltraBERT validates MW output (MW-11) |
| K0 stores | st_hipp_events (permanent memory) | End destination for MW output |

---

## 29. Dependency Graph and Build Order

### Internal Component Dependencies

```text

[1] ExtractionContext + CompressedTurn types
    (data structures for context assembly)
         |
         v
[2] Relevance Filter (Rule Engine)
    (5 skip rules, no dependencies on LLM or Bridge)
         |
         v
[3] SessionState Reader (Multi-Reader interface)
    (reads 5 sections, builds ExtractionContext)
         |
         v
[4] Person Resolver
    (resolves natural names to person_ids from context)
         |
         v
[5] LLM Writer Agent + Extraction Validator
    (depends on Model Hub for LLM calls)
         |
         v
[6] Envelope Builder + Privacy Enforcer
    (deterministic field mapping, band-based stripping)
         |
         v
[7] Delta Aggregator + Batch Emitter
    (250ms window, Bridge submit)
         |
         v
[8] Turn Dispatcher + Pipeline Orchestrator
    (wires all stages together, subscribes to DeltaBus)

```

### External Dependencies

| Dependency | Component | What MW Uses |
| --- | --- | --- |
| DeltaBus | K1 Coordination | Subscription to turn.complete.v1 |
| SessionState | K1 SessionState Store | Multi-reader access (lock-free) |
| Fabric Agent Factory | K1 Fabric | Spawns MemoryWriterAgent per session |
| Model Hub | K1 L2.5 | LLM calls for extraction |
| Bridge Command Port | K1 Cross-Kernel Bridge | IKernelCommandPort.submit() |
| K1 Event Bus | K1 Coordination | Event emission (metrics, status) |

### Recommended Build Order

| Phase | What | Why First |
| --- | --- | --- |
| Phase 1 | Types: ExtractionContext, CompressedTurn, MemoryExtraction | Everything reads these |
| Phase 2 | Relevance Filter | No external deps, testable in isolation |
| Phase 3 | SessionState Reader + Person Resolver | Depends on SS interface only |
| Phase 4 | Extraction Validator | Pure validation logic, testable |
| Phase 5 | LLM Writer Agent | Depends on Model Hub integration |
| Phase 6 | Envelope Builder + Privacy Enforcer | Deterministic, pure functions |
| Phase 7 | Delta Aggregator + Batch Emitter | Depends on Bridge interface |
| Phase 8 | Turn Dispatcher + Pipeline | Wires everything together |
| Phase 9 | Agent Contract registration in Fabric | Requires Fabric Registry |

---

## 30. Directory Structure (Target)

```text

k1/memory_writer/
  __init__.py
  types.py                           # Domain types: 14 enums, 11 frozen dataclasses (34-field MemoryAtom)
  config.py                          # MWConfig frozen dataclass (all tunable parameters)
  invariants.py                      # MW-01..MW-11 machine-checkable assertion helpers
  events.py                          # Event topic constants + frozen payload dataclasses
  memory_writer.mmd                  # Architecture diagram
  memory_writer_architecture.md      # This document

  ports/                             # Hexagonal port protocols (5 ports)
    __init__.py                      # Re-exports all 5 ports
    session_read_port.py             # ISessionReadPort (read-only, MW-01, MW-02)
    bridge_command_port.py           # IBridgeCommandPort (fire-and-forget, MW-03, MW-09)
    event_subscription_port.py       # IEventSubscriptionPort (bus subscribe/publish)
    model_hub_port.py                # IModelHubPort (LLM chat, MW-06, MW-07)
    health_port.py                   # IHealthPort (readiness + health check)

  pipeline/
    __init__.py
    pipeline.py                      # MemoryWriterPipeline (wires 5 stages)
    turn_dispatcher.py               # TurnDispatcher (Bus subscription, dedup)

  filter/
    __init__.py
    relevance_filter.py              # RelevanceFilter (5 skip rules)
    rules.py                         # Individual rule implementations (R1-R5)

  context/
    __init__.py
    session_reader.py                # MWSessionReader (multi-reader, 13-section snapshot)
    context_builder.py               # ContextBuilder (assembles ExtractionContext)
    person_resolver.py               # PersonResolver (name -> person_id)

  extraction/
    __init__.py
    writer_agent.py                  # MemoryWriterAgent (LLM extraction, 2000 token budget)
    extraction_validator.py          # ExtractionValidator (post-LLM validation, 34-field)
    prompts/
      memory_writer_persona.md       # System prompt for Writer Agent

  envelope/
    __init__.py
    envelope_builder.py              # EnvelopeBuilder (MemoryAtom -> MWEnvelope)
    field_mapper.py                  # Field mapping rules (34-field atom -> K0 body)
    privacy_enforcer.py              # PrivacyEnforcer (band-based field stripping)

  batch/
    __init__.py
    delta_aggregator.py              # DeltaAggregator (250ms window, dedup)
    batch_emitter.py                 # BatchEmitter (Bridge submit)

  health/
    __init__.py
    circuit_breaker.py               # MWCircuitBreaker (3 failures/min, 30s recovery)

  adapters/                          # Infrastructure bindings (hexagonal adapters)
    __init__.py
    session_read_adapter.py          # Binds ISessionReadPort to K1 SessionState
    bridge_command_adapter.py        # Binds IBridgeCommandPort to Bridge IKernelCommandPort
    event_subscription_adapter.py    # Binds IEventSubscriptionPort to K1 Bus
    model_hub_adapter.py             # Binds IModelHubPort to K1 Model Hub
    health_adapter.py                # Binds IHealthPort to Fabric health system
    test_adapters.py                 # All 5 in-memory mock adapters for testing

```

---

## 31. Worked Examples (End-to-End)

### Example 1: Simple Meal Memory

```text

Turn: User says "Had dinner with Mom at Olive Garden yesterday"
Session: session-abc123, Turn #5, Band: GREEN

Stage 1 -- Filter:
  R4 (trivial)? No -- >5 words, has entities (Mom, Olive Garden)
  R5 (continuation)? No -- not a continuation phrase
  R1 (clarification)? No -- not a repair
  R2 (meta)? No -- about life, not system
  R3 (duplicate)? No -- hash not in window
  Result: PASS

Stage 2 -- Context Assembly:
  SessionState read:
    history_active: [turn 3: "...", turn 4: "..."]
    beliefs_active: [{name: "Mom", person_id: "person_mom", aliases: ["Mother"]}]
    affective_now: {emotion: "contentment", intensity: 0.4}
    scoreboard: {topics: ["family"]}
    meta: {session_id: "session-abc123", actor: "user-001", band: "GREEN"}
  ExtractionContext assembled (~160 tokens)

Stage 3 -- LLM Extraction:
  Prompt sent to GPT-4o-mini (387 tokens total)
  Response:
    [{
      "text": "Had dinner with Mom at Olive Garden",
      "participants": ["Mom"],
      "location_name": "Olive Garden",
      "activity_type": "MEAL",
      "topics": ["family", "dining"],
      "sentiment_label": "positive",
      "emotion_tags": ["contentment"],
      "categories": ["social", "meal"],
      "confidence": 0.95
    }]
  Validator: PASS (all checks green)
  Person Resolver: "Mom" -> "person_mom"

Stage 4 -- Envelope Build:
  Body: {"operation": "UPSERT", "text": "Had dinner with Mom at Olive Garden",
         "event_time_utc": "2026-02-06T19:00:00Z", "participants": ["person_mom"],
         "location_name": "Olive Garden", "activity_type": "MEAL",
         "topics": ["family", "dining"], "sentiment_label": "positive",
         "emotion_tags": ["contentment"], "categories": ["social", "meal"],
         "session_id": "session-abc123", "conversation_turn": 5, "language": "en"}
  Headers: {topic: "memory.delta", schema_uri: "schema://memory.delta", ...}
  Privacy: GREEN, no stripping

Stage 5 -- Batch Submit:
  250ms window -> 1 envelope in batch
  Bridge: IKernelCommandPort.submit() -> CommandBuilder signs -> POST /k0/command.submit
  K0: Gate ALLOW -> WAL + idem + outbox + receipt (93ms) -> 202 Accepted
  K0: P02 -> UltraBERT confirms sentiment=positive, adds emotion=contentment (match) -> st_hipp_events

```

### Example 2: Multi-Fact Turn

```text

Turn: User says "Need to call dentist tomorrow and also check SEVIS appointment"
Session: session-abc123, Turn #8, Band: GREEN

Stage 1 -- Filter: PASS (entities: dentist, SEVIS; activity: tasks)

Stage 3 -- LLM Extraction:
  Extraction 1:
    text: "Need to call dentist tomorrow"
    activity_type: "TASK"
    topics: ["health", "appointment"]
    sentiment_label: "neutral"
    confidence: 0.90

  Extraction 2:
    text: "Need to check SEVIS appointment date"
    activity_type: "TASK"
    topics: ["immigration", "appointment"]
    sentiment_label: "neutral"
    confidence: 0.85

Stage 5 -- Batch Submit: 2 envelopes in single batch -> 1 Bridge POST

```

### Example 3: Turn Skipped by Filter

```text

Turn: User says "ok thanks"
Session: session-abc123, Turn #6, Band: GREEN

Stage 1 -- Filter:
  R4 (trivial)? YES -- <5 words, no entities, matches "thanks" pattern
  Result: SKIP (reason: R4)
  Event: k1.mw.filter.decision.v1 {decision: "SKIP", skip_reason: "R4"}

Pipeline exits. No LLM cost. No Bridge submit.

```

### Example 4: RED Band Privacy

```text

Turn: User says "Mom is at Stanford Hospital for a checkup"
Session: session-xyz, Turn #3, Band: RED

Stage 3 -- LLM Extraction:
  text: "Mom is at Stanford Hospital for a checkup"
  participants: ["Mom"]
  location_name: "Stanford Hospital"
  activity_type: "HEALTH"

Stage 4 -- Envelope Build + Privacy Enforcer:
  Band = RED:
    location_name: null (STRIPPED)
    participants: ["person_redacted_0"] (MASKED)

  Final body:
    {"text": "Family member at hospital for a checkup",
     "participants": ["person_redacted_0"], "location_name": null,
     "activity_type": "HEALTH", ...}

```

---

## 32. Open Design Questions

These items require decisions before implementation:

| # | Topic | Status | Blocks |
| --- | --- | --- | --- |
| 1 | **Prompt Engineering**: Exact memory_writer_persona.md content, few-shot examples, output format enforcement | DRAFT EXISTS (Section 18) | Writer Agent quality |
| 2 | **Person Resolver Accuracy**: How to handle ambiguous names ("Alex" could be multiple people), conflict resolution strategy | NEEDS DESIGN | Participant resolution |
| 3 | **Model Hub Integration**: How Writer Agent calls LLM via Model Hub (not yet designed). Routing, fallback, budget enforcement. | BLOCKED ON MODEL HUB | LLM extraction |
| 4 | **Extraction Quality Metrics**: How to measure extraction quality over time. Recall vs precision tradeoff. User feedback loop. | NEEDS DESIGN | Quality improvement |
| 5 | **Duplicate Detection Across Sessions**: Current R3 dedup is within-session only. Cross-session dedup happens in K0 P02 (M01 DG pattern). Is that sufficient? | NEEDS ANALYSIS | Dedup accuracy |
| 6 | **Event Time vs Turn Time**: Should `event_time_utc` be the actual event time (from conversation context) or the turn submission time? | SUPERSEDED by GAP-002 (2026-03-05): preserve conversation anchor separately (`conversation_anchor_ms`) and propagate turn timestamp through MW -> Bridge. `event_time_utc` in K0 must represent conversation time, while referred time is stored separately (`temporal_resolved_epoch_ms` / `temporal_links`). | N/A |
| 7 | **Filter Rule Tuning**: Skip rule thresholds (word count, entity detection sensitivity) need empirical tuning. Need a test corpus. | NEEDS DATA | Filter accuracy |
| 8 | **Confidence Threshold**: Is 0.3 the right confidence floor for dropping extractions? | RESOLVED (v2): `confidence_floor: 0.30` set in `policies.contract.yaml` and `MWConfig`. Empirically derived from LLM extraction experiments. Configurable at runtime. | N/A |
| 9 | **Batch Window Tuning**: Is 250ms optimal? Tradeoff between latency (smaller window) and efficiency (larger window). | NEEDS BENCHMARKS | Performance |
| 10 | **AMBER Location Generalization**: The category lookup table for location generalization needs to be comprehensive. Can we use UltraBERT's ner_general LOC type for this? | NEEDS ANALYSIS | Privacy enforcement |
| 11 | **Multi-Language Support**: Current default is `"en"`. How to detect language from conversation context? SessionState.meta.locale? | NEEDS DESIGN | i18n |

---

## 33. v2 Cross-Reference (stage5_proposal_corrections.md)

Memory Writer v2 design is grounded in `docs/pipelines/p03/stage5_proposal_corrections.md`, which defines three layers:

### LAYER 1 -- Pipeline Architecture

- MW sits on the K1 side of the signal chain: K1 SessionState -> K1 MW v2 -> Bridge -> K0 P02 -> st_hipp_events -> K0 P03 Consolidation
- MW reads 15 SessionState sections (13 hot+warm, 2 skipped)
- 2000-token LLM budget (up from 500 in v1)
- 0-6 atoms per turn (up from 0-3 in v1)

### LAYER 2 -- 34-Field MemoryAtom Schema

The authoritative field reference for MW v2 output. All 34 fields, their types, enums, and required status are defined in:

- JSON Schema: `k1/contracts/schemas/memory_writer/memory_atom.v2.schema.json`
- Python types: `k1/memory_writer/types.py`

12 cognitive dimensions:

1. Sentiment (5-class)
2. Affect (VAD triple)
3. Novelty (4-level)
4. Elaboration Depth (4-level)
5. Temporal Orientation (3-class)
6. Source Type (4-class)
7. Arc Position (4-class)
8. Social Intimacy (3-level)
9. Social Context (6-class)
10. Intent Type (8-class)
11. Activity Type (20-class)
12. Identity Domains (9-class, multi-select)

### LAYER 3 -- K0 P03 Consolidation Contract

MW v2 output must be compatible with K0 P03 consolidation. The 34-field atom maps to `st_hipp_events` columns. K0 P02 enriches MW output before storage. P03 reads from `st_hipp_events` for consolidation into long-term memory.

---

## 34. Implementation Sync Addendum (GAP-002, 2026-03-05)

This section is the coding-time delta from v2 design to current target behavior.
Use it as the implementation checklist when modifying Memory Writer.

### 34.1 Authoritative Temporal Semantics

1. Conversation anchor and referred time are different signals and MUST NOT be conflated.
2. `conversation_anchor_ms` means "when this turn happened" (from `turn.complete.v1.timestamp_ms`).
3. Referred time(s) mean "what time the content talks about" and belong in `temporal_links` (or legacy `temporal`).
4. K0 `event_time_utc` must represent conversation time. Referred time goes to `temporal_resolved_epoch_ms` / `temporal_links_json`.

### 34.2 Required MW/Bridge Coding Updates

| ID | File | Required Update |
| --- | --- | --- |
| MW-A1 | `k1/memory_writer/types.py` | Ensure ExtractionContext carries turn timestamp from trigger (`current_turn.timestamp_ms` path remains authoritative). |
| MW-A2 | `k1/memory_writer/pipeline/envelope_stage.py` | Add `turn_timestamp_ms` in envelope body for every extracted atom (including cases where legacy `temporal` is null). |
| MW-A3 | `bridge/core/envelope_builder.py` | Add optional `event_time_ms` input to `EnvelopeBuilder.build(...)`; if set, derive `envelope.ts` from it; otherwise fallback to `now_utc()`. |
| MW-A4 | Bridge caller path | Pass turn timestamp into `EnvelopeBuilder.build(event_time_ms=...)` from MW batch submission path. |
| MW-B1 | `k1/memory_writer/types.py` | Add `TemporalLinkType` enum (Part V taxonomy: CONVERSATION_TIME, MENTIONED_TIME, INFERRED_TIME, DEADLINE). |
| MW-B2 | `k1/memory_writer/types.py` | Add frozen `TemporalLink` dataclass (link_type, epoch_ms, text_mention, precision, is_backdated). |
| MW-B3 | `k1/memory_writer/types.py` | Add `temporal_links: List[TemporalLink]` on MemoryAtom; keep legacy `temporal` during migration window. |
| MW-B5 | `k1/memory_writer/pipeline/writer_agent.py` | Update prompt to extract multiple temporal references per atom, not a single temporal value. |
| MW-B6 | `k1/contracts/schemas/memory_writer/memory_atom.v2.schema.json` | Add schema for `temporal_links`; keep backward compatibility for legacy payloads. |
| MW-B7 | `k1/memory_writer/invariants.py` | Validate temporal_links bounds and enums; cap links per atom. |

### 34.3 Deprecation Timeline (Implementation)

1. Phase 2: populate both `temporal_links` and legacy `temporal`.
2. Phase 2 + 1 release: stop populating `temporal` for new atoms (field still accepted).
3. Phase 2 + 2 releases: remove legacy `temporal`/`temporal_orientation` generation path and update schema compatibility plan.

### 34.4 Do/Do Not Guidance for Contributors

1. Do use `turn.complete.v1.timestamp_ms` as the conversation-time source of truth.
2. Do keep MW extraction per-atom and avoid cross-atom linking logic in MW.
3. Do not overwrite conversation-time semantics with resolved/referred temporal values.
4. Do not remove UltraBERT fallback assumptions from downstream K0 design notes.

### 34.5 Verification Checklist for MW Changes

1. Envelope body always includes `turn_timestamp_ms`.
2. Bridge `envelope.ts` equals turn time when `event_time_ms` is provided.
3. Multi-temporal utterances produce 2+ `temporal_links` entries.
4. Legacy envelopes without `temporal_links` still validate and flow.

---

## 35. K1 Correction Signal Fields (R2 Epic 7.2)

### Background: Why K1 Must Signal Corrections

R2 research (Phase 9 diagnostic) proved that K0 P03 cannot detect EVOLVE/CONTRADICT through embedding cosine distance. UltraBERT family-diary data has a similarity floor of ~0.92, making old-vs-corrected facts indistinguishable from genuinely similar facts. The architectural decision: EVOLVE and CONTRADICT are conversational signals that only K1's LLM can detect. P03 becomes the signal processor, not the signal detector.

See:

- `docs/pipelines/P03_consolidation_dossier_v2.md` Section 1.3.1 (Signal Detection Boundary)
- `poc/r2_phase_research/docs/R2_RESEARCH_FINAL.md` Section 15 (EVOLVE/CONTRADICT K1 Signal Delegation)
- `poc/r2_phase_research/docs/R2_EPISODIC_INTEGRATION_EPIC_PLAN.md` Milestone 7 / Epic 7.2

### Signal Detection Tiers

| Tier | Signals | Detector | Where |
| --- | --- | --- | --- |
| Tier 1 (Embedding) | REINFORCE, EXTEND, CREATE | K0 P03 cosine distance | R3 reconciliation |
| Tier 2 (Conversational) | EVOLVE, CONTRADICT | K1 LLM (Stage 3) | Memory Writer extraction |
| Tier 3 (Temporal) | PRUNE | K0 timer/decay | Retention policy |

### Fields Added to MemoryAtom (v2.2)

Five new optional fields on `MemoryAtom` carry correction metadata from K1 to K0:

| # | Field | Type | Default | Description |
| --- | --- | --- | --- | --- |
| 1 | `correction_signal` | bool | `false` | K1 LLM detected this atom corrects a previously stored fact. Flags atom as EVOLVE candidate for P03 R3 reconciliation. |
| 2 | `contradiction_signal` | bool | `false` | K1 LLM detected this atom contradicts stored knowledge with no clear resolution. Flags atom as CONTRADICT candidate. |
| 3 | `supersedes_concept` | string or null | `null` | Namespaced concept key being replaced. Format: `"domain:value"` (e.g. `"cuisine_preference:thai"`, `"school:riverdale"`, `"job:google"`). Gives P03 a targeted truth lookup key instead of brute-force embedding search. |
| 4 | `correction_source` | string or null | `null` | How the correction was detected. One of: `"user_explicit"` (user directly states change: "Actually, I prefer Thai now"), `"user_implicit"` (inferred from context shift: user orders Thai repeatedly), `"context_change"` (environmental change: "We moved to Portland"). |
| 5 | `session_context_id` | string or null | `null` | Session UUID where correction was detected. Enables P03 to build an audit trail for EVOLVE/CONTRADICT decisions. |

All fields have defaults, so v2.0/v2.1 atoms validate against v2.2 without changes.

### Signal Flow

```text
User says: "Actually, we prefer Thai food now, not Italian"
  |
  v
[K1 Stage 3: LLM Extraction]
  LLM detects correction in conversation context
  Produces MemoryAtom with:
    text: "Family now prefers Thai food"
    correction_signal: true
    supersedes_concept: "cuisine_preference:italian"
    correction_source: "user_explicit"
    session_context_id: "session-abc123"
  |
  v
[K1 Stage 4: Envelope Builder]
  Fields pass through as envelope body fields (no transformation)
  |
  v
[Bridge -> K0 Gate -> P02]
  P02 stores fields in st_hipp_events columns (passthrough)
  |
  v
[K0 P03 R3 Reconciliation]
  Reads correction_signal = true
  Routes directly to EVOLVE handler
  Uses supersedes_concept for targeted truth lookup
  Skips cosine-distance comparison entirely
```

### Detection Logic (Stage 3 LLM Responsibility)

The Writer Agent LLM prompt will include instructions to detect corrections:

1. **Explicit correction**: User directly contradicts prior knowledge ("Actually X is now Y", "I changed my mind about X", "That's not right, it's Y")
2. **Implicit correction**: User behavior implies a change (ordering Thai food 5 times after previously stating Italian preference)
3. **Context change**: Life event triggers knowledge update ("We moved to Portland", "I started a new job at Google")

The LLM sets `correction_signal: true` when it detects any of these patterns. It sets `contradiction_signal: true` when the user states something that conflicts with context but does not clearly resolve the conflict.

The LLM sets `supersedes_concept` using a `"domain:value"` key format. The domain is a category (cuisine_preference, school, job, home_city, etc.) and the value is the OLD fact being replaced. This gives P03 a precise lookup key.

### Invariant: No False Signal is Worse Than Missing One

- A **missed** correction signal (false negative) means P03 falls back to cosine distance, which already fails for EVOLVE. Result: the correction is stored as a new CREATE instead of an EVOLVE. This is the current behavior and acceptable as a degraded mode.
- A **false** correction signal (false positive) means P03 would incorrectly EVOLVE an existing truth. This is actively harmful.

Therefore: the LLM should err on the side of NOT flagging corrections. `confidence` on the atom already provides a secondary gate. P03 can ignore correction signals below a confidence threshold.

### Schema and Code Locations

| Artifact | Path | Change |
| --- | --- | --- |
| JSON Schema | `k1/contracts/schemas/memory_writer/memory_atom.v2.schema.json` | 5 fields added, version bumped to v2.2 |
| Python types | `k1/memory_writer/types.py` | 5 fields added to `MemoryAtom` dataclass |
| Architecture doc | `k1/memory_writer/memory_writer_architecture.md` | This section (35) |

### Downstream Dependencies (Not Yet Implemented)

These are tracked in R2 Epic Plan Milestones 7 and 9:

| Component | Required Change | Epic |
| --- | --- | --- |
| Writer Agent prompt | Add correction detection instructions | 7.2.1-7.2.3 |
| Envelope Builder stage | Pass through 5 new fields (no transform needed) | 7.2.4 |
| Bridge passthrough | No change needed (body is opaque JSON) | -- |
| K0 P02 st_hipp_events | Add 5 columns to migration | 7.2.0 |
| K0 P03 R3 reconciliation | Read correction_signal, route to EVOLVE/CONTRADICT | 9.x |

---

*This document is the single design reference for Memory Writer within the K1 Cognitive Kernel. All implementation must comply with the invariants, schemas, and flows described here. For the broader K1 architecture context, see `k1_cognitive_architecture_skeleton.mmd`. For the K0 receiving pipeline, see `docs/pipelines/P02_write_dossier.md`. For Bridge transport details, see `architecture_diagrams/bridge/bridge_architecture.mmd`. For v2 field definitions, see `docs/pipelines/p03/stage5_proposal_corrections.md`.*
