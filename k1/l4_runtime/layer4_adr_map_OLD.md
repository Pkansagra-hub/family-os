# Layer 4 (Runtime Core) — ADR Family Map

**Complete end-to-end ADR references for K1 Layer 4 modules**

---

## 📋 Overview

**Layer 4 Purpose:** Runtime Core (SessionState, Actor Fabric, Learning Loop, Attention)
**Performance Budget:** <1ms SessionState ops, <1ms mailbox enqueue, <100ms learning cycle
**Modules:** 8 modules across 4 categories
**Primary Function:** Runtime state management + actor infrastructure + cognitive loops + attention gating

---

## 🗺️ Layer 4 Architecture

### Core ADRs

| ADR | Title | Status | Priority | Coverage |
|-----|-------|--------|----------|----------|
| **ADR-0004** | 52-Module 5-Layer Architecture | ✅ Complete | 🔴 CRITICAL | Layer 4 definition, 8-module runtime core |
| **ADR-0017** | SessionState 6-Section Design | ✅ Complete | 🔴 CRITICAL | Beliefs, scoreboard, control, persona, multimodal, meta sections |
| **ADR-0002** | Actor Model | ✅ Complete | 🔴 CRITICAL | Actor fabric infrastructure (mailbox, router, supervisor) |
| **ADR-0018** | Learning Loop | ✅ Complete | 🟡 HIGH | Feedback integration, self-model updates, <100ms cycle |
| **ADR-0020** | Attention Mechanism | ✅ Complete | 🟡 HIGH | Salience, focus, distraction filtering |
| **ADR-0004d** | Layer 4 Integration Tests | ✅ Complete | 🟡 HIGH | SessionState serialization, learning loop, <1ms serialize |

---

## 📁 Module-by-Module ADR Map

## Category 1: session_state/ (3 modules)

### **Module 1.1: session_state/model/**
**Purpose:** SessionState 6-section data model
**Location:** `k1/l4_runtime/session_state/model.py`
**Performance:** <1ms serialize/deserialize (FlatBuffers)

#### Primary ADRs

- **ADR-0017** — SessionState 6-Section Design (beliefs, scoreboard, control, persona, multimodal, meta)
- **ADR-0017a** — Beliefs Section (fact storage, confidence, temporal decay)
- **ADR-0017b** — Scoreboard Section (QUD stack, entity tracking, salience)
- **ADR-0017c** — Control Section (current_flow, agent_roster, execution_state)
- **ADR-0017d** — Persona Section (personality traits, LLM system prompt)
- **ADR-0017e** — Multimodal Section (audio waveforms, image embeddings)
- **ADR-0017f** — Meta Section (session metadata, creation_time, total_turns)

#### Related ADRs

- **ADR-0011** — FlatBuffers Serialization (SessionState serialization format)
- **ADR-0012b** — SessionState Root Schema (SEST FlatBuffers schema)
- **ADR-0019** — SessionState Serialization (64KB soft limit, 128KB hard limit, 3-tier eviction)
- **ADR-0024** — Performance Budgets (SessionState <1ms serialize/deserialize)

#### Key Responsibilities

1. **6-Section Architecture:**
   - **Beliefs:** User beliefs, intent history, confidence scores, temporal decay
   - **Scoreboard:** QUD stack, entity tracking, salience (0.0-1.0), pronoun mapping
   - **Control:** current_flow, agent_roster, execution_state, saga_log
   - **Persona:** Personality traits, LLM system prompt injection
   - **Multimodal:** Audio waveforms, image embeddings, video frames
   - **Meta:** Session metadata (session_id, creation_time, total_turns, last_updated)

2. **Size Management:**
   - Soft limit: 64KB (typical)
   - Hard limit: 128KB (enforcement)
   - 3-tier eviction: beliefs (P3), multimodal (P2), scoreboard (P1)

3. **Serialization:**
   - FlatBuffers format (11× faster than JSON)
   - Zero-copy deserialization
   - <1ms P95 serialize/deserialize

