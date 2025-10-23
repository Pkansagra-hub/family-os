# Layer 5 (Infrastructure) — ADR Family Map

**Complete end-to-end ADR references for K1 Layer 5 modules**

---

## 📋 Overview

**Layer 5 Purpose:** Infrastructure (Event Bus, Observability, Resilience, Thermal, K0 Bridge, Config)
**Performance Budget:** <5ms event bus delivery, <10ms circuit breaker, <10ms thermal placement
**Total ADRs:** 165 ADRs (100% coverage)
**Modules:** 19 modules across 6 categories
**Primary Function:** Cross-cutting infrastructure services for all K1 layers

---

## 🗺️ Layer 5 Architecture

### Core ADRs (Foundation)

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

## 📊 ADR Statistics

**Total Layer 5 ADRs:** 166 (100% coverage)

### By Category

- **K0 Bridge (bridge_k0/):** 58 ADRs across 5 modules
- **Resilience (resilience/):** 21 ADRs across 3 modules
- **Thermal (thermal/):** 18 ADRs across 2 modules
- **Event Bus (event_bus/):** 12 ADRs across 2 modules
- **Observability (observability/):** 33 ADRs across 4 modules (includes ADR-0086h for agent metrics)
- **Config & Connectors:** 24 ADRs across 3 modules

### By Family

- **K0 Bridge:** 31 ADRs (K0 communication)
- **Circuit Breaker:** 13 ADRs (Resilience)
- **Thermal Management:** 18 ADRs (Device placement)
- **Prometheus Metrics:** 16 ADRs (Observability, includes ADR-0086h)
- **Backpressure:** 16 ADRs (Flow control)
- **Other Families:** 72 ADRs (Various infrastructure)

---

## 📁 Category 1: bridge_k0/ (K1→K0 Connection Layer)

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
- **ADR-0042** — K0 SSE Event Streaming (durable events foundation)
- **ADR-0042a** — Event Production (WAL reader, fanout manager)
- **ADR-0042b** — Event Consumption (K1 SSE subscriber, cursor tracking)
- **ADR-0042c** — Reconnection (cursor-based resume, exponential backoff)
- **ADR-0042d** — Backpressure (slow consumer detection, disconnect)
- **ADR-0042e** — Device Tiers (mobile/desktop/cloud storage)

#### Related ADRs

- **ADR-0024** — Performance Budgets (SSE delivery <5ms)
- **ADR-0029** — Prometheus Metrics (event rate, subscription count)
- **ADR-0043** — SSE Topic Taxonomy (K0 durable topics)
- **ADR-0043a** — Topic Hierarchy (hierarchical naming, wildcards)
- **ADR-0043b** — Subscription Patterns (exact/wildcard/filters)
- **ADR-0043c** — Topic Routing (at-least-once delivery, fanout)
- **ADR-0043d** — Topic Access Control (4-level ACL, scoping)

#### Key Responsibilities

1. **SSE Port Integration:**
   - HTTP GET to K0 SSE Port (`:5202/v1/events`)
   - EventSource client (SSE protocol)
   - Event types: MEMORY_WRITTEN, CONSOLIDATION_COMPLETE, SYNC_STATUS

2. **Event Subscription:**
   - Topic-based filtering (subscribe to specific event types)
   - Server-side filtering (K0 filters before sending)
   - Reconnection logic (exponential backoff)
   - Cursor-based resume (Last-Event-ID pattern)
   - At-least-once delivery guarantee

3. **Event Delivery:**
   - Push events to K1 event bus
   - <5ms delivery latency
   - Ordering guarantee (per-topic FIFO)
   - Backpressure management (disconnect slow consumers)

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
- **ADR-0022** — K0 Bridge Batching (batching core)
- **ADR-0022a** — Batching Algorithm (batch size, timeout, fairness)
- **ADR-0022b** — HTTP/2 Integration (connection pooling, multiplexing)
- **ADR-0022c** — Backpressure (queue depth, drop oldest)
- **ADR-0022d** — FlatBuffers Schema (compression, zero-copy batch)

#### Related ADRs

- **ADR-0024** — Performance Budgets (batching <10ms)
- **ADR-0029** — Prometheus Metrics (batch size, batching latency)

#### Key Responsibilities

1. **Delta Batching:**
   - Batch SessionState updates every 250ms
   - Compute field-level deltas (field_path, old_value, new_value)
   - Example: `control.current_flow` changed from `null` to `flow_abc123`
   - 3-trigger flush: Time 250ms OR size 64KB OR count 100

2. **Batch Processing:**
   - Coalesce redundant updates (same field updated multiple times)
   - Deduplicate deltas (keep latest value)
   - Batch size: 10-50 deltas typical (adaptive sizing)
   - Fairness queue: Round-robin per session (max 5 messages/session/batch)

3. **K0 Integration:**
   - Send batched deltas to K0 P02 MemoryWrite pipeline
   - Receipt validation (WAL offset confirmation)
   - Error handling: Retry failed batches
   - Compression: zstd level 3 for batches >1KB (2-3× reduction)

**Performance Metrics:**

- Batch interval: 250ms
- Batch size: 10-50 deltas typical
- Batch processing: <10ms P95
- Batching efficiency: 80% reduction in K0 writes
- Throughput: 5000+ msgs/sec batched (vs 100 individual)

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

### **Module 1.6: bridge_k0/http2_client/ (Supporting ADRs)**

**Purpose:** HTTP/2 transport layer for K0 Bridge
**Location:** `k1/bridge_k0/http2/`

#### Primary ADRs

- **ADR-0044** — K0 Bridge HTTP/2 (bridge client core)
- **ADR-0044a** — Transport Protocol (HTTP/2 connection, multiplexing)
- **ADR-0044b** — Serialization (FlatBuffers schema, zero-copy)
- **ADR-0044c** — Batching (multi-trigger batching, compression)
- **ADR-0044d** — Error Handling (exponential backoff, circuit breaker)

#### Key Components

1. **HTTP/2 Connection Manager:**
   - 1 persistent connection per K0 port (5 ports total)
   - Max 100 concurrent streams per connection
   - PING frames every 10s (keep-alive)
   - TLS 1.3 mutual authentication

2. **Stream Multiplexing:**
   - Binary framing (efficient protocol)
   - Header compression (HPACK)
   - Flow control per stream
   - <10ms round-trip vs 50ms HTTP/1.1

3. **Batching Strategy:**
   - Time-bounded (250ms), size-bounded (64KB), count-bounded (50 items)
   - Per-session cooldown (min 50ms between flushes)
   - Priority-based overflow (drop oldest BACKGROUND tasks)
   - zstd compression for payloads >4KB

4. **Error Handling:**
   - Exponential backoff retry (1s → 2s → 4s → 8s → 16s max)
   - Circuit breaker (3 failures → OPEN, 30s timeout)
   - Idempotency keys (write safety)
   - Dead letter queue (3 retries exhausted, 7-day retention)

