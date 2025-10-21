# DEPENDENCY_MAP Population Plan - Batch-by-Batch Approach

**Status:** 🚧 IN PROGRESS - Batch 1 Starting
**Last Updated:** 2025-10-17
**Owner:** K1 Architecture Team
**Target Completion:** 12 weeks (3 batches, 4 weeks each)

---

## Overview

This document provides a **sequential, batch-by-batch plan** to populate `DEPENDENCY_MAP.md` with complete ADR decision logic mappings, starting from foundational layers and building upward.

### Key Principles

1. **Batch-by-batch approach:** Each batch is independent, testable, and deliverable
2. **ADR-first:** Every decision references concrete ADR(s) with decision rationale
3. **Cross-reference validation:** All ADR → Module → Feature mappings verified
4. **Dependency ordering:** Later batches depend on earlier batches being complete
5. **Gate criteria:** Each batch must pass verification before next batch starts

---

## Batch Structure

```
BATCH 1 (Weeks 1-4): Foundation & Layer 5 (Infrastructure)
├─ Week 1: ADR indexing + infrastructure modules
├─ Week 2: Event bus + scheduling core
├─ Week 3: Safety & observability framework
├─ Week 4: K0 bridge + validation
└─ Gate: Layer 5 complete + all infrastructure ADRs mapped

BATCH 2 (Weeks 5-8): Core Layers (Layers 2, 3, 4)
├─ Week 5: Layer 4 (Runtime Core) + SessionState
├─ Week 6: Layer 3 Execution (Agents, Model Hub)
├─ Week 7: Layer 3 Execution (Tools, Dialogue) + Layer 2 Orchestration
├─ Week 8: Cross-layer patterns + validation
└─ Gate: Layers 2-4 complete + orchestration flows mapped

BATCH 3 (Weeks 9-12): Input & Integration (Layers 1 + External Systems)
├─ Week 9: Layer 1 (Input Processing) + voice pipeline
├─ Week 10: External systems + port mappings
├─ Week 11: Performance critical paths + tracing
├─ Week 12: Final validation + roadmap consolidation
└─ Gate: All layers mapped + performance budgets validated + ready for coding
```

---

# BATCH 1: Foundation & Layer 5 (Infrastructure)

## Batch 1 Objectives

- ✅ Create ADR Master Index (all ADRs, sub-ADRs, relationships)
- ✅ Map all 19 Layer 5 infrastructure modules to ADRs
- ✅ Detail event_bus (ADR-0004a) backbone
- ✅ Document K0 bridge integration points
- ✅ Establish cross-reference validation framework
- ✅ Gate verification (no TBD references remain in Layer 5)

---

## Batch 1 Deliverables

### 1.1: ADR_MASTER_INDEX.csv

**Purpose:** Single source of truth for all ADRs and sub-ADRs

**Location:** `docs/plan/ADR_MASTER_INDEX.csv`

**Columns:**

```csv
ADR_ID,Title,Status,Type,Layer(s),Dependencies,SubADRs,Module(s),Performance_SLO,Owner
ADR-0001,K1 Architecture Governance,ACTIVE,Governance,All,None,0001a/0001b/0001c,Core,N/A,Architecture
ADR-0001a,K0-K1 Bridge Protocol,ACTIVE,Integration,L5,ADR-0001,None,k0_bridge,<100ms batch,Integration
ADR-0001b,Model Hub Architecture,ACTIVE,Design,L3,ADR-0001,None,model_hub/*,<3000ms LLM,Execution
ADR-0002,Actor Model Foundation,ACTIVE,Design,L3/L4,None,0002a/0002b/0002c/0002d,mailbox/supervisor/router,<50ms message,Runtime
ADR-0003,MPST Protocol Validation,ACTIVE,Design,L2,None,0003a/0003b/0003c/0003d,protocol_monitor,<10ms validate,Orchestration
...
```

**Batch 1 Actions:**
1. Read all ADRs from `docs/architecture/decisions/`
2. Extract: ID, title, status, type (Governance/Design/Implementation/Integration)
3. Identify primary layer(s) each ADR affects
4. Map ADR → sub-ADRs (dependencies)
5. Cross-reference with DEPENDENCY_MAP module inventory
6. Add performance SLOs where applicable
7. Output CSV with 63 rows (ADR-0001 through ADR-0063+)

**Success Criteria:**
- ✅ All ADRs from `docs/architecture/decisions/` indexed
- ✅ All sub-ADRs documented (ADR-0001a, 0001b, etc.)
- ✅ No circular dependencies
- ✅ Each ADR linked to 1+ modules
- ✅ CSV validates against schema