**Performance Metrics:**
- Serialize: <1ms P95 (64KB typical)
- Deserialize: <0.1ms P95
- Size: 64KB soft, 128KB hard
- Eviction overhead: <5ms P95

---

### **Module 1.2: session_state/control/**
**Purpose:** SessionState control plane (locking, updates, sync)
**Location:** `k1/l4_runtime/session_state/control.py`
**Performance:** <0.1ms locking, <2ms delta batching

#### Primary ADRs

- **ADR-0017c** — Control Section (current_flow, agent_roster, execution_state)
- **ADR-0007d** — SessionState Locking (current_flow field, flow_id, concurrent plan prevention)
- **ADR-0001f** — SessionState Delta Batching (250ms batching, P02 MemoryWrite)

#### Related ADRs

- **ADR-0019** — SessionState Serialization (delta computation)
- **ADR-0024** — Performance Budgets (locking <0.1ms)

#### Key Responsibilities

1. **Locking Mechanism:**
   - current_flow field lock (prevent concurrent plan execution)
   - flow_id tracking
   - <0.1ms lock/unlock overhead

2. **Delta Batching:**
   - Batch SessionState updates every 250ms
   - Compute field-level deltas (field_path, old_value, new_value)
   - Send to K0 via STATE_DELTA messages

3. **Execution State Tracking:**
   - Track agent_roster (active agents)
   - Monitor execution_state (IDLE/EXECUTING/DRAINING/HALTED)
   - Saga log maintenance

**Performance Metrics:**
- Lock operation: <0.1ms P95
- Delta computation: <1ms P95
- Batch interval: 250ms
- Batch size: 10-50 deltas typical

---

### **Module 1.3: session_state/memory_manager/**
**Purpose:** In-memory SessionState management
**Location:** `k1/l4_runtime/session_state/memory_manager.py`
**Performance:** <5ms eviction, >90% hit rate

#### Primary ADRs

- **ADR-0019** — SessionState Serialization (3-tier eviction, 64KB/128KB limits)
- **ADR-0012b** — Memory Manager Schema (MemorySnapshot, EvictionCandidate, MemoryUsage)

#### Related ADRs

- **ADR-0017** — SessionState 6-Section Design (eviction priorities)
- **ADR-0024** — Performance Budgets (eviction <5ms)
- **ADR-0029** — Prometheus Metrics (memory usage, eviction rate)

#### Key Responsibilities

1. **3-Tier Eviction:**
   - **Priority 1 (beliefs):** Least important, evict first
   - **Priority 2 (multimodal):** Medium importance
   - **Priority 3 (scoreboard):** Most important, never evict current QUD

2. **Size Enforcement:**
   - Soft limit: 64KB (trigger warning)
   - Hard limit: 128KB (forced eviction)
   - Eviction algorithm: Hybrid LRU + priority-based

3. **Memory Tracking:**
   - Per-section size tracking
   - Eviction candidate identification
   - Persistence checkpoints (every 1000 deltas)

**Performance Metrics:**
- Eviction: <5ms P95
- Hit rate: >90% (cached sessions)
- Miss penalty: 50-100ms (K0 reload)
- Memory overhead: <10MB per session

---

## Category 2: actor_fabric/ (3 modules)

### **Module 2.1: actor_fabric/mailbox/**
**Purpose:** MPSC message queues (4-tier priority)
**Location:** `k1/l4_runtime/actor_fabric/mailbox/`
**Performance:** <1ms enqueue/dequeue

#### Primary ADRs

- **ADR-0002a** — Actor Fabric Mailbox (MPSC queue, 4-tier priority, WFQ scheduler)
- **ADR-0028** — WFQ Scheduler (weight-based fairness, URGENT 10×, BACKGROUND 1×)

#### Related ADRs

- **ADR-0024** — Performance Budgets (mailbox <1ms)
- **ADR-0029** — Prometheus Metrics (mailbox depth, message rate, DLQ)

#### Key Responsibilities

