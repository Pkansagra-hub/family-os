# Layer 4 (Runtime) — ADR Family Map

**Complete end-to-end ADR references for K1 Layer 4 modules**

---

## 📋 Overview

**Layer 4 Purpose:** Runtime (SessionState, Actor Fabric, API Gateway, Voice Pipeline, Learning, Ingress)
**Performance Budget:** <1ms SessionState ops, <1ms mailbox, <100ms learning, <500ms E2E voice turn
**Total Relevant ADRs:** 154 ADRs
**Coverage:** Runtime infrastructure, state management, ingress pipelines, voice/WebSocket, learning loops, API gateway
**Primary Function:** Runtime state + actor infrastructure + API ingress + voice pipeline + cognitive loops

---

## 📚 Complete ADR Reference List (154 ADRs)

### **K0 Core (6 ADRs)**
- ADR-0001 — Memory Kernel (K0 P01-P20 pipelines)
- ADR-0001f — State Management (multi-store: episodic, semantic, procedural)
- ADR-0081 — Knowledge Graph (3-table schema, temporal edges)
- ADR-0081a — Knowledge Graph Schema (nodes, edges, temporal_edges)
- ADR-0081b — Knowledge Graph Queries (BFS, DFS, Dijkstra, <50ms P95)
- ADR-0081c — Knowledge Graph Episodic Integration (NER, entity resolution)
- ADR-0081d — Knowledge Graph Visualization (Mermaid, GraphML, JSON export)

### **K0 Memory Consolidation (5 ADRs)**
- ADR-0084 — Core Architecture (3-layer pipeline, 90-min sleep cycles)
- ADR-0084a — Hippocampal Replay (CA3 recurrent, synaptic strengthening)
- ADR-0084b — Sleep State Machine (NREM1/NREM2/REM phases)
- ADR-0084c — Knowledge Graph Consolidation (entity extraction, relationship inference)
- ADR-0084d — Dream Exploration (random walks, counterfactual thinking)

### **Actor Model & Fabric (7 ADRs)**
- ADR-0002 — Actor Model (isolated actors, message passing, supervision trees)
- ADR-0002a — Mailbox (MPSC queue, 4-tier priority, WFQ scheduler, DLQ)
- ADR-0002b — Supervisor (heartbeat 1Hz, crash detection <100ms, blacklist)
- ADR-0002c — Router (location transparency, 5-check admission pipeline)

### **Agent Lifecycle (5 ADRs)**
- ADR-0005 — Lifecycle FSM (6-state: PENDING/WARMING/ACTIVE/IDLE/DRAINING/TERMINATED)
- ADR-0005b — IDLE Pooling (TTL tracking, reactivation <50ms, >80% hit rate)
- ADR-0005c — DRAINING State (3-phase drain, 5s timeout)
- ADR-0005d — Supervisor (heartbeat monitoring, blacklist manager)
- ADR-0005e — Personalities (4 AI agents + 54 pure actors)
- ADR-0086f — Dynamic Agent Lifecycle Integration (IDLE pool, create_or_reuse, <10ms reactivation)
- ADR-0086g — Agent Registry Extension (multi-index registry, 58+ types, O(1) lookups)

### **K1 Core Architecture (6 ADRs)**
- ADR-0004 — 52-Module 5-Layer Architecture (Layer 4 definition)
- ADR-0004b — Import Linting (L4→L5 only, no L4→L1/L2/L3)
- ADR-0004c — Documentation (module READMEs, auto-generation)
- ADR-0004d — Testing (Layer 4 integration tests)

### **Protocol Validation (8 ADRs)**
- ADR-0003 — PDL Language (YAML protocol parser, FSM compilation)
- ADR-0003a — PDL Language (compiler pipeline, <100ms compilation)
- ADR-0003b — Protocol Definitions (6 protocols: hire, task, clarification, barge-in, tool, saga)
- ADR-0003c — Protocol Monitor (FSM registry, validator, timeout enforcer)
- ADR-0003d — Security (role verifier, agent lease, message signer)

### **4-Stage Planning (1 ADR)**
- ADR-0007d — Stage 4 Commit (SessionState locking, flow_id, <0.1ms)

