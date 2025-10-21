# K1 Intelligence Module - DEPENDENCY_MAP Population Roadmap

**Status:** 📋 PLANNING PHASE
**Last Updated:** 2025-10-17
**Purpose:** Break down DEPENDENCY_MAP.md population into small, manageable batches

---

## Overview: 4 Phases × 12 Batches = 61 Modules Populated

### Timeline

```
Phase 1 (Weeks 1-4): Core Layer Logic
├─ Batch 1: Layer 1 Foundations (4 modules)
├─ Batch 2: Layer 2 Orchestration (3 modules)
├─ Batch 3: Layer 3 Agent Lifecycle (6 modules)
├─ Batch 4: Layer 3 Model Hub (7 modules)
├─ Batch 5: Layer 3 Tools & Dialogue (9 modules)
├─ Batch 6: Layer 4 Runtime (4 modules)
├─ Batch 7: Layer 4 Learning (4 modules)
├─ Batch 8: Layer 5 Infrastructure Core (7 modules)
├─ Batch 9: Layer 5 Safety & Policy (3 modules)
├─ Batch 10: Layer 5 Observability (4 modules)
├─ Batch 11: Layer 5 Configuration (3 modules)
└─ Batch 12: Layer 5 Connectors (2 modules)

Phase 1 Gate: ADR-0006/0007 implemented + ADR-0003 validates 6 protocols + ADR-0028 scheduler live

Phase 2 (Weeks 5-8): External Systems
├─ Batch 13: Voice I/O Adapters (5 modules)
├─ Batch 14: LLM Provider Integration (4 modules)
├─ Batch 15: Tool & MCP Integration (4 modules)
└─ Batch 16: Storage & Observability Backends (4 modules)

Phase 2 Gate: 3+ LLM providers + 5+ MCP tools + voice pipeline (ADR-0056) operational

Phase 3 (Weeks 9-10): K0 Bridge & Sync
├─ Batch 17: K0-K1 Bridge Core (4 modules)
└─ Batch 18: Multi-Device Family Sync (3 modules)

Phase 3 Gate: K0 bridge operational + ADR-0050a coherence validated + LAN sync <1ms + P2P sync <500ms

Phase 4 (Weeks 11-12): Testing & UX
├─ Batch 19: Integration Testing Framework (4 modules)
├─ Batch 20: E2E & Chaos Testing (3 modules)
└─ Batch 21: UX & Product Features (4 modules)

Phase 4 Gate: E2E tests validate P95 budgets + ADR-0066 simulation harness operational
```

---

## PHASE 1: Core Layer Logic (Weeks 1-4)

**Goal:** Populate each layer's foundational modules with ADR decision mapping

**Success Criteria:**
- ✅ Every module has primary ADR + sub-ADR references
- ✅ Dependency graph shows layer-to-layer relationships
- ✅ Performance budgets (ADR-0024) linked to each module
- ✅ Layer boundary enforcement (ADR-0004b) validated
- ✅ Event bus (ADR-0004a) backbone operational for L1→L5→L2 flow

**Primary ADRs Used:**
- ADR-0004 (52-module architecture master reference)
- ADR-0003 (MPST protocol validation) ✅ IMPLEMENTED
- ADR-0005 (Agent lifecycle FSM) ✅ IMPLEMENTED
- ADR-0002 (Actor model) ✅ IMPLEMENTED
- ADR-0006, 0006a-0006e (3-phase orchestration) ⏳ PRIORITY 1
- ADR-0007, 0007a-0007d (4-stage planning) ⏳ PRIORITY 1
- ADR-0028 (WFQ scheduler) ⏳ PRIORITY 1

---

### **BATCH 1: Layer 1 Input Processing Foundations**


**Modules (4):** stream_switch, operators, intent_router, meta_policy

**What to Populate:**
1. stream_switch
   - Imports: `k1.infrastructure.event_bus` (L5)
   - Exports: `InputStreamEvent` → event_bus (L5)
   - ADRs: ADR-0056 (voice pipeline), ADR-0057 (voice backpressure)
   - Performance: <5ms per stream event
   - Sub-modules: VAD detection, frame buffering, stream routing

2. operators
   - Imports: `k1.infrastructure.metrics` (L5), `k1.infrastructure.logging` (L5)
   - Exports: `StreamTransformedEvent` → event_bus (L5)
   - ADRs: ADR-0056a (ASR integration), ADR-0056b (TTS integration)
   - Performance: <5ms per transformation
   - Sub-modules: ASR transformer, TTS transformer, vision transformer

3. intent_router
   - Imports: `k1.infrastructure.event_bus` (L5)
   - Exports: `IntentDetectedEvent` → event_bus (L5)
   - ADRs: ADR-0058 (intent classification), ADR-0058a (voice intent bridge)
   - Performance: <50ms P95 (T1: regex <1ms, T2: SLM 2-3ms, T3: LLM <50ms)
   - Sub-modules: Regex engine, SLM router, LLM fallback, confidence scorer

4. meta_policy
   - Imports: `k1.infrastructure.event_bus` (L5), `k1.infrastructure.policy` (L5)
   - Exports: `ProactivityEvent`, `ClarificationEvent` → event_bus (L5)
   - ADRs: ADR-0057c (meta-policy proactivity), ADR-0058b (clarification engine)
   - Performance: <10ms decision latency
   - Sub-modules: Proactivity scorer, clarification trigger, context analyzer