**Sub-Module 2.1.1: mailbox/mpsc_queue.py**
- Ring buffer implementation
- 4-tier priority: URGENT, REALTIME, INTERACTIVE, BACKGROUND
- Backpressure: High watermark (50), low watermark (25)
- Dead Letter Queue: 100 messages, 5 min retention

**Sub-Module 2.1.2: mailbox/scheduler.py**
- WFQ scheduling (Weighted Fair Queuing)
- Priority weights: URGENT 10.0, REALTIME 5.0, INTERACTIVE 2.0, BACKGROUND 1.0
- Starvation prevention: Virtual time aging
- Anti-starvation threshold: 5s max wait

**Sub-Module 2.1.3: mailbox/backpressure.py**
- High watermark (50 messages): Slow down producer
- Low watermark (25 messages): Resume normal rate
- Overflow policies: DROP_OLDEST, DROP_NEWEST, REJECT
- Metrics: Backpressure events, dropped messages

**Sub-Module 2.1.4: mailbox/dlq.py**
- Dead Letter Queue: 100 messages max
- Retention: 5 min
- Dropped reasons: TIMEOUT, OVERFLOW, VALIDATION_ERROR, DESTINATION_UNREACHABLE
- Debugging: Inspect failed messages

**Performance Metrics:**
- Enqueue: <1ms P95
- Dequeue: <0.5ms P95
- Mailbox depth: <10 typical, <50 high watermark
- Message throughput: 1000+ msgs/sec
- DLQ size: <5 typical, <100 max

---

### **Module 2.2: actor_fabric/router/**
**Purpose:** Message routing & admission control
**Location:** `k1/l4_runtime/actor_fabric/router/`
**Performance:** <1ms routing, <2ms admission

#### Primary ADRs

- **ADR-0002c** — Actor Router (location transparency, 5-check pipeline)
- **ADR-0010c** — Capability Enforcement (admission control integration)

#### Related ADRs

- **ADR-0024** — Performance Budgets (routing <1ms)
- **ADR-0029** — Prometheus Metrics (routing latency, admission rejections)

#### Key Responsibilities

**Sub-Module 2.2.1: router/router.py**
- Location transparency: Hash table by actor_id
- Routing table: O(1) lookup
- 5-check pipeline: Admission → Capability → Rate Limit → Quota → Destination

**Sub-Module 2.2.2: router/admission.py**
- 5-check admission control:
  1. **Capability verification:** HMAC-SHA256 signature validation
  2. **Role attestation:** Sender/receiver role match
  3. **Token bucket:** 100 msg/s sustained, 150 burst
  4. **In-flight limits:** Max 100 concurrent messages per sender
  5. **Session quotas:** Max 1000 messages per session

**Sub-Module 2.2.3: router/token_bucket.py**
- Token bucket algorithm (100 msg/s sustained)
- Burst allowance: 150 messages
- Refill rate: 100 tokens/sec
- Per-sender tracking

**Sub-Module 2.2.4: router/capability_verifier.py**
- HMAC-SHA256 signature verification
- Lease expiration check
- Sender/receiver role match
- Resource type validation (TOOL_CALL, MEMORY_READ, MEMORY_WRITE, MODEL_CALL, NETWORK_ACCESS)

**Performance Metrics:**
- Routing: <1ms P95
- Admission: <2ms P95 (5 checks)
- Capability verification: <0.5ms P95
- Token bucket overhead: <0.1ms P95
- Rejection rate: <5% (normal operation)

---

### **Module 2.3: actor_fabric/supervisor/**
**Purpose:** Health monitoring & crash recovery
**Location:** `k1/l4_runtime/actor_fabric/supervisor/`
**Performance:** <100ms crash detection, <2s restart

#### Primary ADRs

- **ADR-0002b** — Actor Fabric Supervisor (heartbeat, crash detection, blacklist)
- **ADR-0005d** — Agent Supervisor (agent-specific supervision)

#### Related ADRs

- **ADR-0024** — Performance Budgets (crash detection <100ms)
- **ADR-0029** — Prometheus Metrics (crash rate, blacklist, restart attempts)