### **Saga Error Recovery (1 ADR)**
- ADR-0008d — Deadlock Handling (resource ordering, 5s timeout detection)

### **Capability Security (2 ADRs)**
- ADR-0010b — Assignment Policy (policy engine, agent capability mapper)
- ADR-0010c — Runtime Enforcement (validation <0.5ms, validation cache)

### **FlatBuffers Serialization (8 ADRs)**
- ADR-0011a — Schema Design (validator, naming conventions, deprecation)
- ADR-0011b — Code Generation (flatc v23.5.26, Python/C++/Rust bindings)
- ADR-0011c — Performance (SessionState 11× faster than JSON)
- ADR-0011d — Schema Evolution (version registry, migration scripts)

### **FlatBuffers Schemas (2 ADRs)**
- ADR-0012 — Schema Taxonomy (76 schemas, 9 categories)
- ADR-0012d — Layer 4 Schemas (HTTPRequest, WebSocketMessage, SSEEvent, AudioFrame)

### **Schema Versioning (5 ADRs)**
- ADR-0013 — SemVer Policy (MAJOR/MINOR/PATCH, 90-day deprecation)
- ADR-0013a — Version Registry (228+ entries, compatibility matrix)
- ADR-0013b — CI/CD Automation (schema diff, version bump validation)
- ADR-0013c — Deprecation Workflow (annotations, email/Slack notifications)
- ADR-0013d — Contract Testing (Pact-style, forward/backward compatibility)

### **REST API (9 ADRs)**
- ADR-0014 — Content Negotiation (Accept/Content-Type, JSON default)
- ADR-0014a — Content Negotiation (Accept header parsing, 406/415 errors)
- ADR-0014b — OpenAPI Generation (auto-derive from .fbs, 8,450 lines spec)
- ADR-0014c — Serialization Pipeline (JSON↔FlatBuffers, <5ms overhead)
- ADR-0014d — Client SDKs (Python, TypeScript, curl examples)

### **REST API Session Management (4 ADRs)**
- ADR-0041 — RESTful Principles (stateless, HTTP caching, HATEOAS)
- ADR-0041a — Session Lifecycle CRUD (POST/GET/PATCH/DELETE)
- ADR-0041b — Idempotency (Idempotency-Key header, 24h retention)
- ADR-0041c — Pagination (cursor-based, <100ms, infinite scroll)
- ADR-0041d — Documentation (OpenAPI 3.1, RFC 7807 problem details)

### **WebSocket Binary Protocol (6 ADRs)**
- ADR-0015 — Protocol Design (binary FlatBuffers, 17 message types)
- ADR-0015a — Message Routing (bidirectional, flow control)
- ADR-0015b — Flow Control (ACK protocol, batch 5 messages)
- ADR-0015c — Reconnection (resume protocol, exponential backoff)
- ADR-0015d — Streaming (model inference, TTFT <150ms, barge-in)
- ADR-0015e — Client SDK (TypeScript SDK, React hooks)

### **WebSocket Realtime Chat (5 ADRs)**
- ADR-0040 — Protocol Foundation (stateless, <20ms latency)
- ADR-0040a — Connection Management (lifecycle, heartbeat)
- ADR-0040b — Binary Serialization (FlatBuffers, <5ms)
- ADR-0040c — Backpressure Flow Control (bounded queue, slow client detection)
- ADR-0040d — Heartbeat Reconnection (30s heartbeat, resume protocol)

### **SSE Event Schemas (5 ADRs)**
- ADR-0016 — Event Taxonomy (17 event types, 5 categories)
- ADR-0016a — Event Taxonomy (agent lifecycle, turn, tool, session, system)
- ADR-0016b — Serialization (FlatBuffers→JSON, <2ms P95)
- ADR-0016c — Filtering (topic-based, 60-70% bandwidth savings)
- ADR-0016d — Browser Integration (native EventSource, React hook)

### **K0 SSE Event Streaming (2 ADRs)**
- ADR-0042a — Event Production (WALReader, FanoutManager, <10ms delivery)
- ADR-0042d — Backpressure (detect slow consumers, graceful disconnect)

### **SSE Topic Taxonomy (1 ADR)**
- ADR-0043c — Topic Routing (K0TopicRouter, at-least-once delivery, DLQ)