**Deliverables:**
- Update Layer 1 section in DEPENDENCY_MAP.md with:
  - Exact imports/exports for each module
  - ADR references with sub-ADR breakdown
  - Performance budget links
  - Inter-module communication diagram

**Acceptance Criteria:**
- ✅ All 4 modules have filled ADR Reference column (was "TBD")
- ✅ Dependency details show exact L5 imports
- ✅ Performance budgets reference ADR-0024
- ✅ Layer boundary enforcement (L1 → L5 only) documented

**Time Estimate:** 2-3 hours

---

### **BATCH 2: Layer 2 Orchestration Foundations**

**Modules (3):** planner, orchestrator, protocol_monitor

**What to Populate:**

1. planner (4-Stage Pipeline)
   - Imports: `k1.infrastructure.event_bus`, `k1.runtime.session_state`, `k1.execution.model_hub` (Layers 1, 3, 4, 5)
   - Exports: `FlowDef` (plan definition)
   - ADRs: ADR-0007 (4-stage planning: sketch→expand→validate→commit)
   - Sub-ADRs: ADR-0007a (sketch LLM), ADR-0007b (expand deterministic), ADR-0007c (validate rules), ADR-0007d (commit)
   - Performance: <5000ms P95 (includes LLM call in Stage 1)
   - LLM Usage: One of 4 AI agents using Model Hub
   - Sub-modules: Sketch engine (LLM), Expander (deterministic), Validator (rules + arbiter), Committer (persistence)

2. orchestrator (3-Phase Coordination)
   - Imports: `k1.infrastructure.event_bus`, `k1.execution.*`, `k1.runtime.session_state` (Layers 1, 3, 4, 5)
   - Exports: Agent hire requests → Layer 3
   - ADRs: ADR-0006 (3-phase orchestration: negotiation→selection→execution)
   - Sub-ADRs: ADR-0006a (negotiation), ADR-0006b (scoring), ADR-0006c (parallel DAG), ADR-0006d (saga integration)
   - Pattern: Contract Net Protocol (Smith 1980 research-based)
   - Performance: <250ms P95
   - Sub-modules: Negotiator (broadcast proposals), Scorer (agent evaluation), Executor (execution scheduler)

3. protocol_monitor (MPST Validation)
   - Imports: `k1.runtime.session_state`, `k1.infrastructure.metrics` (Layers 4, 5)
   - Exports: Protocol violation alerts
   - ADRs: ADR-0003 (MPST protocol validation) ✅ IMPLEMENTED
   - Sub-ADRs: ADR-0003a (Agent Hire), ADR-0003b (Task Execution), ADR-0003c (Clarification), ADR-0003d (Barge-In)
   - Validates: 6 protocols (Agent Hire, Task Execution, Clarification, Barge-In, Tool Call, Saga Rollback)
   - Performance: <1ms validation latency (async)

**Deliverables:**
- Update Layer 2 section in DEPENDENCY_MAP.md with:
  - 3-phase orchestration diagram (negotiation→selection→execution)
  - 4-stage planning pipeline diagram (sketch→expand→validate→commit)
  - 6 protocols monitored with MPST references
  - Inter-module communication flow (event_bus → orchestrator → planner ↔ Layer 3)

**Acceptance Criteria:**
- ✅ ADR-0006/0007 primary references + 5 sub-ADRs each documented
- ✅ ADR-0003 validates all 6 protocols (documented with Scribble notation)
- ✅ Full visibility imports documented (L1, L3, L4, 5)
- ✅ Contract Net Protocol research citation included

**Time Estimate:** 2-3 hours

---

### **BATCH 3: Layer 3 Agent Lifecycle**

**Modules (6):** registry, hire_fire, supervisor, personality, mailbox, active_roster

**What to Populate:**

1. registry
   - Imports: `k1.infrastructure.config` (L5)
   - Exports: Agent specs, templates
   - ADRs: ADR-0004 (architecture), ADR-0005 (lifecycle FSM)
   - Sub-ADRs: ADR-0005a (6 states), ADR-0005b (state transitions), ADR-0005c (supervisor role)

2. hire_fire
   - Imports: `k1.runtime.session_state`, `k1.infrastructure.metrics` (Layers 4, 5)
   - Exports: Agent lifecycle transitions
   - ADRs: ADR-0005 (lifecycle FSM)
   - Sub-ADRs: ADR-0005a (6 states: PENDING→WARMING→ACTIVE→IDLE→DRAINING→TERMINATED)
   - Performance: <600ms PENDING→WARMING→ACTIVE transition

3. supervisor
   - Imports: `k1.runtime.session_state`, `k1.infrastructure.metrics` (Layers 4, 5)
   - Exports: Health monitoring, escalations
   - ADRs: ADR-0002b (supervisor role), ADR-0005c (lifecycle supervision)
   - Sub-ADRs: ADR-0002b1 (crash detection), ADR-0002b2 (blacklist), ADR-0002b3 (escalation)
   - Pattern: Actor Model (Hewitt 1973)