#### Key Responsibilities

**Sub-Module 2.3.1: supervisor/health_check.py**
- Heartbeat monitoring: 1 Hz ping, 1.5s timeout
- Event-loop heartbeat: 200ms interval (detect event-loop stalls)
- Health status: HEALTHY, DEGRADED, UNHEALTHY

**Sub-Module 2.3.2: supervisor/crash_detection.py**
- Crash detection: <100ms detection latency
- Detection methods: Process termination, ping timeout, event-loop stall
- Crash logging: Stack traces, last 100 messages, state dump

**Sub-Module 2.3.3: supervisor/blacklist.py**
- Blacklist policy: 3 crashes in 10 min → 1 hour ban
- Per-version blacklist (buggy agent versions)
- Effectiveness: 88% reduction in repeated crashes

**Sub-Module 2.3.4: supervisor/restart.py**
- Exponential backoff: 200ms → 400ms → 800ms → 1.6s → 3.2s → 30s max
- Max attempts: 5 retries
- Reset interval: 10 min (success → reset retry count)

**Performance Metrics:**
- Heartbeat overhead: <1% CPU
- Crash detection: <100ms P95
- Restart latency: 200ms-30s (exponential backoff)
- Blacklist enforcement: <1ms lookup
- Supervisor overhead: <5ms per actor per second

---

## Category 3: learning/ (1 module)

### **Module 3.1: learning/loop/**
**Purpose:** Online learning & self-model updates
**Location:** `k1/l4_runtime/learning/loop.py`
**Performance:** <100ms learning cycle

#### Primary ADRs

- **ADR-0018** — Learning Loop (feedback integration, self-model updates)
- **ADR-0018a** — Feedback Signal (FeedbackSignal FlatBuffers schema)
- **ADR-0018b** — Self-Model Update (belief revision, confidence adjustment)
- **ADR-0018c** — Regret Minimization (counterfactual reasoning)

#### Related ADRs

- **ADR-0001** — K0 Integration (P20 Self-Model Update pipeline)
- **ADR-0024** — Performance Budgets (learning <100ms)
- **ADR-0029** — Prometheus Metrics (learning cycle latency, update rate)

#### Key Responsibilities

1. **Feedback Integration:**
   - Receive FeedbackSignal events (explicit/implicit feedback)
   - Feedback types: THUMBS_UP, THUMBS_DOWN, CORRECTION, CANCELLATION
   - Feedback source: User, system, agent

2. **Self-Model Update:**
   - Belief revision: Update SessionState beliefs section
   - Confidence adjustment: Decay incorrect beliefs, boost correct ones
   - Learning rate: 0.1 (gradual updates)

3. **Regret Minimization:**
   - Counterfactual reasoning: "What if we did X instead?"
   - Alternative action scoring: Compare actual vs hypothetical outcomes
   - Policy update: Adjust agent selection weights

4. **K0 Integration:**
   - Send self-model updates to K0 P20 Self-Model Update pipeline
   - Track learning events in episodic memory
   - Long-term learning: Aggregate feedback over sessions

**Performance Metrics:**
- Learning cycle: <100ms P95
- Feedback latency: <50ms (ingestion)
- Belief update: <10ms P95
- K0 write latency: <20ms P95
- Update rate: 0.1-1 updates/turn (typical)

---

## Category 4: attention/ (1 module)

### **Module 4.1: attention/gate/**
**Purpose:** Attention mechanism & salience-based filtering
**Location:** `k1/l4_runtime/attention/gate.py`
**Performance:** <5ms attention computation

#### Primary ADRs

- **ADR-0020** — Attention Mechanism (salience, focus, distraction filtering)
- **ADR-0020a** — Salience Computation (recency + frequency + importance weights)
- **ADR-0020b** — Focus Gating (threshold-based filtering, top-k selection)
- **ADR-0020c** — Distraction Filtering (context pruning, irrelevant entity removal)

#### Related ADRs

