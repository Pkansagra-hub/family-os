# MemoryWriter V2 — From Session Summarizer to Cognitive Event Extractor

> **Status:** Architecture whiteboard — design phase.
> **Scope:** MemoryWriter evolution from per-session sentence extraction to cross-session structured cognitive event extraction.
> **Feeds:** K0 P02 Write/Ingest pipeline → K0 P03 Consolidation/Forgetting pipeline.
> **Predecessor:** Current MemoryWriter (V1) as analyzed 2026-06-21.

---

## 1. What MemoryWriter Is Today (V1)

```
Input:  20 turns of conversation from ONE session
Process: One LLM call with basic extraction persona
Output: 0-6 MemoryAtoms (37-field structured events)
Model:  Hardcoded gemini-2.5-flash (ignores LLM_PROVIDER)
Scope:  Single session. Zero awareness of other chats.
Quality: Flat 0.55 confidence. Raw text predominates.
K0:     Fire-and-forget via Bridge. No feedback loop.
```

### Current Architecture

```
turn.completed.v1 → SessionBatchDispatcher (20 turns / 300s idle)
  → MemoryWriterPipeline:
      Stage 1: FILTER (R1-R6 heuristic rules)
      Stage 2: CONTEXT (SS snapshot → ExtractionContext)
      Stage 3: EXTRACT (MemoryWriterAgent — single LLM call)
      Stage 4: ENVELOPE (EnvelopeBuilder → FieldMapper → PrivacyEnforcer)
      Stage 5: BATCH (DeltaAggregator 250ms → BatchEmitter)
  → Bridge → K0 P02 → st_hipp_events → P03 Consolidation
```

### Current MemoryAtom (37 fields)

The MemoryAtom schema is already rich. It carries:

- Core: text, topics, categories, activity_type (30 values)
- Participants: names, relationships, social context, intimacy
- Location: name, type (19 values), place_id, geohash, hierarchy, transitions
- Emotion: sentiment (5 labels), affect (VAD), emotion tags
- Temporal: orientation (4 values), temporal links (0-5, 6 link types)
- Cognitive: source_type, novelty (4 values), elaboration (5 values), identity domains (9 values)
- Narrative: thread_id, arc_position, is_goal_event
- Correction: correction_signal, contradiction_signal, supersedes_concept
- Meta: confidence, session_id, turn, language, conversation_anchor_ms

### What's Missing from V1

| Gap | Impact |
|-----|--------|
| No cross-session awareness | Each chat session produces independent atoms. "Riley math" across 4 chats produces 4 disconnected atom clusters. |
| No belief extraction mode | Extracts facts but doesn't distinguish "I am vegan" (durable belief) from "I had coffee" (episodic event). |
| No procedural extraction | Tool calls happen but patterns ("user dispatches calendar.create_event every Tuesday") are not extracted. |
| No entity context from prior sessions | Can't disambiguate "Ms. Chen" as "the math tutor from Chat #2" vs "the neighbor." |
| Hardcoded model | Uses gemini-2.5-flash regardless of LLM_PROVIDER env var. DeepSeek V4 Pro at 4000 tokens would produce dramatically better extraction. |
| No K0 feedback loop | Sends atoms, never learns which were useful, which were rejected, which were superseded. |
| Flat confidence | 0.55 across all extractions regardless of explicitness. "I am vegan" gets same confidence as "I might try that restaurant." |
| Context lacks narrative continuity | ExtractionContext has current narrative thread but no history of prior threads from other sessions. |

---

## 2. What MemoryWriter Needs to Become (V2)

```
MemoryWriter = "extract structured cognitive events that P03 can build a mind from"

Input:  20 turns from current session — self-sufficient, no K0 dependency.
Process: One LLM call with multi-type cognitive extraction persona.
Output:
  ├─ Episodic atoms (what happened, with temporal links)
  ├─ Belief atoms (what user believes, with contradiction flags)
  ├─ Procedural atoms (what user does repeatedly, tool-call patterns)
  └─ Entity atoms (who/what was mentioned, with disambiguation hints)

Model:  Follows LLM_PROVIDER → DEEPSEEK_MODEL env var resolution (same as front/classifier).
        DeepSeek V4 Pro, 4000 token budget, BACKGROUND priority.
Scope:  Current session. Self-sufficient — no K0 read dependency.
Quality: Calibrated confidence — 0.9 for explicit durable statements, 0.6 for implications,
         0.3 for ambient mood signals.
K0:     Receives atoms tagged with atom_type, belief_confidence, procedure_pattern.
        P03 gets structured cognitive events instead of raw text.

        FUTURE (Phase 5): When K0 recall drivers are ready, inject cross-session
        context (existing beliefs, entity links, topic continuity) from K0.
        This is a SEPARATE workstream — the K0→K1 read path (§3.7).
```

