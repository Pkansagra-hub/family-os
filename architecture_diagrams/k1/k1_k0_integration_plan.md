# K1 Intelligence Module Integration with K0 Kernel Architecture
## Comprehensive Planning Document

**Version:** 1.0  
**Date:** 2025-10-19  
**Status:** Planning - Diagram Definition Phase  
**Owner:** Architecture Team  

---

## Executive Summary

This document outlines the comprehensive plan for integrating **K1 Intelligence Module** (agentic orchestrator) with **K0 Kernel** (memory microkernel) through architecture diagrams. The plan is organized into **Epics** and **Issues**, with each issue representing a specific Mermaid diagram to be created.

**CRITICAL:** This is a **diagram-first, source-of-truth** approach. **NO implementation** will begin until all diagrams are defined, reviewed, and approved.

---

## Table of Contents

1. [Context & Architecture Foundation](#context--architecture-foundation)
2. [ADR References](#adr-references)
3. [Current State Analysis](#current-state-analysis)
4. [Integration Strategy](#integration-strategy)
5. [Epic Breakdown](#epic-breakdown)
6. [Issue Tracking](#issue-tracking)
7. [Timeline & Milestones](#timeline--milestones)
8. [Success Criteria](#success-criteria)

---

## Context & Architecture Foundation

### K0 Kernel (Memory Microkernel)
- **Purpose:** Durable memory management, policy enforcement, receipts
- **Technology:** SQLite + WAL, driver SPI
- **Ports:** P01-P20 (20 well-defined ports)
- **Diagrams:** 4 parts (project_architecture_part1-4.mmd)
- **Reference:** ADR-0001 (K0/K1 Kernel Split Architecture)

### K1 Intelligence Module (Agentic Orchestrator)
- **Purpose:** Multi-agent coordination, LLM routing, tool execution, real-time streams
- **Architecture:** 52-58 modules, 5 layers (Actor Model foundation)
- **Hybrid Design:**
  - **4 AI Agents:** Use Model Hub for LLM reasoning (Concierge, Planner, Researcher, Safety Watch)
  - **48-54 Pure Actors:** Deterministic coordination (Orchestrator, Supervisor, Router, etc.)
- **Reference:** ADR-0001, ADR-0002, ADR-0004

### Integration Points
- **K0 Bridge:** HTTP/2 + FlatBuffers communication layer
- **Ports Used:** P01 (RecallQuery), P02 (MemoryWrite), P06 (LearningTick), P07 (Sync), P08 (ConfigSSE), P10 (PII), P12 (PolicyEval), P17 (ResourceAlloc), P18 (Personalization), P19 (QoS), P20 (Procedures)
- **Reference:** ADR-0001a (K0 Bridge Communication Protocol)

---

## ADR References

### Core Architecture ADRs

| ADR | Title | Relevance to K1-K0 Integration |
|-----|-------|-------------------------------|
| **0001** | K0/K1 Kernel Split Architecture | 🔴 **CRITICAL** - Defines dual-kernel design, K0 Bridge, ports P01-P20 |
| **0001a** | K0 Bridge Communication Protocol | 🔴 **CRITICAL** - HTTP/2 + FlatBuffers, batching, backpressure |
| **0001b** | Model Hub Architecture & LLM Integration | 🟡 **IMPORTANT** - How K1 AI agents use LLMs via Model Hub |
| **0001e** | P21+ Integration Pipeline Layer | 🟢 **RELEVANT** - Future pipeline extensions |
| **0001f** | State Boundary Management (K1 vs K0) | 🔴 **CRITICAL** - K1 SessionState vs K0 persistent storage |
| **0004** | 52-Module 5-Layer Architecture | 🔴 **CRITICAL** - K1 module structure, Layer 3 Model Hub, Layer 5 K0 Bridge |
| **0004a** | Layer 1-2 Event Bus Communication | 🟡 **IMPORTANT** - K1 internal event routing |
| **0004b** | Module Dependency Management | 🟢 **RELEVANT** - K1 import linting |
| **0004c** | Module README Template | 🟢 **RELEVANT** - Documentation standards |
| **0004d** | Per-Layer Integration Testing | 🟡 **IMPORTANT** - K1 testing strategy |
| **0050** | Multi-Device Family Sync Strategy | 🔴 **CRITICAL** - Device-to-device CRDT sync via K0 P07 |
| **0050a** | SessionState Coherence Guarantees | 🟡 **IMPORTANT** - Per-device coherence, K1 SessionState |
| **0050b** | CRDT Device-to-Device Merge Protocol | 🟡 **IMPORTANT** - Conflict resolution via K0 |
| **0050c** | LAN-First Sync Implementation | 🟢 **RELEVANT** - mDNS discovery, TCP P07 |
| **0050d** | P2P E2EE Internet Sync | 🟢 **RELEVANT** - Phase 2 internet sync |

### Additional ADRs to Review

| Category | ADRs | Focus Area |
|----------|------|------------|
| **Agent Lifecycle** | 0005, 0005a-e | Agent FSM, WARMING, IDLE, DRAINING, Supervisor |
| **Orchestration** | 0006, 0006a-e | 3-Phase (Negotiation, Selection, Execution) |
| **Planning** | 0007, 0007a-d | 4-Stage Pipeline (Sketch, Expand, Validate, Commit) |
| **Error Recovery** | 0008, 0008a-d, 0009, 0009a-c | Saga Pattern, Circuit Breaker |
| **Security** | 0010, 0010a-d, 0032-0038 | Capabilities, Egress Rules, PII, E2EE |
| **Serialization** | 0011-0016 | FlatBuffers (76 schemas), WebSocket, SSE |
| **SessionState** | 0017-0023 | 6 sections, 3-tier eviction, K0 WAL integration |
| **Performance** | 0024-0031 | Budgets (TTFT <150ms), KV Cache, Thermal, Metrics |

---

## Current State Analysis

### K0 Kernel Diagrams (Existing)

| Diagram | Location | Status | Coverage |
|---------|----------|--------|----------|
| **Part 1** | `k0/architecture_diagrams/project_architecture_part1.mmd` | ✅ Complete | Memory Core, Family Memory Network, API Servants, Cognitive Orchestration |
| **Part 2** | `k0/architecture_diagrams/project_architecture_part2.mmd` | ✅ Complete | Pipelines P01-P20, Policy Framework, Events Bus |
| **Part 3** | `k0/architecture_diagrams/project_architecture_part3.mmd` | ✅ Complete | Storage Infrastructure, K0 Drivers, WAL/Offsets/DLQ |
| **Part 4** | `k0/architecture_diagrams/project_architecture_part4.mmd` | ✅ Complete | Device-Local Memory, CRDT Sync, Family Graph |

### K1 Intelligence Module Diagrams (Missing - TO BE CREATED)

| K1 Component | Integration Point | Diagram Status | Epic |
|--------------|-------------------|----------------|------|
| **Agent Fabric** (Layer 1) | K0 P02 (agent state), P17 (resources) | ❌ Missing | Epic 1 |
| **Orchestrator Core** (Layer 2) | K0 P04 (decisions), P02 (assignments) | ❌ Missing | Epic 2 |
| **Planner Agent** (Layer 2) | K0 P02 (plans), P01 (context) | ❌ Missing | Epic 3 |
| **Model Hub** (Layer 3) | K0 P18 (personalization), P17 (budgets) | ❌ Missing | Epic 4 |
| **Tool Runner** (Layer 3) | K0 P10 (PII), P20 (procedures) | ❌ Missing | Epic 5 |
| **SessionState** (Layer 4) | K0 P02 (deltas), P07 (sync) | ❌ Missing | Epic 6 |
| **Learning Loop** (Layer 4) | K0 P06 (feedback), P17 (QoS) | ❌ Missing | Epic 7 |
| **K0 Bridge** (Layer 5) | K0 Ports P01-P20 | ❌ Missing | Epic 8 |
| **Infrastructure** (Layer 5) | K0 P08 (config), P19 (rate limits) | ❌ Missing | Epic 9 |

---

## Integration Strategy

### Approach: Diagram-First Source of Truth

```
Phase 1: Diagram Definition (Weeks 1-6)
├─ Epic 1-9: Create integration diagrams
├─ Review cycles: Architecture team approval
└─ Output: Complete K1-K0 integration architecture

Phase 2: Contract Definition (Weeks 7-8)
├─ FlatBuffers schemas (76 total)
├─ Port specifications (P01-P20)
└─ Output: API contracts, validation rules

Phase 3: Implementation (Weeks 9-20)
├─ Layer 5 (Infrastructure, K0 Bridge)
├─ Layer 4 (Runtime, SessionState)
├─ Layer 3 (Execution, Agents, Model Hub)
├─ Layer 2 (Orchestration, Planner)
└─ Layer 1 (Input Processing)

Phase 4: Integration Testing (Weeks 21-24)
├─ Per-layer integration tests
├─ End-to-end K1↔K0 tests
└─ Performance validation (TTFT <150ms)
```

### Diagram Creation Principles

1. **Mermaid-First:** All diagrams in `.mmd` format (version-controllable)
2. **Layered Detail:** High-level overview + detailed component diagrams
3. **Port-Centric:** Show K0 port usage explicitly
4. **Actor Model:** Visualize mailboxes, supervision trees
5. **AI Integration:** Distinguish AI agents (🤖) vs pure actors (⚡)
6. **Performance Budget:** Annotate latency targets on diagrams
7. **FlatBuffers Schema:** Link to schema definitions

---

## Epic Breakdown

### Epic 1: Agent Fabric Integration with K0
**Goal:** Define how K1 Agent Fabric (Layer 1) uses K0 for agent lifecycle state persistence

**ADR Context:** ADR-0005 (Agent Lifecycle FSM), ADR-0002 (Actor Model)

**K0 Ports Used:**
- **P02 (MemoryWrite):** Agent state transitions (PENDING → WARMING → ACTIVE → IDLE → DRAINING → TERMINATED)
- **P17 (ResourceAllocation):** Agent resource budgets (memory, compute)
- **P07 (Sync):** Multi-device agent roster sync

**Issues (Diagrams to Create):**

| Issue | Diagram | Description | Estimated Effort |
|-------|---------|-------------|------------------|
| K1-001 | `k1_agent_lifecycle_k0_integration.mmd` | Agent FSM with K0 state persistence (6 states × K0 writes) | 3 days |
| K1-002 | `k1_supervisor_k0_monitoring.mmd` | Supervisor health checks → K0 metrics (1Hz checks, crash detection) | 2 days |
| K1-003 | `k1_agent_roster_crdt_sync.mmd` | Active agent roster sync via K0 P07 (multi-device) | 4 days |
| K1-004 | `k1_agent_blacklist_k0_storage.mmd` | Agent blacklist persistence (crash threshold, time windows) | 2 days |

**Success Criteria:**
- ✅ All 6 agent states persist to K0 via P02
- ✅ Supervisor can query agent health from K0
- ✅ Multi-device agent roster syncs <50ms via CRDT
- ✅ Blacklist survives K1 restart (K0 WAL recovery)

---

### Epic 2: Orchestrator Core Integration with K0
**Goal:** Define how K1 Orchestrator (Layer 2) uses K0 for task coordination and decision logging

**ADR Context:** ADR-0006 (3-Phase Orchestration), ADR-0001 (K0/K1 Split)

**K0 Ports Used:**
- **P04 (Arbitration/Action):** Decision logging (task assignments, agent selection)
- **P02 (MemoryWrite):** Orchestration state (negotiation results, execution status)
- **P01 (RecallQuery):** Context retrieval for task routing

**Issues (Diagrams to Create):**

| Issue | Diagram | Description | Estimated Effort |
|-------|---------|-------------|------------------|
| K1-005 | `k1_orchestrator_3phase_k0.mmd` | 3-phase flow: Negotiation → Selection → Execution with K0 logging | 5 days |
| K1-006 | `k1_contract_net_k0_proposals.mmd` | Contract Net Protocol proposal storage in K0 | 3 days |
| K1-007 | `k1_task_dag_k0_tracking.mmd` | Parallel DAG execution state in K0 (dependencies, completion) | 4 days |
| K1-008 | `k1_orchestrator_k0_recovery.mmd` | Orchestrator crash recovery from K0 WAL | 3 days |

**Success Criteria:**
- ✅ All 3 phases persist to K0 (negotiation, selection, execution)
- ✅ Task DAG state recoverable from K0 after K1 crash
- ✅ Proposal history queryable for learning loop
- ✅ Multi-device orchestration via K0 CRDT sync

---

### Epic 3: Planner Agent Integration with K0
**Goal:** Define how K1 Planner (AI Agent, Layer 2) uses K0 for plan storage and context retrieval

**ADR Context:** ADR-0007 (4-Stage Planning Pipeline), ADR-0001b (Model Hub LLM Integration)

**K0 Ports Used:**
- **P02 (MemoryWrite):** Plan commits (4-stage pipeline output)
- **P01 (RecallQuery):** Context retrieval for planning (episodic memory, user preferences)
- **P18 (Personalization):** User persona for prompt templates

**Issues (Diagrams to Create):**

| Issue | Diagram | Description | Estimated Effort |
|-------|---------|-------------|------------------|
| K1-009 | `k1_planner_4stage_k0.mmd` | 4-stage pipeline (Sketch → Expand → Validate → Commit) with K0 integration | 5 days |
| K1-010 | `k1_planner_sketch_llm_k0_context.mmd` | LLM sketch stage using K0 P01 for context (episodic recall) | 4 days |
| K1-011 | `k1_planner_validation_k0_arbiter.mmd` | Validation stage with K0 P12 policy checks (arbiter approval) | 3 days |
| K1-012 | `k1_planner_commit_k0_wal.mmd` | Plan commit to K0 WAL (exactly-once semantics) | 3 days |

**Success Criteria:**
- ✅ All 4 planning stages integrated with K0
- ✅ Planner AI agent uses K0 P01 for context retrieval (<50ms)
- ✅ Plans persist to K0 with receipts (auditability)
- ✅ Multi-device plan sync via K0 P07 CRDT

---

### Epic 4: Model Hub Integration with K0
**Goal:** Define how K1 Model Hub (AI Integration Layer, Layer 3) uses K0 for persona, budgets, and learning

**ADR Context:** ADR-0001b (Model Hub Architecture), ADR-0004 (Layer 3 Execution)

**K0 Ports Used:**
- **P18 (Personalization):** User persona state (traits, style, adaptations)
- **P17 (ResourceAllocation):** LLM budget tracking (tokens, dollars, compute)
- **P06 (LearningTick):** Model performance feedback (LLM routing decisions)

**Issues (Diagrams to Create):**

| Issue | Diagram | Description | Estimated Effort |
|-------|---------|-------------|------------------|
| K1-013 | `k1_model_hub_router_k0.mmd` | Model Hub request routing with K0 P18 persona retrieval | 4 days |
| K1-014 | `k1_placement_planner_k0_thermal.mmd` | NPU/GPU/CPU placement with K0 thermal state (P17 resource tracking) | 5 days |
| K1-015 | `k1_kv_cache_k0_eviction.mmd` | KV cache management with K0 session state (75% hit rate target) | 4 days |
| K1-016 | `k1_prompt_library_k0_persona.mmd` | Prompt template selection using K0 P18 personalization | 3 days |
| K1-017 | `k1_model_hub_fallback_k0.mmd` | Model fallback cascade with K0 P17 budget enforcement | 3 days |

**Success Criteria:**
- ✅ Model Hub uses K0 P18 for persona-driven prompt selection
- ✅ LLM budget tracking via K0 P17 (token/cost accounting)
- ✅ KV cache eviction coordinated with K0 SessionState
- ✅ Model fallback cascade respects K0 budget limits

---

### Epic 5: Tool Runner Integration with K0
**Goal:** Define how K1 Tool Runner (Layer 3) uses K0 for PII detection, procedure storage, and audit trails

**ADR Context:** ADR-0033 (Tool Execution Architecture), ADR-0034 (MCP Protocol)

**K0 Ports Used:**
- **P10 (Privacy/PII):** PII detection before tool execution
- **P20 (Procedures/Habits):** Procedure/habit storage and execution
- **P04 (Arbitration):** Tool execution decision logging

**Issues (Diagrams to Create):**

| Issue | Diagram | Description | Estimated Effort |
|-------|---------|-------------|------------------|
| K1-018 | `k1_tool_runner_mcp_k0.mmd` | MCP tool execution with K0 P10 PII redaction | 4 days |
| K1-019 | `k1_sandbox_k0_egress.mmd` | Tool sandbox egress rules via K0 policy (GREEN/AMBER/RED bands) | 3 days |
| K1-020 | `k1_tool_registry_k0_storage.mmd` | Tool catalog persistence in K0 (JSON specs) | 2 days |
| K1-021 | `k1_procedures_k0_p20.mmd` | Procedure/habit execution flow with K0 P20 bidirectional sync | 4 days |

**Success Criteria:**
- ✅ All tool calls pass K0 P10 PII detection
- ✅ Tool sandbox respects K0 privacy bands (egress rules)
- ✅ Procedures stored in K0, executed by K1 Flow Engine
- ✅ Tool execution audit trail in K0 receipts

---

### Epic 6: SessionState Integration with K0
**Goal:** Define how K1 SessionState (Layer 4) syncs with K0 for persistence, CRDT merge, and eviction

**ADR Context:** ADR-0017 (SessionState 6-Section Design), ADR-0019 (FlatBuffers Serialization), ADR-0050 (Multi-Device Sync)

**K0 Ports Used:**
- **P02 (MemoryWrite):** SessionState delta serialization
- **P07 (Sync):** CRDT merge for multi-device SessionState
- **P01 (RecallQuery):** SessionState recovery from K0 WAL

**Issues (Diagrams to Create):**

| Issue | Diagram | Description | Estimated Effort |
|-------|---------|-------------|------------------|
| K1-022 | `k1_sessionstate_6section_k0.mmd` | 6-section SessionState (Beliefs, Scoreboard, Control, Persona, Multimodal, Meta) with K0 sync | 5 days |
| K1-023 | `k1_sessionstate_delta_k0_batching.mmd` | Delta serialization + K0 Bridge batching (250ms flush) | 4 days |
| K1-024 | `k1_sessionstate_eviction_k0.mmd` | 3-tier eviction (64KB soft → 128KB hard → 256KB OOM) with K0 checkpoints | 4 days |
| K1-025 | `k1_sessionstate_crdt_k0_p07.mmd` | Multi-device CRDT merge via K0 P07 (LWW conflict resolution) | 5 days |

**Success Criteria:**
- ✅ All 6 SessionState sections persist to K0 via P02
- ✅ Delta serialization <1ms (FlatBuffers)
- ✅ 3-tier eviction triggers K0 checkpoints
- ✅ Multi-device SessionState sync via K0 P07 CRDT

---

### Epic 7: Learning Loop Integration with K0
**Goal:** Define how K1 Learning Loop (Layer 4) uses K0 for feedback storage, drift detection, and model updates

**ADR Context:** ADR-0059 (Learning Loop Framework), ADR-0006 (Orchestration)

**K0 Ports Used:**
- **P06 (LearningTick):** Feedback signals (explicit 1.0, implicit 0.5, behavioral 0.2)
- **P17 (QoS/Cost):** Performance metrics for drift detection
- **P08 (ConfigSSE):** Model weight updates via SSE hot reload

**Issues (Diagrams to Create):**

| Issue | Diagram | Description | Estimated Effort |
|-------|---------|-------------|------------------|
| K1-026 | `k1_learning_loop_feedback_k0.mmd` | Feedback collection → K0 P06 storage (explicit/implicit/behavioral) | 4 days |
| K1-027 | `k1_drift_detector_k0_metrics.mmd` | Drift detection using K0 P17 performance metrics (success rate drop >20%) | 3 days |
| K1-028 | `k1_model_updater_k0_config.mmd` | Model weight updates → K0 P08 SSE → K1 Config Manager hot reload | 4 days |
| K1-029 | `k1_learning_loop_audit_k0.mmd` | Learning loop audit trail in K0 receipts (parameter changes, rollback) | 3 days |

**Success Criteria:**
- ✅ All feedback signals persist to K0 via P06
- ✅ Drift detection uses K0 metrics (20% threshold)
- ✅ Model updates propagate via K0 P08 SSE (<100ms)
- ✅ Learning loop changes auditable via K0 receipts

---

### Epic 8: K0 Bridge Integration Architecture
**Goal:** Define K0 Bridge as the central communication layer between K1 and K0 (Layer 5)

**ADR Context:** ADR-0001a (K0 Bridge Communication Protocol), ADR-0001 (K0/K1 Split)

**K0 Ports Used:**
- **ALL P01-P20:** Bridge is the interface to all K0 ports
- **Batching:** 250ms flush, 64KB batching, zstd compression
- **Backpressure:** Circuit breaker (3 failures → open)

**Issues (Diagrams to Create):**

| Issue | Diagram | Description | Estimated Effort |
|-------|---------|-------------|------------------|
| K1-030 | `k1_k0_bridge_architecture.mmd` | K0 Bridge overview (HTTP/2, FlatBuffers, batching, compression) | 5 days |
| K1-031 | `k1_k0_bridge_batching_flow.mmd` | Batching algorithm (250ms flush, 64KB limit) with backpressure | 4 days |
| K1-032 | `k1_k0_bridge_circuit_breaker.mmd` | Circuit breaker FSM (CLOSED → OPEN → HALF_OPEN) | 3 days |
| K1-033 | `k1_k0_bridge_port_routing.mmd` | Port routing (P01-P20) with FlatBuffers schema mapping | 4 days |
| K1-034 | `k1_k0_bridge_observability.mmd` | Bridge metrics (batch size, compression ratio, latency) | 3 days |

**Success Criteria:**
- ✅ All K1→K0 communication via K0 Bridge
- ✅ Batching overhead <5% latency
- ✅ Circuit breaker prevents K0 overload
- ✅ Bridge latency <10ms P95

---

### Epic 9: Infrastructure Integration with K0
**Goal:** Define how K1 Infrastructure (Layer 5) uses K0 for config, rate limits, and observability

**ADR Context:** ADR-0004 (Layer 5 Infrastructure), ADR-0080 (Config Hot-Reload)

**K0 Ports Used:**
- **P08 (ConfigSSE):** Hot config updates via SSE
- **P19 (QoS/Rate Limiting):** Rate limit enforcement
- **P17 (QoS/Cost):** Resource governance

**Issues (Diagrams to Create):**

| Issue | Diagram | Description | Estimated Effort |
|-------|---------|-------------|------------------|
| K1-035 | `k1_config_manager_k0_sse.mmd` | Config Manager hot reload via K0 P08 SSE (<100ms) | 3 days |
| K1-036 | `k1_scheduler_k0_qos.mmd` | WFQ scheduler with K0 P17 resource budgets | 4 days |
| K1-037 | `k1_backpressure_k0_watermarks.mmd` | 3-tier backpressure with K0 P19 rate limits | 4 days |
| K1-038 | `k1_thermal_k0_placement.mmd` | Thermal manager with K0 P17 for model placement | 3 days |
| K1-039 | `k1_observability_k0_receipts.mmd` | K1 metrics aggregation → K0 receipts (audit trail) | 3 days |

**Success Criteria:**
- ✅ Config hot reload via K0 P08 (<100ms)
- ✅ Scheduler uses K0 P17 for budget enforcement
- ✅ Backpressure cascade integrated with K0 watermarks
- ✅ All K1 operations emit K0 receipts

---

## Issue Tracking

### Total Issue Count
- **39 diagrams** across 9 epics
- **Estimated effort:** ~135 days (27 weeks with 1 person, 13.5 weeks with 2 people, ~7 weeks with 4 people)

### Issue Priority Matrix

| Priority | Epic | Issue Count | Rationale |
|----------|------|-------------|-----------|
| **P0 (Critical)** | Epic 8 (K0 Bridge) | 5 | Foundation for all K1↔K0 communication |
| **P0 (Critical)** | Epic 6 (SessionState) | 4 | Core state management, multi-device sync |
| **P1 (High)** | Epic 2 (Orchestrator) | 4 | Central coordination, task execution |
| **P1 (High)** | Epic 3 (Planner) | 4 | AI planning, LLM integration |
| **P2 (Medium)** | Epic 1 (Agent Fabric) | 4 | Agent lifecycle, supervisor monitoring |
| **P2 (Medium)** | Epic 4 (Model Hub) | 5 | AI integration infrastructure |
| **P3 (Low)** | Epic 5 (Tool Runner) | 4 | Tool execution, PII detection |
| **P3 (Low)** | Epic 7 (Learning Loop) | 4 | Adaptive learning, feedback |
| **P3 (Low)** | Epic 9 (Infrastructure) | 5 | Config, scheduler, observability |

### Recommended Sequencing

**Week 1-2:** Epic 8 (K0 Bridge) - Foundation  
**Week 3-4:** Epic 6 (SessionState) - State management  
**Week 5-6:** Epic 2 (Orchestrator) + Epic 3 (Planner) - Coordination  
**Week 7-8:** Epic 1 (Agent Fabric) + Epic 4 (Model Hub) - Execution  
**Week 9-10:** Epic 5 (Tool Runner) + Epic 7 (Learning Loop) + Epic 9 (Infrastructure) - Supporting systems  

---

## Timeline & Milestones

### Phase 1: Diagram Definition (Weeks 1-10)

| Milestone | Week | Deliverables | Success Criteria |
|-----------|------|--------------|------------------|
| **M1: Foundation** | Week 2 | Epic 8 (K0 Bridge) complete | 5 diagrams approved, all ports defined |
| **M2: Core State** | Week 4 | Epic 6 (SessionState) complete | 4 diagrams approved, CRDT sync flow validated |
| **M3: Coordination** | Week 6 | Epic 2 (Orchestrator) + Epic 3 (Planner) | 8 diagrams approved, 3-phase + 4-stage flows defined |
| **M4: Execution** | Week 8 | Epic 1 (Agent Fabric) + Epic 4 (Model Hub) | 9 diagrams approved, AI agent integration clear |
| **M5: Complete** | Week 10 | All 9 epics complete | 39 diagrams approved, ready for contract definition |

### Phase 2: Contract Definition (Weeks 11-12)

| Milestone | Week | Deliverables | Success Criteria |
|-----------|------|--------------|------------------|
| **M6: FlatBuffers Schemas** | Week 11 | 76 schemas defined | All K1↔K0 messages schema-validated |
| **M7: Port Specifications** | Week 12 | P01-P20 contracts | All ports documented with examples |

### Phase 3: Implementation (Weeks 13-32)

| Milestone | Week | Deliverables | Success Criteria |
|-----------|------|--------------|------------------|
| **M8: Layer 5** | Week 15 | K0 Bridge + Infrastructure implemented | Bridge latency <10ms P95 |
| **M9: Layer 4** | Week 18 | SessionState + Learning Loop | SessionState serialize <1ms |
| **M10: Layer 3** | Week 24 | Agents + Model Hub + Tools | Agent spawn <45ms, LLM call <50ms |
| **M11: Layer 2** | Week 28 | Orchestrator + Planner | 3-phase + 4-stage pipelines working |
| **M12: Layer 1** | Week 30 | Input Processing | Intent classification <5ms |
| **M13: Integration** | Week 32 | End-to-end K1↔K0 | TTFT <150ms P95 |

### Phase 4: Testing & Validation (Weeks 33-36)

| Milestone | Week | Deliverables | Success Criteria |
|-----------|------|--------------|------------------|
| **M14: Unit Tests** | Week 33 | 91% coverage | All 58 modules tested |
| **M15: Integration Tests** | Week 34 | Per-layer tests | All 5 layers integrated |
| **M16: E2E Tests** | Week 35 | Full turn tests | TTFT <150ms, E2E <2000ms |
| **M17: Performance** | Week 36 | Performance validation | All budgets met (ADR-0024) |

---

## Success Criteria

### Diagram Quality Standards

**Each diagram must include:**
- ✅ Mermaid-compatible syntax (`.mmd` format)
- ✅ Clear component boundaries (K1 modules, K0 ports)
- ✅ Port usage annotations (P01-P20 references)
- ✅ Latency budgets (where applicable)
- ✅ FlatBuffers schema references
- ✅ Actor Model mailboxes (where applicable)
- ✅ AI agent vs pure actor distinction (🤖 vs ⚡)
- ✅ CRDT merge points (for multi-device sync)
- ✅ Error handling paths (circuit breakers, retries)
- ✅ Observability hooks (metrics, traces, receipts)

### Architecture Review Checklist

**Before diagram approval:**
- [ ] ADR references correct and complete
- [ ] K0 port usage validated (P01-P20)
- [ ] FlatBuffers schemas defined
- [ ] Performance budgets annotated
- [ ] Actor Model patterns verified
- [ ] AI agent integration clarified
- [ ] Multi-device sync considered
- [ ] Security/privacy implications reviewed
- [ ] Observability strategy defined
- [ ] Test strategy outlined

### Implementation Readiness

**Diagrams are ready for implementation when:**
- ✅ All 39 diagrams created and approved
- ✅ FlatBuffers schemas (76 total) defined
- ✅ Port contracts (P01-P20) documented
- ✅ Cross-references validated (ADRs, contracts, diagrams)
- ✅ Team trained on architecture
- ✅ Tooling ready (MCP servers, validation tools)

---

## Appendices

### Appendix A: Diagram Template

```mermaid
---
config:
  flowchart:
    htmlLabels: true
    curve: linear
  theme: neo
  layout: elk
---
flowchart TB

%% ====== [DIAGRAM NAME] ======
%% PURPOSE: [Clear statement of what this diagram shows]
%% CONTEXT: [ADR references, K0 ports used]
%% LAYERS: [K1 layers involved]

%% ====== STYLE DEFINITIONS ======
classDef k1_layer1 fill:#eef7ff,stroke:#2a6ebb,stroke-width:2px
classDef k1_layer2 fill:#f8fff0,stroke:#6b8e23,stroke-width:2px
classDef k1_layer3 fill:#fff7e6,stroke:#d48806,stroke-width:2px
classDef k1_layer4 fill:#f3f8ff,stroke:#1f4aa1,stroke-width:2px
classDef k1_layer5 fill:#f0f0f0,stroke:#666,stroke-width:2px
classDef k0_kernel fill:#fffdf0,stroke:#b38b00,stroke-width:3px
classDef ai_agent fill:#f9f0ff,stroke:#722ed1,stroke-width:2px
classDef pure_actor fill:#e6ffe6,stroke:#00cc00,stroke-width:2px

%% ====== COMPONENTS ======
%% [Define K1 components, K0 ports, connections]

%% ====== FLOW ANNOTATIONS ======
%% [Annotate with latency, schema, ADR references]
```

### Appendix B: FlatBuffers Schema Reference

**76 Total Schemas (from ADR-0012):**

| Layer | Schema Count | Examples |
|-------|--------------|----------|
| **Layer 1 (Kernel)** | 15 | Agent, Task, Protocol, Proposal, Assignment |
| **Layer 2 (State)** | 18 | SessionState, Receipt, GroundingCommit, StateDelta |
| **Layer 3 (Execution)** | 16 | ToolCall, MCPRequest, ModelRequest, Sandbox |
| **Layer 4 (Ingress)** | 14 | WebSocketMessage, VoiceFrame, BargeinEvent |
| **Layer 5 (Infrastructure)** | 13 | ConfigUpdate, Metric, TraceSpan, Thermal |

### Appendix C: K0 Port Quick Reference

| Port | Name | Direction | Latency Budget | Used By (K1 Modules) |
|------|------|-----------|----------------|----------------------|
| **P01** | RecallQuery | K1 → K0 | <50ms | Planner, Concierge, Context Builder |
| **P02** | MemoryWrite | K1 → K0 | <100ms | SessionState, Planner, Orchestrator, Agent Fabric |
| **P04** | Arbitration | K1 → K0 | <250ms | Orchestrator, Arbiter, Tool Runner |
| **P06** | LearningTick | K1 → K0 | Async | Learning Loop, Drift Detector |
| **P07** | Sync | K0 ↔ K1 | <50ms (LAN) | SessionState CRDT, Agent Roster |
| **P08** | ConfigSSE | K0 → K1 | <100ms | Config Manager |
| **P10** | PIIDetection | K1 → K0 | <10ms | Tool Runner, Safety Watch |
| **P12** | PolicyEval | K1 → K0 | <20ms | Planner Validator, Arbiter |
| **P17** | ResourceAlloc | K1 ↔ K0 | <10ms | Model Hub, Scheduler, Supervisor |
| **P18** | Personalization | K0 → K1 | <20ms | Model Hub, Prompt Library |
| **P19** | QoS | K1 → K0 | <5ms | Rate Limiter, Scheduler |
| **P20** | Procedures | K0 ↔ K1 | <100ms | Flow Engine, Tool Runner |

---

## Next Steps

### Immediate Actions (Week 1)

1. **Review this plan** with Architecture Team
2. **Assign diagram owners** (2-4 people recommended)
3. **Set up diagram tooling** (Mermaid Live Editor, VS Code extensions)
4. **Create first diagram** (K1-030: K0 Bridge Architecture)
5. **Establish review cadence** (2 diagrams per week target)

### Weekly Cadence

**Monday:**
- Diagram planning session (2h)
- Assign 2 diagrams for the week

**Wednesday:**
- Draft review (1h)
- Feedback and iteration

**Friday:**
- Final review (1h)
- Architecture team approval
- Commit diagrams to repository

### Communication

**Slack Channel:** `#k1-k0-integration-diagrams`  
**Meeting:** Weekly sync (Fridays 2-3pm)  
**Documentation:** Update this plan weekly with progress  

---

## Document Control

**Version:** 1.0  
**Last Updated:** 2025-10-19  
**Approved By:** [Pending]  
**Next Review:** 2025-10-26 (weekly)  

**Change Log:**
- 2025-10-19: Initial version created (39 diagram issues across 9 epics)

---

**END OF PLANNING DOCUMENT**