---

### 1.2: Layer 5 Module Mapping (Infrastructure)

**Purpose:** Replace all "TBD" references in Layer 5 sections with concrete ADR logic

**Modules (19 total):**

#### 5a: Infrastructure Core (7 modules)

**scheduler** (`k1/infrastructure/scheduler/`)
```
ADR References: ADR-0028, ADR-0028a, ADR-0028b, ADR-0028c
Decision Logic:
  - 4-tier priority: CRITICAL (P0), HIGH (P1), NORMAL (P2), LOW (P3)
  - WFQ algorithm (Weighted Fair Queuing)
  - Anti-starvation: P3 gets 5% minimum allocation
  - Backpressure cascade: high load → lower priority throttle
Performance Budget:
  - Task scheduling latency: <1ms P95 (ADR-0024)
  - Dispatch latency: <2ms P95
Dependencies:
  - Imports: None (L5 foundation)
  - Exports to: All layers (scheduling decisions)
External Connections:
  - Cgroup allocation (Kubernetes resource limits)
  - CPU affinity (pin to cores)
Implementation Notes:
  - Reference: ADR-0028a (WFQ implementation strategy)
  - Use token bucket for rate limiting (ADR-0028c)
```

**backpressure** (`k1/infrastructure/backpressure/`)
```
ADR References: ADR-0061, ADR-0061a, ADR-0061b, ADR-0061c
Decision Logic:
  - 3-tier cascade: warn (80%) → backpressure (90%) → drop (95%)
  - Per-stream watermarks (speech, vision, text)
  - Voice-specific actions: pause ASR, drop frames, resume
  - Fairness algorithm: prevent starvation of low-priority streams
Performance Budget:
  - Backpressure detection: <10ms P95 (ADR-0024c)
  - Recovery time: <500ms P95
Dependencies:
  - Imports: Layer 5 (metrics, thermal)
  - Exports to: Layer 1 (input processing pause signals)
External Connections:
  - Voice input stream (pause ASR)
  - Vision processing (skip frames)
Implementation Notes:
  - Reference: ADR-0057a (voice-specific backpressure)
  - Reference: ADR-0061d (backpressure recovery strategies)
```

**thermal** (`k1/infrastructure/thermal/`)
```
ADR References: ADR-0026, ADR-0026a, ADR-0026b, ADR-0026c
Decision Logic:
  - Monitor CPU/GPU/NPU temperatures (thermal sensors)
  - Hysteresis matrix: [COOL, WARM, HOT, CRITICAL] states
  - 5°C hysteresis buffer to prevent thrashing
  - Placement decisions: move workload to cooler device
  - Emergency throttle: disable non-critical workloads
Performance Budget:
  - Temperature reading: <1ms P95
  - Placement decision: <50ms P95
  - Throttle latency: <10ms P95
Dependencies:
  - Imports: Layer 5 (metrics)
  - Exports to: Layer 3 Model Hub (placement decisions)
External Connections:
  - Thermal sensors (CPU, GPU, NPU)
  - Thermal management kernel APIs
Implementation Notes:
  - Reference: ADR-0026c (hysteresis implementation)
  - Reference: ADR-0027a (thermal-aware placement cascade)
```

**budgets** (`k1/infrastructure/budgets/`)
```
ADR References: ADR-0024, ADR-0024a, ADR-0024b, ADR-0024c, ADR-0024d
Decision Logic:
  - Token budget: per-session input/output token limits
  - Dollar budget: per-session API call cost caps
  - Compute budget: CPU/GPU ms per request
  - Latency budget: response time SLOs (TTFT, E2E, P95)
  - Hierarchical enforcement: user → session → request
Performance Budget:
  - Budget check: <1ms P95 (ADR-0024a)
  - Budget exceeded action: fail-safe (graceful degradation)
  - Performance SLOs: (see ADR-0024 table)
Dependencies:
  - Imports: Layer 5 (config, metrics)
  - Exports to: All layers (budget enforcement)
External Connections:
  - LLM API cost tracking (OpenAI, Anthropic, etc)
  - Resource usage monitoring (Kubernetes metrics)
Implementation Notes:
  - Reference: ADR-0031 (per-session cost tracking)
  - Reference: ADR-0024d (budget violation policies)
  - Reference: ADR-0057c (voice-specific latency budgets)
```

