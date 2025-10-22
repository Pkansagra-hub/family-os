# K1 Intelligence Module - Contract Development Plan

**Purpose:** End-to-end plan for creating all contracts from ADRs with clear milestones, epics, and issues.

**Status:** 📋 PLANNING PHASE
**Last Updated:** 2025-10-13
**Owner:** Contract Development Team
**Timeline:** 12 weeks (3 months)

---

## 📊 Executive Summary

**Total Scope:**

- **206 ADRs analyzed** (0001-0050 including sub-ADRs, ADRs 0001-0041 fully detailed)
- **22 contract categories** identified
- **~741 contract files** to create (expanded from 649 after ADR 0039-0041 review, +92 files)
- **4 major milestones** over 12 weeks
- **33 epics** across contract domains
- **~129 implementation issues** (detailed below, comprehensive coverage)

**Major Expansions After ADR 0001-0035 Review:**

- ✅ **Epic 3.3 added:** K0 Pipeline Contracts (P01-P20) - 60 files (20 pipelines × 3 files each)
- ✅ **Epic 2.6 added:** MPST Protocol Detailed Contracts (6 protocols) - 54 files (9 per protocol)
- ✅ **Epic 3.2.3 expanded:** SSE Event Schemas (17 events) - 25 files (17 FlatBuffers + envelope + serializer + 5 filters + browser SDK)
- ✅ **Epic 4.1.1 expanded:** SessionState 6-Section - 21 files (6 sections × 3-4 contracts each: schema + manager + logic)
- ✅ **Epic 4.1.2 expanded:** 3-Tier Eviction Strategy - 15 files (Tier 1: 6, Tier 2: 5, Tier 3: 2, Infrastructure: 2) from 4 files (+11 files)
- ✅ **Epic 4.1.3 expanded:** SessionState Serialization - 27 files (7 root schemas + 7 type schemas + 6 pipeline + 7 coherence) from 7 files (+20 files)
- ✅ **Epic 4.2.1 expanded:** Multi-Tier Storage - 17 files (Hot: 5, Warm: 6, Cold: 6) from 5 files (+12 files)
- ✅ **Epic 4.2.2 expanded:** Turn History Retention & K0 Batching - 22 files (Retention: 10, Batching: 12) from 7 files (+15 files)
- ✅ **Epic 4.2.3 expanded:** Cursor-Based Pagination - 10 files (Encoding: 3, API: 4, Query: 3) from 4 files (+6 files)
- ✅ **Epic 4.3.1 expanded:** Performance Budget Contracts - 15 files (Turn: 3, Component: 5, Memory: 3, Degradation: 4) from 5 files (+10 files)
- ✅ **Epic 4.3.2 expanded:** KV Cache Management Contracts - 16 files (Allocator: 1, Eviction: 3, Allocation: 2, Warming: 2, Compression: 3, Protection: 2, Metrics: 2, Fragmentation: 1) from 6 files (+10 files)
- ✅ **Epic 4.3.3 expanded:** Thermal & Placement Contracts - 28 files (Thermal: 13 + Model Placement: 15) from 13 files (+15 files)
- ✅ **Epic 4.3.4 expanded:** WFQ Scheduler Contracts - 10 files (WFQ Algorithm: 3, Priority & Preemption: 3, Starvation Prevention: 2, Observability: 2) from 4 files (+6 files)
- ✅ **Epic 4.4.1 expanded:** Prometheus Metrics Contracts - 25 files (RED Schema: 4, Turn Metrics: 5, Component Metrics: 5, Infrastructure Metrics: 5, Alerting & Dashboards: 6) from 6 files (+19 files)
- ✅ **Epic 4.3.5 expanded:** Cost Tracking Contracts - 16 files (Hierarchical Budgets: 6, Cost Model: 4, Automatic Fallback: 3, Cost Observability: 3) from 4 files (+12 files)
- ✅ **Epic 4.4.2 expanded:** Intelligent Trace Sampling Contracts - 13 files (Head-Based: 4, Tail-Based: 3, Adaptive: 3, Jaeger: 3) from 5 files (+8 files)
- ✅ **Epic 2.5.5 added:** Band-Based Egress Rules Contracts - 17 files (Network: 4, Filesystem: 5, Resource: 4, Violation Logging: 4)
- ✅ **Epic 2.7 added:** Tool Execution & Sandbox Contracts - 32 files (Architecture: 5, MCP Protocol: 6, WASM Sandbox: 7, Process Sandbox: 8, Selection Logic: 6)
- ✅ **Epic 2.8 added:** MCP Protocol Integration Contracts - 30 files (JSON-RPC: 7, Lifecycle: 8, Circuit Breaker: 6, Error Handling: 9)
- ✅ **Epic 2.9 added:** PII Detection & Redaction Contracts - 30 files (Regex: 6, BERT-NER: 7, Vault: 8, Audit: 9)
- ✅ **Epic 2.10 added:** E2EE for RED Band Contracts - 32 files (AES-256-GCM: 8, Keystore: 10, Selective Encryption: 8, Audit: 6)
- ✅ **Epic 2.11 added:** JWT Authentication Contracts - 30 files (Generation: 8, Validation: 8, Refresh: 7, Authorization: 7)
- ✅ **Epic 2.12 added:** Audit Trail & K0 Receipts Contracts - 30 files (Schema: 8, WAL: 8, Retention: 7, Query: 7)
- ✅ **Epic 2.13 added:** Backpressure Cascade 3-Tier Contracts - 28 files (Watermarks: 8, Propagation: 7, Recovery: 7, Retention Overrides: 6)
- ✅ **Epic 2.14 added:** WebSocket Real-Time Chat Contracts - 30 files (Connection: 8, Protocol: 8, Flow Control: 7, Reconnection: 7)
- ✅ **Epic 2.15 added:** REST API Session Management Contracts - 34 files (Session CRUD: 9, Idempotency: 8, Pagination: 9, Documentation: 8)
- ✅ **Milestone 3 expanded:** FlatBuffers schemas with full Layer 1-5 breakdown (76 schemas)
- ✅ **Serialization contracts:** Complete FlatBuffers, REST API dual format, WebSocket binary, SSE JSON, schema versioning

**Success Criteria:**

- ✅ All contracts map to source ADRs with line references
- ✅ FlatBuffers schemas compile and validate (76 schemas across 5 layers + 17 SSE events + 6 SessionState sections)
- ✅ Protocol definitions pass MPST validation (6 protocols: Agent Hire, Task Execution, Clarification, Barge-In, Tool Call, Saga Rollback)
- ✅ K0 pipeline contracts complete (P01-P20 with request/response/receipt schemas)
- ✅ SSE event contracts complete (17 events × 3: FlatBuffers schema + JSON serialization + filtering)
- ✅ SessionState contracts complete (6 sections × 4: FlatBuffers schema + manager + eviction + serialization)
- ✅ Performance contracts complete (15 performance budgets + 16 KV cache + 28 thermal & placement + 10 WFQ scheduler + 25 Prometheus metrics + 16 cost tracking + 13 trace sampling = 123 contracts)
- ✅ Security contracts complete (27 capability contracts + 17 egress rules + 32 tool execution + 30 MCP protocol + 30 PII detection = 136 contracts)
- ✅ Contract tests achieve 90%+ coverage (Pact-style consumer-driven contracts)
- ✅ Documentation complete with examples (YAML templates, FlatBuffers schemas, OpenAPI 3.1 specs)

**Coverage Summary by ADR:**

- **ADR-0001 (K0/K1 Split):** Epic 1.1 (20 K0 ports) + Epic 3.3 (20 K0 pipelines) = 80 contract files ✅
- **ADR-0002 (Actor Model):** Epic 1.2 (mailbox, supervisor, router) = 7 contract files ✅
- **ADR-0003 (MPST Protocols):** Epic 1.3 (6 PDL definitions) + Epic 2.6 (6 protocol FSMs) = 60 contract files ✅
- **ADR-0004 (52-Module Architecture):** Epic 1.4 (module manifests) = 52 contract files ✅
- **ADR-0005 (Agent Lifecycle):** Epic 2.1 (6-state FSM) = 8 contract files ✅
- **ADR-0006 (Orchestration):** Epic 2.2 (3-phase) = 9 contract files ✅
- **ADR-0007 (Planning):** Epic 2.3 (4-stage) = 9 contract files ✅
- **ADR-0008 (Circuit Breaker) + ADR-0009 (Saga):** Epic 2.4 (error recovery) = 10 contract files ✅
- **ADR-0010 (Capability Security):** Epic 2.5 (capability contracts) = 27 contract files ✅
- **ADR-0011 (FlatBuffers) + ADR-0012 (76 Schemas):** Epic 3.1 (5 layers) = 76 .fbs files + 6 principle files = 82 contract files ✅
- **ADR-0013 (Versioning):** Epic 3.2.4 (schema registry) = 80 contract files (76 registries + 4 tooling) ✅
- **ADR-0014 (REST API):** Epic 3.2.1 (dual format) = 7 contract files ✅
- **ADR-0015 (WebSocket):** Epic 3.2.2 (binary protocol) = 7 contract files ✅
- **ADR-0016 (SSE Events):** Epic 3.2.3 (17 event schemas) = 25 contract files (17 FlatBuffers + envelope + 5 filters + serializer + browser SDK) ✅
- **ADR-0017 (SessionState 6-Section):** Epic 4.1.1 (6 sections detailed) = 21 contract files (6 sections × 3-4: schema + manager + eviction/logic + serialization) ✅
- **ADR-0018 (3-Tier Eviction):** Epic 4.1.2 (eviction strategy) = 15 contract files (Tier 1: 6 + Tier 2: 5 + Tier 3: 2 + Infrastructure: 2) ✅
- **ADR-0019 (FlatBuffers Serialization):** Epic 4.1.3 (serialization pipeline) = 27 contract files (Root: 7 + Types: 7 + Pipeline: 6 + Coherence: 7) ✅
- **ADR-0020 (Multi-Tier Storage):** Epic 4.2.1 (storage tiers) = 17 contract files (Hot: 5 + Warm: 6 + Cold: 6) ✅
- **ADR-0021 (Turn History Retention):** Epic 4.2.2 (retention policies) = 10 contract files (Engine: 1 + Tiers: 3 + Privacy Bands: 3 + GDPR: 1 + Compliance: 2) ✅
- **ADR-0022 (K0 Bridge Batching):** Epic 4.2.2 (batching infrastructure) = 12 contract files (Engine: 3 + HTTP/2: 3 + Backpressure: 3 + Serialization: 3) ✅
- **ADR-0023 (Cursor Pagination):** Epic 4.2.3 (pagination API) = 10 contract files (Encoding: 3 + REST API: 4 + Query: 3) ✅
- **ADR-0024 (Performance Budgets):** Epic 4.3.1 (performance budgets) = 15 contract files (Turn: 3 + Component: 5 + Memory: 3 + Degradation: 4 + Enforcement: 2) ✅
- **ADR-0025 (KV Cache Management):** Epic 4.3.2 (KV cache management) = 16 contract files (Allocator: 1 + Eviction: 3 + Allocation: 2 + Warming: 2 + Compression: 3 + Protection: 2 + Metrics: 2 + Fragmentation: 1) ✅
- **ADR-0026 (Thermal Hysteresis):** Epic 4.3.3 (thermal management) = 13 contract files (Sensors: 2 + Hysteresis: 3 + Cooldown: 2 + Placement: 4 + Emergency: 1 + Notifications: 1) ✅
- **ADR-0027 (Model Placement Cascade):** Epic 4.3.3 (model placement) = 15 contract files (Placement Algorithm: 4 + Automatic Failover: 4 + Cost-Aware Fallback: 4 + Remote Resilience: 3) ✅
- **ADR-0028 (WFQ Scheduler):** Epic 4.3.4 (WFQ scheduler) = 10 contract files (WFQ Algorithm: 3 + Priority & Preemption: 3 + Starvation Prevention: 2 + Observability: 2) ✅
- **ADR-0029 (Prometheus Metrics RED Method):** Epic 4.4.1 (Prometheus metrics) = 25 contract files (RED Schema: 4 + Turn Metrics: 5 + Component Metrics: 5 + Infrastructure Metrics: 5 + Alerting & Dashboards: 6) ✅
- **ADR-0030 (Intelligent Trace Sampling):** Epic 4.4 Issue 4.4.2 (tracing contracts) = 13 contract files (Head-Based: 4 + Tail-Based: 3 + Adaptive: 3 + Jaeger: 3) ✅
- **ADR-0031 (Cost Tracking Per Session):** Epic 4.3 Issue 4.3.5 (cost contracts) = 16 contract files (Budgets: 6 + Pricing: 4 + Fallback: 3 + Observability: 3) ✅
- **ADR-0032 (Band-Based Egress Rules):** Epic 2.5 Issue 2.5.5 (egress contracts) = 17 contract files (Network: 4 + Filesystem: 5 + Resource: 4 + Logging: 4) ✅
- **ADR-0033 (Three-Tier Sandbox Strategy):** Epic 2.7 (tool execution contracts) = 32 contract files (Architecture: 5 + MCP Protocol: 6 + WASM: 7 + Process: 8 + Selection: 6) ✅
- **ADR-0034 (MCP Protocol for Tool Integration):** Epic 2.8 (MCP protocol contracts) = 30 contract files (JSON-RPC: 7 + Lifecycle: 8 + Circuit Breaker: 6 + Error Handling: 9) ✅
- **ADR-0035 (PII Detection & Redaction):** Epic 2.9 (PII privacy contracts) = 30 contract files (Regex: 6 + BERT-NER: 7 + Vault: 8 + Audit: 9) ✅
- **ADR-0036 (E2EE for RED Band):** Epic 2.10 (E2EE contracts) = 32 contract files (AES-256-GCM: 8 + Keystore: 10 + Selective Encryption: 8 + Audit: 6) = **COMPLETE**
- **ADR-0037 (JWT Authentication):** Epic 2.11 (JWT auth contracts) = 30 contract files (Generation: 8 + Validation: 8 + Refresh: 7 + Authorization: 7) = **COMPLETE**
- **ADR-0038 (Audit Trail to K0 Receipts):** Epic 2.12 (receipt contracts) = 30 contract files (Schema: 8 + WAL: 8 + Retention: 7 + Query: 7) = **COMPLETE**
- **ADR-0039 (Backpressure Cascade 3-Tier):** Epic 2.13 (backpressure contracts) = 28 contract files (Watermarks: 8 + Propagation: 7 + Recovery: 7 + Retention Overrides: 6) = **COMPLETE**
- **ADR-0040 (WebSocket Real-Time Chat):** Epic 2.14 (WebSocket contracts) = 30 contract files (Connection: 8 + Protocol: 8 + Flow Control: 7 + Reconnection: 7) = **COMPLETE**
- **ADR-0041 (REST API Session Management):** Epic 2.15 (REST API contracts) = 34 contract files (Session CRUD: 9 + Idempotency: 8 + Pagination: 9 + Documentation: 8) = **COMPLETE**

**Total Contract Files:** ~741 files across 33 epics, 4 milestones, 12 weeks

**Recent Expansion History:**

1. **Initial Plan (User "structure good" feedback):** 150 files, 18 epics, Milestones 1-4
2. **After ADR 0001-0015 Gap Analysis:** 220 files (+70 files), 24 epics (added Epic 2.6, 3.3)
3. **After ADR 0016-0017 Detailed Review:** 266 files (+46 files), 24 epics (expanded Epic 3.2.3, 4.1.1)
4. **After ADR 0018-0020 Infrastructure Review:** 308 files (+42 files), 24 epics (expanded Epic 4.1.2 +11, 4.1.3 +20, 4.2.1 +12)
5. **After ADR 0021-0023 Storage & API Review:** 338 files (+30 files), 24 epics (expanded Epic 4.2.2 +15, 4.2.3 +6)
6. **After ADR 0024-0026 Performance Optimization Review:** 382 files (+44 files), 24 epics (expanded Epic 4.3.1 +10, 4.3.2 +10, 4.3.3 +5, Note: ADR-0027 deferred - will be handled with model placement contracts)
7. **After ADR 0027-0029 Placement/Scheduler/Observability Review:** 432 files (+50 files), 24 epics (expanded Epic 4.3.3 +15 model placement, Epic 4.3.4 +6 WFQ scheduler, Epic 4.4.1 +19 Prometheus metrics, Epic 4.4.1 +10 alerting/dashboards)
8. **After ADR 0030-0032 Tracing/Cost/Security Review:** 465 files (+33 files), 24 epics (Epic 4.4.2 added +13 intelligent trace sampling, Epic 4.3.5 added +16 cost tracking, Epic 2.5.5 added +17 band-based egress rules)
9. **After ADR 0033-0035 Tool Execution/MCP/PII Review:** 557 files (+92 files), 27 epics (Epic 2.7 added +32 tool execution & sandbox, Epic 2.8 added +30 MCP protocol integration, Epic 2.9 added +30 PII detection & redaction)
10. **After ADR 0036-0038 E2EE/JWT/Audit Review:** 649 files (+92 files), 30 epics (Epic 2.10 added +32 E2EE for RED band, Epic 2.11 added +30 JWT authentication, Epic 2.12 added +30 audit trail & K0 receipts)
11. **After ADR 0039-0041 Backpressure/WebSocket/REST Review:** 741 files (+92 files), 33 epics (Epic 2.13 added +28 backpressure cascade, Epic 2.14 added +30 WebSocket real-time chat, Epic 2.15 added +34 REST API session management)
8. **After ADR 0030-0032 Tracing/Cost/Egress Review:** 465 files (+33 files), 24 epics (expanded Epic 4.4.2 +8 trace sampling, Epic 4.3.5 +12 cost tracking, added Epic 2.5.5 +17 egress rules, Issue count +3)
9. **After ADR 0033-0035 Tool Execution/MCP/PII Review:** 557 files (+92 files), 27 epics (added Epic 2.7 +32 tool execution, Epic 2.8 +30 MCP protocol, Epic 2.9 +30 PII detection, Issue count +12)

---

## 🎯 Contract Development Phases

Based on ADRs 0001-0004 and sub-ADRs reviewed, the contract development follows this timeline:

### **Phase 1: Foundation Contracts (Weeks 1-3)**

**ADRs:** 0001-0004 + sub-ADRs
**Focus:** Core kernel architecture, Actor Model, protocols, module structure

### **Phase 2: Agent & Orchestration Contracts (Weeks 4-6)**

**ADRs:** 0005-0009 + sub-ADRs
**Focus:** Agent lifecycle, orchestration, planning, error recovery

### **Phase 3: Serialization & API Contracts (Weeks 7-9)**

**ADRs:** 0011-0016 + sub-ADRs
**Focus:** FlatBuffers schemas, API specifications, WebSocket, SSE

### **Phase 4: State & Performance Contracts (Weeks 10-12)**

**ADRs:** 0017-0031 + sub-ADRs
**Focus:** SessionState, storage, performance budgets, observability

---

## 📦 Milestone 1: Foundation Contracts (Weeks 1-3)

**Goal:** Establish core architectural contracts from foundational ADRs

### **Milestone Deliverables:**

- [ ] K0/K1 integration contracts complete
- [ ] Actor Model mailbox contracts defined
- [ ] MPST protocol contracts validated
- [ ] 52-module architecture documented
- [ ] CI/CD integration for contract validation

---

## Epic 1.1: K0/K1 Kernel Split Contracts

**ADR Source:** ADR-0001, ADR-0001a, ADR-0001f
**Timeline:** Week 1 (5 days)
**Dependencies:** None (foundational)

### **Issues for Epic 1.1:**

#### **Issue 1.1.1: K0 Bridge Port Definitions (P01-P20)**

**Effort:** 2 days
**Assignee:** Backend Contract Lead

**Context (File Reference):**

- **Source ADR:** `docs/architecture/decisions/0001a-k0-bridge-communication-protocol.md`
- **Lines:** 350-650 (Port Specifications)
- **K0 Docs:** Memory kernel documentation (JSON envelope specs)

**Expected Output:**

- **Location:** `contracts/k0_bridge/ports/`
- **Files to Create:**

  ```
  contracts/k0_bridge/ports/
  ├── P01_recall_query.yml         # Memory retrieval contract
  ├── P02_memory_write.yml         # State delta batching
  ├── P03_consolidation.yml        # Memory consolidation triggers
  ├── P04_action_arbitration.yml   # Action selection queries
  ├── P05_prospective_triggers.yml # Reminder/schedule events
  ├── P06_learning_feedback.yml    # Feedback signals (async)
  ├── P07_sync_crdt.yml            # WAL replay, multi-device sync
  ├── P08_embedding_lifecycle.yml  # Embedding requests
  ├── P09_connector_ingestion.yml  # External data ingestion
  ├── P10_pii_detection.yml        # PII redaction requests
  ├── P11_dsar_gdpr.yml            # Data export/deletion
  ├── P12_policy_eval.yml          # Policy decisions (caps/bands)
  ├── P13_index_rebuild.yml        # Reindex coordination
  ├── P14_deduplication.yml        # Near-duplicate detection
  ├── P15_rollups.yml              # Summary generation
  ├── P16_feature_flags.yml        # A/B testing config
  ├── P17_qos.yml                  # Resource allocation, budgets
  ├── P18_personalization_sync.yml # Persona state (traits)
  ├── P19_safety.yml               # Safety filtering
  └── P20_procedures.yml           # Habit execution
  ```

**Contract Schema Template (YAML):**

```yaml
# contracts/k0_bridge/ports/P01_recall_query.yml
port:
  id: "P01"
  name: "RecallQuery"
  direction: "K1_TO_K0"  # K1 → K0
  semantics: "query"  # query | command | event
  performance_budget_ms: 50
  description: "K1 queries K0 for relevant memories (context retrieval for AI agents)"

  request_schema:
    envelope_fields:
      - name: "port"
        type: "string"
        value: "query"
        required: true
      - name: "command_type"
        type: "string"
        value: "recall_query"
        required: true
      - name: "cognitive_trace_id"
        type: "string"
        required: true
      - name: "session_id"
        type: "string"
        required: true
      - name: "qos_band"
        type: "enum"
        values: ["GREEN", "AMBER", "RED"]
        default: "GREEN"

    payload_fields:
      - name: "query_type"
        type: "enum"
        values: ["episodic", "semantic", "procedural", "working_memory"]
        required: true
      - name: "filters"
        type: "object"
        schema:
          - name: "time_range"
            type: "object"
            fields:
              - name: "start"
                type: "int64"
                description: "Unix timestamp (microseconds)"
              - name: "end"
                type: "int64"
          - name: "tags"
            type: "array[string]"
          - name: "similarity_threshold"
            type: "float"
            range: [0.0, 1.0]
      - name: "limit"
        type: "int32"
        default: 10
        range: [1, 100]
      - name: "cognitive_enhancements"
        type: "object"
        schema:
          - name: "working_memory_boost"
            type: "boolean"
            default: false
          - name: "affect_bias"
            type: "boolean"
          - name: "temporal_bias"
            type: "enum"
            values: ["recency", "frequency"]
          - name: "social_bias"
            type: "enum"
            values: ["family_only", "all"]

  response_schema:
    status_codes:
      - code: 200
        meaning: "success"
      - code: 400
        meaning: "invalid_query"
      - code: 500
        meaning: "k0_internal_error"
      - code: 504
        meaning: "timeout"

    payload_fields:
      - name: "results"
        type: "array[Memory]"
        schema:
          - name: "memory_id"
            type: "string"
          - name: "content"
            type: "string"
          - name: "memory_type"
            type: "enum"
            values: ["episodic", "semantic", "procedural"]
          - name: "timestamp"
            type: "int64"
          - name: "relevance_score"
            type: "float"
            range: [0.0, 1.0]
          - name: "provenance"
            type: "object"
            schema:
              - name: "fusion_score"
                type: "float"
              - name: "fts_score"
                type: "float"
              - name: "vector_score"
                type: "float"
              - name: "kg_score"
                type: "float"
      - name: "total_count"
        type: "int32"
      - name: "query_latency_ms"
        type: "float"

  usage_examples:
    - scenario: "Planner AI Agent queries context"
      k1_code: |
        # k1/orchestration/planner/planner_agent.py
        async def generate_plan(self, task: TaskAnnouncement):
            # Step 1: Query K0 for context
            query = RecallQuery(
                query_type="episodic",
                filters=QueryFilters(
                    time_range=TimeRange(start=now() - 7days, end=now()),
                    tags=["planning", task.domain],
                    limit=10
                ),
                cognitive_enhancements={
                    "working_memory_boost": True,
                    "temporal_bias": "recency"
                }
            )
            context = await self.k0_bridge.recall_query(query)

            # Step 2: Use context in LLM prompt
            prompt = self.build_prompt(context.results, task)
            plan = await self.model_hub.call(prompt, model="gpt-4")
            return plan

      k0_routing: |
        # K0 Memory Module handles internally
        # Port "query" + command_type "recall_query" → P01 Pipeline
        # K0 performs multi-store retrieval (FTS + Vector + KG + Episodic)
        # Returns ranked results with provenance

  validation_rules:
    - rule: "time_range.start < time_range.end"
      violation: "invalid_time_range"
    - rule: "limit >= 1 AND limit <= 100"
      violation: "invalid_limit"
    - rule: "similarity_threshold >= 0.0 AND similarity_threshold <= 1.0"
      violation: "invalid_threshold"

  observability:
    prometheus_metrics:
      - name: "k0_bridge_recall_query_total"
        type: "counter"
        labels: ["status", "query_type"]
      - name: "k0_bridge_recall_query_latency_ms"
        type: "histogram"
        buckets: [10, 25, 50, 100, 200]
      - name: "k0_bridge_recall_query_results_count"
        type: "histogram"
        buckets: [0, 1, 5, 10, 20, 50]

    opentelemetry_spans:
      - span_name: "k0_bridge.recall_query"
        attributes:
          - "query_type"
          - "cognitive_trace_id"
          - "result_count"
          - "latency_ms"

  related_adrs:
    - adr: "ADR-0001a"
      section: "Port Specifications - P01"
    - adr: "ADR-0044"
      section: "K0 Bridge HTTP/2 Protocol"

  changelog:
    - version: "1.0"
      date: "2025-10-13"
      changes: "Initial contract definition"
```

**Acceptance Criteria:**

- [ ] 20 port YAML files created in `contracts/k0_bridge/ports/`
- [ ] Each port has complete request/response schemas
- [ ] Usage examples with code snippets
- [ ] Validation rules defined
- [ ] Observability metrics specified
- [ ] ADR references accurate

---

#### **Issue 1.1.2: K0 Bridge Dual Protocol Support (JSON + FlatBuffers)**

**Effort:** 1 day
**Assignee:** Serialization Lead

**Context:**

- **Source ADR:** `docs/architecture/decisions/0001a-k0-bridge-communication-protocol.md`
- **Lines:** 100-250 (Dual Protocol Support section)

**Expected Output:**

- **Location:** `contracts/k0_bridge/protocols/`
- **Files:**

  ```
  contracts/k0_bridge/protocols/
  ├── json_envelope_spec.yml       # JSON envelope contract (PRIMARY)
  ├── flatbuffers_envelope_spec.yml # FlatBuffers envelope (SECONDARY)
  ├── content_negotiation.yml      # Format selection contract
  └── protocol_versioning.yml      # Schema version evolution
  ```

**Contract Example (json_envelope_spec.yml):**

```yaml
json_envelope:
  name: "K0 Bridge JSON Envelope"
  format: "JSON"
  priority: "PRIMARY"
  description: "K0's native envelope format for all bridge communications"

  envelope_structure:
    required_fields:
      - name: "port"
        type: "string"
        values: ["command", "query", "sync", "observability"]
      - name: "command_type"
        type: "string"
        description: "Specific operation (e.g., memory_write, recall_query)"
      - name: "envelope_id"
        type: "string"
        format: "UUID"
      - name: "cognitive_trace_id"
        type: "string"
        format: "UUID"
      - name: "timestamp"
        type: "string"
        format: "ISO8601"
      - name: "device_id"
        type: "string"
      - name: "session_id"
        type: "string"
      - name: "user_id"
        type: "string"
      - name: "schema_version"
        type: "string"
        format: "semver"
      - name: "qos_band"
        type: "enum"
        values: ["GREEN", "AMBER", "RED"]
      - name: "obligations"
        type: "array[string]"
        description: "Cognitive processing obligations for Smart Lane"
      - name: "payload"
        type: "object"
        description: "Port-specific payload data"
      - name: "signature"
        type: "string"
        format: "ed25519_hex"

  content_negotiation:
    request_header: "Content-Type: application/json"
    response_header: "Content-Type: application/json"
    fallback: "Always supported (no fallback needed)"

  usage_guidance:
    when_to_use:
      - "All K0 operations (K0's native format)"
      - "Low-frequency operations (config updates, admin)"
      - "Human-readable debugging and testing"
      - "Backward compatibility with K0 ecosystem"
    performance:
      serialization: "~1.5-2ms"
      deserialization: "~1-1.5ms"
      size_overhead: "Baseline (1.0x)"

  example:
    fast_lane_write: |
      {
        "port": "command",
        "command_type": "memory_write",
        "envelope_id": "env_abc123",
        "cognitive_trace_id": "trace_xyz789",
        "timestamp": "2025-10-13T12:34:56.789Z",
        "device_id": "device_dad_phone",
        "session_id": "sess_456",
        "user_id": "user_dad",
        "schema_version": "1.2.0",
        "qos_band": "GREEN",
        "obligations": [],
        "payload": {
          "memory_type": "preference",
          "content": "User likes espresso",
          "tags": ["coffee", "preference"]
        },
        "signature": "ed25519_signature_hex"
      }
```

**Acceptance Criteria:**

- [ ] JSON envelope spec complete with all required fields
- [ ] FlatBuffers envelope spec mapped to JSON structure
- [ ] Content negotiation rules documented
- [ ] Performance comparison table (JSON vs FlatBuffers)
- [ ] Usage guidance for developers

---

#### **Issue 1.1.3: State Boundary Management Contracts**

**Effort:** 1 day
**Assignee:** State Management Lead

**Context:**

- **Source ADR:** `docs/architecture/decisions/0001f-state-boundary-management-k1-k0.md`
- **Lines:** 150-450 (State Allocation section)

**Expected Output:**

- **Location:** `contracts/sessionstate/boundaries/`
- **Files:**

  ```
  contracts/sessionstate/boundaries/
  ├── k1_state_allocation.yml      # What lives in K1 SessionState
  ├── k0_state_allocation.yml      # What lives in K0 long-term memory
  ├── state_flow_patterns.yml      # K1→K0 write, K0→K1 read, recovery
  ├── consistency_guarantees.yml   # K1 eventual, K0 strong consistency
  └── size_budgets.yml             # K1 64KB, K0 unbounded
  ```