### Two Independent Workstreams

The design intentionally separates concerns:

| Workstream | Direction | What It Does | Depends On |
|-----------|-----------|-------------|------------|
| **Write Path** (§3.1–3.6) | K1 → K0 | MW extracts richer atoms, submits to K0 | Nothing new — Bridge, P02 exist today |
| **Read Path** (§3.7) | K0 → K1 | K0 recall drivers, cognitive relevance scoring | K0 driver development (WalDriver, FtsDriver exist; PgVector, KG, episodic, semantic need wiring) |

**The write path does NOT need the read path to deliver value.** MW can produce belief atoms, procedural atoms, and calibrated confidence using ONLY the current session's SS snapshot. Cross-session context injection is Phase 5 — wired only when the K0 read path is operational. No chicken-egg. No circular dependency.

---

## 3. Detailed V2 Design

### 3.1 Cross-Session Context Injection

**Current:** `ExtractionContext` is built from THIS session's SS snapshot only.

**V2:** Before LLM extraction, query K0 for:

| Query | Returns | Injects Into |
|-------|---------|-------------|
| Active beliefs for mentioned entities | List of `{entity, belief, confidence, session_id, age_days}` | `active_beliefs` section of extraction prompt |
| Topic continuity | "This topic was discussed in N prior chats, spanning M days. Last discussed: D days ago." | `topic_continuity` section |
| Entity disambiguation | "Ms. Chen = math tutor (from Chat #2, 3 weeks ago). Also: Ms. Chen = neighbor (from Chat #5, 1 week ago). Current context suggests: math tutor (0.85 confidence)." | `entity_context` section |
| Contradiction candidates | "Existing belief: 'Riley is struggling with math' (Feb). New statement suggests improvement. Flag as potential EVOLVE." | `contradiction_candidates` section |

**New fields on `ExtractionContext`:**

```python
active_beliefs: List[BeliefAnchor]      # beliefs from prior sessions about entities in this chat
topic_continuity: Optional[TopicHistory]  # cross-session topic tracking
entity_context: Dict[str, EntityLink]     # disambiguated entities with KG links
contradiction_candidates: List[ContradictionCandidate]  # potential belief contradictions
```

### 3.2 Multi-Type Extraction

**Current:** All extractions are `MemoryAtom`. No type differentiation.

**V2:** The LLM prompt distinguishes four extraction modes:

| Atom Type | When to Extract | Key Fields | Feeds P03 Stage |
|-----------|----------------|------------|-----------------|
| **Episodic** (`atom_type: "episodic"`) | Events, conversations, experiences | temporal_links, location, participants, narrative | R2 Clustering, R1 Replay |
| **Belief** (`atom_type: "belief"`) | Durable user beliefs, preferences, facts about self/world | supersedes_concept, contradiction_signal, belief_confidence (separate from atom confidence) | R7 TruthWriter (REINFORCE/EVOLVE/CONTRADICT) |
| **Procedural** (`atom_type: "procedural"`) | Repeated tool calls, habits, routines | procedure_pattern (daily/weekly/monthly), tool_name, tool_args_pattern | R2 Pattern Extraction, st_procedural |
| **Entity** (`atom_type: "entity"`) | New people, places, organizations mentioned | entity_type (PERSON/LOCATION/ORG), disambiguation_hints, relationship_to_speaker | R4 KG Consolidation |

**New fields on `MemoryAtom`:**

```python
atom_type: AtomType  # EPISODIC | BELIEF | PROCEDURAL | ENTITY
belief_confidence: Optional[float]  # separate from atom.confidence — how durable is this belief?
procedure_pattern: Optional[ProcedurePattern]  # {frequency, tool_name, args_template}
entity_type: Optional[EntityType]  # PERSON | LOCATION | ORGANIZATION | CONCEPT
entity_disambiguation: Optional[str]  # "Ms. Chen = math tutor, NOT neighbor"
cross_session_links: List[CrossSessionLink]  # [{target_session_id, target_atom_id, relation}]
```

### 3.3 Model Selection