**cache** (`k1/infrastructure/cache/`)
```
ADR References: ADR-0025, ADR-0025a, ADR-0025b, ADR-0025c, ADR-0025d, ADR-0025e
Decision Logic:
  - Two caches: KV cache (128MB, model hidden states) + Prompt cache (64MB)
  - Eviction policy: LRU-LFU hybrid (80% LRU, 20% LFU)
  - Compression: Zstd (zstandard) for cold entries
  - 3-tier bands: GREEN (no limit) / AMBER (soft cap 80%) / RED (hard cap 90%)
  - Hit rate target: 75% (cold-start penalty: 5-10% latency increase)
Performance Budget:
  - Cache lookup: <100μs P95 (ADR-0025a)
  - Eviction: <10ms P95 for batch evictions
  - Compression/decompression: <50ms P95 per 16KB block
Dependencies:
  - Imports: Layer 5 (config, metrics)
  - Exports to: Layer 3 Model Hub (cache hits/misses)
External Connections:
  - GPU/TPU memory (if available)
  - Persistent cache (SSD backend)
Implementation Notes:
  - Reference: ADR-0025d (eviction strategy tuning)
  - Reference: ADR-0060 (adaptive cache placement by learning loop)
  - Reference: ADR-0027b (thermal-aware cache placement)
```

**rate_limiting** (`k1/infrastructure/rate_limiting/`)
```
ADR References: ADR-0028, ADR-0028c (token bucket)
Decision Logic:
  - Per-intent rate limit (requests/second)
  - Per-user rate limit (requests/minute/hour)
  - Token bucket algorithm: refill rate + burst capacity
  - Gradual backoff (not sudden drop): queue with priority
  - Drift detection: 2x normal rate → flag suspicious pattern
Performance Budget:
  - Rate check: <1ms P95
  - Backoff decision: <2ms P95
Dependencies:
  - Imports: Layer 5 (metrics, policy)
  - Exports to: Layer 2 Orchestrator (admission control)
External Connections:
  - API rate limits (external LLM providers)
  - User quota management (K0 sync)
Implementation Notes:
  - Reference: ADR-0049 (Fast/Smart lane router with admission control)
```

**storage_connector** (`k1/infrastructure/storage_connector/`)
```
ADR References: ADR-0020, ADR-0020a, ADR-0020b, ADR-0020c, ADR-0022 (K0 batching)
Decision Logic:
  - 3-tier storage: L1 (RAM, hot) / L2 (SSD K0 WAL) / L3 (S3, cold)
  - SessionState lifecycle: write-through L1 → batch L2 every 100ms → archive L3 after 30d
  - K0 bridge batching: 10-50 messages / 100ms window (ADR-0022)
  - Compression: Zstd for L2/L3 (10:1 ratio target)
  - Encryption: AES-256-GCM for RED band (ADR-0036)
Performance Budget:
  - L1 (RAM) latency: <1ms P95
  - L2 (SSD) latency: <10ms P95
  - K0 sync latency: <100ms P95 (batching)
  - L3 archive latency: <1000ms P95
Dependencies:
  - Imports: Layer 5 (config, metrics)
  - Exports to: K0 Kernel (state persistence)
External Connections:
  - PostgreSQL (K0 WAL store)
  - Redis (cache layer)
  - S3 / Google Cloud Storage (cold archive)
Implementation Notes:
  - Reference: ADR-0021 (turn history retention policies by band)
  - Reference: ADR-0023 (cursor-based pagination with K0 optimization)
  - Reference: ADR-0050 (multi-device sync strategy uses K0 bridge)
```

**event_bus** (`k1/infrastructure/event_bus/`)
```
ADR References: ADR-0004a, ADR-0045, ADR-0048
Decision Logic:
  - Pub/sub backbone for cross-layer async communication
  - Topics: IntentDetected, UserInput, VoiceCommand, BargeIn, StateChanged, MetricEmitted
  - Publisher: Layer 1 (Input), Layer 3 (Execution), Layer 4 (Learning)
  - Subscribers: Layer 2 (Orchestration), Layer 4 (Runtime), Layer 5 (Observability)
  - Delivery guarantee: at-least-once (with deduplication)
  - Message ordering: per-topic FIFO
Performance Budget:
  - Publish latency: <2ms P95 (ADR-0004a)
  - Subscribe latency: <5ms P95 (delivery start)
  - End-to-end message delivery: <10ms P95
Dependencies:
  - Imports: None (L5 foundation)
  - Exports to: All layers (events)
External Connections:
  - K0 bridge SSE (K0 sends events to K1)
Implementation Notes:
  - Reference: ADR-0045 (agent SSE coordination)
  - Reference: ADR-0048 (K1 internal event bus architecture)
  - Reference: ADR-0043 (SSE topic taxonomy)
```

