# Layer 2 (Orchestration) — ADR Family Map

**Complete end-to-end ADR references for K1 Layer 2 modules**

---

## 📋 Overview

**Layer 2 Purpose:** Orchestration & Planning
**Performance Budget:** <100ms P95 (orchestration only, planning <2500ms)
**Modules:** 3 core modules + 4 planner sub-modules (7 total)
**Primary Function:** 4-stage planning pipeline + 3-phase orchestration + protocol validation
**Total Relevant ADRs:** 127 ADRs (updated from ADR_REFERENCE.md)
**Last Updated:** January 2025

---

## � Quick Reference: All 127 ADRs for Layer 2

**ADR Families Relevant to Layer 2:**

1. **K1 Core Architecture** (ADR-0001, 0001f, 0004, 0004b, 0004c, 0004d)
2. **3-Phase Orchestration** (ADR-0006, 0006a, 0006b, 0006c, 0006d, 0006e)
3. **4-Stage Planning** (ADR-0007, 0007b, 0007c, 0007d)
4. **Saga Error Recovery** (ADR-0008, 0008a, 0008b, 0008c, 0008d)
5. **Protocol Validation** (ADR-0003, 0003a, 0003b, 0003c, 0003d)
6. **FlatBuffers** (ADR-0011a, 0011b, 0011c, 0011d, 0012, 0012b)
7. **Schema Versioning** (ADR-0013, 0013a, 0013b, 0013c, 0013d)
8. **API & Protocols** (ADR-0014b, 0014d, 0015, 0015a-e, 0016, 0016a, 0016c, 0016d)
9. **SessionState** (ADR-0019, 0019a)
10. **Performance & QoS** (ADR-0021c, 0022d, 0023c, 0024, 0024b, 0024d)
11. **Scheduling** (ADR-0028, 0028a, 0028b, 0028c)
12. **Observability** (ADR-0029, 0029c, 0029d, 0030)
13. **Security & Privacy** (ADR-0010, 0032, 0035c, 0035d, 0036, 0036a-d, 0037d, 0038, 0038a-d, 0039)
14. **Agent Coordination** (ADR-0045, 0045a-d, 0072, 0073)
15. **K0 Integration** (ADR-0042a, 0042d, 0043c, 0046, 0047, 0048, 0049, 0050)
16. **HITL Protocols** (ADR-0052, 0052a-e)
17. **Turn Management** (ADR-0053, 0053a-c, 0054, 0054a, 0054b)
18. **Voice Pipeline** (ADR-0056, 0056a, 0056d, 0056e)
19. **Learning Loop** (ADR-0059, 0059a-e, 0079)
20. **Knowledge Graph** (ADR-0081, 0081a-d)
21. **Multi-Party Dialogue** (ADR-0082, 0082b)
22. **Memory Consolidation** (ADR-0084, 0084a-d)
23. **Embodied Awareness** (ADR-0085, 0085a, 0085c)

**Total:** 127 ADRs covering all aspects of Layer 2 orchestration and planning.