**Performance Metrics:**

- Connection establishment: <100ms P95
- Round-trip latency: <10ms (vs 50ms HTTP/1.1)
- Connection pool hit rate: >90%
- Batch efficiency: 98% request reduction (50:1 ratio)

---

## 📁 Category 2: resilience/ (Circuit Breaker & Retry)

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

4. **Hot Reload:**
   - Monitor config files (circuit_breaker.yaml, retry_policy.yaml)
   - Detect changes (file modification events)
   - Apply changes without restart (<100ms)

5. **Observability:**
   - Prometheus metrics: state gauge, transitions counter, calls counter, failures counter, fallbacks counter, latency histogram
   - Structured logging: 4 log events (opened, closed, transition, fallback)
   - Grafana dashboards: state timeline, failure rate, latency P95
   - Alerts: stuck OPEN 5m, flapping 10/5m, success <50%, timeout >10/min, fallback >50%

**Performance Metrics:**

- Circuit check: <10ms P95
- Failure detection: <20ms
- State transition: <5ms
- Cascade success rate: >99%
- Config reload: <100ms P95

---

### **Module 2.2: resilience/retry_policy/**

**Purpose:** Retry policies (exponential backoff)
**Location:** `k1/l5_infrastructure/resilience/retry_policy.py`
**Performance:** <5ms retry decision

#### Primary ADRs

- **ADR-0008b** — Saga Retry Policy (max 5 retries, exponential backoff, jitter)

#### Related ADRs

- **ADR-0024** — Performance Budgets (retry decision <5ms)
- **ADR-0008a** — Idempotency (Redis integration, duplicate prevention)
- **ADR-0008c** — Distributed State (K0 persistence, saga log)

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

3. **Idempotency Integration:**
   - Redis GET/SETEX for duplicate detection
   - 5-minute TTL per operation
   - <1ms latency check

4. **Audit Trail:**
   - K0 WAL logging for saga compensation
   - CompensationLog FlatBuffers schema
   - 7-day retention, <5ms write

**Performance Metrics:**

- Retry decision: <5ms P95
- Retry success rate: >80% (2nd attempt)
- Total retry latency: 100ms-10s (depends on backoff)
- Idempotency check: <1ms

---

### **Module 2.3: resilience/hot_reload/**

**Purpose:** Config hot reload (asyncio file watcher)
**Location:** `k1/l5_infrastructure/resilience/hot_reload.py`
**Performance:** <100ms reload latency

#### Primary ADRs

- **ADR-0009b** — Hot Reload (file watcher, asyncio reload)
- **ADR-0080** — Config Hot-Reload (change detection, validator, rollback)

#### Related ADRs

- **ADR-0024** — Performance Budgets (config reload <100ms)

#### Key Responsibilities

1. **File Watcher:**
   - Monitor config files (circuit_breaker.yaml, retry_policy.yaml, etc.)
   - Detect changes (file modification events)
   - Trigger reload
   - watchdog library integration

2. **Config Reload:**
   - Parse updated config files
   - Validate new config (JSON schema + semantic validation)
   - Apply changes without restart (<100ms)
   - Atomic updates (zero-downtime)

3. **Validation:**
   - JSON schema validation (structure, types, constraints)
   - Semantic validation (config-specific logic)
   - <50ms P95 validation latency

4. **Rollback:**
   - Automatic rollback on error
   - Restore previous state
   - <200ms rollback latency
   - Audit trail with trace_id

**Performance Metrics:**

- Reload latency: <100ms P95
- Reload frequency: <1/hour typical
- Detection latency: <100ms (file change → reload trigger)
- Validation: <50ms P95
- Rollback: <200ms

---

## 📁 Category 3: thermal/ (Thermal Management)

### **Module 3.1: thermal/placement_planner/**

**Purpose:** Thermal-aware model placement (NPU→GPU→CPU→Remote)
**Location:** `k1/l5_infrastructure/thermal/placement_planner.py`
**Performance:** <10ms placement decision

#### Primary ADRs

- **ADR-0026** — Thermal Management (hysteresis matrix, 4-tier placement)
- **ADR-0026a** — Thermal Zones (5 zones: COOL/WARM/HOT/CRITICAL/EMERGENCY)
- **ADR-0026b** — Hysteresis FSM (state transitions, dead zone, persistence)
- **ADR-0026c** — Hysteresis Matrix (asymmetric thresholds, cooldown periods)
- **ADR-0026d** — Throttling (HOT/CRITICAL/EMERGENCY state degradation)
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
   - Temperature zones: COOL (<70°C), WARM (70-74°C), HOT (75-84°C), CRITICAL (85-95°C), EMERGENCY (>95°C)
   - Hysteresis matrix: Asymmetric thresholds (upgrade +5°C, downgrade -2°C, 7°C band)
   - Cooldown periods: Upgrade 10s, downgrade 30-60s (3:1 to 6:1 ratio)
   - Emergency jump: CRITICAL → Remote (immediate, skip GPU/CPU)

3. **Hysteresis FSM:**
   - 5°C buffer prevents oscillation
   - Upward transition >threshold+5°C, downward transition <threshold-5°C
   - Dead zone: Temperatures in zone maintain current state (no rapid switching)
   - State persistence: Minimum 10-second duration (exception: EMERGENCY)

4. **Placement Decision:**
   - Monitor device temperature (1 Hz polling)
   - Choose accelerator based on thermal zone
   - State-aware policies: COOL/WARM (all), HOT (GPU/CPU/Remote), CRITICAL (CPU/Remote), EMERGENCY (Remote only)
   - Automatic failover: Running models migrate on thermal state change
   - KV cache transfer <30ms, model loading <50ms, <100ms total failover

5. **Throttling:**
   - **HOT State:** Increase batch interval 20% (100ms → 120ms), defer background tasks
   - **CRITICAL State:** Skip persona/grounding/vision processing, simplified responses
   - **EMERGENCY State:** Reject new turns, notify user "Device cooling down", Remote only

**Performance Metrics:**

- Placement decision: <10ms P95
- Thermal polling: 1 Hz
- Temperature read: <5ms P95
- Failover latency: <100ms (detection 20ms + transfer 30ms + loading 50ms)
- Emergency jump: <50ms (CRITICAL → Remote)

---

### **Module 3.2: thermal/monitor/**

**Purpose:** Device temperature monitoring
**Location:** `k1/l5_infrastructure/thermal/monitor.py`
**Performance:** <5ms temperature read

#### Primary ADRs

- **ADR-0026** — Thermal Management (monitoring integration)
- **ADR-0026a** — Thermal Zones (sensor monitoring, state detection)

#### Key Responsibilities