4. personality
   - Imports: `k1.infrastructure.config` (L5)
   - Exports: Personality traits, tone settings
   - ADRs: ADR-0005e (personality adaptation)
   - Sub-ADRs: ADR-0067 (delight factors), ADR-0069 (affect modulation)

5. mailbox
   - Imports: `k1.infrastructure.metrics` (L5)
   - Exports: MPSC message queues
   - ADRs: ADR-0002a (mailbox architecture)
   - Pattern: Message-passing Actor Model
   - Performance: <1ms enqueue latency

6. active_roster
   - Imports: `k1.infrastructure.metrics` (L5)
   - Exports: Agent status tracking
   - ADRs: ADR-0005b (lifecycle state transitions)
   - Performance: <10ms roster lookup

**Deliverables:**
- Update Layer 3 "Agent Lifecycle" subsection with:
  - FSM state diagram (6 states)
  - Supervisor monitoring architecture
  - Mailbox MPSC queue design
  - Registry + personality integration

**Acceptance Criteria:**
- ✅ All 6 modules have ADR-0005 references + sub-ADRs
- ✅ FSM transitions documented with timeouts
- ✅ Supervisor escalation policy documented
- ✅ Actor Model research citations included

**Time Estimate:** 2-3 hours

---

### **BATCH 4: Layer 3 Model Hub (LLM Integration)**

**Modules (7):** router, placement_planner, adapters, kv_cache_broker, prompt_library, fallback_cascade, safety_filter

**What to Populate:**

1. router
   - Imports: `k1.infrastructure.config` (L5)
   - Exports: LLM call routing decisions
   - ADRs: ADR-0001b (Model Hub architecture), ADR-0018 (model provider abstraction)
   - Sub-ADRs: ADR-0018a (router logic), ADR-0018b (fallback selection)
   - Serves: 4 AI agents (Concierge, Planner, Researcher, Safety Watch)

2. placement_planner
   - Imports: `k1.infrastructure.thermal`, `k1.infrastructure.budgets` (L5)
   - Exports: Placement decisions (NPU/GPU/CPU/Remote)
   - ADRs: ADR-0027 (model placement cascade)
   - Sub-ADRs: ADR-0027a (thermal awareness), ADR-0027b (cost awareness), ADR-0027c (latency SLOs)
   - Research: FPGA/GPU scheduling literature
   - Performance: <50ms placement decision

3. adapters
   - Imports: `k1.infrastructure.config` (L5)
   - Exports: Unified LLM interface
   - ADRs: ADR-0018 (model provider abstraction)
   - Sub-ADRs: ADR-0019 (provider failover), ADR-0018a (adapter pattern)
   - Providers: OpenAI, Anthropic, Google, vLLM, Ollama, Azure

4. kv_cache_broker
   - Imports: `k1.infrastructure.cache` (L5)
   - Exports: Managed KV cache state
   - ADRs: ADR-0025 (KV cache management), ADR-0060 (adaptive cache)
   - Sub-ADRs: ADR-0025a (eviction strategy), ADR-0060a (learning-driven placement)
   - Budget: 128MB shared cache
   - Performance: <1ms cache lookup

5. prompt_library
   - Imports: `k1.infrastructure.storage_connector` (L5)
   - Exports: Prompt templates + system messages
   - ADRs: ADR-0020 (prompt template management)
   - Sub-ADRs: ADR-0020a (template versioning), ADR-0020b (context optimization)
   - Serves: 4 AI agents (Concierge, Planner, Researcher, Safety Watch)

6. fallback_cascade
   - Imports: `k1.infrastructure.config`, `k1.infrastructure.budgets` (L5)
   - Exports: Provider failover decisions
   - ADRs: ADR-0019 (model failover & fallback)
   - Sub-ADRs: ADR-0019a (fallback sequence), ADR-0019b (cost awareness), ADR-0019c (latency SLOs)
   - Pattern: Graceful degradation

7. safety_filter
   - Imports: `k1.infrastructure.safety.pii_detector`, `k1.infrastructure.policy` (L5)
   - Exports: Safety check results
   - ADRs: ADR-0035 (PII detection), ADR-0032 (band-based security)
   - Sub-ADRs: ADR-0035a (detection methods), ADR-0035b (redaction)
   - Serves: Safety Watch agent only (1 of 4 AI agents)

**Deliverables:**
- Update Layer 3 "Model Hub" subsection with:
  - Router decision tree (which provider for which call)
  - Placement ladder (NPU → GPU → CPU → Remote)
  - Adapter interface for all providers
  - KV cache management strategy
  - 4 AI agents served + budgets

**Acceptance Criteria:**
- ✅ All 7 modules have Model Hub (ADR-0001b) + provider (ADR-0018/0019) references
- ✅ 4 AI agents explicitly listed with LLM budgets
- ✅ Fallback cascade documented with cost awareness
- ✅ KV cache management tied to Learning Loop (ADR-0060)

**Time Estimate:** 2-3 hours

---

### **BATCH 5: Layer 3 Tools & Dialogue**

**Modules (9):** runner, sandbox, registry, adapters, control (5 Tool modules) + scoreboard, state_tracker, turn_manager, repair (4 Dialogue modules)

**What to Populate:**

