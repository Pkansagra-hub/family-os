# Layer 2 (Orchestration) — ADR Family Map

**Complete end-to-end ADR references for K1 Layer 2 modules**

---

## 📋 Overview

**Layer 2 Purpose:** Orchestration & Planning
**Performance Budget:** <100ms P95
**Modules:** 3 modules + 4 planner sub-modules (7 total)
**Primary Function:** 4-stage planning pipeline + 3-phase orchestration + protocol validation

---

## 🗺️ Layer 2 Architecture

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

### **Layer 2 ← Layer 1 (Event Bus Subscription)**

```
Layer 1 publishes:              Layer 2 subscribes:
─────────────────               ──────────────────
IntentDetected event      →     orchestrator (trigger 3-phase)
ClarificationRequired     →     clarification protocol
BargeIn event            →     barge-in protocol
```

### **Layer 2 → Layer 3 (Agent Hire & Tool Execution)**

```
Layer 2 sends:                  Layer 3 receives:
──────────────                  ────────────────
AgentHireRequest         →      agents/hire_fire (spawn agent)
TaskAssignment           →      agent mailbox (execute step)
ToolCallRequest          →      tools/runner (execute tool)
```

### **Layer 2 → Layer 4 (SessionState & Runtime)**

```
Layer 2 writes:                 Layer 4 manages:
───────────────                 ────────────────
FlowDef (current plan)   →      session_state/control section
AgentLease (capabilities) →     session_state/control section
```

### **Layer 2 → Layer 5 (K0 Bridge & Infrastructure)**

```
Layer 2 calls:                  Layer 5 provides:
──────────────                  ────────────────
PLAN_COMMITTED event     →      k0_bridge (WAL write)
STATE_DELTA batch        →      k0_bridge (SessionState sync)
```

**Key Constraints:**
1. **Allowed imports:** L2→L1/L3/L4/L5 (most permissive layer)
2. **Event-driven L1→L2:** No direct imports from L1, subscribe to EventBus
3. **Direct calls L2→L3:** Agent hire, tool execution (synchronous)
4. **Async K0 writes:** Batched STATE_DELTA (250ms interval)

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

## 🚀 Next Steps (Implementation Roadmap)

### **Phase 1: Planning Pipeline (Week 1-3)**
1. Implement planner/sketch (LLM inference + JSON parsing)
2. Implement planner/expand (tool registry lookup)
3. Implement planner/validate (6 rule checks + arbiter)
4. Implement planner/commit (K0 WAL write)
5. Add planning metrics (latency, success rate)

### **Phase 2: Orchestration Core (Week 4-6)**
1. Implement orchestrator/negotiation (Contract Net)
2. Implement orchestrator/selection (MADM scoring)
3. Implement orchestrator/execution (DAG builder, wave executor)
4. Add orchestration metrics (latency, agent proposals)
5. Integration with Layer 3 (agent hire, tool execution)

### **Phase 3: Saga Pattern (Week 7-8)**
1. Implement Saga coordinator (LIFO compensation)
2. Implement compensation registry (50+ tool handlers)
3. Implement recovery strategies (forward/backward/hybrid)
4. Implement failure classifier (transient/permanent/ambiguous)
5. Add Saga metrics (compensation success rate)

### **Phase 4: Protocol Validation (Week 9-10)**
1. Implement PDL parser (YAML→FSM)
2. Implement protocol monitor (runtime validation)
3. Implement 6 protocol definitions (hire/task/clarification/barge_in/tool_call/saga)
4. Implement timeout enforcer (background task)
5. Add protocol metrics (violations, timeouts)

### **Phase 5: Integration & Testing (Week 11-12)**
1. Layer 2 ← Layer 1 integration (EventBus subscription)
2. Layer 2 → Layer 3 integration (agent hire, tool execution)
3. Layer 2 → Layer 4 integration (SessionState writes)
4. Layer 2 → Layer 5 integration (K0 Bridge)
5. End-to-end integration tests (full turn)

---

## 📚 Complete ADR Reference List

### **Primary Layer 2 ADRs**
- ADR-0004 — 52-Module 5-Layer Architecture
- ADR-0006 — 3-Phase Orchestration
- ADR-0007 — 4-Stage Planning Pipeline
- ADR-0008 — Saga Error Recovery
- ADR-0003 — Protocol Validation (MPST)