1. **Temperature Monitoring:**
   - Poll NPU/GPU/CPU temperature sensors (1 Hz)
   - Thermal zones: COOL, WARM, HOT, CRITICAL, EMERGENCY
   - Alert on CRITICAL (≥85°C)
   - Multi-sensor aggregation (max temperature rule)

2. **Cross-Platform Support:**
   - Linux thermal zones (/sys/class/thermal/)
   - Windows WMI
   - macOS IOKit
   - Graceful degradation on sensor failure

3. **Metrics Emission:**
   - Push temperature metrics to Prometheus
   - Alert thresholds: HOT (75°C), CRITICAL (85°C)
   - thermal_state gauge (0-4 enum)
   - thermal_temperature_celsius gauge

**Performance Metrics:**

- Temperature read: <5ms P95
- Polling frequency: 1 Hz
- Alert latency: <100ms
- State detection: <0.2ms (zone classification)

---

## 📁 Category 4: event_bus/ (Internal Event Bus)

### **Module 4.1: event_bus/event_bus/**

**Purpose:** Layer 1→2 event bus (pub/sub)
**Location:** `k1/l5_infrastructure/event_bus/event_bus.py`
**Performance:** <5ms event delivery

#### Primary ADRs

- **ADR-0004a** — Event Bus (Layer 1-2 communication, pub/sub, zero-copy)
- **ADR-0048** — K1 Internal Event Bus (in-memory pub/sub, k1.* namespace)

#### Related ADRs

- **ADR-0024** — Performance Budgets (event bus <5ms)
- **ADR-0029** — Prometheus Metrics (event rate, subscription count, delivery latency)

#### Key Responsibilities

1. **Pub/Sub Pattern:**
   - Topic-based routing (INTENT_DETECTED, USER_INPUT, VOICE_COMMAND, BARGE_IN)
   - Multiple subscribers per topic
   - Async delivery (asyncio.Queue per subscriber)
   - 1-to-N fanout broadcast

2. **Event Delivery:**
   - Zero-copy: Pass references (no serialization)
   - <5ms delivery latency (<2ms typical)
   - Ordering: FIFO per topic
   - 1000s events/sec throughput

3. **Backpressure:**
   - Subscriber queue depth: 50 max (1000 for K1 internal)
   - Overflow: DROP_OLDEST policy
   - Slow subscriber detection: >100ms processing time (>90% full queue)
   - Graceful degradation

4. **K0/K1 Separation:**
   - 100% K1-internal (no K0 boundary crossing)
   - No K0 storage writes
   - No K0 SSE fanout
   - Ephemeral events only (no persistence)

**Performance Metrics:**

- Event delivery: <5ms P95 (<2ms typical, <1ms per event)
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

## Category 5: observability/ (Metrics, Tracing, Logging)

### **Module 5.1: observability/metrics/**

**Purpose:** Prometheus metrics exporter
**Location:** `k1/l5_infrastructure/observability/metrics.py`
**Performance:** <10ms metric emission

#### Primary ADRs

- **ADR-0029**  Prometheus Metrics (50+ metrics across all layers)
- **ADR-0029a**  RED Method (rate, error, duration metrics)
- **ADR-0029d**  Infrastructure (thermal, CPU, cost metrics)
- **ADR-0029e**  Alerting (SLO alerts, routing, dashboards)
- **ADR-0002d**  Actor Fabric Observability (mailbox, router, supervisor metrics)

#### Related ADRs

- **ADR-0024**  Performance Budgets (metric emission <10ms)

#### Key Responsibilities

1. **Metric Types:**
   - **Counters:** agent_hire_count, tool_execution_count, crash_count
   - **Gauges:** mailbox_depth, active_agent_count, kv_cache_hit_rate
   - **Histograms:** layer1_latency_ms, model_hub_inference_ms, tool_execution_ms

2. **Metric Emission:**
   - Push to Prometheus (HTTP POST to `:9091/metrics`)
   - Scrape interval: 10s
   - <10ms emission overhead (<1% CPU)

3. **Metrics Catalog (50+ metrics):**
   - **Layer 1 (5 metrics):** TTFT, VAD latency, intent classification latency
   - **Layer 2 (8 metrics):** Planning latency, orchestration latency, protocol validation
   - **Layer 3 (12 metrics):** Agent lifecycle, Model Hub inference, tool execution
   - **Layer 4 (10 metrics):** SessionState size, mailbox depth, learning cycle
   - **Layer 5 (15 metrics):** Event bus delivery, thermal temperature, circuit breaker state

4. **RED Method:**
   - **Rate:** Requests per second (15 rate counters)
   - **Error:** Errors per second (15 error counters)
   - **Duration:** P50/P95/P99 latency (15 histogram metrics)

5. **Infrastructure Metrics:**
   - **Thermal:** thermal_state gauge (0-4), thermal_temperature_celsius, throttling events
   - **CPU:** cpu_utilization_percent gauge, per-core tracking, throttling detection
   - **Cost:** cost_per_turn_usd histogram, budget_exceeded counter, monthly burn rate

6. **Alerting:**
   - **SLO Alerts:** 10 alert rule groups (TTFT >157ms, E2E >2100ms, Error >1%)
   - **Alert Routing:** CRITICALPagerDuty, WARNINGSlack, INFOGrafana
   - **Dashboards:** 4 dashboards (Turn Overview, Component Health, Infrastructure, Incident Response)

**Performance Metrics:**

- Metric emission: <10ms P95
- Scrape interval: 10s
- Metric overhead: <1% CPU
- Total metrics: 50+

---

### **Module 5.1b: observability/agent_metrics/**

**Purpose:** Dynamic agent metrics & observability
**Location:** `k1/l5_infrastructure/observability/agent_metrics.py`
**Performance:** <1ms metric emission

#### Primary ADRs

- **ADR-0086h**  Agent Metrics & Observability (25+ Prometheus metrics, OpenTelemetry tracing, 3 Grafana dashboards)

#### Related ADRs

- **ADR-0029**  Prometheus Metrics (base metrics framework)
- **ADR-0030**  Trace Sampling (tracing integration)

#### Key Responsibilities

1. **Agent Creation Metrics (25+ metrics):**
   - **Creation:** agent_created_total (counter), creation_latency_ms (5 phases: validation, reservation, template, spawn, register)
   - **Termination:** agent_terminated_total, termination_latency_ms
   - **Reuse:** agent_reused_total (IDLE pool hits)
   - **Performance:** reactivation_latency_ms (<10ms target), creation_latency_ms (<100ms target)
   - **Resources:** agent_memory_mb, agent_accelerator_slots (NPU/GPU/CPU/Remote)
   - **Agent Count:** agent_count_by_type (58+ types), agent_count_by_state (PENDING/WARMING/ACTIVE/IDLE/DRAINING/TERMINATED)
   - **IDLE Pool:** idle_pool_size, idle_pool_hit_total, idle_pool_miss_total, idle_duration_seconds
   - **State Transitions:** state_transitions_total (6 states × 6 states = 36 transitions), state_transition_latency_ms
   - **Errors:** errors_total (6 categories: resource_exhausted, template_invalid, creation_failed, reactivation_failed, composition_failed, termination_failed)
   - **Registry:** registry_size (58+ agent types), registry_query_latency_ms

