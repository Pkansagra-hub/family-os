# Layer 5 (Infrastructure) — ADR Family Map

**Complete end-to-end ADR references for K1 Layer 5 modules**

---

## 📋 Overview

**Layer 5 Purpose:** Infrastructure (Safety, Observability, Config, Connectors, Resilience)
**Performance Budget:** <5ms event bus delivery, <100ms thermal placement, <10ms circuit breaker
**Modules:** 19 modules across 6 categories
**Primary Function:** Cross-cutting infrastructure services for all K1 layers

---

## 🗺️ Layer 5 Architecture

### Core ADRs

| ADR | Title | Status | Priority | Coverage |
|-----|-------|--------|----------|----------|
| **ADR-0004** | 52-Module 5-Layer Architecture | ✅ Complete | 🔴 CRITICAL | Layer 5 definition, 19-module infrastructure |
| **ADR-0001a** | K0 Bridge Architecture | ✅ Complete | 🔴 CRITICAL | Dual-protocol K1→K0 communication |
| **ADR-0029** | Prometheus Metrics | ✅ Complete | 🔴 CRITICAL | 50+ metrics across all subsystems |
| **ADR-0009** | Circuit Breaker | ✅ Complete | 🟡 HIGH | 3-state FSM, failure isolation |
| **ADR-0026** | Thermal Management | ✅ Complete | 🟡 HIGH | Hysteresis matrix, 4-tier placement |
| **ADR-0004a** | Event Bus | ✅ Complete | 🟡 HIGH | Layer 1→2 communication, pub/sub |
| **ADR-0004d** | Layer 5 Integration Tests | ✅ Complete | 🟡 HIGH | Event bus, thermal, resilience tests |

---

## 📁 Module-by-Module ADR Map

## Category 1: bridge_k0/ (5 modules - K1→K0 Connection Layer)

### **Module 1.1: bridge_k0/command_client/**
**Purpose:** K0 Command Port client (write operations)
**Location:** `k1/bridge_k0/command_client.py`
**Performance:** <50ms P95 (GREEN), <200ms P95 (AMBER/RED)

#### Primary ADRs

- **ADR-0001a** — K0 Bridge Architecture (dual-protocol, 4 ports, lane processing)
- **ADR-0001** — K0 Integration (20 pipelines, 4 external ports)

#### Related ADRs

- **ADR-0011** — FlatBuffers Serialization (optional optimization)
- **ADR-0024** — Performance Budgets (K0 Bridge <50ms GREEN, <200ms AMBER/RED)
- **ADR-0029** — Prometheus Metrics (command latency, error rate)

#### Key Responsibilities

1. **Command Port Integration:**
   - HTTP POST to K0 Command Port (`:5200/v1/command`)
   - Dual-protocol: JSON (primary) + FlatBuffers (secondary)
   - Commands: MEMORY_WRITE, PLAN_COMMITTED, SAGA_LOG, STATE_DELTA

2. **Lane Processing:**
   - **Fast Lane (GREEN):** <50ms P95, 70% of writes
   - **Smart Lane (AMBER/RED):** <200ms P95, 30% of writes (safety review)
   - Privacy band-aware routing

3. **Reliability:**
   - Idempotency keys (UUIDv7)
   - Receipt validation (WAL offset, timestamp)
   - Retry policy: 3 attempts, exponential backoff (100ms→400ms→1600ms)

**Performance Metrics:**
- Command latency (GREEN): <50ms P95
- Command latency (AMBER/RED): <200ms P95
- Success rate: >99.9%
- Retry rate: <1%

---

### **Module 1.2: bridge_k0/query_client/**
**Purpose:** K0 Query Port client (read operations)
**Location:** `k1/bridge_k0/query_client.py`
**Performance:** <100ms P95 (multi-store retrieval)

#### Primary ADRs

- **ADR-0001a** — K0 Bridge Architecture (multi-store retrieval, fusion)
- **ADR-0001** — K0 Integration (P01 RecallQuery pipeline)

#### Related ADRs

- **ADR-0024** — Performance Budgets (K0 queries <100ms)
- **ADR-0029** — Prometheus Metrics (query latency, hit rate)

#### Key Responsibilities

1. **Query Port Integration:**
   - HTTP POST to K0 Query Port (`:5201/v1/query`)
   - Dual-protocol: JSON (primary) + FlatBuffers (secondary)
   - Queries: RECALL, SEARCH, KG_NEIGHBORS, KG_PATHS