- **ADR-0017b** — Scoreboard Section (entity salience tracking)
- **ADR-0024** — Performance Budgets (attention <5ms)

#### Key Responsibilities

1. **Salience Computation:**
   - Recency weight: Exponential decay (0.9 per turn)
   - Frequency weight: Access count normalization
   - Importance weight: User-explicit mentions (2× boost)
   - Combined score: 0.4 × recency + 0.3 × frequency + 0.3 × importance

2. **Focus Gating:**
   - Salience threshold: 0.3 (filter low-salience entities)
   - Top-k selection: Keep top 10 entities in focus
   - Focus transition: <5ms computation

3. **Distraction Filtering:**
   - Context pruning: Remove entities below threshold
   - Irrelevant entity removal: Drop entities not mentioned in last 5 turns
   - Attention budget: Limit total entities in SessionState scoreboard

4. **Integration:**
   - Read from SessionState scoreboard section
   - Update entity salience scores
   - Prune low-salience entities before LLM invocation

**Performance Metrics:**
- Salience computation: <5ms P95
- Focus transition: <5ms P95
- Distraction filtering: <2ms P95
- Entity count: 5-20 typical, 50 max
- Attention overhead: <10ms per turn

---

## 🔗 Cross-Cutting ADRs (Affect All Layer 4 Modules)

### **Architecture & Design**
- **ADR-0002** — Actor Model (all Layer 4 actor infrastructure)
- **ADR-0004** — 52-Module 5-Layer Architecture (Layer 4 definition)
- **ADR-0004b** — Import Linting (L4→L5 only, no L4→L1/L2/L3 imports)
- **ADR-0004d** — Layer 4 Integration Tests

### **Serialization & Data**
- **ADR-0011** — FlatBuffers Serialization (SessionState, FeedbackSignal)
- **ADR-0012b** — SessionState Root Schema (SEST FlatBuffers schema)
- **ADR-0013** — Schema Versioning

### **Observability**
- **ADR-0029** — Prometheus Metrics (SessionState size, mailbox depth, crash rate, learning rate)
- **ADR-0030** — Trace Sampling (cognitive_trace_id propagation)

### **Performance & Reliability**
- **ADR-0024** — Performance Budgets (Layer 4: SessionState <1ms, mailbox <1ms, learning <100ms)
- **ADR-0028** — WFQ Scheduler (mailbox priority scheduling)
- **ADR-0009** — Circuit Breaker (actor fabric resilience)

### **Security & Privacy**
- **ADR-0010** — Capability Security (actor fabric admission control)
- **ADR-0010c** — Capability Enforcement (router integration)

---

## 🎯 Layer 4 Performance Budget Breakdown

### **Total Layer 4 Budget: <1ms typical operations**

| Component | Budget | Typical | P95 | ADR |
|-----------|--------|---------|-----|-----|
| SessionState serialize | 1ms | 0.5ms | 1ms | ADR-0019 |
| SessionState deserialize | 0.1ms | 0.05ms | 0.1ms | ADR-0019 |
| SessionState lock | 0.1ms | 0.05ms | 0.1ms | ADR-0007d |
| SessionState delta batch | 2ms | 1ms | 2ms | ADR-0001f |
| SessionState eviction | 5ms | 3ms | 5ms | ADR-0019 |
| Mailbox enqueue | 1ms | 0.5ms | 1ms | ADR-0002a |
| Mailbox dequeue | 0.5ms | 0.3ms | 0.5ms | ADR-0002a |
| Router admission (5 checks) | 2ms | 1ms | 2ms | ADR-0002c |
| Capability verification | 0.5ms | 0.3ms | 0.5ms | ADR-0010c |
| Supervisor heartbeat | 5ms | 3ms | 5ms | ADR-0002b |
| Crash detection | 100ms | 50ms | 100ms | ADR-0002b |
| Learning cycle | 100ms | 50ms | 100ms | ADR-0018 |
| Attention computation | 5ms | 3ms | 5ms | ADR-0020 |

---