**Tool Execution (5 modules):**

1. runner
   - Imports: `k1.infrastructure.policy`, `k1.infrastructure.metrics` (L5)
   - Exports: Tool execution results + receipts
   - ADRs: ADR-0012 (tool discovery, validation, execution)
   - Sub-ADRs: ADR-0012a (discovery), ADR-0012b (validation), ADR-0012c (execution)

2. sandbox
   - Imports: `k1.infrastructure.policy` (L5)
   - Exports: Sandboxed execution environments
   - ADRs: ADR-0033 (three-tier sandbox strategy)
   - Sub-ADRs: ADR-0033a (Protocol layer), ADR-0033b (Sandbox layer), ADR-0033c (Band layer)
   - Types: MCP (JSON-RPC), WASM, Process isolation

3. registry
   - Imports: `k1.infrastructure.config` (L5)
   - Exports: Tool catalog + capabilities
   - ADRs: ADR-0013 (dynamic tool loading), ADR-0010 (capability-based security)
   - Sub-ADRs: ADR-0013a (runtime registration), ADR-0013b (versioning)

4. adapters
   - Imports: `k1.infrastructure.config` (L5)
   - Exports: Tool protocol adapters (MCP, REST, GraphQL, SOAP)
   - ADRs: ADR-0034 (MCP protocol for tool sandboxing)
   - Sub-ADRs: ADR-0034a (JSON-RPC 2.0), ADR-0034b (streaming)

5. control
   - Imports: `k1.infrastructure.metrics`, `k1.infrastructure.policy` (L5)
   - Exports: Tool execution constraints (timeout, resource limits)
   - ADRs: ADR-0014 (tool timeout management), ADR-0031 (cost tracking)
   - Sub-ADRs: ADR-0014a (timeout enforcement), ADR-0031a (hierarchical budgets)

**Dialogue Management (4 modules):**

6. scoreboard
   - Imports: `k1.infrastructure.metrics` (L5)
   - Exports: Task progress tracking
   - ADRs: ADR-0053 (message queue & coalescing)
   - Sub-ADRs: ADR-0053a (rapid message batching)

7. state_tracker
   - Imports: `k1.runtime.session_state`, `k1.infrastructure.metrics` (Layers 4, 5)
   - Exports: Dialogue state mutations
   - ADRs: ADR-0054 (turn boundary management)
   - Sub-ADRs: ADR-0054a (explicit turns), ADR-0054b (implicit turns)

8. turn_manager
   - Imports: `k1.infrastructure.event_bus`, `k1.infrastructure.metrics` (L5)
   - Exports: Turn transitions, barge-in handling
   - ADRs: ADR-0057 (voice-specific backpressure)
   - Sub-ADRs: ADR-0057a (barge-in detection), ADR-0057b (preemption logic)

9. repair
   - Imports: `k1.infrastructure.metrics`, `k1.infrastructure.policy` (L5)
   - Exports: Error recovery + clarification
   - ADRs: ADR-0008 (saga pattern error recovery)
   - Sub-ADRs: ADR-0008a (compensating txns), ADR-0008b (repair sequences)

**Deliverables:**
- Update Layer 3 "Tool Execution" subsection with:
  - Three-tier sandbox strategy diagram
  - MCP protocol adapter architecture
  - Tool registry + capability model
  - Tool timeout + cost budget framework

- Update Layer 3 "Dialogue Management" subsection with:
  - Turn boundary diagram (explicit vs implicit)
  - Message coalescing strategy
  - Repair protocol for error recovery

**Acceptance Criteria:**
- ✅ All 9 modules have primary ADR + sub-ADRs documented
- ✅ Three-tier sandbox (Protocol × Sandbox × Band) diagram included
- ✅ MCP protocol integration fully documented
- ✅ Tool capability model linked to ADR-0010 (least privilege)
- ✅ Dialogue flow diagram shows turn boundaries + repair paths

**Time Estimate:** 3-4 hours

---

### **BATCH 6: Layer 4 Runtime Core**

**Modules (4):** leases, mailbox, session_state, flow_engine

**What to Populate:**

1. leases
   - Imports: `k1.infrastructure.policy` (L5)
   - Exports: Capability tokens + lease management
   - ADRs: ADR-0010 (capability-based security)
   - Sub-ADRs: ADR-0010a (token generation), ADR-0010b (delegation), ADR-0010c (revocation)
   - Research: Capabilities (Dennis & Van Horn 1966)

2. mailbox
   - Imports: `k1.infrastructure.metrics` (L5)
   - Exports: Per-agent MPSC queues
   - ADRs: ADR-0002a (mailbox architecture) - same as Layer 3 mailbox but L4 coordination
   - Performance: <1ms enqueue latency
   - Pattern: Message-passing coordination

3. session_state (6-Section Design)
   - Imports: `k1.infrastructure.metrics`, `k1.infrastructure.storage_connector` (L5)
   - Exports: Serialized state → K0 bridge
   - ADRs: ADR-0017 (SessionState 6-section design)
   - Sub-ADRs: ADR-0017a (Beliefs), ADR-0017b (Scoreboard), ADR-0017c (Control), ADR-0017d (Persona), ADR-0017e (Multimodal), ADR-0017f (Meta)
   - 6 Sections:
     1. Beliefs: User model, preferences, history
     2. Scoreboard: Task tracking, common ground
     3. Control: Current intent, active flow
     4. Persona: Agent personality, tone settings
     5. Multimodal: Recent inputs (audio, video, text)
     6. Meta: Session metadata (trace_id, start_time)
   - Performance Budget: Serialize <1ms (FlatBuffers)
   - Memory Budget: <64KB per session (soft limit)