2. **Multi-Store Retrieval:**
   - **FTS5 (full-text search):** Keyword matching, BM25 ranking
   - **FAISS (vector search):** Semantic similarity, cosine distance
   - **SQLite KG (knowledge graph):** Entity relationships, graph traversal
   - **Episodic Memory:** Recent conversation turns (last 10 turns)

3. **Fusion Strategy:**
   - Maximal Marginal Relevance (MMR): Relevance + diversity
   - Reciprocal Rank Fusion (RRF): Combine rankings from multiple stores
   - Top-k selection: Return best 20 results

**Performance Metrics:**
- Query latency: <100ms P95
- Hit rate: >75% (cached)
- Miss penalty: 200-300ms (full retrieval)
- Fusion overhead: <10ms

---

### **Module 1.3: bridge_k0/sse_client/**
**Purpose:** K0 SSE Port client (event streaming)
**Location:** `k1/bridge_k0/sse_client.py`
**Performance:** <5ms event delivery

#### Primary ADRs

- **ADR-0001a** — K0 Bridge Architecture (SSE subscription, event streaming)
- **ADR-0016** — SSE Event Schemas (K0→K1 events)

#### Related ADRs

- **ADR-0024** — Performance Budgets (SSE delivery <5ms)
- **ADR-0029** — Prometheus Metrics (event rate, subscription count)

#### Key Responsibilities

1. **SSE Port Integration:**
   - HTTP GET to K0 SSE Port (`:5202/v1/events`)
   - EventSource client (SSE protocol)
   - Event types: MEMORY_WRITTEN, CONSOLIDATION_COMPLETE, SYNC_STATUS

2. **Event Subscription:**
   - Topic-based filtering (subscribe to specific event types)
   - Server-side filtering (K0 filters before sending)
   - Reconnection logic (exponential backoff)

3. **Event Delivery:**
   - Push events to K1 event bus
   - <5ms delivery latency
   - Ordering guarantee (per-topic FIFO)

**Performance Metrics:**
- Event delivery: <5ms P95
- Throughput: 100+ events/sec
- Reconnection latency: <1s
- Subscription overhead: <10ms

---

### **Module 1.4: bridge_k0/batch_client/**
**Purpose:** SessionState delta batching (250ms interval)
**Location:** `k1/bridge_k0/batch_client.py`
**Performance:** <10ms batch processing

#### Primary ADRs

- **ADR-0001f** — SessionState Delta Batching (250ms batching, P02 MemoryWrite)
- **ADR-0017** — SessionState 6-Section Design (delta source)

#### Related ADRs

- **ADR-0024** — Performance Budgets (batching <10ms)
- **ADR-0029** — Prometheus Metrics (batch size, batching latency)

#### Key Responsibilities

1. **Delta Batching:**
   - Batch SessionState updates every 250ms
   - Compute field-level deltas (field_path, old_value, new_value)
   - Example: `control.current_flow` changed from `null` to `flow_abc123`

2. **Batch Processing:**
   - Coalesce redundant updates (same field updated multiple times)
   - Deduplicate deltas (keep latest value)
   - Batch size: 10-50 deltas typical

3. **K0 Integration:**
   - Send batched deltas to K0 P02 MemoryWrite pipeline
   - Receipt validation (WAL offset confirmation)
   - Error handling: Retry failed batches

**Performance Metrics:**
- Batch interval: 250ms
- Batch size: 10-50 deltas typical
- Batch processing: <10ms P95
- Batching efficiency: 80% reduction in K0 writes

---

### **Module 1.5: bridge_k0/observability_client/**
**Purpose:** K0 Observability Port client (metrics/logs push)
**Location:** `k1/bridge_k0/observability_client.py`
**Performance:** <20ms metric push

#### Primary ADRs

- **ADR-0001a** — K0 Bridge Architecture (observability integration)
- **ADR-0029** — Prometheus Metrics (K1→K0 metric forwarding)

#### Related ADRs

- **ADR-0030** — Trace Sampling (cognitive_trace_id propagation)

#### Key Responsibilities

1. **Observability Port Integration:**
   - HTTP POST to K0 Observability Port (`:5203/v1/observability`)
   - Push K1 metrics/logs to K0 for centralized observability
   - Metrics: K1 layer latencies, agent lifecycle, tool execution

2. **Metric Forwarding:**
   - Prometheus metric format (OpenMetrics)
   - Batch metrics every 10s
   - Push to K0 for unified dashboard

3. **Log Forwarding:**
   - Structured JSON logs (cognitive_trace_id, timestamp, level, message)
   - Batch logs every 5s
   - Push to K0 for centralized logging

**Performance Metrics:**
- Metric push: <20ms P95
- Log push: <10ms P95
- Batch interval: 10s (metrics), 5s (logs)