### **SSE-WebSocket Bridge (1 ADR)**
- ADR-0046 — Bridge Architecture (10 event mappings, <20ms latency)

### **SessionState 6-Section Design (7 ADRs)**
- ADR-0017 — Overall Architecture (6 sections, 64KB soft limit, voice continuity amendment)
- ADR-0017a — Beliefs Section (fact storage, confidence, LRU eviction)
- ADR-0017b — Scoreboard Section (QUD stack, entity tracking, salience decay)
- ADR-0017c — Control Section (agent leases, flow state, turn lock)
- ADR-0017d — Persona Section (personality traits, LLM prompt injection)
- ADR-0017e — Multimodal Section (audio/vision context, streaming state)
- ADR-0017f — Meta Section (telemetry, performance metrics, Prometheus export)

### **3-Tier Eviction Strategy (4 ADRs)**
- ADR-0018 — Eviction Architecture (soft 64KB, hard 128KB, OOM 256KB)
- ADR-0018a — Tier 1 Soft Eviction (LRU, priority eviction, <5ms)
- ADR-0018b — Tier 2 Hard Eviction (beliefs/scoreboard/multimodal, <3ms compression)
- ADR-0018c — Tier 3 OOM Prevention (critical state save, <10ms, session termination)

### **SessionState Serialization (5 ADRs)**
- ADR-0019 — Serialization Core (full <1ms, delta <0.5ms, zero-copy)
- ADR-0019a — Schema Definition (6 sections + delta schema)
- ADR-0019b — Serialization Core (dirty flag tracking, delta pipeline)
- ADR-0019c — K0 WAL Integration (5min checkpoint, sequence numbers)
- ADR-0019d — Serialization Core (zero-copy optimization, lazy proxies)

### **Multi-Tier Storage (4 ADRs)**
- ADR-0020 — Lifecycle Management (Hot→Warm→Cold migration)
- ADR-0020a — Hot Tier (L1 RAM: 56MB, <1ms access, LRU tracking)
- ADR-0020b — Warm Tier (L2 SSD: 100MB, <50ms, 30-day retention)
- ADR-0020c — Cold Tier (L3 Object: S3, <500ms, unlimited capacity)

### **Turn History Retention (2 ADRs)**
- ADR-0021 — Retention Policies (user deletion rights, GDPR Article 17)
- ADR-0021c — Compliance (GDPR Article 5(e), 365-day baseline)

### **K0 Bridge Batching (1 ADR)**
- ADR-0022d — FlatBuffers Schema (ReceiptBatch, zero-copy batch)

### **Cursor-Based Pagination (4 ADRs)**
- ADR-0023 — Pagination Core (opaque cursor, O(1) seek, <50ms)
- ADR-0023a — Cursor Encoding (HMAC SHA-256, Base64, versioning)
- ADR-0023b — REST API (pagination metadata, total count, rate limiting)
- ADR-0023c — K0 WAL Query (query optimization, cold tier fallback)

### **Performance Budgets (5 ADRs)**
- ADR-0024 — Component-Level Budgets (grounding act <30ms)
- ADR-0024b — Component-Level Budgets (detailed breakdown)
- ADR-0024c — Memory Budgets (64KB soft, 128KB hard, 256KB OOM)
- ADR-0024d — Graceful Degradation (backpressure, user transparency)

### **Thermal Management (2 ADRs)**
- ADR-0026 — User Notifications (emergency notifications, recovery)
- ADR-0026d — User Notifications (WebSocket/SSE events)

### **Prometheus Metrics (2 ADRs)**
- ADR-0029 — Turn-Level (TTFT, E2E latency, barge-in metrics)
- ADR-0029b — Turn-Level (detailed metric definitions)

### **JWT Authentication (5 ADRs)**
- ADR-0037 — Horizontal Scaling (stateless validation, public key distribution)
- ADR-0037a — Token Generation (RS256, 1h access + 7d refresh tokens)
- ADR-0037b — Token Validation (<2ms, signature + expiry + blacklist)
- ADR-0037c — Refresh Token Flow (single-use, rotation, <100ms)
- ADR-0037d — Session Binding (space isolation, RBAC, privacy band enforcement)