**Current:** `model_hint` is hardcoded to `"gemini-2.5-flash"` in `MWConfig`.

**V2:** Follow the same env var resolution as front/classifier:

```python
# In MemoryWriterFactory.create() or MemoryWriterService.__init__()
_provider = os.environ.get("LLM_PROVIDER", "")
_model = os.environ.get("DEEPSEEK_MODEL") or os.environ.get("VERTEX_MODEL") or ""

if _provider and _model:
    config.model_hint = _model
    config.provider_preference = _provider
```

**Token budget increase:** 2000 → 4000 for single-turn, 4000 → 8000 for session-batch. DeepSeek V4 Pro at 8K tokens produces dramatically richer extraction than gemini-flash at 2K.

### 3.4 Calibrated Confidence

**Current:** LLM assigns 0.55 flat across everything.

**V2:** Extraction persona instructs:

| Confidence | When |
|-----------|------|
| 0.9-1.0 | Explicit durable statements: "I am vegan", "We moved to Austin", "Riley's birthday is June 12" |
| 0.7-0.8 | Strongly implied: "I've been vegan for 10 years so..." → implies durable belief about being vegan |
| 0.5-0.6 | Moderate signal: "I think I prefer morning meetings" → preference, but not definitively stated |
| 0.3-0.4 | Weak signal: "I'm tired today" → ambient state, not durable |
| 0.1-0.2 | Speculative: "Maybe I should start running" → intention, not commitment |

The persona prompt explicitly maps confidence to statement types. The downstream `ExtractionValidator` enforces `confidence_floor` per atom type: 0.5 for beliefs, 0.3 for episodic, 0.2 for entities.

### 3.5 K0 Feedback Loop

**Current:** Fire-and-forget. No knowledge of what happened to atoms after submission.

**V2:** K0 P03 emits structured feedback to MW:

| Feedback Signal | Source | What MW Does |
|----------------|--------|-------------|
| `atom_rejected` | P02 Gate or P03 validation | Log, adjust extraction thresholds if rejection rate > 20% |
| `atom_superseded` | P03 R3 dedup or R7 EVOLVE | Log, reduce confidence on similar future extractions |
| `atom_useful` | P03 R1 importance scoring (top 20% of scored atoms) | Boost confidence on similar extraction patterns |
| `belief_contradicted` | P03 R7 CONTRADICT decision | Flag in next extraction: "previous belief X was contradicted — check for corrections" |
| `entity_merged` | P03 R4 disambiguation | Update entity context for future extractions |

**Implementation:** K0 P03 emits `p03.atom.feedback.v1` SSE events. MW listens via its existing `IEventSubscriptionPort`. Feedback is lightweight — just `{atom_id, decision, reason}`.

### 3.6 Prompt Enhancements

The current `memory_writer_persona.md` is solid on cultural awareness and cognitive dimensions. V2 adds:

**New sections in system prompt:**

1. **Cross-Session Awareness Block:**

   ```
   You are processing Chat #{chat_number} in a series. The user has discussed
   "{topic}" in {prior_chat_count} prior chats spanning {date_range}.
   Last discussed: {last_discussed_date}.
   ```

2. **Existing Beliefs Block:**

   ```
   EXISTING BELIEFS (from prior sessions — do NOT re-extract these):
   - "Riley is struggling with math" (confidence: 0.85, last updated: Feb 2026)
   - "Ms. Chen is Riley's math tutor, Tuesdays at 4pm" (confidence: 0.90, Mar 2026)

   If the current conversation confirms, contradicts, or evolves any of these,
   flag with correction_signal/contradiction_signal/supersedes_concept.
   ```

3. **Entity Disambiguation Block:**

   ```
   KNOWN ENTITIES in this context:
   - "Ms. Chen" → math tutor (entity_id: person_ms_chen_tutor)
   - "Riley" → daughter (entity_id: person_riley)
   - "Riverside Park" → soccer practice location (entity_id: place_riverside_park)

   Use these entity_ids in participants/location fields.
   If a new entity is introduced, extract it as atom_type: "entity".
   ```

4. **Procedural Pattern Extraction Block:**

   ```
   PROCEDURAL EXTRACTION:
   The conversation history includes tool calls made by the assistant.
   If the user repeatedly requests the same action (e.g., "schedule Riley's soccer"
   appearing every Tuesday), extract a procedural atom:

   {
     "atom_type": "procedural",
     "text": "User schedules Riley's soccer practice every Tuesday evening",
     "procedure_pattern": {
       "frequency": "weekly",
       "tool_name": "calendar.create_event",
       "args_template": {"title": "Riley Soccer", "day": "Tuesday", "time": "5pm"}
     }
   }
   ```