---

#### 5b: Safety & Policy (5 modules)

**policy** (`k1/infrastructure/safety/policy/`)
```
ADR References: ADR-0032, ADR-0032a, ADR-0032b, ADR-0032c, ADR-0032d
Decision Logic:
  - 3 privacy bands: GREEN (unrestricted) / AMBER (restricted, monitoring) / RED (approval required)
  - Per-band egress rules: network, filesystem, resource permissions
  - Capability-based access control (CBAC) token system (ADR-0010)
  - Audit logging for AMBER/RED operations (ADR-0038)
Performance Budget:
  - Band check: <1ms P95
  - Policy enforcement: <2ms P95
Dependencies:
  - Imports: Layer 5 (config)
  - Exports to: All layers (band enforcement)
External Connections:
  - K0 bridge (policy sync)
  - Arbiter service (RED band approvals)
Implementation Notes:
  - Reference: ADR-0036 (E2EE for RED band data)
  - Reference: ADR-0035 (PII detection at input with band-aware redaction)
```

**pii_detector** (`k1/infrastructure/safety/pii_detector/`)
```
ADR References: ADR-0035, ADR-0035a, ADR-0035b, ADR-0035c, ADR-0035d
Decision Logic:
  - 3-tier detection: Regex (<1ms) → ONNX NER (<3ms) → LLM fallback (<50ms)
  - Regex patterns: SSN, credit card, phone, email, address
  - ONNX models: Named Entity Recognition (person, org, location)
  - LLM fallback: contextual PII detection (policy, PHI, financial)
  - Redaction strategy: mask vs. vault (store encrypted, return reference)
  - Band-specific redaction: GREEN (no redaction) / AMBER (mask) / RED (vault)
Performance Budget:
  - PII detection: <50ms P95 (all tiers combined)
  - Redaction: <10ms P95
Dependencies:
  - Imports: Layer 5 (config, cache), Layer 3 Model Hub (LLM fallback)
  - Exports to: Layer 1 (redaction on input), Layer 5 audit
External Connections:
  - Regex pattern database (versioned)
  - ONNX model server
  - Encryption vault (for PII storage)
Implementation Notes:
  - Reference: ADR-0035d (PII vault architecture)
  - Reference: ADR-0036 (E2EE storage for RED band PII)
```

**arbiter** (`k1/infrastructure/safety/arbiter/`)
```
ADR References: ADR-0052, ADR-0052a, ADR-0052b, ADR-0052c, ADR-0052d
Decision Logic:
  - Human-in-the-loop approval for RED band operations
  - Risk assessment: cost (>$100) / capability (dangerous tools) / policy (RED band)
  - Approval timeout: 5 minutes (then fail-safe to deny)
  - Audit trail: all approvals/denials logged with rationale
  - Multi-level approval: standard / escalated / executive
Performance Budget:
  - Risk assessment: <100ms P95
  - Approval decision: varies (human decision), but timeout enforced
Dependencies:
  - Imports: Layer 5 (policy, config), Layer 2 Orchestrator (risk flagging)
  - Exports to: Layer 2 (approval/denial), Layer 5 audit
External Connections:
  - Human arbiter (UI/notification system)
  - K0 bridge (approval sync across devices)
Implementation Notes:
  - Reference: ADR-0052d (multi-level approval workflows)
  - Reference: ADR-0054 (turn boundary management for HITL)
```

---

#### 5c: Observability (4 modules)

**tracing** (`k1/infrastructure/observability/tracing/`)
```
ADR References: ADR-0029, ADR-0029a, ADR-0029b, ADR-0029c, ADR-0029d
Decision Logic:
  - Distributed tracing with cognitive_trace_id propagation
  - OpenTelemetry SDK for span creation/export
  - Sampling strategy: HEAD (deterministic) / TAIL (adaptive) / BAGGAGE (custom)
  - Per-trace sampling: 10% baseline, 100% on errors, adaptive on latency spike
  - Exporters: Jaeger, Datadog, Honeycomb (configurable)
  - Span attributes: trace_id, span_id, parent_id, latency_ms, error, service_name
Performance Budget:
  - Span creation: <100μs P95
  - Trace export: batched (no blocking on hot path)
Dependencies:
  - Imports: None (L5 foundation)
  - Exports to: All layers (trace context)
External Connections:
  - Jaeger (default OTEL backend)
  - Datadog APM (optional enterprise backend)
Implementation Notes:
  - Reference: ADR-0029d (trace sampling strategy tuning)
  - Reference: ADR-0030 (trace sampling correlates with metrics)
```