**Contract Example (k1_state_allocation.yml):**

```yaml
k1_sessionstate_allocation:
  name: "K1 SessionState Working Memory"
  purpose: "Fast, ephemeral working memory for active conversation turns"

  size_budget:
    soft_limit: "64KB"
    hard_limit: "128KB"
    warning_threshold: "92KB"

  sections:
    - section: "beliefs"
      purpose: "Current task, active goals, assumptions, user intents"
      typical_size: "8KB"
      max_size: "16KB"
      update_frequency: "Every turn (~100ms)"
      eviction_policy: "Keep top 10 beliefs by recency"
      example_data: "User wants to schedule Emma's soccer practice"

    - section: "scoreboard"
      purpose: "Agent proposals, negotiation state, selections"
      typical_size: "4KB"
      max_size: "8KB"
      update_frequency: "During 3-phase orchestration"
      eviction_policy: "Keep current turn scores only"
      example_data:
        - agent: "Planner"
          score: 0.85
        - agent: "Researcher"
          score: 0.62

    - section: "control"
      purpose: "Turn state, protocol FSM, flow position"
      typical_size: "2KB"
      max_size: "4KB"
      update_frequency: "Continuously during turn execution"
      eviction_policy: "Essential flow state, no eviction"
      example_data:
        turn: 5
        phase: "execution"
        protocol: "task_execution"

    - section: "persona"
      purpose: "Dynamic traits from K0, current style, adaptations"
      typical_size: "4KB"
      max_size: "8KB"
      update_frequency: "Session start + periodic sync"
      eviction_policy: "Keep top 20 traits by relevance"
      example_data:
        formality: 0.3
        verbosity: 0.5
        emoji_use: true

    - section: "multimodal"
      purpose: "Audio buffer, pending tool results, streaming state"
      typical_size: "32KB"
      max_size: "48KB"
      update_frequency: "Voice input, tool calls, SSE streaming"
      eviction_policy: "LRU eviction for audio buffers"
      example_data:
        audio_buffer: "4KB compressed audio"
        pending_tools: ["calendar.get"]

    - section: "meta"
      purpose: "Trace IDs, timestamps, metrics, debug data"
      typical_size: "4KB"
      max_size: "8KB"
      update_frequency: "Continuously for observability"
      eviction_policy: "Keep last 100 trace IDs"
      example_data:
        trace_id: "abc123"
        ttft_ms: 140
        turn_start: "2025-10-13T12:34:56.789Z"

  characteristics:
    durability: "Ephemeral - lost on K1 crash (rebuilt from K0 WAL)"
    access_speed: "<1ms (in-memory, no disk I/O)"
    update_rate: "Hundreds of times per session"
    serialization: "FlatBuffers for K0 flushes"

  lifecycle:
    creation: "Session start (persona load from K0)"
    updates: "Every turn (beliefs, scoreboard, control)"
    persistence: "Batch flush to K0 every 250ms"
    destruction: "Session end (final flush, memory freed)"
    recovery: "K1 crash → rebuild from K0 WAL (<5s)"

  related_adrs:
    - adr: "ADR-0001f"
      section: "State Allocation - K1 State"
    - adr: "ADR-0017"
      section: "SessionState 6-Section Design"
```

**Acceptance Criteria:**

- [ ] K1 state allocation contract complete with 6 sections
- [ ] K0 state allocation contract (7 memory types)
- [ ] State flow patterns documented (write, read, recovery)
- [ ] Consistency guarantees specified
- [ ] Size budgets with eviction policies

---

## Epic 1.2: Actor Model Contracts

**ADR Source:** ADR-0002, ADR-0002a-d
**Timeline:** Week 1-2 (3 days)
**Dependencies:** None (foundational)

### **Issues for Epic 1.2:**

#### **Issue 1.2.1: Mailbox Message Envelope Schema**

**Effort:** 1 day
**Assignee:** Messaging Infrastructure Lead

**Context:**

- **Source ADR:** `docs/architecture/decisions/0002-actor-model-agent-isolation.md`
- **Lines:** 500-800 (Mailbox architecture section)
- **Related:** ADR-0002a Mailbox MPSC Queue Implementation

**Expected Output:**

- **Location:** `contracts/actor_model/mailbox/`
- **Files:**

  ```
  contracts/actor_model/mailbox/
  ├── message_envelope.yml          # Mailbox message envelope spec
  ├── mpsc_queue_contract.yml       # Lock-free queue guarantees
  ├── routing_contract.yml          # Router message routing rules
  ├── backpressure_contract.yml     # Watermark policies
  └── dead_letter_queue.yml         # DLQ handling
  ```

**Contract Example (message_envelope.yml):**

```yaml
mailbox_message_envelope:
  name: "Actor Mailbox Message Envelope"
  description: "Standard message format for ALL Actor Model communications (AI agents + pure actors)"
  applies_to:
    - "ALL 52 K1 modules (AI agents: 4, Pure actors: 48)"
    - "Inter-agent messaging"
    - "Agent → Orchestrator → Agent communication"

  envelope_structure:
    required_fields:
      - name: "message_id"
        type: "string"
        format: "UUID"
        description: "Unique message identifier"
      - name: "message_type"
        type: "enum"
        values:
          - "task_announcement"      # Orchestrator → AI agents (broadcast)
          - "plan_proposal"           # AI agent → Orchestrator
          - "plan_approval"           # Orchestrator → AI agent
          - "tool_request"            # AI agent → Tool Runner
          - "tool_result"             # Tool Runner → AI agent
          - "health_check"            # Supervisor → ALL components
          - "health_response"         # ALL components → Supervisor
          - "protocol_violation"      # Protocol Monitor → component
          - "state_delta"             # SessionState → K0 Bridge
          - "config_update"           # Config Manager → ALL components
      - name: "sender_id"
        type: "string"
        description: "Sender component ID (agent_id or component_id)"
      - name: "receiver_id"
        type: "string"
        description: "Receiver component ID ('*' for broadcast)"
      - name: "timestamp"
        type: "int64"
        description: "Unix timestamp (microseconds)"
      - name: "cognitive_trace_id"
        type: "string"
        format: "UUID"
        description: "End-to-end trace ID for observability"
      - name: "priority"
        type: "enum"
        values: ["LOW", "NORMAL", "HIGH", "URGENT"]
        default: "NORMAL"
      - name: "ttl_ms"
        type: "int32"
        description: "Time-to-live in milliseconds (drop if expired)"
      - name: "payload"
        type: "bytes"
        description: "FlatBuffers serialized payload"
      - name: "reply_to"
        type: "string"
        optional: true
        description: "Sender mailbox for reply (if expecting response)"

  ai_agent_usage:
    description: "AI agents use mailboxes for Actor Model, call Model Hub internally"
    example_flow: |
      1. Orchestrator → send(HireRequest) → Planner mailbox [ACTOR MESSAGE]
      2. Planner internal: receive() → call Model Hub → LLM reasoning [NOT in message]
      3. Planner → send(Proposal) → Orchestrator mailbox [ACTOR MESSAGE]

    key_point: "Protocols validate Actor messages, NOT LLM calls. AI agents manage LLM timeouts internally."

  serialization:
    format: "FlatBuffers"
    schema_file: "contracts/flatbuffers/layer1_kernel/mailbox_message.fbs"
    zero_copy: true
    performance: "<0.5ms P95 serialization"

  routing:
    broadcast_semantics: "receiver_id='*' → all agents in roster"
    unicast_semantics: "receiver_id=<agent_id> → single mailbox"
    multicast: "Not supported (use multiple unicast)"

  backpressure:
    watermarks:
      low: "25% mailbox capacity"
      medium: "50% mailbox capacity"
      high: "75% mailbox capacity"
      critical: "90% mailbox capacity (drop LOW priority)"
    actions:
      - threshold: "high"
        action: "Log warning, emit metric"
      - threshold: "critical"
        action: "Drop LOW priority messages, send backpressure signal"

  observability:
    prometheus_metrics:
      - name: "mailbox_messages_sent_total"
        type: "counter"
        labels: ["sender_id", "receiver_id", "message_type"]
      - name: "mailbox_messages_received_total"
        type: "counter"
        labels: ["receiver_id", "message_type"]
      - name: "mailbox_queue_depth"
        type: "gauge"
        labels: ["component_id"]
      - name: "mailbox_message_latency_ms"
        type: "histogram"
        buckets: [0.1, 0.5, 1, 5, 10, 50]

  related_adrs:
    - adr: "ADR-0002"
      section: "Actor Model - Message Passing"
    - adr: "ADR-0002a"
      section: "Mailbox MPSC Queue Implementation"
```

**Acceptance Criteria:**

- [ ] Message envelope YAML complete with all fields
- [ ] AI agent vs pure actor usage clarified
- [ ] MPSC queue contract with lock-free guarantees
- [ ] Routing contract (broadcast, unicast)
- [ ] Backpressure watermark policies
- [ ] Dead letter queue handling

---

#### **Issue 1.2.2: Supervisor Health Check Protocol**

**Effort:** 1 day
**Assignee:** Reliability Lead

**Context:**

- **Source ADR:** `docs/architecture/decisions/0002b-supervisor-monitoring-crash-recovery.md`
- **Related:** Supervisor monitoring for ALL 52 K1 components

**Expected Output:**

- **Location:** `contracts/actor_model/supervisor/`
- **Files:**

  ```
  contracts/actor_model/supervisor/
  ├── health_check_protocol.yml     # Ping-pong health checks (1Hz)
  ├── crash_detection.yml           # Crash detection criteria
  ├── blacklist_policy.yml          # 3 crashes → blacklist policy
  ├── supervisor_metrics.yml        # Supervisor observability
  └── restart_strategy.yml          # Component restart policies
  ```

**Acceptance Criteria:**

- [ ] Health check protocol (1Hz ping-pong) documented
- [ ] Crash detection criteria (3 missed pings = crash)
- [ ] Blacklist policy (3 crashes in 10min → blacklist 1hr)
- [ ] Supervisor metrics specified
- [ ] Restart strategies for AI agents vs pure actors

---

#### **Issue 1.2.3: Actor Router & Admission Control**

**Effort:** 1 day
**Assignee:** Infrastructure Lead

**Context:**

- **Source ADR:** `docs/architecture/decisions/0002c-actor-router-admission-control.md`
- **Lines:** Focus on message routing and load management

**Expected Output:**

- **Location:** `contracts/actor_model/router/`
- **Files:**

  ```
  contracts/actor_model/router/
  ├── routing_table_schema.yml      # component_id → mailbox mapping
  ├── admission_control.yml         # Load shedding policies
  ├── priority_routing.yml          # Priority-based message routing
  └── router_observability.yml      # Router metrics
  ```

**Acceptance Criteria:**

- [ ] Routing table schema (component_id → mailbox)
- [ ] Admission control policies (drop LOW priority at 90% load)
- [ ] Priority routing rules (URGENT → front of queue)
- [ ] Router observability metrics

---

## Epic 1.3: MPST Protocol Contracts

**ADR Source:** ADR-0003, ADR-0003a-d
**Timeline:** Week 2 (5 days)
**Dependencies:** Epic 1.2 (Actor Model contracts)

### **Issues for Epic 1.3:**

#### **Issue 1.3.1: Protocol Definition Language (PDL) Specification**

**Effort:** 2 days
**Assignee:** Protocol Architect

**Context:**

- **Source ADR:** `docs/architecture/decisions/0003a-protocol-definition-language-pdl-specification.md`
- **Lines:** Custom YAML-based PDL for conversation protocols

**Expected Output:**

- **Location:** `contracts/protocols/pdl/`
- **Files:**

  ```
  contracts/protocols/pdl/
  ├── pdl_specification.yml         # PDL language spec
  ├── pdl_schema_validation.yml     # JSON Schema for PDL files
  ├── pdl_compiler_contract.yml     # PDL → FSM compilation rules
  └── pdl_examples.yml              # Example protocols
  ```

**Contract Example (pdl_specification.yml):**

```yaml
protocol_definition_language:
  name: "K1 Protocol Definition Language (PDL)"
  version: "1.0"
  format: "YAML"
  description: "Custom DSL for defining conversation protocols with MPST validation"

  top_level_structure:
    required_fields:
      - name: "protocol"
        type: "object"
        description: "Root protocol definition"
        fields:
          - name: "name"
            type: "string"
            example: "agent_hire"
          - name: "version"
            type: "string"
            format: "semver"
          - name: "description"
            type: "string"
          - name: "initial_state"
            type: "string"
            description: "Entry state name"
          - name: "terminal_states"
            type: "array[string]"
            description: "List of exit state names"
          - name: "states"
            type: "array[State]"
          - name: "transitions"
            type: "array[Transition]"
          - name: "timeouts"
            type: "array[TimeoutPolicy]"
          - name: "violations"
            type: "array[ViolationHandler]"

  state_definition:
    required_fields:
      - name: "name"
        type: "string"
      - name: "type"
        type: "enum"
        values: ["entry", "interaction", "decision", "exit"]
      - name: "timeout_ms"
        type: "int32"
        optional: true
        description: "State timeout (null = no timeout)"
      - name: "llm_aware"
        type: "boolean"
        default: false
        description: "Allow AI agent LLM calls within state (separate from protocol timeout)"

  transition_definition:
    required_fields:
      - name: "from"
        type: "string"
        description: "Source state name"
      - name: "to"
        type: "string"
        description: "Destination state name"
      - name: "message"
        type: "string"
        description: "Message type triggering transition"
      - name: "sender"
        type: "string"
        description: "Sender role (e.g., 'orchestrator', 'agent')"
      - name: "receivers"
        type: "array[string]"
        description: "Receiver roles ('*' for broadcast)"
      - name: "cardinality"
        type: "string"
        optional: true
        default: "1"
        examples: ["1", "0..1", "0..*", "1..*"]
      - name: "condition"
        type: "string"
        optional: true
        description: "Boolean condition for transition"

  ai_agent_integration:
    description: "Protocols validate Actor messages, AI agents use LLM reasoning internally"
    protocol_timeouts:
      description: "Time to receive Actor message in mailbox"
      example: "500ms for HireRequest → Proposal"
    llm_timeouts:
      description: "Time for AI agent Model Hub call (separate concern)"
      example: "5000ms for Planner LLM reasoning"
    key_distinction: |
      Protocol: Validates mailbox message flow (Orchestrator → Planner)
      AI Agent: Manages LLM calls internally (Planner → Model Hub → LLM)
      Protocol does NOT see LLM calls, only Actor messages.

  example_protocol:
    agent_hire: |
      protocol:
        name: "agent_hire"
        version: "1.0"
        initial_state: "start"
        terminal_states: ["hired", "rejected", "timeout"]

        states:
          - name: "start"
            type: "entry"
            timeout_ms: null

          - name: "negotiation"
            type: "interaction"
            timeout_ms: 500  # 500ms to collect Actor proposals
            llm_aware: true  # AI agents can call Model Hub internally

          - name: "selection"
            type: "decision"
            timeout_ms: 100

        transitions:
          - from: "start"
            to: "negotiation"
            message: "HireRequest"
            sender: "orchestrator"
            receivers: ["*"]  # Broadcast to all agents

          - from: "negotiation"
            to: "selection"
            message: "ProposalsClosed"
            sender: "orchestrator"
            trigger: "timeout"  # Auto after 500ms

  validation_rules:
    - rule: "All terminal_states must be in states list"
      error: "invalid_terminal_state"
    - rule: "All transitions.from/to must reference valid state names"
      error: "invalid_transition_target"
    - rule: "No cycles in transitions (unless intentional loops)"
      error: "potential_deadlock"

  related_adrs:
    - adr: "ADR-0003a"
      section: "Protocol Definition Language Specification"
```

**Acceptance Criteria:**

- [ ] Complete PDL specification YAML
- [ ] JSON Schema for PDL validation
- [ ] PDL compiler contract (YAML → FSM)
- [ ] Example protocols (hire, task, clarification)
- [ ] AI agent integration clarified

---

#### **Issue 1.3.2: Six Core Protocol Definitions**

**Effort:** 2 days
**Assignee:** Protocol Architect + AI Agent Specialist

**Context:**

- **Source ADR:** `docs/architecture/decisions/0003b-6-core-protocol-implementations.md`
- **Lines:** Complete specifications for 6 protocols

**Expected Output:**

- **Location:** `contracts/protocols/definitions/`
- **Files:**

  ```
  contracts/protocols/definitions/
  ├── agent_hire.pdl.yml            # Agent hiring (6 states, 8 transitions)
  ├── task_execution.pdl.yml        # Task execution (5 states, 10 transitions)
  ├── clarification.pdl.yml         # Clarification cycle (4 states, 6 transitions)
  ├── barge_in.pdl.yml              # User interruption (3 states, 5 transitions)
  ├── tool_call.pdl.yml             # Tool call (4 states, 7 transitions)
  └── saga_rollback.pdl.yml         # Saga rollback (5 states, 9 transitions)
  ```

**Contract Example (agent_hire.pdl.yml):**

```yaml
# contracts/protocols/definitions/agent_hire.pdl.yml
protocol:
  name: "agent_hire"
  version: "1.0"
  description: "Hire AI agent with negotiation and selection (Contract Net Protocol)"

  initial_state: "start"
  terminal_states: ["hired", "rejected", "timeout"]

  # FSM States
  states:
    - name: "start"
      type: "entry"
      timeout_ms: null
      description: "Protocol entry point"

    - name: "negotiation"
      type: "interaction"
      description: "Collect proposals from AI agents"
      timeout_ms: 500  # 500ms to collect all proposals
      llm_aware: true  # AI agents (Planner) can call Model Hub here
      comment: |
        AI agents receive HireRequest, call Model Hub for reasoning,
        generate Proposal. Protocol validates Actor messages, NOT LLM calls.

    - name: "selection"
      type: "decision"
      description: "Score proposals, select winner (Orchestrator pure actor logic)"
      timeout_ms: 100
      llm_aware: false  # Orchestrator uses deterministic scoring, NO LLM

    - name: "hired"
      type: "exit"
      description: "Agent successfully hired"

    - name: "rejected"
      type: "exit"
      description: "No suitable agent found"

    - name: "timeout"
      type: "exit"
      description: "Negotiation timed out"

  # FSM Transitions
  transitions:
    - from: "start"
      to: "negotiation"
      message: "HireRequest"
      sender: "orchestrator"
      receivers: ["*"]  # Broadcast to all agents (AI + pure)
      message_schema: "HireRequest.fbs"

    - from: "negotiation"
      to: "negotiation"
      message: "Proposal"
      sender: "agent"  # AI agents (Planner, Researcher) or pure actors
      receivers: ["orchestrator"]
      cardinality: "0..*"  # Multiple proposals allowed
      message_schema: "Proposal.fbs"
      comment: "AI agents call Model Hub internally before sending Proposal"

    - from: "negotiation"
      to: "selection"
      message: "ProposalsClosed"
      sender: "orchestrator"
      receivers: []
      trigger: "timeout"  # Automatic after 500ms
      comment: "Orchestrator closes negotiation, starts selection"

    - from: "selection"
      to: "hired"
      message: "HireApproval"
      sender: "orchestrator"
      receivers: ["agent"]
      condition: "score > threshold"
      message_schema: "HireApproval.fbs"

    - from: "selection"
      to: "rejected"
      message: "HireRejection"
      sender: "orchestrator"
      receivers: ["agent"]
      condition: "score <= threshold"
      message_schema: "HireRejection.fbs"

    - from: "negotiation"
      to: "timeout"
      message: "Timeout"
      sender: "system"
      trigger: "timeout"

  # Timeout Policies
  timeouts:
    - state: "negotiation"
      action: "ProposalsClosed"  # Auto-close after 500ms
      description: "Collect proposals for 500ms, then close"
    - state: "selection"
      action: "HireRejection"    # Reject if selection takes >100ms
      description: "Selection must complete in 100ms"

  # Violation Handling
  violations:
    - type: "unexpected_message"
      action: "block"       # Drop invalid message
      log: true
      description: "Proposal sent before HireRequest"
    - type: "timeout"
      action: "fallback"    # Trigger timeout transition
      log: true
    - type: "deadlock"
      action: "abort"       # Abort protocol, cleanup
      log: true

  ai_agent_context:
    description: "Protocol governs Actor messages between Orchestrator and AI agents"
    ai_agent_behavior: |
      1. AI agent receives HireRequest (Actor message, protocol validates)
      2. AI agent calls Model Hub internally (LLM reasoning, NOT in protocol)
      3. AI agent sends Proposal (Actor message, protocol validates)
    timeout_semantics:
      protocol_timeout: "500ms - Time to receive Proposal Actor message"
      llm_timeout: "5000ms - Time for Model Hub LLM call (AI agent manages internally)"

  performance_budget:
    total_protocol_latency: "500ms P95 (negotiation 500ms + selection 100ms)"
    ai_agent_llm_latency: "50-150ms typical (Planner reasoning)"
    orchestrator_selection: "<5ms (deterministic scoring, pure actor)"

  observability:
    protocol_monitor_metrics:
      - name: "protocol_agent_hire_duration_ms"
        type: "histogram"
        buckets: [100, 250, 500, 1000]
      - name: "protocol_agent_hire_violations_total"
        type: "counter"
        labels: ["violation_type"]
      - name: "protocol_agent_hire_proposals_count"
        type: "histogram"
        buckets: [0, 1, 2, 3, 5]

  related_adrs:
    - adr: "ADR-0003b"
      section: "Agent Hire Protocol"
    - adr: "ADR-0006a"
      section: "Contract Net Protocol Negotiation"
```

**Acceptance Criteria:**

- [ ] 6 protocol PDL files created
- [ ] Each protocol has complete FSM (states, transitions, timeouts)
- [ ] AI agent vs pure actor behavior clarified
- [ ] Protocol timeout vs LLM timeout distinction documented
- [ ] Message schemas referenced (FlatBuffers)
- [ ] Observability metrics specified

---

#### **Issue 1.3.3: Protocol Monitor Runtime Implementation Contract**

**Effort:** 1 day
**Assignee:** Runtime Engineer

**Context:**

- **Source ADR:** `docs/architecture/decisions/0003c-protocol-monitor-runtime-implementation.md`
- **Lines:** Protocol Monitor as pure actor, FSM executor

**Expected Output:**

- **Location:** `contracts/protocols/runtime/`
- **Files:**

  ```
  contracts/protocols/runtime/
  ├── protocol_monitor_api.yml      # Protocol Monitor public API
  ├── fsm_execution_contract.yml    # FSM state transitions
  ├── violation_handlers.yml        # Block, warn, repair strategies
  └── protocol_lifecycle.yml        # Start, validate, complete
  ```

**Acceptance Criteria:**

- [ ] Protocol Monitor API contract (load, start, validate, complete)
- [ ] FSM execution contract (state tracking, transition rules)
- [ ] Violation handlers (block, DLQ, timeout injection)
- [ ] Protocol lifecycle management

---

## Epic 1.4: 52-Module Architecture Documentation

**ADR Source:** ADR-0004, ADR-0004a-d
**Timeline:** Week 3 (5 days)
**Dependencies:** Epic 1.1, 1.2, 1.3 (foundational architecture)

### **Issues for Epic 1.4:**

#### **Issue 1.4.1: 5-Layer Architecture Module Manifest**

**Effort:** 2 days
**Assignee:** Architecture Documentation Lead

**Context:**

- **Source ADR:** `docs/architecture/decisions/0004-52-module-5-layer-architecture.md`
- **Lines:** 100-600 (Complete module classification)
- **Related:** `docs/k1_module_analysis.md`

**Expected Output:**

- **Location:** `contracts/architecture/`
- **Files:**

  ```
  contracts/architecture/
  ├── module_manifest.yml           # Complete 52-module registry
  ├── layer_dependencies.yml        # Layer import rules
  ├── ai_agent_classification.yml   # 4 AI agents identified
  ├── pure_actor_classification.yml # 48 pure actors identified
  └── module_readme_template.md    # README template for modules
  ```

**Contract Example (module_manifest.yml):**

```yaml
k1_module_manifest:
  name: "K1 Intelligence Module - Complete Architecture"
  version: "1.0"
  total_modules: 52
  classification_summary:
    ai_agents: 4  # Use Model Hub for LLM reasoning
    pure_actors: 48  # Deterministic logic only

  layers:
    layer1_input_processing:
      id: 1
      name: "Input Processing"
      module_count: 4
      purpose: "Multi-modal input perception and intent routing"
      performance_target: "Intent classification <5ms P95 (T2 SLM)"
      modules:
        - module_id: "m001"
          name: "streams/stream_switch"
          type: "pure_actor"
          llm_usage: false
          purpose: "Unified multi-modal input bus"
          files: 12
          loc: 800

        - module_id: "m002"
          name: "streams/operators"
          type: "pure_actor"
          llm_usage: false
          purpose: "Stream transformations (VAD, ASR, TTS)"
          files: 12
          loc: 900

        - module_id: "m003"
          name: "orchestration/intent_router"
          type: "pure_actor"
          llm_usage: false
          purpose: "3-tier intent classification (T1 regex, T2 SLM, T3 LLM)"
          files: 12
          loc: 700
          comment: "T3 uses LLM BUT router itself is pure actor (delegates to Model Hub)"

        - module_id: "m004"
          name: "orchestration/meta_policy"
          type: "pure_actor"
          llm_usage: false
          purpose: "Proactivity + clarification engines"
          files: 12
          loc: 800

    layer2_orchestration:
      id: 2
      name: "Orchestration"
      module_count: 3
      purpose: "Multi-agent coordination and plan generation"
      performance_target: "Plan generation 50-80ms P95"
      modules:
        - module_id: "m005"
          name: "orchestration/planner"
          type: "ai_agent"
          llm_usage: true
          model_hub_calls: true
          purpose: "4-stage planner (sketch → expand → validate → commit)"
          files: 24
          loc: 1400
          llm_budget_ms: 5000
          llm_providers: ["OpenAI GPT-4", "Anthropic Claude", "vLLM", "Ollama"]

        - module_id: "m006"
          name: "orchestration/orchestrator"
          type: "pure_actor"
          llm_usage: false
          purpose: "Multi-agent coordinator (Contract Net Protocol)"
          files: 24
          loc: 1500
          comment: "Uses deterministic scoring, NO Model Hub calls"

        - module_id: "m007"
          name: "orchestration/protocol_monitor"
          type: "pure_actor"
          llm_usage: false
          purpose: "MPST/Scribble protocol validation (6 protocols)"
          files: 12
          loc: 1000

    layer3_execution:
      id: 3
      name: "Execution"
      module_count: 22
      purpose: "Agent lifecycle, AI integration (Model Hub), tool execution"
      performance_target: "Model Hub call <50ms P95, Tool call <3s P95"
      subsections:
        agent_lifecycle:
          modules:
            - module_id: "m008"
              name: "agents/registry"
              type: "pure_actor"
              llm_usage: false
              purpose: "Agent YAML specifications"
            - module_id: "m009"
              name: "agents/hire_fire"
              type: "pure_actor"
              llm_usage: false
              purpose: "Lifecycle FSM manager"
            - module_id: "m010"
              name: "agents/supervisor"
              type: "pure_actor"
              llm_usage: false
              purpose: "Health monitoring, crash detection"
            - module_id: "m011"
              name: "agents/personality"
              type: "pure_actor"
              llm_usage: false
              purpose: "Persona adaptation"
            - module_id: "m012"
              name: "agents/mailbox"
              type: "pure_actor"
              llm_usage: false
              purpose: "Inter-agent messaging (MPSC queues)"
            - module_id: "m013"
              name: "agents/active_roster"
              type: "pure_actor"
              llm_usage: false
              purpose: "Runtime agent tracking"

        model_hub:
          description: "AI integration infrastructure (ONLY for 4 AI agents)"
          modules:
            - module_id: "m014"
              name: "model_hub/router"
              type: "pure_actor"
              llm_usage: false
              purpose: "Model request routing (routes TO LLMs, doesn't call)"
            - module_id: "m015"
              name: "model_hub/placement_planner"
              type: "pure_actor"
              llm_usage: false
              purpose: "NPU/GPU/CPU/Remote selector"
            - module_id: "m016"
              name: "model_hub/adapters"
              type: "pure_actor"
              llm_usage: false
              purpose: "Provider adapters (OpenAI, Anthropic, vLLM, Ollama)"
              comment: "API clients, not AI agents themselves"
            - module_id: "m017"
              name: "model_hub/kv_cache_broker"
              type: "pure_actor"
              llm_usage: false
              purpose: "Global KV cache manager (75% hit rate)"
            - module_id: "m018"
              name: "model_hub/prompt_library"
              type: "pure_actor"
              llm_usage: false
              purpose: "Prompt template storage (Jinja2)"
            - module_id: "m019"
              name: "model_hub/fallback_cascade"
              type: "pure_actor"
              llm_usage: false
              purpose: "Model fallback routing"
            - module_id: "m020"
              name: "model_hub/safety_filter"
              type: "ai_agent"
              llm_usage: true
              model_hub_calls: true
              purpose: "Content safety (Safety Watch AI agent)"
              llm_budget_ms: 100

        tool_execution:
          modules:
            - module_id: "m021"
              name: "tools/runner"
              type: "pure_actor"
              llm_usage: false
              purpose: "Tool execution engine"
            # ... (continue for tools/sandbox, tools/registry, tools/adapters, tools/control)

        dialogue_management:
          modules:
            - module_id: "m026"
              name: "dialogue/scoreboard"
              type: "pure_actor"
              llm_usage: false
            # ... (continue for dialogue modules)

        ai_agent_implementations:
          description: "The 4 AI agents that use Model Hub"
          modules:
            - module_id: "m030"
              name: "agents/concierge"
              type: "ai_agent"
              llm_usage: true
              model_hub_calls: true
              purpose: "NLU, intent classification"
              llm_budget_ms: 50
              llm_providers: ["GPT-4-turbo", "Claude-3-haiku"]

            - module_id: "m031"
              name: "agents/researcher"
              type: "ai_agent"
              llm_usage: true
              model_hub_calls: true
              purpose: "Knowledge synthesis, research"
              llm_budget_ms: 3000
              llm_providers: ["GPT-4", "Claude-3-sonnet"]

    # ... (continue for Layer 4 and Layer 5)

  component_classification:
    ai_agents:
      count: 4
      modules:
        - "orchestration/planner"
        - "agents/concierge"
        - "agents/researcher"
        - "model_hub/safety_filter"  # Safety Watch agent
      characteristics:
        - "Call Model Hub for LLM reasoning"
        - "Have persona prompts in k1/model_hub/prompt_library/agent_prompts/"
        - "Latency: 50-500ms (LLM inference)"
        - "Cost: $0.001-0.005 per operation"
        - "Non-deterministic (LLM outputs vary)"
        - "Use Actor Model for concurrency (mailboxes, supervision)"

    pure_actors:
      count: 48
      modules:
        - "orchestration/orchestrator"
        - "orchestration/protocol_monitor"
        - "agents/supervisor"
        - "model_hub/router"  # Routes to LLMs but doesn't call
        # ... (all other 44 modules)
      characteristics:
        - "NO Model Hub calls (deterministic logic only)"
        - "Have config in k1/config/*.yml"
        - "Latency: <5ms (CPU-bound operations)"
        - "Cost: $0.00 (zero LLM spend)"
        - "Deterministic (same input = same output)"
        - "Use Actor Model for concurrency (mailboxes, supervision)"

  layer_dependencies:
    rules:
      - "Layer 1 can only import Layer 5 (Infrastructure)"
      - "Layer 2 can import Layers 1, 3, 4, 5"
      - "Layer 3 can only import Layers 4, 5"
      - "Layer 4 can only import Layer 5"
      - "Layer 5 cannot import from other layers (foundation)"
    enforcement:
      tool: "import-linter"
      config_file: "pyproject.toml"
      pre_commit_hook: true

  related_adrs:
    - adr: "ADR-0004"
      section: "52-Module 5-Layer Architecture"
    - adr: "ADR-0001"
      section: "Component Classification: Pure Actors vs AI Agents"
```