2. **OpenTelemetry Tracing:**
   - 4-level span hierarchy: agent.create → agent.reserve → agent.compose → agent.spawn
   - Span attributes: agent_id, agent_type, session_id, resource_type, template_version
   - <1ms span creation overhead

3. **Grafana Dashboards (3 dashboards):**
   - **Agent Performance:** Creation/reactivation latency, IDLE pool hit rate, state transitions
   - **Resource Utilization:** Memory usage, accelerator allocation, resource exhaustion events
   - **Lifecycle Health:** Active agent count by type, termination reasons, error rates

4. **Cardinality Management:**
   - <10K active time series (agent_id cardinality bounded by 100 concurrent agents)
   - agent_type dimension: 58+ types (bounded set)
   - state dimension: 6 states (fixed)

**Performance Metrics:**

- Metric emission: <1ms P95 (minimal overhead)
- Span creation: <1ms P95
- Total agent metrics: 25+
- Cardinality: <10K time series

---

### **Module 5.2: observability/tracing/**

**Purpose:** OpenTelemetry distributed tracing
**Location:** `k1/l5_infrastructure/observability/tracing.py`
**Performance:** <5ms span creation

#### Primary ADRs

- **ADR-0030**  Trace Sampling (cognitive_trace_id, 1% sampling)
- **ADR-0030a**  Head-Based Sampling (baseline 1%, error 100%, slow 100%)
- **ADR-0030b**  Tail-Based Sampling (span buffering, post-decision)
- **ADR-0030c**  Adaptive Sampling (rate adjustment FSM, health indicators)
- **ADR-0030d**  Jaeger Integration (OTLP exporter, Badger storage)
- **ADR-0002d**  Actor Fabric Observability (actor.send/recv spans)

#### Related ADRs

- **ADR-0024**  Performance Budgets (tracing <5ms)

#### Key Responsibilities

1. **Span Creation:**
   - OpenTelemetry spans (start, end, attributes)
   - Span types: actor.send, actor.recv, router.admission, mailbox.enq, mailbox.deq
   - cognitive_trace_id propagation (128-bit unique ID)
   - W3C Trace Context format

2. **Trace Sampling:**
   - **Baseline:** 1% random sampling (hash-based decision <0.2ms)
   - **Error:** 100% error sampling (turn_status==ERROR)
   - **Slow Request:** 100% sampling for >P95 latency (TTFT >150ms, E2E >2000ms)
   - **Privacy Band:** 100% RED band sampling (audit compliance)

3. **Tail-Based Sampling:**
   - 60s span buffer (<50MB memory)
   - Decision after turn completion (<100ms latency)
   - KEEP (export) or DISCARD (drop)
   - TTL-based eviction for overflow protection

4. **Adaptive Sampling:**
   - 3 states: NORMAL (1%), DEGRADATION (10%), CRITICAL (50%)
   - Health-based triggers: TTFT/error rate/backpressure
   - Gradual recovery: 50%25%10%5%1%
   - Hysteresis: 10% margin (prevent oscillation)

5. **Trace Export:**
   - Export to Jaeger/Zipkin (OTLP protocol)
   - Batch export: Every 5s, max 100 spans per batch
   - gRPC OTLP (localhost:4317)
   - Non-blocking async export (<5ms latency)

6. **Storage:**
   - **Hot:** 7 days (all sampled traces)
   - **Warm:** 30 days (errors/SLO violations/RED band)
   - **Cold:** >30 days to S3 (optional)
   - Cost target: <$50/month (97% reduction vs 100% tracing)

**Performance Metrics:**

- Span creation: <5ms P95
- Sampling rate: 1% (normal), 100% (errors)
- Trace export: <50ms per batch
- Storage volume: 25MB/day (175MB hot, 750MB warm)

---

### **Module 5.3: observability/logging/**

**Purpose:** Structured logging (JSON format)
**Location:** `k1/l5_infrastructure/observability/logging.py`
**Performance:** <5ms log write

#### Primary ADRs

- **ADR-0002d**  Actor Fabric Observability (structured logs, 6 event types)

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

- **ADR-0029**  Prometheus Metrics (dashboard integration)
- **ADR-0002d**  Actor Fabric Observability (mailbox, router, supervisor dashboards)
- **ADR-0029e**  Alerting (Turn Overview, Component Health, Infrastructure, Incident Response)

#### Key Responsibilities

1. **Dashboard Catalog (7 dashboards):**
   - **K1 Overview:** Layer latencies, agent lifecycle, tool execution
   - **Layer 1 Dashboard:** TTFT, VAD latency, intent classification
   - **Layer 2 Dashboard:** Planning latency, orchestration latency, protocol validation
   - **Layer 3 Dashboard:** Agent lifecycle, Model Hub inference, tool execution
   - **Layer 4 Dashboard:** SessionState size, mailbox depth, learning cycle
   - **Layer 5 Dashboard:** Event bus delivery, thermal temperature, circuit breaker state
   - **Actor Fabric Dashboard:** Mailbox health, admission control, supervisor, message flow

**Total Dashboards:** 7 dashboards

---

## Category 6: Backpressure & Performance

### **Backpressure ADRs (Cross-cutting)**

#### Primary ADRs

- **ADR-0039a**  Tier Triggers (watermark thresholds, hysteresis buffer)
- **ADR-0039b**  Signal Propagation (actor model messaging, tier priority)
- **ADR-0039c**  Recovery (stepwise gradual resume, health checks)
- **ADR-0061**  Backpressure (3-tier cascade core)
- **ADR-0061a**  Watermark Thresholds (80/90/95%, hysteresis, thermal integration)
- **ADR-0061b**  RED Metrics & Alerts (Prometheus, rate/error/duration, Grafana)
- **ADR-0061c**  Privacy Band Overrides (RED band bypass, emergency paths)
- **ADR-0061d**  Fairness & Anti-Starvation (WFQ scheduler, aging policies)
- **ADR-0057**  Voice Backpressure (3-tier cascade, ASR/TTS integration)

#### Key Components

1. **3-Tier Cascade:**
   - **Tier 1:** Per-stream watermarks (80% warn, 90% degrade, 95% reject)
   - **Tier 2:** Voice pipeline monitoring (ASR frame drop, TTS degradation)
   - **Tier 3:** Global limits enforcement (512MB memory, 5000 queue items)