5. **Confidence Calibration Block** (see §3.4 above)

---

## 4. Architecture Changes

### 4.1 New Files

| File | Purpose |
|------|---------|
| `k1/memory_writer/context/k0_context_provider.py` | `K0ContextProvider` — queries K0 for cross-session beliefs, entities, topic history |
| `k1/memory_writer/feedback/feedback_handler.py` | `FeedbackHandler` — consumes `p03.atom.feedback.v1` SSE, adjusts MW thresholds |
| `k1/memory_writer/docs/memory_writer_v2.md` | This document |

### 4.2 Modified Files

| File | Change |
|------|--------|
| `k1/memory_writer/extraction/writer_agent.py` | `MemoryWriterAgent` — new extraction modes (belief, procedural, entity), cross-session context in prompt |
| `k1/memory_writer/extraction/prompts/memory_writer_persona.md` | Add cross-session awareness, existing beliefs, entity context, procedural extraction, confidence calibration blocks |
| `k1/memory_writer/context/context_builder.py` | `ContextBuilder.build()` — new fields: active_beliefs, topic_continuity, entity_context, contradiction_candidates |
| `k1/memory_writer/types.py` | New types: `AtomType`, `BeliefAnchor`, `TopicHistory`, `EntityLink`, `ContradictionCandidate`, `CrossSessionLink`, `ProcedurePattern`, `EntityType`, `AtomFeedback` |
| `k1/memory_writer/envelope/field_mapper.py` | `FieldMapper.map_atom_to_body()` — map new atom_type, belief_confidence, procedure_pattern, entity fields to K0 body |
| `k1/memory_writer/config.py` | `MWConfig` — add `provider_preference`, increase `llm_token_budget` default to 4000, `llm_token_budget_session` to 8000 |
| `k1/memory_writer/factory.py` | `MemoryWriterFactory.create()` — resolve model from env vars, wire K0ContextProvider |
| `k1/memory_writer/ports/` | `IK0ContextPort` Protocol — query cross-session context from K0 |
| `k1/memory_writer/adapters/` | `K0ContextAdapter` — implements `IK0ContextPort` via Bridge recall |

### 4.3 K0 Contract Changes

| Contract | Change |
|----------|--------|
| `memory.write.v1` | Body schema extended with `atom_type`, `belief_confidence`, `procedure_pattern`, `entity_type`, `cross_session_links` |
| `p03.atom.feedback.v1` | NEW contract — P03 emits atom quality feedback to K1 |
| `recall.request.v1` | Already supports entity/topic queries — used by `K0ContextProvider` for cross-session context |

---

## 5. Token Economics

| Scenario | V1 (Current) | V2 (Target) |
|----------|-------------|-------------|
| Per-turn extraction | 2000 tokens (gemini-flash) | 4000 tokens (DeepSeek V4 Pro) |
| Session-batch (20 turns) | 4000 tokens | 8000 tokens |
| Cross-session context query | N/A | ~500 tokens (belief recall from K0) |
| Feedback processing | N/A | < 100 tokens (SSE event, no LLM) |
| Daily cost (50 turns/day) | ~$0.003 (gemini-flash) | ~$0.03 (DeepSeek V4 Pro) |

The 10x cost increase is justified by the quality delta: structured cognitive events instead of raw sentences, belief tracking instead of flat facts, procedural patterns instead of ignored tool calls.

---

## 6. Migration Path

### Workstream A: Write Path Strengthening (K1 → K0)

Independent. No K0 read dependency. Delivers value immediately.

**Phase A1: Model + Confidence (1-2 days)**

- Wire `LLM_PROVIDER` / `DEEPSEEK_MODEL` env var resolution
- Add confidence calibration block to persona prompt
- Increase token budget: 2000 → 4000
- **Risk:** Low. Backward compatible.

**Phase A2: Multi-Type Extraction (3-4 days)**

- Add `atom_type` field (episodic/belief/procedural/entity)
- Add belief, procedural, entity extraction modes to persona
- Update FieldMapper for new atom types
- **Risk:** Medium. P03 must handle new atom types (P03 R7 TruthWriter already routes by type).

**Phase A3: Extraction Quality (2-3 days)**