For detailed component breakdown, see the [Complete ADR Reference List](#-complete-adr-reference-list) section.

---

## �🗺️ Layer 2 Architecture

### Core ADRs

| ADR | Title | Status | Priority | Coverage |
|-----|-------|--------|----------|----------|
| **ADR-0004** | 52-Module 5-Layer Architecture | ✅ Complete | 🔴 CRITICAL | Layer 2 definition, 3-phase orchestration, 4-stage planning |
| **ADR-0006** | 3-Phase Orchestration | ✅ Complete | 🔴 CRITICAL | Contract Net, scoring, DAG execution, Saga rollback |
| **ADR-0007** | 4-Stage Planning Pipeline | ✅ Complete | 🔴 CRITICAL | Sketch→Expand→Validate→Commit, LLM + deterministic |
| **ADR-0008** | Saga Error Recovery | ✅ Complete | 🟡 HIGH | LIFO compensation, idempotency, crash recovery |
| **ADR-0003** | Protocol Validation (MPST) | ✅ Complete | 🟡 HIGH | 6 protocols, FSM validation, timeout enforcement |
| **ADR-0004d** | Layer 2 Integration Tests | ✅ Complete | 🟡 HIGH | 3-phase, planning, protocol validation, <250ms budget |

---

## 📁 Module-by-Module ADR Map

### **Module 1: planner/** (4 sub-modules)

**Purpose:** 4-stage AI-powered planning pipeline
**Location:** `k1/l2_orchestration/planner/`
**Performance:** <2500ms P95 (Sketch 500ms + Expand 1ms + Validate 1ms + Commit 10ms)

#### Primary ADRs

- **ADR-0007** — 4-Stage Planning Pipeline (complete architecture)
- **ADR-0007a** — Stage 1: Sketch (LLM inference, JSON output)
- **ADR-0007b** — Stage 2: Expand (tool registry lookup, metadata enrichment)
- **ADR-0007c** — Stage 3: Validate (2-tier validation: rules + arbiter)
- **ADR-0007d** — Stage 4: Commit (K0 WAL write, SessionState locking)

#### Planner Related ADRs

- **ADR-0001b** — Model Hub integration (Planner AI agent)
- **ADR-0002** — Actor Model (Planner is AI agent, uses mailbox)
- **ADR-0005e** — Agent personalities (Planner 5000ms budget)
- **ADR-0011** — FlatBuffers serialization (FlowDef binary format)
- **ADR-0012** — FlatBuffers schemas (PlanSketch, PlanNode, ValidationResult)
- **ADR-0024** — Performance budgets (planning <2500ms P95)
- **ADR-0027** — Model placement (local-first for Planner)
- **ADR-0029** — Prometheus metrics (planning latency, validation failures)
- **ADR-0031** — Cost tracking (LLM token usage)

#### Sub-Module 1.1: planner/sketch/

**Purpose:** LLM-powered plan generation (Stage 1)
**Performance:** 150-500ms P95

**Key Responsibilities:**

1. **LLM Inference:** Generate structured JSON plan from user intent
2. **Prompt Engineering:** System prompt + few-shot examples (5-10)
3. **JSON Schema Enforcement:** OpenAI JSON mode, Gemini JSON mode, Claude prefill
4. **Temperature Tuning:** 0.3 primary (consistency), 0.0 fallback (retry)
5. **Token Budget:** 800 max tokens response, 3650 total tokens (4K window)

**Performance Metrics:**

- LLM inference: 150-500ms P95
- JSON parse success: >99%
- Plan quality: >85% valid plans (pass validation)

**Key ADRs:**

- ADR-0007a (Sketch stage specification)
- ADR-0001b (Model Hub integration)
- ADR-0027 (Model placement: local-first SLM)

---

#### Sub-Module 1.2: planner/expand/

**Purpose:** Enrich plan with metadata (Stage 2)
**Performance:** <1ms P95

**Key Responsibilities:**

1. **Tool Registry Lookup:** O(1) hash table lookup per step
2. **Prompt Matching:** Keyword/category matching (>90% match success)
3. **Metadata Enrichment:** Schema filling (schema_in, schema_out, latency_hint, cost_hint, band_required)
4. **ExpandedPlan Output:** Enriched plan with complete metadata

**Performance Metrics:**

- Tool lookup: <0.1ms per step (O(1) hash table)
- Prompt matching: <0.5ms per step
- Total expand: <1ms P95 (10 steps)

**Key ADRs:**

- ADR-0007b (Expand stage specification)
- ADR-0033 (Tool registry integration)

---

#### Sub-Module 1.3: planner/validate/

**Purpose:** 2-tier validation (Stage 3)
**Performance:** <1ms P95 (Tier 1) + 50-100ms (Tier 2 arbiter, <15% invocation)

**Key Responsibilities:**

**Tier 1: Rule-Based Validation (<1ms):**

1. **Structural Validation:** Step count ≤10, unique step_ids, sequential IDs (<0.1ms)
2. **Dependency Validation:** Kahn's algorithm DAG cycle detection, O(V+E) (<0.2ms)
3. **Capability Validation:** Set intersection, missing capabilities check (<0.05ms)
4. **Budget Validation:** Latency budget, cost budget checks (<0.05ms)
5. **Band Validation:** Privacy band hierarchy (GREEN<AMBER<RED), session band comparison (<0.05ms)
6. **Schema Validation:** JSON Schema validation, step parameters vs tool schema_in (<0.5ms)

**Tier 2: LLM Arbiter (50-100ms, invoked <15% of plans):**

- **Invocation Rules:** AMBER/RED band plans, child space, age<18
- **Safety Check:** LLM arbiter reviews plan for safety/appropriateness
- **Model:** gpt-4o-mini (fast, cheap)
- **Reject Rate:** <5% of reviewed plans

**Performance Metrics:**

- Tier 1 validation: <1ms P95 (6 checks)
- Tier 2 arbiter: 50-100ms P95 (when invoked)
- Validation pass rate: >95% (Tier 1), >95% (Tier 2)
- Total validation: <1ms P95 (weighted, 85% Tier 1 only)

**Key ADRs:**

- ADR-0007c (Validate stage specification)
- ADR-0010 (Capability validation)
- ADR-0024 (Privacy bands)

---

#### Sub-Module 1.4: planner/commit/

**Purpose:** Persist validated plan to K0 (Stage 4)
**Performance:** <10ms P95

**Key Responsibilities:**

1. **FlowDef Serialization:** FlatBuffers binary format (<1ms)
2. **K0 WAL Write:** HTTP POST /k0/wal/append, PLAN_COMMITTED topic (<5ms)
3. **SessionState Locking:** current_flow field, flow_id, prevent concurrent plans (<0.1ms)
4. **STATE_DELTA Emission:** K0 sync, field_path (control.current_flow), old/new value (<2ms)
5. **Idempotency:** Idempotency key generation, hash(session+plan+time_bucket), 60s window

**Performance Metrics:**

- FlatBuffers serialization: <1ms
- K0 WAL write: <5ms P95
- SessionState locking: <0.1ms
- STATE_DELTA emission: <2ms
- Total commit: <10ms P95

**Key ADRs:**

- ADR-0007d (Commit stage specification)
- ADR-0011 (FlatBuffers serialization)
- ADR-0019 (SessionState serialization)
- ADR-0022 (K0 Bridge batching)

---

### **Module 2: orchestrator/**

**Purpose:** 3-phase multi-agent coordination
**Location:** `k1/l2_orchestration/orchestrator/`
**Performance:** <250ms P95 (Negotiation 50ms + Selection 100ms + Execution 100ms)

#### Orchestrator Primary ADRs

- **ADR-0006** — 3-Phase Orchestration (complete architecture)
- **ADR-0006a** — Phase 1: Negotiation (Contract Net Protocol)
- **ADR-0006b** — Phase 2: Selection (6-factor MADM scoring)
- **ADR-0006c** — Phase 3: Execution (DAG parallel execution)
- **ADR-0006d** — Saga Pattern (LIFO compensation, rollback)
- **ADR-0006e** — Multi-Agent Coordination (wave independence analysis)

#### Orchestrator Related ADRs

- **ADR-0002** — Actor Model (Orchestrator is pure actor)
- **ADR-0005** — Agent lifecycle (hire/fire, WARMING→ACTIVE)
- **ADR-0008** — Saga error recovery (detailed compensation logic)
- **ADR-0024** — Performance budgets (orchestration <250ms P95)
- **ADR-0028** — WFQ scheduler (INTERACTIVE priority)
- **ADR-0029** — Prometheus metrics (orchestration latency, success rate)

#### Phase 1: Negotiation (Contract Net Protocol)

**Purpose:** Agent bidding and proposal collection
**Performance:** <50ms P95

**Key Responsibilities:**

1. **TaskAnnouncement Broadcast:** Broadcast to all ACTIVE agents via mailbox
2. **Proposal Collection:** MPSC queue, 50ms timeout, non-blocking receive
3. **Agent Bidding:** Agents evaluate capability/confidence/cost/latency
4. **Confidence Scoring:** 4 factors (capability 40%, success rate 30%, load 20%, context 10%)
5. **Fallback Strategy:** 4-tier (hire→simplify→wait-retry→degrade)

**Performance Metrics:**

- Broadcast latency: <5ms (10 agents)
- Proposal collection: <50ms timeout
- Agent response time: <30ms P95 (per agent)
- No-proposal handling: <10ms fallback decision

**Key ADRs:**

- ADR-0006a (Negotiation specification)
- ADR-0005 (Agent lifecycle: hire on-demand)

---

#### Phase 2: Selection (MADM Scoring)

**Purpose:** Multi-Attribute Decision Making (6-factor weighted scoring)
**Performance:** <5ms P95

**Key Responsibilities:**

1. **Scoring Engine:** 6-factor weighted sum
   - Confidence (weight 10.0): Agent self-reported confidence
   - Latency (weight 8.0): Expected latency (normalized 0-1)
   - Cost (weight -5.0): Estimated cost (negative = cheaper better)
   - Parallelism bonus (weight 3.0): Can run in parallel with other steps
   - Track record (weight 2.0): Historical success rate
   - Busy penalty (weight -4.0): Current agent load

2. **Normalization:** Latency/cost normalization (0-1 scale), exponential decay
3. **Weighted Scoring:** Score = Σ(factor × weight), <5ms P95 computation
4. **Tie-Breaking:** 4 strategies (resident 60%, fast 20%, cheap 10%, random 10%)
5. **Winner Selection:** Highest score wins, tie detection (epsilon 0.01), TaskAssignment message

**Performance Metrics:**

- Scoring computation: <5ms P95 (10 proposals)
- Tie-breaking: <0.5ms
- TaskAssignment message: <1ms

**Key ADRs:**

- ADR-0006b (Selection specification)
- ADR-0029 (Metrics: agent selection patterns)

---

#### Phase 3: Execution (DAG Parallel Execution)

**Purpose:** Parallel DAG execution with dependency resolution
**Performance:** Varies (depends on plan complexity, 100ms-5000ms)

**Key Responsibilities:**

1. **DAG Builder:** Nodes (steps), edges (dependencies), in-degree, out-edges, acyclic validation
2. **Wave Computation:** Topological sort (Kahn's algorithm), wave grouping, parallel independence
3. **Dependency Resolution:** Variable substitution ({step_N.field}), step result lookup
4. **Parallel Execution:** asyncio.gather, barrier synchronization, semaphore (max 3 concurrent)
5. **Straggler Detection:** Identify slow steps, timeout enforcement

**Performance Metrics:**

- DAG building: <5ms (10 steps)
- Wave computation: <2ms (topological sort)
- Execution latency: Varies (plan-dependent)
- Parallelism speedup: 2-3× (compared to sequential)

**Key ADRs:**

- ADR-0006c (Execution specification)
- ADR-0008 (Saga compensation on failure)

---

#### Saga Pattern (Compensation & Rollback)

**Purpose:** Distributed transaction management with compensation
**Performance:** <100ms per compensation

**Key Responsibilities:**

1. **Saga Coordinator:** execute_saga, compensation triggering, LIFO unwinding, audit trail
2. **Compensation Tracking:** Completed steps stack (LIFO), compensation actions, parameter resolution
3. **Compensation Execution:** CompensationExecution message, timeout enforcement (3s), retry logic (1× retry)
4. **Multi-Agent Compensation:** Agent coordination, concurrent compensation, best-effort
5. **Recovery Strategies:**
   - **Forward Recovery:** Retry with exponential backoff (max 5 retries)
   - **Backward Recovery:** LIFO compensation (reverse execution order)
   - **Hybrid Recovery:** Retry forward first, fallback to rollback (~18s worst-case)

**Performance Metrics:**

- Compensation execution: <100ms per step (3s timeout)
- LIFO unwinding: <5s total (5 steps × 1s avg)
- Failure classification: <1ms (transient vs permanent)
- Recovery success rate: >92%

**Key ADRs:**

- ADR-0006d (Saga pattern specification)
- ADR-0008 (Detailed Saga error recovery)
- ADR-0008a (Compensation design patterns)
- ADR-0008b (Recovery strategies)
- ADR-0008c (Distributed state management)
- ADR-0008d (Timeout management, deadlock handling)

---

### **Module 3: protocol_monitor/**

**Purpose:** Multiparty Session Type (MPST) protocol validation
**Location:** `k1/l2_orchestration/protocol_monitor/`
**Performance:** <2ms P95 (validation), <100ms (protocol compilation)

#### Protocol Monitor Primary ADRs

- **ADR-0003** — Protocol Validation (MPST overview)
- **ADR-0003a** — PDL Language (YAML-based protocol definition)
- **ADR-0003b** — 6 Protocol Definitions (hire, task, clarification, barge-in, tool_call, saga)
- **ADR-0003c** — Protocol Monitor (runtime validation)
- **ADR-0003d** — Security (role verification, 2-phase validation)

#### Protocol Monitor Related ADRs

- **ADR-0002** — Actor Model (Protocol Monitor is pure actor)
- **ADR-0010** — Capability security (role verification integration)
- **ADR-0011** — FlatBuffers serialization (protocol FSM binary format)
- **ADR-0024** — Performance budgets (validation <2ms P95)
- **ADR-0029** — Prometheus metrics (protocol violations, timeout rate)

#### Key Responsibilities

**1. Protocol Compilation (PDL → FSM):**

- **PDL Parser:** YAML parsing, syntax/semantic validation, FSM generation
- **Compiler Pipeline:** YAML→FSM, deadlock detection (Tarjan's algorithm), FlatBuffers serialization
- **Performance:** <100ms compilation per protocol
- **6 Protocols:** hire.pdl.yml, task.pdl.yml, clarification.pdl.yml, barge_in.pdl.yml, tool_call.pdl.yml, saga.pdl.yml

**2. Runtime Validation:**

- **FSM Registry:** Load 6 protocols from FlatBuffers, <100ms per protocol, reachability check
- **Session FSM Tracker:** Per-session state, RwLock concurrency, hash table, cleanup
- **Protocol Validator:** Receive-side validation, <5ms P95 mailbox budget, <2ms validation
- **Violation Handler:** BLOCK, WARN, DLQ, REPAIR, FALLBACK, ABORT actions
- **Timeout Enforcer:** Background task, 100ms poll, auto-transitions, progress guarantees
- **Composition Manager:** Pause/resume/interrupt/abort, protocol stack, nested protocols

**3. Security (2-Phase Validation):**

- **Phase 1: Role Verification (<1ms):** HMAC-SHA256 verification, lease lookup, capability check
- **Phase 2: Protocol Validation (<2ms):** State transition validation, message schema check
- **Total:** <3ms P95 (2-phase validation)

**Performance Metrics:**

- Protocol compilation: <100ms per protocol (one-time startup cost)
- FSM loading: <100ms per protocol (6 protocols = 600ms startup)
- Runtime validation: <2ms P95 per message
- Role verification: <1ms P95 (HMAC check)
- Violation detection: <1ms (state mismatch)
- Timeout detection: <100ms (background poll)

**6 Protocol Specifications:**

1. **Agent Hire Protocol:** 6 states, 8 transitions, Contract Net, 500ms negotiation, 100ms selection
2. **Task Execution Protocol:** 5 states, 10 transitions, AI planning, 5000ms LLM timeout, 10000ms execution
3. **Clarification Protocol:** 4 states, 6 transitions, nested protocol, 30000ms user timeout, human-in-loop
4. **Barge-In Protocol:** 3 states, 5 transitions, interrupt handling, 200ms decision, VAD detection
5. **Tool Call Protocol:** 4 states, 7 transitions, MCP/WASM sandbox, 3000ms execution timeout
6. **Saga Rollback Protocol:** 5 states, 9 transitions, compensation, 5000ms compensate, 2000ms rollback

**Key ADRs:**

- ADR-0003a (PDL language specification)
- ADR-0003b (Protocol definitions)
- ADR-0003c (Protocol monitor implementation)
- ADR-0003d (Security: role verification)

---

## 🔗 Cross-Cutting ADRs (Affect All Layer 2 Modules)

### **Architecture & Design**

- **ADR-0002** — Actor Model (Orchestrator/Protocol Monitor are pure actors, Planner is AI agent)
- **ADR-0004** — 52-Module 5-Layer Architecture (Layer 2 definition)
- **ADR-0004b** — Import Linting (L2→L1/L3/L4/L5, allowed to import all layers)
- **ADR-0004d** — Layer 2 Integration Tests (end-to-end test suite)

### **Serialization & Data**

- **ADR-0011** — FlatBuffers serialization (FlowDef, protocol FSM)
- **ADR-0012** — 76 FlatBuffers schemas (PlanSketch, TaskAnnouncement, Proposal, Selection, FSM)
- **ADR-0013** — Schema versioning (SemVer, backward compatibility)
- **ADR-0019** — SessionState serialization (Layer 2 reads/writes SessionState)

### **Observability**

- **ADR-0029** — Prometheus metrics (orchestration, planning, protocol violations)
- **ADR-0030** — Trace sampling (cognitive_trace_id propagation through orchestration)

### **Performance & Reliability**

- **ADR-0024** — Performance budgets (Layer 2: <100ms P95 total, planning <2500ms)
- **ADR-0028** — WFQ scheduler (Layer 2 uses INTERACTIVE/BACKGROUND queues)
- **ADR-0009** — Circuit breaker (Layer 2 integrates circuit breakers for agent hire/LLM)

### **Security & Privacy**

- **ADR-0010** — Capability security (Layer 2 validates agent capabilities, role verification)
- **ADR-0032** — Egress control (Layer 2 respects privacy bands for planning)
- **ADR-0035** — PII detection (Layer 2 redacts PII from plans before K0)

### **Cost & Resource Management**

- **ADR-0027** — Model placement cascade (Layer 2 Planner uses local-first LLM)
- **ADR-0031** — Cost tracking (Layer 2 tracks LLM planning costs)

---

## 🎯 Layer 2 Performance Budget Breakdown

### **Total Layer 2 Budget: <100ms P95 (orchestration only, planning excluded)**

| Component | Budget | Typical | P95 | ADR |
|-----------|--------|---------|-----|-----|
| planner/sketch | 500ms | 300ms | 500ms | ADR-0007a |
| planner/expand | 1ms | 0.5ms | 1ms | ADR-0007b |
| planner/validate | 1ms | 0.8ms | 1ms | ADR-0007c |
| planner/commit | 10ms | 5ms | 10ms | ADR-0007d |
| **Planning Total** | **2500ms** | **1500ms** | **2500ms** | **ADR-0007** |
| orchestrator/negotiation | 50ms | 30ms | 50ms | ADR-0006a |
| orchestrator/selection | 5ms | 3ms | 5ms | ADR-0006b |
| orchestrator/execution | varies | varies | varies | ADR-0006c |
| **Orchestration Total** | **<250ms** | **150ms** | **250ms** | **ADR-0006** |
| protocol_monitor | 2ms | 1ms | 2ms | ADR-0003c |

**Note:** Planning (2500ms) is **ONE-TIME** per conversation turn. Orchestration (250ms) is **PER STEP** in the plan.

---

## 🔄 Layer 2 Integration Points

### **Layer 2 ← Layer 1 (Event Bus Subscription via Layer 5)**

**Pattern:** Layer 1 → Layer 5 (Event Bus) → Layer 2 (pub/sub, async, <10ms P95)

```
Layer 1 publishes:                    Layer 5 Event Bus routes:           Layer 2 subscribes:
─────────────────                     ─────────────────────────           ──────────────────
IntentDetected event            →     EventTopic.INTENT_DETECTED    →     orchestrator (trigger 3-phase)
UserInput event                 →     EventTopic.USER_INPUT         →     session context update
VoiceCommand event              →     EventTopic.VOICE_COMMAND      →     command handler
BargeIn event                   →     EventTopic.BARGE_IN           →     barge-in protocol (MPST)
```

**Performance:** <10ms P95 end-to-end (L1 publish <2ms + L5 delivery <5ms)
**Reference:** ADR-0004a (Layer 1-2 Event Bus Communication)

### **Layer 2 → Layer 3 (Agent Hire & Tool Execution)**

**Pattern:** Direct synchronous calls (L2→L3 imports allowed per ADR-0004b)

```
Layer 2 sends:                        Layer 3 receives:
──────────────                        ────────────────
AgentHireRequest                →     agents/hire_fire (spawn agent, <600ms P95)
TaskAssignment (Actor message)  →     agent mailbox (MPSC queue, execute step)
ToolCallRequest                 →     tools/runner (MCP/WASM, <3000ms timeout)
```

**Communication:** Actor Model mailbox (MPSC queue), MPST protocol validation
**Reference:** ADR-0002 (Actor Model), ADR-0003 (MPST Protocols)

### **Layer 2 → Layer 4 (SessionState & Runtime)**

**Pattern:** Direct writes to SessionState control section

```
Layer 2 writes:                       Layer 4 manages:
───────────────                       ────────────────
FlowDef (current plan)          →     session_state/control.current_flow
AgentLease (capabilities)       →     session_state/control.agent_leases
Saga checkpoints                →     session_state/control.saga_state
Planning metadata               →     session_state/control.planning_state
```

**Serialization:** FlatBuffers (<1ms serialize, zero-copy)
**Reference:** ADR-0019 (SessionState Serialization), ADR-0011 (FlatBuffers)

### **Layer 2 → Layer 5 (K0 Bridge & Infrastructure)**

**Pattern:** Async batched writes to K0 WAL (250ms interval)

```
Layer 2 emits:                        Layer 5 provides:
──────────────                        ────────────────
PLAN_COMMITTED event            →     k0_bridge (WAL write, audit trail)
STATE_DELTA batch               →     k0_bridge (SessionState sync to K0)
SAGA_COMPENSATION event         →     k0_bridge (compensation audit log)
```

**Batching:** 250ms interval or 100 events (whichever first)
**Reference:** ADR-0022d (K0 Bridge Batching), ADR-0038 (Audit Trail)

---

### **Integration Constraints & Design Patterns**

1. **Allowed imports:** L2→L1/L3/L4/L5 (most permissive layer per ADR-0004)
2. **Event-driven L1→L2:** No direct imports from L1, pub/sub via Layer 5 EventBus (ADR-0004a)
3. **Direct calls L2→L3:** Synchronous agent hire, task assignment via Actor mailboxes (ADR-0002)
4. **Async K0 writes:** Batched STATE_DELTA (250ms interval) to prevent WAL saturation (ADR-0022d)
5. **MPST validation:** All L2→L3 actor messages validated by Protocol Monitor (ADR-0003)
6. **Zero-copy optimization:** FlatBuffers serialization for SessionState writes (ADR-0011)

**Cross-Layer Latency Budget:**

- L1→L5→L2 (event flow): <10ms P95
- L2→L3 (agent hire): <600ms P95
- L2→L4 (state write): <1ms P95
- L2→L5 (K0 batch): <50ms P95 (async, non-blocking)

---

## 🧪 Layer 2 Testing Strategy (ADR-0004d)

### **Integration Tests**

**Location:** `tests/integration/layer2/`

1. **3-Phase Orchestration Tests:**
   - Phase 1 negotiation: TaskAnnouncement → proposals
   - Phase 2 selection: MADM scoring, winner selection
   - Phase 3 execution: DAG parallel execution, barrier sync
   - Saga compensation: LIFO rollback, idempotency
   - Performance: <250ms P95

2. **4-Stage Planning Tests:**
   - Stage 1 sketch: LLM inference, JSON parsing
   - Stage 2 expand: Tool registry lookup, metadata enrichment
   - Stage 3 validate: 6 rule checks, arbiter invocation (<15%)
   - Stage 4 commit: K0 WAL write, SessionState locking
   - Performance: <2500ms P95

3. **Protocol Validation Tests:**
   - 6 protocol FSM loading
   - Runtime validation: state transitions, message schema
   - Timeout enforcement: auto-transitions, progress guarantees
   - Security: role verification, 2-phase validation
   - Performance: <2ms P95 validation

4. **Multi-Agent Coordination Tests:**
   - Multi-agent negotiation (10+ agents)
   - Parallel wave execution (3 concurrent steps)
   - Agent synchronization (barrier, rendezvous)
   - Load balancing (agent busy penalty)

5. **End-to-End Tests:**
   - Intent → planning → orchestration → execution → response
   - Error handling: agent crash, tool timeout, LLM failure
   - Saga compensation: rollback on failure
   - Performance: <3000ms P95 (full turn)

---

## 📊 Layer 2 Observability (ADR-0029)

### **Prometheus Metrics**

| Metric | Type | Labels | Description | ADR |
|--------|------|--------|-------------|-----|
| `layer2_planning_latency_ms` | Histogram | stage (sketch/expand/validate/commit) | Planning pipeline latency | ADR-0029 |
| `layer2_planning_success_rate` | Gauge | - | % of plans that pass validation | ADR-0029 |
| `layer2_validation_failures_total` | Counter | failure_type (structural/dependency/capability/budget/band/schema) | Validation failures | ADR-0029 |
| `layer2_orchestration_latency_ms` | Histogram | phase (negotiation/selection/execution) | Orchestration latency | ADR-0029 |
| `layer2_agent_proposals_total` | Counter | intent_type | Agent proposals per negotiation | ADR-0029 |
| `layer2_agent_selection_score` | Histogram | agent_id | Agent selection scores | ADR-0029 |
| `layer2_dag_parallelism` | Histogram | - | Parallel steps per wave | ADR-0029 |
| `layer2_saga_compensations_total` | Counter | status (success/failure) | Saga compensation executions | ADR-0029 |
| `layer2_protocol_violations_total` | Counter | protocol (hire/task/clarification/barge_in/tool_call/saga), violation_type | Protocol violations | ADR-0029 |
| `layer2_protocol_timeouts_total` | Counter | protocol | Protocol timeout events | ADR-0029 |

### **Grafana Dashboards**

**Layer 2 Overview Dashboard:**

- Planning pipeline waterfall (4 stages)
- Orchestration latency (3 phases)
- Agent selection distribution (winner breakdown)
- Protocol violation rate (per protocol)
- Saga compensation success rate
- Performance budget compliance (P50/P95/P99)

---

## 🚀 Implementation Roadmap (Production-Grade Plan)

**Planning Principles Applied:**

- ✅ **Iterative Delivery:** Ship working features every 2 weeks (ADR-0007, Agile methodology)
- ✅ **Risk-First:** Tackle highest-risk items early (unknown unknowns, LLM integration)
- ✅ **Continuous Validation:** Performance budgets + integration tests at each phase
- ✅ **Parallel Workstreams:** Infrastructure + features can proceed concurrently
- ✅ **Incremental Integration:** Validate layer boundaries early, prevent big-bang integration
- ✅ **Observability-First:** Metrics + tracing from day 1 (ADR-0029, ADR-0030)

**Critical Path:** Phase 1 → Phase 2 → Phase 5 (8 weeks minimum viable orchestration)
**Parallel Tracks:** Phase 3 (Saga) + Phase 4 (Protocol) can run alongside Phase 2

---

### **Phase 0: Foundation & Risk Mitigation (Week -2 to 0)**

**Goal:** De-risk critical dependencies before main implementation

**Critical Dependencies:**

1. ✅ **ADR Review & Alignment**
   - Read ADR-0004 (Layer 2 architecture), ADR-0006 (orchestration), ADR-0007 (planning)
   - Verify all 127 ADRs understood by team
   - Create ADR decision log (track architectural decisions)
   - **Deliverable:** ADR alignment document + team sign-off
   - **Risk Mitigation:** Prevents mid-flight architecture changes

2. ✅ **FlatBuffers Schema Validation** (ADR-0011, ADR-0012)
   - Validate 76 schemas compile with flatc v23.5.26
   - Generate Python/C++/Rust bindings (<100ms compilation)
   - Test SessionState serialization (64KB <1ms serialize/deserialize)
   - **Deliverable:** Schema validation report + generated bindings
   - **Risk Mitigation:** Prevents serialization bottlenecks in production

3. ✅ **K0 Integration Proof-of-Concept** (ADR-0022d, ADR-0023c)
   - Test K0 WAL write (<5ms P95)
   - Test K0 Bridge batching (250ms interval, 100 events)
   - Test SessionState locking (optimistic concurrency)
   - **Deliverable:** K0 integration test suite (Ward framework)
   - **Risk Mitigation:** Validates K0 performance assumptions

4. ✅ **LLM Model Selection & Benchmarking** (ADR-0027, ADR-0031)
   - Benchmark local SLM candidates (Llama 3.1 8B, Mistral 7B, Phi-3.5)
   - Measure planning latency (target: <500ms P95 for Sketch stage)
   - Measure JSON parsing success rate (target: >99%)
   - Test prompt engineering (5-10 few-shot examples)
   - **Deliverable:** Model selection report + benchmark results
   - **Risk Mitigation:** Prevents late-stage model swaps

5. ✅ **Performance Baseline Establishment** (ADR-0024)
   - Define component-level budgets (orchestration <250ms, planning <2500ms)
   - Set up Prometheus + Grafana dashboards
   - Create performance regression test suite
   - **Deliverable:** Performance budget specification + monitoring setup
   - **Risk Mitigation:** Enables continuous performance validation

**Exit Criteria:**

- [ ] All ADRs reviewed and aligned
- [ ] FlatBuffers schemas validated and bindings generated
- [ ] K0 integration POC passing (<5ms WAL writes)
- [ ] LLM model selected with benchmark data
- [ ] Prometheus/Grafana dashboards operational

---

### **Phase 1: Planning Pipeline MVP (Week 1-3, Critical Path)**

**Goal:** Ship minimal viable planning pipeline with real LLM integration

**Workstream 1A: Core Planning Pipeline (Week 1-2)**

1. **Sketch Stage (ADR-0007a)** — Week 1
   - Implement LLM inference pipeline (local SLM)
   - Add JSON schema enforcement (OpenAI JSON mode)
   - Add prompt engineering (5-10 few-shot examples)
   - Add retry logic (temperature 0.3 → 0.0 fallback)
   - **Performance Target:** 150-500ms P95
   - **Deliverable:** `planner/sketch.py` + WARD tests
   - **Risk:** LLM latency variability → mitigation: local-first model (ADR-0027)

2. **Expand Stage (ADR-0007b)** — Week 1
   - Implement tool registry (hash table O(1) lookup)
   - Add metadata enrichment (schema_in, schema_out, latency_hint)
   - Add prompt matching (keyword/category, >90% success)
   - **Performance Target:** <1ms P95
   - **Deliverable:** `planner/expand.py` + WARD tests
   - **Risk:** Tool registry size → mitigation: lazy loading

3. **Validate Stage (ADR-0007c)** — Week 2
   - Implement Tier 1 rule-based validation (6 checks)
     - Structural (step count ≤10, unique IDs)
     - Dependency (Kahn's algorithm, DAG cycle detection)
     - Capability (set intersection)
     - Budget (latency/cost checks)
     - Band (privacy hierarchy)
     - Schema (JSON Schema validation)
   - Implement Tier 2 LLM arbiter (<15% invocation rate)
   - **Performance Target:** <1ms P95 (Tier 1), 50-100ms (Tier 2)
   - **Deliverable:** `planner/validate.py` + WARD tests
   - **Risk:** Arbiter latency → mitigation: gpt-4o-mini (fast, cheap)

4. **Commit Stage (ADR-0007d)** — Week 2
   - Implement FlatBuffers serialization (FlowDef)
   - Implement K0 WAL write (HTTP POST /k0/wal/append)
   - Implement SessionState locking (current_flow field)
   - Implement STATE_DELTA emission
   - Add idempotency (hash-based deduplication, 60s window)
   - **Performance Target:** <10ms P95
   - **Deliverable:** `planner/commit.py` + WARD tests
   - **Risk:** K0 WAL contention → mitigation: batching (ADR-0022d)

**Workstream 1B: Observability & Metrics (Week 2-3, Parallel)**

5. **Planning Metrics (ADR-0029)** — Week 2-3
   - Add Prometheus metrics (planning latency, success rate, validation failures)
   - Add OpenTelemetry tracing (cognitive_trace_id propagation)
   - Create Grafana dashboard (4-stage waterfall)
   - **Deliverable:** Metrics + traces + dashboard
   - **Risk:** Overhead → mitigation: sampling (ADR-0030)

**Workstream 1C: Integration Tests (Week 3)**

6. **End-to-End Planning Tests** — Week 3
   - Test full 4-stage pipeline (Sketch→Expand→Validate→Commit)
   - Test error handling (LLM timeout, validation failure, K0 write failure)
   - Test performance budgets (<2500ms P95)
   - **Deliverable:** `tests/integration/layer2/test_planning_pipeline.py`
   - **Exit Criteria:** >95% plan validation success, <2500ms P95

**Phase 1 Deliverables:**

- ✅ Working planning pipeline (4 stages)
- ✅ WARD integration tests (>95% success rate)
- ✅ Performance validated (<2500ms P95)
- ✅ Metrics + tracing operational

**Phase 1 Risks & Mitigation:**

- **Risk:** LLM latency spikes → **Mitigation:** Local SLM + timeout + fallback (ADR-0027)
- **Risk:** K0 WAL saturation → **Mitigation:** Batching (ADR-0022d)
- **Risk:** Validation false positives → **Mitigation:** Tunable thresholds + escape hatch

---

### **Phase 2: Orchestration Core (Week 4-6, Critical Path)**

**Goal:** Ship 3-phase orchestration with real agent coordination

**Workstream 2A: Negotiation Phase (Week 4)**

1. **Contract Net Protocol (ADR-0006a)** — Week 4
   - Implement TaskAnnouncement broadcast (mailbox-based)
   - Implement proposal collection (MPSC queue, 50ms timeout)
   - Implement agent bidding (4-factor confidence scoring)
   - Add fallback strategies (hire→simplify→wait-retry→degrade)
   - **Performance Target:** <50ms P95
   - **Deliverable:** `orchestrator/negotiation.py` + WARD tests
   - **Risk:** Agent unresponsiveness → mitigation: 50ms timeout + fallback

**Workstream 2B: Selection Phase (Week 4)**

2. **MADM Scoring (ADR-0006b)** — Week 4
   - Implement 6-factor weighted scoring engine
     - Confidence (10.0), Latency (8.0), Cost (-5.0)
     - Parallelism (3.0), Track record (2.0), Busy penalty (-4.0)
   - Add normalization (latency/cost → 0-1 scale)
   - Add tie-breaking (4 strategies: resident/fast/cheap/random)
   - **Performance Target:** <5ms P95
   - **Deliverable:** `orchestrator/selection.py` + WARD tests
   - **Risk:** Bias in scoring → mitigation: tunable weights (ADR-0049)

**Workstream 2C: Execution Phase (Week 5)**

3. **DAG Parallel Execution (ADR-0006c)** — Week 5
   - Implement DAG builder (nodes, edges, Kahn's algorithm)
   - Implement wave computation (topological sort, parallel grouping)
   - Implement dependency resolution (variable substitution)
   - Implement parallel executor (asyncio.gather, semaphore limit 3)
   - Add straggler detection (timeout enforcement)
   - **Performance Target:** 2-3× speedup vs sequential
   - **Deliverable:** `orchestrator/execution.py` + WARD tests
   - **Risk:** Deadlock in DAG → mitigation: acyclic validation (ADR-0007c)

**Workstream 2D: Layer 3 Integration (Week 5-6, Parallel)**

4. **Agent Hire Integration (ADR-0005, ADR-0072)** — Week 5
   - Integrate with Layer 3 AgentFactory
   - Implement AgentHireRequest message
   - Test agent spawning (<600ms P95)
   - **Deliverable:** `tests/integration/layer2/test_l2_l3_agent_hire.py`
   - **Risk:** Agent spawn latency → mitigation: pre-warming (ADR-0073)

5. **Tool Execution Integration** — Week 6
   - Integrate with Layer 3 ToolRunner (MCP/WASM)
   - Implement ToolCallRequest message
   - Test tool execution (<3000ms timeout)
   - **Deliverable:** `tests/integration/layer2/test_l2_l3_tool_execution.py`
   - **Risk:** Tool timeout → mitigation: cancellation support (ADR-0053c)

**Workstream 2E: Observability (Week 6, Parallel)**

6. **Orchestration Metrics (ADR-0029)** — Week 6
   - Add Prometheus metrics (orchestration latency, agent proposals, selection scores)
   - Add tracing (3-phase spans)
   - Create Grafana dashboard (3-phase waterfall)
   - **Deliverable:** Metrics + dashboard

**Phase 2 Deliverables:**

- ✅ Working 3-phase orchestration (Negotiation→Selection→Execution)
- ✅ Layer 3 integration (agent hire + tool execution)
- ✅ WARD integration tests (>92% success rate)
- ✅ Performance validated (<250ms P95 orchestration)
- ✅ Metrics + tracing operational

**Phase 2 Risks & Mitigation:**

- **Risk:** Agent coordination failures → **Mitigation:** Fallback strategies (ADR-0006a)
- **Risk:** DAG execution deadlock → **Mitigation:** Acyclic validation + timeouts
- **Risk:** Layer 3 latency → **Mitigation:** Pre-warming + circuit breakers (ADR-0009)

---

### **Phase 3: Saga Pattern (Week 7-8, Parallel Track)**

**Goal:** Add distributed transaction management with compensation

**Note:** Can run in parallel with Phase 2 (Week 5-6) if resources available

1. **Saga Coordinator (ADR-0008)** — Week 7
   - Implement execute_saga (LIFO compensation tracking)
   - Implement compensation triggering (on failure)
   - Add audit trail (K0 WAL integration)
   - **Performance Target:** <100ms per compensation
   - **Deliverable:** `orchestrator/saga.py` + WARD tests

2. **Compensation Registry (ADR-0008a)** — Week 7
   - Design 50+ tool compensation handlers
   - Implement compensation action mapping
   - Add parameter resolution (reverse transformations)
   - **Deliverable:** `orchestrator/compensation_registry.py`

3. **Recovery Strategies (ADR-0008b)** — Week 8
   - Implement forward recovery (retry with backoff, max 5 retries)
   - Implement backward recovery (LIFO unwinding)
   - Implement hybrid recovery (retry → fallback rollback)
   - Add failure classifier (transient/permanent/ambiguous)
   - **Performance Target:** <5s total recovery (5 steps)
   - **Deliverable:** `orchestrator/recovery.py` + WARD tests

4. **Distributed State Management (ADR-0008c)** — Week 8
   - Implement crash recovery (WAL replay)
   - Add idempotency checks (deduplication)
   - Test multi-agent compensation
   - **Deliverable:** `tests/integration/layer2/test_saga_recovery.py`

5. **Saga Metrics (ADR-0029)** — Week 8
   - Add compensation success rate metrics
   - Add recovery strategy distribution
   - **Deliverable:** Metrics + dashboard panel

**Phase 3 Deliverables:**

- ✅ Saga coordinator with LIFO compensation
- ✅ 50+ compensation handlers
- ✅ Recovery strategies (forward/backward/hybrid)
- ✅ WARD integration tests (>92% recovery success)

**Phase 3 Risks & Mitigation:**

- **Risk:** Compensation failures → **Mitigation:** Best-effort + audit trail (ADR-0008)
- **Risk:** Distributed state corruption → **Mitigation:** WAL-based crash recovery

---

### **Phase 4: Protocol Validation (Week 9-10, Parallel Track)**

**Goal:** Add MPST runtime validation for all agent interactions

**Note:** Can run in parallel with Phase 3 if resources available

1. **PDL Parser (ADR-0003a)** — Week 9
   - Implement YAML parser (PDL → FSM)
   - Add syntax/semantic validation
   - Add deadlock detection (Tarjan's algorithm)
   - Add FlatBuffers FSM serialization
   - **Performance Target:** <100ms compilation per protocol
   - **Deliverable:** `protocol_monitor/pdl_parser.py` + WARD tests

2. **Protocol Monitor (ADR-0003c)** — Week 9
   - Implement FSM registry (load 6 protocols)
   - Implement session FSM tracker (per-session state, RwLock)
   - Implement receive-side validation (<2ms P95)
   - Add violation handler (BLOCK/WARN/DLQ/REPAIR/FALLBACK/ABORT)
   - **Performance Target:** <2ms P95 validation
   - **Deliverable:** `protocol_monitor/monitor.py` + WARD tests

3. **Protocol Definitions (ADR-0003b)** — Week 10
   - Implement 6 PDL protocols:
     - hire.pdl.yml (6 states, 8 transitions)
     - task.pdl.yml (5 states, 10 transitions)
     - clarification.pdl.yml (4 states, 6 transitions)
     - barge_in.pdl.yml (3 states, 5 transitions)
     - tool_call.pdl.yml (4 states, 7 transitions)
     - saga.pdl.yml (5 states, 9 transitions)
   - **Deliverable:** `contracts/protocols/*.pdl.yml` + compiled FSMs

4. **Timeout Enforcer (ADR-0003c, ADR-0008d)** — Week 10
   - Implement background timeout task (100ms poll)
   - Add auto-transitions on timeout
   - Add progress guarantees (liveness properties)
   - **Deliverable:** `protocol_monitor/timeout_enforcer.py` + WARD tests

5. **Security Integration (ADR-0003d, ADR-0010)** — Week 10
   - Implement 2-phase validation (role verification + protocol)
   - Add HMAC-SHA256 role verification (<1ms)
   - Add capability checks
   - **Performance Target:** <3ms total (role + protocol)
   - **Deliverable:** `protocol_monitor/security.py` + WARD tests

6. **Protocol Metrics (ADR-0029)** — Week 10
   - Add protocol violation counters (per protocol)
   - Add timeout rate metrics
   - Create Grafana dashboard (protocol health)
   - **Deliverable:** Metrics + dashboard

**Phase 4 Deliverables:**

- ✅ PDL compiler (YAML → FSM)
- ✅ Protocol monitor with runtime validation
- ✅ 6 protocol definitions (hire/task/clarification/barge_in/tool_call/saga)
- ✅ Timeout enforcement + security integration
- ✅ WARD integration tests (<2ms P95 validation)

**Phase 4 Risks & Mitigation:**

- **Risk:** Protocol violations → **Mitigation:** Graceful degradation (WARN/REPAIR modes)
- **Risk:** Timeout false positives → **Mitigation:** Tunable timeout thresholds

---

### **Phase 5: Integration & Production Hardening (Week 11-12, Critical Path)**

**Goal:** Validate all layer integrations + production readiness

**Workstream 5A: Layer Integrations (Week 11)**

1. **Layer 2 ← Layer 1 Integration (ADR-0004a)** — Week 11
   - Subscribe to Layer 5 EventBus (IntentDetected, UserInput, VoiceCommand, BargeIn)
   - Test event-driven orchestration trigger
   - Validate <10ms P95 event delivery
   - **Deliverable:** `tests/integration/layer2/test_l1_l2_event_bus.py`

2. **Layer 2 → Layer 4 Integration (ADR-0019)** — Week 11
   - Test SessionState writes (control.current_flow, agent_leases)read
   - Test FlatBuffers serialization (<1ms)
   - Validate optimistic locking
   - **Deliverable:** `tests/integration/layer2/test_l2_l4_session_state.py`

3. **Layer 2 → Layer 5 Integration (ADR-0022d)** — Week 11
   - Test K0 Bridge batching (250ms interval, 100 events)
   - Test PLAN_COMMITTED, STATE_DELTA, SAGA_COMPENSATION events
   - Validate <50ms P95 async writes
   - **Deliverable:** `tests/integration/layer2/test_l2_l5_k0_bridge.py`

**Workstream 5B: End-to-End Tests (Week 11-12)**

4. **Full Turn Integration Test** — Week 11
   - Test complete flow: IntentDetected → Planning → Orchestration → Execution → Response
   - Validate performance (<3000ms P95 full turn)
   - Test error paths (LLM timeout, agent crash, tool failure)
   - **Deliverable:** `tests/integration/layer2/test_end_to_end_turn.py`

5. **Error Handling & Resilience Tests** — Week 12
   - Test agent crash recovery
   - Test tool timeout handling (3s timeout)
   - Test LLM failure fallback
   - Test Saga compensation on failure
   - Test circuit breaker activation (ADR-0009)
   - **Deliverable:** `tests/integration/layer2/test_error_handling.py`

6. **Performance Regression Suite** — Week 12
   - Validate all performance budgets:
     - Planning: <2500ms P95
     - Orchestration: <250ms P95
     - Protocol validation: <2ms P95
     - Layer integrations: <10ms P95 (L1→L2), <1ms (L2→L4), <50ms (L2→L5)
   - **Deliverable:** `tests/performance/layer2_budgets.py`

**Workstream 5C: Production Readiness (Week 12)**

7. **Chaos Engineering Tests** — Week 12
   - Test K0 unavailability (WAL writes fail)
   - Test Layer 3 agent spawn failures
   - Test network partitions (Layer 5 EventBus)
   - **Deliverable:** `tests/chaos/layer2_chaos.py`

8. **Security Hardening** — Week 12
   - Audit capability checks (ADR-0010)
   - Audit PII handling (ADR-0035)
   - Audit privacy band enforcement (ADR-0032, ADR-0039)
   - Test role verification (ADR-0003d)
   - **Deliverable:** Security audit report

9. **Documentation & Runbooks** — Week 12
   - Update ADR_REFERENCE.md with implementation notes
   - Create operational runbooks (troubleshooting, rollback)
   - Update layer2_adr_map.md with lessons learned
   - **Deliverable:** Documentation + runbooks

**Phase 5 Deliverables:**

- ✅ All layer integrations validated (L1↔L2, L2↔L3, L2↔L4, L2↔L5)
- ✅ End-to-end integration tests passing
- ✅ Performance budgets validated (all <P95 targets)
- ✅ Error handling + resilience tests passing
- ✅ Chaos engineering tests passing
- ✅ Security audit complete
- ✅ Production runbooks created

**Phase 5 Risks & Mitigation:**

- **Risk:** Performance regression → **Mitigation:** Continuous perf tests (Phase 0)
- **Risk:** Integration bugs → **Mitigation:** Early boundary validation (Phase 2)
- **Risk:** Production incidents → **Mitigation:** Runbooks + observability (ADR-0029)

---

### **Post-Launch: Continuous Improvement (Week 13+)**

**Goal:** Monitor production, iterate based on real usage

1. **Week 13-14: Production Monitoring**
   - Monitor Grafana dashboards (planning, orchestration, protocol violations)
   - Analyze performance P95/P99 (validate budgets)
   - Track Saga compensation success rate (target >92%)
   - Track protocol violation rate (target <1%)

2. **Week 15-16: Performance Optimization**
   - Optimize hot paths (profiling with py-spy)
   - Tune LLM model (if latency issues)
   - Tune MADM weights (if selection bias detected)
   - Optimize K0 batching (if WAL contention)

3. **Week 17-18: Feature Enhancements**
   - Add missing compensation handlers (as tools added)
   - Add new protocol definitions (as needed)
   - Enhance validation rules (based on production failures)

4. **Ongoing: ADR Updates**
   - Update ADRs with production learnings
   - Create new ADRs for architectural changes
   - Maintain ADR_REFERENCE.md and layer2_adr_map.md

---

## 📊 Roadmap Summary

| Phase | Duration | Critical Path | Deliverables | Risk Level |
|-------|----------|---------------|--------------|------------|
| **Phase 0: Foundation** | 2 weeks | ✅ Yes | ADR alignment, K0 POC, LLM benchmark | 🔴 HIGH |
| **Phase 1: Planning** | 3 weeks | ✅ Yes | 4-stage pipeline + metrics + tests | 🟡 MEDIUM |
| **Phase 2: Orchestration** | 3 weeks | ✅ Yes | 3-phase orchestration + L3 integration | 🟡 MEDIUM |
| **Phase 3: Saga** | 2 weeks | ⚪ Parallel | Compensation + recovery strategies | 🟢 LOW |
| **Phase 4: Protocol** | 2 weeks | ⚪ Parallel | MPST validation + 6 protocols | 🟢 LOW |
| **Phase 5: Integration** | 2 weeks | ✅ Yes | E2E tests + production hardening | 🟡 MEDIUM |
| **Post-Launch** | Ongoing | ⚪ Continuous | Monitoring + optimization + enhancements | 🟢 LOW |

**Total Duration:** 12 weeks (critical path) + 2 weeks (foundation) = **14 weeks to production**
**Parallel Optimization:** With 2 teams, can compress to **10 weeks** (Phase 3+4 parallel)

**Success Metrics:**

- ✅ Planning: >95% validation success, <2500ms P95
- ✅ Orchestration: >92% execution success, <250ms P95
- ✅ Saga: >92% compensation success, <5s recovery
- ✅ Protocol: <1% violation rate, <2ms P95 validation
- ✅ Integration: <3000ms P95 full turn, >99% uptime

---

## 📚 Complete ADR Reference List

### **Primary Layer 2 ADRs (6 ADRs)**

- ADR-0001 — Memory Kernel (K0 Core, dual-kernel architecture)
- ADR-0001f — Memory Kernel (multi-store: episodic, semantic, procedural)
- ADR-0004 — 52-Module 5-Layer Architecture
- ADR-0006 — 3-Phase Orchestration
- ADR-0007 — 4-Stage Planning Pipeline
- ADR-0008 — Saga Error Recovery
- ADR-0003 — Protocol Validation (MPST)

### **Planning Pipeline ADRs - Module 1 (4 ADRs)**

- ADR-0007a — Stage 1: Sketch (LLM inference, JSON output)
- ADR-0007b — Stage 2: Expand (tool registry, metadata enrichment)
- ADR-0007c — Stage 3: Validate (2-tier: rules + arbiter)
- ADR-0007d — Stage 4: Commit (K0 WAL write, SessionState locking)

### **Orchestration ADRs - Module 2 (6 ADRs)**

- ADR-0006a — Phase 1: Negotiation (Contract Net Protocol)
- ADR-0006b — Phase 2: Selection (MADM 6-factor scoring)
- ADR-0006c — Phase 3: Execution (DAG parallel execution)
- ADR-0006d — Saga Pattern (LIFO compensation)
- ADR-0006e — Multi-Agent Coordination (wave independence)

### **Saga Error Recovery ADRs (5 ADRs)**

- ADR-0008 — Saga Orchestrator (core compensation logic)
- ADR-0008a — Compensation Design Patterns (50+ tool handlers)
- ADR-0008b — Recovery Strategies (forward/backward/hybrid)
- ADR-0008c — Distributed State Management (crash recovery)
- ADR-0008d — Timeout Management & Deadlock Handling

### **Protocol Validation ADRs - Module 3 (5 ADRs)**

- ADR-0003 — Protocol Validation (MPST overview, 6 protocols)
- ADR-0003a — PDL Language (YAML-based protocol definition)
- ADR-0003b — 6 Protocol Definitions (hire/task/clarification/barge-in/tool_call/saga)
- ADR-0003c — Protocol Monitor (runtime FSM validation)
- ADR-0003d — Security (role verification, 2-phase validation)

### **FlatBuffers & Serialization (10 ADRs)**

- ADR-0011a — Schema Design (naming, types, forward compatibility)
- ADR-0011b — Code Generation (flatc compiler, Python/C++/Rust)
- ADR-0011c — Performance (11× throughput vs JSON)
- ADR-0011d — Schema Evolution (version registry, migration)
- ADR-0012 — Schema Taxonomy (76 schemas, 9 categories)
- ADR-0012b — Layer 2 Schemas (SessionState, planning, orchestration)
- ADR-0013 — SemVer Policy (versioning rules, 90-day deprecation)
- ADR-0013a — Version Registry (compatibility matrix)
- ADR-0013b — CI/CD Automation (schema diff, changelog generation)
- ADR-0013c — Deprecation Workflow (FlatBuffers annotations, notifications)
- ADR-0013d — Contract Testing (forward/backward compatibility)

### **API & Protocol ADRs (14 ADRs)**

- ADR-0014b — OpenAPI Generation (auto-gen from FlatBuffers)
- ADR-0014d — Client SDKs (Python/TypeScript, JSON/FlatBuffers)
- ADR-0015 — WebSocket Binary Protocol (message envelope)
- ADR-0015a — Protocol Design (17 message types)
- ADR-0015b — Flow Control (ACK protocol, batching)
- ADR-0015c — Reconnection (RESUME message, deduplication)
- ADR-0015d — Streaming (token chunks, logprobs)
- ADR-0015e — Client SDK (TypeScript, reconnect/ACK/dedup managers)
- ADR-0016 — SSE Event Taxonomy (17 event types, 5 categories)
- ADR-0016a — Event Taxonomy (agent/turn/tool/session/system events)
- ADR-0016c — Filtering (topic-based, 60-70% bandwidth savings)
- ADR-0016d — Browser Integration (EventSource, React hooks)

### **SessionState & Storage (5 ADRs)**

- ADR-0019 — SessionState Serialization Core (FlatBuffers binary format)
- ADR-0019a — Schema Definition (6 sections: beliefs/scoreboard/control/persona/multimodal/meta)
- ADR-0021c — Turn History Retention (GDPR Article 5(e), 365-day baseline)
- ADR-0022d — K0 Bridge FlatBuffers Schema (batch serialization)
- ADR-0023c — K0 WAL Query (cursor-based pagination, <50ms P95)

### **Performance, Scheduling & QoS (9 ADRs)**

- ADR-0024 — Component-Level Budgets (intent <50ms, orchestration <250ms)
- ADR-0024b — Budget Propagation (deadline_ms propagation)
- ADR-0024d — Graceful Degradation (skip optional features, fallback models)
- ADR-0028 — WFQ Scheduler Priority Queues (URGENT/REALTIME/INTERACTIVE/BACKGROUND)
- ADR-0028a — Virtual Time (fairness formula, proportional CPU allocation)
- ADR-0028b — Preemption (priority-based, <10ms overhead)
- ADR-0028c — Anti-Starvation (age-based boosting, forced scheduling)

### **Observability & Metrics (4 ADRs)**

- ADR-0029 — Prometheus Metrics Component (orchestrator/planner metrics)
- ADR-0029c — Component Metrics (task counters, latency histograms)
- ADR-0029d — Infrastructure Metrics (KV cache, memory, evictions)
- ADR-0030 — Trace Sampling (cognitive_trace_id propagation)

### **Security, Privacy & Compliance (16 ADRs)**

- ADR-0010 — Capability Security (role verification, least privilege)
- ADR-0032 — Egress Control (privacy bands, external API restrictions)
- ADR-0035c — PII Encrypted Vault (AES-256-GCM, KMS integration)
- ADR-0035d — PII Audit Trail (90-day/7-year retention, GDPR/HIPAA)
- ADR-0036 — E2EE Zero-Knowledge Architecture (operator isolation)
- ADR-0036a — AES-256-GCM Encryption (NIST SP 800-38D, hardware acceleration)
- ADR-0036b — KMS Integration (AWS/Azure/Google, BYOK support)
- ADR-0036c — Selective Encryption (SessionState E2EE integration)
- ADR-0036d — E2EE Audit Trail (7-year retention, GDPR/HIPAA compliance)
- ADR-0037d — JWT Session Binding (SessionState metadata integration)
- ADR-0038 — Audit Trail Immutability (append-only, cryptographic hash chain)
- ADR-0038a — Receipt Types (turn/tool/state/agent receipts, SHA-256 integrity)
- ADR-0038b — WAL Integration (async write pipeline, crash recovery)
- ADR-0038c — Retention Policies (band-specific: GREEN 365d, RED 90d)
- ADR-0038d — Query Interface (session/user receipts, hash chain verification)
- ADR-0039 — Privacy Band Retention (RED 97d, GREEN/AMBER 395d, GDPR minimization)

### **Agent Coordination & Fabric (8 ADRs)**

- ADR-0045 — Contract Net Protocol (3-phase orchestration, K1 mailbox-based)
- ADR-0045a — K1 Event Bus (in-memory pub/sub, zero persistence, <2ms fanout)
- ADR-0045b — Topic Routing (trie-based matching, capability filtering)
- ADR-0045c — Delivery Guarantees (at-most-once/at-least-once, idempotency)
- ADR-0045d — Backpressure (mailbox watermark, overflow policies, throttling)
- ADR-0072 — Agent Creation (AgentFactory, runtime creation, <100ms P95)
- ADR-0073 — Lifecycle FSM (WARMING/IDLE/DRAINING states, health checks)

### **K0 Integration & Infrastructure (10 ADRs)**

- ADR-0042a — K0 SSE Event Production (WAL cursor-based, fanout 1-to-N)
- ADR-0042d — K0 SSE Backpressure (slow consumer disconnect, lag monitoring)
- ADR-0043c — SSE Topic Routing (wildcard patterns, at-least-once delivery)
- ADR-0046 — SSE-WebSocket Bridge Configuration (10K connections, send queue)
- ADR-0047 — OpenAPI 3.1 SDK Generation (TypeScript/Python/Go SDKs)
- ADR-0048 — K1 Internal Event Bus Categories (orchestration/planning events, ephemeral only)
- ADR-0049 — Fast/Smart Lane Router (configurable weights, hot-reload)
- ADR-0050 — Multi-Device Family Sync (hybrid LAN/Internet, device autonomy)

### **Enhanced HITL Protocols (6 ADRs)**

- ADR-0052 — Research Foundation (grounding theory, error prevention, Swiss cheese model)
- ADR-0052a — Step-by-Step Approval (progressive disclosure, Saga rollback)
- ADR-0052b — RED Band Approval (risk scoring >0.7, forcing functions, 7-year audit)
- ADR-0052c — Nested Clarifications (QUD stack, multi-turn dialogue state)
- ADR-0052d — Proactive Confirmation (6 confidence factors, <0.70 triggers HITL)
- ADR-0052e — HITL Schema Integration (workflow state, clarification history, FlatBuffers)

### **Turn & Message Management (7 ADRs)**

- ADR-0053 — Message Queue & Coalescing (Nagle's algorithm, SEDA, token bucket)
- ADR-0053a — Coalesce Window (1-3s adaptive, typing speed detection)
- ADR-0053b — Rate Limits (token bucket, per-user 5 msg/sec, burst 10)
- ADR-0053c — Cancel Path (cooperative cancellation, K0 WAL rollback)
- ADR-0054 — Turn Boundary Management (implicit pause, explicit submit)
- ADR-0054a — Implicit Pause (1.5-2.5s TRP threshold, Sacks et al. 1974)
- ADR-0054b — Explicit Submit (send button, Enter key, voice "Send")

### **Voice Pipeline (5 ADRs)**

- ADR-0056 — Pipeline Architecture (K0 P11 ASR + P12 TTS integration)
- ADR-0056a — ASR Ingress (20ms frames, VAD, partial transcripts)
- ADR-0056d — TTS Synthesis (prosody controls, SSML generation, streaming)
- ADR-0056e — Audio Output (jitter buffer 80ms, packet loss recovery)

### **Learning Loop (6 ADRs)**

- ADR-0059 — Core Architecture (K0/K1 boundary, advisory-only, P06 integration)
- ADR-0059a — Feedback Signals (explicit/implicit/behavioral, weighted scoring)
- ADR-0059b — Drift Detection (statistical/behavioral/safety, z-score <3.0)
- ADR-0059c — Parameter Contracts (allowed vs forbidden, bounds validation)
- ADR-0059d — Audit & Rollback (K0 WAL query, point-in-time/selective rollback)
- ADR-0059e — Synthetic Data (persona generator, regression testing, quality metrics)
- ADR-0079 — Drift Detection Algorithm (KL divergence <0.05, 1000-sample warm-up)

### **Knowledge Graph (5 ADRs)**

- ADR-0081 — Knowledge Graph Schema (3-table design, 7 entity types, temporal edges)
- ADR-0081a — Graph Schema & Temporal Edges (bitemporal support, relationship evolution)
- ADR-0081b — Query API & Traversal (BFS/DFS/Dijkstra, <10ms entity lookup)
- ADR-0081c — Episodic Integration (4-stage NER pipeline, spaCy en_core_web_lg)
- ADR-0081d — Visualization & Metrics (Mermaid/GraphML export, real-time metrics)

### **Multi-Party Dialogue (3 ADRs)**

- ADR-0082 — Core Architecture (speaker diarization, turn-taking, conflict resolution)
- ADR-0082b — Turn-Taking (overlap detection, 3 allocation strategies, urgency detection)

### **K0 Memory Consolidation (5 ADRs)**

- ADR-0084 — Core Architecture (3-layer pipeline, 90-min sleep cycles, P03 integration)
- ADR-0084a — Hippocampal Replay (CA3 recurrent activation, 10-20× accelerated replay)
- ADR-0084b — Sleep State Machine (IDLE→NREM1→NREM2→REM→WAKING, resource management)
- ADR-0084c — Knowledge Graph Consolidation (entity extraction, relationship inference, schema evolution)
- ADR-0084d — Dream Exploration (explorative dreaming, counterfactual thinking, mental rehearsal)

### **Embodied Awareness (3 ADRs)**

- ADR-0085 — Core Architecture (7 presence mechanisms, CRDT sync, multi-device)
- ADR-0085a — Device Presence (switch detection, confidence scoring, session handoff)
- ADR-0085c — Context Sharing (notification coordinator, smart handoff, preference learner)

### **Infrastructure & Cross-Cutting (7 ADRs)**

- ADR-0002 — Actor Model (pure actors vs AI agents, mailbox communication)
- ADR-0004b — Import Linting (layer dependency rules, L2→all layers)
- ADR-0004c — Documentation (module READMEs, auto-generation, CI enforcement)
- ADR-0004d — Layer 2 Integration Tests (3-phase/planning/protocol validation)
- ADR-0005 — Agent Lifecycle (hire/fire, WARMING→ACTIVE states)
- ADR-0009 — Circuit Breaker (agent hire resilience, LLM fault tolerance)
- ADR-0027 — Model Placement (Planner local-first SLM)
- ADR-0031 — Cost Tracking (LLM token usage, planning costs)

**Total:** 127 ADRs covering all aspects of Layer 2 orchestration, planning, and related infrastructure.

---

## 🔍 How to Use This Map

1. **Starting New Work:**
   - Read module-specific ADRs first (e.g., ADR-0006 for orchestration, ADR-0007 for planning)
   - Check cross-cutting ADRs for design constraints (serialization, security, observability)
   - Review performance budgets (ADR-0024) before implementing
   - Consult ADR_REFERENCE.md for detailed component breakdown with file paths

2. **During Implementation:**
   - Follow ADR architectural patterns (Actor Model, Contract Net, MADM, DAG, Saga)
   - Use FlatBuffers for serialization (ADR-0011/0012)
   - Add Prometheus metrics (ADR-0029)
   - Add integration tests (ADR-0004d)
   - Respect layer dependencies (ADR-0004b: L2→all layers allowed)

3. **After Implementation:**
   - Validate performance budgets (<100ms orchestration, <2500ms planning)
   - Run integration tests (Ward framework)
   - Update ADR if architecture changed
   - Update this map if new ADRs added

4. **When Lost:**
   - Start with ADR-0004 (complete Layer 2 architecture)
   - Check ADR-0006 (3-phase orchestration) or ADR-0007 (4-stage planning)
   - Check `docs/whiteboard_architecture.md` (3K lines)
   - Consult `k1/l2_orchestration/ADR_REFERENCE.md` (127 ADRs, detailed component breakdown)
   - Use this map to find relevant ADRs by topic

---

**Status:** ✅ **UPDATED** — Synchronized with ADR_REFERENCE.md (127 ADRs)
**Last Updated:** January 2025
**Total ADRs:** 127 ADRs covering Layer 2 (updated from 35+)
**Coverage:** 100% of Layer 2 modules (3 modules + 4 planner sub-modules = 7 total)
**Source:** `k1/l2_orchestration/ADR_REFERENCE.md` (authoritative reference)

---

*For detailed component-level breakdown with file paths and implementation details, see: `k1/l2_orchestration/ADR_REFERENCE.md`*
