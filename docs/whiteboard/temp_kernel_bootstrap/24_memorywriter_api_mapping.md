# MemoryWriter — Formal API Mapping

> Generated: 2026-04-14 · Scope: Inputs, Outputs, Processing for every MemoryWriter boundary

---

## 1. Entry Points (What Goes IN)

### 1.1 Primary Trigger — `turn.complete.v1` Event

MemoryWriter is a **background L4 agent** — it has NO synchronous API. It activates on a bus event.

| Topic | Payload | Publisher | Effect |
| --- | --- | --- | --- |
| `turn.complete.v1` | `TurnCompletePayload` | Concierge (after each conversation turn) | `TurnDispatcher._on_turn_complete()` → `MemoryWriterPipeline.process()` |

**TurnCompletePayload** (frozen):

| Field | Type | Default | Source |
| --- | --- | --- | --- |
| `turn_id` | `str` | — | Concierge |
| `session_id` | `str` | — | Concierge |
| `cognitive_trace_id` | `str` | — | Distributed trace |
| `user_message` | `str` | — | User input |
| `assistant_response` | `str` | — | LLM response |
| `timestamp_ms` | `int` | — | Turn creation time |
| `turn_number` | `int` | — | Sequential turn counter |
| `mentioned_time_raw` | `str` | `""` | GAP-002: Concierge temporal parse |
| `mentioned_time_resolved_ms` | `int` | `0` | Resolved epoch |
| `mentioned_time_confidence` | `float` | `0.0` | Parse confidence |
| `mentioned_time_is_relative` | `bool` | `True` | "yesterday" vs "Jan 5" |
| `mentioned_location_raw` | `str` | `""` | Location text |
| `mentioned_location_type` | `str` | `""` | LocationType string |
| `mentioned_location_entity_id` | `str` | `""` | Entity reference |
| `mentioned_location_confidence` | `float` | `0.0` | Parse confidence |

### 1.2 SessionState Read — ISessionReadPort

| Method | Input | Output | Invariant |
| --- | --- | --- | --- |
| `snapshot(sections)` | `List[str]` | `Dict[str, Any]` | MW-01 (read-only), MW-02 (<1ms P99) |
| `read_section(name)` | `str` | `Optional[Dict[str, Any]]` | — |
| `list_sections()` | — | `FrozenSet[str]` | Dynamic discovery |
| `snapshot_all(exclude)` | `FrozenSet[str]` | `Dict[str, Any]` | Section-agnostic |

**Sections read** (13 of 15, minus `skip_sections`):

| Section | Used By | Purpose |
| --- | --- | --- |
| `history_active` | `ContextBuilder._extract_history()` | Recent turns, tool calls |
| `beliefs_active` | `ContextBuilder._extract_persons()` + `context_assembly` | Mentioned entities (PERSON), temporal/spatial fallback |
| `affective_now` | `ContextBuilder._extract_affect()` | Current emotion for affect tagging |
| `affective_baseline` | `ContextBuilder` | Baseline emotion (phantom section) |
| `scoreboard` | `ContextBuilder._extract_topics()` | Active topics + salience |
| `task_state` | `ContextBuilder` | Active goals |
| `control` | `ContextBuilder` | Safety band (GREEN/AMBER/RED) |
| `persona` | `ContextBuilder` | Persona aliases for PersonResolver |
| `ifl` | `ContextBuilder` | Device context (phantom section) |
| `narrative_active` | `ContextBuilder` | Active narrative arcs |
| `meta` | `ContextBuilder` | Session ID fallback |

**Skipped sections** (default): `telemetry`, `artifacts_warm`

**Production adapter**: `SessionReadAdapter` — wraps `SessionStateManager`, calls `get_section()` → `to_dict()`. Handles phantom sections (KeyError → None).

### 1.3 LLM Calls — IModelHubPort (MW-specific)

| Method | Input | Output | Invariant |
| --- | --- | --- | --- |
| `chat(messages, budget_tokens, model_hint)` | `List[Dict[str, str]]`, `int`, `str` | `ChatResponse` | MW-06 (2000 token budget) |

**ChatResponse** (frozen):

| Field | Type | Default |
| --- | --- | --- |
| `content` | `str` | `""` |
| `total_tokens` | `int` | `0` |
| `prompt_tokens` | `int` | `0` |
| `completion_tokens` | `int` | `0` |
| `model` | `str` | `""` |
| `latency_ms` | `float` | `0.0` |