4. flow_engine
   - Imports: `k1.runtime.session_state`, `k1.execution.*`, `k1.infrastructure.*` (Layers 3, 4, 5)
   - Exports: Flow execution results
   - ADRs: ADR-TBD (deterministic DSL executor)
   - DSL Commands: Await, Decide, Call, Yield, Persist, Fork/Join, Abort
   - Performance: <100ms per DSL operation

**Deliverables:**
- Update Layer 4 "Runtime" subsection with:
  - 6-section SessionState architecture diagram
  - Memory layout + eviction strategy
  - FlatBuffers serialization schema reference
  - Lease token model + delegation chain
  - Flow engine DSL command reference

**Acceptance Criteria:**
- ✅ ADR-0017 (6-section design) fully documented with all sub-sections
- ✅ SessionState serialization <1ms performance requirement documented
- ✅ 64KB memory budget linked to ADR-0024
- ✅ Capability-based security (ADR-0010) integrated with leases
- ✅ Flow engine DSL commands documented with examples

**Time Estimate:** 2-3 hours

---

### **BATCH 7: Layer 4 Learning Loop**

**Modules (4):** learning_loop, feedback_collector, drift_detector, model_updater

**What to Populate:**

1. learning_loop
   - Imports: `k1.infrastructure.metrics`, `k1.infrastructure.config_manager` (L5)
   - Exports: Updated weights → Layer 5 (config_manager)
   - ADRs: ADR-0059 (learning loop architecture)
   - Sub-ADRs: ADR-0059a (feedback signals), ADR-0059b (drift detection), ADR-0059c (weight updates)
   - Research: Reinforcement Learning (Sutton & Barto 2018)

2. feedback_collector
   - Imports: `k1.infrastructure.event_bus` (L5)
   - Exports: Aggregated feedback signals
   - ADRs: ADR-0059a (feedback signals)
   - Sub-ADRs: ADR-0059a1 (explicit: weight 1.0), ADR-0059a2 (implicit: weight 0.5), ADR-0059a3 (behavioral: weight 0.2)
   - Signals:
     - Explicit: User thumbs-up/down (weight 1.0)
     - Implicit: Task success/failure (weight 0.5)
     - Behavioral: Time-to-task, retry patterns (weight 0.2)

3. drift_detector
   - Imports: `k1.infrastructure.metrics` (L5)
   - Exports: Drift alerts + retraining triggers
   - ADRs: ADR-0059b (drift detection)
   - Sub-ADRs: ADR-0059b1 (performance monitoring), ADR-0059b2 (threshold detection)
   - Trigger: Performance drop >20% triggers retraining

4. model_updater
   - Imports: `k1.infrastructure.config_manager`, `k1.infrastructure.metrics` (L5)
   - Exports: Updated weights → config hot-reload
   - ADRs: ADR-0059c (weight updates)
   - Sub-ADRs: ADR-0059c1 (ranking updates), ADR-0059c2 (config deployment)

**Deliverables:**
- Update Layer 4 "Learning" subsection with:
  - Feedback signal weighting schema
  - Drift detection threshold + monitoring
  - Weight update + hot-reload flow
  - Learning signal aggregation pipeline

**Acceptance Criteria:**
- ✅ ADR-0059 (learning loop) fully documented with all sub-ADRs
- ✅ 3 feedback signal types with weights documented
- ✅ Drift detection >20% threshold explicitly stated
- ✅ Config hot-reload integration with Layer 5 documented
- ✅ Reinforcement Learning research citations included

**Time Estimate:** 2-3 hours

---

### **BATCH 8: Layer 5 Infrastructure Core**

**Modules (7):** scheduler, backpressure, thermal, budgets, cache, rate_limiting, storage_connector

**What to Populate:**

1. scheduler (WFQ - Weighted Fair Queuing)
   - Imports: None (L5 foundation)
   - Exports: Task scheduling decisions to all layers
   - ADRs: ADR-0028 (WFQ scheduler)
   - Sub-ADRs: ADR-0028a (4-tier priority), ADR-0028b (anti-starvation), ADR-0028c (fairness)
   - Priority Tiers:
     1. CRITICAL: User voice input, safety violations
     2. HIGH: Model Hub calls, orchestration
     3. NORMAL: Tool execution, state updates
     4. LOW: Learning loop, metrics aggregation
   - Performance: <1ms scheduling decision

2. backpressure (Flow Control & Cascade)
   - Imports: None (L5 foundation)
   - Exports: Backpressure signals to all layers
   - ADRs: ADR-0061 (3-tier backpressure cascade)
   - Sub-ADRs: ADR-0061a (watermarks), ADR-0061b (fairness), ADR-0061c (recovery)
   - 3 Tiers:
     1. Soft (50%): Warnings, metrics
     2. Hard (75%): Drop low-priority tasks
     3. OOM (90%): Drop all except CRITICAL
   - Cascade: Voice-specific degradation ladder (ADR-0057)