2. **Watermark Thresholds:**
   - 10% hysteresis (prevents oscillation)
   - Overflow actions: drop_oldest, block_sender, merge_deltas, disconnect_slow
   - Recovery time: 5s/10s/30s (by tier)

3. **Signal Propagation:**
   - Event-based backpressure propagation (<50ms guarantee)
   - BackpressureSignal FlatBuffers broadcast
   - Tier priority: EMERGENCY > REJECT_NEW > CANCEL_BACKGROUND

4. **Recovery:**
   - Stepwise: Tier 321Normal (one step at a time)
   - Sustained stability: 10-30s below deactivation watermarks
   - Rate limiting: 10% admission increase every 5s
   - ~2min total recovery

5. **Privacy Band Overrides:**
   - RED band bypass logic (arbiter approval, emergency safety always pass)
   - AMBER degradation (local only, no remote fallback)
   - GREEN rejection (503 Service Unavailable at capacity)

6. **Fairness:**
   - WFQ (Weighted Fair Queuing) scheduler
   - Priority levels 1-5, quantum allocation
   - Aging policies: Wait time >10s  automatic escalation
   - Priority inheritance for blocked high-priority tasks

**Performance Metrics:**

- Backpressure check: <5ms overhead
- Signal propagation: <50ms P95
- Watermark breach detection: <20ms
- Recovery latency: ~2min (sustained)

---

## Category 7: Config, Connectors & Extensions

### **Module 7.1: config/loader/**

**Purpose:** YAML config loader
**Location:** `k1/l5_infrastructure/config/loader.py`
**Performance:** <50ms config load

#### Primary ADRs

- **ADR-0009b**  Hot Reload (config file monitoring)
- **ADR-0080**  Config Hot-Reload (change detection, validator, rollback)

#### Key Responsibilities

1. **Config Loading:**
   - Load YAML config files (kernel.yaml, logging.yaml, circuit_breaker.yaml)
   - Validate schema (JSON schema validation)
   - Merge configs (defaults + overrides)

2. **Hot Reload:**
   - Detect config file changes
   - Reload without restart (<100ms)
   - Zero-downtime config apply
   - Atomic updates

**Performance Metrics:**

- Config load: <50ms P95 (startup)
- Hot reload: <100ms P95

---

### **Module 7.2: config/schema_validator/**

**Purpose:** Config schema validation
**Location:** `k1/l5_infrastructure/config/schema_validator.py`
**Performance:** <10ms validation

#### Primary ADRs

- **ADR-0080**  Config Hot-Reload (ConfigValidator)

#### Key Responsibilities

1. **Schema Validation:**
   - JSON schema validation (Draft 7)
   - Validate config structure, types, constraints
   - Semantic validation (config-specific validators)
   - Error reporting (detailed validation errors)

**Performance Metrics:**

- Validation: <10ms P95 (<50ms budget)

---

### **Module 7.3: connectors/k0_connector/**

**Purpose:** K0 connection lifecycle management
**Location:** `k1/l5_infrastructure/connectors/k0_connector.py`
**Performance:** <100ms connection establishment

#### Primary ADRs

- **ADR-0001a**  K0 Bridge Architecture (connection management)
- **ADR-0044**  K0 Bridge HTTP/2 (bridge client)
- **ADR-0044a**  Transport Protocol (connection health, auto-reconnect)

#### Key Responsibilities

1. **Connection Lifecycle:**
   - Establish HTTP/2 connection to K0 (TLS 1.3)
   - Health check: Ping K0 every 10s
   - Reconnection: Exponential backoff (1s2s4s8s30s max)

2. **Connection Pooling:**
   - Connection pool: 5 connections (command, query, SSE, observability, health)
   - Keep-alive: 60s timeout
   - Connection reuse: >90% hit rate

**Performance Metrics:**

- Connection establishment: <100ms P95
- Reconnection latency: 1s-30s (exponential backoff)
- Connection pool hit rate: >90%

---

### **Module 7.4: extensions/ (Extension Points)**

**Purpose:** Layer 5 extensibility framework
**Location:** `k1/l5_infrastructure/extensions/`

#### Primary ADRs

- **ADR-0075**  Layer 5 Extensibility (9 extension points)
- **ADR-0074**  Module System (module discovery, loading)

#### Extension Points

1. **ConfigProvider:** Custom config sources, validation hooks
2. **MetricsExporter:** Prometheus/StatsD/CloudWatch exporters
3. **TraceExporter:** OpenTelemetry/Jaeger/Zipkin exporters
4. **LogHandler:** Structured logging, formatters, rotation
5. **ThermalPolicy:** Device thermal classification, cooling strategies
6. **PlacementStrategy:** Agent-to-device placement, load balancing
7. **CachePolicy:** KV cache compression, eviction, thermal adjustment
8. **BackpressureHandler:** Queue management, flow control, degradation
9. **ErrorInterceptor:** Error transformation, circuit breaker, retry
10. **HealthCheckProvider:** Health endpoints, liveness/readiness probes

---

## Cross-Cutting ADRs (Affect All Layer 5 Modules)

### **Architecture & Design**

- **ADR-0004**  52-Module 5-Layer Architecture (Layer 5 definition)
- **ADR-0004b**  Import Linting (L5none, leaf layer)
- **ADR-0004d**  Layer 5 Integration Tests

### **Observability**

- **ADR-0029**  Prometheus Metrics (50+ metrics across all layers)
- **ADR-0030**  Trace Sampling (cognitive_trace_id propagation, 1% sampling)

### **Performance & Reliability**

- **ADR-0024**  Performance Budgets (Layer 5: Event bus <5ms, Circuit breaker <10ms, Thermal <10ms)
- **ADR-0024a**  Turn-Level Budgets (TTFT <150ms, E2E <2000ms, Barge-in <120ms)
- **ADR-0024b**  Component-Level Budgets (Config reload <100ms)
- **ADR-0024c**  Memory Budgets (K1 <500MB P95, energy targets)
- **ADR-0024d**  Graceful Degradation (degradation manager, recovery policy)
- **ADR-0009**  Circuit Breaker (resilience across all K1 components)
- **ADR-0026**  Thermal Management (device-wide thermal monitoring)
- **ADR-0027**  Model Placement Cascade (4-tier fallback)

### **K0 Integration**

- **ADR-0001**  K0 Integration (20 pipelines, 4 external ports)
- **ADR-0001a**  K0 Bridge Architecture (dual-protocol, lane processing)
- **ADR-0001f**  SessionState Delta Batching (250ms batching)
- **ADR-0081**  Knowledge Graph (K0 Core integration)
- **ADR-0081a**  Knowledge Graph (graph schema, temporal edges)
- **ADR-0081b**  Knowledge Graph (query API, graph traversal)
- **ADR-0081c**  Knowledge Graph (episodic integration, entity extraction)
- **ADR-0081d**  Knowledge Graph (visualization, metrics)
- **ADR-0084**  K0 Memory Consolidation (3-layer pipeline, sleep coordination)
- **ADR-0084a**  Hippocampal Replay (pattern strengthening, CA3 recurrent)
- **ADR-0084b**  Sleep State Machine (idle detection, state orchestration)
- **ADR-0084c**  Knowledge Graph Consolidation (entity extraction, relationship inference)
- **ADR-0084d**  Dream Exploration (explorative dreaming, counterfactual thinking)