**metrics** (`k1/infrastructure/observability/metrics/`)
```
ADR References: ADR-0030, ADR-0030a, ADR-0030b, ADR-0030c, ADR-0030d
Decision Logic:
  - Prometheus metrics (RED method: Rate / Errors / Duration)
  - Counters: events_total (state transitions, tool calls)
  - Gauges: active_agents, cache_utilization, queue_depth
  - Histograms: latency_ms (10ms, 50ms, 100ms, 250ms, 500ms, 1000ms buckets)
  - Labels: layer, module, intent, agent_id, error_type
  - Cardinality control: <10k timeseries (high-cardinality fields removed)
Performance Budget:
  - Metric recording: <100μs P95
  - Scrape interval: 15s (standard Prometheus)
  - Cardinality budget: <10,000 timeseries
Dependencies:
  - Imports: None (L5 foundation)
  - Exports to: All layers (metrics collection)
External Connections:
  - Prometheus (scrape /metrics endpoint)
  - Grafana (visualization)
  - AlertManager (alerting)
Implementation Notes:
  - Reference: ADR-0030c (high-cardinality field filtering)
  - Reference: ADR-0024 (performance budget tracking via metrics)
```

**receipts** (`k1/infrastructure/observability/receipts/`)
```
ADR References: ADR-0038, ADR-0038a, ADR-0038b, ADR-0038c, ADR-0038d
Decision Logic:
  - Receipt types: Model (LLM calls), Tool (execution), Protocol (MPST), State (persistence)
  - Each receipt: operation_id, timestamp, duration_ms, result, cost, trace_id
  - Immutable append-only ledger (Merkle tree chaining)
  - Retention: 90 days (GREEN) / 1 year (AMBER) / 7 years (RED)
  - Audit export: K0 bridge batching (ADR-0022) every 1 hour or 1MB
Performance Budget:
  - Receipt creation: <1ms P95
  - Receipt audit export: <100ms P95 (batched)
Dependencies:
  - Imports: Layer 5 (storage, tracing)
  - Exports to: K0 Kernel (audit ledger)
External Connections:
  - K0 bridge (audit trail sync)
  - Compliance logging (SOC 2, HIPAA, etc.)
Implementation Notes:
  - Reference: ADR-0038d (Merkle tree receipt chaining for tamper detection)
  - Reference: ADR-0021 (retention policies by privacy band)
```

**perf_harness** (`k1/infrastructure/observability/perf_harness/`)
```
ADR References: ADR-0066, ADR-0066a, ADR-0066b, ADR-0066c, ADR-0070
Decision Logic:
  - Synthetic load generation: replicate real user patterns
  - Benchmark scenarios: intent classification, planning, tool execution
  - Latency tracking: P50, P95, P99 per scenario
  - Memory profiling: peak usage, leak detection
  - Regression detection: compare against baseline (from ADR-0024)
  - Output: performance report + alerts on SLO violation
Performance Budget:
  - Benchmark run: <5 minutes for full suite
  - Regression detection: <1ms overhead per operation
Dependencies:
  - Imports: Layer 5 (config, metrics)
  - Exports to: CI/CD pipeline (regression detection)
External Connections:
  - GitHub Actions (automated benchmarks on PR)
  - Performance database (historical tracking)
Implementation Notes:
  - Reference: ADR-0066c (LLM evaluation framework integration)
  - Reference: ADR-0070 (observability infrastructure for quality labeling)
```

---

#### 5d: Configuration (3 modules)

**global** (`k1/infrastructure/config/global/`)
```
ADR References: ADR-0024, ADR-0032, ADR-0035, ADR-0036, ADR-0037
Decision Logic:
  - Config files: agents.yml, models.yml, tools.yml, scheduler.yml, policies.yml
  - Format: YAML (human-readable) with schema validation
  - Versioning: semantic versioning (major.minor.patch)
  - Hot reload capability: no restart required
  - Env var override: ENV_VAR_NAME overrides config.yaml entry
Performance Budget:
  - Config load: <100ms P95
  - Hot reload: <100ms P95
  - Env var lookup: <1ms P95
Dependencies:
  - Imports: None (L5 foundation)
  - Exports to: All layers (configuration values)
External Connections:
  - ConfigMap (Kubernetes)
  - AWS Parameter Store / Google Secret Manager (if cloud-hosted)
Implementation Notes:
  - Reference: ADR-0042 (K0 SSE event streaming for config updates)
  - Reference: ADR-0043 (SSE topic taxonomy includes config topics)
```

