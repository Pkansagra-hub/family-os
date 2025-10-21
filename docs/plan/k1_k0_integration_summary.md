# K1-K0 Integration: Things We Need To Do

**Document Type:** Executive Summary & Checklist  
**Status:** Planning Phase  
**Date:** 2025-10-19  
**Owner:** Architecture Team  

---

## Document Purpose

This document provides a high-level overview of all tasks required to integrate K1 Intelligence Module with K0 Kernel, derived from:
- **ADR-0001** (K0/K1 Kernel Split) & sub-ADRs (0001a-f)
- **ADR-0004** (52-Module 5-Layer Architecture) & sub-ADRs (0004a-d)
- **ADR-0050** (Multi-Device Sync) & sub-ADRs (0050a-d)
- **K0 Phase 2 Mermaid Diagrams** (8 diagrams in `architecture_diagrams/k0/`)

**Full Details:** See `K1_K0_INTEGRATION_PLANNING.md` for complete epic/issue breakdown

---

## Summary: 10 Epics, 50+ Issues, 14 Weeks

| Epic | Issues | Weeks | Priority | Complexity |
|------|--------|-------|----------|------------|
| **Epic 1: K0 Bridge Communication** | 5 | 4 weeks | 🔴 CRITICAL | HIGH |
| **Epic 2: Agent Fabric Integration** | 5 | 4 weeks | 🔴 CRITICAL | HIGH |
| **Epic 3: Orchestrator Integration** | 5 | 3 weeks | 🟡 HIGH | MEDIUM |
| **Epic 4: Planner Integration** | 5 | 3 weeks | 🟡 HIGH | MEDIUM |
| **Epic 5: Model Hub Integration** | 5 | 3 weeks | 🟡 HIGH | MEDIUM |
| **Epic 6: SessionState Integration** | 5 | 3 weeks | 🟡 HIGH | MEDIUM |
| **Epic 7: Learning Loop Integration** | 5 | 3 weeks | 🟢 MEDIUM | MEDIUM |
| **Epic 8: Performance Budgets** | 5 | 3 weeks | 🟡 HIGH | HIGH |
| **Epic 9: Multi-Device Sync** | 5 | 4 weeks | 🔴 CRITICAL | HIGH |
| **Epic 10: Observability Integration** | 5 | 3 weeks | 🟢 MEDIUM | LOW |
| **TOTAL** | **50** | **14 weeks** (parallel) | | |

---

## Epic 1: K0 Bridge Communication Protocol 🔴

**ADR Reference:** ADR-0001a (K0 Bridge Communication Protocol)

**Goal:** Implement dual protocol (JSON + FlatBuffers) for K0 ↔ K1 communication with <10ms P95 latency

**Why Critical:** Foundation for ALL K0 ↔ K1 communication. Blocks every other epic.

### Issues:

1. **Issue 1.1: FlatBuffers Schema Implementation (76 schemas)**
   - Generate Layer 1-5 schemas (15+18+16+14+13)
   - Python bindings in `k1/contracts/flatbuffers/`
   - Schema version registry & compatibility tests
   - **Target:** <1ms serialization/deserialization
   - **ADR:** ADR-0011, ADR-0012
   - **Effort:** 2 weeks

2. **Issue 1.2: HTTP/2 Batching & Compression**
   - Batching algorithm (250ms or 64KB limit)
   - HTTP/2 multiplexing
   - Zstd level 3 compression (>4:1 ratio)
   - Backpressure cascade (K0 >80% full)
   - **Target:** <10ms bridge latency P95
   - **ADR:** ADR-0022
   - **Effort:** 3 weeks

3. **Issue 1.3: Circuit Breaker & Backpressure**
   - 3-state FSM (CLOSED → OPEN → HALF_OPEN)
   - Per-port config (P01-P20)
   - Failure threshold (3 failures → open)
   - Prometheus metrics & alerts
   - **ADR:** ADR-0009
   - **Effort:** 2 weeks

4. **Issue 1.4: Idempotency Ledger Integration**
   - UUID v7 request IDs in K1
   - K0 duplicate detection (<5s window)
   - Ledger cleanup (30-day retention)
   - **Target:** 100% exactly-once guarantee
   - **Effort:** 1 week