---

## Category 2: resilience/ (3 modules)

### **Module 2.1: resilience/circuit_breaker/**
**Purpose:** Circuit breaker (3-state FSM)
**Location:** `k1/l5_infrastructure/resilience/circuit_breaker_manager.py`
**Performance:** <10ms circuit breaker check

#### Primary ADRs

- **ADR-0009** — Circuit Breaker (3-state FSM: CLOSED/OPEN/HALF_OPEN)
- **ADR-0009a** — Circuit State Transitions (failure threshold, cooldown)
- **ADR-0009b** — Hot Reload (dynamic config updates)
- **ADR-0009c** — Fallback Cascade (primary → fallback routing)

#### Related ADRs

- **ADR-0024** — Performance Budgets (circuit breaker <10ms)
- **ADR-0027** — Model Placement Cascade (circuit breaker integration)
- **ADR-0029** — Prometheus Metrics (circuit breaker state, failure rate)

#### Key Responsibilities

1. **3-State FSM:**
   - **CLOSED:** Normal operation, track failures
   - **OPEN:** Fail-fast (reject immediately), cooldown 30s
   - **HALF_OPEN:** Test recovery (allow 1 request), transition to CLOSED/OPEN

2. **Failure Detection:**
   - Failure threshold: 5 consecutive failures
   - Failure types: Timeout, exception, crash
   - Success reset: 3 consecutive successes → reset failure count

3. **Fallback Cascade:**
   - Primary target fails → circuit opens
   - Fallback chain: NPU → GPU → CPU → Remote
   - Effectiveness: 92% cascade prevention (5K failures avoided)

**Performance Metrics:**
- Circuit check: <10ms P95
- Failure detection: <20ms
- State transition: <5ms
- Cascade success rate: >99%

---

### **Module 2.2: resilience/retry_policy/**
**Purpose:** Retry policies (exponential backoff)
**Location:** `k1/l5_infrastructure/resilience/retry_policy.py`
**Performance:** <5ms retry decision

#### Primary ADRs

- **ADR-0008b** — Saga Retry Policy (max 5 retries, exponential backoff, jitter)

#### Related ADRs

- **ADR-0024** — Performance Budgets (retry decision <5ms)

#### Key Responsibilities

1. **Retry Policy:**
   - Max retries: 5 attempts
   - Exponential backoff: 100ms → 200ms → 400ms → 800ms → 1600ms
   - Jitter: 20% random variation (prevent thundering herd)
   - Total budget: 10s

2. **Retry Decision:**
   - Retryable errors: Timeout, network error, 5xx HTTP
   - Non-retryable errors: Validation error, 4xx HTTP
   - Idempotency: Retry safe operations only

**Performance Metrics:**
- Retry decision: <5ms P95
- Retry success rate: >80% (2nd attempt)
- Total retry latency: 100ms-10s (depends on backoff)

---

### **Module 2.3: resilience/hot_reload/**
**Purpose:** Config hot reload (asyncio file watcher)
**Location:** `k1/l5_infrastructure/resilience/hot_reload.py`
**Performance:** <100ms reload latency

#### Primary ADRs

- **ADR-0009b** — Hot Reload (file watcher, asyncio reload)

#### Key Responsibilities

1. **File Watcher:**
   - Monitor config files (circuit_breaker.yaml, retry_policy.yaml)
   - Detect changes (file modification events)
   - Trigger reload

2. **Config Reload:**
   - Parse updated config files
   - Validate new config
   - Apply changes without restart (<100ms)

**Performance Metrics:**
- Reload latency: <100ms P95
- Reload frequency: <1/hour typical

---

## Category 3: thermal/ (2 modules)

### **Module 3.1: thermal/placement_planner/**
**Purpose:** Thermal-aware model placement (NPU→GPU→CPU→Remote)
**Location:** `k1/l5_infrastructure/thermal/placement_planner.py`
**Performance:** <10ms placement decision

#### Primary ADRs

- **ADR-0026** — Thermal Management (hysteresis matrix, 4-tier placement)
- **ADR-0027** — Model Placement Cascade (NPU→GPU→CPU→Remote)

#### Related ADRs

- **ADR-0024** — Performance Budgets (placement <10ms)
- **ADR-0029** — Prometheus Metrics (device temperature, placement decisions)

#### Key Responsibilities

1. **4-Tier Placement:**
   - **NPU (30ms, 10W):** Optimal for on-device inference
   - **GPU (50ms, 12W):** Fallback for NPU overload
   - **CPU (120ms, 15W):** Fallback for GPU overload
   - **Remote (500ms, 5W):** Cloud-based inference (last resort)