3. thermal (NPU/GPU/CPU Heat Management)
   - Imports: None (L5 foundation)
   - Exports: Placement decisions → model_hub.placement_planner
   - ADRs: ADR-0026 (thermal hysteresis matrix)
   - Sub-ADRs: ADR-0026a (temperature monitoring), ADR-0026b (hysteresis), ADR-0026c (placement decisions)
   - Hysteresis: 5°C buffer (prevent thrashing)
   - States: Cool, Warm, Hot, Critical with escalating placement options

4. budgets (Resource Limits)
   - Imports: None (L5 foundation)
   - Exports: Budget enforcement to all layers
   - ADRs: ADR-0024 (performance budgets), ADR-0031 (cost tracking)
   - Sub-ADRs: ADR-0024a (TTFT), ADR-0024b (E2E latency), ADR-0031a (hierarchical), ADR-0031b (per-session)
   - Budget Types:
     - Tokens (model input/output)
     - Dollars (API call costs)
     - Compute ms (CPU/GPU time)
     - Latency (response time SLOs)

5. cache (KV Cache 128MB + Prompt Cache 64MB)
   - Imports: None (L5 foundation)
   - Exports: Managed cache state to model_hub
   - ADRs: ADR-0025 (KV cache management)
   - Sub-ADRs: ADR-0025a (eviction strategy), ADR-0025b (compression), ADR-0025c (memory tiering)
   - Budget: 128MB model KV + 64MB prompt templates
   - Strategy: LRU-LFU hybrid with Zstd compression
   - Eviction: 3-tier (soft→hard→OOM) tied to backpressure

6. rate_limiting (Token Bucket per-Intent)
   - Imports: None (L5 foundation)
   - Exports: Rate limit decisions to orchestrator
   - ADRs: ADR-TBD (rate limiting)
   - Per-intent limits with drift detection
   - Gradual backoff (not sudden drop)

7. storage_connector (Persistence Abstraction)
   - Imports: None (L5 foundation)
   - Exports: Persistence interface to session_state + k0_bridge
   - ADRs: ADR-0020 (multi-tier storage L1/L2/L3)
   - Sub-ADRs: ADR-0020a (L1 RAM), ADR-0020b (L2 SSD K0 WAL), ADR-0020c (L3 S3)
   - Tiers:
     - L1: In-memory (hot)
     - L2: SSD K0 WAL (warm)
     - L3: S3 cold archive (cold)

**Deliverables:**
- Update Layer 5 "Infrastructure" subsection with:
  - WFQ scheduler 4-tier priority architecture
  - Backpressure 3-tier cascade diagram
  - Thermal state machine + hysteresis logic
  - Budget enforcement hierarchy
  - KV cache + prompt cache architecture
  - Multi-tier storage (L1/L2/L3) diagram

**Acceptance Criteria:**
- ✅ ADR-0028 (WFQ scheduler) fully documented with priority tiers
- ✅ ADR-0061 (backpressure cascade) with watermarks documented
- ✅ ADR-0026 (thermal hysteresis) with 5°C buffer explicit
- ✅ ADR-0024 (performance budgets) linked to all SLOs
- ✅ ADR-0025 (cache management) with 128MB/64MB budgets
- ✅ ADR-0020 (multi-tier storage) with L1/L2/L3 tiers

**Time Estimate:** 3-4 hours

---

### **BATCH 9: Layer 5 Safety & Policy**

**Modules (3):** policy, pii_detector, arbiter

**What to Populate:**

1. policy (Bands.yml + Caps.yml + Budgets.yml Enforcement)
   - Imports: None (L5 foundation)
   - Exports: Policy enforcement rules to all layers
   - ADRs: ADR-0032 (band-based egress rules), ADR-0033 (three-tier sandbox)
   - Sub-ADRs: ADR-0032a (GREEN band), ADR-0032b (AMBER band), ADR-0032c (RED band)
   - 3 Privacy Bands:
     - GREEN: Unrestricted, no PII concerns
     - AMBER: Restricted, monitoring required
     - RED: Requires arbiter approval, high sensitivity
   - Enforcement: Network, filesystem, resource egress per band

2. pii_detector (3-Tier: Regex → ONNX → LLM)
   - Imports: None (L5 foundation)
   - Exports: PII detection + redaction markers
   - ADRs: ADR-0035 (PII detection & redaction)
   - Sub-ADRs: ADR-0035a (regex patterns <1ms), ADR-0035b (ONNX 2-3ms), ADR-0035c (LLM fallback <50ms)
   - Vault: Secret storage for detected PII
   - Redaction: Replace with markers `[PII: NAME]`, `[PII: EMAIL]`, etc.

3. arbiter (RED Band Human-in-the-Loop)
   - Imports: None (L5 foundation)
   - Exports: Approval/rejection decisions for RED band operations
   - ADRs: ADR-0052 (enhanced HITL protocols)
   - Sub-ADRs: ADR-0052a (approval workflows), ADR-0052b (risk confirmation), ADR-0052c (timeouts)
   - Pattern: Async approval with timeouts
   - Escalation: Operator/admin review path