**Production adapter**: `ModelHubAdapter` — anti-corruption layer translating `chat()` → `execute(HubRequest)`:

- Messages: `Dict[str, str]` → K1 `Message(role, content)`
- System prompt extraction from first message if `role == "system"`
- Builds `HubRequest(capability=CHAT, payload=ChatPayload, constraints=RequestConstraints(max_tokens=budget, timeout_ms=60000, priority=BACKGROUND, temperature=0.7))`
- `consumer_id = "memory_writer"`
- `provider_preference = model_hint` unless `"cheapest"` (then None)

---

## 2. Exit Points (What Goes OUT)

### 2.1 K0 Bridge Commands — IBridgeCommandPort

The **ONLY** output path to K0 storage (MW-03).

| Method | Input | Output | Target |
| --- | --- | --- | --- |
| `submit(topic, schema_uri, body)` | `str`, `str`, `dict` | — | Bridge → K0 P02 pipeline |
| `submit_batch(envelopes)` | `List[dict]` | — | Bridge → K0 P02 pipeline |

Each envelope contains:

- `topic`: `"memory.delta"`
- `schema_uri`: `"schema://memory.delta"`
- `body`: 34+ field memory atom dict (see §4.1)
- `headers`: `cognitive_trace_id`, `tenant_id`, `space_id`, `actor`, `device_id`, `band`

**Production adapter**: `BridgeCommandAdapter` — wraps Bridge's `KernelCommandPort.submit_command()` / `submit_command_batch()`. Extracts `trace_id` from body (MW-10).

### 2.2 Event Emissions — IEventSubscriptionPort

5 observability topics produced:

| Topic | Payload | When |
| --- | --- | --- |
| `k1.mw.filter.decision.v1` | `FilterDecisionEvent` (turn_id, decision=PASS/SKIP, skip_reason, latency_ms) | After Stage 1 |
| `k1.mw.extraction.complete.v1` | `ExtractionCompleteEvent` (turn_id, atom_count, total_tokens, latency_ms) | After Stage 3 |
| `k1.mw.batch.submitted.v1` | `BatchSubmittedEvent` (batch_id, envelope_count, bridge_latency_ms) | After Stage 5 |
| `k1.mw.pipeline.error.v1` | `PipelineErrorEvent` (turn_id, stage, error_type, message) | On any stage error |
| `k1.mw.circuit.open.v1` | `CircuitOpenEvent` (failure_count, recovery_probe_at) | LLM circuit trips |

**Production adapter**: `EventSubscriptionAdapter` — wraps `FabricBusAdapter`. Subscribe wraps async handler in sync wrapper via `asyncio.create_task()`.

### 2.3 Health Reports — IHealthPort

| Method | Input | Output |
| --- | --- | --- |
| `is_ready()` | — | `bool` (started AND NOT circuit_open) |
| `health_check()` | — | `HealthStatus` |

**HealthStatus** (frozen):

| Field | Type | Default |
| --- | --- | --- |
| `is_healthy` | `bool` | — |
| `llm_circuit_open` | `bool` | `False` |
| `pending_batch_count` | `int` | `0` |
| `last_extraction_ms` | `float` | `0.0` |
| `detail` | `str` | `""` |

**Production adapter**: `HealthAdapter` — composes CircuitBreaker state + pipeline state callables.

---

## 3. Processing Pipeline — 5 Stages