5. **Issue 1.5: Observability (trace_id propagation)**
   - cognitive_trace_id generation in K1
   - Propagate in all FlatBuffers messages
   - OpenTelemetry spans (K1 → K0 bridge call)
   - Jaeger integration
   - **Target:** <1ms overhead
   - **ADR:** ADR-0029, ADR-0030
   - **Effort:** 1 week

**Diagram Updates:**
- `project_architecture_part1.mmd`: K0_KERNEL, K0_BUS, evt_types, SHARED_IDEMPOTENCY
- `k0_comprehensive_architecture.mmd`: K0_PORTS, K0_DRIVERS

---

## Epic 2: Agent Fabric Integration 🔴

**ADR Reference:** ADR-0002 (Actor Model), ADR-0005 (Agent Lifecycle FSM)

**Goal:** Integrate K1 Agent Fabric with K0 for agent state persistence and recovery

**Why Critical:** Agents are core to K1 intelligence. Required for orchestration.

### Issues:

1. **Issue 2.1: Agent Lifecycle FSM (6 states)**
   - PENDING → WARMING → ACTIVE → IDLE → DRAINING → TERMINATED
   - State transitions with K0 persistence
   - Recovery on K1 restart (WAL replay)
   - Blacklist (3 crashes → disabled)
   - **Target:** <45ms agent spawn, <5s crash recovery
   - **ADR:** ADR-0005, ADR-0005a-d
   - **Effort:** 3 weeks

2. **Issue 2.2: Mailbox MPSC Queue Implementation**
   - Lock-free MPSC ring buffer (1024 slots)
   - Priority messages (urgent, normal, background)
   - Dead letter queue (DLQ)
   - Prometheus metrics (queue depth, throughput)
   - **Target:** <100ns producer enqueue
   - **ADR:** ADR-0002a
   - **Effort:** 2 weeks

3. **Issue 2.3: Supervisor Monitoring & Crash Recovery**
   - Supervisor actor (1Hz health checks)
   - Crash detection (<5s)
   - Automatic restart (exponential backoff)
   - Crash logging to K0
   - **ADR:** ADR-0002b
   - **Effort:** 2 weeks

4. **Issue 2.4: Agent Hire/Fire via K0 Ports**
   - Hire workflow (orchestrator → supervisor → spawn)
   - Fire workflow (draining → terminated)
   - State persistence (P02 MemoryWrite)
   - Recovery rehires active agents
   - **Target:** <50ms hire, <5s fire
   - **Effort:** 2 weeks

5. **Issue 2.5: Personality & Capability System**
   - Persona prompt library (Jinja2 templates)
   - Capability tokens (unforgeable, lease-based)
   - Runtime capability enforcement
   - Capability revocation & audit trail
   - **ADR:** ADR-0005e, ADR-0010
   - **Effort:** 2 weeks

**Diagram Updates:**
- `project_architecture_part1.mmd`: Agent_Fabric
- `project_architecture_part2.mmd`: FSM, supervisor tree

---

## Epic 3: Orchestrator Integration 🟡

**ADR Reference:** ADR-0006 (3-Phase Orchestration - Contract Net)

**Goal:** Implement Contract Net Protocol for multi-agent coordination

### Issues:

1. **Issue 3.1: 3-Phase Coordination (Negotiation → Selection → Execution)**
2. **Issue 3.2: Multi-Criteria Proposal Scoring**
3. **Issue 3.3: Parallel DAG Execution**
4. **Issue 3.4: Saga Pattern Integration**
5. **Issue 3.5: Protocol Monitor (MPST validation)**

**Diagram Updates:**
- `project_architecture_part2.mmd`: Orchestrator section
- `project_architecture_part4.mmd`: Multi-agent workflow

**Effort:** 3 weeks

---

## Epic 4: Planner Integration 🟡

**ADR Reference:** ADR-0007 (4-Stage Planning Pipeline)

**Goal:** Integrate LLM-powered planner with K0 WAL commit

### Issues:

1. **Issue 4.1: 4-Stage Pipeline (Sketch → Expand → Validate → Commit)**
2. **Issue 4.2: LLM Prompt Engineering (Model Hub)**
3. **Issue 4.3: Tool/Prompt Registry**
4. **Issue 4.4: Validation (Rules + Arbiter)**
5. **Issue 4.5: K0 WAL Commit Integration**

**Diagram Updates:**
- `project_architecture_part2.mmd`: Planner section
- `project_architecture_part1.mmd`: P04 Arbitration pipeline

**Effort:** 3 weeks

---

## Epic 5: Model Hub Integration 🟡

**ADR Reference:** Layer 3 (Execution), ADR-0001b (Model Hub Architecture)

**Goal:** Integrate NPU/GPU/CPU/Remote placement with thermal management

### Issues:

1. **Issue 5.1: NPU/GPU/CPU/Remote Placement (thermal-aware)**
2. **Issue 5.2: KV Cache Broker (75% hit rate target)**
3. **Issue 5.3: Provider Adapters (OpenAI, Anthropic, vLLM, Ollama)**
4. **Issue 5.4: Prompt Library (role-based, size-based)**
5. **Issue 5.5: Fallback Cascade & Safety Filter**

**Diagram Updates:**
- `project_architecture_part3.mmd`: Model Hub section
- `project_architecture_part1.mmd`: Model Hub detail

**Effort:** 3 weeks

---

## Epic 6: SessionState Integration 🟡

**ADR Reference:** ADR-0017 (SessionState 6-Section Design)

**Goal:** Implement 6-section SessionState with 3-tier eviction

### Issues:

1. **Issue 6.1: 6-Section Design (beliefs, scoreboard, control, persona, multimodal, meta)**
2. **Issue 6.2: 3-Tier Eviction (64KB → 128KB → 256KB)**
3. **Issue 6.3: FlatBuffers Serialization (<1ms)**
4. **Issue 6.4: K0 WAL Checkpointing (5min interval)**
5. **Issue 6.5: Delta Serialization Pipeline**

**Diagram Updates:**
- `project_architecture_part1.mmd`: SessionState section
- `storage_infra.mmd`: State persistence layer

**Effort:** 3 weeks

---

## Epic 7: Learning Loop Integration 🟢

**ADR Reference:** ADR-0059 (Learning Loop Framework)

**Goal:** Implement adaptive learning with drift detection

### Issues:

1. **Issue 7.1: Feedback Signal Taxonomy (explicit, implicit, behavioral)**
2. **Issue 7.2: Drift Detection Algorithm**
3. **Issue 7.3: Planner Parameter Updates**
4. **Issue 7.4: Audit & Rollback Mechanisms**
5. **Issue 7.5: Synthetic Data Pipeline**

**Diagram Updates:**
- `project_architecture_part4.mmd`: Learning loop flows

**Effort:** 3 weeks

---

## Epic 8: Performance Budgets 🟡

**ADR Reference:** ADR-0024 (Performance Budgets)

**Goal:** Validate TTFT <150ms P95 and component-level budgets

### Issues:

1. **Issue 8.1: TTFT <150ms P95 Validation**
2. **Issue 8.2: Component-Level Budgets**
3. **Issue 8.3: Memory Budgets (K1 <500MB)**
4. **Issue 8.4: Graceful Degradation**
5. **Issue 8.5: Hot Path Optimization (Layers 1-3)**

**Diagram Updates:**
- All diagrams: Performance annotations

**Effort:** 3 weeks

---

## Epic 9: Multi-Device Sync 🔴

**ADR Reference:** ADR-0050 (Multi-Device Sync Strategy)

**Goal:** Implement CRDT sync for device-local K0+K1

**Why Critical:** Enables multi-device family experience (Phase 1 MVP)

### Issues:

1. **Issue 9.1: CRDT Merge Protocol (LWW - Last-Write-Wins)**
2. **Issue 9.2: SessionState Coherence (per-device guarantees)**
3. **Issue 9.3: LAN-First Sync (mDNS, TCP, <50ms)**
4. **Issue 9.4: P2P E2EE Internet Sync (Phase 2, 8-9 weeks)**
5. **Issue 9.5: Automatic LAN Fallback**