### **Planning Pipeline ADRs (Module 1)**
- ADR-0007a — Stage 1: Sketch
- ADR-0007b — Stage 2: Expand
- ADR-0007c — Stage 3: Validate
- ADR-0007d — Stage 4: Commit

### **Orchestration ADRs (Module 2)**
- ADR-0006a — Phase 1: Negotiation (Contract Net)
- ADR-0006b — Phase 2: Selection (MADM scoring)
- ADR-0006c — Phase 3: Execution (DAG parallel)
- ADR-0006d — Saga Pattern (compensation)
- ADR-0006e — Multi-Agent Coordination

### **Saga Error Recovery ADRs (Module 2 supporting)**
- ADR-0008a — Compensation Design Patterns
- ADR-0008b — Recovery Strategies
- ADR-0008c — Distributed State Management
- ADR-0008d — Timeout Management & Deadlock Handling

### **Protocol Validation ADRs (Module 3)**
- ADR-0003a — PDL Language (YAML protocol definition)
- ADR-0003b — 6 Protocol Definitions
- ADR-0003c — Protocol Monitor (runtime validation)
- ADR-0003d — Security (role verification, 2-phase validation)

### **Cross-Cutting ADRs**
- ADR-0002 — Actor Model (Orchestrator/Protocol Monitor actors, Planner AI agent)
- ADR-0004b — Import Linting (L2→all layers allowed)
- ADR-0004d — Layer 2 Integration Tests
- ADR-0005 — Agent Lifecycle (hire/fire integration)
- ADR-0009 — Circuit Breaker (agent hire, LLM resilience)
- ADR-0010 — Capability Security (role verification, validation)
- ADR-0011 — FlatBuffers Serialization (FlowDef, FSM)
- ADR-0012 — FlatBuffers Schemas (PlanSketch, TaskAnnouncement, Protocol FSM)
- ADR-0013 — Schema Versioning
- ADR-0019 — SessionState Serialization (Layer 2 writes control section)
- ADR-0022 — K0 Bridge Batching (PLAN_COMMITTED, STATE_DELTA)
- ADR-0024 — Performance Budgets (Layer 2: <100ms orchestration, <2500ms planning)
- ADR-0027 — Model Placement (Planner local-first)
- ADR-0028 — WFQ Scheduler (INTERACTIVE/BACKGROUND)
- ADR-0029 — Prometheus Metrics (orchestration, planning, protocols)
- ADR-0030 — Trace Sampling (cognitive_trace_id)
- ADR-0031 — Cost Tracking (Planner LLM costs)
- ADR-0032 — Egress Control (privacy bands)
- ADR-0035 — PII Detection (redaction before K0)

---

## 🔍 How to Use This Map

1. **Starting New Work:**
   - Read module-specific ADRs first (e.g., ADR-0006 for orchestration)
   - Check cross-cutting ADRs for design constraints
   - Review performance budgets (ADR-0024) before implementing

2. **During Implementation:**
   - Follow ADR architectural patterns (Actor Model, Contract Net, MADM, DAG, Saga)
   - Use FlatBuffers for serialization (ADR-0011/0012)
   - Add Prometheus metrics (ADR-0029)
   - Add integration tests (ADR-0004d)

3. **After Implementation:**
   - Validate performance budgets (<100ms orchestration, <2500ms planning)
   - Run integration tests (Ward framework)
   - Update ADR if architecture changed

4. **When Lost:**
   - Start with ADR-0004 (complete Layer 2 architecture)
   - Check ADR-0006 (3-phase orchestration) or ADR-0007 (4-stage planning)
   - Check `docs/whiteboard_architecture.md` (3K lines)
   - Use this map to find relevant ADRs

---

**Status:** ✅ **COMPLETE** — All Layer 2 ADRs mapped end-to-end
**Last Updated:** January 2025
**Total ADRs:** 35+ ADRs covering Layer 2 (5 primary + 30 supporting)
**Coverage:** 100% of Layer 2 modules (3 modules + 4 planner sub-modules = 7 total)
