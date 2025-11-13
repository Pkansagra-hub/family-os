
# ADR Reference Guide: Cross-Cutting Concerns

**Generated:** Auto-generated from ADR family map
**Purpose:** Quick reference for ADRs relevant to Cross-Cutting Concerns development

## Overview

These ADRs apply across all layers and affect system-wide architecture.

**Total Relevant ADRs:** 66

---

## Quick Reference: All ADRs for Cross-Cutting Concerns

| ADR | Title | Family |
|-----|-------|--------|
| [ADR-0001](./0001-*.md) | 0001 Memory Kernel | K0 Core |
| [ADR-0001f](./0001f-*.md) | 0001F Memory Kernel | K0 Core |
| [ADR-0004](./0004-*.md) | 0004 Architecture | K1 Core |
| [ADR-0004b](./0004b-*.md) | 0004B Dependencies | K1 Core |
| [ADR-0004c](./0004c-*.md) | 0004C Documentation | ADR Notes |
| [ADR-0004d](./0004d-*.md) | 0004D Testing | K1 Core |
| [ADR-0011a](./0011a-*.md) | 0011A Schema Design | FlatBuffers |
| [ADR-0011b](./0011b-*.md) | 0011B Code Generation | FlatBuffers |
| [ADR-0011c](./0011c-*.md) | 0011C Performance | FlatBuffers |
| [ADR-0011d](./0011d-*.md) | 0011D Schema Evolution | FlatBuffers |
| [ADR-0012](./0012-*.md) | 0012 Schema Taxonomy | FlatBuffers Schemas |
| [ADR-0013](./0013-*.md) | 0013 SemVer Policy | Schema Versioning |
| [ADR-0013a](./0013a-*.md) | 0013A Version Registry | Schema Versioning |
| [ADR-0013b](./0013b-*.md) | 0013B CI/CD Automation | Schema Versioning |
| [ADR-0013c](./0013c-*.md) | 0013C Deprecation Workflow | Schema Versioning |
| [ADR-0013d](./0013d-*.md) | 0013D Contract Testing | Schema Versioning |
| [ADR-0014b](./0014b-*.md) | 0014B OpenAPI Generation | REST API Dual Format |
| [ADR-0014d](./0014d-*.md) | 0014D Client SDKs | REST API Dual Format |
| [ADR-0015](./0015-*.md) | 0015 Protocol Design | WebSocket Binary Protocol |
| [ADR-0015a](./0015a-*.md) | 0015A Protocol Design | WebSocket Binary Protocol |
| [ADR-0015b](./0015b-*.md) | 0015B Flow Control | WebSocket Binary Protocol |
| [ADR-0015c](./0015c-*.md) | 0015C Reconnection | WebSocket Binary Protocol |
| [ADR-0015d](./0015d-*.md) | 0015D Streaming | WebSocket Binary Protocol |
| [ADR-0015e](./0015e-*.md) | 0015E Client SDK | WebSocket Binary Protocol |
| [ADR-0016](./0016-*.md) | 0016 Event Taxonomy | SSE Event Schemas |
| [ADR-0016a](./0016a-*.md) | 0016A Event Taxonomy | SSE Event Schemas |
| [ADR-0016c](./0016c-*.md) | 0016C Filtering | SSE Event Schemas |
| [ADR-0016d](./0016d-*.md) | 0016D Browser Integration | SSE Event Schemas |
| [ADR-0019](./0019-*.md) | 0019 Serialization Core | FlatBuffers SessionState Serialization |
| [ADR-0019a](./0019a-*.md) | 0019A Schema Definition | FlatBuffers SessionState Serialization |
| [ADR-0021c](./0021c-*.md) | 0021C Compliance | Turn History Retention |
| [ADR-0022d](./0022d-*.md) | 0022D FlatBuffers Schema | K0 Bridge Batching |
| [ADR-0023c](./0023c-*.md) | 0023C K0 WAL Query | Cursor-Based Pagination |
| [ADR-0042a](./0042a-*.md) | 0042A Event Production | K0 SSE Event Streaming |
| [ADR-0042d](./0042d-*.md) | 0042D Backpressure | K0 SSE Event Streaming |
| [ADR-0043c](./0043c-*.md) | 0043C Topic Routing | SSE Topic Taxonomy |
| [ADR-0046](./0046-*.md) | 0046 Configuration | SSE-WebSocket Bridge |
| [ADR-0047](./0047-*.md) | 0047 SDK Generation | OpenAPI 3.1 Specs |
| [ADR-0048](./0048-*.md) | 0048 K0/K1 Separation | K1 Internal Event Bus |
| [ADR-0049](./0049-*.md) | 0049 Configuration | Fast/Smart Lane Router |
| [ADR-0050](./0050-*.md) | 0050 Sync Strategy | Multi-Device Family Sync |
| [ADR-0052](./0052-*.md) | 0052 Research Foundation | Enhanced HITL Protocols |
| [ADR-0052b](./0052b-*.md) | 0052B RED Band Approval | Enhanced HITL Protocols |
| [ADR-0052c](./0052c-*.md) | 0052C Nested Clarifications | Enhanced HITL Protocols |
| [ADR-0052d](./0052d-*.md) | 0052D Proactive Confirmation | Enhanced HITL Protocols |
| [ADR-0053](./0053-*.md) | 0053 Main | Message Queue & Coalescing |
| [ADR-0053a](./0053a-*.md) | 0053A Coalesce Window | Message Queue & Coalescing |
| [ADR-0053b](./0053b-*.md) | 0053B Rate Limits | Message Queue & Coalescing |
| [ADR-0053c](./0053c-*.md) | 0053C Cancel Path | Message Queue & Coalescing |
| [ADR-0054](./0054-*.md) | 0054 Main | Turn Boundary Management |
| [ADR-0054a](./0054a-*.md) | 0054A Implicit Pause | Turn Boundary Management |
| [ADR-0054b](./0054b-*.md) | 0054B Explicit Submit | Turn Boundary Management |
| [ADR-0056](./0056-*.md) | 0056 Pipeline Architecture | Voice Pipeline Implementation |
| [ADR-0056a](./0056a-*.md) | 0056A ASR Ingress | Voice Pipeline Implementation |
| [ADR-0056d](./0056d-*.md) | 0056D TTS Synthesis | Voice Pipeline Implementation |
| [ADR-0056e](./0056e-*.md) | 0056E Audio Output | Voice Pipeline Implementation |
| [ADR-0081](./0081-*.md) | 0081 Knowledge Graph | K0 Core |
| [ADR-0081a](./0081a-*.md) | 0081A Knowledge Graph | K0 Core |
| [ADR-0081b](./0081b-*.md) | 0081B Knowledge Graph | K0 Core |
| [ADR-0081c](./0081c-*.md) | 0081C Knowledge Graph | K0 Core |
| [ADR-0081d](./0081d-*.md) | 0081D Knowledge Graph | K0 Core |
| [ADR-0084](./0084-*.md) | 0084 Core Architecture | K0 Memory Consolidation |
| [ADR-0084a](./0084a-*.md) | 0084A Hippocampal Replay | K0 Memory Consolidation |
| [ADR-0084b](./0084b-*.md) | 0084B Sleep State Machine | K0 Memory Consolidation |
| [ADR-0084c](./0084c-*.md) | 0084C Knowledge Graph Consol. | K0 Memory Consolidation |
| [ADR-0084d](./0084d-*.md) | 0084D Dream Exploration | K0 Memory Consolidation |

---

## Detailed Breakdown by Family

### ADR Notes

#### [ADR-0004c](./0004c-*.md): 0004C Documentation

**Components:**

- **Documentation** → Module READMEs
  - File: `tools/k1_doc_gen.py`
  - k1-doc-gen, README template, auto-generation, docstring extraction, metadata parsing, CI enforcement


### Cursor-Based Pagination

#### [ADR-0023c](./0023c-*.md): 0023C K0 WAL Query

**Components:**

- **K0 WAL Query** → SQLite Index
  - File: `k0/wal_storage/indexes.sql`
  - CREATE INDEX idx_session_turn ON turns (session_id, turn_id), <50ms P95 indexed query


### Enhanced HITL Protocols

#### [ADR-0052](./0052-*.md): 0052 Research Foundation

**Components:**

- **Research Foundation** → Grounding Theory
  - File: `docs/research/clark_brennan_1991_grounding.md`
  - Common ground theory (Clark & Brennan 1991), clarification as grounding act, HITL builds common ground

- **Research Foundation** → Error Prevention
  - File: `docs/research/norman_1988_design.md`
  - Forcing functions (Norman 1988), explicit confirmation prevents accidental actions, RED band approval design

- **Research Foundation** → Swiss Cheese Model
  - File: `docs/research/reason_1990_human_error.md`
  - Defense-in-depth safety layers (Reason 1990), multi-layered HITL prevents failures (anomaly + risk + explicit)

- **Research Foundation** → Session Types Validation
  - File: `docs/research/honda_2008_mpst.md`
  - Multiparty Session Types (Honda 2008), protocol validation for nested HITL interactions

- **Audit Trail** → 7-Year Retention
  - File: `k0/receipts/hitl_audit_log.py`
  - RED band approvals logged to K0 receipts, 7-year retention (SOC2/ISO27001 compliance)