**Diagram Updates:**
- `d5_multi_node_topology.mmd`: Multi-device topology
- `project_architecture_part1.mmd`: P07 Sync pipeline

**Effort:** 4 weeks (Phase 1), 8-9 weeks (Phase 2)

---

## Epic 10: Observability Integration 🟢

**ADR Reference:** ADR-0029, ADR-0030 (Observability)

**Goal:** Implement comprehensive observability (metrics, tracing, receipts)

### Issues:

1. **Issue 10.1: Prometheus Metrics (RED method)**
2. **Issue 10.2: OpenTelemetry Tracing (cognitive_trace_id)**
3. **Issue 10.3: Intelligent Trace Sampling**
4. **Issue 10.4: Receipt Aggregation**
5. **Issue 10.5: Grafana Dashboards**

**Diagram Updates:**
- `project_architecture_part3.mmd`: Observability section
- `project_architecture_part1.mmd`: Receipt system

**Effort:** 3 weeks

---

## Diagram Integration Checklist

### 8 Diagrams to Update

| Diagram | Priority | Sections to Update | Related Epics |
|---------|----------|-------------------|---------------|
| **project_architecture_part1.mmd** | 🔴 HIGH | K0_KERNEL, K0_BUS, Agent_Fabric, PIPELINES, COGNITIVE_ORCHESTRATION | Epic 1, 2, 3, 4, 6, 9 |
| **project_architecture_part2.mmd** | 🔴 HIGH | Orchestrator, Planner, Agent_Fabric, Supervisor | Epic 2, 3, 4 |
| **project_architecture_part3.mmd** | 🟡 MEDIUM | Model Hub, Observability, Thermal, Config | Epic 5, 8, 10 |
| **project_architecture_part4.mmd** | 🟡 MEDIUM | TTFT Pipeline, Multi-agent, Learning Loop, Voice Pipeline | Epic 3, 7, 8 |
| **k0_comprehensive_architecture.mmd** | 🔴 HIGH | K0_PORTS, K0_DRIVERS, WAL, Receipts | Epic 1, 6, 10 |
| **storage_infra.mmd** | 🟡 MEDIUM | SessionState, Multi-Tier, KV Cache | Epic 5, 6 |
| **d5_multi_node_topology.mmd** | 🔴 HIGH | Device Nodes, CRDT Sync, LAN Sync, P2P E2EE | Epic 9 |
| **d5_failover_sequence.mmd** | 🟡 MEDIUM | K1 Crash, WAL Replay, Circuit Breaker | Epic 1, 2 |

---

## ADR References by Epic

### Critical ADRs (Must Read First)

| ADR | Title | Epics | Status |
|-----|-------|-------|--------|
| **ADR-0001** | K0/K1 Kernel Split Architecture | All | ✅ Accepted |
| **ADR-0001a** | K0 Bridge Communication Protocol | Epic 1 | ✅ Approved |
| **ADR-0004** | 52-Module 5-Layer Microkernel | All | ✅ Accepted |
| **ADR-0050** | Multi-Device Family Sync Strategy | Epic 9 | ✅ Accepted |

### Epic-Specific ADRs

**Epic 1 (K0 Bridge):**
- ADR-0011: FlatBuffers for All Contracts
- ADR-0012: 76 FlatBuffers Schemas
- ADR-0022: K0 Bridge Bounded Batching
- ADR-0009: Circuit Breaker Pattern

**Epic 2 (Agent Fabric):**
- ADR-0002: Actor Model for Agent Isolation
- ADR-0002a: Mailbox MPSC Queue
- ADR-0002b: Supervisor Monitoring
- ADR-0005: Agent Lifecycle FSM (6 States)
- ADR-0005a-e: Agent FSM sub-decisions
- ADR-0010: Capability-Based Security

**Epic 3 (Orchestrator):**
- ADR-0006: 3-Phase Orchestration (Contract Net)
- ADR-0006a-e: Orchestrator sub-decisions
- ADR-0008: Saga Pattern for Error Recovery

**Epic 4 (Planner):**
- ADR-0007: 4-Stage Planning Pipeline
- ADR-0007a-d: Planner sub-decisions