**schemas** (`k1/infrastructure/config/schemas/`)
```
ADR References: ADR-0011, ADR-0011a, ADR-0011b, ADR-0011c, ADR-0011d, ADR-0012, ADR-0013
Decision Logic:
  - 76 FlatBuffers schemas (5 layers × 15 schemas avg)
  - Pydantic models for runtime validation
  - Bidirectional serialization: Pydantic ↔ FlatBuffers ↔ JSON
  - Schema versioning: 90-day deprecation workflow (ADR-0013)
  - Backward compatibility: new optional fields, never remove
Performance Budget:
  - Schema validation: <1ms P95
  - Serialization: <1ms P95 for 64KB payloads (FlatBuffers)
  - Deserialization: <1ms P95 (zero-copy)
Dependencies:
  - Imports: None (L5 foundation)
  - Exports to: All layers (schema definitions)
External Connections:
  - Proto3 definitions (if migrating to protobuf)
Implementation Notes:
  - Reference: ADR-0011d (FlatBuffers best practices for K1)
  - Reference: ADR-0013d (deprecation workflow automation)
```

**config_manager** (`k1/infrastructure/config/config_manager/`)
```
ADR References: ADR-0042, ADR-0042a, ADR-0042b, ADR-0042c, ADR-0042d, ADR-0042e
Decision Logic:
  - Watch config files for changes (OS file watcher or polling)
  - K0 bridge SSE listener: subscribe to K0 config events
  - Config merge: local override > K0 broadcast > compiled defaults
  - Version tracking: detect conflicts, use K0 as source of truth
  - Propagate to layers: emit ConfigUpdated event → event_bus (L5)
  - Validation: schema check before hot reload
Performance Budget:
  - Config update detection: <1s P95 (polling interval)
  - Hot reload: <100ms P95
  - SSE message delivery: <50ms P95
Dependencies:
  - Imports: Layer 5 (event_bus, storage, tracing)
  - Exports to: All layers (ConfigUpdated events)
External Connections:
  - K0 bridge (config SSE stream)
  - File system watcher
Implementation Notes:
  - Reference: ADR-0044 (K0 bridge HTTP/2 + FlatBuffers for config streaming)
  - Reference: ADR-0001f (K0-K1 boundary enforcement includes config isolation)
```

---

#### 5e: Connectors (2 modules)

**k0_bridge** (`k1/infrastructure/connectors/k0_bridge/`)
```
ADR References: ADR-0001a, ADR-0022, ADR-0042, ADR-0043, ADR-0044
Decision Logic:
  - Bidirectional communication with K0 kernel
  - Two transports: JSON (flexible) + FlatBuffers (efficient)
  - Message batching: 10-50 msgs / 100ms window OR 64KB cumulative size
  - Compression: Zstd (10:1 ratio target)
  - HTTP/2 multiplexing: multiple concurrent streams
  - Retry logic: exponential backoff (1s, 2s, 4s, 8s, 16s max)
Performance Budget:
  - Message send latency: <50ms P95 (batching)
  - Message receive latency: <50ms P95
  - Batch processing: <10ms P95 (decompression + parsing)
  - End-to-end K0 round-trip: <500ms P95
Dependencies:
  - Imports: Layer 5 (storage, config, tracing)
  - Exports to: K0 Kernel (state, audit, config)
External Connections:
  - K0 kernel (REST/HTTP/2 API)
  - TLS certificate management
Implementation Notes:
  - Reference: ADR-0022d (batching tuning strategy)
  - Reference: ADR-0044d (HTTP/2 connection lifecycle)
  - Reference: ADR-0050c (LAN-first sync for multi-device uses K0 bridge)
```

**model_hub_client** (`k1/infrastructure/connectors/model_hub_client/`)
```
ADR References: ADR-0001b, ADR-0018, ADR-0019
Decision Logic:
  - Internal interface for Layer 3 Model Hub (orchestration entry point)
  - Request: intent_id, model_name, prompt, max_tokens, temperature
  - Response: token_stream (for streaming) OR completion (for batch)
  - Error handling: fallback cascade (ADR-0019a)
  - Token accounting: track input/output tokens for budgets
Performance Budget:
  - Request processing: <100ms P95
  - Token accounting: <1ms P95
Dependencies:
  - Imports: Layer 5 (config, metrics, cache)
  - Exports to: Layer 3 Model Hub (LLM responses)
External Connections:
  - None (internal interface to Model Hub)
Implementation Notes:
  - Reference: ADR-0018 (model provider abstraction)
  - Reference: ADR-0021 (response streaming for token delivery)
```