### **Serialization & Schemas**

- **ADR-0011**  FlatBuffers Serialization (zero-copy, <1ms P95)
- **ADR-0011a**  Schema Design (naming conventions, type system, forward compatibility)
- **ADR-0011b**  Code Generation (flatc compiler, Python/C++/Rust bindings)
- **ADR-0011c**  Performance (zero-copy access, SIMD optimization)
- **ADR-0011d**  Schema Evolution (version registry, backward/forward compatibility)
- **ADR-0012**  Schema Taxonomy (76 schemas, 9 categories)
- **ADR-0012e**  Layer 5 Schemas (ConfigSnapshot, MetricSample, ThermalPlacement, BackpressureSignal)
- **ADR-0013**  Schema Versioning (SemVer policy, 90-day deprecation)
- **ADR-0013a**  Version Registry (central registry, compatibility matrix)
- **ADR-0013b**  CI/CD Automation (schema diff analysis, version bump validation)
- **ADR-0013c**  Deprecation Workflow (runtime alerts, FlatBuffers annotations)
- **ADR-0013d**  Contract Testing (Pact-style tests, forward/backward compatibility)

### **Storage & Retention**

- **ADR-0019**  SessionState Serialization (K0 Bridge batching, schema validation)
- **ADR-0019a**  Schema Definition (root schema, delta schema, 6 section schemas)
- **ADR-0019c**  K0 WAL Integration (K0 Bridge WAL append)
- **ADR-0020**  Multi-Tier Storage (Hot/Warm/Cold strategy, automatic tiering)
- **ADR-0020b**  Warm Tier (K0 Bridge integration, SSD I/O)
- **ADR-0021**  Turn History Retention (privacy band tiers, multi-tier retention)
- **ADR-0021a**  Policy Engine (retention policy engine, enforcement)
- **ADR-0021b**  Privacy Band Overrides (RED 97 days, BLACK ephemeral)
- **ADR-0021c**  Compliance (audit trail, GDPR Article 5/17)

### **Security & Privacy**

- **ADR-0010c**  Runtime Enforcement (K0 Bridge capability validation)
- **ADR-0010d**  Audit Trail (K0 WAL logging, 6 event types)
- **ADR-0032**  Egress Control (network, filesystem, resources, violation logging)
- **ADR-0032a**  Network (privacy band policies, iptables enforcement)
- **ADR-0032b**  Filesystem (chroot jail, seccomp filter, path restrictions)
- **ADR-0032c**  Resources (cgroups limits, OOM killer, execution timeouts)
- **ADR-0032d**  Violation Logging (ToolReceipt audit, real-time alerting)
- **ADR-0035**  PII Detection (hybrid detection, redaction)
- **ADR-0035a**  Regex Patterns (12 structured patterns, <1ms detection)
- **ADR-0035b**  ML-based NER (BERT-NER model, BIO tagging)
- **ADR-0036c**  Selective Encryption (band detection, section selection)

### **Cost Tracking**

- **ADR-0031**  Cost Tracking (per-session, budget enforcement)
- **ADR-0031a**  Per-Session (hierarchical budgets: SessionDailyMonthly)
- **ADR-0031b**  Pricing (provider pricing, cost calculation, volume discounts)
- **ADR-0031c**  Fallback (4-tier fallback strategy, model selection)
- **ADR-0031d**  Observability (Prometheus metrics, Grafana dashboards, audit trail)

### **KV Cache Management**

- **ADR-0025**  KV Cache Management (global allocator, 512MB budget)
- **ADR-0025a**  Global Allocator (per-session min/max, fragmentation prevention)
- **ADR-0025b**  Hybrid Eviction (LRU 60% + LFU 40%, >75% hit rate target)
- **ADR-0025c**  Cache Warming (resume detection, prefetch strategy)
- **ADR-0025d**  Compression (zstd level 3, 70% size reduction)
- **ADR-0025e**  Protection (never evict tier, priority tiers)

### **Multi-Device Sync**

- **ADR-0050**  Multi-Device Sync (network-aware routing, hybrid strategy)
- **ADR-0050a**  SessionState Coherence (bounded staleness 250ms P95)
- **ADR-0050b**  CRDT Merge (last-write-wins, vector clock)
- **ADR-0050c**  Phase 1 LAN Sync (mDNS discovery, TCP peer, <1ms latency)
- **ADR-0050d**  Phase 2 Internet Sync (device certificates, P2P E2EE tunnel)
- **ADR-0085**  Embodied Awareness (multi-device presence, location awareness)
- **ADR-0085a**  Device Presence (heartbeat protocol, device registry)
- **ADR-0085c**  Context Sharing (presence syncer, K0 P07 CRDT sync)

### **Message Queue & Coalescing**

- **ADR-0053**  Message Queue (coalescing, rate limits, cancellation)
- **ADR-0053a**  Coalesce Window (30% reduction, P50 <1.5s)
- **ADR-0053b**  Rate Limits (5 msg/sec default, token bucket)
- **ADR-0053c**  Cancel Path (<120ms cancellation latency)

### **Turn Boundary Management**

- **ADR-0054**  Turn Boundary (implicit pause, explicit submit)
- **ADR-0054a**  Implicit Pause (2s silence threshold, <50ms detection)
- **ADR-0054b**  Explicit Submit (send button, enter key, voice command)
- **ADR-0054c**  MPST Transitions (protocol state tracking)

### **Enhanced HITL Protocols**

- **ADR-0052**  Enhanced HITL (observability, research foundation, audit trail)
- **ADR-0052a**  Step-by-Step Approval (workflow rollback, metrics)
- **ADR-0052b**  RED Band Approval (phrase matching, two-person rule)
- **ADR-0052c**  Nested Clarifications (max depth 3, go-back support)
- **ADR-0052d**  Proactive Confirmation (confidence threshold, feedback signals)

### **Voice Pipeline**

- **ADR-0056**  Voice Pipeline (K0 ASR/TTS pipelines, frame processing)
- **ADR-0056a**  ASR Ingress (frame handling, VAD processing, partial results)
- **ADR-0056d**  TTS Synthesis (prosody controls, SSML generation, streaming audio)
- **ADR-0056e**  Audio Output (buffer management, jitter buffer)

### **REST API & WebSocket**