- **Audit Trail** → HITL Audit Schema
  - File: `k1/schemas/flatbuffers/hitl_audit_record.fbs`
  - Full audit trail: who approved, when, what phrase, risk score, outcome (1KB per approval)

- **Testing** → WARD Integration Tests
  - File: `tests/integration/test_hitl_extensions.py`
  - Comprehensive HITL tests: step-by-step rollback, RED band phrases, nested go-back, proactive confidence

#### [ADR-0052b](./0052b-*.md): 0052B RED Band Approval

**Components:**

- **RED Band Approval** → Audit Trail
  - File: `k0/receipts/red_band_audit.py`
  - 7-year retention to K0 receipts (ADR-0038), SOC2/ISO27001 compliance, immutable append-only logs

- **RED Band Approval** → RedBandAuditRecord
  - File: `k1/schemas/flatbuffers/red_band_audit.fbs`
  - Full audit: approval_id, operation, confidence_factors, phrase match result, approver IDs, execution result (1KB)

- **RED Band Approval** → Norman's Forcing Functions
  - File: `docs/research/norman_1988_forcing_functions.md`
  - Design of Everyday Things (Norman 1988), explicit phrase typing forces conscious confirmation

- **RED Band Approval** → Swiss Cheese Model
  - File: `docs/research/reason_1990_swiss_cheese.md`
  - Defense-in-depth (Reason 1990), RED band approval is one safety layer among many

#### [ADR-0052c](./0052c-*.md): 0052C Nested Clarifications

**Components:**

- **Nested Clarifications** → Grounding Theory
  - File: `docs/research/clark_brennan_1991_grounding.md`
  - Grounding in Communication (Clark & Brennan 1991), nested clarifications build common ground incrementally

- **Nested Clarifications** → QUD Theory
  - File: `docs/research/roberts_1996_qud.md`
  - Questions Under Discussion (Roberts 1996), QUD stack = hierarchical question structure

- **Nested Clarifications** → Multi-Turn Dialogue
  - File: `docs/research/jurafsky_martin_2020_dialogue.md`
  - Dialogue state tracking (Jurafsky & Martin 2020), ClarificationHistory is dialogue state for HITL chains

#### [ADR-0052d](./0052d-*.md): 0052D Proactive Confirmation

**Components:**

- **Proactive Confirmation** → ProactiveConfirmationRecord
  - File: `k1/schemas/flatbuffers/proactive_confirmation.fbs`
  - K0 receipts audit: decision_id, confidence_score, reasoning, user_response (proceeded/retried/cancelled), outcome, feedback_signal

- **Proactive Confirmation** → Feedback Signals
  - File: `k0/learning/feedback_integration.py`
  - 1.0 (agent was right), 0.5 (partial correctness), 0.0 (agent was wrong), feed to Learning Loop (ADR-0059)


### Fast/Smart Lane Router

#### [ADR-0049](./0049-*.md): 0049 Configuration

**Components:**

- **Configuration** → Router Config
  - File: `k1/config/k0_bridge.yml`
  - Configurable weights, hot-reload via Config Manager, feature flag lane_router.enabled


### FlatBuffers

#### [ADR-0011a](./0011a-*.md): 0011A Schema Design

**Components:**

- **Schema Design** → Schema Validator
  - File: `tools/schema_validator.py`
  - Schema validation, file identifier checks, root type validation, compile-time errors

- **Schema Design** → Naming Conventions
  - File: `contracts/flatbuffers/naming.yml`
  - PascalCase tables, snake_case fields, UPPER_SNAKE_CASE enums, 4-char file IDs

- **Schema Design** → Type System
  - File: `contracts/flatbuffers/type_system.yml`
  - Scalars, vectors, strings, tables, unions, enums, structs, value types

- **Schema Design** → Forward Compatibility
  - File: `contracts/flatbuffers/compatibility.yml`
  - Optional fields, default values, no removals, union polymorphism

- **Schema Design** → Deprecation Policy
  - File: `contracts/flatbuffers/deprecation.yml`
  - 3-release grace period, (deprecated) attribute, migration guides

- **Schema Design** → Schema Registry
  - File: `k1/schemas/SCHEMA_VERSIONS.md`
  - 76 schemas, file ID→version mapping, introduced/deprecated/removed tracking

#### [ADR-0011b](./0011b-*.md): 0011B Code Generation

**Components:**

- **Code Generation** → flatc Compiler
  - File: `tools/flatc/wrapper.py`
  - v23.5.26, Python/C++/Rust bindings, --gen-object-api, <100ms compilation

- **Code Generation** → Python Bindings
  - File: `k1/schemas/generated/python/`
  - AgentState, TaskAnnouncement, SessionState, 76 generated modules

- **Code Generation** → C++ Bindings
  - File: `k1/schemas/generated/cpp/`
  - agent_state_generated.h, FlatBufferBuilder, C++17 concepts

- **Code Generation** → Rust Bindings
  - File: `k1/schemas/generated/rust/`
  - Cargo crate, flatbuffers::FlatBufferBuilder, Rust 1.70

- **Code Generation** → Build Integration
  - File: `CMakeLists.txt`
  - CMake add_custom_target, Bazel flatbuffer_library, setup.py build_py

- **Code Generation** → Type Stubs
  - File: `k1/schemas/types.py`
  - Python type hints, mypy support, IDE autocomplete, type-safe APIs

- **Code Generation** → CI Validation
  - File: `ci/validate_schemas.sh`
  - Schema compilation checks, breaking change detection, pre-commit hooks

#### [ADR-0011c](./0011c-*.md): 0011C Performance

**Components:**

- **Performance** → Benchmarks
  - File: `tests/performance/flatbuffers_bench.py`
  - SessionState 64KB <1ms serialize, <0.1ms deserialize, 11× throughput vs JSON

#### [ADR-0011d](./0011d-*.md): 0011D Schema Evolution

**Components:**

- **Schema Evolution** → Version Registry
  - File: `k1/schemas/SCHEMA_VERSIONS.md`
  - major.minor versioning, introduced/deprecated/removed tracking, 4-char file IDs

- **Schema Evolution** → Backward Compatibility
  - File: `contracts/flatbuffers/backward_compat.yml`
  - Add optional fields, new enum values, new tables, deprecation allowed

- **Schema Evolution** → Forward Compatibility
  - File: `contracts/flatbuffers/forward_compat.yml`
  - Ignore unknown fields, default values, unknown enum handling

- **Schema Evolution** → Migration Scripts
  - File: `scripts/migrate_schema.py`
  - Automated migration, field renaming, type changes, 3-release timeline

- **Schema Evolution** → Schema Diff Tool
  - File: `scripts/schema_diff.py`
  - Detect changes, breaking change alerts, version comparison


### FlatBuffers Schemas

#### [ADR-0012](./0012-*.md): 0012 Schema Taxonomy

**Components:**

- **Schema Taxonomy** → Complete Inventory
  - File: `k1/schemas/SCHEMA_INVENTORY.md`
  - 76 schemas total, 9 categories, hybrid architecture coverage (pure actors + AI agents)

- **Schema Taxonomy** → Category Organization
  - File: `k1/schemas/`
  - Base Types 5, K0 Pipelines 20, Agent Contracts 8, State 6, Model Hub 7, Tools 5, Protocol 6, Observability 5, WebSocket 7, Infrastructure 7

- **Schema Taxonomy** → File Structure
  - File: `k1/schemas/{category}/{entity}.fbs`
  - PascalCase tables, snake_case fields, 4-char file IDs, category-based organization

- **Schema Taxonomy** → Decision Matrix
  - File: `docs/architecture/decisions/0012-76-flatbuffers-schemas.md`
  - 76 schemas selected 9/10 vs 5 alternatives (fewer 3/10, Protobuf 6/10, more 5/10, monolithic 2/10)

- **Schema Taxonomy** → Design Patterns
  - File: `k1/schemas/PATTERNS.md`
  - 6 patterns: Request/Response Pairs, Agent Messages, SessionState, StateDelta, Protocol Events, Observability

- **File Identifiers** → Registry
  - File: `k1/schemas/FILE_IDENTIFIERS.md`
  - 76 4-char codes (AGST, TASK, PROP, SEST, BLFS, TDEF, MREQ, HREQ, AUDF, CFGS, METS, BPSG, etc.)

- **File Identifiers** → Validation
  - File: `k1/schemas/validators/file_id_validator.py`
  - File ID uniqueness checks, collision detection, identifier format validation

- **Schema Versioning** → Version Strategy
  - File: `k1/schemas/VERSIONING.md`
  - v1.0-v1.2, forward/backward compatibility, 3-release deprecation window

- **Schema Versioning** → Evolution Rules
  - File: `contracts/flatbuffers/evolution.yml`
  - Optional fields, default values, no removals, union polymorphism, migration scripts

- **Schema Versioning** → Breaking Changes
  - File: `docs/architecture/SCHEMA_CHANGES.md`
  - Change tracking, impact analysis, migration guides, CI validation

- **Performance** → Serialization Budgets
  - File: `k1/schemas/PERFORMANCE.md`
  - <0.5-3.2ms serialize (depends on size), <0.1-0.5ms deserialize, zero-copy optimization