```text
turn.complete.v1 event arrives
  → TurnDispatcher._on_turn_complete(raw_payload)
    → Deserialize → TurnCompletePayload
    → Dedup check (_processed_ids set)
    → Backpressure (max 1 concurrent + 1 queued, newest-wins)
    → pipeline.process(payload)

Stage 1: RELEVANCE FILTER (rule-based, no LLM — MW-07)
  → RelevanceFilter.evaluate(user_message, assistant_response, entities, topics, turn_id, timestamp_ms, turn_metadata)
  → Rule evaluation order (cheapest-first):
    R6: Tool Call Boost → auto-PASS if tool_calls present
    R4: Empty → SKIP if <5 words, no entities, matches trivial pattern
    R5: Continuation → SKIP if matches continuation phrase, ≤10 words, no entities
    R1: Clarification → SKIP if user clarifies + assistant repairs + no entities
    R2: System Meta → SKIP if system/meta question + no entities
    R3: Duplicate → SKIP if SHA-256(participants+topics) within 300s dedup window
  → FilterDecision(passed, skip_reason, turn_id, latency_ms)
  → If SKIP: publish k1.mw.filter.decision.v1, return PipelineResult(skipped=True)

Stage 2: CONTEXT ASSEMBLY (SessionState read — MW-01, MW-02)
  → MWSessionReader.read_snapshot() — reads all sections minus skip_sections
    → assert_mw02_read_latency() — must be <1ms P99
  → ContextBuilder.build(snapshot, payload) → ExtractionContext
    → Extracts: history (recent turns + tool calls), persons, affect, topics/salience,
      goals, control (safety band), persona, device context, narrative,
      temporal/spatial (payload-first, SS-fallback — fixes race condition T7)

Stage 3: LLM EXTRACTION (circuit-breaker protected)
  → Circuit breaker check (is_open? → skip with error)
  → MemoryWriterAgent.extract(context, trace_id)
    → assert_mw06_token_budget(budget) — max 2000 tokens
    → Build system prompt (memory_writer_persona.md)
    → Build user prompt (serialized ExtractionContext — last 5 turns, text[:100])
    → IModelHubPort.chat(messages, budget=2000, model_hint="cheapest")
    → Parse JSON response → List[RawExtraction] (hard cap 6 — MW-05)
    → On failure: circuit_breaker.record_failure(), return []
    → On success: circuit_breaker.record_success()
  → ExtractionValidator.validate(extractions, context) → List[MemoryAtom]
    → Check 1: MW-04 text truncation (≤50 words)
    → Check 2: Drop if text empty or topics empty
    → Check 3: PersonResolver.resolve_all() → person_ids (4-step cascade)
    → Check 4: Drop below confidence_floor (0.30)
    → Check 5: MW-12 temporal_links (max 5 per atom, valid link_types only)
    → Post-loop cap: MW-05 (max 6 atoms total)
  → Publish k1.mw.extraction.complete.v1

Stage 4: ENVELOPE BUILD + PRIVACY
  → EnvelopeBuilder.build(atoms, context, trace_id)
    → assert_mw10_trace_id(trace_id) — every envelope must carry trace_id
    → FieldMapper.map_atom_to_body(atom, context, trace_id) → 34+ field dict
      → Direct fields: text, topics, categories, activity_type, participants, etc.
      → Derived fields (K0 gap-fill): G1 sentiment_score, G2 dominant_emotion,
        G3 dominant_emotions_json, G4 affect_valence, G5 geohash_6, G6 place_id,
        G8 num_participants
      → PlaceResolver.resolve_with_geohash() → (place_id, geohash_6)
    → Headers: cognitive_trace_id, tenant_id, space_id, topic, schema_uri, actor, device_id, band
  → PrivacyEnforcer.enforce(body, band)
    → GREEN: pass-through
    → AMBER: generalize location_name → category label (18 mappings)
    → RED: strip all location fields, mask participants to person_redacted_{i}
    → Unknown band → RED (fail-secure)

Stage 5: BATCH + SUBMIT
  → DeltaAggregator.add(envelope) — dedup by SHA-256(participants+topics)[:16]
  → DeltaAggregator.flush() — sort by (conversation_turn, extraction_sequence)
  → BatchEmitter.emit(batch) → IBridgeCommandPort.submit_batch(envelopes)
    → Bridge → K0 P02 Episodic Pipeline
  → Publish k1.mw.batch.submitted.v1

Pipeline errors at ANY stage:
  → Caught, logged, publish k1.mw.pipeline.error.v1
  → Return PipelineResult(error=stage_name)
  → Pipeline NEVER raises
```

---

## 4. Type System

### 4.1 MemoryAtom — 37+ Field Core Domain Object

**MemoryAtom** (frozen):