2. **Thermal Management:**
   - Temperature zones: COOL (<60°C), WARM (60-75°C), HOT (75-85°C), CRITICAL (≥85°C)
   - Hysteresis matrix: 3°C dead zone (prevent rapid switching)
   - Emergency jump: CRITICAL → Remote (immediate)

3. **Placement Decision:**
   - Monitor device temperature (1 Hz polling)
   - Choose accelerator based on thermal zone
   - <10ms placement decision

**Performance Metrics:**
- Placement decision: <10ms P95
- Thermal polling: 1 Hz
- Failover latency: <100ms (detection 20ms + transfer 30ms + loading 50ms)
- Emergency jump: <50ms (CRITICAL → Remote)

---

### **Module 3.2: thermal/monitor/**
**Purpose:** Device temperature monitoring
**Location:** `k1/l5_infrastructure/thermal/monitor.py`
**Performance:** <5ms temperature read

#### Primary ADRs

- **ADR-0026** — Thermal Management (monitoring integration)

#### Key Responsibilities

1. **Temperature Monitoring:**
   - Poll NPU/GPU/CPU temperature sensors (1 Hz)
   - Thermal zones: COOL, WARM, HOT, CRITICAL
   - Alert on CRITICAL (≥85°C)

2. **Metrics Emission:**
   - Push temperature metrics to Prometheus
   - Alert thresholds: HOT (75°C), CRITICAL (85°C)

**Performance Metrics:**
- Temperature read: <5ms P95
- Polling frequency: 1 Hz
- Alert latency: <100ms

---

## Category 4: event_bus/ (2 modules)

### **Module 4.1: event_bus/event_bus/**
**Purpose:** Layer 1→2 event bus (pub/sub)
**Location:** `k1/l5_infrastructure/event_bus/event_bus.py`
**Performance:** <5ms event delivery

#### Primary ADRs

- **ADR-0004a** — Event Bus (Layer 1-2 communication, pub/sub, zero-copy)

#### Related ADRs

- **ADR-0024** — Performance Budgets (event bus <5ms)
- **ADR-0029** — Prometheus Metrics (event rate, subscription count, delivery latency)

#### Key Responsibilities

1. **Pub/Sub Pattern:**
   - Topic-based routing (INTENT_DETECTED, USER_INPUT, VOICE_COMMAND, BARGE_IN)
   - Multiple subscribers per topic
   - Async delivery (asyncio.Queue per subscriber)

2. **Event Delivery:**
   - Zero-copy: Pass references (no serialization)
   - <5ms delivery latency
   - Ordering: FIFO per topic

3. **Backpressure:**
   - Subscriber queue depth: 50 max
   - Overflow: DROP_OLDEST policy
   - Slow subscriber detection: >100ms processing time

**Performance Metrics:**
- Event delivery: <5ms P95
- Throughput: 1000+ events/sec
- Subscriber queue depth: <10 typical, <50 max
- Backpressure events: <1% of deliveries

---

### **Module 4.2: event_bus/schemas/**
**Purpose:** Event schemas (EventBus message types)
**Location:** `k1/l5_infrastructure/event_bus/schemas.py`
**Performance:** N/A (static definitions)

#### Primary ADRs

- **ADR-0004a** — Event Bus (event schema definitions)

#### Key Responsibilities

1. **Event Schemas:**
   - **IntentDetected:** tier (T1/T2/T3), intent, confidence, entities
   - **UserInput:** input_type (text/voice), raw_text, cognitive_trace_id
   - **VoiceCommand:** transcript, vad_confidence, language
   - **BargeIn:** interrupt_time, cancellation_reason

2. **Cognitive Trace ID:**
   - Propagate cognitive_trace_id across all events
   - End-to-end tracing (L1→L2→L3→L4→L5→K0)

**Event Count:** 10+ event types

---

## Category 5: observability/ (4 modules)

### **Module 5.1: observability/metrics/**
**Purpose:** Prometheus metrics exporter
**Location:** `k1/l5_infrastructure/observability/metrics.py`
**Performance:** <10ms metric emission

#### Primary ADRs

- **ADR-0029** — Prometheus Metrics (50+ metrics across all layers)
- **ADR-0002d** — Actor Fabric Observability (mailbox, router, supervisor metrics)

#### Related ADRs

- **ADR-0024** — Performance Budgets (metric emission <10ms)

#### Key Responsibilities