- **Performance** → Size Efficiency
  - File: `k1/schemas/BENCHMARKS.md`
  - 1× FlatBuffers vs JSON 3×, 64KB SessionState, 256B-64KB typical schemas, 150× faster

- **Code Generation** → flatc Compiler
  - File: `tools/flatc/k1_compile_schemas.py`
  - v23.5.26, <10s compilation for all 76 schemas, --gen-object-api flag

- **Code Generation** → Python Bindings
  - File: `k1/schemas/generated/python/`
  - 228 generated files (76 schemas × 3 files/schema avg), imports, type hints

- **Code Generation** → C++ Bindings
  - File: `k1/schemas/generated/cpp/`
  - *_generated.h headers, FlatBufferBuilder, C++17 concepts, constexpr support

- **Code Generation** → Rust Bindings
  - File: `k1/schemas/generated/rust/`
  - Cargo crate flatbuffers-k1, FlatBufferBuilder, Rust 1.70+, future support

- **Code Generation** → Build Scripts
  - File: `scripts/generate_schemas.py`
  - CI integration, pre-commit hooks, incremental compilation, dependency tracking

- **Testing** → Contract Testing
  - File: `tests/schemas/test_contracts.py`
  - Schema round-trip tests, compatibility tests, breaking change detection

- **Testing** → Schema Fixtures
  - File: `tests/schemas/fixtures/`
  - Sample data for all 76 schemas, valid/invalid cases, edge cases

- **Testing** → Performance Tests
  - File: `tests/schemas/test_performance.py`
  - Serialization latency tests, memory usage tests, benchmark regression detection

- **Documentation** → Schema Catalog
  - File: `docs/schemas/CATALOG.md`
  - Complete reference: all 76 schemas, fields, types, examples, use cases

- **Documentation** → Integration Guide
  - File: `docs/schemas/INTEGRATION.md`
  - How to use schemas in K1 modules, best practices, common patterns, anti-patterns


### FlatBuffers SessionState Serialization

#### [ADR-0019](./0019-*.md): 0019 Serialization Core

**Components:**

- **Serialization Core** → Schema Validation
  - File: `k1/schemas/session_state/validator.py`
  - Compile-time type safety, FlatBuffers compiler, 18 bugs caught

#### [ADR-0019a](./0019a-*.md): 0019A Schema Definition

**Components:**

- **Schema Definition** → Root Schema
  - File: `k1/schemas/session_state/session_state_root.fbs`
  - SessionStateRoot container, all 6 sections + metadata, schema_version SemVer 2.0

- **Schema Definition** → Delta Schema
  - File: `k1/schemas/session_state/session_state_delta.fbs`
  - SessionStateDelta, nullable sections (only changed), changed_sections array

- **Schema Definition** → Beliefs Section Schema
  - File: `k1/schemas/session_state/sections/beliefs_section.fbs`
  - Fact storage (key-value with confidence), LRU order, privacy band, 10-20KB size

- **Schema Definition** → Scoreboard Section Schema
  - File: `k1/schemas/session_state/sections/scoreboard_section.fbs`
  - Entity tracking (referents, salience), QUD stack, common ground, 4-8KB size

- **Schema Definition** → Control Section Schema
  - File: `k1/schemas/session_state/sections/control_section.fbs`
  - Agent leases (30s expiry), flow state (3-phase), turn lock, budget tracker, 8-12KB size