## 🔄 Layer 4 Integration Points

### **Layer 4 ← Layer 2/3 (State Updates)**

```
Layer 2/3 writes:               Layer 4 manages:
────────────────                ────────────────
AgentState               →      session_state/control (agent_roster)
Plan commit              →      session_state/control (current_flow)
Dialogue update          →      session_state/scoreboard (QUD, entities)
Belief update            →      session_state/beliefs (facts, confidence)
```

### **Layer 4 → Layer 5 (Infrastructure)**

```
Layer 4 calls:                  Layer 5 provides:
──────────────                  ────────────────
SessionState deltas      →      bridge_k0/batch_client (250ms batching)
Actor messages           →      event_bus/event_bus (pub/sub)
Circuit breaker          →      resilience/circuit_breaker
Metrics                  →      observability/metrics
```

### **Layer 4 ↔ Actor Fabric (Internal)**

```
All Layer 4 modules use:
────────────────────────
mailbox/ (MPSC queues)          - Message passing between actors
router/ (admission control)     - 5-check pipeline for all messages
supervisor/ (health monitoring) - Heartbeat + crash detection
```

**Key Constraints:**
1. **Allowed imports:** L4→L5 only (no L4→L1/L2/L3)
2. **SessionState synchronization:** Batched deltas every 250ms to K0
3. **Actor messaging:** All Layer 4 modules are actors (58 total: 4 AI + 54 pure)

---

## 🧪 Layer 4 Testing Strategy (ADR-0004d)

### **Integration Tests**

**Location:** `tests/integration/layer4/`

1. **SessionState Tests:**
   - 6-section serialization (<1ms)
   - Eviction (3-tier priority, <5ms)
   - Locking (current_flow, <0.1ms)
   - Delta batching (250ms interval, 10-50 deltas)
   - Memory management (64KB soft, 128KB hard)

2. **Actor Fabric Tests:**
   - Mailbox MPSC queue (4-tier priority, <1ms enqueue)
   - Router admission (5-check pipeline, <2ms)
   - Supervisor health check (1 Hz heartbeat, <100ms crash detection)
   - Token bucket rate limiting (100 msg/s, 150 burst)

3. **Learning Loop Tests:**
   - Feedback integration (FeedbackSignal ingestion)
   - Self-model update (belief revision, confidence adjustment)
   - Regret minimization (counterfactual reasoning)
   - K0 integration (P20 Self-Model Update pipeline)
   - Performance: <100ms learning cycle

4. **Attention Tests:**
   - Salience computation (recency + frequency + importance)
   - Focus gating (threshold 0.3, top-10 selection)
   - Distraction filtering (context pruning)
   - Performance: <5ms attention computation

5. **End-to-End Tests:**
   - SessionState → Actor Fabric → Learning → Attention full cycle
   - Multi-actor coordination (mailbox + router)
   - Crash recovery (supervisor restart)
   - Performance: <10ms total Layer 4 overhead per turn

---

## 📊 Layer 4 Observability (ADR-0029)

### **Prometheus Metrics**

| Metric | Type | Labels | Description | ADR |
|--------|------|--------|-------------|-----|
| `layer4_session_state_size_bytes` | Histogram | section (beliefs/scoreboard/control/persona/multimodal/meta) | SessionState size per section | ADR-0029 |
| `layer4_session_state_serialize_ms` | Histogram | - | Serialization latency | ADR-0029 |
| `layer4_session_state_eviction_count` | Counter | priority (P1/P2/P3) | Eviction events | ADR-0029 |
| `layer4_mailbox_depth` | Gauge | actor_id, priority (URGENT/REALTIME/INTERACTIVE/BACKGROUND) | Mailbox depth | ADR-0029 |
| `layer4_mailbox_enqueue_ms` | Histogram | priority | Enqueue latency | ADR-0029 |
| `layer4_router_admission_rejections` | Counter | reason (CAPABILITY/RATE_LIMIT/QUOTA/DESTINATION) | Admission rejections | ADR-0029 |
| `layer4_supervisor_crash_rate` | Counter | actor_id | Crash events | ADR-0029 |
| `layer4_supervisor_blacklist_size` | Gauge | - | Blacklisted agent versions | ADR-0029 |
| `layer4_learning_cycle_ms` | Histogram | - | Learning cycle latency | ADR-0029 |
| `layer4_attention_entity_count` | Gauge | - | Entities in focus | ADR-0029 |