1. **Metric Types:**
   - **Counters:** agent_hire_count, tool_execution_count, crash_count
   - **Gauges:** mailbox_depth, active_agent_count, kv_cache_hit_rate
   - **Histograms:** layer1_latency_ms, model_hub_inference_ms, tool_execution_ms

2. **Metric Emission:**
   - Push to Prometheus (HTTP POST to `:9091/metrics`)
   - Scrape interval: 10s
   - <10ms emission overhead

3. **Metrics Catalog:**
   - **Layer 1 (5 metrics):** TTFT, VAD latency, intent classification latency
   - **Layer 2 (8 metrics):** Planning latency, orchestration latency, protocol validation
   - **Layer 3 (12 metrics):** Agent lifecycle, Model Hub inference, tool execution
   - **Layer 4 (10 metrics):** SessionState size, mailbox depth, learning cycle
   - **Layer 5 (15 metrics):** Event bus delivery, thermal temperature, circuit breaker state

**Total Metrics:** 50+ metrics

**Performance Metrics:**
- Metric emission: <10ms P95
- Scrape interval: 10s
- Metric overhead: <1% CPU

---

### **Module 5.2: observability/tracing/**
**Purpose:** OpenTelemetry distributed tracing
**Location:** `k1/l5_infrastructure/observability/tracing.py`
**Performance:** <5ms span creation

#### Primary ADRs

- **ADR-0030** — Trace Sampling (cognitive_trace_id, 1% sampling)
- **ADR-0002d** — Actor Fabric Observability (actor.send/recv spans)

#### Related ADRs

- **ADR-0024** — Performance Budgets (tracing <5ms)

#### Key Responsibilities

1. **Span Creation:**
   - OpenTelemetry spans (start, end, attributes)
   - Span types: actor.send, actor.recv, router.admission, mailbox.enq, mailbox.deq
   - cognitive_trace_id propagation

2. **Trace Sampling:**
   - 1% sampling rate (reduce overhead)
   - Always sample: Errors, high-latency requests (>5s)
   - Sampling decision: Hash-based (consistent per trace)

3. **Trace Export:**
   - Export to Jaeger/Zipkin (OTLP protocol)
   - Batch export: Every 5s, max 100 spans per batch

**Performance Metrics:**
- Span creation: <5ms P95
- Sampling rate: 1% (normal), 100% (errors)
- Trace export: <50ms per batch

---

### **Module 5.3: observability/logging/**
**Purpose:** Structured logging (JSON format)
**Location:** `k1/l5_infrastructure/observability/logging.py`
**Performance:** <5ms log write

#### Primary ADRs

- **ADR-0002d** — Actor Fabric Observability (structured logs, 6 event types)

#### Key Responsibilities

1. **Log Format:**
   - JSON structured logs
   - Fields: timestamp, level (DEBUG/INFO/WARN/ERROR), cognitive_trace_id, message, context

2. **Event Types:**
   - **ACTOR_STARTED:** actor_id, actor_type, initialization_time
   - **ACTOR_STOPPED:** actor_id, reason, uptime
   - **MESSAGE_SENT:** sender, receiver, message_type, priority
   - **MESSAGE_RECEIVED:** receiver, sender, processing_time
   - **ADMISSION_REJECTED:** sender, receiver, reason
   - **CRASH_DETECTED:** actor_id, crash_reason, stack_trace

3. **Log Volume:**
   - <10MB/hour (typical)
   - Log rotation: Daily, 7-day retention

**Performance Metrics:**
- Log write: <5ms P95
- Log volume: <10MB/hour
- Log rotation: Daily

---

### **Module 5.4: observability/dashboards/**
**Purpose:** Grafana dashboards
**Location:** `k1/l5_infrastructure/observability/dashboards/`
**Performance:** N/A (static definitions)

#### Primary ADRs

- **ADR-0029** — Prometheus Metrics (dashboard integration)
- **ADR-0002d** — Actor Fabric Observability (mailbox, router, supervisor dashboards)

#### Key Responsibilities

1. **Dashboard Catalog:**
   - **K1 Overview:** Layer latencies, agent lifecycle, tool execution
   - **Layer 1 Dashboard:** TTFT, VAD latency, intent classification
   - **Layer 2 Dashboard:** Planning latency, orchestration latency, protocol validation
   - **Layer 3 Dashboard:** Agent lifecycle, Model Hub inference, tool execution
   - **Layer 4 Dashboard:** SessionState size, mailbox depth, learning cycle
   - **Layer 5 Dashboard:** Event bus delivery, thermal temperature, circuit breaker state
   - **Actor Fabric Dashboard:** Mailbox health, admission control, supervisor, message flow

**Total Dashboards:** 7 dashboards

---