**Acceptance Criteria:**

- [ ] Complete 52-module manifest with all details
- [ ] AI agent classification (4 modules clearly marked)
- [ ] Pure actor classification (48 modules)
- [ ] Layer dependency rules documented
- [ ] Module README template created

---

## 📦 Milestone 2: Agent & Orchestration Contracts (Weeks 4-6)

**Goal:** Define agent lifecycle, orchestration, planning, error recovery, and capability security contracts

### **Milestone Deliverables:**

- [ ] Agent lifecycle FSM contracts (6 states)
- [ ] Orchestration 3-phase contracts (Contract Net Protocol)
- [ ] Planning pipeline contracts (4 stages)
- [ ] Saga pattern error recovery contracts
- [ ] Circuit breaker contracts
- [ ] Capability-based security contracts (unforgeable tokens)

---

## Epic 2.1: Agent Lifecycle Contracts

**ADR Source:** ADR-0005, ADR-0005a-e
**Timeline:** Week 4 (5 days)
**Dependencies:** Milestone 1 (Actor Model, Protocols)

### **Issues for Epic 2.1:**

#### **Issue 2.1.1: Agent Lifecycle FSM Contract**

**Effort:** 1 day | **Source ADR:** `0005-agent-lifecycle-fsm.md`

**Expected Output:** `contracts/agent_lifecycle/`

```
├── lifecycle_fsm.yml                # 6-state FSM: PENDING → WARMING → ACTIVE → IDLE → DRAINING → TERMINATED
├── state_transitions.yml            # Transition rules and triggers
├── warming_state.yml                # Model preloading, KV cache warming (ADR-0005a)
├── idle_pooling.yml                 # Fast reactivation from idle pool (ADR-0005b)
├── draining_shutdown.yml            # Graceful task completion (ADR-0005c)
└── performance_budgets.yml          # <45ms spawn, <60s idle timeout
```

**Key Contracts:**

- FSM state definitions with entry/exit actions
- Transition guards and timing constraints
- Performance budgets per state

---

#### **Issue 2.1.2: Supervisor Monitoring & Blacklist Contracts**

**Effort:** 1 day | **Source ADR:** `0005d-supervisor-blacklist.md`

**Expected Output:** `contracts/agent_lifecycle/supervisor/`

```
├── health_monitoring.yml            # 1Hz ping, 3 missed = crash
├── crash_detection.yml              # Crash criteria and logging
├── blacklist_policy.yml             # 3 crashes in 10min → blacklist 1hr
├── resource_monitoring.yml          # Memory/CPU per agent tracking
└── rollback_strategy.yml            # Terminate unhealthy agents
```

---

#### **Issue 2.1.3: Agent Personality & Capabilities Contracts**

**Effort:** 1 day | **Source ADR:** `0005e-agent-personality-capabilities.md`

**Expected Output:** `contracts/agent_lifecycle/personality/`

```
├── capability_tokens.yml            # Unforgeable capability tokens
├── persona_prompts.yml              # Jinja2 prompt templates (AI agents only)
├── personality_traits.yml           # Formality, verbosity, empathy scores
├── capability_assignment.yml        # Role-based capability distribution
└── agent_registry_schema.yml        # YAML agent specifications
```

---

## Epic 2.2: Orchestration Contracts (Contract Net Protocol)

**ADR Source:** ADR-0006, ADR-0006a-e
**Timeline:** Week 4-5 (3 days)
**Dependencies:** Epic 2.1 (Agent Lifecycle)

### **Issues for Epic 2.2:**

#### **Issue 2.2.1: 3-Phase Orchestration Contract**

**Effort:** 1 day | **Source ADR:** `0006-3phase-orchestration-contract-net.md`

**Expected Output:** `contracts/orchestration/3phase/`

```
├── negotiation_phase.yml            # Task announcement → proposals
├── selection_phase.yml              # Multi-criteria scoring
├── execution_phase.yml              # Task execution → result
├── contract_net_protocol.yml        # CNP message formats
└── orchestration_metrics.yml        # Latency, success rate
```

---

#### **Issue 2.2.2: Multi-Criteria Scoring Contract**

**Effort:** 1 day | **Source ADR:** `0006b-multi-criteria-scoring.md`

**Expected Output:** `contracts/orchestration/scoring/`

```
├── scoring_algorithm.yml            # Capability (0.4) + Latency (0.3) + Cost (0.2) + Specialization (0.1)
├── capability_matching.yml          # Required vs provided capabilities
├── latency_scoring.yml              # Latency budget vs agent estimate
├── cost_scoring.yml                 # Cost budget vs agent quote
└── specialization_bonus.yml         # Domain expertise weighting
```

---

#### **Issue 2.2.3: Parallel DAG Execution & Saga Integration**

**Effort:** 1 day | **Source ADR:** `0006c-parallel-dag-execution.md`, `0006d-saga-pattern-integration.md`

**Expected Output:** `contracts/orchestration/execution/`

```
├── dag_execution.yml                # Parallel task execution with dependencies
├── task_dependencies.yml            # DAG topology representation
├── saga_integration.yml             # Error recovery via compensating transactions
└── execution_metrics.yml            # Throughput, parallelism metrics
```

---

## Epic 2.3: Planning Pipeline Contracts

**ADR Source:** ADR-0007, ADR-0007a-d
**Timeline:** Week 5 (3 days)
**Dependencies:** Epic 2.2 (Orchestration)

### **Issues for Epic 2.3:**

#### **Issue 2.3.1: 4-Stage Planning Pipeline Contract**

**Effort:** 1 day | **Source ADR:** `0007-4stage-planning-pipeline.md`

**Expected Output:** `contracts/planning/pipeline/`

```
├── sketch_stage.yml                 # LLM-powered plan sketching (ADR-0007a)
├── expand_stage.yml                 # Tool/prompt registry integration (ADR-0007b)
├── validation_stage.yml             # 2-tier: rules + arbiter (ADR-0007c)
├── commit_stage.yml                 # K0 WAL integration (ADR-0007d)
└── pipeline_performance.yml         # 50-80ms P95 target
```

**Key Contracts:**

- Sketch stage: LLM prompt templates for Planner AI agent
- Expand stage: Tool registry lookup, prompt template selection
- Validation stage: Rule engine + arbiter fallback
- Commit stage: Plan persistence to K0

---

#### **Issue 2.3.2: Tool & Prompt Registry Contracts**

**Effort:** 1 day | **Source ADR:** `0007b-expand-stage-tool-prompt-registry-integration.md`

**Expected Output:** `contracts/planning/registries/`

```
├── tool_registry_schema.yml         # Tool catalog (JSON specs)
├── prompt_registry_schema.yml       # Prompt templates (Jinja2)
├── tool_selection_rules.yml         # Tool matching algorithm
└── prompt_selection_rules.yml       # Role/size-based prompt selection
```

---

#### **Issue 2.3.3: Plan Validation Contracts**

**Effort:** 1 day | **Source ADR:** `0007c-validation-stage-2-tier-implementation.md`

**Expected Output:** `contracts/planning/validation/`

```
├── rule_engine_schema.yml           # Validation rules (cycles, budgets, capabilities)
├── arbiter_contract.yml             # Human-in-loop arbiter for RED band
├── validation_metrics.yml           # Pass rate, arbiter escalation rate
└── fallback_policies.yml            # Validation failure handling
```

---

## Epic 2.4: Error Recovery Contracts (Saga & Circuit Breaker)

**ADR Source:** ADR-0008, ADR-0008a-d, ADR-0009, ADR-0009a-c
**Timeline:** Week 6 (5 days)
**Dependencies:** Epic 2.2, 2.3 (Orchestration, Planning)

### **Issues for Epic 2.4:**

#### **Issue 2.4.1: Saga Pattern Contracts**

**Effort:** 2 days | **Source ADR:** `0008-saga-pattern-error-recovery.md`

**Expected Output:** `contracts/error_recovery/saga/`

```
├── saga_definition.yml              # Saga state machine
├── compensating_transactions.yml    # Rollback handlers (ADR-0008a)
├── forward_vs_backward_recovery.yml # Recovery strategy selection (ADR-0008b)
├── distributed_state_management.yml # State tracking across agents (ADR-0008c)
└── timeout_deadlock_handling.yml    # Timeout enforcement, deadlock detection (ADR-0008d)
```

**Key Contracts:**

- Compensating transaction design (idempotent, logged)
- Forward recovery (retry, continue) vs backward recovery (rollback, abort)
- Distributed state tracking (saga log)
- Timeout policies per saga step

---

#### **Issue 2.4.2: Circuit Breaker Contracts**

**Effort:** 2 days | **Source ADR:** `0009-circuit-breaker-pattern.md`

**Expected Output:** `contracts/error_recovery/circuit_breaker/`

```
├── circuit_breaker_fsm.yml          # 3-state FSM: CLOSED → OPEN → HALF_OPEN (ADR-0009a)
├── per_service_config.yml           # Service-specific thresholds (ADR-0009b)
├── circuit_breaker_metrics.yml      # Observability (ADR-0009c)
└── failure_criteria.yml             # 3 failures → open for 60s
```

---

#### **Issue 2.4.3: Timeout & Deadlock Handling Contracts**

**Effort:** 1 day | **Source ADR:** `0008d-timeout-deadlock-handling.md`

**Expected Output:** `contracts/error_recovery/timeouts/`

```
├── timeout_policies.yml             # Per-operation timeout budgets
├── deadlock_detection.yml           # Circular wait detection
├── timeout_enforcement.yml          # Timeout injection, cancellation
└── recovery_strategies.yml          # Retry, abort, escalate
```

---

## Epic 2.5: Capability-Based Security Contracts

**ADR Source:** ADR-0010, ADR-0010a-d
**Timeline:** Week 6 (5 days)
**Dependencies:** Epic 2.1, 2.2, 2.3 (Agent Lifecycle, Orchestration, Planning)

### **Issues for Epic 2.5:**

#### **Issue 2.5.1: Capability Token Design Contracts**

**Effort:** 2 days | **Source ADR:** `0010-capability-based-security.md`, `0010a-capability-token-design-lifecycle.md`

**Expected Output:** `contracts/security/capabilities/`

```
├── capability_token_schema.yml      # Unforgeable token structure (capability_id, subject, resource, rights, constraints)
├── hmac_sha256_signing.yml          # Cryptographic signature with secret key
├── capability_rights_enum.yml       # Standard rights (READ, WRITE, EXECUTE, DELETE, DELEGATE, ATTENUATE)
├── privacy_band_enum.yml            # Privacy classifications (GREEN, AMBER, RED, BLACK)
├── capability_constraints.yml       # Usage constraints (max_cost_usd, max_invocations, requires_approval, privacy_band)
├── capability_validation.yml        # Validation logic (signature check, expiration, constraints)
└── capability_lifecycle.yml         # Issuance, verification, revocation, delegation
```

**Key Contracts:**

- Capability token structure with HMAC-SHA256 signature
- Rights enum (READ, WRITE, EXECUTE, DELETE, DELEGATE, ATTENUATE)
- Constraints schema (max_cost_usd, max_invocations, privacy_band)
- Validation rules (signature, expiration, invocation limits)

---

#### **Issue 2.5.2: Capability Manager Contracts**

**Effort:** 2 days | **Source ADR:** `0010-capability-based-security.md`

**Expected Output:** `contracts/security/capability_manager/`

```
├── capability_issuance.yml          # Issue capability with signing
├── capability_verification.yml      # Verify signature + validate constraints
├── capability_revocation.yml        # Revoke capability (add to revocation list)
├── capability_registry.yml          # In-memory capability storage (Redis)
├── role_based_templates.yml         # Role-to-capability mappings (planner, booking_agent, etc.)
├── secret_key_management.yml        # Secret key rotation (90-day policy)
└── capability_metrics.yml           # Prometheus metrics (issued, verified, denied, revoked)
```

**Key Contracts:**

- Capability Manager API (issue, verify, revoke)
- Role-based capability templates (planner → read_tools only)
- Secret key management (rotation, storage in Vault)
- Metrics for observability

---

#### **Issue 2.5.3: Agent Capability Assignment Contracts**

**Effort:** 1 day | **Source ADR:** `0010b-agent-capability-assignment-policy.md`

**Expected Output:** `contracts/security/agent_capabilities/`

```
├── planner_agent_capabilities.yml   # Planner: read_tools, execute_read_tools (no write, no delete)
├── booking_agent_capabilities.yml   # Booking: execute_booking, max_cost_usd: 100.0, requires_approval: true
├── tool_runner_capabilities.yml     # Tool Runner: execute_tools per tool (weather, calendar, booking)
├── orchestrator_capabilities.yml    # Orchestrator: delegate capabilities to sub-agents
├── least_privilege_policy.yml       # Minimum capabilities per agent role
└── capability_delegation_rules.yml  # Delegation & attenuation policies
```

**Key Contracts:**