| Field | Type | Default |
| --- | --- | --- |
| `schema_version` | `str` | `"2.0"` |
| `operation` | `str` | `"UPSERT"` |
| `text` | `str` | `""` |
| `topics` | `List[str]` | `[]` |
| `categories` | `List[str]` | `[]` |
| `activity_type` | `Optional[ActivityType]` | `None` |
| `participants` | `List[str]` | `[]` |
| `participant_relationships` | `Dict[str, ParticipantRelationship]` | `{}` |
| `social_context` | `Optional[SocialContext]` | `None` |
| `social_intimacy` | `Optional[SocialIntimacy]` | `None` |
| `location_name` | `Optional[str]` | `None` |
| `location_type` | `Optional[LocationType]` | `None` |
| `place_id` | `Optional[str]` | `None` |
| `location_hierarchy` | `tuple` | `()` |
| `transition_from_place` | `Optional[str]` | `None` |
| `transition_mode` | `Optional[str]` | `None` |
| `sentiment_label` | `SentimentLabel` | `NEUTRAL` |
| `emotion_tags` | `List[str]` | `[]` |
| `affect` | `Affect` | `Affect(0.0, 0.0, 0.5)` |
| `entity_salience` | `Dict[str, float]` | `{}` |
| `narrative` | `Optional[Narrative]` | `None` |
| `temporal` | `Optional[Temporal]` | `None` |
| `temporal_links` | `tuple` | `()` |
| `intent_type` | `Optional[IntentType]` | `None` |
| `goal_context` | `Optional[str]` | `None` |
| `task_context` | `Optional[str]` | `None` |
| `source_type` | `SourceType` | `USER_STATED` |
| `novelty` | `NoveltyLevel` | `EXPECTED` |
| `elaboration_depth` | `ElaborationDepth` | `MENTION` |
| `identity_domains` | `List[str]` | `[]` |
| `temporal_orientation` | `TemporalOrientation` | `PAST` |
| `conversation_anchor_ms` | `int` | `0` |
| `correction_signal` | `bool` | `False` |
| `contradiction_signal` | `bool` | `False` |
| `supersedes_concept` | `Optional[str]` | `None` |
| `correction_source` | `Optional[str]` | `None` |
| `session_context_id` | `Optional[str]` | `None` |
| `confidence` | `float` | `0.0` |
| `session_id` | `str` | `""` |
| `conversation_turn` | `int` | `0` |
| `extraction_sequence` | `int` | `0` |
| `language` | `str` | `"en"` |

### 4.2 Enums (16)

| Enum | Values Count | Key Values |
| --- | --- | --- |
| `SentimentLabel` | 5 | VERY_NEGATIVE → VERY_POSITIVE |
| `NoveltyLevel` | 4 | ROUTINE, EXPECTED, NOVEL, SURPRISING |
| `ElaborationDepth` | 5 | MENTION → REFLECTED |
| `TemporalOrientation` | 4 | PAST, ONGOING, FUTURE_COMMITMENT, HABITUAL |
| `TemporalLinkType` | 6 | RETROSPECTIVE, PROSPECTIVE, CONCURRENT, HABITUAL, CONTEXTUAL, CONDITIONAL |
| `SourceType` | 4 | USER_STATED, USER_IMPLIED, DEVICE_OBSERVED, SYSTEM_INFERRED |
| `ArcPosition` | 4 | EXPOSITION, RISING_ACTION, CLIMAX, RESOLUTION |
| `SocialIntimacy` | 3 | LOW, MEDIUM, HIGH |
| `ActivityType` | 30 | MEAL through CONFLICT |
| `RelationshipType` | 8 | PARENT_OF through OTHER |
| `LocationType` | 19 | HOME through SOCIAL_VENUE |
| `IdentityDomain` | 9 | PARENT through SPIRITUAL_SELF |
| `SkipReason` | 6 | CLARIFICATION, SYSTEM_TURN, DUPLICATE, EMPTY, TRIVIAL, STALE |
| `IntentType` | 8 | LOG_MEMORY through OTHER |
| `SocialContext` | 6 | SOLO through COMMUNITY |
| `CircuitBreakerState` | 3 | CLOSED, OPEN, HALF_OPEN |

### 4.3 Nested Value Objects (frozen)

| Type | Fields |
| --- | --- |
| `Affect` | `valence: float` (-1→+1), `arousal: float` (0→1), `dominance: float` (0→1) |
| `ParticipantRelationship` | `type: RelationshipType`, `target: str`, `confidence: float` |
| `Narrative` | `thread_id: str`, `arc_position: ArcPosition`, `is_goal_event: bool` |
| `Temporal` | `mentioned_time: str`, `resolved_epoch_ms: int`, `is_backdated: bool` |
| `TemporalLink` | `mentioned_time: str`, `resolved_epoch_ms: int` (0), `uncertainty_window_ms: int` (0), `link_type: str` ("CONCURRENT"), `confidence: float` (1.0) |