---

### 1.3: Event Bus Detailed Specification

**Location:** Update DEPENDENCY_MAP.md → "Event Bus & Coordination" section

```markdown
## Event Bus Architecture (ADR-0004a, 0045, 0048)

### Topics Defined

| Topic | Publisher | Subscribers | Payload | SLA |
|-------|-----------|-------------|---------|-----|
| `intent.detected` | intent_router (L1) | orchestrator (L2), learning_loop (L4) | IntentDetected event | <10ms |
| `user.input` | stream_switch (L1) | all layers | UserInputEvent | <5ms |
| `voice.command` | stream_switch (L1) | meta_policy (L1), orchestrator (L2) | VoiceCommandEvent | <5ms |
| `barge_in.detected` | operators (L1) | orchestrator (L2), turn_manager (L3) | BargeInEvent | <5ms |
| `state.changed` | session_state (L4) | learning_loop (L4), metrics (L5) | StateChangedEvent | <2ms |
| `metric.emitted` | metrics (L5) | perf_harness (L5), K0 bridge (L5) | MetricEvent | <1ms |
| `config.updated` | config_manager (L5) | All layers | ConfigUpdatedEvent | <100ms |

### Message Ordering Guarantee

FIFO per-topic (can be parallelized across topics).

### Delivery Guarantee

At-least-once (deduplication on receive side by trace_id + message_id).

### Backpressure Handling

If subscriber queue depth > 10,000: emit backpressure_warning event.
```

---

### 1.4: K0 Bridge Integration Points

**Location:** Add new section "K0-K1 Bridge Integration Map"

```markdown
## K0-K1 Bridge Integration (ADR-0001a, 0022, 0042, 0043, 0044)

### State Sync (ADR-0001a)

K1 → K0: SessionState serialization
- Trigger: on state mutation OR every 100ms (whichever first)
- Protocol: FlatBuffers (ADR-0019d) or JSON fallback
- Batching: ADR-0022 (10-50 msgs / 100ms)

K0 → K1: Session recovery
- Trigger: session resume OR K1 restart
- Protocol: K0 sends full state snapshot as FlatBuffers
- Latency budget: <500ms P95

### Config Sync (ADR-0042, 0043)

K0 → K1: Config updates via SSE
- Channel: HTTP/2 SSE (ADR-0044)
- Topics: agents.yml, models.yml, tools.yml, policies.yml (ADR-0043 taxonomy)
- Propagation: config_manager receives SSE → validates → hot reloads
- Latency budget: <100ms P95

K1 → K0: Policy violations
- Trigger: RED band operation attempt
- Protocol: audit_receipt → K0 bridge → K0 audit ledger
- Latency budget: <100ms P95

### Port Mapping (P01-P20)

| Port | Purpose | Protocol | From | To | Latency Budget |
|------|---------|----------|------|-----|-----------------|
| P01 | State sync | FlatBuffers | K1 | K0 | <500ms |
| P02 | Config SSE | HTTP/2 | K0 | K1 | <100ms |
| P03 | Audit trail | FlatBuffers | K1 | K0 | <100ms |
| P04 | Model mgmt | JSON | K1 | K0 | <200ms |
| P05 | Multi-device discovery | mDNS | K1 | K1 (peer) | <1s |
| ... | ... | ... | ... | ... | ... |
```

---

### 1.5: Cross-Reference Validation Framework

**Purpose:** Ensure all "TBD" references are replaced with concrete ADRs

**Validation Checklist:**