**Epic 5 (Model Hub):**
- ADR-0001b: Model Hub Architecture & LLM Integration
- ADR-0026: Thermal Hysteresis Matrix
- ADR-0027: Model Placement Cascade

**Epic 6 (SessionState):**
- ADR-0017: SessionState 6-Section Design
- ADR-0017a-f: SessionState sub-decisions
- ADR-0018: 3-Tier Eviction Strategy
- ADR-0019: FlatBuffers SessionState Serialization

**Epic 7 (Learning Loop):**
- ADR-0059: Learning Loop Framework
- ADR-0059a-e: Learning sub-decisions

**Epic 8 (Performance):**
- ADR-0024: Performance Budgets (P95)
- ADR-0024a-d: Performance sub-decisions
- ADR-0025: KV Cache Management

**Epic 9 (Multi-Device):**
- ADR-0050: Multi-Device Family Sync Strategy
- ADR-0050a: SessionState Coherence Guarantees
- ADR-0050b: CRDT Device-to-Device Merge
- ADR-0050c: LAN-First Sync Implementation (Phase 1)
- ADR-0050d: P2P E2EE Internet Sync (Phase 2)

**Epic 10 (Observability):**
- ADR-0029: Prometheus Metrics (RED Method)
- ADR-0029a-e: Metrics sub-decisions
- ADR-0030: Intelligent Trace Sampling
- ADR-0030a-d: Sampling sub-decisions

---

## Implementation Timeline (High-Level)

### Phase 1: Foundation (Weeks 1-4)
**Goal:** K0 Bridge + Agent Fabric operational

- **Week 1-2:** FlatBuffers schemas (Issue 1.1)
- **Week 2-3:** HTTP/2 batching (Issue 1.2)
- **Week 3-4:** Circuit breaker + Agent FSM (Issue 1.3, 2.1)
- **Week 4:** Idempotency, observability, mailbox (Issue 1.4, 1.5, 2.2)

**Milestone:** K1 agents can communicate with K0 via bridge

---

### Phase 2: Orchestration (Weeks 5-8)
**Goal:** Multi-agent coordination working

- **Week 5-6:** 3-phase orchestration (Epic 3)
- **Week 6-8:** 4-stage planner (Epic 4)
- **Week 7-9:** Model Hub integration (Epic 5, parallel)

**Milestone:** K1 can orchestrate multi-agent tasks with LLM reasoning

---

### Phase 3: State & Learning (Weeks 8-11)
**Goal:** Persistent state and adaptive learning

- **Week 8-10:** SessionState 6-section + eviction (Epic 6)
- **Week 9-11:** Learning loop + drift detection (Epic 7, parallel)

**Milestone:** K1 state persisted to K0, learning from feedback

---

### Phase 4: Performance & Multi-Device (Weeks 10-14)
**Goal:** Production-ready performance and multi-device sync

- **Week 10-12:** Performance validation + hot path (Epic 8)
- **Week 11-13:** LAN-first sync (Epic 9, Phase 1)
- **Week 12-14:** Observability dashboards (Epic 10, parallel)

**Milestone:** TTFT <150ms P95, multi-device LAN sync working

---

### Phase 5: P2P E2EE (Weeks 13-22, Phase 2)
**Goal:** Internet sync for remote devices

- **Week 13-18:** E2EE infrastructure (Issue 9.4)
- **Week 18-22:** P2P tunnel + testing (Issue 9.5)

**Milestone:** Devices sync over internet with E2EE

---

## Success Criteria (Must Achieve)

### Performance Targets (ADR-0024)

| Metric | Target | Current | Status |
|--------|--------|---------|--------|
| TTFT | <150ms P95 | 140ms | ✅ |
| E2E Turn | <2000ms P95 | 1850ms | ✅ |
| K0 Bridge | <10ms P95 | TBD | ⏳ |
| Agent Spawn | <45ms P95 | TBD | ⏳ |
| Model Hub | <50ms P95 | 48ms | ✅ |
| SessionState Serialize | <1ms | TBD | ⏳ |
| Config Reload | <100ms P95 | 93ms | ✅ |
| LAN Sync | <50ms | TBD | ⏳ |
| Internet Sync | <500ms P95 | TBD | ⏳ (Phase 2) |
| K1 Memory | <500MB | 450MB | ✅ |

