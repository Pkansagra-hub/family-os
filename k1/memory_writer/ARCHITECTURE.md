# K1 Memory Writer — ARCHITECTURE.md

> **Component**: `k1.memory_writer` — L4 Background Agent (Episodic Memory Formation)
> **Scan date**: 2026-04-05
> **Source files**: 8 .py files (~2,150 lines)
> **Test files**: 0 (zero test coverage)
> **Diagrams**: `memory_writer.mmd` (474 lines)
> **Design doc**: `memory_writer_architecture.md` (2,488 lines, 35 sections)
> **Contracts**: 3 YAML + 1 JSON schema

---

## Table of Contents

1. [Component Overview](#1-component-overview)
2. [Port Surface](#2-port-surface)
3. [Domain Types](#3-domain-types)
4. [Events](#4-events)
5. [Configuration](#5-configuration)
6. [Invariants](#6-invariants)
7. [Context Assembly](#7-context-assembly)
8. [Contracts](#8-contracts)
9. [Cross-Component Connections](#9-cross-component-connections)
10. [Planned vs Actual — Gap Analysis](#10-planned-vs-actual--gap-analysis)
11. [Test Coverage](#11-test-coverage)
12. [Risks & Recommendations](#12-risks--recommendations)

---

## 1. Component Overview

Memory Writer is K1's **episodic memory formation system**. It observes completed conversation turns (via `turn.complete.v1` from Concierge), determines if they contain memorable facts, extracts 0–6 short factual statements via LLM (2000-token budget), builds K0-compatible 37-field command envelopes, and submits them through the Bridge for permanent storage in K0's `st_hipp_events`.

**One-sentence role**: Translator between K1's conversational model and K0's event model.

### What Exists vs What's Planned

| Category | Planned (wiring.contract.yaml) | Actually Exists | Status |
|---|---|---|---|
| Port Protocols (5) | ISessionReadPort, IBridgeCommandPort, IEventSubscriptionPort, IModelHubPort, IHealthPort | All 5 defined | ✅ Ports exist |
| Domain types + enums | MemoryAtom (37 fields), ExtractionContext, 12 enums, 6 nested DCs | All implemented | ✅ Types exist |
| Events (topics + payloads) | 1 consumed + 5 produced topics, 6 payload DCs | All implemented | ✅ Events exist |
| Config | MWConfig (frozen DC, 15 fields) | Implemented | ✅ Config exists |
| Invariants | MW-01 through MW-13 assertion helpers | All implemented | ✅ Invariants exist |
| Context assembly | resolve_mentioned_time, resolve_mentioned_location, PlaceResolver | Implemented | ✅ Context exists |
| **Pipeline** (5-stage orchestration) | MemoryWriterPipeline, TurnDispatcher | ❌ **NOT IMPLEMENTED** | 🔴 Missing |
| **Filter** (stage 1) | RelevanceFilter, 5 skip rules | ❌ **NOT IMPLEMENTED** | 🔴 Missing |
| **Context builder** (stage 2) | MWSessionReader, ContextBuilder, PersonResolver | ❌ **NOT IMPLEMENTED** | 🔴 Missing |
| **Extraction** (stage 3) | WriterAgent, ExtractionValidator, persona prompt | ❌ **NOT IMPLEMENTED** | 🔴 Missing |
| **Envelope** (stage 4) | EnvelopeBuilder, FieldMapper, PrivacyEnforcer | ❌ **NOT IMPLEMENTED** | 🔴 Missing |
| **Batch** (stage 5) | DeltaAggregator, BatchEmitter | ❌ **NOT IMPLEMENTED** | 🔴 Missing |
| **Health** | CircuitBreaker | ❌ **NOT IMPLEMENTED** | 🔴 Missing |
| **Adapters** (5 production + 1 test) | SessionRead, BridgeCommand, EventSubscription, ModelHub, Health, TestAdapters | 2 of 5 production adapters exist (SessionRead, ModelHub) | ⚠️ Partial |
| **Factory** | MemoryWriterFactory | ❌ **NOT IMPLEMENTED** | 🔴 Missing |
| **Tests** | Any | 8 files, 254+ tests (types, invariants, adapters, context, place, exports) | ⚠️ Partial |

**Bottom line**: Memory Writer has comprehensive contracts, types, ports, events, config, invariants, and a 2,488-line design document — but **zero pipeline code and zero factory**. Two adapters exist (SessionRead, ModelHub), and 8 test files cover types, invariants, adapters, context assembly, and place resolver. The entire 5-stage extraction pipeline specified in the wiring contract does not exist.

---

## 2. Port Surface

All 5 ports are defined as `@runtime_checkable Protocol` classes in `ports/`.

### ISessionReadPort (`ports/session_read_port.py`, ~95 lines)

Read-only async access to SessionState. MW-01: NO write methods exist. MW-02: <1ms P99.

| Method | Signature | Returns |
|---|---|---|
| `snapshot` | `async (self, sections: list[str]) -> dict[str, Any]` | Dict mapping section name → data |
| `read_section` | `async (self, name: str) -> Optional[dict[str, Any]]` | Single section data or None |
| `list_sections` | `(self) -> FrozenSet[str]` | All SS section names from `ALL_SECTIONS` |
| `snapshot_all` | `async (self, exclude: FrozenSet[str] = frozenset()) -> dict[str, Any]` | All sections minus `exclude` |

Section-agnostic: reads ALL SessionState sections from `ALL_SECTIONS` except `skip_sections` (default: `telemetry`, `artifacts_warm`). New SS sections auto-included without config changes.

### IBridgeCommandPort (`ports/bridge_command_port.py`, ~80 lines)

Fire-and-forget command submission to K0 via Bridge. MW-03: ONLY output path. MW-09: Offline-safe (LocalOutbox). MW-10: cognitive_trace_id required.

| Method | Signature | Returns |
|---|---|---|
| `submit` | `async (self, topic: str, schema_uri: str, body: dict) -> None` | None |
| `submit_batch` | `async (self, envelopes: list[dict]) -> None` | None |

### IEventSubscriptionPort (`ports/event_subscription_port.py`, ~90 lines)

K1 Bus subscription for `turn.complete.v1` events. Also publishes 5 observability topics.

| Method | Signature | Returns |
|---|---|---|
| `subscribe` | `async (self, topic: str, handler: Callable[..., Coroutine]) -> Subscription` | Subscription handle |
| `unsubscribe` | `async (self, subscription_id: str) -> None` | None |
| `publish` | `async (self, topic: str, payload: dict) -> None` | None |

### IModelHubPort (`ports/model_hub_port.py`, ~60 lines)

LLM extraction call. MW-06: budget always 2000 tokens. MW-07: NEVER used by filter. Circuit breaker protected.

| Method | Signature | Returns |
|---|---|---|
| `chat` | `async (self, messages: list[dict[str, str]], budget_tokens: int, model_hint: str) -> ChatResponse` | ChatResponse |

### IHealthPort (`ports/health_port.py`, ~50 lines)

Readiness/liveness probes for Fabric agent lifecycle.

| Method | Signature | Returns |
|---|---|---|
| `is_ready` | `async (self) -> bool` | True if pipeline initialized and circuit not open |
| `health_check` | `async (self) -> HealthStatus` | HealthStatus with circuit state, pending count, latency |

### Production Adapters: ⚠️ 2 of 5 EXIST

The wiring contract specifies 6 adapter files in `adapters/`:
- `session_read_adapter.py` ✅, `bridge_command_adapter.py` ❌, `event_subscription_adapter.py` ❌, `model_hub_adapter.py` ✅, `health_adapter.py` ❌, `test_adapters.py` ❌

The `adapters/` directory exists with 3 files (`__init__.py`, `session_read_adapter.py`, `model_hub_adapter.py`). 2 production adapters implemented, 3 remaining.

---

## 3. Domain Types

All types in `types.py` (~580 lines). Pure frozen dataclasses + str-based enums. Zero business logic, zero I/O, stdlib-only imports.

### Enums (12)

| Enum | Values | Source |
|---|---|---|
| `SentimentLabel` | 5 (very_negative → very_positive) | affective_now |
| `NoveltyLevel` | 4 (ROUTINE → SURPRISING) | MW comparison vs beliefs + scoreboard |
| `ElaborationDepth` | 4 (MENTION → DEEPLY_PROCESSED) | Turn count on topic (1/2-3/4-6/7+) |
| `TemporalOrientation` | 3 (PAST, ONGOING, FUTURE_COMMITMENT) | resolved_epoch_ms vs now |
| `TemporalLinkType` | 6 (RETROSPECTIVE → CONDITIONAL) | Per-link temporal classification |
| `SourceType` | 4 (user_stated → system_inferred) | Provenance |
| `ArcPosition` | 4 (EXPOSITION → RESOLUTION) | narrative_active.arc.position |
| `SocialIntimacy` | 3 (LOW/MEDIUM/HIGH) | Relationship proximity |
| `ActivityType` | 20 (MEAL → MEMORY) | Merged K1 12-type + legacy 12-type |
| `RelationshipType` | 8 (PARENT_OF → OTHER) | Participant relationships |
| `LocationType` | 12 (home → other) | Location category |
| `IdentityDomain` | 9 (parent → spiritual_self) | Identity categories activated |
| `SkipReason` | 5 (DUPLICATE → EMPTY) | RelevanceFilter skip reasons |
| `IntentType` | 8 (log_memory → other) | control.intents[0] |
| `SocialContext` | 6 (solo → community) | Derived from relationships |

### Core Dataclasses

| Dataclass | Fields | Purpose |
|---|---|---|
| `MemoryAtom` | 37 | The memory atom — maps 1:1 to `memory_atom.v2.schema.json`. 14 required fields. Includes correction signals (R2 Epic 7.2), temporal links (0–5), place_id (GAP-002 Epic 3.1) |
| `ExtractionContext` | 25+ | Assembled from 15 SS sections for LLM prompt. Current turn, recent history, active persons, affect, narrative, topics, goals, control, device, persona, temporal/spatial |
| `CompressedTurn` | 5 | Minimal turn for history context: turn_id, role, text, timestamp_ms, turn_number |
| `FilterDecision` | 4 | PASS/SKIP result with reason, turn_id, latency_ms |
| `PersonResolution` | 4 | Name→person_id resolution: natural_name, person_id, confidence, is_provisional |
| `MWEnvelope` | 4 | Wraps MemoryAtom with routing: topic, schema_uri, trace_id, atom |
| `HealthStatus` | 5 | Health probe result: is_healthy, llm_circuit_open, pending_batch_count, last_extraction_ms, detail |
| `ChatResponse` | 6 | LLM response: content, total/prompt/completion tokens, model, latency_ms |
| `Subscription` | 2 | Bus subscription handle: subscription_id, topic |

### Nested Value Objects

| Object | Fields | Source |
|---|---|---|
| `Affect` | 3 (valence/arousal/dominance) | affective_now.dimensions |
| `ParticipantRelationship` | 3 (type/target/confidence) | Person relationships |
| `Narrative` | 3 (thread_id/arc_position/is_goal_event) | narrative_active |
| `Temporal` | 3 (mentioned_time/resolved_epoch_ms/is_backdated) | beliefs_active.MentionedTime |
| `TemporalLink` | 5 (mentioned_time/resolved_epoch_ms/uncertainty_window_ms/link_type/confidence) | Per-atom temporal references |

---

## 4. Events

All in `events.py` (~140 lines). Topic constants + frozen payload dataclasses.

### Consumed (1 topic)

| Topic | Payload | Emitted By |
|---|---|---|
| `turn.complete.v1` | `TurnCompletePayload` (18 fields) | Concierge after DELIVERING |

`TurnCompletePayload` fields: turn_id, session_id, cognitive_trace_id, user_message, assistant_response, timestamp_ms, turn_number + 8 temporal/spatial fields (GAP-002 Epic 1.1 — snapshotted before `start_new_turn()` to eliminate race condition T7).

### Produced (5 observability topics)

| Topic | Payload | When |
|---|---|---|
| `k1.mw.filter.decision.v1` | `FilterDecisionEvent` (turn_id, decision, skip_reason, latency_ms) | After every filter evaluation |
| `k1.mw.extraction.complete.v1` | `ExtractionCompleteEvent` (turn_id, atom_count, total_tokens, latency_ms) | After LLM extraction + validation |
| `k1.mw.batch.submitted.v1` | `BatchSubmittedEvent` (batch_id, envelope_count, bridge_latency_ms) | After batch submitted to Bridge |
| `k1.mw.pipeline.error.v1` | `PipelineErrorEvent` (turn_id, stage, error_type, message) | On any pipeline stage error |
| `k1.mw.circuit.open.v1` | `CircuitOpenEvent` (failure_count, recovery_probe_at) | When LLM circuit breaker trips |

---

## 5. Configuration

`config.py` (~100 lines). Single frozen `MWConfig` dataclass. Immutable after creation.

| Group | Field | Default | Invariant |
|---|---|---|---|
| LLM Extraction | `llm_token_budget` | 2000 | MW-06 |
| Atom Validation | `max_atoms_per_turn` | 6 | MW-05 |
| Atom Validation | `max_text_words` | 50 | MW-04 |
| Atom Validation | `confidence_floor` | 0.30 | — |
| Atom Validation | `max_temporal_links_per_atom` | 5 | MW-12 |
| Batch | `batch_window_ms` | 250 | MW-08 |
| Batch | `max_batch_size` | 10 | — |
| Filter | `filter_dedup_window_seconds` | 300 | MW-07 |
| Filter | `filter_trivial_word_threshold` | 5 | MW-07 |
| Circuit Breaker | `circuit_breaker_failure_threshold` | 3 | — |
| Circuit Breaker | `circuit_breaker_recovery_probe_seconds` | 30 | — |
| SS Sections | `skip_sections` | `{"telemetry", "artifacts_warm"}` | MW-01/02 |
| Model Hub | `model_hint` | "cheapest" | — |

Section-agnostic: MW reads ALL sections from `ALL_SECTIONS` except `skip_sections` via `snapshot_all(exclude=config.skip_sections)`. New SS sections auto-included.

---

## 6. Invariants

`invariants.py` (~450 lines). Runtime assertion helpers for MW-01 through MW-13. Each raises `InvariantViolation(invariant_id, message)`.

| ID | Invariant | Enforcement | Helper |
|---|---|---|---|
| MW-01 | NEVER writes SessionState | Compile-time (no write port) | `assert_mw01_no_write_port(deps)` |
| MW-02 | Reads SS lock-free <1ms | Runtime timing | `assert_mw02_read_latency(latency_ms)` |
| MW-03 | All K0 writes via Bridge only | Compile-time (only IBridgeCommandPort) | `assert_mw03_bridge_only(deps)` |
| MW-04 | Body text ≤ 50 words | Runtime validation | `assert_mw04_text_length(text, config)` |
| MW-05 | 0–6 atoms per turn max | Runtime pipeline output | `assert_mw05_atom_count(count, config)` |
| MW-06 | LLM budget: 2000 tokens | Runtime assertion | `assert_mw06_token_budget(budget, config)` |
| MW-07 | Filter is rule-based (no LLM) | Compile-time (no model port in filter) | `assert_mw07_filter_no_llm(deps)` |
| MW-08 | Batch window: 250ms | Runtime config validation | `assert_mw08_batch_window(config)` |
| MW-09 | Offline-safe (LocalOutbox) | Runtime adapter check | `assert_mw09_offline_capable(adapter)` |
| MW-10 | All envelopes carry cognitive_trace_id | Runtime assertion | `assert_mw10_trace_id(trace_id)` |
| MW-11 | UltraBERT validates in K0 P02, not K1 | Compile-time (no ultrabert import) | `assert_mw11_no_ultrabert_import()` |
| MW-12 | temporal_links: 0–5 per atom, valid types | Runtime validation | `assert_mw12_temporal_links(links, config)` |
| MW-13 | place_id: None or `^place_[a-z0-9_]+$` | Runtime validation | `assert_mw13_place_id(place_id)` |

---

## 7. Context Assembly

Two modules handle temporal/spatial context resolution:

### `context_assembly.py` (~175 lines)

Payload-first, SessionState-fallback pattern. Eliminates race condition T7 (Concierge's `start_new_turn()` clears beliefs_active fields before MW reads them).

| Function | Signature | Returns | Logic |
|---|---|---|---|
| `resolve_mentioned_time` | `(payload, beliefs_snapshot) -> tuple[str, int, float, bool]` | (raw, resolved_ms, confidence, is_relative) | Priority: payload fields > beliefs_active.mentioned_time |
| `resolve_mentioned_location` | `(payload, beliefs_snapshot) -> tuple[str, str, str, float]` | (raw, type, entity_id, confidence) | Priority: payload fields > beliefs_active.mentioned_location |
| `resolve_place_id` | `(location_raw, beliefs_snapshot) -> Optional[str]` | place_id or None | Uses PlaceResolver with LOCATION entities |
| `assemble_temporal_spatial` | `(payload, beliefs_snapshot) -> dict[str, Any]` | 10-key dict for ExtractionContext | Calls all three resolvers |

### `place_resolver.py` (~120 lines)

Resolves location names to stable `place_<slug>` identifiers using EntityRef objects from beliefs_active.

| Class | Slots | Methods |
|---|---|---|
| `ResolvedPlace` | place_id, canonical_name, confidence | (frozen dataclass) |
| `PlaceResolver` | `_exact_map`, `_entries` | `resolve(name) -> Optional[str]` |

Resolution: O(1) exact match (case-insensitive) → O(n) prefix fallback. Slug: lowercase, spaces→underscores, punctuation stripped.

---

## 8. Contracts

Three YAML contracts + 1 JSON schema:

### `module.contract.yaml`
- Module metadata (id: memory_writer, band: GREEN)
- 25 exported symbols (1 facade, 8 services, 5 ports, 6 types, 5 enums)
- Dependencies: sessionstate (required), bridge (required), bus (required), model_hub (optional)
- 11 invariants (MW-01 through MW-11)
- Entrypoints: `memory_writer:initialize`, `memory_writer:cleanup`

### `wiring.contract.yaml`
- Code root: `k1/memory_writer`
- **43 required files** spanning 8 subdirectories: ports/, pipeline/, filter/, context/, extraction/, envelope/, batch/, health/, adapters/
- Import wiring: required [bus, sessionstate], optional [bridge, model_hub], forbidden [direct_db, http, sessionstate_writer, ultrabert]
- Capabilities: provides `memory_writer:process:v1` + `memory_writer:health:v1`; consumes `session:read:v1`, `bridge:command:v1`, `bus:subscribe:v1`, `model_hub:chat:v1`

### `policies.contract.yaml`
- Performance budgets: filter 2ms, SS read 1ms, LLM extraction 500ms, envelope 2ms, batch 310ms, **total P95: 815ms**
- Extraction limits: 6 atoms, 2000 tokens, 50 words, 0.30 confidence floor
- Batch: 250ms window, 10 max
- Filter: 300s dedup window, 5-word trivial threshold
- Circuit breaker: 3 failures/min, 30s recovery probe
- Safety bands: GREEN→all pass, AMBER→strip location, RED→strip location+names
- Audit: cognitive_trace_id required on all envelopes

### `memory_atom.v2.schema.json`
- JSON Schema for the 37-field MemoryAtom. Maps 1:1 to `types.MemoryAtom`.

---

## 9. Cross-Component Connections

### Planned Inbound (ports this component expects injected)

| Provider | Port | Adapter (planned) | Status |
|---|---|---|---|
| SessionState | `ISessionReadPort` | `SessionReadAdapter` | ✅ Implemented |
| Bridge | `IBridgeCommandPort` | `BridgeCommandAdapter` | ❌ Adapter not implemented |
| Bus | `IEventSubscriptionPort` | `EventSubscriptionAdapter` | ❌ Adapter not implemented |
| ModelHub | `IModelHubPort` | `ModelHubAdapter` | ✅ Implemented |
| (self) | `IHealthPort` | `HealthAdapter` | ❌ Adapter not implemented |

### Planned Outbound (events this component emits)

| Consumer | Via | Topic | Status |
|---|---|---|---|
| Observability / Bus | IEventSubscriptionPort.publish() | 5 `k1.mw.*` topics | ❌ No emitter code |
| K0 (Bridge) | IBridgeCommandPort.submit_batch() | `memory.write` | ❌ No emitter code |

### Trigger

| Source | Event | Handler |
|---|---|---|
| Concierge | `turn.complete.v1` | Planned: `TurnDispatcher` → `MemoryWriterPipeline` | ❌ Neither exists |

---

## 10. Planned vs Actual — Gap Analysis

The wiring contract specifies **43 required files** across 8 subdirectories. Here is the full gap:

### Files that EXIST (16 of 43)

> **STALE (2026-04-22 / TD-2.4):** This 16/43 (~37%) snapshot is from M0. The package now ships **46 .py files** and is largely feature-complete. Use the file tree under `k1/memory_writer/` for the current state — the table below is kept only for historical context and is no longer maintained.

| File | Lines | Content |
|---|---|---|
| `__init__.py` | ~155 | Re-exports 54 symbols (ports, types, enums, events, config, adapters) |
| `types.py` | ~580 | 15 enums + 14 dataclasses (MemoryAtom 42f, ExtractionContext, etc.) |
| `config.py` | ~100 | MWConfig frozen dataclass |
| `events.py` | ~140 | 6 topic constants + 6 payload dataclasses |
| `invariants.py` | ~450 | MW-01 through MW-13 assertion helpers |
| `context_assembly.py` | ~175 | Temporal/spatial resolution (payload-first pattern) |
| `place_resolver.py` | ~120 | PlaceResolver + ResolvedPlace |
| `ports/__init__.py` | ~35 | Re-exports all 5 ports |
| `ports/session_read_port.py` | ~95 | ISessionReadPort Protocol |
| `ports/bridge_command_port.py` | ~80 | IBridgeCommandPort Protocol |
| `ports/event_subscription_port.py` | ~90 | IEventSubscriptionPort Protocol |
| `ports/model_hub_port.py` | ~60 | IModelHubPort Protocol |
| `ports/health_port.py` | ~50 | IHealthPort Protocol |
| `adapters/__init__.py` | ~8 | Re-exports ModelHubAdapter, SessionReadAdapter |
| `adapters/session_read_adapter.py` | ~120 | SessionReadAdapter: wraps SSM, snapshot/read_section, phantom handling |
| `adapters/model_hub_adapter.py` | ~100 | ModelHubAdapter: wraps K1 IModelHubPort, MW chat() → K1 execute() |

### Entire Directories that DO NOT EXIST (8 of 8 subdirectories)

| Directory | Planned Files | Purpose |
|---|---|---|
| `pipeline/` | pipeline.py, turn_dispatcher.py | 5-stage orchestration + bus trigger |
| `filter/` | relevance_filter.py, rules.py | Stage 1: rule-based filter (5 skip rules) |
| `context/` | session_reader.py, context_builder.py, person_resolver.py | Stage 2: SS read + context assembly |
| `extraction/` | writer_agent.py, extraction_validator.py, prompts/persona.md | Stage 3: LLM extraction + validation |
| `envelope/` | envelope_builder.py, field_mapper.py, privacy_enforcer.py | Stage 4: atom→envelope mapping |
| `batch/` | delta_aggregator.py, batch_emitter.py | Stage 5: 250ms aggregation + Bridge submit |
| `health/` | circuit_breaker.py | LLM circuit breaker |
| `adapters/` | 3 remaining (bridge, event_subscription, health + test_adapters) | Concrete port implementations |

**Total**: 16 files exist out of 43 planned. **27 files missing (63%).**

### What Exists is "Layer 0" — Contracts + Types + Invariants

The existing code forms a well-designed foundation layer:
- **Types** define the complete data model (MemoryAtom with 42 fields, 15 enums, 14 dataclasses)
- **Ports** define the hexagonal boundary (5 Protocol ABCs)
- **Events** define the bus integration (1 consumed + 5 produced topics)
- **Config** centralizes all tunable parameters
- **Invariants** provide runtime assertion helpers for MW-01 through MW-13
- **Context assembly** solves the race condition (GAP-002 T7)
- **PlaceResolver** handles location resolution

But the entire **pipeline** (the actual processing logic) — filter, context builder, extraction, envelope builder, batch emitter, circuit breaker, adapters, and factory — does not exist.

---

## 11. Test Coverage

| Metric | Count |
|---|---|
| Test files | 8 |
| Test functions | 254+ |

| File | Tests | What It Tests |
|---|---|---|
| `test_turn_timestamp_propagation.py` | 22 | conversation_anchor_ms flow through MemoryAtom, ExtractionContext, MWEnvelope |
| `test_temporal_link.py` | 38 | TemporalLink DC, MW-12 invariant, 6 link types, uncertainty windows |
| `test_session_read_adapter_056.py` | 28 | SessionReadAdapter snapshot/read_section, phantom sections |
| `test_race_condition_fix.py` | 20 | context_assembly.py resolve_mentioned_time/location, T7 race fix |
| `test_place_resolver.py` | 47 | PlaceResolver exact/prefix match, ResolvedPlace DC, edge cases |
| `test_mw_invariants.py` | 27 | MW-01 through MW-13 assertion helpers, InvariantViolation |
| `test_model_hub_adapter_053.py` | 26 | ModelHubAdapter chat() translation, budget enforcement |
| `test_init_exports.py` | 46 | __init__.py exports, enum counts, MemoryAtom fields, MWConfig defaults |

---

## 12. Risks & Recommendations

### Critical Gaps (🔴)

| # | Gap | Impact |
|---|---|---|
| G-1 | **Entire 5-stage pipeline missing** | MW cannot process any turns. Zero functionality beyond type definitions. |
| G-2 | **3 of 5 production adapters missing** | SessionRead and ModelHub exist; BridgeCommand, EventSubscription, Health adapters still needed. |
| G-3 | **Zero factory** | No `MemoryWriterFactory.create_session()` — cannot be instantiated by Tier 2 bootstrap. |
| G-4 | **Tests cover foundation only** | 8 test files, 254+ tests covering types, invariants, adapters, context, place resolver, exports. Pipeline tests pending (Phases 1-5). |
| G-5 | **`__init__.py` populated** | ✅ Fixed: 54 symbols exported, all importable. |

### Architectural Strengths (✅)

| # | Strength | Detail |
|---|---|---|
| S-1 | **Port design is solid** | 5 well-documented Protocol ABCs with runtime_checkable, clear invariant annotations, consistent with Orchestrator pattern |
| S-2 | **MemoryAtom schema is complete** | 42-field frozen dataclass matching JSON schema. Includes v2 additions (temporal_links, place_id, correction_signals, location_hierarchy, transitions) |
| S-3 | **Invariant helpers are thorough** | MW-01 through MW-13 with clear enforcement strategy (compile-time vs runtime) |
| S-4 | **Race condition solved in design** | context_assembly.py implements payload-first pattern for T7 race condition |
| S-5 | **Contracts are comprehensive** | 3 YAML contracts specify everything: 43 files, wiring, policies, budgets, invariants |
| S-6 | **Design doc is 2,488 lines** | 35-section design document with worked examples, error handling, metrics, cross-references |

### Recommendations

1. **Phase 1** (foundation): Populate `__init__.py` with re-exports matching module.contract.yaml. Add tests for existing types, invariants, context_assembly, and place_resolver.
2. **Phase 2** (pipeline skeleton): Create `pipeline/`, `filter/`, `context/`, `extraction/`, `envelope/`, `batch/` directories with minimal implementations. Wire the 5-stage pipeline.
3. **Phase 3** (adapters): Implement `adapters/` — start with test adapters, then production adapters bridging to SessionState, Bridge, Bus, ModelHub.
4. **Phase 4** (factory): Create `MemoryWriterFactory.create_session(5 ports)` following Orchestrator pattern. Wire into Tier 2 bootstrap.

### Performance Budget (from policies.contract.yaml)

| Stage | P99 Budget |
|---|---|
| Filter (rule-based) | 2ms |
| SessionState read | 1ms |
| LLM extraction | 500ms |
| Envelope build | 2ms |
| Batch submit | 310ms |
| **Total (P95)** | **815ms** |