**Deliverables:**
- Update Layer 5 "Safety & Policy" subsection with:
  - 3-band privacy model (GREEN/AMBER/RED) diagram
  - PII detection 3-tier cascade
  - Arbiter approval workflow
  - Egress enforcement per band

**Acceptance Criteria:**
- ✅ ADR-0032 (band-based security) with 3 bands documented
- ✅ ADR-0035 (PII detection) with 3-tier cascade documented
- ✅ ADR-0052 (HITL) with arbiter approval flow documented
- ✅ Egress enforcement (network/fs/resource) per band specified
- ✅ Secret vault architecture for PII storage

**Time Estimate:** 2-3 hours

---

### **BATCH 10: Layer 5 Observability**

**Modules (4):** tracing, metrics, receipts, perf_harness

**What to Populate:**

1. tracing (OpenTelemetry + cognitive_trace_id)
   - Imports: None (L5 foundation)
   - Exports: Trace spans to all layers
   - ADRs: ADR-0029 (OpenTelemetry tracing)
   - Sub-ADRs: ADR-0029a (trace propagation), ADR-0029b (span types), ADR-0029c (sampling)
   - Sampling Strategies: Head, tail, adaptive
   - cognitive_trace_id: Propagated to all operations

2. metrics (Prometheus RED Method)
   - Imports: None (L5 foundation)
   - Exports: Metrics to all layers
   - ADRs: ADR-0030 (Prometheus metrics)
   - Sub-ADRs: ADR-0030a (counters), ADR-0030b (gauges), ADR-0030c (histograms)
   - RED Method:
     - Rate: Requests per second
     - Errors: Error rate percentage
     - Duration: Latency percentiles (P50/P95/P99)

3. receipts (Aggregation + Audit)
   - Imports: None (L5 foundation)
   - Exports: Audit trails + compliance logs
   - ADRs: ADR-0038 (audit trail receipts)
   - Sub-ADRs: ADR-0038a (model receipts), ADR-0038b (tool receipts), ADR-0038c (protocol receipts), ADR-0038d (state receipts)
   - Receipt Types: Model calls, tool execution, MPST violations, state persistence

4. perf_harness (Synthetic Load + Benchmarks)
   - Imports: None (L5 foundation)
   - Exports: Performance validation results
   - ADRs: ADR-0066 (developer testing & simulation harness)
   - Sub-ADRs: ADR-0066a (synthetic users), ADR-0066b (load profiles), ADR-0066c (LLM eval)
   - Benchmarks: Validate P95 latency budgets (ADR-0024)

**Deliverables:**
- Update Layer 5 "Observability" subsection with:
  - OpenTelemetry tracing architecture
  - Prometheus RED method metrics schema
  - Receipt types + audit trail structure
  - Performance harness synthetic load profiles

**Acceptance Criteria:**
- ✅ ADR-0029 (tracing) with cognitive_trace_id propagation documented
- ✅ ADR-0030 (metrics) with RED method fully documented
- ✅ ADR-0038 (receipts) with 4 receipt types specified
- ✅ ADR-0066 (perf harness) with synthetic profiles documented
- ✅ All metrics tied to performance budgets (ADR-0024)

**Time Estimate:** 2-3 hours

---

### **BATCH 11: Layer 5 Configuration**

**Modules (3):** global, schemas, config_manager

**What to Populate:**

1. global (agents.yml, models.yml, tools.yml, scheduler.yml)
   - Imports: None (L5 foundation)
   - Exports: Global configuration to all layers
   - ADRs: ADR-TBD (global configuration)
   - Config Files:
     - agents.yml: Agent registry + capabilities
     - models.yml: Model providers + endpoints
     - tools.yml: Tool registry + MCP mappings
     - scheduler.yml: WFQ weights + priority tiers
     - policy.yml: Band definitions + egress rules

2. schemas (Pydantic + FlatBuffers Definitions)
   - Imports: None (L5 foundation)
   - Exports: Schema definitions to all layers
   - ADRs: ADR-0011 (FlatBuffers binary format), ADR-0012 (76 schema definitions), ADR-0013 (schema versioning)
   - Sub-ADRs: ADR-0011a (zero-copy serialization), ADR-0012a (schema registry), ADR-0013a (90-day deprecation)
   - 76 Schemas: Across 5 layers (L1-L5 interaction schemas)

3. config_manager (Hot Reload + SSE Listener)
   - Imports: None (L5 foundation)
   - Exports: Config updates to all layers (non-blocking hot reload)
   - ADRs: ADR-TBD (config management), ADR-0042 (K0 SSE event streaming)
   - Sub-ADRs: ADR-TBD-a (hot reload mechanics), ADR-0042a (SSE subscription)
   - Features:
     - Hot reload (no restart required)
     - SSE listener for config changes from K0
     - Merger (combine local + K0 configs)
     - Validator (schema validation)

**Deliverables:**
- Update Layer 5 "Configuration" subsection with:
  - Global config file structure (5 files)
  - FlatBuffers schema registry reference
  - Schema versioning + deprecation policy
  - Hot-reload architecture diagram