### **Grafana Dashboards**

**Layer 4 Overview Dashboard:**
- SessionState size evolution (per section)
- Mailbox health (depth, enqueue/dequeue latency)
- Actor fabric (admission rejections, crash rate, blacklist)
- Learning loop (cycle latency, update rate)
- Attention mechanism (entity count, salience distribution)

---

## 🚀 Layer 4 Implementation Roadmap

### **Phase 1: Core Infrastructure (Weeks 1-3)**
- SessionState model (6 sections)
- Actor fabric (mailbox, router, supervisor)
- FlatBuffers serialization
- Integration tests

### **Phase 2: State Management (Weeks 4-6)**
- SessionState control plane (locking, deltas)
- Memory manager (3-tier eviction)
- K0 integration (batch client)

### **Phase 3: Cognitive Loops (Weeks 7-9)**
- Learning loop (feedback integration)
- Attention mechanism (salience, focus gating)
- Self-model updates

### **Phase 4: Observability & Hardening (Weeks 10-12)**
- Prometheus metrics (10+ metrics)
- Grafana dashboards
- Performance tuning (<1ms SessionState ops)
- Load testing (1000 actors, 1000 msg/s)

---

## 📚 Complete ADR Reference List

### **Primary Layer 4 ADRs**
- ADR-0004 — 52-Module 5-Layer Architecture
- ADR-0017 — SessionState 6-Section Design
- ADR-0002 — Actor Model
- ADR-0018 — Learning Loop
- ADR-0020 — Attention Mechanism

### **SessionState ADRs (Category 1)**
- ADR-0017a — Beliefs Section
- ADR-0017b — Scoreboard Section
- ADR-0017c — Control Section
- ADR-0017d — Persona Section
- ADR-0017e — Multimodal Section
- ADR-0017f — Meta Section
- ADR-0019 — SessionState Serialization (3-tier eviction, 64KB/128KB limits)
- ADR-0007d — SessionState Locking
- ADR-0001f — SessionState Delta Batching

### **Actor Fabric ADRs (Category 2)**
- ADR-0002a — Actor Fabric Mailbox (MPSC queue, 4-tier priority)
- ADR-0002b — Actor Fabric Supervisor (heartbeat, crash detection, blacklist)
- ADR-0002c — Actor Router (location transparency, 5-check pipeline)
- ADR-0028 — WFQ Scheduler (weight-based fairness)
- ADR-0010c — Capability Enforcement (admission control)

### **Learning Loop ADRs (Category 3)**
- ADR-0018a — Feedback Signal
- ADR-0018b — Self-Model Update
- ADR-0018c — Regret Minimization

### **Attention ADRs (Category 4)**
- ADR-0020a — Salience Computation
- ADR-0020b — Focus Gating
- ADR-0020c — Distraction Filtering

### **Cross-Cutting ADRs**
- ADR-0004b — Import Linting
- ADR-0004d — Layer 4 Integration Tests
- ADR-0009 — Circuit Breaker
- ADR-0011 — FlatBuffers Serialization
- ADR-0012b — SessionState Root Schema
- ADR-0013 — Schema Versioning
- ADR-0024 — Performance Budgets
- ADR-0029 — Prometheus Metrics
- ADR-0030 — Trace Sampling

---

**Status:** ✅ **COMPLETE** — All Layer 4 ADRs mapped end-to-end
**Last Updated:** January 2025
**Total ADRs:** 35+ ADRs covering Layer 4 (5 primary + 30 supporting)
**Coverage:** 100% of Layer 4 modules (8/8 modules mapped across 4 categories)