### Quality Targets

- Test Coverage: 91% (WARD framework)
- Test-to-Code Ratio: 0.65
- ADR Compliance: 100%
- Zero Simulations: 100% (production code)
- Import Linter: Zero violations

### Reliability Targets

- K1 Uptime: 99.9%
- Crash Recovery: <5s
- Circuit Breaker: 3 failures → open
- Agent Blacklist: 3 crashes → disable
- CRDT Convergence: 100%

---

## Risk Summary

### High-Risk Items (Need Immediate Attention)

| Risk | Impact | Mitigation |
|------|--------|------------|
| FlatBuffers complexity | Blocks all epics | Phased implementation, start with core 20 schemas |
| K0 Bridge latency >10ms | Breaks TTFT budget | Early prototyping, profiling in Week 1 |
| Agent crash cascade | System instability | Supervision trees, circuit breakers, isolation |
| CRDT merge conflicts | Data consistency | LWW with device ordering, extensive testing |
| Multi-device sync latency | Poor UX | LAN preference, automatic fallback |

---

## Resource Requirements

### Team Allocation (5 Developers)

| Role | Focus | Epics |
|------|-------|-------|
| **Backend Lead** | K0 Bridge, Agent Fabric, Multi-Device | Epic 1, 2, 9 |
| **Backend Senior 1** | Orchestrator, Planner | Epic 3, 4 |
| **Backend Senior 2** | Model Hub, SessionState | Epic 5, 6 |
| **Backend Mid** | Learning Loop, Performance | Epic 7, 8 |
| **DevOps Lead** | Observability, Infrastructure | Epic 10 |

### External Dependencies

- FlatBuffers compiler (v24.3+)
- HTTP/2 library (httpx)
- Python 3.11+ (structural pattern matching)
- SQLite 3.42+ (K0 WAL)
- OpenTelemetry SDK
- Prometheus + Grafana
- WARD test framework

---

## Next Steps (Immediate Actions)

### This Week (Week 0)

1. **Architecture Review:**
   - Schedule 2-hour review meeting
   - Present this document + full planning doc
   - Get sign-off from stakeholders

2. **Epic Assignment:**
   - Assign epic owners (see resource allocation)
   - Create project board (Jira/GitHub Projects)
   - Set up epic templates

3. **Sprint 0 Planning:**
   - Break down Epic 1, Issue 1.1 into tasks
   - Estimate story points
   - Prepare Sprint 1 backlog

4. **Infrastructure Setup:**
   - CI/CD pipeline (WARD tests)
   - Pre-commit hooks (import linter)
   - Documentation templates

### Week 1 (Kickoff)

1. **Sprint 1 Start:**
   - Epic 1, Issue 1.1 (FlatBuffers schemas)
   - Daily standups (15min, 10am)
   - Weekly architecture sync (Friday, 2pm)

2. **Parallel Work:**
   - Backend: FlatBuffers schema generation (core 20)
   - DevOps: CI/CD pipeline setup
   - QA: WARD test framework setup
   - Architect: Diagram updates (part1.mmd)

---

## Approval Checklist

- [ ] Lead Architect sign-off
- [ ] K0 Technical Lead sign-off
- [ ] K1 Technical Lead sign-off
- [ ] Product Owner sign-off
- [ ] DevOps Lead sign-off
- [ ] QA Lead sign-off

---

## Document References

**Full Planning:** `K1_K0_INTEGRATION_PLANNING.md` (complete epic/issue breakdown)

**ADR Catalog:** `docs/architecture/decisions/ADR_MASTER_REFERENCE.md`

**K0 Diagrams:** `architecture_diagrams/k0/architecture_diagrams/`

**K1 Specifications:** `docs/whiteboard.md` (21K lines)

**K1 Module Analysis:** `docs/k1_module_analysis.md` (52 modules, 758 files)

---

**Status:** ✅ READY FOR REVIEW  
**Version:** 1.0  
**Last Updated:** 2025-10-19  
**Next Review:** After architecture approval meeting

---

**END OF SUMMARY**