- Cross-reference contradictions within session ("turn 3 contradicts turn 7")
- Tool-call pattern detection from `tool_calls_per_turn` in ExtractionContext
- Entity disambiguation within session ("Ms. Chen" = math tutor, not neighbor)
- **Risk:** Low. All data is in current session SS snapshot.

### Workstream B: Read Path Development (K0 → K1)

Independent. No MW dependency. Activated memory layers benefit all K1 consumers.

**Phase B1: Driver Wiring (3-5 days)**

- Wire `PgVectorDriver` for `st_vec` (semantic search)
- Wire `EpisodicDriver` for `st_epi` (128 episodes, real data)
- Wire `SemanticDriver` for `st_sem` (patterns)
- Wire `KGDriver` for `st_kg_dom` + `st_kg_edges`
- **Risk:** Low. Tables exist, data exists, explore script proves queries work.

**Phase B2: Cognitive Relevance Scoring (5-7 days)**

- Replace flat FTS scoring with multi-factor relevance
- Narrative context, emotional state, temporal proximity, entity salience
- Cross-layer merging (st_epi + st_sem + st_kg + st_social → enriched hits)
- **Risk:** High. Requires new relevance model. No prior art in codebase.

**Phase B3: Recall Contract V2 (3-4 days)**

- Extend `RecallRequestV1` with `cognitive_context` (affect, narrative, temporal, spatial, recent turns)
- K0 QueryAggregator uses context for scoring
- Response includes `source_layer` per hit, enabling the LLM to distinguish episodic from semantic
- **Risk:** Medium. Contract change affects all recall consumers.

### Workstream C: Cross-Session Integration (Depends on A + B)

Only when both workstreams are complete.

**Phase C1: Context Injection (2-3 days)**

- `K0ContextProvider` queries K0 recall for existing beliefs, entities, topic continuity
- Inject into MW extraction prompt as context block
- **Risk:** Low. Both paths functional. Just wiring them together.

**Phase C2: Feedback Loop (2-3 days)**

- Define `p03.atom.feedback.v1` contract
- `FeedbackHandler` consumes K0 P03 feedback, adjusts MW thresholds
- **Risk:** Medium. Requires P03 to emit feedback events (R8 GapDetector extends naturally).

---

## 7. Open Questions

| # | Question | Status |
|---|---|---|
| 1 | Should cross-session context query happen per-batch or be cached? | **Open** — Cached per session with TTL refresh would reduce K0 load. |
| 2 | Should belief extraction also propose mutations to K1 SessionState (like section update)? | **Open** — Would create a second writer to `beliefs_active`. Currently only section update writes. Coordination needed. |
| 3 | Should procedural extraction use a separate LLM call or be folded into the main extraction? | **Open** — Tool-call patterns span multiple turns, might need session-level (not batch-level) analysis. |
| 4 | What's the atomicity guarantee for cross-session links? | **Open** — If atom A in batch 1 links to atom B in batch 2, but batch 2 hasn't been extracted yet, the link is dangling. |
| 5 | Should entity disambiguation be LLM-driven or query K0 KG? | **Open** — K0 KG already has entities (st_kg_dom) and relationships (st_kg_edges). Querying KG is faster and more consistent than LLM disambiguation. |

---

## 8. Decision Log

| Date | Decision | Rationale |
|------|----------|-----------|
| 2026-06-21 | MemoryWriter stays in K1, consolidation stays in K0 P03 | K0 P03 already owns cross-session consolidation (HDBSCAN, decay, KG, 8 memory layers). MW's role is to feed P03 richer atoms, not duplicate consolidation. |
| 2026-06-21 | Cross-session context comes from K0 recall queries, not MW internal state | MW is per-session. K0 is cross-session. Query K0 for what exists, don't maintain duplicate state in MW. |
| 2026-06-21 | atom_type field added to MemoryAtom | Distinguishes episodic/belief/procedural/entity at extraction time. P03 routes differently by type. |
| 2026-06-21 | Confidence calibrated per statement type, not flat 0.55 | Explicit durable statements ("I am vegan") get 0.9. Ambient mood ("I'm tired") gets 0.3. Prevents noise from saturating P03. |
| 2026-06-21 | Model follows LLM_PROVIDER env var | Same resolution logic as front actor and section update classifier. DeepSeek V4 Pro at 8K tokens >> gemini-flash at 2K tokens for memory extraction quality. |