## Category 6: config/ (2 modules) + connectors/ (1 module)

### **Module 6.1: config/loader/**
**Purpose:** YAML config loader
**Location:** `k1/l5_infrastructure/config/loader.py`
**Performance:** <50ms config load

#### Primary ADRs

- **ADR-0009b** — Hot Reload (config file monitoring)

#### Key Responsibilities

1. **Config Loading:**
   - Load YAML config files (kernel.yaml, logging.yaml, circuit_breaker.yaml)
   - Validate schema (JSON schema validation)
   - Merge configs (defaults + overrides)

2. **Hot Reload:**
   - Detect config file changes
   - Reload without restart (<100ms)

**Performance Metrics:**
- Config load: <50ms P95 (startup)
- Hot reload: <100ms P95

---

### **Module 6.2: config/schema_validator/**
**Purpose:** Config schema validation
**Location:** `k1/l5_infrastructure/config/schema_validator.py`
**Performance:** <10ms validation

#### Key Responsibilities

1. **Schema Validation:**
   - JSON schema validation (Draft 7)
   - Validate config structure, types, constraints
   - Error reporting (detailed validation errors)

**Performance Metrics:**
- Validation: <10ms P95

---

### **Module 6.3: connectors/k0_connector/**
**Purpose:** K0 connection lifecycle management
**Location:** `k1/l5_infrastructure/connectors/k0_connector.py`
**Performance:** <100ms connection establishment

#### Primary ADRs

- **ADR-0001a** — K0 Bridge Architecture (connection management)

#### Key Responsibilities

1. **Connection Lifecycle:**
   - Establish HTTP/2 connection to K0 (TLS 1.3)
   - Health check: Ping K0 every 10s
   - Reconnection: Exponential backoff (1s→2s→4s→8s→30s max)

2. **Connection Pooling:**
   - Connection pool: 5 connections (command, query, SSE, observability, health)
   - Keep-alive: 60s timeout
   - Connection reuse: >90% hit rate

**Performance Metrics:**
- Connection establishment: <100ms P95
- Reconnection latency: 1s-30s (exponential backoff)
- Connection pool hit rate: >90%

---

## 🔗 Cross-Cutting ADRs (Affect All Layer 5 Modules)

### **Architecture & Design**
- **ADR-0004** — 52-Module 5-Layer Architecture (Layer 5 definition)
- **ADR-0004b** — Import Linting (L5→none, leaf layer)
- **ADR-0004d** — Layer 5 Integration Tests

### **Observability**
- **ADR-0029** — Prometheus Metrics (50+ metrics across all layers)
- **ADR-0030** — Trace Sampling (cognitive_trace_id propagation, 1% sampling)

### **Performance & Reliability**
- **ADR-0024** — Performance Budgets (Layer 5: Event bus <5ms, Circuit breaker <10ms, Thermal <10ms)
- **ADR-0009** — Circuit Breaker (resilience across all K1 components)
- **ADR-0026** — Thermal Management (device-wide thermal monitoring)
- **ADR-0027** — Model Placement Cascade (4-tier fallback)

### **K0 Integration**
- **ADR-0001** — K0 Integration (20 pipelines, 4 external ports)
- **ADR-0001a** — K0 Bridge Architecture (dual-protocol, lane processing)
- **ADR-0001f** — SessionState Delta Batching (250ms batching)

---

## 🎯 Layer 5 Performance Budget Breakdown

### **Total Layer 5 Budget: Varies by component**

| Component | Budget | Typical | P95 | ADR |
|-----------|--------|---------|-----|-----|
| K0 Command (GREEN) | 50ms | 30ms | 50ms | ADR-0001a |
| K0 Command (AMBER/RED) | 200ms | 120ms | 200ms | ADR-0001a |
| K0 Query | 100ms | 60ms | 100ms | ADR-0001a |
| SSE event delivery | 5ms | 3ms | 5ms | ADR-0016 |
| SessionState batch | 10ms | 5ms | 10ms | ADR-0001f |
| Circuit breaker check | 10ms | 5ms | 10ms | ADR-0009 |
| Retry decision | 5ms | 3ms | 5ms | ADR-0008b |
| Thermal placement | 10ms | 5ms | 10ms | ADR-0026 |
| Temperature read | 5ms | 3ms | 5ms | ADR-0026 |
| Event bus delivery | 5ms | 3ms | 5ms | ADR-0004a |
| Metric emission | 10ms | 5ms | 10ms | ADR-0029 |
| Trace span creation | 5ms | 3ms | 5ms | ADR-0030 |
| Log write | 5ms | 3ms | 5ms | ADR-0002d |
| Config load | 50ms | 30ms | 50ms | ADR-0009b |