### 4.4 Pipeline Types

| Type | Fields |
| --- | --- |
| `CompressedTurn` | `turn_id`, `role`, `text`, `timestamp_ms`, `turn_number` |
| `ExtractionContext` | 25 fields: current_turn, recent_turns, active_persons, affect (current + baseline), narrative, topics/salience, goals, control/device/persona context, session_id, conversation_turn, temporal/spatial fields (8), tool_calls_per_turn |
| `FilterDecision` | `passed: bool`, `skip_reason: Optional[SkipReason]`, `turn_id: str`, `latency_ms: float` |
| `RawExtraction` | 30 fields (mutable, NOT frozen) — LLM output before validation |
| `PersonResolution` | `natural_name: str`, `person_id: str`, `confidence: float`, `is_provisional: bool` |
| `MWEnvelope` | `topic: str`, `schema_uri: str`, `trace_id: str`, `atom: MemoryAtom` |
| `PipelineResult` | `skipped: bool`, `skip_reason: str`, `atoms_extracted: int`, `envelopes_submitted: int`, `llm_tokens_used: int`, `llm_latency_ms: float`, `trace_id: str`, `error: Optional[str]` |

### 4.5 Error Types

| Exception | Parent | Fields |
| --- | --- | --- |
| `InvariantViolation` | `Exception` | `invariant_id: str`, `message: str` |

---

## 5. Services (Internal Pipeline Components)

### 5.1 TurnDispatcher — Event-Driven Entry

| Aspect | Detail |
| --- | --- |
| Topic | `turn.complete.v1` |
| Dedup | In-memory `_processed_ids` set (at-most-once) |
| Backpressure | Max 1 concurrent + 1 queued payload (newest-wins) |
| Deserialization | Raw dict → `TurnCompletePayload` with safe defaults |

### 5.2 RelevanceFilter — Stage 1

Rule-based, zero LLM dependencies (MW-07). Cheapest-first evaluation.

| Rule | Pattern | Decision |
| --- | --- | --- |
| R6 | Tool calls present in turn_metadata | auto-PASS |
| R4 | <5 words, no entities, trivial pattern (21 phrases) | SKIP(EMPTY) |
| R5 | Continuation phrase (13 phrases), ≤10 words, no entities | SKIP(TRIVIAL) |
| R1 | User clarification (6 regexes) + assistant repair (4 regexes) + no entities | SKIP(CLARIFICATION) |
| R2 | System/meta question (5 regexes) + no entities | SKIP(SYSTEM_TURN) |
| R3 | SHA-256 content hash within 300s dedup window (ring buffer capacity=100) | SKIP(DUPLICATE) |

### 5.3 ContextBuilder — Stage 2

Assembles `ExtractionContext` from 13 SessionState sections + `TurnCompletePayload`.

Key temporal/spatial resolution: **payload-first, SessionState-fallback** pattern (fixes race condition T7 where Concierge clears SS temporal fields before MW reads).

### 5.4 MemoryWriterAgent — Stage 3 (LLM)

| Aspect | Detail |
| --- | --- |
| System prompt | `memory_writer_persona.md` — loaded once at construction |
| User prompt | Serialized ExtractionContext (last 5 turns, text[:100]) |
| Token budget | 2000 (MW-06) |
| Model hint | `"cheapest"` (default from MWConfig) |
| Parse | JSON response → `List[RawExtraction]` (strip markdown fences) |
| Hard cap | 6 extractions per response (MW-05) |
| Temporal links | 5 per atom (MW-12) |
| Error handling | Never raises — returns `[]` |

### 5.5 ExtractionValidator — Post-Extraction

5-check validation pipeline converting `RawExtraction` → `MemoryAtom`:

1. MW-04: Truncate text to 50 words
2. Drop if text empty or topics empty
3. PersonResolver 4-step cascade (exact → alias → partial → provisional)
4. Drop below confidence floor (0.30)
5. MW-12: Temporal links capped at 5, valid link_types only
6. MW-05: Post-loop cap at 6 atoms total

### 5.6 EnvelopeBuilder + FieldMapper — Stage 4

Converts `MemoryAtom` → K0 command envelope dict with 34 direct fields + 7 derived gap-fill fields (G1–G8).

### 5.7 PrivacyEnforcer — Stage 4 (post-build)