- **ADR-0014a**  Content Negotiation (JSON/FlatBuffers dual format)
- **ADR-0014b**  OpenAPI Generation (FlatBuffers parser, JSON schema mapper)
- **ADR-0014d**  Client SDKs (Python/TypeScript SDKs, curl examples)
- **ADR-0015**  WebSocket Binary Protocol (message envelope, 17 message types)
- **ADR-0015a**  Protocol Design (clientserver, serverclient messages)
- **ADR-0015b**  Flow Control (ACK protocol, batch 5 messages)
- **ADR-0015c**  Reconnection (RESUME message, exponential backoff)
- **ADR-0015d**  Streaming (token schema, chunk_index, logprob)
- **ADR-0015e**  Client SDK (TypeScript SDK, reconnect/ACK/dedup managers)
- **ADR-0046**  SSE-WebSocket Bridge (K1 SSE subscriber, event transformation)
- **ADR-0047**  OpenAPI 3.1 Specs (SDK generation, TypeScript/Python/Go)

### **SSE Event Schemas**

- **ADR-0016**  SSE Event Schemas (event taxonomy, 17 event types)
- **ADR-0016a**  Event Taxonomy (agent/turn/tool/session/system events)
- **ADR-0016c**  Filtering (server-side filtering, topic mappings, 60-70% bandwidth savings)
- **ADR-0016d**  Browser Integration (native EventSource, React hooks, TypeScript SDK)

### **Fast/Smart Lane Router**

- **ADR-0049**  Fast/Smart Lane Router (4-factor score, lane criteria)

---

## Layer 5 Performance Budget Breakdown

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
| Config reload | 100ms | 80ms | 100ms | ADR-0080 |

---

## Layer 5 Integration Points

### **Layer 5  Layer 1/2/3/4 (Infrastructure Services)**

```
All layers call:                Layer 5 provides:

K0 writes                     bridge_k0/command_client
K0 reads                      bridge_k0/query_client
Event pub/sub                 event_bus/event_bus
Circuit breaker               resilience/circuit_breaker
Metrics                       observability/metrics
Tracing                       observability/tracing
Logging                       observability/logging
Thermal placement             thermal/placement_planner
Config access                 config/loader
```

### **Layer 5  K0 (External Dependency)**

```
Layer 5 calls:                  K0 provides:

Command writes                 K0 Command Port (:5200)
Query reads                    K0 Query Port (:5201)
Event subscription             K0 SSE Port (:5202)
Observability push             K0 Observability Port (:5203)
```

**Key Constraints:**

1. **Leaf layer:** L5 imports nothing (no L5L1/L2/L3/L4 imports)
2. **Cross-cutting:** All layers depend on L5 infrastructure
3. **External dependency:** L5 depends on K0 (dual-kernel architecture)

---

## Layer 5 Testing Strategy (ADR-0004d)

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
   - Emergency jump (CRITICAL  Remote, <50ms)

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
   - Full K1K0 round trip (write  read  event)
   - Performance: <200ms P95 (GREEN), <500ms P95 (AMBER/RED)

---

## Layer 5 Observability (ADR-0029)

### **Prometheus Metrics (50+ metrics)**

| Metric | Type | Labels | Description | ADR |
|--------|------|--------|-------------|-----|
| `layer5_k0_command_latency_ms` | Histogram | band, command_type | K0 Command Port latency | ADR-0029 |
| `layer5_k0_query_latency_ms` | Histogram | query_type | K0 Query Port latency | ADR-0029 |
| `layer5_sse_event_rate` | Counter | event_type | SSE event delivery rate | ADR-0029 |
| `layer5_batch_size` | Histogram | - | SessionState batch size | ADR-0029 |
| `layer5_circuit_breaker_state` | Gauge | target | Circuit breaker state (0=CLOSED, 1=OPEN, 2=HALF_OPEN) | ADR-0029 |
| `layer5_retry_attempts` | Counter | target, attempt | Retry attempts | ADR-0029 |
| `layer5_thermal_temperature_celsius` | Gauge | device | Device temperature | ADR-0029 |
| `layer5_thermal_placement_decisions` | Counter | placement | Placement decisions | ADR-0029 |
| `layer5_event_bus_delivery_ms` | Histogram | topic | Event bus delivery latency | ADR-0029 |
| `layer5_event_bus_backpressure_events` | Counter | subscriber | Backpressure events | ADR-0029 |
| `layer5_metric_emission_ms` | Histogram | - | Metric emission latency | ADR-0029 |
| `layer5_trace_span_creation_ms` | Histogram | span_type | Span creation latency | ADR-0029 |
| `layer5_log_write_ms` | Histogram | level | Log write latency | ADR-0029 |
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

## Layer 5 Implementation Roadmap

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

## Complete ADR Reference List

### **Primary Layer 5 ADRs (7 core)**

- ADR-0004  52-Module 5-Layer Architecture
- ADR-0001a  K0 Bridge Architecture
- ADR-0029  Prometheus Metrics
- ADR-0009  Circuit Breaker
- ADR-0026  Thermal Management
- ADR-0004a  Event Bus
- ADR-0004d  Layer 5 Integration Tests

### **K0 Bridge ADRs (31 ADRs)**

- ADR-0001  K0 Integration
- ADR-0001f  SessionState Delta Batching
- ADR-0016  SSE Event Schemas
- ADR-0016a  Event Taxonomy
- ADR-0016c  Filtering
- ADR-0016d  Browser Integration
- ADR-0022  K0 Bridge Batching
- ADR-0022a  Batching Algorithm
- ADR-0022b  HTTP/2 Integration
- ADR-0022c  Backpressure
- ADR-0022d  FlatBuffers Schema
- ADR-0042  K0 SSE Event Streaming
- ADR-0042a  Event Production
- ADR-0042b  Event Consumption
- ADR-0042c  Reconnection
- ADR-0042d  Backpressure
- ADR-0042e  Device Tiers
- ADR-0043  SSE Topic Taxonomy
- ADR-0043a  Topic Hierarchy
- ADR-0043b  Subscription Patterns
- ADR-0043c  Topic Routing
- ADR-0043d  Topic Access Control
- ADR-0044  K0 Bridge HTTP/2
- ADR-0044a  Transport Protocol
- ADR-0044b  Serialization
- ADR-0044c  Batching
- ADR-0044d  Error Handling
- ADR-0046  SSE-WebSocket Bridge
- ADR-0047  OpenAPI 3.1 Specs
- ADR-0049  Fast/Smart Lane Router
- ADR-0024  Performance Budgets (K0 Bridge <50ms GREEN, <200ms AMBER/RED)

### **Resilience ADRs (13 ADRs)**

- ADR-0009  Circuit Breaker
- ADR-0009a  Circuit State Transitions
- ADR-0009b  Hot Reload
- ADR-0009c  Fallback Cascade
- ADR-0008a  Idempotency
- ADR-0008b  Saga Retry Policy
- ADR-0008c  Distributed State
- ADR-0080  Config Hot-Reload
- ADR-0027  Model Placement Cascade

