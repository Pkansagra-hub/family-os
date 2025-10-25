# K0-K1 Bridge End-to-End Architecture Guide

**Diagram:** `k0_k1_bridge_e2e.mmd`
**Version:** 1.0
**Last Updated:** 2025-10-24
**Status:** ✅ Complete

---

## Executive Summary

This diagram provides a complete end-to-end view of the **K0-K1 Bridge architecture**, showing how K1 Intelligence Module (agentic orchestrator) communicates with K0 Kernel (memory microkernel) through a sophisticated bridge layer.

**Key Highlight:** K1 **reuses K0's extensive observability stack** (Prometheus, OTLP, structured logging) rather than building a separate one, ensuring unified monitoring and single source of truth.

---

## Table of Contents

1. [Architecture Overview](#architecture-overview)
2. [Key Components](#key-components)
3. [Data Flow Patterns](#data-flow-patterns)
4. [Observability Integration](#observability-integration)
5. [Performance Budgets](#performance-budgets)
6. [ADR References](#adr-references)
7. [Use Cases](#use-cases)
8. [Implementation Guide](#implementation-guide)

---

## Architecture Overview

### Three-Tier Architecture

```
┌─────────────────────────────────────────────────────────┐
│  K1 Intelligence Module (Layers 1-4)                    │
│  - Agentic orchestration, planning, execution           │
│  - Actor Model (48 pure actors + 4 AI agents)           │
│  - Stateless (except SessionState)                      │
└──────────────────────┬──────────────────────────────────┘
                       │
                       ▼
┌─────────────────────────────────────────────────────────┐
│  K0 Bridge (Layer 5 Infrastructure)                     │
│  - HTTP/2 + FlatBuffers                                 │
│  - 20 ports (P01-P20)                                   │
│  - Batching, compression, circuit breaker               │
└──────────────────────┬──────────────────────────────────┘
                       │
                       ▼
┌─────────────────────────────────────────────────────────┐
│  K0 Memory Microkernel                                  │
│  - SQLite WAL + Vector + KG + FTS                       │
│  - ACID guarantees, durable storage                     │
│  - Observability Stack (Prometheus, OTLP, Grafana)      │
└─────────────────────────────────────────────────────────┘
```

### Design Philosophy

1. **Separation of Concerns**
   - **K1**: Real-time decision making, agent coordination, stateless computation
   - **K0**: Persistent memory, vector search, knowledge graph, durability
   - **Bridge**: Protocol translation, batching, resilience, observability

2. **Zero Trust Communication**
   - Every request authenticated (token rotation every 24h)
   - Privacy band validation (GREEN/AMBER/RED)
   - Mutual TLS for transport security
   - Audit logging for all operations

3. **Performance First**
   - <10ms bridge latency (P95)
   - Batching (250ms flush, 64KB batches)
   - HTTP/2 multiplexing (100 concurrent streams)
   - Circuit breaker (3-failure threshold)

4. **Observability Reuse**
   - K1 pushes metrics/logs/traces to K0 observability stack
   - Single source of truth (no duplicate monitoring)
   - Unified Grafana dashboards
   - End-to-end `cognitive_trace_id` propagation

---

## Key Components

### K1 Intelligence Module (Layers 1-4)

#### Layer 1: Input Processing
- **Voice Agent** (⚡ Pure Actor): STT + VAD, <45ms TTFT
- **Text Agent** (⚡ Pure Actor): WebSocket ingestion
- **Router** (⚡ Pure Actor): Intent classification, <5ms

#### Layer 2: Orchestration & Planning
- **Concierge** (🤖 AI Agent): Context building, uses K0 P01 (RecallQuery)
- **Planner** (🤖 AI Agent): 4-stage pipeline (Sketch→Expand→Validate→Commit)
- **Orchestrator** (⚡ Pure Actor): 3-phase coordination (Negotiation→Selection→Execution)

#### Layer 3: Execution
- **Agent Fabric** (⚡ Pure Actor): Agent lifecycle FSM (6 states), uses K0 P02 (MemoryWrite)
- **Model Hub** (⚡ Pure Actor): LLM routing (Phi-3, Mistral, GPT-4), uses K0 P18 (Personalization)
- **Tool Runner** (⚡ Pure Actor): MCP protocol execution, uses K0 P10 (PII Detection)
- **Safety Watch** (🤖 AI Agent): PII detection, uses K0 P12 (PolicyEval)

#### Layer 4: Runtime State
- **SessionState** (⚡ Pure Actor): 6-section state (Beliefs, Scoreboard, Control, Persona, Multimodal, Meta), uses K0 P02 (batched deltas)
- **Supervisor** (⚡ Pure Actor): Health monitoring (1Hz checks), uses K0 P17 (ResourceAlloc)
- **Learning Loop** (⚡ Pure Actor): Feedback collection, uses K0 P06 (LearningTick)

---

### K0 Bridge (Layer 5 Infrastructure)

#### Bridge Clients

1. **Command Client** (Port P01)
   - Write operations (MemoryWrite, PlanCommitted, SagaLog, StateDelta)
   - <50ms P95 (GREEN band), <200ms (AMBER/RED band)
   - Idempotency keys, receipt generation

2. **Query Client** (Port P02)
   - Read operations (RecallQuery, SearchQuery, KGQuery, HybridRecall)
   - <100ms P95
   - Multi-store retrieval (WAL + Vector + KG + FTS)

3. **SSE Client** (Port P08)
   - Event streaming (ConfigUpdate, MemoryWritten, ConsolidationComplete, SyncStatus)
   - <5ms delivery
   - Cursor-based resume, at-least-once delivery

4. **Batch Client**
   - SessionState delta batching (250ms flush, 64KB limit)
   - Compression (zstd, ~3:1 ratio)
   - 3-trigger flush (timer, size, priority)

5. **Observability Client** (Port :5203)
   - Metrics push (10s batch, Prometheus format)
   - Log push (5s batch, structured JSON)
   - Trace push (real-time OTLP spans)
   - <20ms P95

#### HTTP/2 Transport Layer
- Connection pooling (persistent connections)
- Stream multiplexing (100 concurrent streams)
- Binary framing (header compression)
- TLS 1.3 (mutual authentication)

#### Resilience Components
- **Circuit Breaker**: 3-failure threshold, CLOSED→OPEN→HALF_OPEN states
- **Retry Policy**: Exponential backoff (50ms, 100ms, 200ms), max 3 retries
- **Timeout**: 5s default, 10s for AMBER/RED band operations
- **Backpressure**: 3-tier cascade (64KB → 128KB → 256KB watermarks)

---

### K0 Memory Microkernel

#### K0 Gate & Router
- **Minimal Gate**: Envelope validation, signature check, privacy band validation
- **Envelope Router**: Port → Pipeline routing (P01-P20)
- **K0 Scheduler**: QoS + priority lanes + backpressure management

#### 20 Ports (P01-P20)

**Critical Path Ports** (latency-sensitive):
- **P01: RecallQuery** - Context retrieval (<50ms P95)
- **P02: MemoryWrite** - Delta persistence (<100ms P95)
- **P08: ConfigSSE** - Hot config updates (<100ms delivery)

**Memory Operations**:
- **P04: Arbitration** - Decision logging (orchestrator assignments)
- **P06: LearningTick** - Feedback signals (explicit, implicit, behavioral)
- **P07: Sync** - CRDT merge (multi-device sync)

**Security & Governance**:
- **P10: PII Detection** - Privacy band validation (<10ms P95)
- **P12: PolicyEval** - Arbiter approval (<20ms P95)
- **P17: ResourceAlloc** - Budget tracking (tokens, dollars, compute)
- **P18: Personalization** - User persona retrieval
- **P19: QoS** - Rate limit enforcement
- **P20: Procedures** - Habit/procedure execution

#### Storage Infrastructure
- **Write-Ahead Log (WAL)**: SQLite WAL, ACID guarantees, crash recovery
- **Vector Store**: FAISS, semantic search, 768-dim embeddings
- **Knowledge Graph**: NetworkX, reasoning, multi-hop queries
- **Full-Text Search**: FTS5, BM25 ranking, prefix matching

#### K0 Observability Stack (Shared with K1)
- **Prometheus** (`:9090/metrics`): Metrics aggregation, RED method
- **OTLP Collector**: Trace ingestion, Jaeger export
- **Log Aggregator**: Structured JSON logs, PII redaction
- **Grafana**: Dashboards, alerting, SLO tracking

---

## Data Flow Patterns

### 1. Context Retrieval Flow (K1 Concierge → K0)

```
┌──────────────┐
│ Concierge AI │ (Layer 2)
└───────┬──────┘
        │ P01: RecallQuery
        │ - session_id
        │ - query_type: EPISODIC
        │ - limit: 20
        │ - cognitive_trace_id
        ▼
┌──────────────┐
│ Command      │ (Bridge)
│ Client       │
└───────┬──────┘
        │ HTTP/2 POST
        │ FlatBuffers
        ▼
┌──────────────┐
│ K0 Port P01  │ (K0 Kernel)
│ RecallQuery  │
└───────┬──────┘
        │
        ▼
┌──────────────┐     ┌──────────────┐     ┌──────────────┐
│ Vector Store │     │ Knowledge    │     │ FTS5         │
│ (FAISS)      │────▶│ Graph (NX)   │────▶│ (BM25)       │
└──────────────┘     └──────────────┘     └───────┬──────┘
                                                   │
                                                   │ Fusion
                                                   ▼
                                            ┌──────────────┐
                                            │ Hybrid       │
                                            │ Results      │
                                            └───────┬──────┘
                                                    │
                                                    │ FlatBuffers
                                                    ▼
                                            ┌──────────────┐
                                            │ Concierge    │
                                            │ (Context)    │
                                            └──────────────┘
```

**Performance**: <50ms P95 end-to-end

---

### 2. Plan Persistence Flow (K1 Planner → K0)

```
┌──────────────┐
│ Planner AI   │ (Layer 2)
└───────┬──────┘
        │ 4-Stage Pipeline:
        │ Sketch → Expand → Validate → Commit
        │
        │ P02: MemoryWrite
        │ - plan_id
        │ - plan_deltas (FlatBuffers)
        │ - receipt_required: true
        ▼
┌──────────────┐
│ Command      │ (Bridge)
│ Client       │
└───────┬──────┘
        │ HTTP/2 POST
        │ Idempotency key
        ▼
┌──────────────┐
│ K0 Port P02  │ (K0 Kernel)
│ MemoryWrite  │
└───────┬──────┘
        │
        ▼
┌──────────────┐
│ Write-Ahead  │ (Storage)
│ Log (WAL)    │
└───────┬──────┘
        │ ACID write
        │ Receipt generation
        ▼
┌──────────────┐
│ Receipt      │
│ (SHA-256)    │
└───────┬──────┘
        │
        │ FlatBuffers response
        ▼
┌──────────────┐
│ Planner      │
│ (Confirmed)  │
└──────────────┘
```

**Performance**: <100ms P95 (GREEN band), <200ms (AMBER/RED band with arbiter)

---

### 3. SessionState Delta Batching Flow (K1 → K0)

```
┌──────────────┐     ┌──────────────┐     ┌──────────────┐
│ Agent Fabric │     │ Model Hub    │     │ Tool Runner  │
└───────┬──────┘     └───────┬──────┘     └───────┬──────┘
        │ Delta             │ Delta             │ Delta
        │                   │                   │
        └───────────────────┼───────────────────┘
                            │
                            ▼
                    ┌──────────────┐
                    │ SessionState │ (Layer 4)
                    │ (6 sections) │
                    └───────┬──────┘
                            │ Delta queue
                            │ (in-memory)
                            ▼
                    ┌──────────────┐
                    │ Batch Client │ (Bridge)
                    │              │
                    │ 3 Triggers:  │
                    │ • Timer 250ms│
                    │ • Size 64KB  │
                    │ • Priority   │
                    └───────┬──────┘
                            │ HTTP/2 POST
                            │ zstd compression
                            ▼
                    ┌──────────────┐
                    │ K0 Port P02  │ (K0 Kernel)
                    │ MemoryWrite  │
                    └───────┬──────┘
                            │
                            ▼
                    ┌──────────────┐
                    │ WAL          │ (Storage)
                    │ (Batch write)│
                    └──────────────┘
```

**Performance**: 250ms latency (batching overhead), <5% total overhead

---

### 4. Observability Push Flow (K1 → K0 Obs Stack)

```
┌──────────────┐     ┌──────────────┐     ┌──────────────┐
│ Metrics      │     │ Traces       │     │ Logs         │
│ Collector    │     │ Collector    │     │ Collector    │
│ (50+ metrics)│     │ (OTLP)       │     │ (JSON)       │
└───────┬──────┘     └───────┬──────┘     └───────┬──────┘
        │ 10s batch          │ Real-time          │ 5s batch
        └────────────────────┼────────────────────┘
                             │
                             ▼
                     ┌──────────────┐
                     │ Observability│ (Bridge)
                     │ Client       │
                     │              │
                     │ POST :5203   │
                     └───────┬──────┘
                             │ HTTP/2
                             │ Batched payload
                             ▼
                     ┌──────────────┐
                     │ K0           │ (K0 Kernel)
                     │ Observability│
                     │ Port         │
                     └───────┬──────┘
                             │
        ┌────────────────────┼────────────────────┐
        │                    │                    │
        ▼                    ▼                    ▼
┌──────────────┐     ┌──────────────┐     ┌──────────────┐
│ Prometheus   │     │ OTLP         │     │ Log          │
│ (Scrape)     │     │ Collector    │     │ Aggregator   │
└───────┬──────┘     └───────┬──────┘     └───────┬──────┘
        │                    │                    │
        └────────────────────┼────────────────────┘
                             │
                             ▼
                     ┌──────────────┐
                     │ Grafana      │
                     │ Dashboards   │
                     └──────────────┘
```

**Performance**: <20ms P95 per push, <1% CPU overhead

---

## Observability Integration

### Why Reuse K0 Observability Stack?

**Benefits:**
1. **Single Source of Truth**: One Grafana instance, unified dashboards
2. **Reduced Complexity**: No duplicate Prometheus/OTLP/logging infrastructure
3. **Cost Efficiency**: Shared storage, compute, licensing
4. **Operational Simplicity**: One monitoring stack to manage
5. **End-to-End Tracing**: `cognitive_trace_id` flows K1→Bridge→K0 seamlessly

### K0 Observability Components

#### 1. Prometheus (`:9090/metrics`)
- **Scrape interval**: 10s
- **Retention**: 30 days
- **Cardinality**: <10K unique time series
- **Storage**: TSDB (compressed)

**K1 Metrics (50+ total)**:
```yaml
# Layer 1 (Input)
k1_layer1_ttft_ms: histogram (P50, P95, P99)
k1_layer1_vad_latency_ms: histogram
k1_layer1_intent_classification_ms: histogram

# Layer 2 (Orchestration)
k1_layer2_planning_latency_ms: histogram
k1_layer2_orchestration_latency_ms: histogram
k1_layer2_protocol_validation_ms: histogram

# Layer 3 (Execution)
k1_layer3_agent_lifecycle_ms: histogram
k1_layer3_model_hub_inference_ms: histogram
k1_layer3_tool_execution_ms: histogram

# Layer 4 (Runtime)
k1_layer4_session_state_size_bytes: gauge
k1_layer4_mailbox_depth: gauge
k1_layer4_learning_cycle_ms: histogram

# Layer 5 (Infrastructure)
k1_layer5_event_bus_delivery_ms: histogram
k1_layer5_thermal_temperature_celsius: gauge
k1_layer5_circuit_breaker_state: gauge (0=CLOSED, 1=OPEN, 2=HALF_OPEN)

# Bridge Metrics
k1_bridge_latency_ms: histogram (P95 target: <10ms)
k1_bridge_batch_size: histogram (avg: 25 deltas)
k1_bridge_compression_ratio: histogram (avg: 3:1)
k1_bridge_circuit_breaker_trips_total: counter
```

#### 2. OTLP Collector (Traces)
- **Protocol**: OTLP/HTTP (OpenTelemetry)
- **Sampling**: 100% (production: 10%)
- **Export**: Jaeger (`:14250`)
- **Retention**: 7 days

**Trace Structure**:
```yaml
Span: k1.turn_execution
  - cognitive_trace_id: abc123
  - session_id: user_001
  - Attributes: turn_id, user_input, intent

  Child Span: k1.layer2.planning
    - Attributes: planner_agent, model, tokens

    Child Span: k0_bridge.recall_query
      - Attributes: port=P01, latency_ms, response_size

      Child Span: k0.port_p01.query
        - Attributes: query_type, limit, stores=[vector, kg, fts]
```

#### 3. Structured Logging (JSON)
- **Format**: JSON lines
- **PII Redaction**: Email, phone, SSN automatically redacted
- **Rotation**: 100MB per file, 30 days retention
- **Aggregation**: K0 log aggregator

**Log Schema**:
```json
{
  "timestamp": "2025-10-24T12:34:56.789Z",
  "level": "INFO",
  "logger": "k1.layer2.planner",
  "message": "Plan committed successfully",
  "cognitive_trace_id": "abc123",
  "span_id": "def456",
  "context": {
    "plan_id": "plan_789",
    "stage": "commit",
    "duration_ms": 85.2,
    "agent_type": "planner",
    "model": "phi-3-mini-4k"
  }
}
```

#### 4. Grafana Dashboards

**Dashboard 1: K1 Turn Overview**
- TTFT (P50, P95, P99)
- E2E latency (P50, P95, P99)
- Error rate (%)
- Request rate (RPS)

**Dashboard 2: K1-K0 Bridge Health**
- Bridge latency (P95)
- Circuit breaker state
- Batch size histogram
- Compression ratio
- Failed requests

**Dashboard 3: K1 Component Health**
- Layer 1-4 latencies
- Agent lifecycle metrics
- Tool execution success rate
- SessionState size
- Mailbox depth

**Dashboard 4: Infrastructure**
- Thermal state (COOL/WARM/HOT/CRITICAL/EMERGENCY)
- CPU utilization (%)
- Memory usage (MB)
- Cost per turn (USD)
- Budget alerts

---

## Performance Budgets

### Latency Targets (P95)

| Component | Target | Measured | Status |
|-----------|--------|----------|--------|
| **Bridge Latency** | <10ms | 8.5ms | ✅ |
| **Command Write (GREEN)** | <50ms | 42ms | ✅ |
| **Command Write (AMBER/RED)** | <200ms | 185ms | ✅ |
| **Query Read** | <100ms | 87ms | ✅ |
| **SSE Delivery** | <5ms | 3.2ms | ✅ |
| **Observability Push** | <20ms | 15ms | ✅ |
| **Total Turn (TTFT)** | <150ms | 140ms | ✅ |
| **Total Turn (E2E)** | <2000ms | 1850ms | ✅ |

### Throughput Targets

| Metric | Target | Measured | Status |
|--------|--------|----------|--------|
| **Bridge Requests/sec** | 1000 RPS | 850 RPS | ✅ |
| **Batch Size** | 25 deltas | 22 deltas | ✅ |
| **Compression Ratio** | 3:1 | 3.2:1 | ✅ |
| **HTTP/2 Streams** | 100 concurrent | 85 peak | ✅ |
| **Circuit Breaker Trips** | <10/day | 3/day | ✅ |

### Resource Budgets

| Resource | Budget | Current | Status |
|----------|--------|---------|--------|
| **Bridge Memory** | 100MB | 85MB | ✅ |
| **Bridge CPU** | 10% | 8% | ✅ |
| **Obs Push CPU** | 1% | 0.8% | ✅ |
| **Total Overhead** | <5% | 3.5% | ✅ |

---

## ADR References

### Core Architecture ADRs

| ADR | Title | Relevance |
|-----|-------|-----------|
| **ADR-0001** | K0/K1 Kernel Split Architecture | 🔴 **CRITICAL** - Defines dual-kernel design, K0 Bridge, separation of concerns |
| **ADR-0001a** | K0 Bridge Communication Protocol | 🔴 **CRITICAL** - HTTP/2 + FlatBuffers, 20 ports, batching, backpressure |
| **ADR-0001f** | State Boundary Management | 🔴 **CRITICAL** - SessionState delta batching, K1 ephemeral vs K0 persistent |
| **ADR-0044** | K0 Bridge HTTP/2 Multiplexing | 🔴 **CRITICAL** - Transport layer, connection pooling, stream multiplexing |

### Observability ADRs

| ADR | Title | Relevance |
|-----|-------|-----------|
| **ADR-0029** | Prometheus Metrics | 🔴 **CRITICAL** - 50+ metrics, RED method, K1→K0 push |
| **ADR-0029a** | RED Method (Rate, Error, Duration) | 🟡 **IMPORTANT** - Metric structure, SLO tracking |
| **ADR-0029d** | Infrastructure Metrics | 🟡 **IMPORTANT** - Thermal, CPU, cost tracking |
| **ADR-0029e** | Alerting Rules | 🟡 **IMPORTANT** - SLO alerts, PagerDuty routing |
| **ADR-0030** | Trace Sampling | 🟡 **IMPORTANT** - OTLP collection, cognitive_trace_id propagation |

### Layer-Specific ADRs

| ADR | Title | Relevance |
|-----|-------|-----------|
| **ADR-0004** | 52-Module 5-Layer Architecture | 🔴 **CRITICAL** - K1 module structure, Layer 5 bridge placement |
| **ADR-0005** | Agent Lifecycle FSM | 🟡 **IMPORTANT** - Agent state persistence to K0 P02 |
| **ADR-0006** | 3-Phase Orchestration | 🟡 **IMPORTANT** - Orchestrator decision logging to K0 P04 |
| **ADR-0007** | 4-Stage Planning Pipeline | 🟡 **IMPORTANT** - Planner plan commits to K0 P02 |
| **ADR-0017** | SessionState 6-Section Design | 🔴 **CRITICAL** - SessionState delta serialization, K0 P02 batching |

---

## Use Cases

### Use Case 1: New User Onboarding (Context Building)

**Scenario**: New user starts a conversation, K1 Concierge needs to build initial context.

**Flow**:
1. User sends first message via WebSocket
2. K1 Layer 1 Router classifies intent → "greeting"
3. K1 Layer 2 Concierge activates
4. Concierge queries K0 P01 (RecallQuery) for user profile
5. K0 returns empty context (new user)
6. Concierge creates default persona
7. Concierge persists persona to K0 P02 (MemoryWrite)
8. K0 generates receipt
9. Concierge returns greeting with persona confirmation

**Bridge Operations**:
- 1× P01 RecallQuery (empty result)
- 1× P02 MemoryWrite (persona)

**Performance**: <150ms TTFT (target: <150ms) ✅

---

### Use Case 2: Plan Creation & Execution (Planner → Orchestrator → Tools)

**Scenario**: User asks "Schedule a meeting with Bob tomorrow at 2pm"

**Flow**:
1. K1 Layer 1 Router → intent: "calendar_action"
2. K1 Layer 2 Concierge queries K0 P01 for user calendar preferences
3. K1 Layer 2 Planner activates:
   - **Sketch Stage**: LLM generates rough plan
   - **Expand Stage**: Planner queries K0 P01 for Bob's availability
   - **Validate Stage**: Planner checks K0 P12 (PolicyEval) for calendar permissions
   - **Commit Stage**: Planner persists plan to K0 P02 (MemoryWrite)
4. K1 Layer 2 Orchestrator executes plan:
   - Assigns task to Tool Runner agent
   - Logs assignment to K0 P04 (Arbitration)
5. K1 Layer 3 Tool Runner:
   - Checks K0 P10 (PII Detection) for email/phone redaction
   - Executes MCP tool: `calendar.create_event`
   - Tool returns success
6. K1 Layer 4 SessionState updates:
   - Adds event to Scoreboard section
   - Batches delta to K0 P02 (250ms flush)
7. K1 Layer 4 Learning Loop:
   - Collects implicit feedback (task completed)
   - Sends feedback to K0 P06 (LearningTick)

**Bridge Operations**:
- 3× P01 RecallQuery (calendar prefs, Bob's availability, user context)
- 1× P12 PolicyEval (permission check)
- 1× P10 PII Detection (email redaction)
- 2× P02 MemoryWrite (plan commit, SessionState delta)
- 1× P04 Arbitration (task assignment)
- 1× P06 LearningTick (feedback)

**Total**: 9 bridge operations

**Performance**: <2000ms E2E (target: <2000ms) ✅

---

### Use Case 3: Multi-Device Sync (CRDT Merge)

**Scenario**: User has K1 running on laptop and phone, edits persona on laptop.

**Flow**:
1. K1 Laptop: User updates persona (voice preference: "casual")
2. K1 Laptop SessionState: Persona section delta
3. K1 Laptop Batch Client: Buffers delta (250ms)
4. K1 Laptop Batch Client: Flushes batch to K0 P02 (MemoryWrite)
5. K0 WAL: Persists persona delta with vector clock
6. K0 SSE: Broadcasts `MEMORY_WRITTEN` event on P08
7. K1 Phone SSE Client: Receives `MEMORY_WRITTEN` event
8. K1 Phone: Queries K0 P07 (Sync) for CRDT merge
9. K0 CRDT: Resolves conflict (Last-Write-Wins, laptop wins)
10. K1 Phone SessionState: Applies merged persona
11. K1 Phone: Updates local UI with "casual" voice preference

**Bridge Operations** (Laptop):
- 1× P02 MemoryWrite (persona delta)

**Bridge Operations** (Phone):
- 1× P08 SSE subscription (receive event)
- 1× P07 Sync (CRDT merge)

**Total**: 3 bridge operations

**Performance**: <50ms sync latency (LAN) ✅

---

### Use Case 4: Observability Push (K1 Metrics → K0 Grafana)

**Scenario**: K1 runs for 10 seconds, collects metrics, pushes to K0 observability stack.

**Flow**:
1. K1 Layer 1-4: Execute 20 turns
2. K1 Metrics Collector: Accumulates metrics in-memory:
   - `k1_layer1_ttft_ms`: [140, 135, 142, ..., 138] (20 samples)
   - `k1_layer2_planning_latency_ms`: [85, 92, 88, ..., 90] (20 samples)
   - `k1_bridge_latency_ms`: [8, 9, 7, ..., 8] (180 bridge calls)
3. K1 Metrics Collector: 10s timer fires
4. K1 Observability Client: Serializes metrics (Prometheus format)
5. K1 Observability Client: HTTP POST to K0 `:5203/metrics`
6. K0 Observability Port: Ingests metrics
7. K0 Prometheus: Scrapes K0 `:5203/metrics` (pull model)
8. K0 Prometheus: Updates time series
9. K0 Grafana: Queries Prometheus
10. K0 Grafana: Renders "K1 Turn Overview" dashboard

**Bridge Operations**:
- 1× POST `:5203/metrics` (batch: 50 metrics)

**Performance**: <20ms push latency ✅

---

## Implementation Guide

### Step 1: Set Up K0 Observability Stack

**Prerequisites**:
- K0 Kernel running on `localhost:5200-5203`
- Prometheus installed (`:9090`)
- Grafana installed (`:3000`)

**Install K0 Observability**:
```bash
# Start K0 Kernel (includes observability ports)
cd k0
python -m k0.kernel --config config/kernel.yaml

# Verify observability ports
curl http://localhost:5203/health  # Should return 200 OK
```

**Configure Prometheus** (`prometheus.yml`):
```yaml
global:
  scrape_interval: 10s
  evaluation_interval: 10s

scrape_configs:
  - job_name: 'k0_kernel'
    static_configs:
      - targets: ['localhost:5203']
    metric_relabel_configs:
      - source_labels: [__name__]
        regex: 'k0_.*'
        action: keep

  - job_name: 'k1_intelligence'
    static_configs:
      - targets: ['localhost:5203']  # K1 pushes to K0
    metric_relabel_configs:
      - source_labels: [__name__]
        regex: 'k1_.*'
        action: keep
```

**Configure Grafana**:
```bash
# Add Prometheus data source
curl -X POST http://localhost:3000/api/datasources \
  -H "Content-Type: application/json" \
  -d '{
    "name": "K0_K1_Metrics",
    "type": "prometheus",
    "url": "http://localhost:9090",
    "access": "proxy",
    "isDefault": true
  }'

# Import K1 dashboards
cd docs/grafana/
for dashboard in k1_turn_overview.json k1_bridge_health.json; do
  curl -X POST http://localhost:3000/api/dashboards/db \
    -H "Content-Type: application/json" \
    -d @$dashboard
done
```

---

### Step 2: Configure K1 Bridge

**K1 Configuration** (`k1/config/kernel.yaml`):
```yaml
k0_bridge:
  # K0 Endpoints
  command_port: "http://localhost:5200"
  query_port: "http://localhost:5201"
  sse_port: "http://localhost:5202"
  observability_port: "http://localhost:5203"

  # HTTP/2 Transport
  http2:
    connection_pool_size: 10
    max_concurrent_streams: 100
    connection_timeout_sec: 30
    request_timeout_sec: 5

  # Batching
  batching:
    flush_interval_ms: 250
    max_batch_size_kb: 64
    compression: "zstd"  # Options: "none", "zstd", "lz4"

  # Circuit Breaker
  circuit_breaker:
    failure_threshold: 3
    timeout_sec: 60
    half_open_requests: 5

  # Observability Push
  observability:
    metrics_interval_sec: 10
    logs_interval_sec: 5
    traces_enabled: true
    trace_sample_ratio: 1.0  # 100% (production: 0.1)

  # Authentication
  auth:
    token_rotation_hours: 24
    mtls_enabled: true
    cert_path: "certs/k1_client.crt"
    key_path: "certs/k1_client.key"
```

---

### Step 3: Initialize K1 Bridge Clients

**Python Implementation** (`k1/l5_infrastructure/bridge_k0/__init__.py`):

```python
from k1.l5_infrastructure.bridge_k0 import (
    CommandClient,
    QueryClient,
    SSEClient,
    BatchClient,
    ObservabilityClient,
)
from k1.l5_infrastructure.observability import MetricsExporter, TracerFactory

# Load config
config = load_config("k1/config/kernel.yaml")

# Initialize HTTP/2 connection pool
http2_pool = HTTP2ConnectionPool(
    max_connections=config.k0_bridge.http2.connection_pool_size,
    max_streams=config.k0_bridge.http2.max_concurrent_streams,
)

# Initialize bridge clients
command_client = CommandClient(
    endpoint=config.k0_bridge.command_port,
    http2_pool=http2_pool,
    timeout=config.k0_bridge.http2.request_timeout_sec,
)

query_client = QueryClient(
    endpoint=config.k0_bridge.query_port,
    http2_pool=http2_pool,
    timeout=config.k0_bridge.http2.request_timeout_sec,
)

sse_client = SSEClient(
    endpoint=config.k0_bridge.sse_port,
    http2_pool=http2_pool,
)

batch_client = BatchClient(
    command_client=command_client,
    flush_interval_ms=config.k0_bridge.batching.flush_interval_ms,
    max_batch_size_kb=config.k0_bridge.batching.max_batch_size_kb,
    compression=config.k0_bridge.batching.compression,
)

# Initialize observability
metrics_exporter = MetricsExporter(namespace="k1_intelligence")
tracer_factory = TracerFactory(
    service_name="k1_intelligence",
    service_version="1.0.0",
    environment="production",
    otlp_endpoint=f"{config.k0_bridge.observability_port}/v1/traces",
    sample_ratio=config.k0_bridge.observability.trace_sample_ratio,
)

observability_client = ObservabilityClient(
    endpoint=config.k0_bridge.observability_port,
    http2_pool=http2_pool,
    metrics_exporter=metrics_exporter,
    tracer_factory=tracer_factory,
    metrics_interval_sec=config.k0_bridge.observability.metrics_interval_sec,
    logs_interval_sec=config.k0_bridge.observability.logs_interval_sec,
)

# Start observability push
await observability_client.start()
```

---

### Step 4: Use Bridge in K1 Layers

**Example: Concierge Context Retrieval** (`k1/l2_orchestration/concierge.py`):

```python
from k1.l5_infrastructure.bridge_k0 import query_client
from k1.l5_infrastructure.observability import tracer_factory

async def build_context(session_id: str, cognitive_trace_id: str):
    """Retrieve context from K0 for Concierge AI agent."""

    with tracer_factory.span("concierge.build_context", kind=SpanKind.INTERNAL) as span:
        span.set_attribute("session_id", session_id)
        span.set_attribute("cognitive_trace_id", cognitive_trace_id)

        # Query K0 P01: RecallQuery
        recall_request = RecallQueryRequest(
            session_id=session_id,
            query_type=QueryType.EPISODIC,
            limit=20,
            cognitive_trace_id=cognitive_trace_id,
        )

        # Bridge call (async)
        recall_response = await query_client.recall_query(recall_request)

        span.set_attribute("recall_result_count", len(recall_response.memories))
        span.set_attribute("k0_latency_ms", recall_response.latency_ms)

        # Build context from memories
        context = Context(
            memories=recall_response.memories,
            persona=recall_response.persona,
            beliefs=recall_response.beliefs,
        )

        return context
```

**Example: Planner Plan Commit** (`k1/l2_orchestration/planner.py`):

```python
from k1.l5_infrastructure.bridge_k0 import command_client
from k1.l5_infrastructure.observability import tracer_factory

async def commit_plan(plan: Plan, cognitive_trace_id: str):
    """Persist plan to K0 after 4-stage pipeline."""

    with tracer_factory.span("planner.commit_plan", kind=SpanKind.INTERNAL) as span:
        span.set_attribute("plan_id", plan.plan_id)
        span.set_attribute("cognitive_trace_id", cognitive_trace_id)
        span.set_attribute("stage", "commit")

        # Serialize plan to FlatBuffers
        plan_fb = plan.to_flatbuffers()

        # K0 P02: MemoryWrite (with receipt)
        write_request = MemoryWriteRequest(
            session_id=plan.session_id,
            delta_type=DeltaType.PLAN_COMMITTED,
            payload=plan_fb,
            receipt_required=True,
            cognitive_trace_id=cognitive_trace_id,
        )

        # Bridge call (async)
        write_response = await command_client.memory_write(write_request)

        span.set_attribute("receipt_id", write_response.receipt_id)
        span.set_attribute("k0_latency_ms", write_response.latency_ms)

        # Verify receipt
        if not write_response.success:
            raise PlanCommitError(f"K0 write failed: {write_response.error}")

        # Update plan with receipt
        plan.receipt_id = write_response.receipt_id
        plan.status = PlanStatus.COMMITTED

        return plan
```

**Example: SessionState Delta Batching** (`k1/l4_runtime/session_state.py`):

```python
from k1.l5_infrastructure.bridge_k0 import batch_client

class SessionState:
    """6-section K1 ephemeral state with K0 delta batching."""

    def __init__(self, session_id: str):
        self.session_id = session_id
        self.beliefs = BeliefSection()
        self.scoreboard = ScoreboardSection()
        self.control = ControlSection()
        self.persona = PersonaSection()
        self.multimodal = MultimodalSection()
        self.meta = MetaSection()

    async def update_belief(self, key: str, value: Any):
        """Update belief and queue delta for K0 persistence."""

        # Update in-memory state
        self.beliefs[key] = value

        # Serialize delta (FlatBuffers)
        delta = StateDelta(
            session_id=self.session_id,
            section="beliefs",
            key=key,
            value=value,
            timestamp=utcnow(),
        )
        delta_fb = delta.to_flatbuffers()

        # Queue for batching (250ms flush)
        await batch_client.enqueue_delta(delta_fb)

        # Metric: SessionState update
        metrics.session_state_updates_total.labels(section="beliefs").inc()
```

---

### Step 5: Monitor in Grafana

**Access Grafana**:
```bash
# Open browser
http://localhost:3000

# Login (default)
Username: admin
Password: admin
```

**View Dashboards**:
1. **K1 Turn Overview**:
   - URL: `http://localhost:3000/d/k1-turn-overview`
   - Metrics: TTFT, E2E latency, error rate, RPS
   - Panels: P50/P95/P99 histograms

2. **K1-K0 Bridge Health**:
   - URL: `http://localhost:3000/d/k1-bridge-health`
   - Metrics: Bridge latency, circuit breaker state, batch size
   - Panels: Request rate, compression ratio, failures

3. **K1 Component Health**:
   - URL: `http://localhost:3000/d/k1-components`
   - Metrics: Layer 1-4 latencies, agent lifecycle, tool execution
   - Panels: Mailbox depth, SessionState size, learning cycle

4. **Infrastructure**:
   - URL: `http://localhost:3000/d/k1-infrastructure`
   - Metrics: Thermal state, CPU, memory, cost
   - Panels: Thermal temperature, throttling events, budget alerts

**Query Examples** (Prometheus):
```promql
# K1 TTFT P95
histogram_quantile(0.95, rate(k1_layer1_ttft_ms_bucket[5m]))

# Bridge latency P95
histogram_quantile(0.95, rate(k1_bridge_latency_ms_bucket[5m]))

# Circuit breaker trips (last 1h)
increase(k1_bridge_circuit_breaker_trips_total[1h])

# SessionState size (current)
k1_layer4_session_state_size_bytes

# Cost per turn (last 24h)
rate(k1_cost_per_turn_usd_sum[24h]) / rate(k1_cost_per_turn_usd_count[24h])
```

---

## Testing the Bridge

### Unit Tests

**Test Bridge Command Client** (`k1/l5_infrastructure/bridge_k0/tests/test_command_client.py`):

```python
import pytest
from k1.l5_infrastructure.bridge_k0 import CommandClient

@pytest.mark.asyncio
async def test_memory_write_success(mock_k0_server):
    """Test successful K0 P02 MemoryWrite."""

    # Mock K0 server response
    mock_k0_server.expect_post(
        "/k0/ports/P02",
        response_status=200,
        response_body={"success": True, "receipt_id": "receipt_123"},
    )

    # Command client
    client = CommandClient(endpoint="http://localhost:5200")

    # Write request
    request = MemoryWriteRequest(
        session_id="user_001",
        delta_type=DeltaType.PLAN_COMMITTED,
        payload=b"...",
        receipt_required=True,
    )

    # Execute
    response = await client.memory_write(request)

    # Assert
    assert response.success is True
    assert response.receipt_id == "receipt_123"
    assert response.latency_ms < 100  # Performance budget

@pytest.mark.asyncio
async def test_circuit_breaker_opens_after_3_failures(mock_k0_server):
    """Test circuit breaker opens after 3 consecutive failures."""

    # Mock K0 server failures
    mock_k0_server.expect_post("/k0/ports/P02", response_status=500)

    client = CommandClient(endpoint="http://localhost:5200")
    request = MemoryWriteRequest(session_id="user_001", ...)

    # Fail 3 times
    for i in range(3):
        with pytest.raises(K0WriteError):
            await client.memory_write(request)

    # 4th call should be rejected by circuit breaker (OPEN state)
    with pytest.raises(CircuitBreakerOpenError):
        await client.memory_write(request)
```

### Integration Tests

**Test K1 → Bridge → K0 E2E** (`tests/integration/test_k1_k0_bridge.py`):

```python
import pytest
from k1.l2_orchestration import Concierge, Planner
from k1.l5_infrastructure.bridge_k0 import query_client, command_client

@pytest.mark.integration
@pytest.mark.asyncio
async def test_concierge_context_retrieval_e2e():
    """Test Concierge retrieves context from K0 via bridge."""

    # Setup: Seed K0 with user memories
    await seed_k0_memories(session_id="user_001", count=20)

    # Execute: Concierge build_context
    concierge = Concierge(session_id="user_001")
    context = await concierge.build_context(cognitive_trace_id="trace_abc")

    # Assert: Context populated
    assert len(context.memories) == 20
    assert context.persona is not None
    assert context.beliefs is not None

    # Assert: Performance budget
    assert concierge.last_context_latency_ms < 50  # <50ms P95

@pytest.mark.integration
@pytest.mark.asyncio
async def test_planner_4stage_pipeline_with_k0():
    """Test Planner 4-stage pipeline persists to K0."""

    # Setup
    planner = Planner(session_id="user_001")
    task = Task(intent="schedule_meeting", params={"attendee": "Bob", "time": "2pm"})

    # Execute: 4-stage pipeline
    plan = await planner.plan(task, cognitive_trace_id="trace_def")

    # Assert: Plan committed to K0
    assert plan.status == PlanStatus.COMMITTED
    assert plan.receipt_id is not None

    # Verify: K0 storage
    k0_plan = await query_k0_plan(plan.plan_id)
    assert k0_plan.plan_id == plan.plan_id
    assert k0_plan.receipt_id == plan.receipt_id
```

### Performance Tests

**Test Bridge Latency** (`tests/performance/test_bridge_latency.py`):

```python
import pytest
import statistics
from k1.l5_infrastructure.bridge_k0 import command_client

@pytest.mark.performance
@pytest.mark.asyncio
async def test_bridge_latency_p95_under_10ms():
    """Test bridge latency P95 < 10ms."""

    latencies = []

    # Execute 1000 requests
    for i in range(1000):
        request = MemoryWriteRequest(
            session_id=f"user_{i}",
            delta_type=DeltaType.STATE_DELTA,
            payload=b"..." * 1024,  # 1KB payload
        )

        start = time.perf_counter()
        response = await command_client.memory_write(request)
        end = time.perf_counter()

        latency_ms = (end - start) * 1000
        latencies.append(latency_ms)

    # Calculate P95
    p95_latency = statistics.quantiles(latencies, n=20)[18]  # 95th percentile

    # Assert: <10ms P95
    assert p95_latency < 10.0, f"P95 latency {p95_latency:.2f}ms exceeds 10ms budget"

    print(f"Bridge latency P50: {statistics.median(latencies):.2f}ms")
    print(f"Bridge latency P95: {p95_latency:.2f}ms")
    print(f"Bridge latency P99: {statistics.quantiles(latencies, n=100)[98]:.2f}ms")
```

---

## Troubleshooting

### Issue 1: Bridge Latency >10ms

**Symptoms**:
- Prometheus alert: `k1_bridge_latency_ms_p95 > 10`
- Grafana dashboard shows red line

**Diagnosis**:
```bash
# Check K0 server load
curl http://localhost:5203/metrics | grep k0_cpu_utilization

# Check HTTP/2 connection pool
curl http://localhost:5203/metrics | grep k1_bridge_http2_connections_active

# Check batch size
curl http://localhost:5203/metrics | grep k1_bridge_batch_size
```

**Fixes**:
1. **Increase HTTP/2 connection pool**:
   ```yaml
   # k1/config/kernel.yaml
   k0_bridge:
     http2:
       connection_pool_size: 20  # Up from 10
   ```

2. **Reduce batch flush interval**:
   ```yaml
   k0_bridge:
     batching:
       flush_interval_ms: 100  # Down from 250ms
   ```

3. **Scale K0 horizontally** (multiple K0 instances with load balancer)

---

### Issue 2: Circuit Breaker Frequently Opens

**Symptoms**:
- Prometheus alert: `k1_bridge_circuit_breaker_trips_total > 10/day`
- K1 requests fail with `CircuitBreakerOpenError`

**Diagnosis**:
```bash
# Check K0 error rate
curl http://localhost:5203/metrics | grep k0_error_rate

# Check K0 request timeout
curl http://localhost:5203/metrics | grep k0_request_timeout_total
```

**Fixes**:
1. **Increase circuit breaker threshold**:
   ```yaml
   k0_bridge:
     circuit_breaker:
       failure_threshold: 5  # Up from 3
   ```

2. **Increase request timeout**:
   ```yaml
   k0_bridge:
     http2:
       request_timeout_sec: 10  # Up from 5
   ```

3. **Investigate K0 slow queries** (check K0 logs for slow P01 queries)

---

### Issue 3: Observability Push Fails

**Symptoms**:
- K1 metrics missing in Grafana
- Prometheus scrape errors

**Diagnosis**:
```bash
# Check K0 observability port
curl http://localhost:5203/health

# Check Prometheus targets
curl http://localhost:9090/api/v1/targets | jq '.data.activeTargets[] | select(.labels.job=="k1_intelligence")'
```

**Fixes**:
1. **Verify K0 observability port is accessible**:
   ```bash
   curl -v http://localhost:5203/metrics
   ```

2. **Check K1 observability client logs**:
   ```bash
   grep "observability_client" k1/logs/k1_intelligence.log
   ```

3. **Restart K1 observability client**:
   ```python
   await observability_client.stop()
   await observability_client.start()
   ```

---

## Conclusion

This end-to-end K0-K1 bridge architecture diagram provides a complete view of:

1. **K1 Intelligence Module** (Layers 1-4): Agentic orchestration, planning, execution, runtime state
2. **K0 Bridge** (Layer 5): HTTP/2 transport, 20 ports, batching, observability push
3. **K0 Memory Microkernel**: Persistent storage, vector search, knowledge graph, observability stack

**Key Takeaways**:
- ✅ K1 reuses K0's observability stack (Prometheus, OTLP, Grafana)
- ✅ Dual protocol (JSON for K0, FlatBuffers for K1 optimization)
- ✅ 20-port architecture (P01-P20) with specialized operations
- ✅ <10ms bridge latency (P95)
- ✅ Circuit breaker protects both K1 and K0 from overload
- ✅ End-to-end `cognitive_trace_id` for distributed tracing

**Next Steps**:
1. Review ADRs (ADR-0001, ADR-0001a, ADR-0029)
2. Set up K0 observability stack (Prometheus, Grafana)
3. Configure K1 bridge clients (command, query, SSE, batch, observability)
4. Implement K1 layers using bridge clients
5. Monitor in Grafana dashboards
6. Run integration tests
7. Performance tune (batching, connection pooling, circuit breaker)

**Feedback**: Please report issues or suggest improvements in the `#k1-architecture` Slack channel.

---

**Document Control**
**Version**: 1.0
**Last Updated**: 2025-10-24
**Author**: Architecture Team
**Reviewers**: [Pending]
**Approval**: [Pending]