---

## 🔄 Layer 5 Integration Points

### **Layer 5 ← Layer 1/2/3/4 (Infrastructure Services)**

```
All layers call:                Layer 5 provides:
───────────────                ────────────────
K0 writes               →      bridge_k0/command_client
K0 reads                →      bridge_k0/query_client
Event pub/sub           →      event_bus/event_bus
Circuit breaker         →      resilience/circuit_breaker
Metrics                 →      observability/metrics
Tracing                 →      observability/tracing
Logging                 →      observability/logging
Thermal placement       →      thermal/placement_planner
Config access           →      config/loader
```

### **Layer 5 → K0 (External Dependency)**

```
Layer 5 calls:                  K0 provides:
──────────────                  ────────────
Command writes           →      K0 Command Port (:5200)
Query reads              →      K0 Query Port (:5201)
Event subscription       →      K0 SSE Port (:5202)
Observability push       →      K0 Observability Port (:5203)
```

**Key Constraints:**
1. **Leaf layer:** L5 imports nothing (no L5→L1/L2/L3/L4 imports)
2. **Cross-cutting:** All layers depend on L5 infrastructure
3. **External dependency:** L5 depends on K0 (dual-kernel architecture)

---

## 🧪 Layer 5 Testing Strategy (ADR-0004d)

### **Integration Tests**

**Location:** `tests/integration/layer5/`

1. **K0 Bridge Tests:**
   - Command client (write operations, <50ms GREEN, <200ms AMBER/RED)
   - Query client (multi-store retrieval, <100ms)
   - SSE client (event streaming, <5ms delivery)
   - Batch client (delta batching, 250ms interval)
   - Observability client (metric/log push)

2. **Resilience Tests:**
   - Circuit breaker (3-state FSM, failure detection, fallback cascade)
   - Retry policy (exponential backoff, jitter, max 5 retries)
   - Hot reload (config updates, <100ms reload)

3. **Thermal Tests:**
   - Placement planner (4-tier cascade, thermal zones)
   - Temperature monitor (1 Hz polling, alert thresholds)
   - Emergency jump (CRITICAL → Remote, <50ms)

4. **Event Bus Tests:**
   - Pub/sub delivery (<5ms, FIFO ordering)
   - Backpressure (subscriber queue depth 50, overflow policies)
   - Multiple subscribers (fan-out, zero-copy)

5. **Observability Tests:**
   - Metrics (50+ metrics, <10ms emission)
   - Tracing (span creation, 1% sampling, cognitive_trace_id propagation)
   - Logging (structured JSON, 6 event types, <5ms write)

6. **Config Tests:**
   - Config loader (YAML parsing, schema validation)
   - Hot reload (file watcher, <100ms reload)

7. **End-to-End Tests:**
   - Full K1→K0 round trip (write → read → event)
   - Performance: <200ms P95 (GREEN), <500ms P95 (AMBER/RED)

---

## 📊 Layer 5 Observability (ADR-0029)

### **Prometheus Metrics**

| Metric | Type | Labels | Description | ADR |
|--------|------|--------|-------------|-----|
| `layer5_k0_command_latency_ms` | Histogram | band (GREEN/AMBER/RED), command_type | K0 Command Port latency | ADR-0029 |
| `layer5_k0_query_latency_ms` | Histogram | query_type | K0 Query Port latency | ADR-0029 |
| `layer5_sse_event_rate` | Counter | event_type | SSE event delivery rate | ADR-0029 |
| `layer5_batch_size` | Histogram | - | SessionState batch size | ADR-0029 |
| `layer5_circuit_breaker_state` | Gauge | target | Circuit breaker state (0=CLOSED, 1=OPEN, 2=HALF_OPEN) | ADR-0029 |
| `layer5_retry_attempts` | Counter | target, attempt (1-5) | Retry attempts | ADR-0029 |
| `layer5_thermal_temperature_celsius` | Gauge | device (NPU/GPU/CPU) | Device temperature | ADR-0029 |
| `layer5_thermal_placement_decisions` | Counter | placement (NPU/GPU/CPU/Remote) | Placement decisions | ADR-0029 |
| `layer5_event_bus_delivery_ms` | Histogram | topic | Event bus delivery latency | ADR-0029 |
| `layer5_event_bus_backpressure_events` | Counter | subscriber | Backpressure events | ADR-0029 |
| `layer5_metric_emission_ms` | Histogram | - | Metric emission latency | ADR-0029 |
| `layer5_trace_span_creation_ms` | Histogram | span_type | Span creation latency | ADR-0029 |
| `layer5_log_write_ms` | Histogram | level (DEBUG/INFO/WARN/ERROR) | Log write latency | ADR-0029 |
| `layer5_config_reload_latency_ms` | Histogram | config_file | Config reload latency | ADR-0029 |
| `layer5_k0_connection_pool_hit_rate` | Gauge | - | Connection pool hit rate | ADR-0029 |