| Band | Action |
| --- | --- |
| GREEN | Pass-through |
| AMBER | Generalize location_name → category label (18 mappings) |
| RED | Strip all location fields, mask participants to `person_redacted_{i}` |
| Unknown | RED (fail-secure) |

### 5.8 DeltaAggregator — Stage 5

250ms time-window batching. Dedup by `SHA-256(sorted(participants)+":"+sorted(topics))[:16]`. Sort by `(conversation_turn, extraction_sequence)` on flush.

### 5.9 BatchEmitter — Stage 5

Fire-and-forget flush to Bridge via `IBridgeCommandPort.submit_batch()`. All exceptions caught (best-effort).

### 5.10 CircuitBreaker — Cross-cutting

| Parameter | Default |
| --- | --- |
| Failure threshold | 3 consecutive failures → OPEN |
| Recovery probe | 30s before HALF_OPEN |
| State machine | CLOSED → OPEN → HALF_OPEN → CLOSED |
| Scope | LLM calls only (MemoryWriterAgent.extract) |

---

## 6. Configuration

### 6.1 MWConfig (frozen)

| Field | Default | Invariant |
| --- | --- | --- |
| `llm_token_budget` | `2000` | MW-06 |
| `max_atoms_per_turn` | `6` | MW-05 |
| `max_text_words` | `50` | MW-04 |
| `confidence_floor` | `0.30` | — |
| `max_temporal_links_per_atom` | `5` | MW-12 |
| `batch_window_ms` | `250` | MW-08 |
| `max_batch_size` | `10` | — |
| `filter_dedup_window_seconds` | `300` | MW-07 |
| `filter_trivial_word_threshold` | `5` | MW-07 |
| `circuit_breaker_failure_threshold` | `3` | — |
| `circuit_breaker_recovery_probe_seconds` | `30` | — |
| `skip_sections` | `frozenset({"telemetry", "artifacts_warm"})` | MW-01/02 |
| `model_hint` | `"cheapest"` | — |
| `known_location_geohashes` | `{}` | — |

---

## 7. Factory Wiring

### 7.1 MemoryWriterFactory.create()

| Parameter | Type | Validated |
| --- | --- | --- |
| `session_read_port` | `ISessionReadPort` | isinstance check |
| `model_hub_port` | `IModelHubPort` | isinstance check |
| `bridge_command_port` | `IBridgeCommandPort` | isinstance check |
| `event_subscription_port` | `IEventSubscriptionPort` | isinstance check |
| `health_port` | `IHealthPort` | isinstance check |
| `config` | `MWConfig \| None` | defaults to `MWConfig()` |

**Internal wiring (9 stages):**

| Stage | Component | Injected With |
| --- | --- | --- |
| Validate | 5 ports isinstance + `validate_init_invariants()` | MW-01, MW-03, MW-07, MW-08, MW-09, MW-11 |
| Stage 1 | `RelevanceFilter(config)` | Config |
| Stage 2 | `MWSessionReader(session_read_port, config)`, `PlaceResolver([])`, `ContextBuilder(config)` | SessionRead port, Config |
| Stage 3 | `PromptLoader(prompts_dir)`, `MemoryWriterAgent(model_hub_port, config, prompt_loader)`, `PersonResolver()`, `ExtractionValidator(person_resolver, config)`, `CircuitBreaker(...)` | ModelHub port, Config |
| Stage 4 | `FieldMapper(place_resolver, config)`, `EnvelopeBuilder(field_mapper)`, `PrivacyEnforcer()` | PlaceResolver, Config |
| Stage 5 | `DeltaAggregator(config)`, `BatchEmitter(bridge_command_port)` | Bridge port, Config |
| Pipeline | `MemoryWriterPipeline(all components, event_port, config)` | All |
| Dispatcher | `TurnDispatcher(pipeline, event_subscription_port)` | Pipeline, EventSub port |
| Service | `MemoryWriterService(pipeline, dispatcher, circuit_breaker, health_port, config)` | All |

### 7.2 MemoryWriterFabricRegistration

Lifecycle helper for per-session creation/teardown:

- `create_for_session(...)` → creates CircuitBreaker, HealthAdapter, delegates to Factory, calls `service.start()`
- `teardown_session(service)` → calls `service.stop()`

---

## 8. Invariants (13 Hard Constraints)