- Per-agent capability templates (4 AI agents + key pure actors)
- Least privilege enforcement (Planner can't book reservations)
- Delegation rules (Orchestrator can delegate attenuated capabilities)

---

#### **Issue 2.5.4: Capability Enforcement & Audit Contracts**

**Effort:** 1 day | **Source ADR:** `0010c-capability-enforcement-runtime.md`, `0010d-capability-revocation-audit-trail.md`

**Expected Output:** `contracts/security/enforcement/`

```
├── tool_runner_enforcement.yml      # Tool Runner checks capability before execution
├── model_hub_enforcement.yml        # Model Hub checks capability before LLM call
├── hot_path_validation.yml          # <1ms validation latency (HMAC check + constraint validation)
├── audit_trail_schema.yml           # K0 WAL audit log (capability_id, agent_id, resource, action, timestamp)
├── revocation_propagation.yml       # Multi-instance revocation (Redis pub/sub)
├── revoked_capability_handling.yml  # Graceful revocation (allow in-flight operations to complete)
└── capability_usage_metrics.yml     # Prometheus metrics per resource/agent
```

**Key Contracts:**

- Hot path enforcement (<1ms validation before every tool/model call)
- Audit trail to K0 WAL (100% capability usage logged)
- Revocation propagation (Redis pub/sub for multi-instance K1)
- Metrics for observability (denial reasons, usage patterns)

---

#### **Issue 2.5.5: Band-Based Egress Rules Contracts**

**Effort:** 4 days | **Source ADR:** `0032-band-based-egress-rules.md` + sub-ADRs `0032a-d`

**Expected Output:** `contracts/security/egress/` (17 files)

**Network Egress Control - ADR-0032a (4 files):**

```
├── iptables_egress_controller.yml              # Iptables --pid-owner process isolation: Per-tool firewall rules, <5ms rule setup via iptables-restore, default-deny policy (DROP all OUTPUT), cleanup on tool exit, supports IPv4/IPv6
├── privacy_band_network_policies.yml           # Privacy band policies: GREEN (whitelisted domains: *.openai.com *.anthropic.com, 443/tcp only), AMBER (+ PII masking proxy), RED (127.0.0.1 only), BLACK (all network blocked)
├── domain_whitelist_manager.yml                # Domain whitelist per tool: web_search (*.google.com, *.bing.com), image_generation (*.replicate.com), llm_call (provider domains), dynamic reload from config <100ms
└── private_ip_blocker.yml                      # Private IP blocking: Block 192.168.0.0/16, 10.0.0.0/8, 172.16.0.0/12, 169.254.0.0/16 (except RED band 127.0.0.1), block port 22/23/3389 (SSH/Telnet/RDP), <1ms rule evaluation
```

**Filesystem Egress Control - ADR-0032b (5 files):**

```
├── chroot_jail_manager.yml                     # Chroot jail creation: Ephemeral jails from templates (minimal-jail, python-jail, node-jail), <3ms jail setup, per-tool isolation (tool_id → /tmp/jail_<tool_id>), cleanup on exit
├── readonly_mounts_system.yml                  # Read-only mounts: /usr/lib (system libraries), /usr/bin (binaries), /etc/resolv.conf (DNS), /tmp/input (tool input data), mounted with MS_RDONLY + MS_NOSUID + MS_NODEV
├── writable_output_isolation.yml               # Writable output: /tmp/output only (max 100MB per tool), tmpfs mount (memory-backed, fast cleanup), quota enforcement (du -s check before write), violation → ENOSPC error
├── seccomp_bpf_filter.yml                      # Seccomp-bpf syscall filtering: Block dangerous syscalls (mount, umount, pivot_root, ptrace, reboot, swapon, chroot, kexec_load), SECCOMP_RET_KILL on violation, <0.1ms filter load
└── ephemeral_jail_cleanup.yml                  # Ephemeral cleanup: Jail destruction on tool exit (<100ms), rm -rf /tmp/jail_<tool_id>, unmount all mounts, iptables rule cleanup, kill remaining processes (killall -9 in cgroup)
```

**Resource Egress Control - ADR-0032c (4 files):**

```
├── cgroups_v2_controller.yml                   # Cgroups v2 controller: Per-tool cgroup creation /sys/fs/cgroup/k1_tool_<tool_id>, <2ms cgroup setup, zero runtime overhead, automatic cleanup on process exit via notify_on_release
├── cpu_memory_limits_by_band.yml               # CPU/Memory limits by privacy band: GREEN (cpu.max 400000 100000 = 4 CPUs, memory.max 2GB), AMBER (200000 100000 = 2 CPUs, 1GB), RED (100000 100000 = 1 CPU, 512MB), BLACK (0 resources)
├── pid_limits_fork_bomb_protection.yml         # PID limits (fork bomb protection): GREEN (pids.max 100), AMBER (50), RED (20), BLACK (1), prevents runaway process creation, violation → EAGAIN on fork/clone
└── io_throttling_bandwidth_limits.yml          # I/O throttling: GREEN (io.max 10GB/s writes), AMBER (5GB/s), RED (1GB/s), BLACK (100KB/s), disk quota enforcement, prevents disk exhaustion attacks
```

**Egress Violation Logging - ADR-0032d (4 files):**

```
├── violation_detector.yml                      # Violation detector: Capture events from iptables LOG target, seccomp audit, cgroups notifications, filesystem inotify, <1ms event capture, batch 100 events/sec
├── k0_tool_receipt_integration.yml             # K0 ToolReceipt integration: Write violation events to ToolReceipt FlatBuffers, batch forward to K0 (100 events → 1 batch), <10ms forward latency, async (non-blocking tool execution)
├── violation_severity_classifier.yml           # Severity classification: LOW (expected behavior: GREEN tool accessing whitelisted domain), MEDIUM (suspicious: repeated attempts), HIGH (attack likely: RED tool network attempt), CRITICAL (active breach: seccomp kill)
└── compliance_audit_trail_7year.yml            # Compliance audit trail: 7-year retention (SOC2/ISO27001), tamper-proof append-only logs, 500 bytes/event (tool_id, violation_type, timestamp, resource, privacy_band, severity), indexed by session_id/tool_id
```

**Key Contracts:**

- Network isolation (iptables --pid-owner per-tool, <5ms setup)
- Filesystem isolation (chroot + seccomp, <3ms jail setup)
- Resource limits (cgroups v2, <2ms setup, zero runtime overhead)
- Violation logging (K0 ToolReceipt integration, 7-year compliance audit trail)

---

## Epic 2.6: MPST Protocol Detailed Contracts (6 Protocols)

**ADR Source:** ADR-0003 (MPST Protocol Validation), Scribble/MPST specifications
**Timeline:** Week 6 (3 days, parallel with Epic 2.5)
**Dependencies:** Epic 1.3 (MPST Protocol PDL definitions), Epic 2.1-2.3 (Agent, Orchestration, Planning)

### **Issues for Epic 2.6:**

#### **Issue 2.6.1: Agent Hire Protocol FSM Contracts**

**Effort:** 1 day | **Source ADR:** `0003-mpst-protocol-validation.md`, architecture_diagrams/k1_agent_lifecycle_fsm.mmd

**Expected Output:** `contracts/protocols/agent_hire/`

```
├── hire_protocol_fsm.yml            # 6-state FSM (PENDING → WARMING → ACTIVE → IDLE → DRAINING → TERMINATED)
├── hire_request_contract.yml        # Orchestrator → Supervisor: AgentHireRequest (required_capabilities, memory_budget_mb, warmup_timeout_ms)
├── hire_response_contract.yml       # Supervisor → Orchestrator: AgentHireResponse (HIRED/REJECTED/TIMEOUT/OUT_OF_MEMORY)
├── warmup_contracts.yml             # PENDING → WARMING: Model loading, resource allocation, capability assignment
├── activation_contracts.yml         # WARMING → ACTIVE: Health check pass, ready for tasks
├── idle_detection_contracts.yml     # ACTIVE → IDLE: No tasks for idle_timeout_ms (default 60s)
├── drain_initiation_contracts.yml   # IDLE → DRAINING: Supervisor initiates drain, finish in-flight tasks
├── termination_contracts.yml        # DRAINING → TERMINATED: Cleanup resources, release memory
├── crash_handling_contracts.yml     # * → TERMINATED: Unhandled exception, crash detection, blacklist (3 crashes in 10min)
└── timeout_enforcement.yml          # Protocol timeouts (warmup: 200ms, idle: 60s, drain: 5s)
```

**Key Contracts:**

- 6-state agent lifecycle FSM with deterministic transitions
- Hire request/response message schemas (FlatBuffers)
- Timeout enforcement contracts (warmup <200ms, drain <5s)
- Crash detection and blacklist management (3 crashes → 1 hour blacklist)

---

#### **Issue 2.6.2: Task Execution Protocol Contracts**

**Effort:** 1 day | **Source ADR:** `0003-mpst-protocol-validation.md`, ADR-0006 (3-Phase Orchestration)

**Expected Output:** `contracts/protocols/task_execution/`

```
├── task_protocol_fsm.yml            # 4-phase FSM (ANNOUNCE → PROPOSE → SELECT → EXECUTE → COMPLETE)
├── task_announcement_contract.yml   # Orchestrator → All Agents: TaskAnnouncement (task_id, intent, user_input, required_capabilities)
├── proposal_request_contract.yml    # Orchestrator → Eligible Agents: ProposalRequest (task_id, deadline_ms)
├── proposal_response_contract.yml   # Agent → Orchestrator: Proposal (agent_id, estimated_latency_ms, confidence, cost_usd)
├── selection_contract.yml           # Orchestrator internal: Selection algorithm (Hiring Score = 0.4*confidence + 0.3*latency + 0.3*cost)
├── task_assignment_contract.yml     # Orchestrator → Winner Agent: TaskAssignment (task_id, timeout_ms, budget)
├── progress_monitoring_contract.yml # Agent → Orchestrator: ProgressUpdate (task_id, progress_percent, eta_ms)
├── completion_contract.yml          # Agent → Orchestrator: TaskResult (task_id, success, result, latency_ms, receipts)
├── failure_handling_contract.yml    # Agent → Orchestrator: TaskFailure (task_id, error_code, retry_after_ms)
└── timeout_enforcement.yml          # Protocol timeouts (proposal: 100ms, execution: 5000ms)
```

**Key Contracts:**

- 4-phase task execution protocol (Contract Net Protocol)
- Hiring score algorithm (0.4 confidence + 0.3 latency + 0.3 cost)
- Progress monitoring with progress updates
- Failure handling with retry strategies

---

#### **Issue 2.6.3: Clarification Protocol Contracts**

**Effort:** 0.5 day | **Source ADR:** `0003-mpst-protocol-validation.md`

**Expected Output:** `contracts/protocols/clarification/`

```
├── clarification_protocol_fsm.yml   # 3-state FSM (REQUEST → WAITING_RESPONSE → RESOLVED)
├── clarification_request_contract.yml # Planner → User: ClarificationRequest (question, options, context, priority)
├── clarification_response_contract.yml # User → Planner: ClarificationResponse (answer, confidence, timestamp)
├── timeout_handling_contract.yml    # Timeout if no response in 60s (use default, escalate, abort)
├── priority_levels.yml              # Priority (BLOCKING: wait, OPTIONAL: use default)
└── websocket_delivery.yml           # WebSocket message type: CLARIFICATION_REQUEST
```

**Key Contracts:**

- 3-state clarification FSM (REQUEST → WAITING → RESOLVED)
- Clarification request/response schemas
- Timeout handling (60s → use default or escalate)
- Priority levels (BLOCKING vs OPTIONAL)

---

#### **Issue 2.6.4: Barge-In Protocol Contracts**

**Effort:** 0.5 day | **Source ADR:** `0003-mpst-protocol-validation.md`

**Expected Output:** `contracts/protocols/barge_in/`

```
├── barge_in_protocol_fsm.yml        # 4-state FSM (STREAMING → INTERRUPTED → DRAINING → RESUMED)
├── barge_in_signal_contract.yml     # Client → Server: BargeInSignal (reason: STOP/NEW_INPUT, timestamp)
├── interrupt_propagation_contract.yml # API Gateway → Agent: InterruptSignal (agent_id, turn_id)
├── drain_contract.yml               # Agent → Orchestrator: DrainInProgress (tasks_remaining, eta_ms)
├── resume_contract.yml              # Orchestrator → Agent: ResumeExecution (task_id, context)
├── latency_target.yml               # Barge-in latency <120ms P95 (from user input to agent interrupt)
└── websocket_delivery.yml           # WebSocket message type: BARGE_IN
```

**Key Contracts:**

- 4-state barge-in FSM (STREAMING → INTERRUPTED → DRAINING → RESUMED)
- Interrupt propagation (WebSocket → API Gateway → Agent)
- Drain contracts (finish in-flight operations)
- Latency target (<120ms P95 from user input to agent interrupt)

---

#### **Issue 2.6.5: Tool Call Protocol Contracts**

**Effort:** 0.5 day | **Source ADR:** `0003-mpst-protocol-validation.md`

**Expected Output:** `contracts/protocols/tool_call/`

```
├── tool_call_protocol_fsm.yml       # 5-state FSM (REQUESTED → APPROVAL_PENDING → EXECUTING → COMPLETED/FAILED)
├── tool_call_request_contract.yml   # Agent → Tool Runner: ToolCall (tool_name, args, privacy_band, budget)
├── approval_required_contract.yml   # Tool Runner → User: ToolApproval (tool_name, args, privacy_band, estimated_cost)
├── approval_response_contract.yml   # User → Tool Runner: ToolApprovalResponse (approved, reason)
├── execution_contract.yml           # Tool Runner → Tool: ToolExecution (sandbox config, timeout_ms, capability token)
├── result_contract.yml              # Tool → Tool Runner: ToolResult (success, result, latency_ms, cost_usd)
├── failure_handling_contract.yml    # Tool → Tool Runner: ToolFailure (error_code, retry_after_ms, fallback_tool)
├── capability_enforcement.yml       # Tool Runner validates capability token before execution
└── timeout_enforcement.yml          # Protocol timeouts (approval: 30s, execution: 3000ms)
```

**Key Contracts:**

- 5-state tool call FSM (REQUEST → APPROVAL → EXECUTE → COMPLETE/FAIL)
- Approval workflow for RED band tools (user must approve)
- Capability token enforcement (Tool Runner validates before execution)
- Timeout enforcement (approval: 30s, execution: 3000ms)

---

#### **Issue 2.6.6: Saga Rollback Protocol Contracts**

**Effort:** 0.5 day | **Source ADR:** `0003-mpst-protocol-validation.md`, ADR-0009 (Saga Pattern)

**Expected Output:** `contracts/protocols/saga_rollback/`

```
├── saga_protocol_fsm.yml            # 5-state FSM (EXECUTING → COMPENSATING → ROLLED_BACK/FAILED)
├── saga_definition_contract.yml     # Saga structure (steps, compensations, dependencies)
├── compensation_request_contract.yml # Orchestrator → Agent: CompensationRequest (saga_id, step_id, original_action)
├── compensation_response_contract.yml # Agent → Orchestrator: CompensationResult (success, rollback_complete)
├── rollback_strategy.yml            # Rollback strategies (UNDO, COMPENSATE, BEST_EFFORT)
├── partial_rollback.yml             # Partial rollback if compensation fails (log, alert, manual intervention)
├── idempotency_contracts.yml        # Compensation idempotency (safe to retry)
└── timeout_enforcement.yml          # Compensation timeout (5000ms, then fail saga)
```

**Key Contracts:**

- 5-state saga FSM (EXECUTE → COMPENSATE → ROLLBACK/FAIL)
- Compensation request/response schemas
- Rollback strategies (UNDO, COMPENSATE, BEST_EFFORT)
- Idempotency guarantees (safe to retry compensations)

---

**Epic 2.6 Summary:** 6 MPST protocol detailed contracts (Agent Hire, Task Execution, Clarification, Barge-In, Tool Call, Saga Rollback). Each protocol has FSM state machine contracts, message schemas (request/response), timeout enforcement, and failure handling. Total: 54 contract files (9 per protocol on average).

---

## Epic 2.7: Tool Execution & Sandbox Contracts (ADR-0033)

**ADR Source:** ADR-0033 (Three-Tier Sandbox Strategy), Sub-ADRs 0033a-d
**Timeline:** Week 6 (4 days, parallel with Epic 2.6)
**Dependencies:** Epic 2.5 (Egress Rules), Epic 1.1 (K0 Ports)

**Epic Overview:** 2-layer tool execution architecture with Protocol Layer (MCP/Direct) × Sandbox Layer (WASM/Process/Container) providing 100% tool coverage, graduated security, and automatic selection with fallback cascade.

### **Issues for Epic 2.7:**

#### **Issue 2.7.1: 2D Tool Execution Architecture Contracts**

**Effort:** 1 day | **Source ADR:** `0033-three-tier-sandbox-strategy.md`

**Expected Output:** `contracts/tools/architecture/` (5 files)

```
├── 2d_architecture_protocol_sandbox.yml    # Protocol Layer (MCP 80%, Direct 20%) × Sandbox Layer (WASM 15%, Process 80%, Container 5%), 6 valid combinations
├── protocol_layer_mcp_vs_direct.yml        # MCP Protocol (JSON-RPC 2.0 over stdio/HTTP) vs Direct API (REST/CLI), 80% MCP adoption (608 tools)
├── sandbox_layer_wasm_process_container.yml # WASM (zero syscalls, capability-based), Process (ADR-0032 egress), Container (Firecracker microVM), graduated isolation
├── valid_combinations_matrix.yml           # MCP+WASM (10%), MCP+Process (70%), Direct+Process (15%), etc. - Coverage: 100% of tools
└── tool_registry_yaml_format.yml           # Tool definition: protocol (mcp|direct), sandbox (wasm|process|container), band (GREEN|AMBER|RED), timeout, capabilities
```

---

#### **Issue 2.7.2: MCP Protocol Integration Contracts (Layer 1)**

**Effort:** 1 day | **Source ADR:** `0033a-mcp-protocol-integration.md`

**Expected Output:** `contracts/tools/mcp_protocol/` (6 files)

```
├── json_rpc_2_0_protocol.yml               # JSON-RPC 2.0 format: {"jsonrpc":"2.0", "method":"tools/call", "params":{...}, "id":"..."}, stdio/HTTP transports
├── mcp_client_implementation.yml           # MCPClient wraps JSON-RPC, supports stdio (70%) and HTTP (10%) transports, timeout enforcement per tool
├── mcp_server_lifecycle.yml                # Server states: initialize → tools/list → tools/call → shutdown, graceful termination (SIGTERM → 5s → SIGKILL)
├── stdio_transport_pipes.yml               # JSON-RPC over stdin/stdout pipes (newline-delimited JSON), for Process sandbox MCP servers
├── http_transport_post.yml                 # JSON-RPC over HTTP POST (for WASM sandbox MCP servers, since stdio unavailable in WASM)
└── protocol_sandbox_independence.yml       # MCP protocol (Layer 1) works with ANY sandbox (Layer 2: WASM, Process, Container), orthogonal concerns
```

---

#### **Issue 2.7.3: WASM Sandbox Implementation Contracts (Layer 2)**

**Effort:** 1 day | **Source ADR:** `0033b-wasm-sandbox-implementation.md`

**Expected Output:** `contracts/tools/wasm_sandbox/` (7 files)

```
├── wasmtime_runtime.yml                    # Wasmtime runtime initialization, WASM module loading from .wasm file, <10ms instantiation
├── wasi_capabilities_filesystem.yml        # WASI preopened directories (e.g., /tmp/tool_workspace), capability-based filesystem access (can't access random files)
├── wasi_capabilities_network.yml           # WASI allowed hosts (e.g., api.openweathermap.org), capability-based network access (can't connect to arbitrary hosts)
├── zero_syscall_isolation.yml              # WASM cannot call OS syscalls directly (no open, socket, exec), 100% isolation from host OS
├── cross_platform_wasm.yml                 # WASM runs identically on Linux, macOS, Windows (no OS-specific dependencies), <5MB memory per module
├── performance_tradeoff_10x_slower.yml     # WASM 10x slower than native (acceptable for 15% untrusted tools), use Process sandbox for 80% of tools
└── mcp_in_wasm_integration.yml             # MCP server implemented in WASM (user_plugin.wasm), HTTP transport for MCP protocol (stdio unavailable in WASM)
```

---

#### **Issue 2.7.4: Process Sandbox Implementation Contracts (Layer 2)**

**Effort:** 1 day | **Source ADR:** `0033c-process-sandbox-implementation.md`

**Expected Output:** `contracts/tools/process_sandbox/` (8 files)

```
├── os_process_isolation.yml                # Separate PID per tool, no shared memory, subprocess.Popen spawning, <100ms overhead
├── adr_0032_egress_integration.yml         # Full ADR-0032 4-layer egress control: iptables (network), chroot (filesystem), cgroups (resource), audit logging
├── network_egress_iptables.yml             # iptables --pid-owner per-tool, privacy band policies (GREEN/AMBER/RED), <5ms rule setup (from ADR-0032a)
├── filesystem_egress_chroot.yml            # chroot jails per tool, read-only system mounts, writable output isolation (/tmp/output), seccomp-bpf (from ADR-0032b)
├── resource_egress_cgroups.yml             # cgroups v2 limits (CPU, memory, PIDs, I/O), privacy band resource policies, <2ms setup (from ADR-0032c)
├── violation_logging_k0.yml                # Violation detector, K0 ToolReceipt integration, 7-year compliance audit trail (from ADR-0032d)
├── native_performance.yml                  # <100ms process spawn + egress setup, native syscalls allowed (filtered by seccomp), 80% of tools use Process sandbox
└── mcp_over_stdio.yml                      # MCP server as native process (weather_api.py), JSON-RPC over stdin/stdout pipes, MCPClient stdio transport
```

---

#### **Issue 2.7.5: 2D Selection Logic & Fallback Cascade**

**Effort:** 1 day | **Source ADR:** `0033d-2d-selection-logic.md`

**Expected Output:** `contracts/tools/selection/` (6 files)

```
├── tool_execution_selector.yml             # ToolExecutionSelector algorithm: Evaluates 6 valid combinations (MCP×WASM, MCP×Process, MCP×Container, Direct×WASM, Direct×Process, Direct×Container)
├── protocol_selection_axis1.yml            # Axis 1: MCP (if tool has MCP server, 80%) vs Direct (legacy tools, 20%), prefer MCP for standardization
├── sandbox_selection_axis2.yml             # Axis 2: WASM (untrusted code, 15%) vs Process (standard tools, 80%) vs Container (RED band high-risk, 5%)
├── fallback_cascade_4_stages.yml           # Stage 1: Preferred (MCP+WASM) → Stage 2: Fallback sandbox (MCP+Process) → Stage 3: Fallback protocol (Direct+Process) → Stage 4: Double fallback (Direct+WASM)
├── tool_characteristics_criteria.yml       # Selection criteria: tool_name, band (GREEN/AMBER/RED), trust_level (TRUSTED/VERIFIED/UNTRUSTED), has_mcp_server, performance_critical
└── observability_metrics.yml               # Log every selection decision with rationale, metrics for fallback frequency, tracing for debugging
```

**Key Contracts for Epic 2.7:**

- 2D architecture: Protocol (MCP/Direct) × Sandbox (WASM/Process/Container)
- MCP protocol integration (JSON-RPC 2.0, stdio/HTTP)
- WASM sandbox (Wasmtime, WASI, zero syscalls, 15% tools)
- Process sandbox (OS isolation, ADR-0032 egress, 80% tools)
- Automatic selection with 4-stage fallback cascade

**Total Contracts: 32 files** (5 architecture + 6 MCP + 7 WASM + 8 Process + 6 selection)

---

## Epic 2.8: MCP Protocol Integration Contracts (ADR-0034)

**ADR Source:** ADR-0034 (MCP Protocol for Tool Integration), Sub-ADRs 0034a-d
**Timeline:** Week 7 (5 days, parallel with Epic 3.1)
**Dependencies:** Epic 2.7 (Tool Execution Architecture), Epic 2.4 (Error Recovery)

**Epic Overview:** MCP protocol implementation with JSON-RPC 2.0, process lifecycle management, circuit breaker resilience, and comprehensive error handling achieving 98% crash isolation and 92% cascade prevention.

### **Issues for Epic 2.8:**

#### **Issue 2.8.1: JSON-RPC 2.0 Protocol Implementation**

**Effort:** 1 day | **Source ADR:** `0034a-mcp-jsonrpc-protocol.md`

**Expected Output:** `contracts/mcp/jsonrpc/` (7 files)

```
├── jsonrpc_request_format.yml              # JSON-RPC 2.0 request: {"jsonrpc":"2.0", "method":"tools/call", "params":{...}, "id":"UUID"}, validation rules
├── jsonrpc_response_format.yml             # Success response: {"jsonrpc":"2.0", "result":{...}, "id":"UUID"} OR Error response: {"jsonrpc":"2.0", "error":{code,message,data}, "id":"UUID"}
├── jsonrpc_error_codes.yml                 # Standard error codes: -32700 (parse error), -32600 (invalid request), -32601 (method not found), -32602 (invalid params), -32603 (internal error)
├── stdio_transport_impl.yml                # StdioTransport: Newline-delimited JSON over stdin/stdout pipes, async request/response matching by ID, pending_requests: Dict[str, Future]
├── http_transport_impl.yml                 # HttpTransport: JSON-RPC over HTTP POST, used for WASM sandbox MCP servers (stdio unavailable in WASM)
├── request_id_tracking.yml                 # Unique request ID (UUID v4) for every request, client tracks pending requests (request_id → Future mapping), match responses to requests
└── method_routing.yml                      # Standard MCP methods: initialize, tools/list, tools/call, shutdown, method dispatcher (method → handler function)
```

---

#### **Issue 2.8.2: MCP Process Lifecycle & Timeout Enforcement**

**Effort:** 1 day | **Source ADR:** `0034b-mcp-process-lifecycle.md`

**Expected Output:** `contracts/mcp/lifecycle/` (8 files)

```
├── lifecycle_fsm_5_states.yml              # 5-state FSM: SPAWNING (starting) → RUNNING (healthy) → TERMINATING (graceful shutdown) → TERMINATED (exited cleanly) → CRASHED (non-zero exit/signal)
├── process_spawner.yml                     # MCPProcessSpawner: asyncio.create_subprocess_exec(stdin=PIPE, stdout=PIPE, stderr=PIPE), track process state (lifecycle FSM)
├── initialize_request.yml                  # SPAWNING → RUNNING: Send "initialize" JSON-RPC request, wait for response (timeout: 5s), server responds with capabilities
├── timeout_enforcement.yml                 # Per-tool timeout configuration (calculator: 5s, video: 300s, default: 30s), asyncio.wait_for wraps request, on timeout: SIGTERM → 5s → SIGKILL
├── graceful_shutdown.yml                   # RUNNING → TERMINATING: Send "shutdown" JSON-RPC request, wait 5s for graceful exit, if not exited: SIGTERM → 5s → SIGKILL
├── crash_detection.yml                     # RUNNING → CRASHED: Monitor process exit code (0 = clean, non-zero = error), monitor signals (SIGSEGV, SIGABRT = crash), emit crash event
├── resource_cleanup.yml                    # TERMINATING/CRASHED → TERMINATED: Close stdin/stdout pipes (prevent PIPE buffer leaks), wait for process exit (prevent zombies), release file descriptors
└── process_monitor_task.yml                # Background asyncio task monitors process.wait(), updates lifecycle state, handles unexpected crashes, restarts if configured
```

---

#### **Issue 2.8.3: Circuit Breaker Integration**

**Effort:** 1 day | **Source ADR:** `0034c-mcp-circuit-breaker.md`

**Expected Output:** `contracts/mcp/circuit_breaker/` (6 files)

```
├── circuit_breaker_fsm_3_states.yml        # 3-state FSM: CLOSED (normal, requests allowed) → OPEN (failing, reject immediately) → HALF_OPEN (testing recovery, allow 1 probe) → CLOSED
├── per_tool_circuit_breaker.yml            # Each tool has separate circuit breaker instance, state tracked in-memory (tool_id → CircuitBreakerState), Redis-backed for multi-instance K1 (future)
├── failure_threshold_config.yml            # Configurable per tool (default: 5 failures in 10 min), weather_api: 5 failures, calendar_api: 3 failures (internal API, more reliable)
├── timeout_cooldown_config.yml             # Configurable per tool (default: 30s cooldown), weather_api: 30s (recovers quickly), video_transcoder: 90s (needs warmup time)
├── state_transitions.yml                   # CLOSED → OPEN: failure_count ≥ threshold, OPEN → HALF_OPEN: timeout elapsed, HALF_OPEN → CLOSED: probe succeeds, HALF_OPEN → OPEN: probe fails (reset cooldown)
└── cascade_prevention_metrics.yml          # 92% cascade prevention (96 failures vs 1,200 without circuit breaker), metrics: circuit_state, failure_count, total_rejections
```

---

#### **Issue 2.8.4: Error Handling & Recovery Strategies**

**Effort:** 2 days | **Source ADR:** `0034d-mcp-error-handling.md`

**Expected Output:** `contracts/mcp/error_handling/` (9 files)

```
├── error_classification_3_categories.yml   # TRANSIENT (network timeout, 503, rate limit 429) → retry 3x, PERMANENT (400 invalid params, 404 not found, 401 unauthorized) → no retry, CRITICAL (tool crash, circuit breaker OPEN, security violation) → escalate
├── retry_strategy_exponential_backoff.yml  # Exponential backoff: delay = base_delay × 2^(retry_count-1) with jitter (random 0-500ms), max retries: 3 (total 4 executions including original)
├── fallback_tier1_retry.yml                # Tier 1: Retry same tool with exponential backoff (85% success rate for transient errors)
├── fallback_tier2_alternative_tool.yml     # Tier 2: Different tool with same capability (weather_api → weather_backup, 70% success rate)
├── fallback_tier3_cached_result.yml        # Tier 3: Return stale cached data from K0 (5-60 min old, 60% success rate)
├── fallback_tier4_graceful_degradation.yml # Tier 4: User-facing error message, suggest alternatives, continue conversation (100% graceful)
├── circuit_breaker_integration.yml         # Circuit breaker OPEN → Skip Tier 1 (retry), go directly to Tier 2+ (fallback), circuit breaker HALF_OPEN → allow 1 retry (probe)
├── user_facing_error_messages.yml          # Friendly, actionable messages: "I couldn't reach the service right now. Let me try again..." (no technical jargon)
└── error_propagation_logging.yml           # K0 logging: All errors logged with trace_id, error_code, tool_id, retry_count, developer-facing: detailed error codes and stack traces
```

**Key Contracts for Epic 2.8:**

- JSON-RPC 2.0 protocol implementation (stdio/HTTP transports)
- Process lifecycle FSM (5 states: SPAWNING/RUNNING/TERMINATING/TERMINATED/CRASHED)
- Circuit breaker resilience (3 states: CLOSED/OPEN/HALF_OPEN, 92% cascade prevention)
- Comprehensive error handling (error classification, exponential backoff, 4-tier fallback)

**Total Contracts: 30 files** (7 JSON-RPC + 8 lifecycle + 6 circuit breaker + 9 error handling)

---

## Epic 2.9: PII Detection & Redaction Contracts (ADR-0035)

**ADR Source:** ADR-0035 (PII Detection & Redaction), Sub-ADRs 0035a-d
**Timeline:** Week 7-8 (6 days, parallel with Epic 3.1)
**Dependencies:** Epic 4.1 (SessionState), Epic 4.2 (K0 Storage)

**Epic Overview:** Hybrid regex + ML-based PII detection achieving 95% recall with <5ms overhead, encrypted vault with AES-256-GCM, GDPR/HIPAA compliance with comprehensive audit trail.

### **Issues for Epic 2.9:**

#### **Issue 2.9.1: Regex Pattern Library for Structured PII**

**Effort:** 1 day | **Source ADR:** `0035a-regex-pattern-library.md`

**Expected Output:** `contracts/privacy/regex_patterns/` (6 files)

```
├── regex_pattern_registry.yml              # 12 precompiled patterns: SSN (\d{3}-\d{2}-\d{4}), email, phone, credit card, address, IP address, driver license, passport, IBAN, MAC address, health insurance, tax ID
├── pattern_validation_logic.yml            # Luhn algorithm for credit cards, SSN format validation (no 000-xx-xxxx), email RFC 5322 validation, phone E.164 international format
├── pattern_configuration_yaml.yml          # YAML config: pattern metadata (name, regex, placeholder, confidence, validator function), hot-reload support (update patterns without restart)
├── performance_optimization.yml            # Precompiled patterns at startup (lazy_static or once_cell in Rust), early exit on first match per PII type, batch processing in single pass
├── international_support_phase2.yml        # US SSN, UK NHS (\d{3}-\d{3}-\d{4}), Canadian SIN (\d{3}-\d{3}-\d{3}), EU VAT (country-specific patterns)
└── accuracy_metrics.yml                    # 85% recall for structured PII (10,200/12,000 detections), 100% precision (0 false positives with validation), <1ms overhead per pattern
```

---

#### **Issue 2.9.2: ML-based NER for Unstructured PII**

**Effort:** 2 days | **Source ADR:** `0035b-ml-based-ner.md`

**Expected Output:** `contracts/privacy/bert_ner/` (7 files)

```
├── bert_base_model.yml                     # BERT-base (110M parameters) fine-tuned on CoNLL-2003 NER dataset, BIO tagging scheme (B-PERSON, I-PERSON, B-LOCATION, etc.)
├── onnx_runtime_inference.yml              # Export BERT to ONNX format, ONNX Runtime for inference (CPU initially, GPU optional), INT8 quantization for 4× speedup (5ms → 1.25ms)
├── pii_entity_types.yml                    # PERSON (names: John Doe), LOCATION (addresses: 123 Main St), ORGANIZATION (companies: Acme Corp), extend to MISC (miscellaneous PII)
├── post_processing.yml                     # Merge adjacent tokens (B-PERSON + I-PERSON → full name), confidence filtering (threshold: 0.8), deduplication with regex results (prefer regex for structured PII)
├── fallback_strategy.yml                   # If model unavailable: fall back to regex-only (85% recall), if inference times out (>10ms): skip ML, use regex-only, emit metric: ner_fallback_total
├── cross_platform_model.yml                # BERT-NER model runs on Linux, macOS, Windows (ONNX Runtime), <100MB memory footprint (quantized model), <500ms model loading at startup
└── accuracy_metrics.yml                    # 95% recall for unstructured PII (1,800/1,900 names/addresses detected), 99% precision (<1% false positives), <5ms NER inference (avg 4.5ms with INT8)
```

---

#### **Issue 2.9.3: Encrypted PII Vault & Key Management**

**Effort:** 2 days | **Source ADR:** `0035c-encrypted-vault-key-management.md`

**Expected Output:** `contracts/privacy/vault/` (8 files)

```
├── aes_256_gcm_encryption.yml              # AES-256-GCM authenticated encryption (confidentiality + integrity), 256-bit key (32 bytes), 96-bit nonce (12 bytes, unique per encryption), 128-bit auth tag (16 bytes)
├── local_keystore_integration.yml          # Encryption key stored in OS Keychain (Windows Credential Manager/macOS Keychain/Linux Secret Service), reuses KeystoreClient from ADR-0036b, <1ms key fetch (35× faster than cloud KMS)
├── k0_vault_schema.yml                     # K0 table: pii_vault (vault_key PRIMARY KEY, encrypted_value BLOB, nonce BLOB, auth_tag BLOB, pii_type TEXT, user_id, space_id, trace_id, keystore_key_id TEXT, keystore_backend TEXT ["OS_KEYCHAIN"|"ENCRYPTED_FILE"|"LOCAL_HSM"|"CLOUD_KMS"], created_at, deleted_at)
├── vault_operations_store_retrieve_delete.yml # Store: Get key from OS Keychain (<1ms), encrypt PII, generate vault_key (UUID), insert into pii_vault, Retrieve: Fetch ciphertext, get key from keystore, decrypt, return plaintext, Delete: Soft delete (set deleted_at timestamp)
├── gdpr_compliance_right_to_erasure.yml    # Right to erasure: User can delete PII from vault (soft delete → hard delete after 30 days grace period), right to access: user can retrieve original PII from vault
├── performance_metrics.yml                 # <2ms encryption overhead (avg 1.8ms per PII value), <3ms vault operations (down from 5ms), <1ms key fetch from OS keychain (vs 35-50ms cloud KMS), 100% offline capability
├── breach_protection.yml                   # K0 database breach: SessionState stores redacted placeholders ([SSN], [EMAIL]), vault stores encrypted ciphertext (0xABCD...), decryption key in OS Keychain (hardware-backed TPM/Secure Enclave), attacker cannot decrypt without user password/biometric unlock
└── audit_trail_integration.yml             # All vault operations logged to K0 audit_log table (operation, vault_key, user_id, timestamp, success/error), integration with Prometheus (vault_operations_total metric), local audit (no CloudTrail dependency)
```

---

#### **Issue 2.9.4: Audit Trail & GDPR/HIPAA Compliance**

**Effort:** 1 day | **Source ADR:** `0035d-audit-trail-gdpr-compliance.md`

**Expected Output:** `contracts/privacy/audit/` (9 files)

```
├── audit_log_schema.yml                    # K0 table: audit_log (id AUTOINCREMENT, operation TEXT, pii_type TEXT, user_id, space_id, trace_id, timestamp, vault_key, original_value_hash SHA-256, redacted_placeholder, detection_method, confidence)
├── gdpr_requests_schema.yml                # K0 table: gdpr_requests (id AUTOINCREMENT, request_type TEXT ["access"|"erasure"|"portability"], user_id, space_id, requested_at, fulfilled_at, status ["pending"|"fulfilled"|"rejected"], response_data JSON)
├── gdpr_right_to_access.yml                # User requests data export, K1 queries audit_log for all PII operations, retrieves encrypted PII from vault, generates JSON data export, user receives within 30 days
├── gdpr_right_to_erasure.yml               # User requests data deletion, K1 soft deletes PII from vault (set deleted_at), hard delete after 30 days grace period, user notified within 30 days
├── gdpr_data_portability.yml               # User requests data export in machine-readable format, K1 generates JSON with all PII values (SSN, email, phone), structured format (GDPR Article 20)
├── hipaa_audit_controls.yml                # 164.308(a)(1)(ii)(D): Log all PHI access (who, what, when), 164.312(b): Audit trail (user_id, operation, timestamp), 164.528(a): Accounting of disclosures (user can request access log)
├── compliance_metrics.yml                  # Redaction count (total PII redacted), vault operations (store/retrieve/delete), GDPR requests (access/erasure), compliance rate (% requests fulfilled within 30 days)
├── anomaly_detection.yml                   # Detect unusual PII access (same user accessing 100+ PII values), detect privilege escalation (non-admin accessing admin operations), alert on suspicious patterns
└── retention_policies.yml                  # Audit log retention: 90 days (GDPR), 7 years (HIPAA), soft delete grace period: 30 days, automatic cleanup after retention period
```

**Key Contracts for Epic 2.9:**

- Regex pattern library (12 patterns, 85% recall, <1ms, 100% precision)
- ML-based NER (BERT-base, 95% recall, <5ms, 99% precision)
- Encrypted vault (AES-256-GCM, OS Keychain local-first, GDPR right to erasure)
- Comprehensive audit trail (GDPR/HIPAA compliance, right to access/erasure)

**Architecture Notes:**

- **Local-First:** Encryption keys stored in OS Keychain (Windows Credential Manager, macOS Keychain, Linux Secret Service)
- **Hardware-Backed:** TPM/Secure Enclave protection, biometric unlock (Touch ID/Face ID/Windows Hello)
- **Performance:** <1ms key fetch (35-50× faster than cloud KMS), <3ms vault operations (48-53% faster)
- **Offline Capability:** 100% local operation, zero internet dependency
- **Cloud Optional:** Cloud KMS available for enterprise deployments only (not required)

**Total Contracts: 30 files** (6 regex + 7 NER + 8 vault + 9 audit)

---

## Epic 2.10: E2EE for RED Band Contracts

**Source ADR:** ADR-0036 (E2EE for RED Band) + sub-ADRs (0036a-d)
**Priority:** CRITICAL (Security & Privacy)
**Contract Count:** 32 files

**Context:** ADR-0036 requires end-to-end encryption for RED band SessionState with AES-256-GCM, user-controlled keys in HSM/KMS, selective encryption (beliefs/scoreboard/control sections only), <1ms encryption overhead, and BYOK support for zero-knowledge architecture.

#### Issue 2.10.1: AES-256-GCM Encryption Contracts

**Expected Output:** `contracts/security/e2ee/aes256gcm/` (8 files)

```
├── encryption_key.yml                      # EncryptionKey class (256-bit key, AES-NI cipher, AtomicU64 nonce counter, created_at, rotated_at)
├── encrypt_operation.yml                   # Encrypt method: Generate unique nonce (atomic counter increment) → AES-256-GCM encrypt → Split ciphertext + 16-byte auth tag → <1ms validation
├── decrypt_operation.yml                   # Decrypt method: Verify key_id matches → Load nonce from encrypted data → AES-256-GCM decrypt → Verify authentication tag → Return plaintext or abort
├── nonce_management.yml                    # Counter-based nonce: 96-bit (12 bytes), AtomicU64 counter (never repeats), 2^96 capacity per key, force key rotation before exhaustion
├── authentication_tag.yml                  # 128-bit GMAC tag: Computed over ciphertext, prevents tampering, tag verification MUST succeed before decryption, tag failure → abort + log security event
├── hardware_acceleration.yml               # AES-NI instruction usage: 5-10× faster than software, constant-time execution (prevents timing attacks), fallback to software if AES-NI unavailable
├── performance_validation.yml              # <1ms budget enforcement: Measure encrypt/decrypt latency, emit encrypt_latency_ms metric, alert if P95 >1ms
└── error_handling.yml                      # Encryption failures → Log error + return plaintext (graceful degradation), Decryption failures → Abort + return cached/empty SessionState, Nonce exhaustion → Force key rotation immediately
```

**ADR References:** ADR-0036a lines 1-251 (AES-256-GCM), 252-500 (nonce), 501-750 (hardware accel)

---

#### Issue 2.10.2: Keystore Integration & Key Lifecycle Contracts

**Expected Output:** `contracts/security/e2ee/keystore/` (10 files)

```
├── keystore_client_interface.yml           # KeystoreClient trait (reused from ADR-0036b): generate_key(space_id, user_id), get_key(key_id), rotate_key(key_id), revoke_key(key_id), schedule_key_deletion(key_id, pending_days), needs_rotation(key_id)
├── os_keychain_client.yml                  # OS Keychain implementation: Windows Credential Manager (DPAPI + TPM), macOS Keychain (Secure Enclave + T2/M1), Linux Secret Service (GNOME Keyring/KWallet), <1ms key fetch, biometric unlock support
├── encrypted_file_client.yml               # Encrypted File fallback: Password-protected SQLite with Argon2 KDF (100ms derivation), AES-256-GCM encrypted keys, user password/PIN required, <5ms key fetch
├── local_hsm_client.yml                    # Local HSM support (optional): YubiHSM, Nitrokey via PKCS#11, hardware-backed key generation, <10ms key operations, supports key rotation + deletion
├── key_metadata.yml                        # KeyMetadata: key_id (UUID), space_id, user_id, created_at, rotated_at, expires_at (90 days from created/rotated), keystore_backend (OS_KEYCHAIN/ENCRYPTED_FILE/LOCAL_HSM/CLOUD_KMS), is_byok
├── key_generation.yml                      # Generate 256-bit encryption key: Call KeystoreClient.generate_key (AES-256) → Store KeyMetadata in K0 (space_id → key_id mapping) → <1ms latency (OS Keychain), <5ms (Encrypted File)
├── key_rotation.yml                        # Automatic 90-day rotation: Check expires_at daily → Generate new key version → Update key_id references → Old key retained 180 days → <1ms latency
├── key_revocation.yml                      # Immediate revocation: User requests key disable → Delete key from keystore → Blacklist key_id in K0 → Prevent future encryption/decryption
├── byok_import.yml                         # BYOK workflow: User generates 256-bit key → User imports to keystore (store in OS Keychain or Encrypted File) → K1 stores key_id reference → User controls lifecycle (rotate, revoke)
└── key_caching.yml                         # Key caching strategy: Cache keys in memory (session duration, 1-hour max TTL) → Invalidate on rotation → Already fast (<1ms OS Keychain, <5ms Encrypted File), cache reduces concurrent access contention
```

**ADR References:** ADR-0036b lines 1-251 (Keystore hierarchy), 252-500 (lifecycle), 501-750 (BYOK), 751-1000 (multi-provider)

**Note:** This issue reuses KeystoreClient from ADR-0036b (unified key management). Cloud KMS available as optional enterprise backend via keystore_backend enum.

---

#### Issue 2.10.3: Selective Encryption & SessionState Integration Contracts

**Expected Output:** `contracts/security/e2ee/selective/` (8 files)

```
├── e2ee_manager.yml                        # E2EEManager class: check privacy band (RED → encrypt, GREEN/AMBER/BLACK → skip), get key from KeystoreClient (cached, <1ms), create SessionStateEncryptor, encrypt 3 sections in parallel
├── band_detection.yml                      # Privacy band detection: Extract from SessionState.meta.privacy_band → enabled_bands = [RED] → Skip if not in enabled_bands (0ms overhead for GREEN/AMBER)
├── section_selection.yml                   # Section-level selection: encrypted_sections = ["beliefs", "scoreboard", "control"], plaintext_sections = ["persona", "meta"], multimodal handled separately
├── parallel_encryption.yml                 # Parallel encryption with tokio tasks: Encrypt 3 sections concurrently → tokio::spawn for each section → Join all futures → <3ms total (1ms per section × 3 parallel)
├── sessionstate_encryptor.yml              # SessionStateEncryptor: Serialize section to JSON → Encrypt JSON bytes with AES-256-GCM → Store EncryptedData (ciphertext, nonce, auth_tag, key_id)
├── sessionstate_decryptor.yml              # SessionStateDecryptor: Load EncryptedData from K0 → Decrypt ciphertext → Deserialize JSON → Populate SessionState section
├── graceful_degradation.yml                # Encryption failure fallback: Log error → Save plaintext SessionState with RED_ENCRYPTION_FAILED flag → Alert metrics → Continue turn (don't block)
└── performance_monitoring.yml              # Track encryption overhead per band: RED avg 0.8ms, GREEN/AMBER 0ms → Alert if RED >1ms P95 → Cache hit rate for keys >90% (OS Keychain fast access)
```

**ADR References:** ADR-0036c lines 1-251 (selective), 252-500 (integration), 501-750 (async), 751-1000 (performance)

---

#### Issue 2.10.4: Audit Trail & Compliance Contracts

**Expected Output:** `contracts/security/e2ee/audit/` (6 files)

```
├── e2ee_audit_logger.yml                   # E2EEAuditLogger class: log_operation(operation, timestamp, space_id, user_id, key_id, band, trace_id, success, error_message) → INSERT to K0 e2ee_audit_log table, <5ms async
├── audit_log_schema.yml                    # E2EEAuditLog schema: operation (Encrypt/Decrypt/KeyGenerate/KeyRotate/KeyRevoke/KeyDelete/KeyImport/KeyExport), timestamp, space_id, user_id, key_id, band, trace_id, success (bool), error_message (optional)
├── operation_types.yml                     # E2EEOperation enum: Encrypt (SessionState encryption), Decrypt (SessionState decryption), KeyGenerate (new space key), KeyRotate (90-day rotation), KeyRevoke (user revoke), KeyDelete (retention), KeyImport (BYOK), KeyExport (BYOK)
├── gdpr_compliance.yml                     # GDPR Article 15 (right to access): Query e2ee_audit_log by user_id → Export JSON, Article 17 (right to erasure): Delete encryption keys on account deletion, Article 30 (processing records): E2EEAuditLog = record of processing
├── hipaa_compliance.yml                    # HIPAA §164.312(a)(1) (access control): Log who accessed encrypted PHI, §164.312(b) (audit controls): E2EEAuditLog = audit trail, §164.312(e)(2)(ii) (encryption): Log all PHI encryption operations
└── byok_documentation.yml                  # User guide: How to generate 256-bit key (openssl rand -hex 32), import to KMS (aws kms import-key-material), export keys (aws kms get-parameters-for-import), rotate BYOK keys (generate + import new version)
```

**ADR References:** ADR-0036d lines 1-251 (audit), 252-500 (GDPR), 501-750 (HIPAA), 751-1000 (BYOK docs)

**Total Contracts: 32 files** (8 AES + 10 Keystore + 8 selective + 6 audit)

**Key Contracts:**

- **`encryption_key.yml`** — 256-bit AES key with AES-NI hardware acceleration
- **`os_keychain_client.yml`** — OS Keychain (Windows/macOS/Linux) with TPM/Secure Enclave, <1ms key fetch
- **`e2ee_manager.yml`** — Selective encryption for RED band SessionState (beliefs/scoreboard/control sections), <1ms overhead
- **`e2ee_audit_logger.yml`** — GDPR/HIPAA-compliant audit trail with local logging

**Architecture Notes:**

- **Local-First:** Keys stored in OS Keychain (Windows Credential Manager/macOS Keychain/Linux Secret Service), hardware-backed TPM/Secure Enclave, biometric unlock support
- **Performance:** <1ms key fetch (vs 35-50ms cloud KMS), <3ms selective encryption for RED band, 100% offline capability
- **Security:** AES-256-GCM with 128-bit authentication tag, constant-time execution with AES-NI, key rotation every 90 days
- **Privacy:** Zero-knowledge architecture with BYOK support, selective encryption (only RED band), GDPR/HIPAA-compliant audit trail
- **Cloud Optional:** Cloud KMS available as optional enterprise backend via keystore_backend enum (not required for local-first operation)

---

## Epic 2.11: JWT Authentication Contracts

**Source ADR:** ADR-0037 (JWT Authentication) + sub-ADRs (0037a-d)
**Priority:** CRITICAL (Security & Privacy)
**Contract Count:** 30 files

**Context:** ADR-0037 requires JWT-based authentication with RS256 signing, 1-hour access tokens, 7-day refresh tokens, stateless validation (<2ms), fine-grained claims (roles, privacy_band, space_id, capabilities), refresh token rotation, and comprehensive authorization.

#### Issue 2.11.1: Token Generation & Signing Contracts

**Expected Output:** `contracts/security/jwt/generation/` (8 files)

```
├── auth_service.yml                        # AuthService class: issue_tokens(user_id, space_id, roles, privacy_band, capabilities) → Issue access + refresh tokens, RS256 sign with private key (2048-bit RSA), <50ms
├── claims_structure.yml                    # Claims struct: Standard (sub, iat, exp, iss, aud, jti), Custom (space_id, roles: Vec<String>, privacy_band: String, capabilities: Vec<String>), no PII in claims
├── access_token_issuance.yml               # Issue 1-hour access token: Create Claims (exp = now + 1h) → Sign with RSA private key (RS256) → Return JWT string (header.payload.signature), <50ms
├── refresh_token_issuance.yml              # Issue 7-day refresh token: Minimal claims (sub, exp = now + 7d, jti, token_type = "refresh") → Sign with RSA private key → Store in Redis (refresh:<jti> → user_id, 7-day TTL)
├── token_pair_response.yml                 # TokenPair struct: access_token (JWT string), refresh_token (JWT string), expires_in (3600 seconds), token_type ("Bearer")
├── rs256_signing.yml                       # RS256 signing: RSA 2048-bit private key (PEM format) → SHA-256 hash → JWT header (alg=RS256, typ=JWT, kid=key_id) → Base64URL encode
├── private_key_security.yml                # Private key stored in OS Keychain (Windows Credential Manager/macOS Keychain/Linux Secret Service) or Local HSM (YubiHSM/Nitrokey): Never exposed to K1 memory → Sign operation uses secure keystore → 90-day key rotation
└── observability.yml                       # Prometheus metrics: token_issuance_total (counter), signing_latency_ms (histogram), token_type label (access/refresh)
```

**ADR References:** ADR-0037a lines 1-251 (generation), 252-500 (RS256), 501-750 (claims), 751-1000 (Keystore)

---

#### Issue 2.11.2: Token Validation & Verification Contracts

**Expected Output:** `contracts/security/jwt/validation/` (8 files)

```
├── jwt_validator.yml                       # JWTValidator class: validate_token(token, trace_id) → Decode header → Verify RS256 signature → Check expiry → Extract claims → Check blacklist → <2ms total
├── signature_verification.yml              # RS256 signature verification: Verify with RSA public key (2048-bit, PEM format) → Fail fast if invalid signature → <1ms latency
├── expiry_check.yml                        # Expiry validation: Compare exp claim with current Unix timestamp → 5-minute clock skew tolerance (exp < now - 300 = expired) → Reject expired tokens
├── claims_extraction.yml                   # Parse payload: Base64URL decode payload → Deserialize JSON → Extract Claims struct → Validate required fields (sub, exp, iss, aud)
├── blacklist_check.yml                     # Query Redis for revoked tokens: GET blacklist:<jti> → Cache results (1-minute TTL) → <1ms lookup → Alert on revoked token usage attempt
├── validation_errors.yml                   # JWTValidationError enum: Expired, InvalidSignature, InvalidIssuer, InvalidAudience, Revoked, InvalidToken, InvalidFormat, InvalidAlgorithm
├── public_key_distribution.yml             # Distribute RSA public key: Load from OS Keychain on startup → Cache in memory (all API Gateway instances) → No keystore call per request → Public key refresh on rotation
└── observability.yml                       # Prometheus metrics: validations_total (counter), validation_latency_ms (histogram), blacklist_hit_rate (gauge), failure_reasons (counter by reason)
```

**ADR References:** ADR-0037b lines 1-251 (validation), 252-500 (signature), 501-750 (blacklist), 751-1000 (performance)

---

#### Issue 2.11.3: Refresh Token Flow & Rotation Contracts

**Expected Output:** `contracts/security/jwt/refresh/` (7 files)

```
├── refresh_token_store.yml                 # RefreshTokenStore class: store(jti, user_id, ttl_seconds) → Redis SET refresh:<jti> → user_id (7-day TTL), consume(jti) → Redis GET_DEL (atomic, single-use)
├── refresh_endpoint.yml                    # POST /auth/refresh: Parse refresh_token from body → Validate refresh token (signature + expiry + exists in Redis) → Issue new token pair → Delete old refresh token → <100ms
├── single_use_rotation.yml                 # Consume refresh token: Redis GET_DEL refresh:<jti> (atomic) → If exists: Issue new access + refresh tokens → Delete old refresh token → Store new refresh token
├── reuse_detection.yml                     # Detect refresh token reuse: consume() returns None (token already used) → Security alert → Revoke all refresh tokens for user (revoke_all_for_user) → Force re-login
├── token_family_revocation.yml             # Revoke token family: Query token_family_map (user_id → [jti1, jti2, ...]) → DELETE all refresh tokens from Redis → Clear family map → User must re-login
├── logout_flow.yml                         # DELETE /auth/logout: Parse refresh_token from body → Delete refresh token from Redis (DEL refresh:<jti>) → Optionally blacklist access token (blacklist:<jti> → TTL = token expiry)
└── rate_limiting.yml                       # Rate limit refresh endpoint: 10 refresh requests/minute per user → Redis counter (refresh_rate:<user_id>, 60s TTL) → 429 Too Many Requests if exceeded
```

**ADR References:** ADR-0037c lines 1-251 (refresh), 252-500 (rotation), 501-750 (reuse), 751-1000 (security)

---

#### Issue 2.11.4: Session Binding & Authorization Contracts

**Expected Output:** `contracts/security/jwt/authorization/` (7 files)

```
├── session_jwt_binder.yml                  # SessionStateJWTBinder: bind_claims_to_session(session, claims, trace_id) → session.meta.user_id = claims.sub, session.meta.space_id = claims.space_id, session.meta.roles/privacy_band/capabilities
├── space_isolation.yml                     # Space isolation middleware: Extract space_id from request path/query → Compare with session.meta.space_id → 403 Forbidden if mismatch (cross-space access denied)
├── rbac_decorators.yml                     # Role-based access control: @require_role("admin") decorator → Check claims.roles contains "admin" → 403 if missing, @require_role("operator") for operator endpoints
├── privacy_band_enforcement.yml            # Privacy band hierarchy: RED > AMBER > GREEN → Check user_band >= data_band (e.g., AMBER user can access GREEN data, not RED) → 403 if insufficient band
├── capability_validation.yml               # Capability-based authorization: @require_capability("TOOL_CALL") decorator → Check claims.capabilities contains "TOOL_CALL" → 403 if missing
├── authorization_middleware.yml            # Authorization middleware: Run before all API endpoints → Extract JWT from Authorization header → Validate JWT → Bind claims to session → Check space/role/band/capability → <1ms
└── audit_logging.yml                       # Log authorization denials: space_mismatch (user_id, requested_space, session_space), role_denied (user_id, required_role, user_roles), capability_denied (user_id, required_capability)
```

**ADR References:** ADR-0037d lines 1-251 (binding), 252-500 (space), 501-750 (RBAC), 751-1000 (capability)

**Total Contracts: 30 files** (8 generation + 8 validation + 7 refresh + 7 authorization)

---

## Epic 2.12: Audit Trail & K0 Receipts Contracts

**Source ADR:** ADR-0038 (Audit Trail to K0 Receipts) + sub-ADRs (0038a-d)
**Priority:** CRITICAL (Security & Privacy)
**Contract Count:** 30 files

**Context:** ADR-0038 requires immutable audit trail with K0 receipts for GDPR/HIPAA/SOC2 compliance. Receipts logged to Write-Ahead Log (WAL) with SHA-256 hash chaining, 4 receipt types, band-specific retention, automatic deletion, query interface, and compliance export.

#### Issue 2.12.1: Receipt Generation & Schema Contracts

**Expected Output:** `contracts/observability/receipts/schema/` (8 files)

```
├── turn_receipt.fbs                        # TurnReceipt FlatBuffers: receipt_id, session_id, space_id, user_id, turn_number, user_message (redacted), agent_response (redacted), privacy_band, latency_ms, intent, trace_id, timestamp, previous_receipt_hash, current_hash
├── tool_receipt.fbs                        # ToolReceipt FlatBuffers: receipt_id, session_id, space_id, user_id, turn_number, tool_name, tool_arguments (redacted), tool_result (redacted), success, error, violation_type (from ADR-0032), privacy_band, latency_ms, trace_id, timestamp, hash chain
├── state_receipt.fbs                       # StateReceipt FlatBuffers: receipt_id, session_id, space_id, user_id, section (beliefs/scoreboard/control), delta (JSON string), previous_state_hash (SHA-256 of previous SessionState), new_state_hash, privacy_band, trace_id, timestamp, hash chain
├── agent_receipt.fbs                       # AgentReceipt FlatBuffers: receipt_id, session_id, space_id, user_id, agent_id, operation (hire/fire/suspend/resume), capabilities (Vec<String>), from_state, to_state, privacy_band, trace_id, timestamp, hash chain
├── hash_chain_computation.yml              # SHA-256 hash chain: current_hash = SHA-256(receipt_id + timestamp + data + previous_receipt_hash) → <0.5ms → First receipt: previous_hash = "0" × 64 (genesis)
├── pii_redaction.yml                       # PII redaction rules: email → [REDACTED:EMAIL], SSN → [REDACTED:SSN], phone → [REDACTED:PHONE], credit card → [REDACTED:CC], apply before receipt creation
├── receipt_generator.yml                   # ReceiptGenerator class: create_receipt(type, data) → Redact PII → Compute hash → Serialize with FlatBuffers → Return Receipt struct → <1ms total
└── observability.yml                       # Prometheus metrics: receipts_created_total (counter by type), receipt_creation_latency_ms (histogram), receipts_by_type (gauge), hash_chain_breaks_detected (counter)
```

**ADR References:** ADR-0038a lines 1-251 (receipt types), 252-500 (hash chain), 501-750 (FlatBuffers), 751-1000 (PII redaction)

---

#### Issue 2.12.2: K0 WAL Integration & Async Writes Contracts

**Expected Output:** `contracts/observability/receipts/wal/` (8 files)

```
├── k0_receipts_table.sql                   # receipts table: receipt_id TEXT PK, session_id TEXT, space_id TEXT, user_id TEXT, receipt_type TEXT (TURN/TOOL/STATE/AGENT), privacy_band TEXT, payload BLOB (FlatBuffers), timestamp INTEGER, previous_hash TEXT, current_hash TEXT, indexes on session_id/timestamp/privacy_band
├── receipt_writer.yml                      # ReceiptWriter class: Async queue (mpsc::channel, 10,000 capacity) → Batch writer task (100 receipts or 100ms) → WAL write (append-only, single fsync per batch) → <5ms async
├── async_receipt_queue.yml                 # mpsc::channel: Multi-producer (all K1 components) → Single consumer (batch writer task) → 10,000 receipt capacity → Backpressure on full (block new receipts)
├── batch_writer_task.yml                   # Background task: Collect receipts (max 100 or 100ms timeout, whichever first) → Batch INSERT to K0 receipts table → Single fsync → 98% batch efficiency (avg 95 receipts/batch)
├── wal_configuration.yml                   # K0 WAL mode: PRAGMA journal_mode=WAL (append-only writes), PRAGMA synchronous=NORMAL (durability + performance balance), sequential writes (5000+ writes/sec)
├── backpressure_handling.yml               # Queue full handling: Emit receipt_queue_full_total alert → Block new receipts (backpressure to callers) → Drop oldest receipts if critical (configurable)
├── crash_recovery.yml                      # WAL replay on K1 startup: Read WAL entries → Reconstruct hash chain → Verify integrity (detect missing receipts) → Resume normal operation
└── observability.yml                       # Prometheus metrics: receipts_written_total (counter), receipt_write_latency_ms (histogram), queue_depth (gauge), batch_sizes (histogram), backpressure_events_total (counter)
```

**ADR References:** ADR-0038b lines 1-251 (K0 WAL), 252-500 (async), 501-750 (batch), 751-982 (crash recovery)

---

#### Issue 2.12.3: Retention Policies & Auto-Deletion Contracts

**Expected Output:** `contracts/observability/receipts/retention/` (7 files)

```
├── retention_config.yml                    # Band-specific retention: GREEN 365 days, AMBER 180 days, RED 90 days, grace period 7 days (buffer before deletion), pruning schedule: hourly (cron "0 * * * *")
├── retention_manager.yml                   # RetentionManager class: Load retention policies → Schedule hourly pruning job → DELETE receipts WHERE timestamp < cutoff (band-specific) → <5s pruning latency
├── pruning_job.yml                         # Cron-style hourly job: Calculate cutoff (now - retention_days - grace_period_days) → Batch DELETE (1000 receipts/batch) → Log deletion events → VACUUM after deletion
├── deletion_log_schema.sql                 # deletion_log table: deletion_id TEXT PK, session_id TEXT, privacy_band TEXT, receipt_count INTEGER, deletion_timestamp INTEGER, retention_cutoff INTEGER, job_id TEXT
├── deletion_audit_trail.yml                # Log every deletion: INSERT to deletion_log table → session_id, band, receipt_count, timestamp → Compliance verification (prove GDPR right to erasure)
├── storage_optimization.yml                # VACUUM after deletion: Reclaim disk space (80% storage reduction) → Rebuild indexes (maintain query performance) → Monitor storage savings_bytes
└── observability.yml                       # Prometheus metrics: receipts_pruned_total (counter by band), pruning_latency_ms (histogram), storage_savings_bytes (gauge), deletion_jobs_total (counter)
```

**ADR References:** ADR-0038c lines 1-251 (retention), 252-500 (auto-deletion), 501-750 (deletion audit), 751-905 (storage optimization)

---

#### Issue 2.12.4: Query Interface & Compliance Export Contracts

**Expected Output:** `contracts/observability/receipts/query/` (7 files)

```
├── receipt_query_api.yml                   # Query API endpoints: GET /api/receipts/session/{session_id} (returns all receipts for session, <50ms), GET /api/receipts/user/{user_id} (all sessions, <500ms), filter by receipt_type/start_date/end_date
├── query_params.yml                        # ReceiptQueryParams struct: receipt_type (optional, TURN/TOOL/STATE/AGENT), start_date (optional, Unix timestamp), end_date (optional, Unix timestamp)
├── hash_chain_verification.yml             # Verify hash chain on every query: Iterate receipts → Verify previous_hash → current_hash continuity → Return verification_status (VERIFIED/HASH_CHAIN_BROKEN) → <10ms for 100 receipts
├── receipt_cache.yml                       # LRU cache: Cache session receipts (10-minute TTL) → 1000 sessions max → >75% cache hit rate → <50ms cached queries → Evict LRU on capacity
├── compliance_reporter.yml                 # ComplianceReporter class for GDPR Article 15: Query all user receipts → Export JSON with metadata (user_id, export_date, receipt_counts) → Redact PII → Return export file
├── gdpr_export.yml                         # User audit log export: Query receipts by user_id → Export JSON format → Include metadata (export_date, receipt_types, total_count) → PII already redacted (from receipt generation)
└── observability.yml                       # Prometheus metrics: receipts_queried_total (counter), query_latency_ms (histogram), cache_hit_rate (gauge), hash_chain_verifications_total (counter), hash_chain_breaks_detected (counter)
```

**ADR References:** ADR-0038d lines 1-251 (query), 252-500 (cache), 501-750 (compliance), 751-1038 (GDPR/HIPAA reports)

**Total Contracts: 30 files** (8 schema + 8 WAL + 7 retention + 7 query)

---

## Epic 2.13: Backpressure Cascade 3-Tier Contracts

**Source ADR:** ADR-0039 (Backpressure Cascade) + sub-ADRs (0039a-c)
**Priority:** CRITICAL (Reliability & Performance)
**Contract Count:** 28 files

**Context:** ADR-0039 requires 3-tier backpressure cascade for system overload protection with graduated responses (Tier 1: reject new turns at 50 queue depth, Tier 2: cancel background tasks at 100 queue depth, Tier 3: emergency throttle at 200 queue depth), watermark thresholds with 10% hysteresis (prevents oscillation), <50ms signal propagation to all components via Actor Model message passing, and gradual recovery with rate-limited admission (10% every 5s) to prevent thundering herd.

### Issue 2.13.1: Watermark Thresholds & Tier Triggers Contracts

**Expected Output:** `contracts/infrastructure/backpressure/watermarks/` (8 files)

```
├── watermark_config.yml                    # Tier thresholds: Tier 1 (queue 50, latency 2500ms, active 80), Tier 2 (queue 100, memory 450MB, CPU 85%), Tier 3 (queue 200, memory 480MB, thermal CRITICAL), 10% hysteresis
├── backpressure_tier_enum.yml              # BackpressureTier enum: NORMAL (0), TIER_1_REJECT_NEW (1), TIER_2_CANCEL_BG (2), TIER_3_EMERGENCY (3), severity property
├── watermark_manager.yml                   # WatermarkManager class: Evaluate metrics every 1s, detect tier transitions, emit BackpressureSignal, track sustained duration (5-30s depending on tier)
├── tier_1_triggers.yml                     # Tier 1 activation: queue >50 (5s), E2E >2500ms (10s), active turns >80, deactivation: queue <45, E2E <2250ms, active <72 (10% hysteresis)
├── tier_2_triggers.yml                     # Tier 2 activation: queue >100 (5s), memory >450MB, CPU >85% (10s), deactivation: queue <90, memory <405MB, CPU <77% (10% hysteresis)
├── tier_3_triggers.yml                     # Tier 3 activation: queue >200 (3s), memory >480MB, thermal CRITICAL (3), OOM event, deactivation: queue <180, memory <432MB, thermal WARM (30s sustained)
├── hysteresis_mechanism.yml                # Hysteresis implementation: 10% gap between activation/deactivation (prevents rapid on/off cycling), 5-turn buffer for queue, 50MB buffer for memory
└── observability.yml                       # Prometheus metrics: backpressure_tier_gauge, watermark_breaches_total, tier_transitions_total, hysteresis_gap_ms (time in hysteresis zone)
```

**ADR References:** ADR-0039a lines 1-251 (watermarks), 252-500 (tiers), 501-750 (hysteresis), 751-956 (observability)

---

### Issue 2.13.2: Signal Propagation & Component Response Contracts

**Expected Output:** `contracts/infrastructure/backpressure/propagation/` (7 files)

```
├── backpressure_signal.yml                 # BackpressureSignal struct: tier, timestamp, reason, trace_id, priority property, __lt__ method for priority queue
├── backpressure_coordinator.yml            # BackpressureCoordinator class: Event bus for signal broadcast, register_callback method, broadcast method (<50ms propagation), track current_signal
├── component_registration.yml              # Component registration: API Gateway, Orchestrator, Agent Fabric, Tool Runner register callbacks, BackpressureCallback type definition
├── api_gateway_response.yml                # API Gateway handler: on_backpressure_signal callback, check_admission method (Tier 1: 503 Service Unavailable, Tier 2: reject background, Tier 3: reject all)
├── orchestrator_response.yml               # Orchestrator handler: Tier 1 (continue active), Tier 2 (cancel non-interactive tasks), Tier 3 (throttle all scheduling, cancel pending)
├── agent_fabric_response.yml               # Agent Fabric handler: Tier 1 (no change), Tier 2 (drain idle agents, reject background hiring), Tier 3 (drain all, force GC, evict caches)
└── observability.yml                       # Prometheus metrics: propagation_latency_ms (histogram, <50ms target), component_responses_total (counter by component), signal_broadcast_total (counter)
```

**ADR References:** ADR-0039b lines 1-251 (signal), 252-500 (propagation), 501-750 (components), 751-835 (observability)

---

### Issue 2.13.3: Recovery & Gradual Resume Contracts

**Expected Output:** `contracts/infrastructure/backpressure/recovery/` (7 files)

```
├── recovery_state_machine.yml              # Recovery FSM: Tier 3 → Tier 2 (30s sustained) → Tier 1 (10s sustained) → Normal (10s sustained), automatic rollback on health check failure
├── recovery_manager.yml                    # RecoveryManager class: start_recovery method, _recovery_loop background task, admission_rate_percent (10% → 100%), rate_increase_interval (5s)
├── rate_limiting.yml                       # Gradual admission: Start at 10% capacity, increase 10% every 5s, track admission_rate_percent, prevent thundering herd
├── health_checks.yml                       # Health check validation: Verify queue depth not growing, E2E latency stable/improving, memory not increasing, no error spike, <5s validation window
├── automatic_rollback.yml                  # Rollback trigger: If health check fails during recovery → re-escalate to previous tier, emit recovery_rollback_total metric, log rollback reason
├── recovery_time_budgets.yml               # Target recovery times: Tier 3 → Tier 2 (60s), Tier 2 → Tier 1 (30s), Tier 1 → Normal (30s), total emergency → normal (~2 minutes)
└── observability.yml                       # Prometheus metrics: recovery_duration_seconds (histogram by tier), admission_rate_gauge (0-100%), health_checks_passed_total, rollbacks_total
```

**ADR References:** ADR-0039c lines 1-251 (recovery FSM), 252-500 (gradual resume), 501-750 (health checks), 751-801 (observability)

---

### Issue 2.13.4: Privacy Band Retention Override Contracts

**Expected Output:** `contracts/privacy/retention_overrides/` (6 files)

```
├── retention_policy_config.yml             # Band-specific retention: GREEN (30d warm/365d cold = 395d total), AMBER (same), RED (7d warm/90d cold = 97d total), BLACK (7d/90d = 97d total), 75% faster deletion for RED
├── lifecycle_manager.yml                   # LifecycleManager class: Daily cron job checks retention policies, moves warm → cold after threshold, hard deletes cold after threshold, 100% automation
├── hard_deletion.yml                       # Hard delete process: Delete SessionState from K0 (not soft delete), destroy encryption keys (ADR-0036), retain audit logs (GDPR requirement), data unrecoverable
├── user_control_api.yml                    # User sovereignty API: POST /v1/sessions/{id}/delete (immediate deletion), POST /v1/sessions/{id}/retention (opt-in to extended 30d/365d), GET /v1/sessions/{id}/retention (view status)
├── gdpr_compliance.yml                     # GDPR mapping: Article 5(1)(c) data minimization (7d warm satisfies "limited to necessary"), Article 17 right to erasure (user-triggered deletion), Article 5(1)(e) storage limitation (automated lifecycle)
└── observability.yml                       # Prometheus metrics: retention_policy_applied_total (counter by band), sessions_hard_deleted_total (counter by band), deletion_latency_ms (histogram), gdpr_deletion_requests_total
```

**ADR References:** ADR-0039 lines 1-251 (retention overrides), 252-500 (lifecycle), 501-750 (hard deletion), 751-1000 (GDPR), 1001-1503 (user control)

**Total Contracts: 28 files** (8 watermarks + 7 propagation + 7 recovery + 6 retention overrides)

---

## Epic 2.14: WebSocket Real-Time Chat Contracts

**Source ADR:** ADR-0040 (WebSocket Chat) + sub-ADRs (0040a-d)
**Priority:** CRITICAL (Communication & Real-Time)
**Contract Count:** 30 files

**Context:** ADR-0040 requires WebSocket (RFC 6455) for real-time chat with full-duplex bidirectional communication, <200ms TTFT (time to first token) streaming, FlatBuffers binary protocol (2× smaller than JSON, ADR-0011), JWT authentication in handshake (ADR-0037), auto-reconnect with exponential backoff (1s, 2s, 4s, 8s, 16s max), and 17 message types across 6 categories (Connection, Conversation, User, Agent, Tool, Clarification, Error).

#### Issue 2.14.1: Connection Management & Authentication Contracts

**Expected Output:** `contracts/api/websocket/connection/` (8 files)

```
├── websocket_upgrade_handshake.yml         # HTTP → WebSocket upgrade: Client sends GET with Upgrade: websocket header, server validates Sec-WebSocket-Key, responds with 101 Switching Protocols, <500ms establishment
├── jwt_authentication.yml                  # JWT in query param: ?token=<jwt>, validate signature (RS256 from ADR-0037), extract claims (user_id, session_id, space_id), reject if invalid (403 Forbidden), <50ms validation
├── connection_registry.yml                 # ConnectionRegistry: Arc<RwLock<HashMap<session_id, WebSocketConnection>>>, register/get/remove methods, track session_id, user_id, tx channel, last_heartbeat
├── websocket_connection.yml                # WebSocketConnection struct: session_id, user_id, space_id, tx (mpsc::Sender), last_heartbeat, connected_at, methods for send/close
├── tls_encryption.yml                      # TLS 1.3 (wss://): SSL certificate (Let's Encrypt), cipher suite TLS_AES_256_GCM_SHA384, <200ms TLS handshake, prevents man-in-the-middle attacks
├── graceful_disconnect.yml                 # RFC 6455 close codes: 1000 (normal), 1008 (policy violation), 1011 (server error), send Goodbye message before close, cleanup from connection registry
├── connection_handler.yml                  # WebSocketHandler: handle_connection method, HTTP upgrade logic, authentication flow, register in registry, spawn message loop task
└── observability.yml                       # Prometheus metrics: websocket_connections_total (gauge), connection_latency_ms (histogram <500ms target), authentication_failures_total (counter), graceful_disconnects_total (counter)
```

**ADR References:** ADR-0040a lines 1-251 (connection), 252-500 (JWT auth), 501-750 (registry), 751-1000 (TLS), 1001-1133 (observability)

---

#### Issue 2.14.2: Message Framing & FlatBuffers Protocol Contracts

**Expected Output:** `contracts/api/websocket/protocol/` (8 files)

```
├── websocket_message_envelope.fbs          # WebSocketMessage FlatBuffers: version, message_id, conversation_id, timestamp_ms, trace_id, payload (union of 17 types)
├── message_payload_union.fbs               # MessagePayload union: ConnectionEstablished, Heartbeat, HeartbeatAck, UserMessage, AgentMessageStart, AgentMessageChunk, AgentMessageEnd, ToolCallStarted, Error (17 total)
├── connection_messages.fbs                 # Connection messages: ConnectionEstablished (session_id, capabilities), Heartbeat (timestamp), HeartbeatAck, RefreshToken, TokenRefreshed, Disconnect, Goodbye (7 types)
├── agent_streaming_messages.fbs            # Agent messages: AgentMessageStart (agent_name, turn_id), AgentMessageChunk (text_delta, only new tokens), AgentMessageEnd (finish_reason), delta-based streaming (90% bandwidth reduction)
├── tool_messages.fbs                       # Tool messages: ToolCallStarted (tool_name, arguments), ToolCallChunk (output_delta), ToolCallCompleted (result, success, error)
├── message_router.yml                      # MessageRouter class: Route by message type (enum), handler registry (message_type → callback), type-safe deserialization, <0.1ms routing overhead
├── serialization_performance.yml           # FlatBuffers serialization: <1ms serialization budget, <0.5ms zero-copy deserialization, 50% smaller than JSON (1KB vs 2KB per chunk)
└── observability.yml                       # Prometheus metrics: messages_sent_total (counter by type), serialization_latency_ms (histogram <1ms target), message_size_bytes (histogram), deserialization_errors_total
```

**ADR References:** ADR-0040b lines 1-251 (framing), 252-500 (FlatBuffers), 501-750 (17 types), 751-1000 (delta streaming), 1001-1336 (routing)

---

#### Issue 2.14.3: Backpressure & Flow Control Contracts

**Expected Output:** `contracts/api/websocket/flow_control/` (7 files)

```
├── message_queue.yml                       # MessageQueue: mpsc::channel (100 capacity), bounded queue (prevents infinite growth), non-blocking send (<1ms), recv method, queue depth tracking
├── flow_control_manager.yml                # FlowControlManager: Monitor queue depth per session, warning at 90% full (90 messages), drop oldest messages (FIFO) when queue full, backpressure handling
├── message_buffering.yml                   # Message buffer strategy: Buffer last 100 messages (5-minute TTL), used for reconnection (client requests missed messages), evict messages older than 5 minutes
├── streaming_engine.yml                    # StreamingEngine: <200ms TTFT (time to first token) target, token-by-token streaming, measure latency per token, emit ttft_ms metric
├── slow_client_handling.yml                # Slow client strategy: Detect slow WebSocket send (>500ms RTT), queue fills up (>90%), drop oldest messages (prevent server OOM), emit slow_client_detected metric
├── async_queue_operations.yml              # Async operations: Non-blocking send to queue (<1ms), background task reads from queue and sends to WebSocket, decouple agent generation from WebSocket send
└── observability.yml                       # Prometheus metrics: queue_depth (gauge), messages_dropped_total (counter), ttft_ms (histogram <200ms target), queue_insert_latency_ms (histogram <1ms), slow_clients_total
```

**ADR References:** ADR-0040c lines 1-251 (async queue), 252-500 (flow control), 501-750 (buffering), 751-1000 (streaming), 1001-1063 (observability)

---

#### Issue 2.14.4: Heartbeat & Reconnection Contracts

**Expected Output:** `contracts/api/websocket/reconnection/` (7 files)

```
├── heartbeat_manager.yml                   # HeartbeatManager: 30-second interval ping/pong (RFC 6455 §5.5.2), server sends Heartbeat message, client responds with HeartbeatAck, update last_heartbeat timestamp
├── timeout_detection.yml                   # Timeout threshold: 90 seconds (3× heartbeat interval), close stale connections if no HeartbeatAck, free server resources, emit timeout_detected metric
├── auto_reconnect_client.yml               # Client-side auto-reconnect: Exponential backoff (1s, 2s, 4s, 8s, 16s max), max 5 attempts (stop after 31 seconds), include last_message_id in reconnect request
├── missed_message_replay.yml               # Message replay: Client sends last_message_id on reconnect, server replays buffered messages (from Issue 2.14.3 buffer), 5-minute window, prevent data loss on reconnect
├── exponential_backoff.yml                 # Backoff sequence: 1s, 2s, 4s, 8s, 16s (max), prevent thundering herd on network outage, jitter (±20%) to spread reconnects, max 5 attempts before giving up
├── reconnect_success_rate.yml              # Target >95% reconnect success rate, track reconnect attempts vs successes, emit reconnect_success_rate gauge, identify patterns (mobile networks, firewalls)
└── observability.yml                       # Prometheus metrics: heartbeats_sent_total (counter), timeouts_total (counter), reconnects_total (counter), reconnect_success_rate (gauge >95% target), timeout_detection_latency_ms (<90s)
```

**ADR References:** ADR-0040d lines 1-251 (heartbeat), 252-500 (timeout), 501-750 (auto-reconnect), 751-968 (message replay, observability)

**Total Contracts: 30 files** (8 connection + 8 protocol + 7 flow control + 7 reconnection)

---

## Epic 2.15: REST API Session Management Contracts

**Source ADR:** ADR-0041 (REST API) + sub-ADRs (0041a-d)
**Priority:** CRITICAL (Communication & Integration)
**Contract Count:** 33 files (reduced from 34: removed Redis-specific contracts for K1-only focus)

**Context:** ADR-0041 requires RESTful API following Roy Fielding's constraints (2000) with 21 endpoints for session lifecycle (POST, GET, PATCH, DELETE /v1/sessions), turn submission (sync <5000ms or async with webhook), stateless JWT authentication (ADR-0037), cursor-based pagination (opaque cursor, no offset), idempotency keys (24h deduplication via K0 SQLite, 8% duplicate rate), ETag/Last-Modified caching (82% hit rate = 8ms cached responses), RFC 7807 error format, and OpenAPI 3.1 specification with auto-generated SDKs.

**Dual-Kernel Architecture Note:** These are **K1 API Gateway** contracts. K0 Memory Kernel handles actual storage (SQLite-based idempotency ledger, WAL, receipts). K1 focuses on REST API semantics and K0 integration.

### Issue 2.15.1: Session CRUD & Resource Design Contracts

**Expected Output:** `contracts/api/rest/sessions/` (9 files)

```
├── post_create_session.yml                 # POST /v1/sessions: Create session with persona, privacy_band, capabilities, initial_agents, metadata, ttl_seconds, return 201 Created with Location header, <500ms P95
├── get_session.yml                         # GET /v1/sessions/{id}: Retrieve session details (status, agents, metadata), ETag header (MD5 hash of state), Last-Modified header (ISO 8601), <100ms P95 (uncached), <10ms P95 (cached 304 Not Modified)
├── get_sessions_list.yml                   # GET /v1/sessions: List sessions with cursor-based pagination (limit=20 default, max=100), filter by status/privacy_band, return pagination object (has_more, next_cursor)
├── patch_update_session.yml                # PATCH /v1/sessions/{id}: Partial update (metadata, capabilities, ttl_seconds), return 200 OK with updated session, <200ms P95
├── delete_terminate_session.yml            # DELETE /v1/sessions/{id}: Terminate session (graceful agent drainage, save SessionState to K0), return 200 OK, <300ms P95
├── hateoas_links.yml                       # HATEOAS links in responses: _links object (self, turns, agents, related), clients navigate via links (no hardcoded URLs), evolvable API without breaking clients
├── http_caching.yml                        # HTTP caching strategy: ETag (MD5 hash), Last-Modified (ISO 8601), Cache-Control (private, max-age=300), 82% cache hit rate (2.46M of 3M GETs return 304 Not Modified)
├── resource_oriented_design.yml            # Resource-oriented URLs: Collection /v1/sessions (list), Resource /v1/sessions/{id} (single), Sub-resource /v1/sessions/{id}/turns, no RPC-style (/createSession ❌)
└── observability.yml                       # Prometheus metrics: sessions_created_total (counter), session_read_latency_ms (histogram <100ms uncached), cache_hit_rate (gauge 82% target), sessions_terminated_total (counter)
```

**ADR References:** ADR-0041a lines 1-251 (session CRUD), 252-500 (HATEOAS), 501-750 (caching), 751-1000 (resource design), 1001-1626 (observability)

---

### Issue 2.15.2: Idempotency & State Synchronization Contracts (K1 API Layer)

**Expected Output:** `contracts/api/rest/idempotency/` (7 files)

**Architecture Note:** This issue focuses on **K1 REST API layer** contracts. K0 handles actual idempotency storage (SQLite `idem_ledger` table documented in `k0/README.md` Section 9). K1's role is to accept idempotency keys and delegate to K0.

```
├── idempotency_key_header.yml              # Idempotency-Key header (Stripe pattern): K1 accepts optional header for POST requests, client-generated UUID, K1 includes in K0 envelope, forwards to K0 command port
├── k0_integration.yml                      # K1 → K0 integration: Call POST /k0/command.submit with idem_key in envelope, K0 performs SQLite ledger check (k0/idem/ledger.py), K0 returns 409 IDEMPOTENT_DUPLICATE or 200 OK, K1 translates to REST response
├── duplicate_detection.yml                 # K1 duplicate handling: Receive 409 from K0 → return 200 OK with cached response + X-Idempotent-Replayed: true header, receive 200 from K0 → return 201 Created with new response, <5ms K1 overhead
├── k0_storage_reference.yml                # Reference to K0 implementation: K0 uses SQLite idem_ledger table (not Redis), BLAKE3 hash derivation, 24h TTL via expiry_ts column, <25ms P50 / <150ms P95 (K0 SLO), see k0/README.md Section 9 for details
├── state_synchronization.yml               # State sync between REST and WebSocket: Shared SessionState (ADR-0012) in K1 kernel memory, both channels read/write same state, no dual-write problem, changes visible immediately, <1ms sync latency
├── sync_async_turn_modes.yml               # Turn modes: Sync (wait for response, <5000ms, 30s timeout), Async (return 202 Accepted with turn_id, webhook callback when complete), client chooses via mode parameter, 92% sync / 8% async usage
├── webhook_callbacks.yml                   # Webhook callbacks (async mode): Client registers webhook URL in session metadata, K1 POSTs turn result when complete, retry policy (3 attempts, exponential backoff 1s/2s/4s), 98% first-attempt delivery success
└── observability.yml                       # K1 API metrics: idempotency_checks_total (counter), k0_integration_latency_ms (histogram <5ms K1 overhead), duplicate_requests_total (counter, 8% rate), webhook_deliveries_total (counter), webhook_failures_total
```

**ADR References:** ADR-0041b lines 1-251 (idempotency), 252-500 (K1-K0 integration), 501-750 (state sync), 751-1000 (sync/async modes), 1001-1277 (webhooks, observability)

**K0 Implementation Reference:** See `k0/README.md` Section 9 for actual idempotency ledger implementation (SQLite-based, BLAKE3 hashing, 24h expiry_ts, <25ms P50 latency)

---

### Issue 2.15.3: Cursor-Based Pagination Contracts

**Expected Output:** `contracts/api/rest/pagination/` (9 files)

```
├── opaque_cursor.yml                       # Cursor encoding: Base64-encoded last item ID ({"id": "session-020"}), client can't manipulate cursor (prevents "jump to page 500" abuse), server decodes and validates
├── pagination_manager.yml                  # PaginationManager class (1,120 lines): encode_cursor/decode_cursor methods, paginate method (fetch limit+1, check has_more), O(log n) index lookup vs O(n) offset scan
├── has_more_flag.yml                       # has_more flag: Fetch limit + 1 items to check if more exist, if result.len() > limit: has_more = true, no expensive COUNT(*) query (>1s for 1M rows)
├── next_prev_cursors.yml                   # next_cursor/prev_cursor: Return next_cursor if has_more, return prev_cursor for backward pagination (optional), include in _links.next/_links.prev (HATEOAS)
├── default_max_limits.yml                  # Pagination limits: Default limit 20 items, max limit 100 items (prevent abuse), client can request 1-100 items per page, return 400 Bad Request if limit >100
├── indexed_queries.yml                     # Database optimization: Always use indexed columns (id, user_id, created_at), cursor query (WHERE id > cursor_id LIMIT n), O(log n) B-tree index lookup, <100ms P95 pagination
├── no_total_count.yml                      # No COUNT(*) queries: Trade-off (can't show "Page X of Y"), benefit (no 1s+ COUNT query), mobile apps prefer infinite scroll anyway, has_more sufficient for UX
├── infinite_scrolling.yml                  # Infinite scroll support: Mobile apps load more as user scrolls, simple "give me next 20 after cursor X", no offset tracking, consistent results during concurrent writes
└── observability.yml                       # Prometheus metrics: pagination_requests_total (counter), pagination_latency_ms (histogram <100ms target, 78ms P95 actual), cursor_decode_errors_total (counter), page_sizes (histogram)
```

**ADR References:** ADR-0041c lines 1-251 (cursor), 252-500 (has_more), 501-750 (indexed queries), 751-906 (infinite scroll, observability)

---

### Issue 2.15.4: OpenAPI Spec & RFC 7807 Error Handling Contracts

**Expected Output:** `contracts/api/rest/documentation/` (8 files)

```
├── openapi_3_1_spec.yml                    # OpenAPI 3.1 specification (2,400 lines): All 21 endpoints documented, request/response schemas with examples, authentication schemes (JWT Bearer), auto-generate SDKs (TypeScript, Python, Go)
├── rfc7807_error_format.yml                # RFC 7807 Problem Details: type (URL to error docs), title (human-readable), status (HTTP code), detail (specific message with context), instance (request path), trace_id (optional)
├── error_types.yml                         # 11 error types: session-not-found (404), turn-not-found (404), agent-not-found (404), rate-limit-exceeded (429), invalid-input (400), unauthorized (401), forbidden (403), conflict (409), timeout (504), internal-error (500)
├── http_status_codes.yml                   # Standard HTTP status codes: 200 OK, 201 Created, 202 Accepted, 304 Not Modified, 400 Bad Request, 401 Unauthorized, 403 Forbidden, 404 Not Found, 409 Conflict, 429 Too Many Requests, 500 Internal Server Error
├── error_handler.yml                       # ErrorHandler class (880 lines): handle_error method, typed errors (SessionNotFound, RateLimitExceeded), generate RFC 7807 response, include trace_id, <10ms error response generation
├── swagger_ui_integration.yml              # Swagger UI: Interactive API documentation, try endpoints from browser, see request/response examples, OAuth 2.0 flow for JWT auth, hosted at /docs endpoint
├── sdk_generation.yml                      # Auto-generated SDKs: openapi-generator for TypeScript, Python, Go, Ruby, Java, type-safe client libraries, no manual SDK maintenance, semantic versioning (1.0.0)
└── observability.yml                       # Prometheus metrics: errors_total (counter by type and status), error_response_latency_ms (histogram <10ms), error_rate_gauge (<0.5% target, 0.3% actual), swagger_ui_views_total
```

**ADR References:** ADR-0041d lines 1-251 (OpenAPI), 252-500 (RFC 7807), 501-750 (error types), 751-881 (SDK generation, observability)

**Total Contracts: 33 files** (9 session CRUD + 7 idempotency [K1-only] + 9 pagination + 8 documentation)

**Key Contracts:**

- **`idempotency_key_header.yml`** — K1 accepts Idempotency-Key header, forwards to K0
- **`k0_integration.yml`** — K1 → K0 command port integration contract (how K1 calls K0)
- **`k0_storage_reference.yml`** — Reference to K0's SQLite implementation (see k0/README.md Section 9)
- **`duplicate_detection.yml`** — K1 handles 409 responses from K0, translates to REST semantics

**Architecture Notes:**

- **K1 Responsibility:** REST API layer, accept idempotency keys, forward to K0, translate K0 responses (409 → 200 OK with X-Idempotent-Replayed)
- **K0 Responsibility:** Actual idempotency storage (SQLite `idem_ledger` table), BLAKE3 hash derivation, 24h TTL via `expiry_ts` column, <25ms P50 latency
- **Performance:** <5ms K1 overhead + <25ms P50 K0 latency = <30ms total idempotency check (hypersonic local-first)
- **Local-First:** Zero external dependencies (no Redis), 100% offline capability, SQLite-based storage in K0

---

## 📦 Milestone 3: Serialization & API Contracts (Weeks 7-9)

**Goal:** Define FlatBuffers schemas, API specifications, WebSocket, and SSE contracts

### **Milestone Deliverables:**

- [ ] 76 FlatBuffers schemas across 5 layers
- [ ] OpenAPI 3.1 REST specifications
- [ ] WebSocket binary protocol contracts
- [ ] SSE event schemas (17 types)
- [ ] Schema versioning and evolution contracts

---

## Epic 3.1: FlatBuffers Schema Contracts

**ADR Source:** ADR-0011, ADR-0012, ADR-0012a-e
**Timeline:** Week 7-8 (10 days)
**Dependencies:** Milestone 1-2 (all prior contracts)

### **Issues for Epic 3.1:**

#### **Issue 3.1.1: FlatBuffers Design Principles Contract**

**Effort:** 1 day | **Source ADR:** `0011-flatbuffers-serialization.md`

**Expected Output:** `contracts/flatbuffers/principles/`

```
├── schema_design_principles.yml     # Naming, field ordering, optional fields (ADR-0011a)
├── code_generation_integration.yml  # Build-time codegen (ADR-0011b)
├── zero_copy_performance.yml        # <1ms serialization target (ADR-0011c)
├── schema_evolution_versioning.yml  # Forward/backward compatibility (ADR-0011d)
└── flatbuffers_vs_json.yml          # Performance comparison
```

---

#### **Issue 3.1.2: Layer 1 Core Kernel Schemas (15 schemas)**

**Effort:** 2 days | **Source ADR:** `0012a-layer1-core-kernel-schemas.md`

**Expected Output:** `contracts/flatbuffers/layer1_kernel/`

```
├── agent_lease.fbs                  # Agent capability/lease
├── task_announcement.fbs            # Task broadcast
├── plan_proposal.fbs                # Agent proposal
├── hire_request.fbs                 # Agent hiring
├── protocol_message.fbs             # Protocol validation
├── mailbox_message.fbs              # Actor mailbox envelope
├── health_check.fbs                 # Supervisor health ping
├── supervisor_event.fbs             # Supervisor notifications
... (15 schemas total)
```

**Template Structure for Each Schema:**

```fbs
// agent_lease.fbs
namespace k1.kernel;

table AgentLease {
  agent_id: string;
  capabilities: [Capability];
  bands: [PrivacyBand];
  budgets: Budget;
  ttl_ms: int32;
  issued_at: int64;
  signature: [ubyte];
}

enum Capability: byte {
  TOOL_CALL = 0,
  MCP_ACCESS = 1,
  WASM_SANDBOX = 2,
  PROCESS_SANDBOX = 3
}

enum PrivacyBand: byte {
  GREEN = 0,
  AMBER = 1,
  RED = 2
}

table Budget {
  tokens_max: int32;
  cost_usd_max: float;
  latency_ms_max: int32;
}
```

---

#### **Issue 3.1.3: Layer 2 State & Persistence Schemas (18 schemas)**

**Effort:** 2 days | **Source ADR:** `0012b-layer2-state-persistence-schemas.md`

**Expected Output:** `contracts/flatbuffers/layer2_state/`

```
├── session_state.fbs                # 6-section SessionState
├── state_delta.fbs                  # SessionState delta serialization
├── grounding_commit.fbs             # Conversation turn commit
├── receipt.fbs                      # K0 persistence receipt
├── turn_history.fbs                 # Conversation history
├── memory_write_batch.fbs           # K0 bridge batching
... (18 schemas total)
```

---

#### **Issue 3.1.4: Layer 3 Execution & Tools Schemas (16 schemas)**

**Effort:** 2 days | **Source ADR:** `0012c-layer3-execution-tools-schemas.md`

**Expected Output:** `contracts/flatbuffers/layer3_execution/`

```
├── tool_call.fbs                    # Tool invocation
├── tool_result.fbs                  # Tool response
├── mcp_request.fbs                  # MCP protocol request
├── mcp_response.fbs                 # MCP protocol response
├── wasm_context.fbs                 # WASM sandbox context
├── sandbox_config.fbs               # Sandbox configuration
... (16 schemas total)
```

---

#### **Issue 3.1.5: Layer 4 Ingress & Voice Schemas (14 schemas)**

**Effort:** 2 days | **Source ADR:** `0012d-layer4-ingress-voice-schemas.md`

**Expected Output:** `contracts/flatbuffers/layer4_ingress/`

```
├── websocket_message.fbs            # WebSocket binary protocol
├── sse_event.fbs                    # Server-sent events
├── voice_frame.fbs                  # Audio frame
├── vad_result.fbs                   # Voice activity detection
├── asr_result.fbs                   # Speech recognition
├── tts_request.fbs                  # Text-to-speech
... (14 schemas total)
```

---

#### **Issue 3.1.6: Layer 5 Infrastructure Schemas (13 schemas)**

**Effort:** 1 day | **Source ADR:** `0012e-layer5-infrastructure-schemas.md`

**Expected Output:** `contracts/flatbuffers/layer5_infrastructure/`

```
├── config_update.fbs                # Hot config reload
├── prometheus_metric.fbs            # Metrics export
├── opentelemetry_span.fbs           # Trace spans
├── thermal_state.fbs                # NPU/GPU/CPU temperature
├── backpressure_signal.fbs          # Flow control
├── scheduler_task.fbs               # WFQ scheduler
... (13 schemas total)
```

---

## Epic 3.2: API Specification Contracts

**ADR Source:** ADR-0014, ADR-0015, ADR-0016, ADR-0040, ADR-0041, ADR-0047
**Timeline:** Week 8-9 (5 days)
**Dependencies:** Epic 3.1 (FlatBuffers schemas)

### **Issues for Epic 3.2:**

#### **Issue 3.2.1: REST API Contracts (Dual Format)**

**Effort:** 2 days | **Source ADR:** `0014-json-rest-api-dual-format.md`, `0041-rest-api-session-management.md`

**Expected Output:** `contracts/api/rest/`

```
├── content_negotiation.yml          # JSON vs FlatBuffers selection (ADR-0014a)
├── openapi_spec_generation.yml      # Auto-gen from FlatBuffers (ADR-0014b)
├── request_response_pipeline.yml    # Serialization pipeline (ADR-0014c)
├── session_crud.yml                 # Session resource design (ADR-0041a)
├── idempotency_keys.yml             # State synchronization (ADR-0041b)
├── cursor_pagination.yml            # Efficient listing (ADR-0041c)
└── rfc7807_errors.yml               # Error handling (ADR-0041d)
```

---

#### **Issue 3.2.2: WebSocket Binary Protocol Contracts**

**Effort:** 1 day | **Source ADR:** `0015-websocket-binary-protocol.md`, `0040-websocket-realtime-chat.md`

**Expected Output:** `contracts/api/websocket/`

```
├── message_envelope.yml             # WebSocket message routing (ADR-0015a)
├── flow_control.yml                 # Backpressure (ADR-0015b)
├── reconnection_resume.yml          # Session resume (ADR-0015c)
├── streaming_tokens.yml             # Real-time token delivery (ADR-0015d)
├── typescript_sdk.yml               # Browser SDK (ADR-0015e)
├── connection_management.yml        # Auth, heartbeat (ADR-0040a-d)
└── binary_protocol_spec.yml         # FlatBuffers over WebSocket
```

---

#### **Issue 3.2.3: SSE Event Schema Contracts**

**Effort:** 4 days | **Source ADR:** `0016-sse-event-schemas.md` + sub-ADRs `0016a-d`

**Expected Output:** `contracts/api/sse/` (25 files)

**Event Envelope & Common (2 files):**

```
├── event_envelope.fbs               # EventEnvelope root table (metadata + payload union)
└── event_metadata.fbs               # EventMetadata, SchemaVersion struct
```

**Agent Lifecycle Events (4 FlatBuffers schemas):**

```
├── agent_hired.fbs                  # AgentHired event
├── agent_fired.fbs                  # AgentFired event (TerminationReason enum)
├── agent_crashed.fbs                # AgentCrashed event (blacklist tracking)
└── agent_restarted.fbs              # AgentRestarted event (restart attempt)
```

**Turn Execution Events (4 FlatBuffers schemas):**

```
├── turn_started.fbs                 # TurnStarted event (intent, privacy_band)
├── turn_completed.fbs               # TurnCompleted event (metrics: ttft_ms, tokens)
├── turn_failed.fbs                  # TurnFailed event (failure_reason, retry_policy)
└── turn_interrupted.fbs             # TurnInterrupted event (barge_in_latency_ms)
```

**Tool Execution Events (4 FlatBuffers schemas):**

```
├── tool_call_started.fbs            # ToolCallStarted event
├── tool_call_completed.fbs          # ToolCallCompleted event
├── tool_call_failed.fbs             # ToolCallFailed event
└── tool_approval_required.fbs       # ToolApprovalRequired event (risk_level)
```

**Session Lifecycle Events (3 FlatBuffers schemas):**

```
├── session_created.fbs              # SessionCreated event
├── session_terminated.fbs           # SessionTerminated event
└── session_crashed.fbs              # SessionCrashed event
```

**System Events (2 FlatBuffers schemas):**

```
├── heartbeat.fbs                    # Heartbeat event (keepalive)
└── error.fbs                        # Error event (severity, error_trace)
```

**Serialization & Filtering (5 YAML contracts):**

```
├── flatbuffers_to_json_serializer.yml  # PascalCase→snake_case, <2ms P95 (ADR-0016b)
├── topic_filter.yml                    # 5 topics, O(1) membership check (ADR-0016c)
├── subscription_api.yml                # Query params ?topics=...,?session_id=... (ADR-0016c)
├── sse_formatter.yml                   # SSE text format (event:, id:, data:, retry:)
└── browser_eventsource_integration.yml # EventSource API, auto-reconnect (ADR-0016d)
```

**Event Type Enumeration (1 file):**

```
└── event_types.yml                     # EventType enum, category mapping (ADR-0016a)
```

---

#### **Issue 3.2.4: OpenAPI 3.1 Specifications**

**Effort:** 1 day | **Source ADR:** `0047-openapi-3-1-rest-specs.md`

**Expected Output:** `contracts/api_specs/openapi_3_1_specs/`

```
├── k1_rest_api_v1.yml               # Complete OpenAPI 3.1 spec
├── session_endpoints.yml            # /sessions/* endpoints
├── turn_endpoints.yml               # /turns/* endpoints
├── memory_endpoints.yml             # /memories/* endpoints
├── schema_components.yml            # Reusable schemas
└── security_schemes.yml             # JWT auth
```

---

## Epic 3.3: K0 Pipeline Contracts (P01-P20)

**ADR Source:** ADR-0001 (K0/K1 Kernel Split), ADR-0012 (76 Schemas - Pipelines category)
**Timeline:** Week 9 (5 days)
**Dependencies:** Epic 3.1 (FlatBuffers schemas), Epic 1.1 (K0 Bridge ports)

### **Issues for Epic 3.3:**

#### **Issue 3.3.1: Memory Pipeline Contracts (P01-P05)**

**Effort:** 1 day | **Source ADR:** `0001-k0-k1-kernel-split.md` section "20 K0 Pipelines"

**Expected Output:** `contracts/k0_bridge/pipelines/memory/`

```
├── p01_recall.yml                   # Memory retrieval (query → results)
│   ├── RecallRequest.fbs           # query, context, space_ids, modalities, max_results
│   ├── RecallResponse.fbs          # results (MemoryItem[]), total_found, latency_ms
│   └── recall_receipt.yml          # K0 receipt (hit_rate, source_layers, trace_id)
├── p02_memory_formation.yml         # Write conversation to memory
│   ├── MemoryFormationRequest.fbs  # turn_summary, entities, relations, sentiment
│   ├── MemoryReceipt.fbs           # memory_id, commit_timestamp, WAL_seqno
│   └── formation_contracts.yml     # Durability guarantees (fsync, replication)
├── p03_entity_extraction.yml        # Extract entities from text
│   ├── EntityExtractionRequest.fbs # text, entity_types, context
│   ├── EntityExtractionResponse.fbs # entities (Entity[]), confidence scores
│   └── entity_schema.yml           # Entity types (PERSON, ORG, LOC, DATE, etc.)
├── p04_relation_linking.yml         # Link entities to knowledge graph
│   ├── RelationLinkingRequest.fbs  # entities, candidate_relations
│   ├── RelationLinkingResponse.fbs # relations (Relation[]), confidence
│   └── relation_schema.yml         # Relation types (IS_A, PART_OF, LOCATED_IN, etc.)
└── p05_contradiction_detection.yml  # Detect contradictory facts
    ├── ContradictionRequest.fbs    # new_facts, existing_beliefs
    ├── ContradictionResponse.fbs   # contradictions (Contradiction[]), severity
    └── contradiction_resolution.yml # Resolution strategies (prefer new, prefer old, ask user)
```

**Key Contracts:**

- **P01 Recall:** Multi-modal memory retrieval (text + audio + vision), semantic search, BM25 ranking, vector embeddings
- **P02 Memory Formation:** Turn summarization, entity extraction, sentiment analysis, write to K0 WAL
- **P03 Entity Extraction:** NER (Named Entity Recognition), entity types (PERSON, ORG, LOC, DATE, MONEY, etc.)
- **P04 Relation Linking:** Knowledge graph relations (IS_A, PART_OF, LOCATED_IN, WORKS_FOR, etc.)
- **P05 Contradiction Detection:** Detect conflicting facts, confidence-based resolution

---

#### **Issue 3.3.2: Learning Pipeline Contracts (P06-P08)**

**Effort:** 1 day | **Source ADR:** `0001-k0-k1-kernel-split.md`, ADR-0027 (Learning Loop)

**Expected Output:** `contracts/k0_bridge/pipelines/learning/`

```
├── p06_learning_tick.yml            # Adaptive learning feedback
│   ├── LearningTickRequest.fbs     # feedback_signals (explicit/implicit/behavioral)
│   ├── LearningTickResponse.fbs    # drift_detected, config_updates, new_weights
│   └── feedback_schema.yml         # Signal types (explicit 1.0, implicit 0.5, behavioral 0.2)
├── p07_sync.yml                     # K1 → K0 state synchronization
│   ├── SyncRequest.fbs             # state_deltas, checkpoint_seqno, session_id
│   ├── SyncResponse.fbs            # commit_timestamp, K0_receipt_id, synced_seqno
│   └── sync_guarantees.yml         # Durability (WAL + fsync), bounded staleness (<250ms)
└── p08_preference_learning.yml      # Learn user preferences
    ├── PreferenceRequest.fbs       # interaction_history, preference_candidates
    ├── PreferenceResponse.fbs      # learned_preferences (Preference[]), confidence
    └── preference_schema.yml       # Preference types (communication_style, privacy_level, tools)
```

**Key Contracts:**

- **P06 Learning:** Feedback signals (explicit: user rating, implicit: click-through, behavioral: dwell time), drift detection, config hot-reload
- **P07 Sync:** SessionState delta batching (every 5min or 10 deltas), K0 WAL commit, checkpoint coordination
- **P08 Preference Learning:** Infer user preferences from interaction history (communication style, privacy bands, tool preferences)

---

#### **Issue 3.3.3: Content Analysis Pipeline Contracts (P09-P12)**

**Effort:** 1 day | **Source ADR:** `0001-k0-k1-kernel-split.md`

**Expected Output:** `contracts/k0_bridge/pipelines/content_analysis/`

```
├── p09_sentiment_analysis.yml       # Analyze emotional tone
│   ├── SentimentRequest.fbs        # text, context, language
│   ├── SentimentResponse.fbs       # sentiment (POSITIVE/NEGATIVE/NEUTRAL), confidence, emotions
│   └── sentiment_schema.yml        # Emotion types (joy, anger, sadness, fear, surprise, disgust)
├── p10_pii_detection.yml            # Detect personally identifiable information
│   ├── PIIDetectionRequest.fbs     # text, detection_mode (STRICT/MODERATE/PERMISSIVE)
│   ├── PIIDetectionResponse.fbs    # pii_entities (PIIEntity[]), privacy_band_suggestion
│   └── pii_schema.yml              # PII types (EMAIL, PHONE, SSN, CREDIT_CARD, ADDRESS, NAME)
├── p11_moderation.yml               # Content moderation (safety filter)
│   ├── ModerationRequest.fbs       # text, moderation_policy (STRICT/MODERATE/PERMISSIVE)
│   ├── ModerationResponse.fbs      # blocked, violation_type, confidence, suggested_action
│   └── moderation_schema.yml       # Violation types (HATE_SPEECH, VIOLENCE, SEXUAL, HARASSMENT)
└── p12_policy_evaluation.yml        # Evaluate against family policies
    ├── PolicyEvalRequest.fbs       # action, context, family_policies
    ├── PolicyEvalResponse.fbs      # allowed, violated_policies, arbiter_required
    └── policy_schema.yml           # Policy types (privacy, safety, spending, screen_time)
```

**Key Contracts:**

- **P09 Sentiment:** Emotional tone analysis (POSITIVE/NEGATIVE/NEUTRAL), fine-grained emotions (joy, anger, sadness, etc.)
- **P10 PII Detection:** Identify PII entities (EMAIL, PHONE, SSN, etc.), suggest privacy band (GREEN/AMBER/RED)
- **P11 Moderation:** Content safety filter (HATE_SPEECH, VIOLENCE, SEXUAL, HARASSMENT), confidence-based blocking
- **P12 Policy Evaluation:** Family policy enforcement (privacy, safety, spending limits), arbiter escalation for RED band actions

---

#### **Issue 3.3.4: Transformation Pipeline Contracts (P13-P16)**

**Effort:** 1 day | **Source ADR:** `0001-k0-k1-kernel-split.md`

**Expected Output:** `contracts/k0_bridge/pipelines/transformation/`

```
├── p13_summarization.yml            # Generate summaries
│   ├── SummarizationRequest.fbs    # text, summary_length (SHORT/MEDIUM/LONG), style
│   ├── SummarizationResponse.fbs   # summary, key_points, entities_mentioned
│   └── summary_schema.yml          # Summary types (extractive, abstractive, bullet_points)
├── p14_translation.yml              # Language translation
│   ├── TranslationRequest.fbs      # text, source_lang, target_lang, preserve_entities
│   ├── TranslationResponse.fbs     # translated_text, confidence, detected_lang
│   └── translation_schema.yml      # Supported languages (ISO 639-1 codes)
├── p15_embedding_generation.yml     # Generate text embeddings
│   ├── EmbeddingRequest.fbs        # text, embedding_model (ada-002, etc.), dimensions
│   ├── EmbeddingResponse.fbs       # embedding (float[]), latency_ms, cost_usd
│   └── embedding_schema.yml        # Model types (ada-002, instructor-xl, etc.)
└── p16_vector_search.yml            # Semantic vector search
    ├── VectorSearchRequest.fbs     # query_embedding, top_k, filters, space_ids
    ├── VectorSearchResponse.fbs    # results (VectorMatch[]), similarity_scores
    └── vector_index_schema.yml     # Index types (HNSW, IVF, FLAT), distance metrics (cosine, euclidean)
```

**Key Contracts:**

- **P13 Summarization:** Extractive vs abstractive summaries, length control (SHORT/MEDIUM/LONG), key point extraction
- **P14 Translation:** Multi-language support (ISO 639-1), entity preservation, language detection
- **P15 Embedding Generation:** Text → vector embeddings (ada-002, instructor-xl), dimensionality (768, 1536)
- **P16 Vector Search:** Semantic search with embeddings, top-k retrieval, similarity scoring (cosine, euclidean)

---

#### **Issue 3.3.5: Operational Pipeline Contracts (P17-P20)**

**Effort:** 1 day | **Source ADR:** `0001-k0-k1-kernel-split.md`

**Expected Output:** `contracts/k0_bridge/pipelines/operational/`

```
├── p17_resource_allocation.yml      # Request K0 resources
│   ├── ResourceAllocationRequest.fbs # resource_type (MEMORY/CPU/GPU), amount, duration
│   ├── ResourceAllocationResponse.fbs # allocated, resource_id, expires_at
│   └── resource_schema.yml         # Resource types, allocation policies (fair share, priority)
├── p18_cost_tracking.yml            # Track usage costs
│   ├── CostTrackingRequest.fbs     # operation_type, tokens_used, model_id, duration_ms
│   ├── CostReceipt.fbs             # cost_usd, cost_breakdown (model/storage/compute), budget_remaining
│   └── cost_schema.yml             # Cost models (per-token, per-second, per-GB), budget enforcement
├── p19_audit_logging.yml            # Security audit logs
│   ├── AuditLogRequest.fbs         # event_type, actor_id, resource_id, action, outcome
│   ├── AuditLogReceipt.fbs         # log_id, timestamp, retention_policy
│   └── audit_schema.yml            # Event types (ACCESS, MODIFY, DELETE, ESCALATE), retention (90 days)
└── p20_analytics.yml                # Usage analytics
    ├── AnalyticsRequest.fbs        # query_type (USAGE/PERFORMANCE/ERRORS), time_range, dimensions
    ├── AnalyticsResponse.fbs       # metrics (Metric[]), aggregations, visualizations
    └── analytics_schema.yml        # Metric types (latency_p95, throughput_qps, error_rate)
```

**Key Contracts:**

- **P17 Resource Allocation:** Request K0 resources (memory, CPU, GPU), allocation policies (fair share, priority queues)
- **P18 Cost Tracking:** Per-operation cost tracking (tokens, model inference, storage), budget enforcement (per-session, per-family)
- **P19 Audit Logging:** Security audit trail (who did what, when), retention policies (90 days for compliance)
- **P20 Analytics:** Usage analytics (latency P95, throughput QPS, error rate), time-series queries, dashboard integration

---

**Epic 3.3 Summary:** 20 K0 pipeline contracts (P01-P20) covering memory (P01-P05), learning (P06-P08), content analysis (P09-P12), transformation (P13-P16), operational (P17-P20). Each pipeline has request/response FlatBuffers schemas, receipt contracts, and detailed schema definitions. Total: 60 contract files (3 per pipeline: request, response, schema/receipt).

---

## 📦 Milestone 4: State & Performance Contracts (Weeks 10-12)

**Goal:** Define SessionState, storage, performance budgets, and observability contracts

### **Milestone Deliverables:**

- [ ] SessionState 6-section contracts
- [ ] Multi-tier storage contracts (Hot/Warm/Cold)
- [ ] Performance budget contracts (P95 targets)
- [ ] KV cache management contracts
- [ ] Observability contracts (Prometheus, OpenTelemetry)

---

## Epic 4.1: SessionState Contracts

**ADR Source:** ADR-0017, ADR-0017a-f, ADR-0019, ADR-0050
**Timeline:** Week 10 (5 days)
**Dependencies:** Epic 3.1 (FlatBuffers schemas)

### **Issues for Epic 4.1:**

#### **Issue 4.1.1: 6-Section SessionState Structure**

**Effort:** 4 days | **Source ADR:** `0017-sessionstate-6-section-design.md` + sub-ADRs `0017a-f`

**Expected Output:** `contracts/sessionstate/structure/` (21 files)

**Section 1: Beliefs Section (ADR-0017a) - 4 files:**

```
├── beliefs_section_schema.fbs       # Fact table (key, value, confidence, source, timestamps)
├── beliefs_manager.yml              # add_fact, get_fact, has_fact, remove_fact operations
├── beliefs_lru_eviction.yml         # LRU eviction (least recently accessed), target 10-20KB
└── beliefs_k0_serialization.yml     # FlatBuffers serialization to K0 WAL, <10ms P95
```

**Section 2: Scoreboard Section (ADR-0017b) - 4 files:**

```
├── scoreboard_section_schema.fbs    # Entity, Referent, QUD tables
├── scoreboard_manager.yml           # add_entity, resolve_referent, push_qud operations
├── scoreboard_salience_decay.yml    # Exponential decay (salience *= 0.9 per turn not mentioned)
└── scoreboard_referent_resolution.yml  # Pronoun→entity mapping ("it"→entity_5)
```

**Section 3: Control Section (ADR-0017c) - 4 files:**

```
├── control_section_schema.fbs       # AgentLease, FlowState tables
├── control_manager.yml              # acquire_lease, release_lease, set_flow_state operations
├── control_lease_timeout.yml        # Expired lease detection (lease_expires_ms), periodic scan
└── control_flow_fsm.yml             # 3-phase FSM (negotiation→selection→execution→idle)
```

**Section 4: Persona Section (ADR-0017d) - 3 files:**

```
├── persona_section_schema.fbs       # PersonaTrait table (trait_name, trait_value, confidence)
├── persona_manager.yml              # set_trait, get_trait, get_all_traits operations
└── persona_llm_formatter.yml        # Format traits for LLM system prompt injection, <5ms P95
```

**Section 5: Multimodal Section (ADR-0017e) - 3 files:**

```
├── multimodal_section_schema.fbs    # AudioBuffer, VisionEmbedding tables (K0 blob pointers)
├── multimodal_manager.yml           # add_audio_buffer, add_vision_embedding operations
└── multimodal_lru_eviction.yml      # Evict old buffers/embeddings, target 4-8KB
```

**Section 6: Meta Section (ADR-0017f) - 3 files:**

```
├── meta_section_schema.fbs          # PerformanceMetrics table (avg_ttft_ms, avg_e2e_latency_ms, counters)
├── meta_manager.yml                 # increment_turn_counter, record_ttft, record_e2e_latency operations
└── meta_telemetry_collection.yml    # Incremental averages, Prometheus export
```

---

#### **Issue 4.1.2: 3-Tier Eviction Strategy**

**Effort:** 3 days | **Source ADR:** `0018-3-tier-eviction-strategy.md` + sub-ADRs `0018a-c`

**Expected Output:** `contracts/sessionstate/eviction/` (15 files)

**Tier 1: Soft Eviction (64KB → 80KB) - ADR-0018a (6 files):**

```
├── tier1_threshold_check.yml        # Trigger at 80KB (25% buffer), <100μs decision
├── tier1_eviction_priority.yml      # 4-stage priority (meta → turns → entities → grounding)
├── tier1_meta_eviction.yml          # Evict performance metrics, keep session_id
├── tier1_old_turns_eviction.yml     # Evict turns 4+ ago, keep last 3 turns
├── tier1_expired_entities.yml       # Evict entities not mentioned in 10 turns
└── tier1_grounding_acts.yml         # Evict grounding acts 3+ turns ago
```

**Tier 2: Hard Eviction (128KB → 192KB) - ADR-0018b (5 files):**

```
├── tier2_threshold_check.yml        # Trigger at 192KB (aggressive eviction)
├── tier2_beliefs_lru.yml            # Evict least-used facts (LRU), keep top 50
├── tier2_referent_archival.yml      # Move old referents to common_ground
├── tier2_flow_history.yml           # Keep last 3 flows, evict older
└── tier2_multimodal_compress.yml    # Compress audio/vision pointers
```

**Tier 3: OOM Prevention (256KB Kill) - ADR-0018c (2 files):**

```
├── tier3_session_termination.yml    # Kill session at 256KB (last resort)
└── tier3_oom_metrics.yml            # Track OOM events (target: 0% in production)
```

**Eviction Infrastructure (2 files):**

```
├── eviction_metrics.yml             # Prometheus: tier1_total, tier2_total, tier3_total
└── never_evict_rules.yml            # Control section (agent leases, flow), persona
```

---

#### **Issue 4.1.3: SessionState Serialization & Coherence**

**Effort:** 5 days | **Source ADR:** `0019-flatbuffers-sessionstate-serialization.md` + sub-ADRs `0019a-d`, `0050-sessionstate-coherence-guarantees.md`

**Expected Output:** `contracts/sessionstate/serialization/` (27 files)

**FlatBuffers Schema Root - ADR-0019a (7 files):**

```
├── sessionstate_root.fbs            # Root table: 6 sections + metadata
├── beliefs_section.fbs              # Facts, entities, relations (scoreboard section)
├── scoreboard_section.fbs           # Referents, grounding acts, turn referents
├── control_section.fbs              # Active agents, flow state, turn state
├── persona_section.fbs              # Personality traits, voice preferences
├── multimodal_section.fbs           # Audio buffers, vision embeddings
└── meta_section.fbs                 # Session_id, timestamps, tracing_id
```

**FlatBuffers Type Schemas - ADR-0019a (7 files):**

```
├── fact_type.fbs                    # Fact: content, speaker_id, priority, verified
├── entity_type.fbs                  # Entity: name, type, attributes, last_mentioned
├── agent_lease_type.fbs             # AgentLease: agent_id, capabilities, state
├── personality_trait_type.fbs       # PersonalityTrait: trait_name, strength
├── audio_buffer_type.fbs            # AudioBuffer: buffer_ptr, sample_rate
├── vision_embedding_type.fbs        # VisionEmbedding: embedding_ptr, timestamp
└── relation_type.fbs                # Relation: entity_a, entity_b, relation_type
```

**Serialization Pipeline - ADR-0019b/0019c/0019d (6 files):**

```
├── full_serialization.yml           # Serialize all 6 sections (<1ms, 64KB target)
├── delta_serialization.yml          # Serialize changed sections only (<0.5ms)
├── zero_copy_deserialization.yml    # Mmap access without copy (<0.1ms)
├── k0_checkpoint_protocol.yml       # 5-minute checkpoint to K0 WAL
├── schema_versioning.yml            # SemVer 2.0 for schema evolution
└── serialization_metrics.yml        # Track serialize_ms, delta_size_kb
```

**Coherence Guarantees - ADR-0050 (7 files):**

```
├── coherence_guarantees.yml         # Read-Your-Writes, Monotonic Reads/Writes
├── bounded_staleness.yml            # <250ms lag K1 vs K0
├── consistency_contracts.yml        # K1 eventual, K0 strong
├── snapshot_isolation.yml           # Per-turn snapshot guarantees
├── causal_consistency.yml           # Happens-before ordering
├── conflict_resolution.yml          # Last-write-wins with timestamps
└── coherence_validation.yml         # Runtime consistency checks
```

---

## Epic 4.2: Storage Contracts

**ADR Source:** ADR-0020, ADR-0021, ADR-0022, ADR-0023
**Timeline:** Week 10-11 (3 days)
**Dependencies:** Epic 4.1 (SessionState)

### **Issues for Epic 4.2:**

#### **Issue 4.2.1: Multi-Tier Storage Contracts**

**Effort:** 3 days | **Source ADR:** `0020-multi-tier-storage.md` + sub-ADRs `0020a-c`

**Expected Output:** `contracts/storage/tiers/` (17 files)

**Hot Tier L1 (RAM) - ADR-0020a (5 files):**

```
├── hot_tier_class.yml               # HotTier: 56MB capacity, 1000 sessions
├── hot_lru_eviction.yml             # LRU eviction when capacity > 56MB
├── hot_inactive_timeout.yml         # Move to warm after 60 minutes idle
├── hot_checkpoint_coordination.yml  # Coordinate with K0Checkpointer (5 min)
└── hot_crash_recovery.yml           # Recover from K0 WAL on restart
```

**Warm Tier L2 (SSD) - ADR-0020b (6 files):**

```
├── warm_tier_class.yml              # WarmTier: 100MB capacity, 30 days
├── k0_wal_schema.yml                # SQLite schema: session_checkpoints, turn_history, receipts
├── warm_query_interface.yml         # Query K0 WAL for session retrieval (<50ms)
├── warm_archival_policy.yml         # Move to cold after 30 days
├── warm_sqlite_optimization.yml     # WAL mode, vacuum schedule
└── warm_metrics.yml                 # Track warm_retrieval_ms, warm_capacity_mb
```

**Cold Tier L3 (S3) - ADR-0020c (6 files):**

```
├── cold_tier_class.yml              # ColdTier: Unlimited capacity, S3 backend
├── s3_bucket_structure.yml          # /sessions/{session_id}/YYYY-MM/sessionstate.fb.zst
├── cold_compression.yml             # zstd level 3 compression (3:1 ratio)
├── cold_manifest_index.yml          # manifest.json per session (fast discovery)
├── cold_retrieval_protocol.yml      # Retrieve + decompress (<500ms)
└── cold_lifecycle_rules.yml         # S3 Glacier transition after 1 year
```

---

#### **Issue 4.2.2: Turn History Retention & K0 Batching**

**Effort:** 5 days | **Source ADR:** `0021-turn-history-retention-policies.md` + sub-ADRs `0021a-c`, `0022-k0-bridge-bounded-batching.md` + sub-ADRs `0022a-d`

**Expected Output:** `contracts/storage/retention/` + `contracts/k0_bridge/batching/` (22 files)

**ADR-0021: Turn History Retention Policies (10 files):**

```
retention_policies/
├── retention_policy_engine.yml      # Background task (24-hour interval), 3-tier enforcement
├── hot_tier_retention.yml           # Delete turns >7 days from SessionState
├── warm_tier_retention.yml          # Delete turns >30 days from K0 WAL
├── cold_tier_retention.yml          # Delete sessions >7 years from S3
├── privacy_band_green.yml           # Default retention (7d/30d/7y)
├── privacy_band_amber.yml           # Reduced retention (3d/14d/1y)
├── privacy_band_red.yml             # Immediate deletion (0d/0d/0d)
├── user_deletion_request.yml        # GDPR right to erasure (<24 hours)
├── compliance_reporting.yml         # Daily/weekly reports to S3
└── audit_trail_logging.yml          # Log all deletion events
```

**ADR-0022: K0 Bridge Bounded Batching (12 files):**

```
k0_bridge_batching/
├── batching_engine.yml              # Batch 10-50 messages, 100ms timeout
├── fairness_queue.yml               # Round-robin per session (max 5 msgs/session)
├── adaptive_sizing.yml              # Increase batch size under high load
├── http2_client.yml                 # HTTP/2 client with connection pooling
├── connection_pooling.yml           # 2-4 persistent connections to K0
├── hpack_compression.yml            # Header compression (80-90% reduction)
├── backpressure_monitor.yml         # Monitor K0 queue depth (every 1s)
├── backpressure_state_machine.yml   # NORMAL/WARNING/CRITICAL states
├── backpressure_cascade.yml         # Stop batching at >80% queue depth
├── batch_flatbuffers_schema.fbs     # K0MessageBatch FlatBuffers schema
├── batch_serializer.yml             # Serialize batch to FlatBuffers (<100µs)
└── zstd_compression.yml             # Optional zstd compression (70% reduction)
```

---

#### **Issue 4.2.3: Cursor-Based Pagination**

**Effort:** 3 days | **Source ADR:** `0023-cursor-based-turn-pagination.md` + sub-ADRs `0023a-c`

**Expected Output:** `contracts/api/pagination/` (10 files)

**Cursor Encoding & Security - ADR-0023a (3 files):**

```
├── turn_cursor_dataclass.yml        # TurnCursor(turn_id, timestamp_ms, session_id, version)
├── cursor_encoder.yml               # Encode/decode with HMAC SHA-256 signature
└── cursor_versioning.yml            # Support format evolution (v1, v2, etc.)
```

**Pagination REST API - ADR-0023b (4 files):**

```
├── turns_pagination_endpoint.yml    # GET /api/v1/sessions/{id}/turns?cursor=...&limit=50
├── pagination_response_format.yml   # {turns, next_cursor, has_more}
├── limit_validation.yml             # Enforce 1-100 limit, default 50
└── error_handling.yml               # Invalid cursor, not found, expired
```

**K0 WAL Query Optimization - ADR-0023c (3 files):**

```
├── k0_pagination_query.yml          # K0PaginationQuery class (cursor-based SQL)
├── composite_index_schema.sql       # CREATE INDEX idx_turns_session_timestamp
└── query_performance_metrics.yml    # Track query latency (<50ms P95)
```

---

## Epic 4.3: Performance & Resource Contracts

**ADR Source:** ADR-0024-0031
**Timeline:** Week 11-12 (10 days)
**Dependencies:** Milestone 1-3 (all prior contracts)

**Epic Summary:**

- **Total Contracts:** ~44 files across performance budgets, KV cache, and thermal management
- **Effort Estimate:** 9 days (3 days per issue for Issues 4.3.1-4.3.3, 1 day each for 4.3.4-4.3.5)
- **Key Deliverables:** 15 performance budgets + 16 KV cache contracts + 13 thermal contracts

### **Issues for Epic 4.3:**

#### **Issue 4.3.1: Performance Budget Contracts**

**Effort:** 3 days | **Source ADR:** `0024-performance-budgets-p95-targets.md` + sub-ADRs `0024a-d`

**Expected Output:** `contracts/performance/budgets/` (15 files)

**Turn-Level Performance Budgets - ADR-0024a (3 files):**

```
├── ttft_budget_tracker.yml          # TTFT <150ms P95 (ASR 80ms + Intent 50ms + Orchestrator 20ms)
├── e2e_turn_budget_tracker.yml      # E2E <2000ms P95 (composable budget breakdown)
└── barge_in_cancel_budget.yml       # Barge-in <120ms P95 (instant cancellation)
```

**Component-Level Performance Budgets - ADR-0024b (5 files):**

```
├── intent_classification_budget.yml # <50ms P95, 100ms timeout
├── orchestrator_3phase_budget.yml   # <250ms P95 (negotiation 100ms + selection 50ms + exec 100ms)
├── tool_call_budget.yml             # <3000ms P95, 10000ms timeout with partial results
├── config_reload_budget.yml         # <100ms P95, 200ms timeout (hot-reload YAML)
└── grounding_act_budget.yml         # <30ms P95, 100ms timeout (SessionState update)
```

**Memory Budgets & Resource Limits - ADR-0024c (3 files):**

```
├── sessionstate_size_limits.yml     # 64KB soft / 128KB hard / 256KB OOM (3-tier eviction)
├── kv_cache_global_budget.yml       # 512MB device-wide, 32MB min per session
└── k1_total_memory_budget.yml       # <500MB total (OS + all sessions), psutil monitoring
```

**Graceful Degradation & Budget Pressure - ADR-0024d (4 files):**

```
├── degradation_manager.yml          # GREEN/AMBER/RED/CRITICAL levels (adaptive policies)
├── amber_degradation_actions.yml    # Skip persona (saves 20ms), skip grounding (saves 12ms)
├── red_degradation_actions.yml      # Rule-based intent (saves 40ms), timeout tools at 2000ms
└── critical_degradation_actions.yml # Reject turns (503), cached responses, user notification
```

**Budget Enforcement & Monitoring (2 files):**

```
├── budget_enforcer.yml              # Deadline tracking, 80% utilization warnings
└── prometheus_budget_metrics.yml    # Histograms (P50/P95/P99), alerts (>105% of budget)
```

---

#### **Issue 4.3.2: KV Cache Management Contracts**

**Effort:** 3 days | **Source ADR:** `0025-kv-cache-management-512mb.md` + sub-ADRs `0025a-e`

**Expected Output:** `contracts/performance/kv_cache/` (16 files)

**Global KV Cache Allocator - ADR-0025a (1 file):**

```
└── global_allocator_512mb.yml       # GlobalKVCacheAllocator: 512MB global budget, per-session min 32MB/max 256MB
```

**LRU/LFU Hybrid Eviction - ADR-0025b (3 files):**

```
├── hybrid_eviction_policy.yml       # 60% recency (LRU) + 40% frequency (LFU) scoring
├── eviction_scoring_algorithm.yml   # eviction_score = 0.6*recency + 0.4*frequency
└── batch_eviction_strategy.yml      # Evict 2 sessions at a time (at 90% full = 460MB)
```

**Per-Session Allocation Policies - ADR-0025a continued (2 files):**

```
├── per_session_allocation.yml       # 32MB guaranteed, 128MB default, 256MB max
└── allocation_fragmentation.yml     # Contiguous memory blocks, <3% fragmentation target
```

**Cache Warming & Prefetch - ADR-0025c (2 files):**

```
├── cache_warmer_prefetch.yml        # Prefetch last 3 turns on session resume (<50ms)
└── resume_detection.yml             # Trigger warming if inactive >5 minutes
```

**zstd Compression for Inactive Caches - ADR-0025d (3 files):**

```
├── zstd_compressor_level3.yml       # zstd level 3 (70% reduction: 128MB → 38MB)
├── compression_trigger.yml          # Compress if inactive >10 minutes (<15ms latency)
└── decompression_on_demand.yml      # Decompress on session resume (<20ms latency)
```

**Protected Sessions & Hit Rate - ADR-0025e (2 files):**

```
├── protection_manager.yml           # Never evict: active conversation + safety monitoring
└── hit_rate_monitor.yml             # Track cache hit rate (target >75%), miss penalty tracking
```

**KV Cache Observability (2 files):**

```
├── kv_cache_metrics.yml             # Prometheus: allocated_mb, available_mb, fragmentation_%
└── eviction_rate_metrics.yml        # Track evictions_total, hit_rate_percent, miss_penalty_ms
```

**Memory Fragmentation Prevention (1 file):**

```
└── contiguous_allocation.yml        # Maintain contiguous blocks, defragmentation at <3% threshold
```

---

#### **Issue 4.3.3: Thermal & Placement Contracts**

**Effort:** 5 days | **Source ADR:** `0026-thermal-hysteresis-matrix.md` + `0027-model-placement-cascade.md` + sub-ADRs

**Expected Output:** `contracts/performance/thermal_placement/` (28 files)

**Thermal Sensor Monitoring - ADR-0026a (2 files):**

```
├── thermal_sensors_cross_platform.yml  # Linux thermal zones, Windows WMI, macOS IOKit
└── thermal_state_detection.yml         # 5 states: COOL <60°C, WARM 60-75°C, HOT 75-85°C, CRITICAL 85-95°C, EMERGENCY >95°C
```

**Hysteresis State Machine - ADR-0026b (3 files):**

```
├── hysteresis_fsm_5c_buffer.yml     # 5°C buffer (upgrade +5°C, downgrade -5°C = 10°C dead band)
├── state_transition_thresholds.yml  # WARM→HOT at 80°C, HOT→WARM at 70°C (asymmetric thresholds)
└── state_persistence_timer.yml      # Minimum 10s in state before transition (prevent flapping)
```

**Cooldown Periods - ADR-0026b continued (2 files):**

```
├── upgrade_cooldown_10s.yml         # 10s cooldown before upgrade (fast degradation)
└── downgrade_cooldown_30_60s.yml    # 30-60s cooldown before downgrade (slow recovery)
```

**Model Placement Integration - ADR-0026c (4 files):**

```
├── thermal_placement_manager.yml    # Thermal-aware accelerator selection
├── npu_placement_policy.yml         # NPU (30ms, 10W): COOL/WARM only
├── gpu_placement_policy.yml         # GPU (50ms, 12W): COOL/WARM/HOT only
└── cpu_remote_placement_policy.yml  # CPU (120ms, 15W): All states | Remote (500ms, 5W): EMERGENCY
```

**Emergency Jump & Flapping Prevention - ADR-0026c continued (1 file):**

```
└── emergency_jump_handler.yml       # Critical ≥85°C → immediate Remote (skip intermediate tiers)
```

**User Notifications - ADR-0026d (1 file):**

```
└── thermal_user_notifications.yml   # EMERGENCY: "Device cooling down..." | Recovery: "Device ready"
```

**Model Placement Algorithm - ADR-0027 + ADR-0027a (4 files):**

```
├── placement_cascade_npu_gpu_cpu_remote.yml  # 4-tier cascade: NPU (140ms, 5-8W) → GPU (180ms, 15-25W) → CPU (350ms, 3-10W) → Remote (600ms, 0W, $0.002/token)
├── thermal_cascade_integration.yml           # COOL/WARM→NPU/GPU, HOT→GPU/CPU/Remote, CRITICAL→CPU/Remote, EMERGENCY→Remote only
├── capability_matching_accelerator.yml       # Match model requirements (quantization, memory, features) to accelerator capabilities
└── accelerator_profile_manager.yml           # NPU/GPU/CPU/Remote profiles with latency/power/cost/thermal characteristics
```

**Automatic Failover - ADR-0027b (4 files):**

```
├── failover_manager_100ms_budget.yml         # <100ms total: detection 15ms + KV transfer 25ms + model load 45ms + resume 8ms
├── kv_cache_transfer_pinned_memory.yml       # Pinned memory for fast transfers: 2GB/s NPU→GPU, 8GB/s GPU→CPU
├── checkpoint_serialization_inference.yml    # Save inference state: KV cache, position, hidden states for resume
└── resume_logic_after_failover.yml           # Resume generation from checkpoint without re-running prefix
```

**Cost-Aware Fallback - ADR-0027c (4 files):**

```
├── cost_tracker_per_token.yml                # Track cost per token: $0.000002/token target for remote API ($2 per 1M tokens)
├── budget_state_machine_4_tiers.yml          # UNDER_BUDGET <$0.05, APPROACHING $0.05-$0.10, SOFT_LIMIT $0.10-$0.20, HARD_LIMIT ≥$0.20
├── per_token_cost_tracking.yml               # Accumulate cost per turn: 50 tokens × $0.000002 = $0.0001
└── placement_modifier_budget_aware.yml       # HARD_LIMIT excludes Remote, SOFT_LIMIT deprioritizes Remote, prefer local accelerators
```

**Remote Resilience - ADR-0027d (3 files):**

```
├── remote_resilient_client_retry.yml         # 3 retries with exponential backoff: 1s, 2s, 4s delays, 10s timeout per request
├── circuit_breaker_state_machine.yml         # Open after 5 consecutive failures, half-open after 60s, test with single request
└── retry_logic_exponential_backoff.yml       # Transient errors retry (timeout, 5xx, rate limit), permanent errors fail (4xx, auth)
```

---

#### **Issue 4.3.4: WFQ Scheduler Contracts**

**Effort:** 2 days | **Source ADR:** `0028-weighted-fair-queuing-scheduler.md` + sub-ADRs `0028a-c`

**Expected Output:** `contracts/performance/scheduler/` (10 files)

**WFQ Algorithm & Virtual Time - ADR-0028 + ADR-0028a (3 files):**

```
├── wfq_scheduler_virtual_time.yml             # Virtual time formula: vtime_finish = vtime_start + (turn_cost_ms / weight)
├── virtual_time_tracker_per_session.yml       # Track virtual time per session, proportional CPU allocation (URGENT:REALTIME:INTERACTIVE:BACKGROUND = 10:5:3:1)
└── session_scheduling_state_min_heap.yml      # Min-heap O(log n) selection: schedule session with smallest virtual finish time
```

**Priority Classes & Preemption - ADR-0028 + ADR-0028b (3 files):**

```
├── priority_manager_4_classes.yml             # URGENT (weight 10, ≤50ms), REALTIME (weight 5, ≤150ms), INTERACTIVE (weight 3, ≤300ms), BACKGROUND (weight 1, ≤5000ms)
├── preemption_checkpoint_kv_cache.yml         # Preemption flow: save KV cache (1-10ms), interrupt inference, run high priority, resume preempted
└── resume_from_checkpoint_inference.yml       # Resume preempted session: restore KV cache, position, hidden states, continue generation
```

**Starvation Prevention - ADR-0028c (2 files):**

```
├── age_boost_calculator_10pct_per_sec.yml     # Age boost formula: effective_weight = base_weight × (1 + 0.1 × wait_seconds)
└── forced_scheduling_500ms_threshold.yml      # Force-schedule BACKGROUND if starved >500ms (URGENT >50ms, REALTIME >150ms, INTERACTIVE >300ms)
```

**Scheduler Observability - ADR-0028 + ADR-0029c (2 files):**

```
├── queue_depth_metrics_active_tasks.yml       # Gauge: orchestrator_active_tasks (currently executing tasks per priority class)
└── wait_time_histogram_p50_p95_p99.yml        # Histogram: session_wait_time_ms (latency from task announcement to execution start)
```

---

#### **Issue 4.3.5: Cost Tracking Contracts**

**Effort:** 3 days | **Source ADR:** `0031-cost-tracking-per-session.md` + sub-ADRs `0031a-d`

**Expected Output:** `contracts/performance/cost/` (16 files)

**Hierarchical Budget Enforcement - ADR-0031a (6 files):**

```
├── session_budget_enforcement_10_cents.yml     # Session budget: $0.10 default per conversation, alert at 50%/80%/95%, block at 100%
├── user_daily_budget_enforcement_5_usd.yml     # User daily budget: $5.00 per user per day, auto-reset at midnight UTC, aggregate session costs
├── department_monthly_budget_5k_usd.yml        # Department monthly budget: $5,000 default per department, alert finance at 80%/95%, chargeback reports
├── budget_override_power_users.yml             # Power user overrides: Research leads $20/day, demo accounts $1/day, approved by IT admin
├── budget_violation_enforcement.yml            # Violation handling: Block remote LLM at 100%, fallback to on-device, notify user with reset time
└── hierarchical_budget_aggregation.yml         # Budget rollup: Session → User Daily → Department Monthly, <5ms aggregation, audit trail to K0
```

**Cost Model & Pricing - ADR-0031b (4 files):**

```
├── token_cost_calculator_per_model.yml         # Token costs: GPT-4o ($0.005/$0.015 input/output per 1K), Claude ($0.003/$0.015), Gemini ($0.00125/$0.005), local models ($0.0001/$0.0002)
├── tool_cost_calculator_per_call.yml           # Tool costs: web_search ($0.002/call), image_generation ($0.04/image), web_scraping ($0.001/page), local tools ($0)
├── compute_cost_calculator_hardware.yml        # Compute costs: NPU ($0.00001/sec), GPU ($0.00005/sec), CPU ($0.000001/sec) - hardware amortization
└── pricing_config_hot_reload.yml               # Pricing updates: Monthly provider rate changes, volume discounts (10% at $10K/month), <100ms hot-reload without restart
```

**Automatic Cost Fallback - ADR-0031c (3 files):**

```
├── fallback_tier_state_machine.yml             # 4 fallback tiers: NORMAL (0-50%, continue), WARNING (50-80%, notify), COST_OPTIMIZED (80-95%, cheaper models), LOCAL_ONLY (95-100%, on-device only)
├── cheaper_model_alternatives.yml              # Model downgrades: GPT-4o → GPT-4o-mini (97% cheaper), Claude-3.5-Sonnet → Claude-3-Haiku (90% cheaper), Gemini-1.5-Pro → Gemini-1.5-Flash (80% cheaper)
└── intent_based_local_model_selection.yml      # Local model routing: code_generation → Gemma-2-9B, qa → Phi-3-Mini, summarization → Gemma-2-9B, general → Gemma-2-9B
```

**Cost Observability - ADR-0031d (3 files):**

```
├── cost_prometheus_metrics.yml                 # Prometheus metrics: cost_total_usd (counter), cost_per_turn_usd (histogram buckets [0.001,0.005,0.01,0.02,0.05,0.1,0.2,0.5,1.0]), budget_utilization_ratio (gauge 0.0-1.0), budget_remaining_usd (gauge), fallback_events_total (counter), budget_violations_total (counter)
├── cost_grafana_dashboards.yml                 # Grafana dashboards: IT Admin (real-time budget monitoring, anomaly detection), Finance (MTD spending by department, forecast Q4), Compliance (audit trails, SOC2/ISO27001 reports), Manager (team usage, cost optimization tips)
└── cost_audit_trail_7_years.yml                # Compliance-grade audit trail: 7-year retention (ISO27001/SOC2), immutable append-only logs, full cost attribution (department/user/model/tool), exportable reports for finance chargeback
```

---

## Epic 4.4: Observability Contracts

**ADR Source:** ADR-0029, ADR-0030
**Timeline:** Week 12 (5 days)
**Dependencies:** All prior epics (observability spans all)

### **Issues for Epic 4.4:**

#### **Issue 4.4.1: Prometheus Metrics Contracts (RED Method)**

**Effort:** 4 days | **Source ADR:** `0029-prometheus-metrics-red-method.md` + sub-ADRs `0029a-e`

**Expected Output:** `contracts/observability/metrics/` (25 files)

**RED Method Schema - ADR-0029a (4 files):**

```
├── metric_schema_validator_naming.yml         # Metric naming convention: k1_<component>_<metric>_<unit> (e.g., k1_turn_ttft_ms)
├── naming_convention_enforcer.yml             # Enforce metric types: Counter (rate/errors), Histogram (duration), Gauge (current state)
├── cardinality_limiter_1000_series.yml        # Max 1000 unique time series per metric, label standards: Required (component), Forbidden (user_id, trace_id)
└── histogram_bucket_optimizer_latency.yml     # Histogram buckets: Latency [10,50,100,250,500,1000,2000,5000ms], Cost [0.01,0.05,0.10,0.20,0.50,1.0], Size [1,10,50,100,256,512,1024MB]
```

**Turn-Level Metrics - ADR-0029b (5 files):**

```
├── ttft_tracker_150ms_p95_budget.yml          # TTFT histogram: 150ms P95 budget = ASR 50ms + Intent 50ms + Orchestration 50ms
├── e2e_latency_tracker_2000ms_p95.yml         # E2E histogram: 2000ms P95 budget = TTFT 150ms + LLM Generation 1650ms + TTS 200ms
├── barge_in_latency_tracker_120ms_p95.yml     # Barge-in histogram: 120ms P95 budget = VAD Detection 50ms + Signal Propagation 20ms + TTS Stop 50ms
├── error_classifier_8_types.yml               # Error counter: 8 types (timeout, validation, tool_error, agent_crash, orchestration_timeout, planner_validation, asr_error, tts_error)
└── phase_breakdown_metrics_debug.yml          # Phase metrics: ASR latency, intent classification, orchestration, LLM generation, TTS synthesis (for debugging bottlenecks)
```

**Component Metrics - ADR-0029c (5 files):**

```
├── agent_metrics_6_core.yml                   # 6 agent metrics: transitions_total, crashes_total, hiring_latency_ms, active_agents, blacklisted_agents, supervisor_checks_total
├── orchestrator_metrics_7_core.yml            # 7 orchestrator metrics: tasks_total, 3phase_latency_ms, negotiation_rounds, selection_latency_ms, execution_latency_ms, timeouts_total, active_tasks
├── planner_metrics_5_core.yml                 # 5 planner metrics: plans_total, validation_failures_total, planning_latency_ms, arbiter_approvals_total, fallbacks_total
├── tool_metrics_5_core.yml                    # 5 tool metrics: executions_total, execution_ms, errors_total, timeouts_total, active_executions
└── k0_bridge_metrics_batch.yml                # K0 bridge metrics: batch_latency_ms, batch_size (receipt streaming optimization)
```

**Infrastructure Metrics - ADR-0029d (5 files):**

```
├── kv_cache_metrics_5_core.yml                # 5 KV cache metrics: hit_rate (0.0-1.0, target >0.75), size_mb (budget 128MB), evictions_total (LRU), entries, access_latency_ms (hit <1ms, miss <10ms)
├── thermal_metrics_4_core.yml                 # 4 thermal metrics: state (0=COOL, 1=WARM, 2=HOT, 3=CRITICAL, 4=EMERGENCY), temperature_celsius (NPU/GPU/CPU), throttling_events_total, placement_decisions_total
├── memory_metrics_3_core.yml                  # 3 memory metrics: session_state_size_kb (budget 64KB), k1_memory_total_mb (budget 500MB), session_state_evictions_total (temporal/popularity/size)
├── cpu_metrics_utilization.yml                # 1 CPU metric: utilization_percent (budget 90%)
└── cost_metrics_budget_tracking.yml           # 2 cost metrics: cost_per_turn_usd (budget $0.10 soft), cost_budget_exceeded_total (>$0.20 hard limit)
```

**Alerting & Dashboards - ADR-0029e (6 files):**

```
├── slo_alert_rules_10_groups.yml              # 10 alert rule groups: Turn (TTFT, E2E, error rate, availability), Agent (hiring latency, crash rate, blacklist), Orchestrator (3-phase latency, timeout rate), Planner (validation failures, arbiter approvals), Tool (execution latency, timeout rate), KV Cache (hit rate, size, eviction rate), Thermal (throttling events, emergency state), Memory (SessionState size, K1 total memory), Cost (per-turn budget, monthly burn rate), Synthetic Monitoring (synthetic turn success rate, synthetic TTFT)
├── grafana_turn_overview_dashboard_12_panels.yml   # Grafana Turn Overview: 12 panels (TTFT histogram, E2E histogram, error rate graph, success rate gauge, barge-in latency, active turns, phase breakdown, error types breakdown, timeout stages, asr/intent/llm/tts latency, turn throughput)
├── grafana_component_health_dashboard_18_panels.yml # Grafana Component Health: 18 panels (agent states pie chart, agent transitions timeline, agent crash rate, agent hiring latency, orchestrator 3-phase breakdown, negotiation rounds histogram, selection latency, execution latency, planner validation failures, arbiter approval rate, tool execution latency, tool timeout rate, k0 bridge batch latency, k0 bridge batch size, component error rates, component throughput)
├── grafana_infrastructure_dashboard_15_panels.yml  # Grafana Infrastructure: 15 panels (KV cache hit rate gauge, KV cache size gauge, KV cache eviction rate, thermal state timeline, NPU/GPU/CPU temperature graphs, thermal throttling events, placement decisions pie chart, SessionState size per session, K1 memory total gauge, memory eviction rate, CPU utilization graph, cost per turn histogram, cost budget alerts, thermal placement cascade visualization)
├── grafana_incident_response_dashboard_5_panels.yml # Grafana Incident Response: 5 panels (active alerts list, recent traces with errors, error log stream, runbook links by alert type, incident timeline with annotations)
└── alertmanager_config_routing_escalation.yml      # Alertmanager config: routing to PagerDuty (critical, immediate on-call) and Slack #k1-alerts (warning, 30min async), escalation policies (15min → manager, 1hr warning → critical)
```

---

#### **Issue 4.4.2: Intelligent Trace Sampling Contracts**

**Effort:** 3 days | **Source ADR:** `0030-intelligent-trace-sampling.md` + sub-ADRs `0030a-d`

**Expected Output:** `contracts/observability/tracing/` (13 files)

**Head-Based Sampling Strategy - ADR-0030a (4 files):**

```
├── head_based_sampler_decision_logic.yml       # Sampling rules (priority order): 1. Errors (100%), 2. High latency (TTFT >150ms OR E2E >2000ms = 100%), 3. RED band (100%), 4. Backpressure Tier 1+ (100%), 5. Baseline (1% hash-based)
├── w3c_trace_context_propagation.yml           # W3C Trace Context format: {version}-{trace-id}-{parent-id}-{trace-flags}, traceparent header injection <0.5ms, cognitive_trace_id as trace-id (128-bit UUID)
├── sampling_context_builder.yml                # Sampling context: trace_id, turn_status, ttft_ms, e2e_latency_ms, privacy_band, backpressure_tier, session_id, intent - captured at turn start
└── hash_based_baseline_sampling_1pct.yml       # Deterministic hash-based sampling: SHA256(trace_id) mod 100 < 1 → sample, consistent across services (same trace_id always makes same decision)
```

**Tail-Based Sampling & Span Buffering - ADR-0030b (3 files):**

```
├── tail_sampling_coordinator.yml               # Tail-based decision after turn completion: Evaluate final context (status, latency, privacy band), decide KEEP (export to Jaeger) or DISCARD (drop from buffer), <100ms decision latency
├── span_buffer_management_60s.yml              # Span buffer: 60s retention, <50MB memory budget (10,000 turns × 50 spans × 100 bytes avg = 2.1MB peak × 10x headroom), BatchSpanProcessor integration
└── turn_completion_context_evaluator.yml       # Completion context: trace_id, session_id, turn_status, ttft_ms, e2e_latency_ms, privacy_band, slo_violated, error_message, intent - available at turn end
```

**Adaptive Sampling Rate Adjustment - ADR-0030c (3 files):**

```
├── adaptive_sampling_fsm_3_states.yml          # Adaptive FSM: NORMAL (1% baseline) → DEGRADATION (10% baseline, TTFT >157ms 5s OR error >1%) → CRITICAL (50% baseline, TTFT >210ms 10s OR error >5% OR backpressure Tier 2+)
├── health_indicator_monitoring.yml             # Health checks every 5s: Query Prometheus for TTFT P95, error rate, backpressure tier, upgrade if sustained degradation, downgrade after 60s recovery
└── hysteresis_margin_10pct.yml                 # Hysteresis (prevent oscillation): Upgrade NORMAL→DEGRADATION at 157ms, downgrade at 141ms (10% margin), upgrade DEGRADATION→CRITICAL at 210ms, downgrade at 189ms (10% margin)
```

**Trace Storage & Jaeger Integration - ADR-0030d (3 files):**

```
├── jaeger_otlp_exporter_grpc.yml               # OTLP exporter: gRPC endpoint localhost:4317, batch 512 spans, 5s timeout, resource attributes (service.name, service.version, deployment.environment, k1.kernel)
├── jaeger_badger_storage_retention.yml         # Badger storage backend: Hot storage 7 days (all sampled traces), warm storage 30 days (errors/critical only), embedded key-value store (no external DB), TTL-based eviction, maintenance every 1h
└── jaeger_query_api_client.yml                 # Query API client: REST API (GET /api/traces?service=k1&tag=error:true), gRPC API (FindTraces(query)), trace search by trace_id/session_id/error/latency, <500ms query response
```

---

#### **Issue 4.4.3: Receipt & Audit Trail Contracts**

**Effort:** 1 day | **Source ADR:** `0038-audit-trail-to-k0-receipts.md`

**Expected Output:** `contracts/observability/receipts/`

```
├── receipt_generation.yml           # Schema (ADR-0038a)
├── k0_wal_integration_async.yml     # Async writes (ADR-0038b)
├── retention_policies.yml           # Auto-deletion (ADR-0038c)
├── query_interface_compliance.yml   # Export (ADR-0038d)
└── receipt_signatures.yml           # ED25519 signing
```

---

## 📝 Contract Testing & Validation

### **Testing Infrastructure (All Milestones)**

**Location:** `contracts/testing/`

#### **Issue T.1: Contract Testing Framework**

**Effort:** 3 days | **Source ADR:** `0013d-contract-testing-compatibility-validation.md`

**Expected Output:** `contracts/testing/`

```
├── consumer_contracts/              # Consumer-driven contract tests (Pact-style)
├── provider_contracts/              # Provider contract validation
├── compatibility_matrix/            # Multi-version compatibility (228-380 tests)
├── schema_validation/               # FlatBuffers schema validation
├── protocol_validation/             # MPST protocol validation
└── ci_cd_integration/               # GitHub Actions workflows
```

**Key Testing Components:**

1. **Schema Validation:** FlatBuffers compiler validation, JSON Schema validation
2. **Protocol Validation:** PDL → FSM compilation, state transition validation
3. **Contract Tests:** Consumer-driven tests between K1 components and K0
4. **Compatibility Matrix:** Forward/backward compatibility testing
5. **CI/CD Integration:** Pre-commit hooks, PR validation, breaking change detection

---

## 📊 Final Deliverables Checklist

### **Milestone 1: Foundation (Weeks 1-3)**

- [ ] 20 K0 Bridge port contracts (P01-P20)
- [ ] Actor Model mailbox/supervisor/router contracts
- [ ] 6 MPST protocol definitions (PDL)
- [ ] 52-module architecture manifest

### **Milestone 2: Agent & Orchestration (Weeks 4-6)**

- [ ] Agent lifecycle FSM (6 states)
- [ ] Orchestration 3-phase contracts
- [ ] Planning pipeline (4 stages)
- [ ] Saga & circuit breaker contracts
- [ ] Capability-based security contracts (unforgeable tokens, HMAC-SHA256)

### **Milestone 3: Serialization & API (Weeks 7-9)**

- [ ] 76 FlatBuffers schemas (5 layers)
- [ ] REST API OpenAPI 3.1 specs
- [ ] WebSocket binary protocol
- [ ] SSE event schemas (17 types)

### **Milestone 4: State & Performance (Weeks 10-12)**

- [ ] SessionState 6-section structure
- [ ] Multi-tier storage contracts
- [ ] Performance budgets (P95 targets)
- [ ] Observability contracts (Prometheus, OpenTelemetry)

### **Testing & Validation (All Milestones)**

- [ ] Contract testing framework
- [ ] Compatibility matrix (228-380 tests)
- [ ] CI/CD integration
- [ ] Breaking change detection

---

## 🎓 Contract Development Guidelines

### **For AI Coders:**

1. **Start with ADR:** Always read source ADR first (file path provided in each issue)
2. **Follow Template:** Use YAML schema templates from Milestone 1 examples
3. **Complete Structure:** Include all sections: name, description, fields, validation, observability, related ADRs
4. **Reference Context:** Link to source ADR sections with line numbers
5. **Add Examples:** Include usage examples where helpful
6. **Validation:** Ensure schemas are valid (FlatBuffers compile, YAML parse, JSON Schema validate)
7. **Traceability:** Maintain links between contracts and ADRs
8. **Incremental:** Complete issues in order (dependencies listed)

### **Key Principles:**

- **One Issue = One Contract Domain** (don't combine unrelated contracts)
- **Complete Before Moving On** (finish issue before starting next)
- **Test As You Go** (validate schemas, run contract tests)
- **Document Assumptions** (add comments for unclear cases)
- **Ask If Stuck** (reference ADR for clarification)

---

## 📌 Quick Reference

**Contract Categories:** 22 total
**Contract Files:** ~220 total (expanded from 150 after comprehensive ADR 0001-0015 review)
**FlatBuffers Schemas:** 76 total (Layer 1: 15, Layer 2: 18, Layer 3: 16, Layer 4: 14, Layer 5: 13)
**Protocol Definitions:** 6 core protocols (PDL YAML) + 6 detailed FSM contracts
**K0 Pipelines:** 20 pipelines (P01-P20) with 3 contracts each (request, response, schema/receipt) = 60 files
**API Specifications:** REST (OpenAPI 3.1), WebSocket (17 message types), SSE (17 event types)
**Timeline:** 12 weeks (3 months)

**Priority Order:**

1. K0 Bridge ports (P01-P20) - critical for K1↔K0 communication
2. Actor Model mailbox - critical for all component messaging
3. MPST protocols - critical for agent coordination
4. FlatBuffers schemas - critical for serialization
5. K0 pipeline contracts (P01-P20 detailed) - critical for memory, learning, content analysis
6. Everything else builds on these foundations

---

## 📝 Update Log

### **2025-10-13: Comprehensive ADR 0001-0015 Review & Plan Expansion**

**Changes Made:**

1. **Executive Summary Updated:**
   - Contract files: 150 → **220 files** (+70 files, +47% increase)
   - Epics: 18 → **24 epics** (+6 epics)
   - Added coverage summary mapping all ADRs 0001-0015 to epics

2. **Epic 2.6 Added: MPST Protocol Detailed Contracts (54 files)**
   - Agent Hire Protocol (9 contracts): FSM, hire request/response, warmup, activation, idle detection, drain, termination, crash handling, timeouts
   - Task Execution Protocol (10 contracts): FSM, task announcement, proposal, selection, assignment, progress monitoring, completion, failure handling
   - Clarification Protocol (6 contracts): FSM, clarification request/response, timeout handling, priority levels, WebSocket delivery
   - Barge-In Protocol (6 contracts): FSM, barge-in signal, interrupt propagation, drain, resume, latency target (<120ms)
   - Tool Call Protocol (9 contracts): FSM, tool call request, approval workflow, execution, result, failure handling, capability enforcement
   - Saga Rollback Protocol (8 contracts): FSM, saga definition, compensation request/response, rollback strategies, idempotency
   - **Why Added:** ADR-0003 (MPST Protocol Validation) specifies 6 protocols with full FSM state machines. Previous plan only had PDL definitions (Epic 1.3) but lacked detailed FSM contracts for each protocol.

3. **Epic 3.3 Added: K0 Pipeline Contracts P01-P20 (60 files)**
   - Memory Pipelines P01-P05 (15 contracts): Recall, Memory Formation, Entity Extraction, Relation Linking, Contradiction Detection
   - Learning Pipelines P06-P08 (9 contracts): Learning Tick, Sync (K1→K0), Preference Learning
   - Content Analysis Pipelines P09-P12 (12 contracts): Sentiment Analysis, PII Detection, Moderation, Policy Evaluation
   - Transformation Pipelines P13-P16 (12 contracts): Summarization, Translation, Embedding Generation, Vector Search
   - Operational Pipelines P17-P20 (12 contracts): Resource Allocation, Cost Tracking, Audit Logging, Analytics
   - Each pipeline: 3 contracts (request FlatBuffers, response FlatBuffers, schema/receipt YAML) = 20 × 3 = 60 files
   - **Why Added:** ADR-0001 (K0/K1 Kernel Split) defines 20 K0 pipelines. Previous plan mentioned P01-P20 in Epic 1.1 (port definitions) but lacked detailed request/response/receipt contracts for each pipeline's business logic.

4. **Milestone 3 Epic 3.1 Expanded: FlatBuffers Schemas (76 schemas)**
   - Issue 3.1.1: Base Type Schemas (5 files) - common.fbs, trace.fbs, budget.fbs, error.fbs, version.fbs
   - Issue 3.1.2: Layer 1 Core Kernel Schemas (15 files) - Agent Fabric (5), Orchestrator (4), Planner (3), Protocol Monitor (2), Learning Loop (1)
   - Issue 3.1.3: Layer 2 State & Persistence Schemas (18 files) - SessionState (6), Memory Manager (5), Receipt System (4), K0 Bridge (3)
   - Issue 3.1.4: Layer 3 Execution & Tools Schemas (16 files) - Tool Runner (5), Model Hub (7), MCP Gateway (2), Streaming Engine (2)
   - Issue 3.1.5: Layer 4 Ingress & Voice Schemas (14 files) - API Gateway (3), WebSocket (7), Voice Pipeline (4)
   - Issue 3.1.6: Layer 5 Infrastructure Schemas (13 files) - Config Manager (2), Observability (5), Thermal Manager (2), Backpressure (2), Scheduler (2)
   - **Why Expanded:** ADR-0012 (76 FlatBuffers Schemas) provides complete taxonomy with 9 categories and layer-by-layer breakdown. Previous plan listed schemas generically; now each layer has detailed file structure from ADR-0012a-e.

5. **ADR Context Gathered (ADRs 0001-0015):**
   - **ADR-0011 (FlatBuffers):** Zero-copy serialization, <1ms target, 150x faster than JSON (complete)
   - **ADR-0012 (76 Schemas):** 9 categories, shared base types, schema design patterns (complete)
   - **ADR-0013 (Versioning):** Semantic versioning (MAJOR.MINOR.PATCH), 90-day deprecation windows, schema registry (partial, 501 lines)
   - **ADR-0014 (REST API):** Dual format (JSON default + FlatBuffers optional), content negotiation, OpenAPI 3.1 generation (partial, 501 lines)
   - **ADR-0015 (WebSocket):** FlatBuffers binary protocol, 17 message types, 5-10x faster than JSON, flow control, reconnection (complete, 1453 lines)
   - **ADR-0015a (Message Envelope):** 32-byte envelope overhead, hash table routing <1ms, sequence tracking (partial, 401 lines)

**Files Modified:**

- `contracts/CONTRACT_DEVELOPMENT_PLAN.md` (2314 lines → 2655 lines → 2825 lines, total +511 lines from initial, +22% expansion)

**Latest Update (ADRs 0016-0017 Batch):**

6. **Epic 3.2.3 Expanded: SSE Event Schemas (25 files, +22 from previous 3 files)**
   - Event Envelope & Common (2 files): EventEnvelope root table, EventMetadata with SchemaVersion
   - Agent Lifecycle Events (4 FlatBuffers): AgentHired, AgentFired, AgentCrashed, AgentRestarted
   - Turn Execution Events (4 FlatBuffers): TurnStarted, TurnCompleted, TurnFailed, TurnInterrupted
   - Tool Execution Events (4 FlatBuffers): ToolCallStarted, ToolCallCompleted, ToolCallFailed, ToolApprovalRequired
   - Session Lifecycle Events (3 FlatBuffers): SessionCreated, SessionTerminated, SessionCrashed
   - System Events (2 FlatBuffers): Heartbeat, Error
   - Serialization & Filtering (5 YAML): FlatBuffers→JSON serializer (PascalCase→snake_case, <2ms P95), topic filter (5 topics, O(1) membership), subscription API, SSE formatter, browser EventSource integration
   - Event Type Enumeration (1 file): EventType enum, category mapping
   - **Why Expanded:** ADR-0016a shows 17 individual FlatBuffers schemas (not just 1 combined schema), ADR-0016b requires serialization contract, ADR-0016c requires 5 topic filters, ADR-0016d requires browser SDK contract. Previous plan had only 3 generic files.

7. **Epic 4.1.1 Expanded: SessionState 6-Section Structure (21 files, +14 from previous 7 files)**
   - Beliefs Section (ADR-0017a) - 4 files: schema (Fact table with key/value/confidence/source/timestamps), manager (add_fact/get_fact operations), LRU eviction (least recently accessed, 10-20KB target), K0 serialization (<10ms P95)
   - Scoreboard Section (ADR-0017b) - 4 files: schema (Entity/Referent/QUD tables), manager (add_entity/resolve_referent/push_qud), salience decay (exponential decay salience *= 0.9), referent resolution (pronoun→entity mapping)
   - Control Section (ADR-0017c) - 4 files: schema (AgentLease/FlowState tables), manager (acquire_lease/release_lease/set_flow_state), lease timeout (expired lease detection, periodic scan), flow FSM (3-phase: negotiation→selection→execution→idle)
   - Persona Section (ADR-0017d) - 3 files: schema (PersonaTrait table trait_name/trait_value/confidence), manager (set_trait/get_trait operations), LLM formatter (format traits for system prompt, <5ms P95)
   - Multimodal Section (ADR-0017e) - 3 files: schema (AudioBuffer/VisionEmbedding with K0 blob pointers), manager (add_audio_buffer/add_vision_embedding), LRU eviction (evict old buffers/embeddings, 4-8KB target)
   - Meta Section (ADR-0017f) - 3 files: schema (PerformanceMetrics with avg_ttft_ms/avg_e2e_latency_ms/counters), manager (increment_turn_counter/record_ttft/record_e2e_latency), telemetry collection (incremental averages, Prometheus export)
   - **Why Expanded:** Each sub-ADR (0017a-f) provides detailed implementation for each section. Previous plan had only 1 generic YAML per section (7 files total). Each section needs: FlatBuffers schema + manager implementation + eviction/logic contract + serialization contract (3-4 files per section × 6 sections = 21 files).

**Next Steps:**

- Continue reading ADRs 0018-0031 in next batches (4-5 ADRs per batch)
- Add Milestone 5 if needed after reviewing remaining ADRs (observability, tooling, testing)
- Update plan with any additional missing contracts from ADRs 0018-0031

**Coverage Validation:**

- ✅ ADR-0001 (K0/K1 Split): Epic 1.1 (20 ports) + Epic 3.3 (20 pipelines) = **COMPLETE**
- ✅ ADR-0002 (Actor Model): Epic 1.2 (mailbox, supervisor, router) = **COMPLETE**
- ✅ ADR-0003 (MPST Protocols): Epic 1.3 (6 PDL) + Epic 2.6 (6 FSMs) = **COMPLETE**
- ✅ ADR-0004 (52 Modules): Epic 1.4 (module manifests) = **COMPLETE**
- ✅ ADR-0005 (Agent Lifecycle): Epic 2.1 (6-state FSM) = **COMPLETE**
- ✅ ADR-0006 (Orchestration): Epic 2.2 (3-phase) = **COMPLETE**
- ✅ ADR-0007 (Planning): Epic 2.3 (4-stage) = **COMPLETE**
- ✅ ADR-0008 (Circuit Breaker) + ADR-0009 (Saga): Epic 2.4 (error recovery) = **COMPLETE**
- ✅ ADR-0010 (Capability Security): Epic 2.5 (capability contracts) = **COMPLETE**
- ✅ ADR-0011 (FlatBuffers) + ADR-0012 (76 Schemas): Epic 3.1 (5 layers) = **COMPLETE**
- ✅ ADR-0013 (Versioning): Epic 3.2.4 (schema registry) = **COMPLETE**
- ✅ ADR-0014 (REST API): Epic 3.2.1 (dual format) = **COMPLETE**
- ✅ ADR-0015 (WebSocket): Epic 3.2.2 (binary protocol) = **COMPLETE**
- ✅ ADR-0016 (SSE Events): Epic 3.2.3 (17 event schemas, expanded to 25 files) = **COMPLETE**
- ✅ ADR-0017 (SessionState 6-Section): Epic 4.1.1 (6 sections, expanded to 21 files) = **COMPLETE**
- ✅ ADR-0008 (Circuit Breaker): Epic 2.4 (error recovery) = **COMPLETE**
- ✅ ADR-0009 (Saga Pattern): Epic 2.4 (error recovery) = **COMPLETE**
- ✅ ADR-0010 (Capability Security): Epic 2.5 (27 contracts) = **COMPLETE**
- ✅ ADR-0011 (FlatBuffers): Epic 3.1 Issue 3.1.1-3.1.6 (76 schemas) = **COMPLETE**
- ✅ ADR-0012 (76 Schemas): Epic 3.1 Issue 3.1.1-3.1.6 (layer breakdown) = **COMPLETE**
- ✅ ADR-0013 (Versioning): Epic 3.2 Issue 3.2.4 (schema registry) = **COMPLETE**
- ✅ ADR-0014 (REST API): Epic 3.2 Issue 3.2.1 (dual format) = **COMPLETE**
- ✅ ADR-0015 (WebSocket): Epic 3.2 Issue 3.2.2 (17 message types) = **COMPLETE**

**All ADRs 0001-0015 now have comprehensive contract coverage!**

---

**END OF CONTRACT DEVELOPMENT PLAN**