### **Thermal ADRs (18 ADRs)**

- ADR-0026  Thermal Management
- ADR-0026a  Thermal Zones
- ADR-0026b  Hysteresis FSM
- ADR-0026c  Hysteresis Matrix
- ADR-0026d  Throttling
- ADR-0027  Model Placement Cascade

### **Event Bus ADRs (12 ADRs)**

- ADR-0004a  Event Bus
- ADR-0048  K1 Internal Event Bus

### **Observability ADRs (32 ADRs)**

- ADR-0029  Prometheus Metrics
- ADR-0029a  RED Method
- ADR-0029d  Infrastructure
- ADR-0029e  Alerting
- ADR-0030  Trace Sampling
- ADR-0030a  Head-Based Sampling
- ADR-0030b  Tail-Based Sampling
- ADR-0030c  Adaptive Sampling
- ADR-0030d  Jaeger Integration
- ADR-0002d  Actor Fabric Observability
- ADR-0086h  Agent Metrics & Observability (25+ Prometheus metrics, OpenTelemetry tracing, 3 Grafana dashboards)

### **Backpressure ADRs (16 ADRs)**

- ADR-0039a  Tier Triggers
- ADR-0039b  Signal Propagation
- ADR-0039c  Recovery
- ADR-0061  Backpressure
- ADR-0061a  Watermark Thresholds
- ADR-0061b  RED Metrics & Alerts
- ADR-0061c  Privacy Band Overrides
- ADR-0061d  Fairness & Anti-Starvation
- ADR-0057  Voice Backpressure

### **Performance ADRs (12 ADRs)**

- ADR-0024  Performance Budgets
- ADR-0024a  Turn-Level Budgets
- ADR-0024b  Component-Level Budgets
- ADR-0024c  Memory Budgets
- ADR-0024d  Graceful Degradation

### **Serialization ADRs (20 ADRs)**

- ADR-0011  FlatBuffers Serialization
- ADR-0011a  Schema Design
- ADR-0011b  Code Generation
- ADR-0011c  Performance
- ADR-0011d  Schema Evolution
- ADR-0012  Schema Taxonomy
- ADR-0012e  Layer 5 Schemas
- ADR-0013  Schema Versioning
- ADR-0013a  Version Registry
- ADR-0013b  CI/CD Automation
- ADR-0013c  Deprecation Workflow
- ADR-0013d  Contract Testing
- ADR-0019  SessionState Serialization
- ADR-0019a  Schema Definition
- ADR-0019c  K0 WAL Integration

### **Storage ADRs (12 ADRs)**

- ADR-0020  Multi-Tier Storage
- ADR-0020b  Warm Tier
- ADR-0021  Turn History Retention
- ADR-0021a  Policy Engine
- ADR-0021b  Privacy Band Overrides
- ADR-0021c  Compliance

### **Security ADRs (15 ADRs)**

- ADR-0010c  Runtime Enforcement
- ADR-0010d  Audit Trail
- ADR-0032  Egress Control
- ADR-0032a  Network
- ADR-0032b  Filesystem
- ADR-0032c  Resources
- ADR-0032d  Violation Logging
- ADR-0035  PII Detection
- ADR-0035a  Regex Patterns
- ADR-0035b  ML-based NER
- ADR-0036c  Selective Encryption

### **Cost Tracking ADRs (5 ADRs)**

- ADR-0031  Cost Tracking
- ADR-0031a  Per-Session
- ADR-0031b  Pricing
- ADR-0031c  Fallback
- ADR-0031d  Observability

### **KV Cache ADRs (6 ADRs)**

- ADR-0025  KV Cache Management
- ADR-0025a  Global Allocator
- ADR-0025b  Hybrid Eviction
- ADR-0025c  Cache Warming
- ADR-0025d  Compression
- ADR-0025e  Protection

### **Multi-Device Sync ADRs (9 ADRs)**

- ADR-0050  Multi-Device Sync
- ADR-0050a  SessionState Coherence
- ADR-0050b  CRDT Merge
- ADR-0050c  Phase 1 LAN Sync
- ADR-0050d  Phase 2 Internet Sync
- ADR-0085  Embodied Awareness
- ADR-0085a  Device Presence
- ADR-0085c  Context Sharing

### **Message Queue ADRs (4 ADRs)**

- ADR-0053  Message Queue & Coalescing
- ADR-0053a  Coalesce Window
- ADR-0053b  Rate Limits
- ADR-0053c  Cancel Path

### **Turn Boundary ADRs (4 ADRs)**

- ADR-0054  Turn Boundary Management
- ADR-0054a  Implicit Pause
- ADR-0054b  Explicit Submit
- ADR-0054c  MPST Transitions

### **HITL ADRs (5 ADRs)**

- ADR-0052  Enhanced HITL Protocols
- ADR-0052a  Step-by-Step Approval
- ADR-0052b  RED Band Approval
- ADR-0052c  Nested Clarifications
- ADR-0052d  Proactive Confirmation

### **Voice Pipeline ADRs (4 ADRs)**

- ADR-0056  Voice Pipeline Implementation
- ADR-0056a  ASR Ingress
- ADR-0056d  TTS Synthesis
- ADR-0056e  Audio Output

### **WebSocket ADRs (7 ADRs)**

- ADR-0014a  Content Negotiation
- ADR-0014b  OpenAPI Generation
- ADR-0014d  Client SDKs
- ADR-0015  WebSocket Binary Protocol
- ADR-0015a  Protocol Design
- ADR-0015b  Flow Control
- ADR-0015c  Reconnection
- ADR-0015d  Streaming
- ADR-0015e  Client SDK

### **K0 Core ADRs (9 ADRs)**

- ADR-0001  Memory Kernel
- ADR-0081  Knowledge Graph
- ADR-0081a  Graph Schema
- ADR-0081b  Query API
- ADR-0081c  Episodic Integration
- ADR-0081d  Visualization
- ADR-0084  K0 Memory Consolidation
- ADR-0084a  Hippocampal Replay
- ADR-0084b  Sleep State Machine
- ADR-0084c  Knowledge Graph Consolidation
- ADR-0084d  Dream Exploration

### **Extensions ADRs (2 ADRs)**

- ADR-0074  Module System
- ADR-0075  Layer 5 Extensibility

---

**Status:**  **COMPLETE**  All Layer 5 ADRs mapped end-to-end
**Last Updated:** January 2025
**Total ADRs:** 166 ADRs covering Layer 5
**Coverage:** 100% of Layer 5 modules (19/19 modules mapped across 6 categories)

---

**This file was generated based on ADR_REFERENCE.md (4406 lines, 166 ADRs including ADR-0086h for agent metrics)**