- **Schema Definition** → Persona Section Schema
  - File: `k1/schemas/session_state/sections/persona_section.fbs`
  - Personality traits (Big Five OCEAN), communication style (tone, verbosity, humor), voice continuity (prosody controls, voice history, emotional state), self-model (capabilities, consistency validat...

- **Schema Definition** → Multimodal Section Schema
  - File: `k1/schemas/session_state/sections/multimodal_section.fbs`
  - Audio buffers (K0 blob pointers), vision embeddings (CLIP 512-dim), streaming state, ambient context (room occupancy, PIR/mmWave sensors), multi-party conversations (active speakers, voice biometri...

- **Schema Definition** → Meta Section Schema
  - File: `k1/schemas/session_state/sections/meta_section.fbs`
  - Telemetry (session duration, turn counts), performance metrics (TTFT, E2E), Prometheus export, 2-4KB size

- **Schema Definition** → Type Definitions
  - File: `k1/schemas/session_state/types/`
  - Fact, Entity, AgentLease, PersonalityTrait, AudioBuffer, VisionEmbedding, PerformanceMetrics

- **Schema Definition** → Enum Definitions
  - File: `k1/schemas/session_state/enums/`
  - PrivacyBand (GREEN, AMBER, RED), AgentState (PENDING, ACTIVE, etc.), FlowPhase (NEGOTIATION, SELECTION, EXECUTION)


### K0 Bridge Batching

#### [ADR-0022d](./0022d-*.md): 0022D FlatBuffers Schema

**Components:**

- **FlatBuffers Schema** → Batch Schema
  - File: `k1/schemas/k0_bridge/batch.fbs`
  - ReceiptBatch table, array of receipts, compression flag, batch_id, sequence_number

- **FlatBuffers Schema** → Zero-Copy Batch
  - File: `k1/schemas/k0_bridge/batch.fbs`
  - Zero-copy deserialization, direct buffer access, <0.1ms deserialize, 150× faster vs JSON

- **FlatBuffers Schema** → Batch Metadata
  - File: `k1/schemas/k0_bridge/batch.fbs`
  - batch_id, sequence_number, receipt_count, total_size_bytes, compression_algorithm, timestamp_ms


### K0 Core

#### [ADR-0001](./0001-*.md): 0001 Memory Kernel

**Components:**

- **Memory Kernel** → P01-P20 Pipelines
  - File: `k0/pipelines/`
  - RecallQuery, MemoryWrite, AttentionGate, Hippocampus, FeedbackIntegration, SelfModelUpdate

- **Memory Kernel** → Durable Storage
  - File: `k0/storage/`
  - WAL, receipts, SQLite (hot), Parquet (cold), ACID guarantees

#### [ADR-0001f](./0001f-*.md): 0001F Memory Kernel

**Components:**

- **Memory Kernel** → Multi-Store
  - File: `k0/stores/`
  - Episodic, semantic, procedural, snapshots, affect, self-model, social

#### [ADR-0081](./0081-*.md): 0081 Knowledge Graph

**Components:**

- **Knowledge Graph** → Graph Schema
  - File: `k0/drivers/sqlite_kg.py`
  - 3-table design (nodes, edges, temporal_edges), entity types (Person, Location, Event, Organization, Thing), relationship types (parent, child, sibling, spouse, friend, employed_by, located_at, part...

- **Knowledge Graph** → Temporal Edges
  - File: `k0/kg/temporal_edges.py`
  - Relationship evolution tracking, bitemporal support (valid_from/valid_to for relationship evolution, created_at for insertion time), historical relationship queries, timeline queries ("Who was Alic...

- **Knowledge Graph** → Query API
  - File: `k0/query/kg_temporal.py`
  - 4 query categories (entity lookup, relationship queries, temporal queries, graph traversal), timeline queries with temporal edge filtering, entity lookup <10ms P95, relationship traversal <50ms P95...

- **Knowledge Graph** → Graph Traversal
  - File: `k0/kg/traversal.py`
  - BFS (Breadth-First Search) for shortest path in unweighted graphs O(V+E), DFS (Depth-First Search) for cycle detection and reachability O(V+E), Dijkstra for shortest path in weighted graphs O((V+E)...

- **Knowledge Graph** → Episodic Integration
  - File: `k0/kg/episodic_integration.py`
  - 4-stage extraction pipeline (NER → relationship extraction → entity resolution → KG update), P03 Consolidation integration (episodic → semantic → KG), spaCy en_core_web_lg model (96% accuracy), con...

- **Knowledge Graph** → Entity Extractor
  - File: `k0/kg/entity_extractor.py`
  - spaCy NER integration for Named Entity Recognition (PERSON, GPE, DATE, ORG), dependency parsing for relationship identification (nsubj, dobj, prep), pattern matching for relationship extraction, en...

- **Knowledge Graph** → Visualization
  - File: `k0/kg/visualization.py`
  - Mermaid export (graph LR format for ADRs and design docs), GraphML export (XML format for Gephi/Cytoscape/yEd), JSON export (structured format for API responses and programmatic access), debugging ...

- **Knowledge Graph** → KG Metrics
  - File: `k0/kg/metrics.py`
  - Real-time metrics (node count, edge count, query latency P50/P95/P99, entity resolution accuracy), historical trends (graph growth over time, query performance degradation), alerts (query latency >...

#### [ADR-0081a](./0081a-*.md): 0081A Knowledge Graph

**Components:**

- **Knowledge Graph** → Graph Schema
  - File: `k0/drivers/sqlite_kg.py`
  - 3-table design (nodes, edges, temporal_edges), entity types (Person, Location, Event, Organization, Thing), relationship types (parent, child, sibling, spouse, friend, employed_by, located_at, part...

- **Knowledge Graph** → Temporal Edges
  - File: `k0/kg/temporal_edges.py`
  - Relationship evolution tracking, bitemporal support (valid_from/valid_to for relationship evolution, created_at for insertion time), historical relationship queries, timeline queries ("Who was Alic...

#### [ADR-0081b](./0081b-*.md): 0081B Knowledge Graph

**Components:**

- **Knowledge Graph** → Query API
  - File: `k0/query/kg_temporal.py`
  - 4 query categories (entity lookup, relationship queries, temporal queries, graph traversal), timeline queries with temporal edge filtering, entity lookup <10ms P95, relationship traversal <50ms P95...

- **Knowledge Graph** → Graph Traversal
  - File: `k0/kg/traversal.py`
  - BFS (Breadth-First Search) for shortest path in unweighted graphs O(V+E), DFS (Depth-First Search) for cycle detection and reachability O(V+E), Dijkstra for shortest path in weighted graphs O((V+E)...

#### [ADR-0081c](./0081c-*.md): 0081C Knowledge Graph

**Components:**

- **Knowledge Graph** → Episodic Integration
  - File: `k0/kg/episodic_integration.py`
  - 4-stage extraction pipeline (NER → relationship extraction → entity resolution → KG update), P03 Consolidation integration (episodic → semantic → KG), spaCy en_core_web_lg model (96% accuracy), con...

- **Knowledge Graph** → Entity Extractor
  - File: `k0/kg/entity_extractor.py`
  - spaCy NER integration for Named Entity Recognition (PERSON, GPE, DATE, ORG), dependency parsing for relationship identification (nsubj, dobj, prep), pattern matching for relationship extraction, en...

#### [ADR-0081d](./0081d-*.md): 0081D Knowledge Graph

**Components:**

- **Knowledge Graph** → Visualization
  - File: `k0/kg/visualization.py`
  - Mermaid export (graph LR format for ADRs and design docs), GraphML export (XML format for Gephi/Cytoscape/yEd), JSON export (structured format for API responses and programmatic access), debugging ...

- **Knowledge Graph** → KG Metrics
  - File: `k0/kg/metrics.py`
  - Real-time metrics (node count, edge count, query latency P50/P95/P99, entity resolution accuracy), historical trends (graph growth over time, query performance degradation), alerts (query latency >...


### K0 Memory Consolidation

#### [ADR-0084](./0084-*.md): 0084 Core Architecture

**Components:**

- **Core Architecture** → 3-Layer Pipeline
  - File: `k0/consolidation/`
  - 5 consolidation processes (Hippocampal replay, Neocortical integration, Synaptic homeostasis, KG consolidation, Dream exploration), 90-minute sleep cycles (NREM Phase 1 45min, NREM Phase 2 30min, R...

- **Core Architecture** → Sleep Coordination
  - File: `k0/consolidation/scheduler.py`
  - SLEEP_SCHEDULER idle detection (CPU <5% for 15min, 2AM-5AM preferred, battery >30%), SLEEP_STATE_MACHINE (IDLE→NREM1→NREM2→REM→WAKING→IDLE), SLEEP_TRIGGER event coordination, K0 Offsets progress tr...

- **Core Architecture** → P03 Pipeline Integration
  - File: `k0/pipelines/p03_consolidation.py`
  - K0 WAL (evt_wal) → P03 fan-out, batch processing (1000 events/batch), priority LOW (nice +10), pausable on user activity, 5 consolidation handlers (CONS_HIPPOCAMPAL, CONS_NEOCORTICAL, CONS_SYNAPTIC...

- **Neocortical Integration** → Episodic→Semantic Transform
  - File: `k0/consolidation/neocortical_integration.py`
  - Pattern extraction (temporal patterns, location sequences, entity generalizations), embedding clustering (threshold 0.85), frequency threshold (≥3 occurrences), confidence scoring (≥0.70 to qualify...

- **Neocortical Integration** → Semantic Memory Creation
  - File: `k0/storage/semantic_memories.py`
  - K0::st_sqlite[semantic_memories] storage, pattern types (routine, preference, habit, concept), common entities/actions/temporal context extraction, source episode references, consolidation criteria...

- **Synaptic Homeostasis** → Forgetting & Pruning
  - File: `k0/consolidation/synaptic_homeostasis.py`
  - Stale data detector (last_accessed_ts >90 days, access_count=0, emotional_salience <0.30), Ebbinghaus exponential decay (retention = base^(-time/half_life), base=0.5, half_life=30 days), weak conne...

- **Synaptic Homeostasis** → Archival & Compression
  - File: `k0/storage/archived_memories.py`
  - K0::st_sqlite[archived_memories] table, archive criteria (>90 days, access_count=0, low salience), LZ4 compression, rollups/summaries (P15 integration), SQLite VACUUM every 30 days, ≥30% storage re...

#### [ADR-0084a](./0084a-*.md): 0084A Hippocampal Replay

**Components:**

- **Hippocampal Replay** → Pattern Strengthening
  - File: `k0/consolidation/hippocampal_replay.py`
  - CA3_CONSOLIDATION coordinator, 10-20x accelerated replay, 100-150 memories/NREM Phase 1, emotional salience prioritization (2x replay cycles for salience ≥0.70), access frequency weighting, recency...

- **Hippocampal Replay** → CA3 Recurrent Activation
  - File: `k0/ca3/recurrent_network.py`
  - CA3_RECURRENT association retrieval (~5-10 associated nodes per memory), temporal proximity (co-occurred within 5min), semantic similarity (embedding cosine ≥0.75), causal relationships (from KG_CA...

- **Hippocampal Replay** → Synaptic Strengthening
  - File: `k0/consolidation/synaptic_strengthening.py`
  - Hebbian learning (Δw = η *activation_src* activation_dst, η=0.03), Long-Term Potentiation (LTP) simulation (3+ replays →+10% weight boost), max weight 1.0, asymptotic saturation, replay speed modul...

- **Hippocampal Replay** → Theta Rhythm Coordination
  - File: `k0/ca1/theta_rhythm.py`
  - CA1_THETA oscillation generator (4-8 Hz), NREM theta 4-6 Hz (slow, consolidation), REM theta 6-8 Hz (fast, exploration), theta phase precession (encoding phase π-2π, retrieval phase 0-π), theta-gat...

#### [ADR-0084b](./0084b-*.md): 0084B Sleep State Machine

**Components:**

- **Sleep State Machine** → Idle Detection
  - File: `k0/consolidation/scheduler.py`
  - CPU <5% for 15min window, preferred 2AM-5AM, no user input (keyboard/mouse/touchscreen), battery >30%, Command Port queue <10 entries, fallback (any 3-hour idle), manual trigger (k0ctl consolidate ...

- **Sleep State Machine** → State Orchestration
  - File: `k0/consolidation/state_machine.py`
  - 5 states (IDLE, NREM_PHASE_1, NREM_PHASE_2, REM_PHASE, WAKING), 90-minute ultradian cycles, state durations (NREM1 45min, NREM2 30min, REM 15min, Waking 5min), interruption handling (pause on user ...

- **Sleep State Machine** → NREM Phase 1 Handler
  - File: `k0/consolidation/nrem_phase_1_handler.py`
  - Hippocampal replay execution (ADR-0084a integration), CA3_CONSOLIDATION coordination, 100-150 memories replayed, theta rhythm 4-6 Hz (slow theta), 45-minute phase duration, 2-3 memories/minute repl...

- **Sleep State Machine** → NREM Phase 2 Handler
  - File: `k0/consolidation/nrem_phase_2_handler.py`
  - Synaptic homeostasis (pruning), neocortical integration (episodic→semantic), 50-100 patterns extracted, 500-1000 connections pruned, knowledge graph consolidation, 30-minute phase duration, paralle...

- **Sleep State Machine** → REM Phase Handler
  - File: `k0/consolidation/rem_phase_handler.py`
  - Dream exploration (ADR-0084d integration), theta rhythm 6-8 Hz (fast theta), 5-10 insights generated, 3-5 counterfactuals, 5-10 skills rehearsed, 3-5 reflection prompts, 15-minute phase duration, c...

- **Sleep State Machine** → Waking Phase Handler
  - File: `k0/consolidation/waking_phase_handler.py`
  - Flush pending writes, P13 Index Rebuild integration, consolidation summary generation, infra.consolidation.complete event emission (cycle stats: memories_consolidated, patterns_extracted, insights_...

- **Resource Management** → CPU Priority & Affinity
  - File: `k0/consolidation/resource_limits.py`
  - Nice +10 (low CPU priority), ionice idle (Linux), CPU affinity (last 2 cores), BELOW_NORMAL_PRIORITY_CLASS (Windows), <5% average CPU usage, pausable on user activity, yield to user processes

- **Resource Management** → Memory & Disk Limits
  - File: `k0/consolidation/resource_limits.py`
  - Memory cap 256 MB (resource.setrlimit), batch size 1000 events (prevents memory spikes), disk I/O <5 MB/s, ionice idle class, async writes, fsync every 5min, pause if battery <30%, reduce frequency...

#### [ADR-0084c](./0084c-*.md): 0084C Knowledge Graph Consol.

**Components:**

- **Knowledge Graph Consol.** → Entity Extraction
  - File: `k0/consolidation/kg_consolidation.py`
  - 7 entity types (PERSON, PLACE, ORGANIZATION, CONCEPT, EVENT, TEMPORAL, OBJECT), Named Entity Recognition (NER) via linguistic_mapping, embedding clustering (threshold 0.85), canonical entity creati...

- **Knowledge Graph Consol.** → Relationship Inference
  - File: `k0/kg/relation_discovery.py`
  - 6 relationship types (CAUSAL, TEMPORAL, ASSOCIATIVE, HIERARCHICAL, POSSESSIVE, SOCIAL), co-occurrence detection (≥3 instances, temporal proximity <5min), KG_CAUSAL_GRAPH integration, PMI associatio...

- **Knowledge Graph Consol.** → Schema Evolution
  - File: `k0/kg/concept_evolution.py`
  - KG_CONCEPT_EVOLUTION engine, schema change detection (new entity/relation types ≥10/5 instances), concept merge/split, version control (K0::st_kg[schema_versions]), migration with rollback support,...

- **Knowledge Graph Consol.** → Temporal Reasoning
  - File: `k0/kg/temporal.py`
  - KG_TEMPORAL_ENGINE, time-stamped snapshots (node_id, timestamp, properties), 365-day retention, historical state queries ("What were Alice's interests last month?"), temporal range queries (track c...

#### [ADR-0084d](./0084d-*.md): 0084D Dream Exploration

**Components:**

- **Dream Exploration** → Explorative Dreaming
  - File: `k0/consolidation/dream_exploration.py`
  - DREAM_EXPLORATION semantic space random walks, K0::st_vector traversal, temperature-based sampling (0.70 balanced exploration/exploitation), 50 steps per REM phase, novel association detection (sem...

- **Dream Exploration** → Counterfactual Thinking
  - File: `k0/consolidation/counterfactual_simulator.py`
  - SIM_COUNTERFACTUAL integration, decision point identification, alternative sequence generation, KG_CAUSAL_GRAPH outcome prediction, 3-5 scenarios per REM Phase, counterfactual learning (better alte...

- **Dream Exploration** → Mental Rehearsal
  - File: `k0/consolidation/mental_rehearsal.py`
  - DREAM_REHEARSAL motor skill practice, K0::st_sqlite[motor_programs] simulation, procedural memory strengthening (rehearsal_count++, execution_speed *= 0.95, error_rate*= 0.90), 5-10 skills rehearse...

- **Dream Exploration** → Reflection Prompts
  - File: `k0/consolidation/reflection_prompt_generator.py`
  - 5 prompt types (MEMORY_GAP, UNRESOLVED_THREAD, GOAL_PROGRESS, EMOTIONAL_TREND, HABIT_INSIGHT), memory gap detection (expected events not logged), unresolved thread analysis (goals without progress)...


### K0 SSE Event Streaming

#### [ADR-0042a](./0042a-*.md): 0042A Event Production

**Components:**

- **Event Production** → WALReader Cursor-Based
  - File: `k0/sse/wal_reader.py`
  - Reads durable events from K0 WAL (config, receipts, learning, CRDT), 10ms polling interval, continuous background task, batch reading (max 100 events)

- **Event Production** → FanoutManager 1-to-N
  - File: `k0/sse/fanout_manager.py`
  - 1-to-N broadcasting (single K0 event → N K1 instances), topic-based filtering (wildcard patterns), <10ms delivery latency

- **Event Production** → TopicFilter Wildcard
  - File: `k0/sse/topic_filter.py`
  - Wildcard pattern matching (k0.config.* matches all config events), subscription filtering, future-proof subscriptions

- **Event Production** → EventBatcher Compression
  - File: `k0/sse/event_batcher.py`
  - Compression + batching for event delivery, zstd compression level 3, reduces bandwidth 40-60%

#### [ADR-0042d](./0042d-*.md): 0042D Backpressure

**Components:**

- **Backpressure** → K0BackpressureMonitor
  - File: `k0/sse/backpressure_monitor.py`
  - Detect slow consumers (>10K unACKed events OR >30s lag), track lag time (latest event - last ACK timestamp), emit backpressure metrics

- **Backpressure** → ConsumerDisconnector
  - File: `k0/sse/consumer_disconnector.py`
  - Graceful disconnect with reason (backpressure exceeded), protect K0 from slow consumers, K1 reconnects and catches up via replay

- **Persistence** → WALRetentionManager Cloud
  - File: `k0/wal/retention_manager_cloud.py`
  - Cloud Tier: 7-90 day retention policy (77GB WAL), daily compaction, delete old events (reclaim disk space)

- **Persistence** → WALCompactor
  - File: `k0/wal/compactor.py`
  - Delete old events from K0 WAL, reclaim disk space, efficient storage, optimize replay performance


### K1 Core

#### [ADR-0001](./0001-*.md): 0001 Memory Kernel

**Components:**

- **Architecture** → Dual-Kernel
  - File: `contracts/architecture/k0_k1_split.yml`
  - K0 (memory, P01-P20), K1 (intelligence, 52 modules), hybrid architecture, pure actors vs AI agents

#### [ADR-0004](./0004-*.md): 0004 Architecture

**Components:**

- **Architecture** → Layer Definitions
  - File: `contracts/architecture/layer_dependencies.yml`
  - Layer 1-5 structure, 52-module organization, microkernel design, hot path optimization, fault isolation, industry patterns

- **Architecture** → Module Manifest
  - File: `contracts/architecture/module_manifest.yml`
  - 58 modules, 5 layers, module boundaries, single responsibility, component classification, Actor Model

- **Dependencies** → Layer Rules
  - File: `contracts/architecture/layer_dependencies.yml`
  - L1→L5 only, L2→all, L3→L4+L5, L4→L5, L5→none, dependency direction

#### [ADR-0004b](./0004b-*.md): 0004B Dependencies

**Components:**

- **Dependencies** → Import Linting
  - File: `.importlinter`
  - import-linter, layering contracts, pre-commit hooks, CI enforcement, forbidden imports, escape hatches

- **Dependencies** → Layer Rules
  - File: `contracts/architecture/layer_dependencies.yml`
  - L1→L5 only, L2→all, L3→L4+L5, L4→L5, L5→none, dependency direction

#### [ADR-0004d](./0004d-*.md): 0004D Testing

**Components:**

- **Testing** → Integration Tests
  - File: `tests/integration/layer_test_base.py`
  - Layer-specific test suites, WARD framework, contract validation, performance budgets, P95 latency

- **Testing** → Layer 1 Tests
  - File: `tests/integration/layer1/`
  - Event publish, intent classification, stream processing, 3-tier routing, <50ms budget

- **Testing** → Layer 2 Tests
  - File: `tests/integration/layer2/`
  - 3-phase orchestration, planning pipeline, protocol validation, <250ms budget

- **Testing** → Layer 3 Tests
  - File: `tests/integration/layer3/`
  - Agent lifecycle, tool execution, Model Hub, <600ms hire, <3000ms tool call

- **Testing** → Layer 4 Tests
  - File: `tests/integration/layer4/`
  - SessionState serialization, learning loop, saga rollback, <1ms serialize

- **Testing** → Layer 5 Tests
  - File: `tests/integration/layer5/`
  - Event bus delivery, backpressure, thermal placement, <5ms delivery

- **Testing** → End-to-End Tests
  - File: `tests/integration/end_to_end/`
  - User turn, barge-in, multi-agent, <2000ms P95


### K1 Internal Event Bus

#### [ADR-0048](./0048-*.md): 0048 K0/K1 Separation

**Components:**

- **K0/K1 Separation** → K1 Ephemeral Only
  - File: `docs/architecture/k0_k1_event_separation.md`
  - K1 events ephemeral (no persistence), K0 SSE durable (config, receipts, learning)


### Message Queue & Coalescing

#### [ADR-0053](./0053-*.md): 0053 Main

**Components:**

- **Main** → Research Foundation
  - File: `docs/research/message_queue_research.md`
  - Nagle's Algorithm (TCP 1984), SEDA (2001), Token Bucket, Cooperative Cancellation (Go/Rust), Turn-taking pauses (2-3s)

#### [ADR-0053a](./0053a-*.md): 0053A Coalesce Window

**Components:**

- **Coalesce Window** → Rollout Strategy
  - File: `docs/rollout/message_queue_rollout.md`
  - Week 1 internal testing, Week 2 5% canary, Week 3-4 gradual to 100% (72h soak each stage)

- **Coalesce Window** → Future Work
  - File: `docs/roadmap/coalescing_enhancements.md`
  - Adaptive windows per user typing speed, context-aware coalescing (longer for complex), predictive flush (ML model)

#### [ADR-0053b](./0053b-*.md): 0053B Rate Limits

**Components:**

- **Rate Limits** → Future Work
  - File: `docs/roadmap/rate_limiting_enhancements.md`
  - Distributed rate limiting (Redis cross-instance), adaptive per-user limits (fast typers 7 msg/sec), per-tier system (premium/free), smart retry SDK

#### [ADR-0053c](./0053c-*.md): 0053C Cancel Path

**Components:**

- **Cancel Path** → K0 Bridge Integration
  - File: `k1/bridge_k0/k0_bridge_client.py`
  - rollback method (WAL transaction abort), pending_writes dict, logger.info k0_rollback (session_id, write_id)

- **Cancel Path** → Future Work
  - File: `docs/roadmap/cancellation_enhancements.md`
  - Predictive cancellation (ML model), partial result preservation (resume interrupted), cancellation batching (reduce overhead), cross-instance cancellation (distributed Redis)


### Multi-Device Family Sync

#### [ADR-0050](./0050-*.md): 0050 Sync Strategy

**Components:**

- **Sync Strategy** → Hybrid Strategy
  - File: `docs/architecture/multi_device_sync_strategy.md`
  - Phase 1 (LAN <1ms), Phase 2 (Internet <500ms), device-first privacy

- **Sync Strategy** → Device Autonomy
  - File: `docs/architecture/device_autonomy.md`
  - Each device runs K0+K1 full dual-kernel, no cloud intermediary, privacy-first


### OpenAPI 3.1 Specs

#### [ADR-0047](./0047-*.md): 0047 SDK Generation

**Components:**

- **SDK Generation** → OpenAPI Generator Config
  - File: `.openapi-generator/config.yml`
  - TypeScript (typescript-axios), Python (python), Go (go), package names, output dirs

- **SDK Generation** → TypeScript SDK
  - File: `sdks/typescript/`
  - Auto-generated from openapi.json, axios HTTP client, type-safe interfaces

- **SDK Generation** → Python SDK
  - File: `sdks/python/`
  - Auto-generated from openapi.json, requests HTTP client, type hints

- **SDK Generation** → Go SDK
  - File: `sdks/go/`
  - Auto-generated from openapi.json, net/http client, struct definitions

- **Security Schemes** → Bearer JWT
  - File: `k1/api/rest/security.py`
  - bearerAuth security scheme, Authorization header, JWT format, token validation

- **CI/CD** → OpenAPI Validation
  - File: `.github/workflows/openapi-validation.yml`
  - swagger-validator-action, validate spec on push/PR, fail if invalid schema

- **CI/CD** → SDK Generation Test
  - File: `.github/workflows/openapi-validation.yml`
  - Generate TypeScript SDK, test compilation, ensure SDK builds without errors


### REST API Dual Format

#### [ADR-0014b](./0014b-*.md): 0014B OpenAPI Generation

**Components:**

- **OpenAPI Generation** → FlatBuffers Parser
  - File: `tools/flatbuffers_parser.py`
  - Parse .fbs files, extract tables/enums/unions, regex-based parsing

- **OpenAPI Generation** → JSON Schema Mapper
  - File: `tools/json_schema_mapper.py`
  - FlatBuffers types → JSON Schema types, union → oneOf discriminator, 100% coverage

- **OpenAPI Generation** → OpenAPI 3.1 Spec
  - File: `api/openapi.json`
  - 8,450 lines auto-generated, 40 REST API schemas, paths + schemas + examples

- **OpenAPI Generation** → CI/CD Validation
  - File: `scripts/validate_openapi_spec.py`
  - Fail build if spec out of sync with schemas, <30s generation, 100% accuracy

#### [ADR-0014d](./0014d-*.md): 0014D Client SDKs

**Components:**

- **Client SDKs** → Python SDK (JSON)
  - File: `sdk/python/k1_client.py`
  - K1Client class, requests library, create_session/start_turn/recall/invoke_tool methods

- **Client SDKs** → Python SDK (FlatBuffers)
  - File: `sdk/python/k1_client_fb.py`
  - K1ClientFlatBuffers class, zero-copy deserialization, 50-100ms faster vs JSON

- **Client SDKs** → TypeScript SDK (JSON)
  - File: `sdk/typescript/k1-client.ts`
  - K1Client class, fetch API, browser + Node.js compatible, type-safe interfaces

- **Client SDKs** → TypeScript SDK (FlatBuffers)
  - File: `sdk/typescript/k1-client-fb.ts`
  - FlatBuffers npm package, Buffer serialization, axios for Node.js

- **Client SDKs** → curl Examples
  - File: `docs/api/curl_examples.md`
  - All 20 REST endpoints, JSON payloads, copy-paste ready, Accept/Content-Type headers

- **Client SDKs** → Migration Guide
  - File: `docs/api/MIGRATION_GUIDE.md`
  - When to use FlatBuffers, performance benchmarks (JSON 50ms vs FlatBuffers 5ms), trade-offs

- **Client SDKs** → Postman Collection
  - File: `api/postman_collection.json`
  - Auto-generated from OpenAPI spec, 20 endpoints, environment variables, examples

- **Client SDKs** → Performance Benchmarks
  - File: `benchmarks/json_vs_flatbuffers.py`
  - 1KB-10KB payloads, latency/size comparison, 50-100ms JSON vs 5-10ms FlatBuffers


### SSE Event Schemas

#### [ADR-0016](./0016-*.md): 0016 Event Taxonomy

**Components:**

- **Event Taxonomy** → Event Types
  - File: `k1/schemas/sse/event_envelope.fbs`
  - 17 event types, 5 categories, EventEnvelope, EventPayload union

- **Event Taxonomy** → Agent Lifecycle Events
  - File: `k1/schemas/sse/agent_events.fbs`
  - AgentHired, AgentFired, AgentCrashed, AgentRestarted (4 events)

- **Event Taxonomy** → Turn Events
  - File: `k1/schemas/sse/turn_events.fbs`
  - TurnStarted, TurnCompleted, TurnFailed, TurnInterrupted (4 events)

- **Event Taxonomy** → Tool Events
  - File: `k1/schemas/sse/tool_events.fbs`
  - ToolCallStarted, ToolCallCompleted, ToolCallFailed, ToolApprovalRequired (4 events)

- **Event Taxonomy** → Session Events
  - File: `k1/schemas/sse/session_events.fbs`
  - SessionCreated, SessionTerminated, SessionCrashed (3 events)

- **Event Taxonomy** → System Events
  - File: `k1/schemas/sse/system_events.fbs`
  - Heartbeat, Error (2 events, keepalive + notifications)

#### [ADR-0016a](./0016a-*.md): 0016A Event Taxonomy

**Components:**

- **Event Taxonomy** → Event Types
  - File: `k1/schemas/sse/event_envelope.fbs`
  - 17 event types, 5 categories, EventEnvelope, EventPayload union

- **Event Taxonomy** → Agent Lifecycle Events
  - File: `k1/schemas/sse/agent_events.fbs`
  - AgentHired, AgentFired, AgentCrashed, AgentRestarted (4 events)

- **Event Taxonomy** → Turn Events
  - File: `k1/schemas/sse/turn_events.fbs`
  - TurnStarted, TurnCompleted, TurnFailed, TurnInterrupted (4 events)

- **Event Taxonomy** → Tool Events
  - File: `k1/schemas/sse/tool_events.fbs`
  - ToolCallStarted, ToolCallCompleted, ToolCallFailed, ToolApprovalRequired (4 events)

- **Event Taxonomy** → Session Events
  - File: `k1/schemas/sse/session_events.fbs`
  - SessionCreated, SessionTerminated, SessionCrashed (3 events)

- **Event Taxonomy** → System Events
  - File: `k1/schemas/sse/system_events.fbs`
  - Heartbeat, Error (2 events, keepalive + notifications)

#### [ADR-0016c](./0016c-*.md): 0016C Filtering

**Components:**

- **Filtering** → Topic Mappings
  - File: `k1/config/sse_topics.yml`
  - 5 topics (agent_lifecycle, turn_execution, tool_execution, session_lifecycle, system_health)

- **Filtering** → Bandwidth Savings
  - File: `docs/architecture/sse_bandwidth_analysis.md`
  - 60-70% savings with topic filtering, all topics 6.5KB → filtered 2.2KB

#### [ADR-0016d](./0016d-*.md): 0016D Browser Integration

**Components:**

- **Browser Integration** → Native EventSource
  - File: `docs/api/sse_examples/vanilla_js.js`
  - Vanilla JS, browser-native, auto-reconnect, no SDK, Last-Event-ID

- **Browser Integration** → React Hook
  - File: `sdk/typescript/use_sse_events.ts`
  - useSSEEvents hook, connection state, onEvent callback, useEffect cleanup

- **Browser Integration** → TypeScript SDK
  - File: `sdk/typescript/k1_sse_client.ts`
  - K1SSEClient, Node.js eventsource polyfill, auth headers, reconnect

- **Browser Integration** → Connection State
  - File: `sdk/typescript/connection_state.ts`
  - CONNECTING/CONNECTED/DISCONNECTED/CLOSED, exponential backoff 3s→30s


### SSE Topic Taxonomy

#### [ADR-0043c](./0043c-*.md): 0043C Topic Routing

**Components:**

- **Topic Routing** → K0TopicRouter
  - File: `k0/sse/topic_router.py`
  - Route events from producers to consumers, subscription lookup, fanout strategy (broadcast vs consumer group), delivery tracking

- **Topic Routing** → At-Least-Once Delivery
  - File: `k0/sse/delivery_guarantees.py`
  - Cursor-based ACK for at-least-once delivery, retry on failure (exponential backoff), dead letter queue (DLQ) for terminal failures after 3 retries

- **Topic Routing** → Fanout Strategies
  - File: `k0/sse/fanout_strategies.py`
  - Broadcast all (all consumers receive event), consumer group one (load balance to one), routing metrics (delivery success rate, latency per topic)

- **Topic Routing** → Dead Letter Queue
  - File: `k0/sse/dlq_manager.py`
  - Store failed events (3 retries exhausted), 7-day DLQ retention, max 10K DLQ entries, supervisor alerts for DLQ overflow


### SSE-WebSocket Bridge

#### [ADR-0046](./0046-*.md): 0046 Configuration

**Components:**

- **Configuration** → Bridge Config
  - File: `k1/config/sse_bridge.yml`
  - Subscribed topics, max connections (10K), send_queue_size (100), backpressure_threshold (90%)


### Schema Versioning

#### [ADR-0013](./0013-*.md): 0013 SemVer Policy

**Components:**

- **SemVer Policy** → Version Bump Rules
  - File: `k1/config/versioning_policy.yml`
  - MAJOR (breaking: field removal/type change), MINOR (new optional field), PATCH (documentation)

- **SemVer Policy** → 90-Day Deprecation
  - File: `k1/config/deprecation_policy.yml`
  - 90-day minimum window, email/Slack/ADR notifications, (deprecated) attribute

- **SemVer Policy** → Breaking Changes
  - File: `docs/architecture/BREAKING_CHANGES.md`
  - Field removal, type change, new required field, field rename → MAJOR bump

- **SemVer Policy** → Backward Compatibility
  - File: `docs/architecture/COMPATIBILITY.md`
  - MINOR/PATCH versions backward-compatible, old clients ignore new optional fields

#### [ADR-0013a](./0013a-*.md): 0013A Version Registry

**Components:**

- **Version Registry** → Central Registry
  - File: `k1/config/schema_registry.yml`
  - 76 schemas × 3-5 versions = 228+ entries, version metadata, changelog, compatibility matrix

- **Version Registry** → Compatibility Matrix
  - File: `k1/config/schema_registry.yml`
  - Auto-generated: same MAJOR compatible, different MAJOR incompatible, forward/backward rules

- **Version Registry** → Deprecation Schedule
  - File: `k1/config/schema_registry.yml`
  - 90-day countdown per field, usage percentage, migration guide links, removal dates

- **Version Registry** → CLI Tool
  - File: `tools/k1_schema_version.py`
  - k1-schema-version check/deprecations/validate, <100ms latency, cached registry

#### [ADR-0013b](./0013b-*.md): 0013B CI/CD Automation

**Components:**

- **CI/CD Automation** → Schema Diff Analysis
  - File: `scripts/schema_diff_analyzer.py`
  - Parse old/new .fbs files, compute diff, detect MAJOR/MINOR/PATCH changes, <10s analysis

- **CI/CD Automation** → Version Bump Validation
  - File: `ci/validate_version_bump.py`
  - Fail build if version bump incorrect, <30s CI/CD latency, >95% accuracy

- **CI/CD Automation** → Changelog Generation
  - File: `scripts/generate_changelog.py`
  - Auto-generate CHANGELOG.md from schema diff, Git commit messages

- **CI/CD Automation** → GitHub Actions Workflow
  - File: `.github/workflows/schema-version-validation.yml`
  - Run on PR, validate version bumps, fail if incorrect, clear error messages

#### [ADR-0013c](./0013c-*.md): 0013C Deprecation Workflow

**Components:**

- **Deprecation Workflow** → FlatBuffers Annotations
  - File: `k1/schemas/**/*.fbs`
  - // DEPRECATED (date): reason, REMOVAL DATE, MIGRATION, [deprecated] attribute

- **Deprecation Workflow** → CI/CD Extraction
  - File: `scripts/extract_deprecations.py`
  - Daily cron job, parse .fbs files, extract DEPRECATED fields, update registry

- **Deprecation Workflow** → Email Notifications
  - File: `scripts/send_deprecation_emails.py`
  - 90/60/30/7 days before removal, <k1-dev@example.com>, clear migration guidance

- **Deprecation Workflow** → Slack Bot
  - File: `scripts/slack_deprecation_bot.py`
  - @K1-Schema-Bot, #schema-changes channel, interactive buttons, weekly digest

- **Deprecation Workflow** → Grafana Dashboard
  - File: `observability/dashboards/schema_deprecations.json`
  - Deprecation timeline, usage metrics %, 30-day alerts, top deprecated fields

#### [ADR-0013d](./0013d-*.md): 0013D Contract Testing

**Components:**

- **Contract Testing** → Pact-Style Tests
  - File: `tests/schemas/contract_tests.py`
  - Consumer-driven contracts, forward/backward compatibility tests, 228+ test cases

- **Contract Testing** → Forward Compatibility
  - File: `tests/schemas/test_forward_compat.py`
  - Old client v2.0.0 + new schema v2.1.0 → ✅, new optional fields ignored

- **Contract Testing** → Backward Compatibility
  - File: `tests/schemas/test_backward_compat.py`
  - New client v2.1.0 + old schema v2.0.0 → ✅, missing optional fields handled gracefully

- **Contract Testing** → Breaking Change Detection
  - File: `tests/schemas/test_breaking_changes.py`
  - Detect field removal, type change, new required field → fail tests

- **Contract Testing** → Multi-Version Matrix
  - File: `tests/schemas/test_matrix_generator.py`
  - 76 schemas × 3 versions × 2 directions = 456 test cases, parallelized <20 min

- **Contract Testing** → CI/CD Integration
  - File: `.github/workflows/schema-contract-tests.yml`
  - Run on schema PR, fail if breaking change without MAJOR bump


### Turn Boundary Management

#### [ADR-0054](./0054-*.md): 0054 Main

**Components:**

- **Main** → Research Foundation
  - File: `docs/research/turn_taking_research.md`
  - Sacks et al. 1974 turn-taking, TRP pauses 0.5-2.5s, Google/Alexa 1.5-2.5s thresholds, natural conversation flow

#### [ADR-0054a](./0054a-*.md): 0054A Implicit Pause

**Components:**

- **Implicit Pause** → Research Foundation
  - File: `docs/research/turn_taking_research.md`
  - Sacks et al. 1974 TRP 0.5-2.5s, Google 1.5-2.0s, Alexa 2.0-2.5s, Siri 1.8-2.2s silence thresholds

- **Implicit Pause** → Human Perception
  - File: `docs/research/turn_taking_research.md`
  - <1s pause mid-thought (don't interrupt), 1-2s ambiguous, >2s clear turn end (expect response)

- **Implicit Pause** → Future Work
  - File: `docs/roadmap/turn_boundary_enhancements.md`
  - Adaptive pause threshold per user typing speed (fast 1.5s, slow 2.5s), linguistic completeness detection (LLM check)

#### [ADR-0054b](./0054b-*.md): 0054B Explicit Submit

**Components:**

- **Explicit Submit** → Implementation Phases
  - File: `docs/implementation/explicit_submit_rollout.md`
  - Phase 1: WebSocket protocol, Phase 2: Desktop UI, Phase 3: Mobile UI, Phase 4: Voice commands

- **Explicit Submit** → UX Tests
  - File: `tests/ui/test_explicit_submit.py`
  - Send button click triggers submit, Enter key triggers submit, Shift+Enter triggers submit, voice "Send" command triggers submit


### Turn History Retention

#### [ADR-0021c](./0021c-*.md): 0021C Compliance

**Components:**

- **Compliance** → GDPR Article 5(e)
  - File: `docs/compliance/gdpr_retention.md`
  - "No longer than necessary", time-limited retention, 365-day baseline, legal rationale

- **Compliance** → GDPR Article 17
  - File: `docs/compliance/gdpr_deletion.md`
  - Right to erasure, 30-day grace period, user deletion API, compliance reporting

- **Compliance** → Retention Reports
  - File: `reports/retention_compliance.py`
  - Monthly compliance reports, deletion statistics, policy adherence, audit evidence


### Voice Pipeline Implementation

#### [ADR-0056](./0056-*.md): 0056 Pipeline Architecture

**Components:**

- **Pipeline Architecture** → K0ASRPipeline
  - File: `k0/pipelines/p11_asr/asr_pipeline.py`
  - K0 P11 pipeline: ASR frame buffering, VAD, ASR model inference (Whisper), partial transcript streaming

- **Pipeline Architecture** → K0TTSPipeline
  - File: `k0/pipelines/p12_tts/tts_pipeline.py`
  - K0 P12 pipeline: SSML generation, TTS model inference (VITS), audio streaming synthesis, opus/pcm codec

- **Pipeline Architecture** → ASR Frame Processing
  - File: `k0/pipelines/p11_asr/frame_processor.py`
  - 20ms frames, 80ms ring buffer, VAD energy calculation, partial transcript emission

- **Pipeline Architecture** → VAD Integration
  - File: `k0/pipelines/p11_asr/vad_detector.py`
  - 2s silence threshold (ADR-0054 turn boundary), energy_threshold_db=-50, RMS energy calculation

- **Pipeline Architecture** → Partial Transcript Streaming
  - File: `k0/pipelines/p11_asr/asr_pipeline.py`
  - return_partials=True flag, emit intermediate ASR results for typing indicator style, is_partial flag in transcript

- **Pipeline Architecture** → TTS Streaming Synthesis
  - File: `k0/pipelines/p12_tts/tts_pipeline.py`
  - synthesize_streaming method: text → SSML → TTS model → audio chunks, streaming response (async iterator)

- **Pipeline Architecture** → Prosody Controls
  - File: `k0/pipelines/p12_tts/prosody_controller.py`
  - response.prosody: pitch (Hz), rate (words/min), emphasis (stress patterns), SSML generation

- **Performance Budgets** → ASR Latency
  - File: `k0/pipelines/p11_asr/config.yml`
  - asr_frame_processing_ms: 100 (P95 target), asr_final_transcript_ms: 300 (end of speech → final transcript)

- **Performance Budgets** → TTS Latency
  - File: `k0/pipelines/p12_tts/config.yml`
  - tts_synthesis_first_chunk_ms: 200 (TTFA Time to First Audio), tts_synthesis_streaming_ms: 50 (subsequent chunks)

- **Metrics** → ASR Metrics
  - File: `observability/metrics/voice_pipeline_metrics.py`
  - asr_frame_processing_latency_ms histogram (buckets 10/50/100/200/500), K0 P11 owner

- **Metrics** → TTS Metrics
  - File: `observability/metrics/voice_pipeline_metrics.py`
  - tts_synthesis_latency_ms histogram (buckets 50/100/200/500/1000), K0 P12 owner

- **ASR Ingress** → Frame Handling
  - File: `k0/pipelines/p11_asr/frame_handler.py`
  - ADR-0056a: 20ms audio frames, buffering strategy, frame drop policy at 80% capacity

- **ASR Ingress** → VAD Processing
  - File: `k0/pipelines/p11_asr/vad_processor.py`
  - ADR-0056a: Voice Activity Detection, energy threshold -50dB, 2s silence threshold, RMS energy calculation

- **ASR Ingress** → Partial Results
  - File: `k0/pipelines/p11_asr/partial_result_emitter.py`
  - ADR-0056a: Stream intermediate ASR transcripts, is_partial flag, typing indicator UX, final transcript on turn boundary

- **TTS Synthesis** → Prosody Controls
  - File: `k0/pipelines/p12_tts/prosody_generator.py`
  - ADR-0056d: Pitch control (Hz), rate control (words/min), emphasis patterns (stress), SSML generation

- **TTS Synthesis** → SSML Generation
  - File: `k0/pipelines/p12_tts/ssml_generator.py`
  - ADR-0056d: Convert text + prosody to SSML, <prosody> tags, <emphasis> tags, <break> pauses

- **TTS Synthesis** → Streaming Audio
  - File: `k0/pipelines/p12_tts/streaming_synthesizer.py`
  - ADR-0056d: Chunk-based TTS synthesis, 40ms audio chunks, async iterator, VITS model

- **Audio Output** → Buffer Management
  - File: `k0/pipelines/p12_tts/audio_buffer_manager.py`
  - ADR-0056e: Jitter buffer (80ms), frame reordering, packet loss recovery, adaptive buffering

#### [ADR-0056a](./0056a-*.md): 0056A ASR Ingress

**Components:**

- **ASR Ingress** → Frame Handling
  - File: `k0/pipelines/p11_asr/frame_handler.py`
  - ADR-0056a: 20ms audio frames, buffering strategy, frame drop policy at 80% capacity

- **ASR Ingress** → VAD Processing
  - File: `k0/pipelines/p11_asr/vad_processor.py`
  - ADR-0056a: Voice Activity Detection, energy threshold -50dB, 2s silence threshold, RMS energy calculation

- **ASR Ingress** → Partial Results
  - File: `k0/pipelines/p11_asr/partial_result_emitter.py`
  - ADR-0056a: Stream intermediate ASR transcripts, is_partial flag, typing indicator UX, final transcript on turn boundary

#### [ADR-0056d](./0056d-*.md): 0056D TTS Synthesis

**Components:**

- **TTS Synthesis** → Prosody Controls
  - File: `k0/pipelines/p12_tts/prosody_generator.py`
  - ADR-0056d: Pitch control (Hz), rate control (words/min), emphasis patterns (stress), SSML generation

- **TTS Synthesis** → SSML Generation
  - File: `k0/pipelines/p12_tts/ssml_generator.py`
  - ADR-0056d: Convert text + prosody to SSML, <prosody> tags, <emphasis> tags, <break> pauses

- **TTS Synthesis** → Streaming Audio
  - File: `k0/pipelines/p12_tts/streaming_synthesizer.py`
  - ADR-0056d: Chunk-based TTS synthesis, 40ms audio chunks, async iterator, VITS model

#### [ADR-0056e](./0056e-*.md): 0056E Audio Output

**Components:**

- **Audio Output** → Buffer Management
  - File: `k0/pipelines/p12_tts/audio_buffer_manager.py`
  - ADR-0056e: Jitter buffer (80ms), frame reordering, packet loss recovery, adaptive buffering


### WebSocket Binary Protocol

#### [ADR-0015](./0015-*.md): 0015 Protocol Design

**Components:**

- **Protocol Design** → Message Envelope
  - File: `k1/schemas/websocket/message_envelope.fbs`
  - MessageEnvelope, 17 message types, protocol_version, sequence_number, trace_id

- **Protocol Design** → Message Types
  - File: `k1/schemas/websocket/message_types.fbs`
  - TURN_START, TOKEN_CHUNK, TOOL_CALL, BARGE_IN, PING/PONG (17 types)

- **Protocol Design** → Client→Server Messages
  - File: `k1/schemas/websocket/client_messages.fbs`
  - TurnStart, TurnChunk, BargeIn, ToolApproval (4 types)

- **Protocol Design** → Server→Client Messages
  - File: `k1/schemas/websocket/server_messages.fbs`
  - TokenChunk, ToolCall, ToolResult, StateDelta, GroundingCommit (7 types)

#### [ADR-0015a](./0015a-*.md): 0015A Protocol Design

**Components:**

- **Protocol Design** → Message Envelope
  - File: `k1/schemas/websocket/message_envelope.fbs`
  - MessageEnvelope, 17 message types, protocol_version, sequence_number, trace_id

- **Protocol Design** → Message Types
  - File: `k1/schemas/websocket/message_types.fbs`
  - TURN_START, TOKEN_CHUNK, TOOL_CALL, BARGE_IN, PING/PONG (17 types)

#### [ADR-0015b](./0015b-*.md): 0015B Flow Control

**Components:**

- **Flow Control** → ACK Protocol
  - File: `k1/schemas/websocket/ack.fbs`
  - ACK message, ack_seqno, batch 5 messages or 1s, <5% overhead

- **Flow Control** → ACK Manager Client
  - File: `sdk/typescript/ack_manager.ts`
  - AckManager, batched ACKs, unackedCount, lastAckTime tracking

#### [ADR-0015c](./0015c-*.md): 0015C Reconnection

**Components:**

- **Reconnection** → Resume Protocol
  - File: `k1/schemas/websocket/resume.fbs`
  - RESUME message, last_recv_seqno, ResumeResponse, 5 status codes

- **Reconnection** → Client Reconnect Manager
  - File: `sdk/typescript/reconnect_manager.ts`
  - ReconnectManager, exponential backoff 1s→16s, max 5 attempts

- **Reconnection** → Deduplication Manager
  - File: `sdk/typescript/dedup_manager.ts`
  - DeduplicationManager, 2000 seqno cache, skip replayed messages

#### [ADR-0015d](./0015d-*.md): 0015D Streaming

**Components:**

- **Streaming** → Token Schema
  - File: `k1/schemas/websocket/token_chunk.fbs`
  - TOKEN_CHUNK, chunk_index, logprob, finish_reason, model_id, tokens_generated

#### [ADR-0015e](./0015e-*.md): 0015E Client SDK

**Components:**

- **Client SDK** → TypeScript SDK Core
  - File: `sdk/typescript/k1_websocket.ts`
  - K1WebSocket class, binary WebSocket, FlatBuffers bindings, 1800 lines

- **Client SDK** → Reconnect Manager
  - File: `sdk/typescript/reconnect_manager.ts`
  - ReconnectManager, exponential backoff, RESUME message, 5 attempts max

- **Client SDK** → ACK Manager
  - File: `sdk/typescript/ack_manager.ts`
  - AckManager, batch 5 messages or 1s, flow control, periodic timer

- **Client SDK** → Deduplication Manager
  - File: `sdk/typescript/dedup_manager.ts`
  - DeduplicationManager, Set<number> cache, max 2000 entries, eviction

- **Client SDK** → React Hooks
  - File: `sdk/typescript/use_k1_websocket.ts`
  - useK1WebSocket, useTokenStreaming hooks, connection state, useEffect cleanup

- **Client SDK** → Message Serialization
  - File: `sdk/typescript/serialization.ts`
  - serializeEnvelope, deserializeEnvelope, FlatBuffers builder/reader, ArrayBuffer


---

## Usage Guidelines

1. **Before Development**: Review relevant ADRs to understand architectural decisions and constraints
2. **During Development**: Reference specific ADR sections for implementation details and patterns
3. **Code Reviews**: Verify implementations align with ADR specifications
4. **Updates**: If you modify an ADR, regenerate this file using `python scripts/generate_layer_adr_references.py`

## Legend

- **Family**: High-level architectural area (e.g., Actor Fabric, Bridge, K0 Core)
- **Components**: Specific implementation components covered by the ADR
- **File**: Python module path where component is implemented
- **N/A ADRs**: Cross-cutting concerns that apply to all layers

---

*This file is auto-generated. Do not edit manually. Regenerate using:*
```bash
python scripts/generate_layer_adr_references.py
```