**Acceptance Criteria:**
- ✅ ADR-0011 (FlatBuffers) for serialization documented
- ✅ ADR-0012 (76 schemas) reference documented
- ✅ ADR-0013 (versioning) with 90-day deprecation specified
- ✅ Config hot-reload mechanics fully documented
- ✅ SSE listener for K0 config sync integrated

**Time Estimate:** 2-3 hours

---

### **BATCH 12: Layer 5 Connectors**

**Modules (2):** k0_bridge, model_hub_client

**What to Populate:**

1. k0_bridge (K0 Kernel Communication)
   - Imports: None (L5 foundation)
   - Exports: Batched messages to K0 kernel
   - ADRs: ADR-0001a (K0 bridge communication protocol), ADR-0022 (K0 bridge bounded batching)
   - Sub-ADRs: ADR-0001a-a (JSON + FlatBuffers dual), ADR-0022a (10-50 msgs), ADR-0022b (100ms window)
   - Features:
     - Batching: 10-50 messages per 100ms window
     - Compression: Zstd encoding
     - Ports: P01-P20 (specialized port specs)
     - Protocols: State, config, audit

2. model_hub_client (Internal Model Hub Interface)
   - Imports: None (L5 foundation)
   - Exports: LLM call interface to model_hub (L3)
   - ADRs: ADR-0001b (Model Hub architecture), ADR-0018 (model provider abstraction)
   - Sub-ADRs: ADR-0018-a (unified interface), ADR-0018-b (provider routing)
   - Interface: Unified async LLM call handler

**Deliverables:**
- Update Layer 5 "Connectors" subsection with:
  - K0 bridge communication flow diagram
  - Batching strategy (10-50 msgs / 100ms)
  - Compression + port specifications
  - Model Hub client unified interface

**Acceptance Criteria:**
- ✅ ADR-0001a (K0 bridge protocol) documented
- ✅ ADR-0022 (batching) with 10-50 msg / 100ms explicit
- ✅ Model Hub client unified interface defined
- ✅ Port specifications (P01-P20) referenced

**Time Estimate:** 2 hours

---

## PHASE 1 COMPLETION CHECKLIST

- ✅ All 52 modules have ADR references (no more "TBD")
- ✅ 12 batches completed sequentially
- ✅ Performance budgets (ADR-0024) linked to all latency-critical paths
- ✅ Layer boundary enforcement (ADR-0004b) validated for all imports
- ✅ Event bus (ADR-0004a) operational for L1→L5→L2 coordination
- ✅ ADR-0006 (3-phase orchestration) implemented + tested
- ✅ ADR-0007 (4-stage planning) implemented + tested
- ✅ ADR-0028 (WFQ scheduler) operational
- ✅ ADR-0003 validates all 6 protocols

**Total Time: 24-30 hours (spread across 4 weeks)**

---

## Phase 2-4 Roadmap (Abbreviated)

### Phase 2: External Systems (Weeks 5-8)

**Batches 13-16:** Voice I/O, LLM providers, MCP tools, storage backends

### Phase 3: K0 Bridge & Sync (Weeks 9-10)

**Batches 17-18:** K0 bridge core, multi-device sync (LAN + P2P E2EE)

### Phase 4: Testing & UX (Weeks 11-12)

**Batches 19-21:** Integration testing, E2E tests, UX polish

---

## How to Use This Roadmap

1. **Pick a batch** (e.g., Batch 1: Layer 1 Foundations)
2. **Follow the "What to Populate" section** for each module
3. **Update DEPENDENCY_MAP.md** with:
   - Exact imports/exports
   - ADR references + sub-ADRs
   - Performance budgets
   - Inter-module diagrams
4. **Verify acceptance criteria** are met
5. **Move to next batch** in sequence

---

## Quick Reference: What Each Batch Produces

| Batch | Focus | Modules | Deliverable |
|-------|-------|---------|-------------|
| 1 | L1 Input | 4 | Intent detection pipeline diagram |
| 2 | L2 Orchestration | 3 | 3-phase + 4-stage pipeline diagrams |
| 3 | L3 Agents | 6 | Agent lifecycle FSM diagram |
| 4 | L3 Model Hub | 7 | Model routing + placement ladder |
| 5 | L3 Tools/Dialogue | 9 | Three-tier sandbox + turn boundaries |
| 6 | L4 Runtime | 4 | 6-section SessionState architecture |
| 7 | L4 Learning | 4 | Feedback signals + drift detection |
| 8 | L5 Infrastructure | 7 | Scheduler + backpressure + thermal |
| 9 | L5 Safety | 3 | 3-band privacy model + HITL arbiter |
| 10 | L5 Observability | 4 | Tracing + metrics + receipts |
| 11 | L5 Configuration | 3 | Config hot-reload + schema registry |
| 12 | L5 Connectors | 2 | K0 bridge + Model Hub client |

---

## Key Success Metrics

✅ **Completeness:** 52 modules with ADR references (0% "TBD")
✅ **Consistency:** All imports follow ADR-0004b layering rules
✅ **Performance:** All latency paths reference ADR-0024 budgets
✅ **Traceability:** Every module links to at least 1 ADR
✅ **Testability:** WARD integration tests validate all 6 protocols + P95 budgets

---

**Next Step:** Start with **Batch 1: Layer 1 Foundations** when ready.