```yaml
Batch 1 Validation Criteria:

Layer 5 Modules (19 total):
  ✅ scheduler: ADR-0028 + sub-ADRs referenced
  ✅ backpressure: ADR-0061 + sub-ADRs referenced
  ✅ thermal: ADR-0026 + sub-ADRs referenced
  ✅ budgets: ADR-0024 + sub-ADRs referenced
  ✅ cache: ADR-0025 + sub-ADRs referenced
  ✅ rate_limiting: ADR-0028c referenced
  ✅ storage_connector: ADR-0020/0022 + sub-ADRs referenced
  ✅ event_bus: ADR-0004a/0045/0048 referenced
  ✅ policy: ADR-0032 + sub-ADRs referenced
  ✅ pii_detector: ADR-0035 + sub-ADRs referenced
  ✅ arbiter: ADR-0052 + sub-ADRs referenced
  ✅ tracing: ADR-0029 + sub-ADRs referenced
  ✅ metrics: ADR-0030 + sub-ADRs referenced
  ✅ receipts: ADR-0038 + sub-ADRs referenced
  ✅ perf_harness: ADR-0066/0070 referenced
  ✅ global: ADR-0024/0032/0035/0036/0037 referenced
  ✅ schemas: ADR-0011/0012/0013 + sub-ADRs referenced
  ✅ config_manager: ADR-0042/0043/0044 + sub-ADRs referenced
  ✅ k0_bridge: ADR-0001a/0022/0042/0043/0044 referenced
  ✅ model_hub_client: ADR-0001b/0018/0019 referenced

ADR Index (ADR_MASTER_INDEX.csv):
  ✅ All ADRs from docs/architecture/decisions/ indexed
  ✅ Sub-ADRs identified and linked
  ✅ No circular dependencies
  ✅ Each ADR linked to 1+ modules
  ✅ Performance SLOs populated
  ✅ Dependencies correctly mapped

Cross-References:
  ✅ No "TBD" references remain in Layer 5 sections
  ✅ All inter-layer connections documented
  ✅ Performance budgets traced to ADRs
  ✅ External connections mapped to ADRs

Documentation:
  ✅ DEPENDENCY_MAP.md Layer 5 sections complete
  ✅ ADR_MASTER_INDEX.csv created
  ✅ Event bus topics documented
  ✅ K0 bridge integration points mapped
  ✅ Port mapping (P01-P20) defined
```

---

## Batch 1 Timeline

| Week | Milestone | Deliverable | Success Criteria |
|------|-----------|-------------|------------------|
| 1 | ADR Indexing | ADR_MASTER_INDEX.csv | 63+ rows, no missing sub-ADRs |
| 2 | Infrastructure Core (7) | scheduler, backpressure, thermal, budgets, cache, rate_limiting, storage_connector | All 7 modules mapped to ADRs |
| 2 | Safety & Policy (5) | policy, pii_detector, arbiter, + config foundation | All 5 modules mapped to ADRs |
| 3 | Observability (4) | tracing, metrics, receipts, perf_harness | All 4 modules mapped to ADRs |
| 3 | Configuration (3) | global, schemas, config_manager | All 3 modules mapped to ADRs |
| 4 | Connectors (2) | k0_bridge, model_hub_client | All 2 modules mapped to ADRs |
| 4 | Integration & Validation | Event bus, K0 bridge mapping, validation report | All Layer 5 sections complete, no TBD |

---

## Batch 1 Gate Criteria

**MUST PASS ALL BEFORE BATCH 2 STARTS:**

- ✅ ADR_MASTER_INDEX.csv complete with 63+ rows
- ✅ All 19 Layer 5 modules mapped to concrete ADRs (no TBD)
- ✅ Event bus topics defined (6+)
- ✅ K0 bridge ports mapped (P01-P20)
- ✅ Performance budgets traced to ADRs
- ✅ Cross-reference validation passed
- ✅ DEPENDENCY_MAP.md Layer 5 sections updated

**Batch 1 owner:** Infrastructure Team

---

# BATCH 2: Core Layers (L2, L3, L4) - Weeks 5-8

*[Reserved for next iteration after Batch 1 completion]*

---

# BATCH 3: Input & Integration (L1 + External) - Weeks 9-12

*[Reserved for next iteration after Batch 2 completion]*

---

## Overall Success Criteria (All 3 Batches)

- ✅ All 52 modules mapped to concrete ADRs (no TBD)
- ✅ All 63+ ADRs referenced in DEPENDENCY_MAP.md
- ✅ All performance budgets traced to ADRs (ADR-0024)
- ✅ All external systems mapped to ADRs + port specs
- ✅ K0 bridge integration complete (all 20 ports mapped)
- ✅ Event bus covers all cross-layer communication
- ✅ No circular dependencies in dependency graph
- ✅ Ready for coding/implementation (Phase 2)

---

## Notes for Future Batches

- **Batch 2** will require Layer 5 completion first (foundation layer)
- **Batch 3** will require Batches 1-2 complete (depends on all lower layers)
- Each batch produces deliverables that are dependencies for next batch
- **Gate criteria** are strict: no TBD references allowed past each gate
- **Cross-reference validation** must pass before code implementation begins