### **OpenAPI 3.1 Specs (1 ADR)**
- ADR-0047 — Auto-Generation (FastAPI annotations, Swagger UI, ReDoc)

### **K1 Internal Event Bus (1 ADR)**
- ADR-0048 — Bus Architecture (actor model integration, ephemeral events)

### **Fast/Smart Lane Router (1 ADR)**
- ADR-0049 — Configuration (configurable weights, hot-reload)

### **Multi-Device Family Sync (2 ADRs)**
- ADR-0050 — Sync Strategy (hybrid LAN + Internet, device-first privacy)
- ADR-0050a — SessionState Coherence (per-device guarantees, delta journal)

### **Enhanced HITL Protocols (5 ADRs)**
- ADR-0052 — Performance (step-by-step <10ms, 7-year audit, WARD tests)
- ADR-0052a — Step-by-Step Approval (K0 WAL checkpoint, WorkflowState FSM)
- ADR-0052b — RED Band Approval (audit trail, forcing functions)
- ADR-0052c — Nested Clarifications (clarification stack, max depth 3)
- ADR-0052d — Proactive Confirmation (confidence-based, feedback signals)
- ADR-0052e — Layer 4 Communication (clarification/step-by-step/RED band schemas)

### **Message Queue & Coalescing (4 ADRs)**
- ADR-0053 — Main (FIFO queue, 2s coalesce window, 5 msg/sec rate limit)
- ADR-0053a — Coalesce Window (2s timer, 5-message limit, bypass conditions)
- ADR-0053b — Rate Limits (token bucket, 5 msg/sec + 3 burst)
- ADR-0053c — Cancel Path (4-stage cascade <120ms, cancellation token)

### **Turn Boundary Management (4 ADRs)**
- ADR-0054 — Main (dual-signal: implicit pause ≥2s OR explicit submit)
- ADR-0054a — Implicit Pause (2s threshold, text + voice VAD)
- ADR-0054b — Explicit Submit (Enter/Send button, keyboard shortcuts)
- ADR-0054c — MPST Transitions (IDLE→USER_SPEAKING→AGENT_TURN→IDLE)

### **Context-Switch Detection (4 ADRs)**
- ADR-0055 — Main Detection (3-stage: intent drift + discourse markers + confirmation)
- ADR-0055a — Intent Drift Rules (3-level taxonomy, drift score 0.0-2.0)
- ADR-0055b — Switch Prompt (3 confidence templates, voice variants)
- ADR-0055c — History Management (new/continue/go_back, session stack)

### **Voice Pipeline Implementation (6 ADRs)**
- ADR-0056 — Pipeline Architecture (5-stage: Audio→ASR→Intent→Tools→TTS→Audio)
- ADR-0056a — ASR Ingress (20ms frames, VAD, partial results)
- ADR-0056b — Intent Bridge (K1 orchestrator integration)
- ADR-0056c — Tool Interleaving (tool execution during voice)
- ADR-0056d — TTS Synthesis (prosody controls, SSML, streaming)
- ADR-0056e — Audio Output (jitter buffer 80ms, packet loss recovery)

### **Voice Backpressure (3 ADRs)**
- ADR-0057a — Frame Drop Policy (2-tier: 80-90% drop, 90%+ downsample)
- ADR-0057b — TTS Degradation (5-level ladder: Full→Emergency, MOS 4.3→2.7)
- ADR-0057c — Barge-in Preemption (fast stop <120ms, context preservation)

### **Adaptive KV Cache (3 ADRs)**
- ADR-0060 — Management Core (dynamic placement, eviction policies)
- ADR-0060a — Dynamic Placement (region assignment, thermal-aware)
- ADR-0060b — Eviction & Recovery (hot/cold eviction, rollback)

### **Voice Quality (1 ADR)**
- ADR-0068 — Voice Quality (WER calculation, MOS estimation)

### **KV Cache Optimization (1 ADR)**
- ADR-0076 — Compression Tier (ZSTD 25-35%, priority-aware LRU)

### **Thermal Placement V2 (1 ADR)**
- ADR-0077 — Thermal Profiling (per-device metrics, placement engine)

### **Multi-Party Dialogue (1 ADR)**
- ADR-0082 — Core Architecture (SessionState extension, multi-speaker turn state)