| ID | Invariant | Enforcement | Status |
| --- | --- | --- | --- |
| MW-01 | No SessionState writes (read-only) | Init-time: forbidden keys (`IStateWritePort`, `state_write_port`, `session_write`) | ✅ |
| MW-02 | SS reads lock-free <1ms P99 | Runtime: `assert_mw02_read_latency()` after every `read_snapshot()` | ✅ |
| MW-03 | All K0 writes via Bridge only | Init-time: forbidden keys (`db_port`, `http_port`, `direct_write_port`, `database`) | ✅ |
| MW-04 | Body text ≤ 50 words | Runtime: `ExtractionValidator` truncates via `text.split()` | ✅ |
| MW-05 | 0–6 atoms per turn max | Runtime: `MemoryWriterAgent._parse_response()` hard cap 6, `ExtractionValidator` post-loop cap | ✅ |
| MW-06 | LLM budget 2000 tokens | Runtime: `assert_mw06_token_budget()` before every `chat()` call | ✅ |
| MW-07 | Filter is rule-based (no LLM) | Init-time: forbidden keys (`IModelHubPort`, `model_hub_port`, etc.) | ✅ |
| MW-08 | Batch window 250ms | Init-time: `assert_mw08_batch_window(config)` — window_ms > 0 | ✅ |
| MW-09 | Offline-safe LocalOutbox | Init-time: checks `adapter.supports_offline` | ✅ |
| MW-10 | All envelopes carry cognitive_trace_id | Runtime: `assert_mw10_trace_id()` in `EnvelopeBuilder.build()` | ✅ |
| MW-11 | UltraBERT validates in K0 P02, not K1 | Runtime: scans `sys.modules` for "ultrabert" in MW namespace | ✅ |
| MW-12 | 0–5 TemporalLinks per atom | Runtime: `ExtractionValidator._validate_temporal_links()` + `MemoryWriterAgent._parse_temporal_links()` | ✅ |
| MW-13 | place_id pattern `^place_[a-z0-9_]+$` | Runtime: regex validation | ✅ |

---

## 9. LLM Prompt System

### 9.1 System Prompt — `memory_writer_persona.md`

Loaded once at `MemoryWriterAgent.__init__()` via `PromptLoader`.

| Section | Content |
| --- | --- |
| Extraction Rules | 8 rules: extract everything memorable, self-contained, max 50 words, natural names, preserve framing, no duplicates, low confidence when in doubt |
| What Counts | Facts, opinions, third-party facts, ambient/mood, cultural/spiritual, habitual patterns, corrections |
| Cultural Awareness | Multi-cultural guidance (relationship terms, family structures, religious events) |
| Cognitive Dimensions | 11 dimensions tagged per memory (sentiment, affect, novelty, elaboration, temporal orientation, source type, activity type, intent, social context/intimacy, identity domains) |
| Temporal Links | 0–5 per memory, 6 link types, uncertainty_window_ms, confidence |
| Correction Signals (v2.2) | Explicit, implicit, context_change detection. "Err on NOT flagging." |
| Output Format | Full JSON schema example |

---

## 10. Test Coverage

- **31 test files** under `tests/k1/memory_writer/`
- Coverage areas: all 13 invariants, all pipeline stages, all adapters (prod + test), circuit breaker state machine, person resolver cascade, privacy bands, temporal link validation, race condition fix, lifecycle integration, fabric integration, section-agnostic reads
- Additional tests in `tests/k1/kernel/test_service.py`: `TestP5MemoryWriterWiring` class (kernel-level MW wiring validation)

---

## 11. Gaps & TODOs

| # | Gap | Severity | Detail |
| --- | --- | --- | --- |
| 1 | **HealthAdapter last_extraction_ms** | P4 | Hardcoded to `0.0` — not wired to actual extraction latency |
| 2 | **PlaceResolver empty init** | P3 | Factory passes `PlaceResolver([])` — no location entities loaded. Place resolution returns `None` until entity list populated |
| 3 | **ARCHITECTURE.md stale** | P4 | Claims 16/43 files exist (37%), but implementation is now much more complete. States "8 test files" — now 31 |
| 4 | **Accumulation Gate (Stage 1B)** | P3 | Documented in `.mmd` diagram (6 triggers: T1-T6) but not implemented as separate stage — turns dispatch individually |
| 5 | **`memory=None` in Concierge** | P2 | `recall_memory` tool wired as `memory=None` → `_null_recall` (returns empty list). `RecallMemoryAdapter` exists but not wired to real Bridge query |