### **Grafana Dashboards**

**Layer 5 Overview Dashboard:**
- K0 Bridge (command/query latency, success rate, batch efficiency)
- Resilience (circuit breaker state, retry rate, hot reload events)
- Thermal (device temperature, placement decisions, emergency jumps)
- Event Bus (event rate, delivery latency, backpressure)
- Observability (metric emission, trace sampling, log volume)

---

## 🚀 Layer 5 Implementation Roadmap

### **Phase 1: K0 Bridge (Weeks 1-4)**
- Command client (write operations)
- Query client (multi-store retrieval)
- SSE client (event streaming)
- Batch client (delta batching)
- Observability client (metric/log push)
- Integration tests

### **Phase 2: Resilience (Weeks 5-7)**
- Circuit breaker (3-state FSM)
- Retry policy (exponential backoff)
- Hot reload (config file watcher)
- Integration tests

### **Phase 3: Thermal & Event Bus (Weeks 8-10)**
- Thermal placement planner (4-tier cascade)
- Temperature monitor (1 Hz polling)
- Event bus (pub/sub, zero-copy)
- Integration tests

### **Phase 4: Observability (Weeks 11-13)**
- Prometheus metrics (50+ metrics)
- OpenTelemetry tracing (1% sampling)
- Structured logging (JSON format)
- Grafana dashboards (7 dashboards)
- Integration tests

### **Phase 5: Config & Connectors (Weeks 14-15)**
- Config loader (YAML parsing)
- Schema validator (JSON schema)
- K0 connector (connection lifecycle)
- Integration tests

### **Phase 6: Hardening & Performance (Weeks 16-18)**
- Performance tuning (<5ms event bus, <10ms circuit breaker)
- Load testing (1000 events/sec, 100 K0 writes/sec)
- Chaos engineering (K0 unavailability, thermal throttling)
- Documentation

---

## 📚 Complete ADR Reference List

### **Primary Layer 5 ADRs**
- ADR-0004 — 52-Module 5-Layer Architecture
- ADR-0001a — K0 Bridge Architecture
- ADR-0029 — Prometheus Metrics
- ADR-0009 — Circuit Breaker
- ADR-0026 — Thermal Management
- ADR-0004a — Event Bus

### **K0 Bridge ADRs (Category 1)**
- ADR-0001 — K0 Integration (20 pipelines, 4 external ports)
- ADR-0001f — SessionState Delta Batching (250ms batching)
- ADR-0016 — SSE Event Schemas (K0→K1 events)
- ADR-0024 — Performance Budgets (K0 Bridge <50ms GREEN, <200ms AMBER/RED)

### **Resilience ADRs (Category 2)**
- ADR-0009a — Circuit State Transitions (failure threshold, cooldown)
- ADR-0009b — Hot Reload (dynamic config updates)
- ADR-0009c — Fallback Cascade (primary → fallback routing)
- ADR-0008b — Saga Retry Policy (max 5 retries, exponential backoff)

### **Thermal ADRs (Category 3)**
- ADR-0027 — Model Placement Cascade (NPU→GPU→CPU→Remote)

### **Event Bus ADRs (Category 4)**
- ADR-0004a — Event Bus (Layer 1-2 communication, pub/sub, zero-copy)

### **Observability ADRs (Category 5)**
- ADR-0030 — Trace Sampling (cognitive_trace_id, 1% sampling)
- ADR-0002d — Actor Fabric Observability (mailbox, router, supervisor metrics)

### **Config ADRs (Category 6)**
- ADR-0009b — Hot Reload (config file monitoring)

### **Cross-Cutting ADRs**
- ADR-0004b — Import Linting (L5→none, leaf layer)
- ADR-0004d — Layer 5 Integration Tests
- ADR-0011 — FlatBuffers Serialization (optional K0 Bridge optimization)
- ADR-0024 — Performance Budgets

---

**Status:** ✅ **COMPLETE** — All Layer 5 ADRs mapped end-to-end
**Last Updated:** January 2025
**Total ADRs:** 25+ ADRs covering Layer 5 (7 primary + 18 supporting)
**Coverage:** 100% of Layer 5 modules (19/19 modules mapped across 6 categories)