### **Embodied Awareness (1 ADR)**
- ADR-0085 — Core Architecture (multi-device presence, SessionState extension)

---

## 🗺️ Layer 4 Component Map

### **Component 1: SessionState Management**
**Location:** `k1/l4_runtime/session_state/`
**ADRs:** 22 ADRs (0017-0017f, 0018-0018c, 0019-0019d, 0020-0020c, 0024c)

**Sub-Components:**
- **model/** — 6-section design (ADR-0017)
- **control/** — Locking, flow control (ADR-0017c, 0007d)
- **memory_manager/** — 3-tier eviction (ADR-0018, 0018a-c)
- **serialization/** — FlatBuffers (ADR-0019, 0019a-d)
- **storage/** — Multi-tier (ADR-0020, 0020a-c)

**Performance:**
- Serialize: <1ms P95 (64KB)
- Deserialize: <0.1ms P95
- Eviction: <5ms P95
- Size: 64KB soft, 128KB hard, 256KB OOM

---

### **Component 2: Actor Fabric**
**Location:** `k1/l4_runtime/actor_fabric/`
**ADRs:** 7 ADRs (0002, 0002a-c, 0005, 0005b-e)

**Sub-Components:**
- **mailbox/** — MPSC queue, 4-tier priority (ADR-0002a)
- **router/** — Admission control, 5-check pipeline (ADR-0002c)
- **supervisor/** — Heartbeat, crash detection, blacklist (ADR-0002b)

**Performance:**
- Mailbox enqueue: <1ms P95
- Mailbox dequeue: <0.5ms P95
- Router admission: <2ms P95 (5 checks)
- Crash detection: <100ms P95

---

### **Component 2.5: Dynamic Agent Lifecycle Integration**
**Location:** `k1/l4_runtime/agent_lifecycle/idle_pool_manager.py`
**ADRs:** 1 ADR (0086f)

**Sub-Components:**
- **idle_pool/** — IDLE pool manager, create_or_reuse (ADR-0086f)
- **termination_policies/** — 5 termination policies (ADR-0086f)

**Performance:**
- Reactivation: <10ms P95 (vs 100ms creation)
- Pool hit rate: >60%
- IDLE timeout: 60s (task-specific agents)

---

### **Component 2.6: Agent Registry Extension**
**Location:** `k1/l4_runtime/agent_fabric/registry.py`
**ADRs:** 1 ADR (0086g)

**Sub-Components:**
- **multi_index_registry/** — 5 indexes (type, session, state, capability, primary) (ADR-0086g)
- **agent_specs/** — 58+ agent type specifications YAML (ADR-0086g)

**Performance:**
- Lookup (single index): <1ms P95 (O(1))
- Lookup (combined query): <2ms P95 (3 filters)
- Registry size: 58+ agent types

---

### **Component 3: API Gateway (REST)**
**Location:** `k1/l4_ingress/api_gateway/`
**ADRs:** 13 ADRs (0014-0014d, 0041-0041d)

**Sub-Components:**
- **content_negotiation/** — JSON/FlatBuffers (ADR-0014, 0014a)
- **openapi/** — Spec generation (ADR-0014b, 0047)
- **serialization/** — JSON↔FlatBuffers (ADR-0014c)
- **sessions/** — CRUD operations (ADR-0041, 0041a)
- **pagination/** — Cursor-based (ADR-0023, 0023a-c, 0041c)
- **auth/** — JWT validation (ADR-0037, 0037a-d)

**Performance:**
- Content negotiation: <1ms
- Serialization: <5ms overhead
- Pagination: <100ms P95
- JWT validation: <2ms P95

---

### **Component 4: WebSocket Server**
**Location:** `k1/l4_ingress/websocket/`
**ADRs:** 11 ADRs (0015-0015e, 0040-0040d)

**Sub-Components:**
- **protocol/** — Binary FlatBuffers (ADR-0015, 0015a)
- **flow_control/** — ACK, backpressure (ADR-0015b, 0040c)
- **reconnection/** — Resume protocol (ADR-0015c, 0040d)
- **streaming/** — Model inference (ADR-0015d)

**Performance:**
- Message latency: <20ms P95
- Serialization: <5ms
- Reconnection: <500ms

---

### **Component 5: SSE Gateway**
**Location:** `k1/l4_ingress/sse_gateway/`
**ADRs:** 9 ADRs (0016-0016d, 0042a, 0042d, 0043c, 0046)

**Sub-Components:**
- **event_taxonomy/** — 17 event types (ADR-0016, 0016a)
- **serialization/** — FlatBuffers→JSON (ADR-0016b)
- **filtering/** — Topic-based (ADR-0016c)
- **browser/** — EventSource integration (ADR-0016d)
- **bridge/** — SSE→WebSocket (ADR-0046)

**Performance:**
- Serialization: <2ms P95
- Event delivery: <10ms
- Bandwidth savings: 60-70% (filtering)

---

### **Component 6: Voice Pipeline**
**Location:** `k1/l4_ingress/voice_pipeline/`
**ADRs:** 10 ADRs (0056-0056e, 0057a-c, 0068)

**Sub-Components:**
- **asr_ingress/** — ASR integration (ADR-0056a)
- **intent_bridge/** — Intent classification (ADR-0056b)
- **tool_interleaving/** — Tool execution (ADR-0056c)
- **tts_synthesis/** — TTS streaming (ADR-0056d)
- **audio_output/** — Jitter buffer (ADR-0056e)
- **backpressure/** — Frame drop, TTS degradation (ADR-0057a-b)
- **barge_in/** — Fast stop <120ms (ADR-0057c)

**Performance:**
- E2E voice turn: <500ms P95
- ASR latency: <100ms
- TTS latency: <200ms
- Barge-in stop: <120ms P95

---

### **Component 7: Message Queue**
**Location:** `k1/l4_ingress/websocket/message_queue/`
**ADRs:** 4 ADRs (0053-0053c)

**Sub-Components:**
- **queue/** — FIFO per-session (ADR-0053)
- **coalescing/** — 2s window, 5-message limit (ADR-0053a)
- **rate_limiter/** — Token bucket 5 msg/sec (ADR-0053b)
- **cancellation/** — 4-stage cascade <120ms (ADR-0053c)

**Performance:**
- Coalesce window: 2s
- Rate limit: 5 msg/sec + 3 burst
- Cancellation: <120ms P95

---

### **Component 8: Turn Boundary**
**Location:** `k1/l4_ingress/websocket/turn_boundary/`
**ADRs:** 4 ADRs (0054-0054c)

**Sub-Components:**
- **detector/** — Dual-signal detection (ADR-0054)
- **implicit_pause/** — 2s threshold (ADR-0054a)
- **explicit_submit/** — Enter/Send button (ADR-0054b)
- **protocol_monitor/** — MPST transitions (ADR-0054c)

**Performance:**
- Detection latency: <50ms
- MPST validation: <5ms
- Timeout: 30s USER_SPEAKING, 60s AGENT_TURN

---

### **Component 9: Context Switch**
**Location:** `k1/l4_runtime/intent_switch/`
**ADRs:** 4 ADRs (0055-0055c)

**Sub-Components:**
- **detector/** — 3-stage detection (ADR-0055)
- **drift_calculator/** — Intent drift 0.0-2.0 (ADR-0055a)
- **prompt_generator/** — Confidence templates (ADR-0055b)
- **session_manager/** — History management (ADR-0055c)

**Performance:**
- Drift calculation: <10ms
- Prompt generation: <50ms
- Session archiving: <100ms

---

### **Component 10: Learning Loop**
**Location:** `k1/l4_runtime/learning/`
**ADRs:** 3 ADRs (0018, 0018a-b)

**Sub-Components:**
- **feedback/** — Signal integration (ADR-0018a)
- **self_model/** — Belief revision (ADR-0018b)
- **regret/** — Counterfactual reasoning (ADR-0018c)

**Performance:**
- Learning cycle: <100ms P95
- Feedback latency: <50ms
- Belief update: <10ms P95

---

### **Component 11: Protocol Monitor**
**Location:** `k1/l4_runtime/protocol_monitor/`
**ADRs:** 8 ADRs (0003-0003d)

**Sub-Components:**
- **pdl_parser/** — YAML protocol parser (ADR-0003, 0003a)
- **fsm_registry/** — Compiled FSM storage (ADR-0003c)
- **validator/** — Message validation <5ms (ADR-0003c)
- **timeout_enforcer/** — Per-protocol timeout (ADR-0003c)
- **role_verifier/** — Security validation (ADR-0003d)

**Performance:**
- Parse: <5ms P95
- Validation: <5ms P95
- Compilation: <100ms

---

### **Component 12: HITL Protocols**
**Location:** `k1/l4_runtime/hitl/`
**ADRs:** 5 ADRs (0052-0052e)

**Sub-Components:**
- **step_by_step/** — Workflow checkpoints (ADR-0052a)
- **red_band/** — Audit trail 7 years (ADR-0052b)
- **clarification/** — Stack max depth 3 (ADR-0052c)
- **proactive/** — Confidence-based (ADR-0052d)

**Performance:**
- Checkpoint: <10ms P95
- Audit write: <20ms
- Clarification: <50ms

---

### **Component 13: Knowledge Graph**
**Location:** `k0/kg/` (K0 integration)
**ADRs:** 4 ADRs (0081-0081d)

**Sub-Components:**
- **schema/** — 3-table design (ADR-0081a)
- **queries/** — BFS/DFS/Dijkstra (ADR-0081b)
- **integration/** — Episodic NER (ADR-0081c)
- **visualization/** — Mermaid/GraphML (ADR-0081d)

**Performance:**
- Entity lookup: <10ms P95
- Relationship traversal: <50ms P95
- NER accuracy: 96%

---

### **Component 14: Memory Consolidation**
**Location:** `k0/consolidation/` (K0 integration)
**ADRs:** 5 ADRs (0084-0084d)

**Sub-Components:**
- **scheduler/** — Sleep coordination (ADR-0084b)
- **hippocampal/** — CA3 replay (ADR-0084a)
- **kg_consolidation/** — Entity extraction (ADR-0084c)
- **dream/** — Random walks (ADR-0084d)

**Performance:**
- Sleep cycle: 90 minutes
- Memories replayed: 100-150 per NREM1
- Patterns extracted: 50-100 per NREM2

---

### **Component 15: Adaptive KV Cache**
**Location:** `k1/l4_runtime/kv_cache/`
**ADRs:** 3 ADRs (0060-0060b, 0076)

**Sub-Components:**
- **placement/** — Thermal-aware (ADR-0060a)
- **eviction/** — Hot/cold policies (ADR-0060b)
- **compression/** — ZSTD level 3 (ADR-0076)

**Performance:**
- Placement: <50ms P95
- Eviction: <20ms
- Compression: <1ms P95

---

### **Component 16: Multi-Device Sync**
**Location:** `k1/l4_runtime/sync/`
**ADRs:** 2 ADRs (0050, 0050a)

**Sub-Components:**
- **strategy/** — Hybrid LAN + Internet (ADR-0050)
- **coherence/** — Delta journal (ADR-0050a)

**Performance:**
- LAN sync: <1ms
- Internet sync: <500ms
- Crash recovery: <2s

---

## 🎯 Layer 4 Performance Budget Breakdown

| Component | Budget | Typical | P95 | ADR |
|-----------|--------|---------|-----|-----|
| **SessionState** |
| Serialize | 1ms | 0.5ms | 1ms | ADR-0019 |
| Deserialize | 0.1ms | 0.05ms | 0.1ms | ADR-0019 |
| Eviction | 5ms | 3ms | 5ms | ADR-0018 |
| **Actor Fabric** |
| Mailbox enqueue | 1ms | 0.5ms | 1ms | ADR-0002a |
| Mailbox dequeue | 0.5ms | 0.3ms | 0.5ms | ADR-0002a |
| Router admission | 2ms | 1ms | 2ms | ADR-0002c |
| Crash detection | 100ms | 50ms | 100ms | ADR-0002b |
| **API Gateway** |
| REST endpoint | 100ms | 50ms | 100ms | ADR-0041 |
| JWT validation | 2ms | 1.5ms | 2ms | ADR-0037b |
| Pagination | 100ms | 78ms | 100ms | ADR-0023 |
| **WebSocket** |
| Message latency | 20ms | 10ms | 20ms | ADR-0040 |
| Serialization | 5ms | 3ms | 5ms | ADR-0040b |
| **SSE** |
| Event delivery | 10ms | 5ms | 10ms | ADR-0042a |
| Serialization | 2ms | 1ms | 2ms | ADR-0016b |
| **Voice Pipeline** |
| E2E voice turn | 500ms | 300ms | 500ms | ADR-0056 |
| Barge-in stop | 120ms | 80ms | 120ms | ADR-0057c |
| **Learning** |
| Learning cycle | 100ms | 50ms | 100ms | ADR-0018 |
| **Protocol** |
| Validation | 5ms | 2ms | 5ms | ADR-0003c |

---

## 🔗 Cross-Cutting ADRs

### **Serialization & Data (15 ADRs)**
- ADR-0011 — FlatBuffers (all Layer 4 components)
- ADR-0011a-d — Schema design, code generation, performance
- ADR-0012, 0012d — Schema taxonomy, Layer 4 schemas
- ADR-0013, 0013a-d — Schema versioning, SemVer policy
- ADR-0019, 0019a-d — SessionState serialization

### **Observability (2 ADRs)**
- ADR-0029, 0029b — Prometheus metrics (turn-level)
- ADR-0030 — Trace sampling (cognitive_trace_id)

### **Performance & Reliability (8 ADRs)**
- ADR-0024, 0024b-d — Performance budgets, graceful degradation
- ADR-0026, 0026d — Thermal management, user notifications
- ADR-0060, 0060a-b — Adaptive KV cache
- ADR-0076 — KV cache compression
- ADR-0077 — Thermal profiling

### **Security & Privacy (7 ADRs)**
- ADR-0010b-c — Capability security
- ADR-0037, 0037a-d — JWT authentication
- ADR-0003d — Protocol security

### **API & Communication (25 ADRs)**
- ADR-0014-0014d — REST API dual format
- ADR-0015-0015e — WebSocket binary protocol
- ADR-0016-0016d — SSE event schemas
- ADR-0040-0040d — WebSocket realtime chat
- ADR-0041-0041d — REST API session management
- ADR-0046 — SSE-WebSocket bridge
- ADR-0047 — OpenAPI generation

### **Testing & Quality (3 ADRs)**
- ADR-0004d — Layer 4 integration tests
- ADR-0013d — Contract testing
- ADR-0052 — HITL WARD tests

---

## 📊 Layer 4 Statistics

**Total ADRs:** 156
**By Category:**
- SessionState & Storage: 22 ADRs
- Actor Fabric: 9 ADRs (includes ADR-0086f, 0086g for dynamic agent integration)
- API Gateway (REST): 13 ADRs
- WebSocket: 11 ADRs
- SSE: 9 ADRs
- Voice Pipeline: 10 ADRs
- Message Queue & Turn Boundary: 8 ADRs
- Context Switching: 4 ADRs
- Learning & HITL: 8 ADRs
- Protocol Validation: 8 ADRs
- Knowledge Graph: 4 ADRs
- Memory Consolidation: 5 ADRs
- Serialization & Schemas: 15 ADRs
- Authentication & Security: 12 ADRs
- Performance & Thermal: 8 ADRs
- Multi-Device & Embodied: 4 ADRs
- Cross-Cutting: 6 ADRs

**By Status:**
- ✅ Complete: 156 ADRs (100%)

**By Priority:**
- 🔴 CRITICAL: 10 ADRs (core architecture)
- 🟡 HIGH: 62 ADRs (essential features, includes dynamic agent ADRs)
- 🟢 MEDIUM: 70 ADRs (supporting features)
- ⚪ LOW: 14 ADRs (optimization)

---

**Status:** ✅ **COMPLETE** — All Layer 4 ADRs mapped end-to-end
**Last Updated:** October 2025
**Total ADRs:** 156 ADRs covering Layer 4 runtime infrastructure
**Coverage:** 100% of Layer 4 components (SessionState, Actor Fabric + Dynamic Agent Integration, API Gateway, Voice Pipeline, WebSocket, SSE, Learning, Protocol Monitor, KV Cache, Knowledge Graph, Multi-Device)
**Source:** Auto-generated from ADR_REFERENCE.md comprehensive analysis
