# ADR Reference Guide: Layer 2 - Orchestration

**Generated:** Auto-generated from ADR family map  
**Purpose:** Quick reference for ADRs relevant to Layer 2 - Orchestration development

## Overview

This layer orchestrates agent coordination, planning, and task management.

**Total Relevant ADRs:** 127

---

## Quick Reference: All ADRs for Layer 2 - Orchestration

| ADR | Title | Family |
|-----|-------|--------|
| [ADR-0001](../../docs/architecture/decisions/0001-*.md) | 0001 Memory Kernel | K0 Core |
| [ADR-0001f](../../docs/architecture/decisions/0001f-*.md) | 0001F Memory Kernel | K0 Core |
| [ADR-0004](../../docs/architecture/decisions/0004-*.md) | 0004 Architecture | K1 Core |
| [ADR-0004b](../../docs/architecture/decisions/0004b-*.md) | 0004B Dependencies | K1 Core |
| [ADR-0004c](../../docs/architecture/decisions/0004c-*.md) | 0004C Documentation | ADR Notes |
| [ADR-0004d](../../docs/architecture/decisions/0004d-*.md) | 0004D Testing | K1 Core |
| [ADR-0006](../../docs/architecture/decisions/0006-*.md) | 0006 Phase 1 Negotiation | 3-Phase Orchestration |
| [ADR-0006a](../../docs/architecture/decisions/0006a-*.md) | 0006A Phase 1 Negotiation | 3-Phase Orchestration |
| [ADR-0006b](../../docs/architecture/decisions/0006b-*.md) | 0006B Phase 2 Selection | 3-Phase Orchestration |
| [ADR-0006c](../../docs/architecture/decisions/0006c-*.md) | 0006C Phase 3 Execution | 3-Phase Orchestration |
| [ADR-0006d](../../docs/architecture/decisions/0006d-*.md) | 0006D Saga Pattern | 3-Phase Orchestration |
| [ADR-0006e](../../docs/architecture/decisions/0006e-*.md) | 0006E Multi-Agent Coordination | 3-Phase Orchestration |
| [ADR-0007](../../docs/architecture/decisions/0007-*.md) | 0007 Pipeline Core | 4-Stage Planning |
| [ADR-0007b](../../docs/architecture/decisions/0007b-*.md) | 0007B Stage 2 Expand | 4-Stage Planning |
| [ADR-0007c](../../docs/architecture/decisions/0007c-*.md) | 0007C Stage 3 Validate | 4-Stage Planning |
| [ADR-0007d](../../docs/architecture/decisions/0007d-*.md) | 0007D Stage 4 Commit | 4-Stage Planning |
| [ADR-0008](../../docs/architecture/decisions/0008-*.md) | 0008 Saga Orchestrator | Saga Error Recovery |
| [ADR-0008a](../../docs/architecture/decisions/0008a-*.md) | 0008A Compensation Design | Saga Error Recovery |
| [ADR-0008b](../../docs/architecture/decisions/0008b-*.md) | 0008B Recovery Strategies | Saga Error Recovery |
| [ADR-0008c](../../docs/architecture/decisions/0008c-*.md) | 0008C Distributed State | Saga Error Recovery |
| [ADR-0008d](../../docs/architecture/decisions/0008d-*.md) | 0008D Timeout Management | Saga Error Recovery |
| [ADR-0011a](../../docs/architecture/decisions/0011a-*.md) | 0011A Schema Design | FlatBuffers |
| [ADR-0011b](../../docs/architecture/decisions/0011b-*.md) | 0011B Code Generation | FlatBuffers |
| [ADR-0011c](../../docs/architecture/decisions/0011c-*.md) | 0011C Performance | FlatBuffers |
| [ADR-0011d](../../docs/architecture/decisions/0011d-*.md) | 0011D Schema Evolution | FlatBuffers |
| [ADR-0012](../../docs/architecture/decisions/0012-*.md) | 0012 Schema Taxonomy | FlatBuffers Schemas |
| [ADR-0012b](../../docs/architecture/decisions/0012b-*.md) | 0012B Layer 2 Schemas | FlatBuffers Schemas |
| [ADR-0013](../../docs/architecture/decisions/0013-*.md) | 0013 SemVer Policy | Schema Versioning |
| [ADR-0013a](../../docs/architecture/decisions/0013a-*.md) | 0013A Version Registry | Schema Versioning |
| [ADR-0013b](../../docs/architecture/decisions/0013b-*.md) | 0013B CI/CD Automation | Schema Versioning |
| [ADR-0013c](../../docs/architecture/decisions/0013c-*.md) | 0013C Deprecation Workflow | Schema Versioning |
| [ADR-0013d](../../docs/architecture/decisions/0013d-*.md) | 0013D Contract Testing | Schema Versioning |
| [ADR-0014b](../../docs/architecture/decisions/0014b-*.md) | 0014B OpenAPI Generation | REST API Dual Format |
| [ADR-0014d](../../docs/architecture/decisions/0014d-*.md) | 0014D Client SDKs | REST API Dual Format |
| [ADR-0015](../../docs/architecture/decisions/0015-*.md) | 0015 Protocol Design | WebSocket Binary Protocol |
| [ADR-0015a](../../docs/architecture/decisions/0015a-*.md) | 0015A Protocol Design | WebSocket Binary Protocol |
| [ADR-0015b](../../docs/architecture/decisions/0015b-*.md) | 0015B Flow Control | WebSocket Binary Protocol |
| [ADR-0015c](../../docs/architecture/decisions/0015c-*.md) | 0015C Reconnection | WebSocket Binary Protocol |
| [ADR-0015d](../../docs/architecture/decisions/0015d-*.md) | 0015D Streaming | WebSocket Binary Protocol |
| [ADR-0015e](../../docs/architecture/decisions/0015e-*.md) | 0015E Client SDK | WebSocket Binary Protocol |
| [ADR-0016](../../docs/architecture/decisions/0016-*.md) | 0016 Event Taxonomy | SSE Event Schemas |
| [ADR-0016a](../../docs/architecture/decisions/0016a-*.md) | 0016A Event Taxonomy | SSE Event Schemas |
| [ADR-0016c](../../docs/architecture/decisions/0016c-*.md) | 0016C Filtering | SSE Event Schemas |
| [ADR-0016d](../../docs/architecture/decisions/0016d-*.md) | 0016D Browser Integration | SSE Event Schemas |
| [ADR-0019](../../docs/architecture/decisions/0019-*.md) | 0019 Serialization Core | FlatBuffers SessionState Serialization |
| [ADR-0019a](../../docs/architecture/decisions/0019a-*.md) | 0019A Schema Definition | FlatBuffers SessionState Serialization |
| [ADR-0021c](../../docs/architecture/decisions/0021c-*.md) | 0021C Compliance | Turn History Retention |
| [ADR-0022d](../../docs/architecture/decisions/0022d-*.md) | 0022D FlatBuffers Schema | K0 Bridge Batching |
| [ADR-0023c](../../docs/architecture/decisions/0023c-*.md) | 0023C K0 WAL Query | Cursor-Based Pagination |
| [ADR-0024](../../docs/architecture/decisions/0024-*.md) | 0024 Component-Level Budgets | Performance Budgets |
| [ADR-0024b](../../docs/architecture/decisions/0024b-*.md) | 0024B Component-Level Budgets | Performance Budgets |
| [ADR-0024d](../../docs/architecture/decisions/0024d-*.md) | 0024D Graceful Degradation | Performance Budgets |
| [ADR-0028](../../docs/architecture/decisions/0028-*.md) | 0028 Priority Queues | WFQ Scheduler |
| [ADR-0028a](../../docs/architecture/decisions/0028a-*.md) | 0028A Virtual Time | WFQ Scheduler |
| [ADR-0028b](../../docs/architecture/decisions/0028b-*.md) | 0028B Preemption | WFQ Scheduler |
| [ADR-0028c](../../docs/architecture/decisions/0028c-*.md) | 0028C Anti-Starvation | WFQ Scheduler |
| [ADR-0029](../../docs/architecture/decisions/0029-*.md) | 0029 Component | Prometheus Metrics |
| [ADR-0029c](../../docs/architecture/decisions/0029c-*.md) | 0029C Component | Prometheus Metrics |
| [ADR-0029d](../../docs/architecture/decisions/0029d-*.md) | 0029D Infrastructure | Prometheus Metrics |
| [ADR-0035c](../../docs/architecture/decisions/0035c-*.md) | 0035C Encrypted Vault | PII Detection |
| [ADR-0035d](../../docs/architecture/decisions/0035d-*.md) | 0035D Audit Trail | PII Detection |
| [ADR-0036](../../docs/architecture/decisions/0036-*.md) | 0036 Zero-Knowledge Architecture | E2EE |
| [ADR-0036a](../../docs/architecture/decisions/0036a-*.md) | 0036A AES-256-GCM | E2EE |
| [ADR-0036b](../../docs/architecture/decisions/0036b-*.md) | 0036B KMS Integration | E2EE |
| [ADR-0036c](../../docs/architecture/decisions/0036c-*.md) | 0036C Selective Encryption | E2EE |
| [ADR-0036d](../../docs/architecture/decisions/0036d-*.md) | 0036D Audit Trail | E2EE |
| [ADR-0037d](../../docs/architecture/decisions/0037d-*.md) | 0037D Session Binding | JWT Authentication |
| [ADR-0038](../../docs/architecture/decisions/0038-*.md) | 0038 Immutability | Audit Trail (K0 Receipts) |
| [ADR-0038a](../../docs/architecture/decisions/0038a-*.md) | 0038A Receipt Types | Audit Trail (K0 Receipts) |
| [ADR-0038b](../../docs/architecture/decisions/0038b-*.md) | 0038B WAL Integration | Audit Trail (K0 Receipts) |
| [ADR-0038c](../../docs/architecture/decisions/0038c-*.md) | 0038C Retention Policies | Audit Trail (K0 Receipts) |
| [ADR-0038d](../../docs/architecture/decisions/0038d-*.md) | 0038D Query Interface | Audit Trail (K0 Receipts) |
| [ADR-0039](../../docs/architecture/decisions/0039-*.md) | 0039 Band-Specific Policies | Privacy Band Retention |
| [ADR-0042a](../../docs/architecture/decisions/0042a-*.md) | 0042A Event Production | K0 SSE Event Streaming |
| [ADR-0042d](../../docs/architecture/decisions/0042d-*.md) | 0042D Backpressure | K0 SSE Event Streaming |
| [ADR-0043c](../../docs/architecture/decisions/0043c-*.md) | 0043C Topic Routing | SSE Topic Taxonomy |
| [ADR-0045](../../docs/architecture/decisions/0045-*.md) | 0045 Contract Net Protocol | Agent Coordination |
| [ADR-0045a](../../docs/architecture/decisions/0045a-*.md) | 0045A K1 Event Bus | Agent Coordination K1 Internal |
| [ADR-0045b](../../docs/architecture/decisions/0045b-*.md) | 0045B Topic Routing | Agent Coordination K1 Internal |
| [ADR-0045c](../../docs/architecture/decisions/0045c-*.md) | 0045C Delivery Guarantees | Agent Coordination K1 Internal |
| [ADR-0045d](../../docs/architecture/decisions/0045d-*.md) | 0045D Backpressure | Agent Coordination K1 Internal |
| [ADR-0046](../../docs/architecture/decisions/0046-*.md) | 0046 Configuration | SSE-WebSocket Bridge |
| [ADR-0047](../../docs/architecture/decisions/0047-*.md) | 0047 SDK Generation | OpenAPI 3.1 Specs |
| [ADR-0048](../../docs/architecture/decisions/0048-*.md) | 0048 Event Categories | K1 Internal Event Bus |
| [ADR-0049](../../docs/architecture/decisions/0049-*.md) | 0049 Configuration | Fast/Smart Lane Router |
| [ADR-0050](../../docs/architecture/decisions/0050-*.md) | 0050 Sync Strategy | Multi-Device Family Sync |
| [ADR-0052](../../docs/architecture/decisions/0052-*.md) | 0052 Research Foundation | Enhanced HITL Protocols |
| [ADR-0052a](../../docs/architecture/decisions/0052a-*.md) | 0052A Step-by-Step Approval | Enhanced HITL Protocols |
| [ADR-0052b](../../docs/architecture/decisions/0052b-*.md) | 0052B RED Band Approval | Enhanced HITL Protocols |
| [ADR-0052c](../../docs/architecture/decisions/0052c-*.md) | 0052C Nested Clarifications | Enhanced HITL Protocols |
| [ADR-0052d](../../docs/architecture/decisions/0052d-*.md) | 0052D Proactive Confirmation | Enhanced HITL Protocols |
| [ADR-0052e](../../docs/architecture/decisions/0052e-*.md) | 0052E Layer 2 State | HITL Schema Integration |
| [ADR-0053](../../docs/architecture/decisions/0053-*.md) | 0053 Main | Message Queue & Coalescing |
| [ADR-0053a](../../docs/architecture/decisions/0053a-*.md) | 0053A Coalesce Window | Message Queue & Coalescing |
| [ADR-0053b](../../docs/architecture/decisions/0053b-*.md) | 0053B Rate Limits | Message Queue & Coalescing |
| [ADR-0053c](../../docs/architecture/decisions/0053c-*.md) | 0053C Cancel Path | Message Queue & Coalescing |
| [ADR-0054](../../docs/architecture/decisions/0054-*.md) | 0054 Main | Turn Boundary Management |
| [ADR-0054a](../../docs/architecture/decisions/0054a-*.md) | 0054A Implicit Pause | Turn Boundary Management |
| [ADR-0054b](../../docs/architecture/decisions/0054b-*.md) | 0054B Explicit Submit | Turn Boundary Management |
| [ADR-0056](../../docs/architecture/decisions/0056-*.md) | 0056 Pipeline Architecture | Voice Pipeline Implementation |
| [ADR-0056a](../../docs/architecture/decisions/0056a-*.md) | 0056A ASR Ingress | Voice Pipeline Implementation |
| [ADR-0056d](../../docs/architecture/decisions/0056d-*.md) | 0056D TTS Synthesis | Voice Pipeline Implementation |
| [ADR-0056e](../../docs/architecture/decisions/0056e-*.md) | 0056E Audio Output | Voice Pipeline Implementation |
| [ADR-0059](../../docs/architecture/decisions/0059-*.md) | 0059 Core Architecture | Learning Loop |
| [ADR-0059a](../../docs/architecture/decisions/0059a-*.md) | 0059A Feedback Signals | Learning Loop |
| [ADR-0059b](../../docs/architecture/decisions/0059b-*.md) | 0059B Drift Detection | Learning Loop |
| [ADR-0059c](../../docs/architecture/decisions/0059c-*.md) | 0059C Parameter Contracts | Learning Loop |
| [ADR-0059d](../../docs/architecture/decisions/0059d-*.md) | 0059D Audit & Rollback | Learning Loop |
| [ADR-0059e](../../docs/architecture/decisions/0059e-*.md) | 0059E Synthetic Data | Learning Loop |
| [ADR-0072](../../docs/architecture/decisions/0072-*.md) | 0072 Agent Creation | Agent Fabric |
| [ADR-0073](../../docs/architecture/decisions/0073-*.md) | 0073 Lifecycle FSM | Agent Fabric |
| [ADR-0079](../../docs/architecture/decisions/0079-*.md) | 0079 Drift Detection | Learning Loop Drift |
| [ADR-0081](../../docs/architecture/decisions/0081-*.md) | 0081 Knowledge Graph | K0 Core |
| [ADR-0081a](../../docs/architecture/decisions/0081a-*.md) | 0081A Knowledge Graph | K0 Core |
| [ADR-0081b](../../docs/architecture/decisions/0081b-*.md) | 0081B Knowledge Graph | K0 Core |
| [ADR-0081c](../../docs/architecture/decisions/0081c-*.md) | 0081C Knowledge Graph | K0 Core |
| [ADR-0081d](../../docs/architecture/decisions/0081d-*.md) | 0081D Knowledge Graph | K0 Core |
| [ADR-0082](../../docs/architecture/decisions/0082-*.md) | 0082 Core Architecture | Multi-Party Dialogue |
| [ADR-0082b](../../docs/architecture/decisions/0082b-*.md) | 0082B Turn-Taking | Multi-Party Dialogue |
| [ADR-0084](../../docs/architecture/decisions/0084-*.md) | 0084 Core Architecture | K0 Memory Consolidation |
| [ADR-0084a](../../docs/architecture/decisions/0084a-*.md) | 0084A Hippocampal Replay | K0 Memory Consolidation |
| [ADR-0084b](../../docs/architecture/decisions/0084b-*.md) | 0084B Sleep State Machine | K0 Memory Consolidation |
| [ADR-0084c](../../docs/architecture/decisions/0084c-*.md) | 0084C Knowledge Graph Consol. | K0 Memory Consolidation |
| [ADR-0084d](../../docs/architecture/decisions/0084d-*.md) | 0084D Dream Exploration | K0 Memory Consolidation |
| [ADR-0085](../../docs/architecture/decisions/0085-*.md) | 0085 Core Architecture | Embodied Awareness |
| [ADR-0085a](../../docs/architecture/decisions/0085a-*.md) | 0085A Device Presence | Embodied Awareness |
| [ADR-0085c](../../docs/architecture/decisions/0085c-*.md) | 0085C Context Sharing | Embodied Awareness |

---

## Detailed Breakdown by Family

### 3-Phase Orchestration

#### [ADR-0006](../../docs/architecture/decisions/0006-*.md): 0006 Phase 1 Negotiation

**Components:**

- **Phase 1 Negotiation** → Contract Net Protocol
  - File: `k1/l2_orchestration/orchestrator/negotiation.py`
  - TaskAnnouncement broadcast, proposal collection, 50ms deadline, Contract Net (Smith 1980)

- **Phase 2 Selection** → Scoring Engine
  - File: `k1/l2_orchestration/orchestrator/scoring.py`
  - 6-factor weighted sum, confidence (10.0), latency (8.0), cost (-5.0), MADM

- **Phase 3 Execution** → DAG Execution Engine
  - File: `k1/l2_orchestration/orchestrator/dag_executor.py`
  - Wave computation, parallel execution, asyncio.gather, semaphore (max 3)

- **Saga Pattern** → Saga Coordinator
  - File: `k1/l2_orchestration/orchestrator/saga_coordinator.py`
  - LIFO compensation, reverse-order unwinding, best-effort, Garcia-Molina 1987

#### [ADR-0006a](../../docs/architecture/decisions/0006a-*.md): 0006A Phase 1 Negotiation

**Components:**

- **Phase 1 Negotiation** → Contract Net Protocol
  - File: `k1/l2_orchestration/orchestrator/negotiation.py`
  - TaskAnnouncement broadcast, proposal collection, 50ms deadline, Contract Net (Smith 1980)

- **Phase 1 Negotiation** → Task Announcement
  - File: `k1/l2_orchestration/orchestrator/negotiation.py`
  - Broadcast to ACTIVE agents, mailbox send, task requirements, trace_id

- **Phase 1 Negotiation** → Proposal Collection
  - File: `k1/l2_orchestration/orchestrator/negotiation.py`
  - MPSC queue, 50ms timeout, non-blocking receive, metrics emission

- **Phase 1 Negotiation** → Fallback Strategy
  - File: `k1/l2_orchestration/orchestrator/fallback.py`
  - 4-tier (hire→simplify→wait-retry→degrade), no-proposals handling

#### [ADR-0006b](../../docs/architecture/decisions/0006b-*.md): 0006B Phase 2 Selection

**Components:**

- **Phase 2 Selection** → Scoring Engine
  - File: `k1/l2_orchestration/orchestrator/scoring.py`
  - 6-factor weighted sum, confidence (10.0), latency (8.0), cost (-5.0), MADM

- **Phase 2 Selection** → Normalization
  - File: `k1/l2_orchestration/orchestrator/scoring.py`
  - Latency normalization (0-1), cost normalization (0-1), exponential decay

- **Phase 2 Selection** → Weighted Scoring
  - File: `k1/l2_orchestration/orchestrator/scoring.py`
  - Parallelism bonus (3.0), track record (2.0), busy penalty (-4.0), <5ms P95

- **Phase 2 Selection** → Tie-Breaking
  - File: `k1/l2_orchestration/orchestrator/tie_breaker.py`
  - 4 strategies (resident 60%, fast 20%, cheap 10%, random 10%), deterministic selection

- **Phase 2 Selection** → Winner Selection
  - File: `k1/l2_orchestration/orchestrator/selection.py`
  - Highest score wins, tie detection (epsilon 0.01), TaskAssignment message

#### [ADR-0006c](../../docs/architecture/decisions/0006c-*.md): 0006C Phase 3 Execution

**Components:**

- **Phase 3 Execution** → DAG Execution Engine
  - File: `k1/l2_orchestration/orchestrator/dag_executor.py`
  - Wave computation, parallel execution, asyncio.gather, semaphore (max 3)

- **Phase 3 Execution** → DAG Builder
  - File: `k1/l2_orchestration/orchestrator/dag_builder.py`
  - Nodes (steps), edges (dependencies), in-degree, out-edges, acyclic validation

- **Phase 3 Execution** → Wave Computation
  - File: `k1/l2_orchestration/orchestrator/wave_computer.py`
  - Topological sort (Kahn's algorithm), wave grouping, parallel independence

- **Phase 3 Execution** → Dependency Resolution
  - File: `k1/l2_orchestration/orchestrator/dependency_resolver.py`
  - Variable substitution ({step_N.field}), step result lookup, parameter resolution

- **Phase 3 Execution** → Parallel Execution
  - File: `k1/l2_orchestration/orchestrator/parallel_executor.py`
  - Asyncio.gather, barrier synchronization, semaphore (max 3), straggler detection

#### [ADR-0006d](../../docs/architecture/decisions/0006d-*.md): 0006D Saga Pattern

**Components:**

- **Saga Pattern** → Saga Coordinator
  - File: `k1/l2_orchestration/orchestrator/saga_coordinator.py`
  - LIFO compensation, reverse-order unwinding, best-effort, Garcia-Molina 1987

- **Saga Pattern** → Compensation Tracking
  - File: `k1/l2_orchestration/orchestrator/compensation_tracker.py`
  - Completed steps stack (LIFO), compensation actions, parameters resolution

- **Saga Pattern** → Compensation Execution
  - File: `k1/l2_orchestration/orchestrator/compensation_executor.py`
  - CompensationExecution message, timeout enforcement (3s), retry logic (1× retry)

- **Saga Pattern** → Multi-Agent Compensation
  - File: `k1/l2_orchestration/orchestrator/multi_agent_saga.py`
  - Agent coordination, concurrent compensation, best-effort, error logging

#### [ADR-0006e](../../docs/architecture/decisions/0006e-*.md): 0006E Multi-Agent Coordination

**Components:**

- **Multi-Agent Coordination** → Wave Independence Analysis
  - File: `k1/l2_orchestration/orchestrator/wave_analyzer.py`
  - Shared resource detection, tool contention, independent wave identification

- **Multi-Agent Coordination** → Multi-Agent Assignment
  - File: `k1/l2_orchestration/orchestrator/multi_agent_assignment.py`
  - Per-step negotiation, parallel bidding, agent specialization, Q2 2025 post-MVP

- **Multi-Agent Coordination** → Agent Synchronization
  - File: `k1/l2_orchestration/orchestrator/agent_sync.py`
  - Rendezvous points, barrier synchronization, parallel wave execution

- **Multi-Agent Coordination** → Result Aggregation
  - File: `k1/l2_orchestration/orchestrator/result_aggregator.py`
  - Multi-agent result merging, step result unification, aggregation metrics


### 4-Stage Planning

#### [ADR-0007](../../docs/architecture/decisions/0007-*.md): 0007 Pipeline Core

**Components:**

- **Pipeline Core** → Planning Pipeline
  - File: `k1/l2_orchestration/planner/pipeline.py`
  - 4 stages (Sketch→Expand→Validate→Commit), <2.5s P95, deterministic stages 2-4

- **Stage 2 Expand** → Plan Expander
  - File: `k1/l2_orchestration/planner/expander.py`
  - Tool registry lookup, prompt matching, metadata enrichment, <1ms P95

- **Stage 3 Validate** → Tier 1 Validator
  - File: `k1/l2_orchestration/planner/tier1_validator.py`
  - 6 rule checks (structure, deps, caps, budget, band, schema), <1ms P95

- **Stage 4 Commit** → Plan Committer
  - File: `k1/l2_orchestration/planner/committer.py`
  - FlowDef serialization, K0 WAL write, SessionState locking, <10ms P95

#### [ADR-0007b](../../docs/architecture/decisions/0007b-*.md): 0007B Stage 2 Expand

**Components:**

- **Stage 2 Expand** → Plan Expander
  - File: `k1/l2_orchestration/planner/expander.py`
  - Tool registry lookup, prompt matching, metadata enrichment, <1ms P95

- **Stage 2 Expand** → Metadata Enrichment
  - File: `k1/l2_orchestration/planner/expander.py`
  - Schema filling, capability requirements, cost/latency aggregation, ExpandedPlan

#### [ADR-0007c](../../docs/architecture/decisions/0007c-*.md): 0007C Stage 3 Validate

**Components:**

- **Stage 3 Validate** → Tier 1 Validator
  - File: `k1/l2_orchestration/planner/tier1_validator.py`
  - 6 rule checks (structure, deps, caps, budget, band, schema), <1ms P95

- **Stage 3 Validate** → Structural Validation
  - File: `k1/l2_orchestration/planner/validators/structural.py`
  - Step count ≤10, unique step_ids, sequential IDs, <0.1ms

- **Stage 3 Validate** → Dependency Validation
  - File: `k1/l2_orchestration/planner/validators/dependency.py`
  - Kahn's algorithm, DAG cycle detection, O(V+E), <0.2ms

- **Stage 3 Validate** → Capability Validation
  - File: `k1/l2_orchestration/planner/validators/capability.py`
  - Set intersection, missing capabilities check, <0.05ms

- **Stage 3 Validate** → Budget Validation
  - File: `k1/l2_orchestration/planner/validators/budget.py`
  - Latency budget check, cost budget check, <0.05ms

- **Stage 3 Validate** → Band Validation
  - File: `k1/l2_orchestration/planner/validators/band.py`
  - Privacy band hierarchy (GREEN<AMBER<RED), session band comparison, <0.05ms

- **Stage 3 Validate** → Schema Validation
  - File: `k1/l2_orchestration/planner/validators/schema.py`
  - JSON Schema validation, step parameters vs tool schema_in, <0.5ms

- **Stage 3 Validate** → Arbiter Invocation
  - File: `k1/l2_orchestration/planner/arbiter_invoker.py`
  - Invocation rules (AMBER/RED band, child space, age<18), gpt-4o-mini

#### [ADR-0007d](../../docs/architecture/decisions/0007d-*.md): 0007D Stage 4 Commit

**Components:**

- **Stage 4 Commit** → Plan Committer
  - File: `k1/l2_orchestration/planner/committer.py`
  - FlowDef serialization, K0 WAL write, SessionState locking, <10ms P95

- **Stage 4 Commit** → FlowDef Serialization
  - File: `k1/l2_orchestration/planner/flow_def_serializer.py`
  - FlatBuffers serialization, binary format, <1ms

- **Stage 4 Commit** → Idempotency
  - File: `k1/l2_orchestration/planner/idempotency.py`
  - Idempotency key generation, hash(session+plan+time_bucket), 60s window


### ADR Notes

#### [ADR-0004c](../../docs/architecture/decisions/0004c-*.md): 0004C Documentation

**Components:**

- **Documentation** → Module READMEs
  - File: `tools/k1_doc_gen.py`
  - k1-doc-gen, README template, auto-generation, docstring extraction, metadata parsing, CI enforcement


### Agent Coordination

#### [ADR-0045](../../docs/architecture/decisions/0045-*.md): 0045 Contract Net Protocol

**Components:**

- **Contract Net Protocol** → Coordinator
  - File: `k1/l2_orchestration/contract_net/coordinator.py`
  - 3-phase orchestration (Negotiation 5ms→Selection 3ms→Execution 150ms), <250ms total coordination, K1 mailbox-based (NOT K0 SSE), 1,920 lines implementation

- **Contract Net Protocol** → Task Announcer
  - File: `k1/l2_orchestration/contract_net/task_announcer.py`
  - K1 mailbox broadcast, task dissemination, <1ms mailbox latency, agent discovery, 1,540 lines implementation

- **Contract Net Protocol** → Proposal Manager
  - File: `k1/l2_orchestration/contract_net/proposal_manager.py`
  - Bid collection, 5ms deadline enforcement, proposal tracking, agent capability matching, 1,380 lines implementation

- **Selection Engine** → Weighted Selector
  - File: `k1/l2_orchestration/contract_net/weighted_selector.py`
  - Multi-criteria scoring (confidence 40%, latency 30%, cost 20%, availability 10%), weighted algorithm, winner selection, 1,220 lines implementation


### Agent Coordination K1 Internal

#### [ADR-0045a](../../docs/architecture/decisions/0045a-*.md): 0045A K1 Event Bus

**Components:**

- **K1 Event Bus** → In-Memory Pub/Sub
  - File: `k1/l2_orchestrator/event_bus/pubsub.py`
  - Zero network overhead (pure Python in-process), zero persistence (ephemeral memory-only), <2ms fanout to 10-20 agent mailboxes, push-based delivery (no polling)

- **K1 Event Bus** → Topic-Based Routing
  - File: `k1/l2_orchestrator/event_bus/routing.py`
  - 5 core orchestration topics (k1.orchestration.task.announced, agent.proposal, agent.selected, execution.started, execution.completed), wildcard subscriptions, per-topic subscriber lists

- **K1 Event Bus** → Actor Model Integration
  - File: `k1/l2_orchestrator/event_bus/mailbox_integration.py`
  - Events pushed to agent mailboxes (MPSC queues), no shared state (agents isolated), mailbox-only communication, supervisor tree integration

- **K1 Event Bus** → Zero K0 Dependency
  - File: `k1/l2_orchestrator/event_bus/k0_separation.py`
  - No K0 SSE involvement, no persistence to K0, pure K1 internal coordination, correct layer separation (ADR-0001: K0 = storage, K1 = runtime)

#### [ADR-0045b](../../docs/architecture/decisions/0045b-*.md): 0045B Topic Routing

**Components:**

- **Topic Routing** → Trie-Based Matching
  - File: `k1/l2_orchestrator/event_bus/topic_router.py`
  - O(log n) subscriber lookup, hierarchical topics (k1 → orchestration → event_type), wildcard support (*, **), <100μs routing overhead

- **Topic Routing** → Capability Filtering
  - File: `k1/l2_orchestrator/event_bus/capability_filter.py`
  - Only deliver events matching agent capabilities, filter at routing layer (not delivery layer), reduces fanout overhead, agents specify required_tools/required_capabilities

- **Topic Routing** → Precomputed Subscribers
  - File: `k1/l2_orchestrator/event_bus/subscriber_cache.py`
  - Precomputed subscriber lists per topic, cache invalidation on subscribe/unsubscribe, <100μs routing within 2ms fanout budget

- **Topic Routing** → Dynamic Subscriptions
  - File: `k1/l2_orchestrator/event_bus/subscription_manager.py`
  - Agents update subscriptions on-the-fly, <1ms subscribe/unsubscribe latency, no event loss during subscription changes, atomic subscription updates

#### [ADR-0045c](../../docs/architecture/decisions/0045c-*.md): 0045C Delivery Guarantees

**Components:**

- **Delivery Guarantees** → At-Most-Once
  - File: `k1/l2_orchestrator/event_bus/delivery_at_most_once.py`
  - Single delivery attempt (no retry), for notifications/monitoring (execution.completed), best-effort delivery

- **Delivery Guarantees** → At-Least-Once
  - File: `k1/l2_orchestrator/event_bus/delivery_at_least_once.py`
  - Retry with exponential backoff (100ms → 300ms → 900ms), max 3 attempts, for critical coordination (task.announced, agent.selected), >99.9% delivery success rate

- **Delivery Guarantees** → Idempotency Tracking
  - File: `k1/l2_orchestrator/event_bus/idempotency_tracker.py`
  - 5-min event ID cache, detect duplicate deliveries, subscribers must be idempotent, event IDs tracked globally (K1-wide)

- **Delivery Guarantees** → Dead Letter Queue
  - File: `k1/l2_orchestrator/event_bus/dlq.py`
  - DLQ for terminal failures after 3 attempts, 7-day DLQ retention, max 10K DLQ entries, supervisor alerts for DLQ overflow

#### [ADR-0045d](../../docs/architecture/decisions/0045d-*.md): 0045D Backpressure

**Components:**

- **Backpressure** → Mailbox Watermark Monitoring
  - File: `k1/l2_orchestrator/event_bus/watermark_monitor.py`
  - 50% yellow warning at 50 items (100-item MPSC queue), 80% red critical at 80 items, 150-item hard limit, per-agent watermark tracking

- **Backpressure** → Overflow Policies
  - File: `k1/l2_orchestrator/event_bus/overflow_policy.py`
  - Drop-oldest for at-most-once (evict oldest event from mailbox), block-with-timeout 500ms for at-least-once, priority-based dropping (notifications before critical events)

- **Backpressure** → Publisher Throttling
  - File: `k1/l2_orchestrator/event_bus/publisher_throttle.py`
  - Throttle when 3+ agents at red watermark (>80% capacity), exponential backoff (10ms → 30ms → 90ms → 270ms), resume normal speed when <3 agents at red

- **Backpressure** → Graceful Degradation
  - File: `k1/l2_orchestrator/event_bus/graceful_degradation.py`
  - Prioritize critical events (task.announced, agent.selected), drop low-priority notifications (execution.started, execution.completed), <5% event drop rate during overload vs 30% without backpressure


### Agent Fabric

#### [ADR-0072](../../docs/architecture/decisions/0072-*.md): 0072 Agent Creation

**Components:**

- **Agent Creation** → AgentFactory
  - File: `k1/l2_orchestration/agent_factory.py`
  - Runtime agent creation, agent ID format agent-{session_id}-{timestamp_ms}-{counter:06d}, ResourceReserver, <100ms P95 creation, M1 milestone

- **Agent Creation** → Agent Templates
  - File: `k1/l2_orchestration/agent_templates.py`
  - YAML template system, capability profiles, resource specs, agent presets: planner, safety, tool_runner

#### [ADR-0073](../../docs/architecture/decisions/0073-*.md): 0073 Lifecycle FSM

**Components:**

- **Lifecycle FSM** → WARMING State
  - File: `k1/l2_orchestration/lifecycle/warming_state.py`
  - 4-check validation: resources models capabilities supervisor, <35s timeout P95, health verification, M1 milestone

- **Lifecycle FSM** → IDLE State
  - File: `k1/l2_orchestration/lifecycle/idle_state.py`
  - Agent pooling, TTL management 60s default, health checks every 10s, AgentPoolManager, graceful eviction

- **Lifecycle FSM** → DRAINING State
  - File: `k1/l2_orchestration/lifecycle/draining_state.py`
  - Graceful shutdown, task completion tracking, <30s timeout P95, reject new tasks, TaskTracker integration


### Audit Trail (K0 Receipts)

#### [ADR-0038](../../docs/architecture/decisions/0038-*.md): 0038 Immutability

**Components:**

- **Immutability** → Append-Only Semantics
  - File: `k0/receipts/immutability.py`
  - 100% immutability (no UPDATE/DELETE operations), WAL append-only guarantees, Cryptographic hash chain detects tampering

- **Non-Repudiation** → Forensic Proof
  - File: `k0/receipts/forensics.py`
  - Cryptographic proof of user actions, SHA-256 hash chain (receipt.previous_hash → receipt.current_hash), Forensic-grade evidence for legal disputes

- **Integration** → Compliance Standards
  - File: `k0/compliance/standards.py`
  - GDPR Article 30 (record of processing), HIPAA §164.312(b) (audit controls), SOC2 CC7.2 (system monitoring), ISO 27001 Clause 12.4.1 (event logging)

#### [ADR-0038a](../../docs/architecture/decisions/0038a-*.md): 0038A Receipt Types

**Components:**

- **Receipt Types** → TurnReceipt
  - File: `k0/receipts/turn_receipt.py`
  - User message + agent response, GDPR Article 30 (record of processing), trace_id/session_id/timestamp, PII redacted

- **Receipt Types** → ToolReceipt
  - File: `k0/receipts/tool_receipt.py`
  - Tool execution + violations, HIPAA §164.312(b) (audit controls), tool_name/arguments/result/violation_type

- **Receipt Types** → StateReceipt
  - File: `k0/receipts/state_receipt.py`
  - SessionState delta changes, SOC2 CC7.2 (system monitoring), previous_hash/new_hash/section

- **Receipt Types** → AgentReceipt
  - File: `k0/receipts/agent_receipt.py`
  - Agent lifecycle events (hire/fire), SOC2 CC7.2 (system monitoring), agent_id/capabilities/state

- **Hash Chain** → SHA-256 Integrity
  - File: `k0/receipts/hash_chain.py`
  - SHA-256 hash (previous_hash + receipt_data), First receipt previous_hash = "0"×64, Chain verification on every query

- **Hash Chain** → Tamper Detection
  - File: `k0/receipts/hash_chain.py`
  - Verify previous_hash → current_hash continuity, Detect any modification/deletion, <10ms verification (100 receipts)

- **Serialization** → FlatBuffers
  - File: `k0/receipts/serializer.py`
  - <1ms receipt creation (vs 5ms JSON), Zero-copy deserialization, Cross-language compatibility (Rust ↔ Python), <0.3ms serialization

- **PII Redaction** → Privacy Compliance
  - File: `k0/receipts/pii_redactor.py`
  - Redact emails/phone/SSN in user messages, Redaction markers ([REDACTED:EMAIL], [REDACTED:SSN]), Band-specific redaction (RED aggressive, GREEN minimal)

#### [ADR-0038b](../../docs/architecture/decisions/0038b-*.md): 0038B WAL Integration

**Components:**

- **WAL Integration** → Append-Only Log
  - File: `k0/wal/receipt_log.py`
  - Write-Ahead Log (append-only), Sequential writes (5000+ writes/sec), No UPDATE/DELETE operations, Crash recovery via WAL replay

- **WAL Integration** → Async Write Pipeline
  - File: `k0/wal/async_writer.py`
  - mpsc::channel queue (10K receipts), Batch writing every 100ms or 100 receipts, <1ms queue insert (doesn't block turn), <10ms batch WAL write

- **WAL Integration** → Performance
  - File: `k0/wal/async_writer.py`
  - <5ms async write P95, 95% faster than 20ms sync DB insert, Throughput 1000 receipts/sec (vs 100/sec sync)

- **WAL Integration** → Backpressure Handling
  - File: `k0/wal/backpressure.py`
  - Queue full (10K receipts) → block new receipts, Emit alert (receipt_queue_full_total), Drop oldest (configurable)

- **WAL Integration** → Crash Recovery
  - File: `k0/wal/recovery.py`
  - WAL replay on K1 startup, Reconstruct hash chain from WAL, Verify integrity (no missing receipts)

#### [ADR-0038c](../../docs/architecture/decisions/0038c-*.md): 0038C Retention Policies

**Components:**

- **Retention Policies** → Band-Specific Retention
  - File: `k0/retention/policy_manager.py`
  - GREEN 365 days, AMBER 180 days, RED 90 days, Privacy-aware retention (RED data deleted sooner)

- **Retention Policies** → Auto-Deletion
  - File: `k0/retention/pruning_job.py`
  - Hourly pruning job, DELETE receipts WHERE timestamp < cutoff, Batch deletion (1000 receipts/batch), <5s pruning (10K receipts)

- **Retention Policies** → Deletion Audit Trail
  - File: `k0/retention/deletion_log.py`
  - Log deletion events (session_id/receipt_count/timestamp), Store in deletion_log table, Prove GDPR compliance

- **Retention Policies** → Storage Optimization
  - File: `k0/retention/vacuum.py`
  - 80% storage reduction after 1 year, Vacuum after deletion (reclaim disk space), Index maintenance (rebuild indexes)

#### [ADR-0038d](../../docs/architecture/decisions/0038d-*.md): 0038D Query Interface

**Components:**

- **Query Interface** → Session Receipts
  - File: `k0/receipts/query_api.py`
  - GET /api/receipts/session/{session_id}, <50ms P95 query, Filter by type (TURN/TOOL/STATE/AGENT), Filter by date range

- **Query Interface** → User Receipts
  - File: `k0/receipts/query_api.py`
  - GET /api/receipts/user/{user_id}, <500ms P95 query (multiple sessions), GDPR Article 15 (right to access)

- **Query Interface** → Hash Chain Verification
  - File: `k0/receipts/verification.py`
  - Verify on every query (detect tampering), Check previous_hash → current_hash continuity, <10ms verification (100 receipts), Return verification status

- **Query Interface** → Cache Optimization
  - File: `k0/receipts/cache.py`
  - Cache session receipts (10-min TTL), LRU eviction (1000 sessions max), >75% cache hit rate

- **Compliance Export** → GDPR Article 15 Export
  - File: `k0/compliance/gdpr_exporter.py`
  - User audit log export (JSON format), Include all receipt types, PII redacted + additional redaction for export, <2.4s export (250 receipts)

- **Compliance Export** → HIPAA PHI Access Report
  - File: `k0/compliance/hipaa_exporter.py`
  - §164.312(b) audit controls, PHI access report (who/what/when), ToolReceipt analysis for PHI access

- **Compliance Export** → SOC2 Security Event Log
  - File: `k0/compliance/soc2_exporter.py`
  - CC7.2 system monitoring, Security event log (errors/violations/anomalies), AgentReceipt + StateReceipt analysis


### Cursor-Based Pagination

#### [ADR-0023c](../../docs/architecture/decisions/0023c-*.md): 0023C K0 WAL Query

**Components:**

- **K0 WAL Query** → SQLite Index
  - File: `k0/wal_storage/indexes.sql`
  - CREATE INDEX idx_session_turn ON turns (session_id, turn_id), <50ms P95 indexed query


### E2EE

#### [ADR-0036](../../docs/architecture/decisions/0036-*.md): 0036 Zero-Knowledge Architecture

**Components:**

- **Zero-Knowledge Architecture** → Operator Isolation
  - File: `k0/encryption/zk_architecture.py`
  - K1 kernel cannot decrypt without user key, User key never stored in K0 (only in HSM/KMS), 100% protection from internal threats (DBAs, operators)

- **Zero-Knowledge Architecture** → Privacy Protection
  - File: `k0/encryption/zk_architecture.py`
  - 100% RED privacy protection, 0 plaintext leaks in 6 months, User sovereignty via BYOK, Database compromise doesn't expose keys

- **Integration** → Privacy Bands
  - File: `k0/encryption/privacy_bands.py`
  - Ties to ADR-0032 (Egress Control), RED band = E2EE required, GREEN/AMBER = no encryption (performance), BLACK = opt-out (user choice)

- **Integration** → Compliance
  - File: `k0/encryption/compliance.py`
  - GDPR (Article 25 data protection by design, Article 32 encryption at rest), HIPAA (45 CFR §164.312 AES-256 for PHI), User control (BYOK, sovereignty)

#### [ADR-0036a](../../docs/architecture/decisions/0036a-*.md): 0036A AES-256-GCM

**Components:**

- **AES-256-GCM** → Encryption Algorithm
  - File: `k0/encryption/aes_gcm.py`
  - NIST SP 800-38D standard, Authenticated encryption (confidentiality + integrity), 256-bit key + 96-bit nonce + 128-bit auth tag

- **AES-256-GCM** → Hardware Acceleration
  - File: `k0/encryption/aes_gcm.py`
  - AES-NI instruction set (5× speedup over software), Constant-time execution (prevents timing attacks), <1ms per SessionState section

- **AES-256-GCM** → Nonce Management
  - File: `k0/encryption/nonce_manager.py`
  - 96-bit nonce (2^96 unique values), Counter-based generation (never repeats), Nonce uniqueness enforcement (MUST not reuse with same key)

- **AES-256-GCM** → Authentication Tag
  - File: `k0/encryption/aes_gcm.py`
  - 128-bit GMAC tag, Verifies ciphertext integrity (prevents tampering), Computed over ciphertext + AAD (Additional Authenticated Data)

- **AES-256-GCM** → Quantum Resistance
  - File: `k0/encryption/aes_gcm.py`
  - 256-bit key secure against Grover's algorithm (2^128 operations required), NIST-approved for quantum-resistant encryption

#### [ADR-0036b](../../docs/architecture/decisions/0036b-*.md): 0036B KMS Integration

**Components:**

- **KMS Integration** → Key Providers
  - File: `k0/kms/provider_manager.py`
  - AWS KMS (FIPS 140-2 Level 2), Azure Key Vault (Level 2/3), Google Cloud KMS (Level 3), Local HSM (PKCS#11 interface)

- **KMS Integration** → Key Lifecycle
  - File: `k0/kms/lifecycle_manager.py`
  - Generate (256-bit on space creation), Store (HSM/KMS with space_id mapping), Rotate (90-day automatic), Revoke (immediate), Destroy (365-day retention)

- **KMS Integration** → Performance
  - File: `k0/kms/cache_manager.py`
  - Key fetch <50ms from KMS, Key caching for session duration (reduce KMS calls), Key generation <200ms (one-time per space), Key rotation <500ms (background job)

- **KMS Integration** → BYOK Support
  - File: `k0/kms/byok_manager.py`
  - User can import own 256-bit key, User controls key lifecycle (rotate/revoke), User can export encrypted data + key, Enterprise feature (compliance requirement)

- **KMS Integration** → Key Separation
  - File: `k0/kms/security.py`
  - Keys stored separately from encrypted data (K0 breach doesn't expose keys), Defense in depth (data in K0, keys in HSM/KMS)

#### [ADR-0036c](../../docs/architecture/decisions/0036c-*.md): 0036C Selective Encryption

**Components:**

- **Selective Encryption** → SessionState Integration
  - File: `k1/l2_state/session_state/e2ee_manager.py`
  - Integrate with SessionStateManager (ADR-0017), Encrypt before save to K0, Decrypt after load from K0, Handle encryption failures gracefully (fallback to plaintext with warning)

#### [ADR-0036d](../../docs/architecture/decisions/0036d-*.md): 0036D Audit Trail

**Components:**

- **Audit Trail** → E2EE Operation Logging
  - File: `k0/audit/e2ee_logger.py`
  - All E2EE operations logged (encrypt/decrypt/key_generate/rotate/revoke/delete), Tamper-evident append-only, Include timestamp/operation/space_id/user_id/key_id/band/trace_id/success

- **Audit Trail** → Retention
  - File: `k0/audit/e2ee_logger.py`
  - 7 years (GDPR/HIPAA requirement), <5ms async logging (non-blocking), <100ms audit query (indexed), Stored in K0 audit_log table

- **Audit Trail** → GDPR Compliance
  - File: `k0/audit/gdpr_e2ee_compliance.py`
  - Article 15 (right to access E2EE logs), Article 17 (delete keys on erasure), Article 30 (processing records), Article 32 (security measures)

- **Audit Trail** → HIPAA Compliance
  - File: `k0/audit/hipaa_e2ee_compliance.py`
  - §164.312(a)(1) access control, §164.312(b) audit controls (E2EE logs), §164.312(c)(1) integrity (detect unauthorized decryption), §164.312(e)(2)(ii) encryption audit trail

- **Audit Trail** → Production Metrics
  - File: `k0/audit/e2ee_metrics.py`
  - 1.4M E2EE operations logged (6 months, 120K sessions × 12 ops avg), 100% GDPR compliance (45 DSARs provided with logs), Security incident response capability

- **BYOK** → Documentation
  - File: `k0/kms/byok_docs.py`
  - User guide (generate/import encryption keys), Key export (backup), Key import (restore from backup), Key rotation (without service disruption)


### Embodied Awareness

#### [ADR-0085](../../docs/architecture/decisions/0085-*.md): 0085 Core Architecture

**Components:**

- **Core Architecture** → Multi-Device Presence
  - File: `k1/l1_input/streams/operators/device_presence.py`
  - 7 presence mechanisms (device presence, location awareness, BLE proximity, active session, motion sensors, power state, cross-device sharing), K0 P07 CRDT sync integration (ADR-0050), SessionState ...

#### [ADR-0085a](../../docs/architecture/decisions/0085a-*.md): 0085A Device Presence

**Components:**

- **Device Presence** → Device Switch Detection
  - File: `k1/l2_orchestration/presence/switch_detector.py`
  - Criteria (previous inactive, current active, <60s gap, proximity NEAR/MEDIUM), confidence scoring (timing 0.40, proximity 0.30, pattern 0.30), common switch pattern detection, session handoff sugge...

#### [ADR-0085c](../../docs/architecture/decisions/0085c-*.md): 0085C Context Sharing

**Components:**

- **Context Sharing** → Notification Coordinator
  - File: `k1/l2_orchestration/presence/notification_coordinator.py`
  - 4 routing rules (single active→send there, multiple active→most recent, no active→all devices, user override), active device filtering (screen ON, not IN_POCKET/IN_BAG, battery >20%), notification ...

- **Context Sharing** → Smart Handoff Suggester
  - File: `k1/l2_orchestration/presence/handoff_suggester.py`
  - Device switch detection (1Hz monitoring), handoff criteria (previous inactive, new active, <5min gap, proximity), 3 suggestion types (RESUME_CONVERSATION, CONTINUE_TASK, HANDOFF_MEDIA), session con...

- **Context Sharing** → Device Preference Learner
  - File: `k1/l2_orchestration/presence/preference_learner.py`
  - Usage pattern detection (task type, location, time of day, response length), 30-day sliding window, preference model (device_id, context)→score, daily model updates, preferred device prediction (>0...


### Enhanced HITL Protocols

#### [ADR-0052](../../docs/architecture/decisions/0052-*.md): 0052 Research Foundation

**Components:**

- **Research Foundation** → Grounding Theory
  - File: `docs/research/clark_brennan_1991_grounding.md`
  - Common ground theory (Clark & Brennan 1991), clarification as grounding act, HITL builds common ground

- **Research Foundation** → Error Prevention
  - File: `docs/research/norman_1988_design.md`
  - Forcing functions (Norman 1988), explicit confirmation prevents accidental actions, RED band approval design

- **Research Foundation** → Swiss Cheese Model
  - File: `docs/research/reason_1990_human_error.md`
  - Defense-in-depth safety layers (Reason 1990), multi-layered HITL prevents failures (anomaly + risk + explicit)

- **Research Foundation** → Session Types Validation
  - File: `docs/research/honda_2008_mpst.md`
  - Multiparty Session Types (Honda 2008), protocol validation for nested HITL interactions

- **Audit Trail** → 7-Year Retention
  - File: `k0/receipts/hitl_audit_log.py`
  - RED band approvals logged to K0 receipts, 7-year retention (SOC2/ISO27001 compliance)

- **Audit Trail** → HITL Audit Schema
  - File: `k1/schemas/flatbuffers/hitl_audit_record.fbs`
  - Full audit trail: who approved, when, what phrase, risk score, outcome (1KB per approval)

- **Testing** → WARD Integration Tests
  - File: `tests/integration/test_hitl_extensions.py`
  - Comprehensive HITL tests: step-by-step rollback, RED band phrases, nested go-back, proactive confidence

#### [ADR-0052a](../../docs/architecture/decisions/0052a-*.md): 0052A Step-by-Step Approval

**Components:**

- **Step-by-Step Approval** → Progressive Disclosure
  - File: `k1/l2_orchestrator/planner/step_by_step_handler.py`
  - Show 1 step at a time (Nielsen Norman 2006), per-step approval with rollback capability

- **Step-by-Step Approval** → Saga Pattern Rollback
  - File: `k1/l2_orchestrator/planner/saga_rollback.py`
  - Compensating transactions (Garcia-Molina 1987), rollback previous steps using Saga Pattern (ADR-0008)

- **Step-by-Step Approval** → Planner Integration
  - File: `k1/l2_orchestrator/planner/execution_phase.py`
  - Pause after Validate stage (ADR-0007), wait for user approval before Commit stage execution

- **Step-by-Step Approval** → Error Handling
  - File: `k1/l2_orchestrator/planner/step_error_handler.py`
  - Timeout (keep progress), step failure (retry/rollback/keep), network loss (pause workflow)

#### [ADR-0052b](../../docs/architecture/decisions/0052b-*.md): 0052B RED Band Approval

**Components:**

- **RED Band Approval** → Arbiter Risk Scoring
  - File: `k1/l2_orchestrator/arbiter/risk_scoring.py`
  - Risk score 0.0-1.0 (ADR-0007c), >0.7 triggers HIGH approval, >0.9 triggers CRITICAL (two-person)

- **RED Band Approval** → Audit Trail
  - File: `k0/receipts/red_band_audit.py`
  - 7-year retention to K0 receipts (ADR-0038), SOC2/ISO27001 compliance, immutable append-only logs

- **RED Band Approval** → RedBandAuditRecord
  - File: `k1/schemas/flatbuffers/red_band_audit.fbs`
  - Full audit: approval_id, operation, confidence_factors, phrase match result, approver IDs, execution result (1KB)

- **RED Band Approval** → Norman's Forcing Functions
  - File: `docs/research/norman_1988_forcing_functions.md`
  - Design of Everyday Things (Norman 1988), explicit phrase typing forces conscious confirmation

- **RED Band Approval** → Swiss Cheese Model
  - File: `docs/research/reason_1990_swiss_cheese.md`
  - Defense-in-depth (Reason 1990), RED band approval is one safety layer among many

#### [ADR-0052c](../../docs/architecture/decisions/0052c-*.md): 0052C Nested Clarifications

**Components:**

- **Nested Clarifications** → Grounding Theory
  - File: `docs/research/clark_brennan_1991_grounding.md`
  - Grounding in Communication (Clark & Brennan 1991), nested clarifications build common ground incrementally

- **Nested Clarifications** → QUD Theory
  - File: `docs/research/roberts_1996_qud.md`
  - Questions Under Discussion (Roberts 1996), QUD stack = hierarchical question structure

- **Nested Clarifications** → Multi-Turn Dialogue
  - File: `docs/research/jurafsky_martin_2020_dialogue.md`
  - Dialogue state tracking (Jurafsky & Martin 2020), ClarificationHistory is dialogue state for HITL chains

#### [ADR-0052d](../../docs/architecture/decisions/0052d-*.md): 0052D Proactive Confirmation

**Components:**

- **Proactive Confirmation** → Confidence Scoring
  - File: `k1/l2_orchestrator/planner/confidence_calculator.py`
  - 6 factors: domain_match, context_completeness, plan_similarity, prerequisite_check, user_preference_alignment, side_effect_assessment

- **Proactive Confirmation** → Confidence Factor Weights
  - File: `k1/config/proactive_confirmation.yml`
  - Weights sum to 1.0: domain_match 0.20, context_completeness 0.25, plan_similarity 0.15, prerequisite 0.20, alignment 0.10, side_effects 0.10

- **Proactive Confirmation** → Confidence Penalties
  - File: `k1/l2_orchestrator/planner/confidence_calculator.py`
  - Irreversible actions 0.9× penalty, AMBER privacy 0.85× penalty, RED privacy 0.75× penalty

- **Proactive Confirmation** → ConfidenceFactor
  - File: `k1/schemas/flatbuffers/confidence_factor.fbs`
  - Breakdown: factor_name, score (0.0-1.0), weight, explanation (why this score)

- **Proactive Confirmation** → ProactiveConfirmationRecord
  - File: `k1/schemas/flatbuffers/proactive_confirmation.fbs`
  - K0 receipts audit: decision_id, confidence_score, reasoning, user_response (proceeded/retried/cancelled), outcome, feedback_signal

- **Proactive Confirmation** → Feedback Signals
  - File: `k0/learning/feedback_integration.py`
  - 1.0 (agent was right), 0.5 (partial correctness), 0.0 (agent was wrong), feed to Learning Loop (ADR-0059)


### Fast/Smart Lane Router

#### [ADR-0049](../../docs/architecture/decisions/0049-*.md): 0049 Configuration

**Components:**

- **Configuration** → Router Config
  - File: `k1/config/k0_bridge.yml`
  - Configurable weights, hot-reload via Config Manager, feature flag lane_router.enabled


### FlatBuffers

#### [ADR-0011a](../../docs/architecture/decisions/0011a-*.md): 0011A Schema Design

**Components:**

- **Schema Design** → Schema Validator
  - File: `tools/schema_validator.py`
  - Schema validation, file identifier checks, root type validation, compile-time errors

- **Schema Design** → Naming Conventions
  - File: `contracts/flatbuffers/naming.yml`
  - PascalCase tables, snake_case fields, UPPER_SNAKE_CASE enums, 4-char file IDs

- **Schema Design** → Type System
  - File: `contracts/flatbuffers/type_system.yml`
  - Scalars, vectors, strings, tables, unions, enums, structs, value types

- **Schema Design** → Forward Compatibility
  - File: `contracts/flatbuffers/compatibility.yml`
  - Optional fields, default values, no removals, union polymorphism

- **Schema Design** → Deprecation Policy
  - File: `contracts/flatbuffers/deprecation.yml`
  - 3-release grace period, (deprecated) attribute, migration guides

- **Schema Design** → Schema Registry
  - File: `k1/schemas/SCHEMA_VERSIONS.md`
  - 76 schemas, file ID→version mapping, introduced/deprecated/removed tracking

#### [ADR-0011b](../../docs/architecture/decisions/0011b-*.md): 0011B Code Generation

**Components:**

- **Code Generation** → flatc Compiler
  - File: `tools/flatc/wrapper.py`
  - v23.5.26, Python/C++/Rust bindings, --gen-object-api, <100ms compilation

- **Code Generation** → Python Bindings
  - File: `k1/schemas/generated/python/`
  - AgentState, TaskAnnouncement, SessionState, 76 generated modules

- **Code Generation** → C++ Bindings
  - File: `k1/schemas/generated/cpp/`
  - agent_state_generated.h, FlatBufferBuilder, C++17 concepts

- **Code Generation** → Rust Bindings
  - File: `k1/schemas/generated/rust/`
  - Cargo crate, flatbuffers::FlatBufferBuilder, Rust 1.70

- **Code Generation** → Build Integration
  - File: `CMakeLists.txt`
  - CMake add_custom_target, Bazel flatbuffer_library, setup.py build_py

- **Code Generation** → Type Stubs
  - File: `k1/schemas/types.py`
  - Python type hints, mypy support, IDE autocomplete, type-safe APIs

- **Code Generation** → CI Validation
  - File: `ci/validate_schemas.sh`
  - Schema compilation checks, breaking change detection, pre-commit hooks

#### [ADR-0011c](../../docs/architecture/decisions/0011c-*.md): 0011C Performance

**Components:**

- **Performance** → Benchmarks
  - File: `tests/performance/flatbuffers_bench.py`
  - SessionState 64KB <1ms serialize, <0.1ms deserialize, 11× throughput vs JSON

#### [ADR-0011d](../../docs/architecture/decisions/0011d-*.md): 0011D Schema Evolution

**Components:**

- **Schema Evolution** → Version Registry
  - File: `k1/schemas/SCHEMA_VERSIONS.md`
  - major.minor versioning, introduced/deprecated/removed tracking, 4-char file IDs

- **Schema Evolution** → Backward Compatibility
  - File: `contracts/flatbuffers/backward_compat.yml`
  - Add optional fields, new enum values, new tables, deprecation allowed

- **Schema Evolution** → Forward Compatibility
  - File: `contracts/flatbuffers/forward_compat.yml`
  - Ignore unknown fields, default values, unknown enum handling

- **Schema Evolution** → Migration Scripts
  - File: `scripts/migrate_schema.py`
  - Automated migration, field renaming, type changes, 3-release timeline

- **Schema Evolution** → Schema Diff Tool
  - File: `scripts/schema_diff.py`
  - Detect changes, breaking change alerts, version comparison


### FlatBuffers Schemas

#### [ADR-0012](../../docs/architecture/decisions/0012-*.md): 0012 Schema Taxonomy

**Components:**

- **Schema Taxonomy** → Complete Inventory
  - File: `k1/schemas/SCHEMA_INVENTORY.md`
  - 76 schemas total, 9 categories, hybrid architecture coverage (pure actors + AI agents)

- **Schema Taxonomy** → Category Organization
  - File: `k1/schemas/`
  - Base Types 5, K0 Pipelines 20, Agent Contracts 8, State 6, Model Hub 7, Tools 5, Protocol 6, Observability 5, WebSocket 7, Infrastructure 7

- **Schema Taxonomy** → File Structure
  - File: `k1/schemas/{category}/{entity}.fbs`
  - PascalCase tables, snake_case fields, 4-char file IDs, category-based organization

- **Schema Taxonomy** → Decision Matrix
  - File: `docs/architecture/decisions/0012-76-flatbuffers-schemas.md`
  - 76 schemas selected 9/10 vs 5 alternatives (fewer 3/10, Protobuf 6/10, more 5/10, monolithic 2/10)

- **Schema Taxonomy** → Design Patterns
  - File: `k1/schemas/PATTERNS.md`
  - 6 patterns: Request/Response Pairs, Agent Messages, SessionState, StateDelta, Protocol Events, Observability

- **File Identifiers** → Registry
  - File: `k1/schemas/FILE_IDENTIFIERS.md`
  - 76 4-char codes (AGST, TASK, PROP, SEST, BLFS, TDEF, MREQ, HREQ, AUDF, CFGS, METS, BPSG, etc.)

- **File Identifiers** → Validation
  - File: `k1/schemas/validators/file_id_validator.py`
  - File ID uniqueness checks, collision detection, identifier format validation

- **Schema Versioning** → Version Strategy
  - File: `k1/schemas/VERSIONING.md`
  - v1.0-v1.2, forward/backward compatibility, 3-release deprecation window

- **Schema Versioning** → Evolution Rules
  - File: `contracts/flatbuffers/evolution.yml`
  - Optional fields, default values, no removals, union polymorphism, migration scripts

- **Schema Versioning** → Breaking Changes
  - File: `docs/architecture/SCHEMA_CHANGES.md`
  - Change tracking, impact analysis, migration guides, CI validation

- **Performance** → Serialization Budgets
  - File: `k1/schemas/PERFORMANCE.md`
  - <0.5-3.2ms serialize (depends on size), <0.1-0.5ms deserialize, zero-copy optimization

- **Performance** → Size Efficiency
  - File: `k1/schemas/BENCHMARKS.md`
  - 1× FlatBuffers vs JSON 3×, 64KB SessionState, 256B-64KB typical schemas, 150× faster

- **Code Generation** → flatc Compiler
  - File: `tools/flatc/k1_compile_schemas.py`
  - v23.5.26, <10s compilation for all 76 schemas, --gen-object-api flag

- **Code Generation** → Python Bindings
  - File: `k1/schemas/generated/python/`
  - 228 generated files (76 schemas × 3 files/schema avg), imports, type hints

- **Code Generation** → C++ Bindings
  - File: `k1/schemas/generated/cpp/`
  - *_generated.h headers, FlatBufferBuilder, C++17 concepts, constexpr support

- **Code Generation** → Rust Bindings
  - File: `k1/schemas/generated/rust/`
  - Cargo crate flatbuffers-k1, FlatBufferBuilder, Rust 1.70+, future support

- **Code Generation** → Build Scripts
  - File: `scripts/generate_schemas.py`
  - CI integration, pre-commit hooks, incremental compilation, dependency tracking

- **Testing** → Contract Testing
  - File: `tests/schemas/test_contracts.py`
  - Schema round-trip tests, compatibility tests, breaking change detection

- **Testing** → Schema Fixtures
  - File: `tests/schemas/fixtures/`
  - Sample data for all 76 schemas, valid/invalid cases, edge cases

- **Testing** → Performance Tests
  - File: `tests/schemas/test_performance.py`
  - Serialization latency tests, memory usage tests, benchmark regression detection

- **Documentation** → Schema Catalog
  - File: `docs/schemas/CATALOG.md`
  - Complete reference: all 76 schemas, fields, types, examples, use cases

- **Documentation** → Integration Guide
  - File: `docs/schemas/INTEGRATION.md`
  - How to use schemas in K1 modules, best practices, common patterns, anti-patterns

#### [ADR-0012b](../../docs/architecture/decisions/0012b-*.md): 0012B Layer 2 Schemas

**Components:**

- **Layer 2 Schemas** → SessionState Root
  - File: `k1/l2_state/session_state/schemas/`
  - SessionStateRoot SEST, 6 sections, 64KB soft/128KB hard limits, 3-tier eviction

- **Layer 2 Schemas** → Beliefs Section
  - File: `k1/l2_state/session_state/schemas/`
  - BeliefsSection BLFS, 16KB soft limit, user facts/world knowledge/temporal/spatial

- **Layer 2 Schemas** → Scoreboard Section
  - File: `k1/l2_state/session_state/schemas/`
  - ScoreboardSection SCBS, 8KB soft limit, agent scores/tool scores

- **Layer 2 Schemas** → Control Section
  - File: `k1/l2_state/session_state/schemas/`
  - ControlSection CTRL, 12KB soft limit, active tasks/proposals/saga checkpoints/backpressure

- **Layer 2 Schemas** → Persona Section
  - File: `k1/l2_state/session_state/schemas/`
  - PersonaSection PERS, 8KB soft limit, privacy band GREEN/AMBER/RED, preferences, interaction history

- **Layer 2 Schemas** → Multimodal Section
  - File: `k1/l2_state/session_state/schemas/`
  - MultimodalSection MMSE, 16KB soft limit, audio chunks/transcripts/visual context

- **Layer 2 Schemas** → Meta Section
  - File: `k1/l2_state/session_state/schemas/`
  - MetaSection META, 4KB soft limit, trace_id, turn_number, timestamps, memory totals

- **Layer 2 Schemas** → Memory Manager
  - File: `k1/l2_state/memory_manager/schemas/`
  - MemorySnapshot MSNP, EvictionCandidate EVCT, MemoryUsage MUSG, PersistenceCheckpoint PCHK

- **Layer 2 Schemas** → Receipt System
  - File: `k1/l2_state/receipt_system/schemas/`
  - Receipt ROOT, ReceiptEntry RENT, ReceiptQuery RQRY

- **Layer 2 Schemas** → K0 Bridge
  - File: `k1/l2_state/k0_bridge/schemas/`
  - K0CommandRequest K0CR, K0CommandResponse K0RS, K0BatchRequest K0BR, K0BatchResponse K0BS, K0Receipt K0RC

- **Performance** → Memory Budgets
  - File: `k1/l2_state/session_state/memory_budget.yml`
  - Hot tier 0-64KB, Warm tier 64-96KB, Cold tier 96-128KB, eviction policies


### FlatBuffers SessionState Serialization

#### [ADR-0019](../../docs/architecture/decisions/0019-*.md): 0019 Serialization Core

**Components:**

- **Serialization Core** → Schema Validation
  - File: `k1/schemas/session_state/validator.py`
  - Compile-time type safety, FlatBuffers compiler, 18 bugs caught

#### [ADR-0019a](../../docs/architecture/decisions/0019a-*.md): 0019A Schema Definition

**Components:**

- **Schema Definition** → Root Schema
  - File: `k1/schemas/session_state/session_state_root.fbs`
  - SessionStateRoot container, all 6 sections + metadata, schema_version SemVer 2.0

- **Schema Definition** → Delta Schema
  - File: `k1/schemas/session_state/session_state_delta.fbs`
  - SessionStateDelta, nullable sections (only changed), changed_sections array

- **Schema Definition** → Beliefs Section Schema
  - File: `k1/schemas/session_state/sections/beliefs_section.fbs`
  - Fact storage (key-value with confidence), LRU order, privacy band, 10-20KB size

- **Schema Definition** → Scoreboard Section Schema
  - File: `k1/schemas/session_state/sections/scoreboard_section.fbs`
  - Entity tracking (referents, salience), QUD stack, common ground, 4-8KB size

- **Schema Definition** → Control Section Schema
  - File: `k1/schemas/session_state/sections/control_section.fbs`
  - Agent leases (30s expiry), flow state (3-phase), turn lock, budget tracker, 8-12KB size

- **Schema Definition** → Persona Section Schema
  - File: `k1/schemas/session_state/sections/persona_section.fbs`
  - Personality traits (Big Five OCEAN), communication style (tone, verbosity, humor), voice continuity (prosody controls, voice history, emotional state), self-model (capabilities, consistency validat...

- **Schema Definition** → Multimodal Section Schema
  - File: `k1/schemas/session_state/sections/multimodal_section.fbs`
  - Audio buffers (K0 blob pointers), vision embeddings (CLIP 512-dim), streaming state, ambient context (room occupancy, PIR/mmWave sensors), multi-party conversations (active speakers, voice biometri...

- **Schema Definition** → Meta Section Schema
  - File: `k1/schemas/session_state/sections/meta_section.fbs`
  - Telemetry (session duration, turn counts), performance metrics (TTFT, E2E), Prometheus export, 2-4KB size

- **Schema Definition** → Type Definitions
  - File: `k1/schemas/session_state/types/`
  - Fact, Entity, AgentLease, PersonalityTrait, AudioBuffer, VisionEmbedding, PerformanceMetrics

- **Schema Definition** → Enum Definitions
  - File: `k1/schemas/session_state/enums/`
  - PrivacyBand (GREEN, AMBER, RED), AgentState (PENDING, ACTIVE, etc.), FlowPhase (NEGOTIATION, SELECTION, EXECUTION)


### HITL Schema Integration

#### [ADR-0052e](../../docs/architecture/decisions/0052e-*.md): 0052E Layer 2 State

**Components:**

- **Layer 2 State** → Workflow State Schema
  - File: `k1/contracts/flatbuffers/layer2_state/workflow_state.fbs`
  - HITL workflow state, K0 WAL persistence, state machine tracking, session integration

- **Layer 2 State** → Clarification History Schema
  - File: `k1/contracts/flatbuffers/layer2_state/clarification_history.fbs`
  - Historical clarifications, session state storage, pattern analysis, user preferences

- **Layer 2 State** → HITL Audit Schema
  - File: `k1/contracts/flatbuffers/layer2_state/hitl_audit.fbs`
  - RED band audit records, K0 receipts 7-year retention, compliance logging, GDPR support


### JWT Authentication

#### [ADR-0037d](../../docs/architecture/decisions/0037d-*.md): 0037D Session Binding

**Components:**

- **Session Binding** → SessionState Integration
  - File: `k1/l2_state/session_state/jwt_binder.py`
  - JWT claims → SessionState metadata (user_id/space_id/roles/privacy_band/capabilities), User context available to all agents, Immutable for session lifetime


### K0 Bridge Batching

#### [ADR-0022d](../../docs/architecture/decisions/0022d-*.md): 0022D FlatBuffers Schema

**Components:**

- **FlatBuffers Schema** → Batch Schema
  - File: `k1/schemas/k0_bridge/batch.fbs`
  - ReceiptBatch table, array of receipts, compression flag, batch_id, sequence_number

- **FlatBuffers Schema** → Zero-Copy Batch
  - File: `k1/schemas/k0_bridge/batch.fbs`
  - Zero-copy deserialization, direct buffer access, <0.1ms deserialize, 150× faster vs JSON

- **FlatBuffers Schema** → Batch Metadata
  - File: `k1/schemas/k0_bridge/batch.fbs`
  - batch_id, sequence_number, receipt_count, total_size_bytes, compression_algorithm, timestamp_ms


### K0 Core

#### [ADR-0001](../../docs/architecture/decisions/0001-*.md): 0001 Memory Kernel

**Components:**

- **Memory Kernel** → P01-P20 Pipelines
  - File: `k0/pipelines/`
  - RecallQuery, MemoryWrite, AttentionGate, Hippocampus, FeedbackIntegration, SelfModelUpdate

- **Memory Kernel** → Durable Storage
  - File: `k0/storage/`
  - WAL, receipts, SQLite (hot), Parquet (cold), ACID guarantees

#### [ADR-0001f](../../docs/architecture/decisions/0001f-*.md): 0001F Memory Kernel

**Components:**

- **Memory Kernel** → Multi-Store
  - File: `k0/stores/`
  - Episodic, semantic, procedural, snapshots, affect, self-model, social

#### [ADR-0081](../../docs/architecture/decisions/0081-*.md): 0081 Knowledge Graph

**Components:**

- **Knowledge Graph** → Graph Schema
  - File: `k0/drivers/sqlite_kg.py`
  - 3-table design (nodes, edges, temporal_edges), entity types (Person, Location, Event, Organization, Thing), relationship types (parent, child, sibling, spouse, friend, employed_by, located_at, part...

- **Knowledge Graph** → Temporal Edges
  - File: `k0/kg/temporal_edges.py`
  - Relationship evolution tracking, bitemporal support (valid_from/valid_to for relationship evolution, created_at for insertion time), historical relationship queries, timeline queries ("Who was Alic...

- **Knowledge Graph** → Query API
  - File: `k0/query/kg_temporal.py`
  - 4 query categories (entity lookup, relationship queries, temporal queries, graph traversal), timeline queries with temporal edge filtering, entity lookup <10ms P95, relationship traversal <50ms P95...

- **Knowledge Graph** → Graph Traversal
  - File: `k0/kg/traversal.py`
  - BFS (Breadth-First Search) for shortest path in unweighted graphs O(V+E), DFS (Depth-First Search) for cycle detection and reachability O(V+E), Dijkstra for shortest path in weighted graphs O((V+E)...

- **Knowledge Graph** → Episodic Integration
  - File: `k0/kg/episodic_integration.py`
  - 4-stage extraction pipeline (NER → relationship extraction → entity resolution → KG update), P03 Consolidation integration (episodic → semantic → KG), spaCy en_core_web_lg model (96% accuracy), con...

- **Knowledge Graph** → Entity Extractor
  - File: `k0/kg/entity_extractor.py`
  - spaCy NER integration for Named Entity Recognition (PERSON, GPE, DATE, ORG), dependency parsing for relationship identification (nsubj, dobj, prep), pattern matching for relationship extraction, en...

- **Knowledge Graph** → Visualization
  - File: `k0/kg/visualization.py`
  - Mermaid export (graph LR format for ADRs and design docs), GraphML export (XML format for Gephi/Cytoscape/yEd), JSON export (structured format for API responses and programmatic access), debugging ...

- **Knowledge Graph** → KG Metrics
  - File: `k0/kg/metrics.py`
  - Real-time metrics (node count, edge count, query latency P50/P95/P99, entity resolution accuracy), historical trends (graph growth over time, query performance degradation), alerts (query latency >...

#### [ADR-0081a](../../docs/architecture/decisions/0081a-*.md): 0081A Knowledge Graph

**Components:**

- **Knowledge Graph** → Graph Schema
  - File: `k0/drivers/sqlite_kg.py`
  - 3-table design (nodes, edges, temporal_edges), entity types (Person, Location, Event, Organization, Thing), relationship types (parent, child, sibling, spouse, friend, employed_by, located_at, part...

- **Knowledge Graph** → Temporal Edges
  - File: `k0/kg/temporal_edges.py`
  - Relationship evolution tracking, bitemporal support (valid_from/valid_to for relationship evolution, created_at for insertion time), historical relationship queries, timeline queries ("Who was Alic...

#### [ADR-0081b](../../docs/architecture/decisions/0081b-*.md): 0081B Knowledge Graph

**Components:**

- **Knowledge Graph** → Query API
  - File: `k0/query/kg_temporal.py`
  - 4 query categories (entity lookup, relationship queries, temporal queries, graph traversal), timeline queries with temporal edge filtering, entity lookup <10ms P95, relationship traversal <50ms P95...

- **Knowledge Graph** → Graph Traversal
  - File: `k0/kg/traversal.py`
  - BFS (Breadth-First Search) for shortest path in unweighted graphs O(V+E), DFS (Depth-First Search) for cycle detection and reachability O(V+E), Dijkstra for shortest path in weighted graphs O((V+E)...

#### [ADR-0081c](../../docs/architecture/decisions/0081c-*.md): 0081C Knowledge Graph

**Components:**

- **Knowledge Graph** → Episodic Integration
  - File: `k0/kg/episodic_integration.py`
  - 4-stage extraction pipeline (NER → relationship extraction → entity resolution → KG update), P03 Consolidation integration (episodic → semantic → KG), spaCy en_core_web_lg model (96% accuracy), con...

- **Knowledge Graph** → Entity Extractor
  - File: `k0/kg/entity_extractor.py`
  - spaCy NER integration for Named Entity Recognition (PERSON, GPE, DATE, ORG), dependency parsing for relationship identification (nsubj, dobj, prep), pattern matching for relationship extraction, en...

#### [ADR-0081d](../../docs/architecture/decisions/0081d-*.md): 0081D Knowledge Graph

**Components:**

- **Knowledge Graph** → Visualization
  - File: `k0/kg/visualization.py`
  - Mermaid export (graph LR format for ADRs and design docs), GraphML export (XML format for Gephi/Cytoscape/yEd), JSON export (structured format for API responses and programmatic access), debugging ...

- **Knowledge Graph** → KG Metrics
  - File: `k0/kg/metrics.py`
  - Real-time metrics (node count, edge count, query latency P50/P95/P99, entity resolution accuracy), historical trends (graph growth over time, query performance degradation), alerts (query latency >...


### K0 Memory Consolidation

#### [ADR-0084](../../docs/architecture/decisions/0084-*.md): 0084 Core Architecture

**Components:**

- **Core Architecture** → 3-Layer Pipeline
  - File: `k0/consolidation/`
  - 5 consolidation processes (Hippocampal replay, Neocortical integration, Synaptic homeostasis, KG consolidation, Dream exploration), 90-minute sleep cycles (NREM Phase 1 45min, NREM Phase 2 30min, R...

- **Core Architecture** → Sleep Coordination
  - File: `k0/consolidation/scheduler.py`
  - SLEEP_SCHEDULER idle detection (CPU <5% for 15min, 2AM-5AM preferred, battery >30%), SLEEP_STATE_MACHINE (IDLE→NREM1→NREM2→REM→WAKING→IDLE), SLEEP_TRIGGER event coordination, K0 Offsets progress tr...

- **Core Architecture** → P03 Pipeline Integration
  - File: `k0/pipelines/p03_consolidation.py`
  - K0 WAL (evt_wal) → P03 fan-out, batch processing (1000 events/batch), priority LOW (nice +10), pausable on user activity, 5 consolidation handlers (CONS_HIPPOCAMPAL, CONS_NEOCORTICAL, CONS_SYNAPTIC...

- **Neocortical Integration** → Episodic→Semantic Transform
  - File: `k0/consolidation/neocortical_integration.py`
  - Pattern extraction (temporal patterns, location sequences, entity generalizations), embedding clustering (threshold 0.85), frequency threshold (≥3 occurrences), confidence scoring (≥0.70 to qualify...

- **Neocortical Integration** → Semantic Memory Creation
  - File: `k0/storage/semantic_memories.py`
  - K0::st_sqlite[semantic_memories] storage, pattern types (routine, preference, habit, concept), common entities/actions/temporal context extraction, source episode references, consolidation criteria...

- **Synaptic Homeostasis** → Forgetting & Pruning
  - File: `k0/consolidation/synaptic_homeostasis.py`
  - Stale data detector (last_accessed_ts >90 days, access_count=0, emotional_salience <0.30), Ebbinghaus exponential decay (retention = base^(-time/half_life), base=0.5, half_life=30 days), weak conne...

- **Synaptic Homeostasis** → Archival & Compression
  - File: `k0/storage/archived_memories.py`
  - K0::st_sqlite[archived_memories] table, archive criteria (>90 days, access_count=0, low salience), LZ4 compression, rollups/summaries (P15 integration), SQLite VACUUM every 30 days, ≥30% storage re...

#### [ADR-0084a](../../docs/architecture/decisions/0084a-*.md): 0084A Hippocampal Replay

**Components:**

- **Hippocampal Replay** → Pattern Strengthening
  - File: `k0/consolidation/hippocampal_replay.py`
  - CA3_CONSOLIDATION coordinator, 10-20x accelerated replay, 100-150 memories/NREM Phase 1, emotional salience prioritization (2x replay cycles for salience ≥0.70), access frequency weighting, recency...

- **Hippocampal Replay** → CA3 Recurrent Activation
  - File: `k0/ca3/recurrent_network.py`
  - CA3_RECURRENT association retrieval (~5-10 associated nodes per memory), temporal proximity (co-occurred within 5min), semantic similarity (embedding cosine ≥0.75), causal relationships (from KG_CA...

- **Hippocampal Replay** → Synaptic Strengthening
  - File: `k0/consolidation/synaptic_strengthening.py`
  - Hebbian learning (Δw = η *activation_src* activation_dst, η=0.03), Long-Term Potentiation (LTP) simulation (3+ replays →+10% weight boost), max weight 1.0, asymptotic saturation, replay speed modul...

- **Hippocampal Replay** → Theta Rhythm Coordination
  - File: `k0/ca1/theta_rhythm.py`
  - CA1_THETA oscillation generator (4-8 Hz), NREM theta 4-6 Hz (slow, consolidation), REM theta 6-8 Hz (fast, exploration), theta phase precession (encoding phase π-2π, retrieval phase 0-π), theta-gat...

#### [ADR-0084b](../../docs/architecture/decisions/0084b-*.md): 0084B Sleep State Machine

**Components:**

- **Sleep State Machine** → Idle Detection
  - File: `k0/consolidation/scheduler.py`
  - CPU <5% for 15min window, preferred 2AM-5AM, no user input (keyboard/mouse/touchscreen), battery >30%, Command Port queue <10 entries, fallback (any 3-hour idle), manual trigger (k0ctl consolidate ...

- **Sleep State Machine** → State Orchestration
  - File: `k0/consolidation/state_machine.py`
  - 5 states (IDLE, NREM_PHASE_1, NREM_PHASE_2, REM_PHASE, WAKING), 90-minute ultradian cycles, state durations (NREM1 45min, NREM2 30min, REM 15min, Waking 5min), interruption handling (pause on user ...

- **Sleep State Machine** → NREM Phase 1 Handler
  - File: `k0/consolidation/nrem_phase_1_handler.py`
  - Hippocampal replay execution (ADR-0084a integration), CA3_CONSOLIDATION coordination, 100-150 memories replayed, theta rhythm 4-6 Hz (slow theta), 45-minute phase duration, 2-3 memories/minute repl...

- **Sleep State Machine** → NREM Phase 2 Handler
  - File: `k0/consolidation/nrem_phase_2_handler.py`
  - Synaptic homeostasis (pruning), neocortical integration (episodic→semantic), 50-100 patterns extracted, 500-1000 connections pruned, knowledge graph consolidation, 30-minute phase duration, paralle...

- **Sleep State Machine** → REM Phase Handler
  - File: `k0/consolidation/rem_phase_handler.py`
  - Dream exploration (ADR-0084d integration), theta rhythm 6-8 Hz (fast theta), 5-10 insights generated, 3-5 counterfactuals, 5-10 skills rehearsed, 3-5 reflection prompts, 15-minute phase duration, c...

- **Sleep State Machine** → Waking Phase Handler
  - File: `k0/consolidation/waking_phase_handler.py`
  - Flush pending writes, P13 Index Rebuild integration, consolidation summary generation, infra.consolidation.complete event emission (cycle stats: memories_consolidated, patterns_extracted, insights_...

- **Resource Management** → CPU Priority & Affinity
  - File: `k0/consolidation/resource_limits.py`
  - Nice +10 (low CPU priority), ionice idle (Linux), CPU affinity (last 2 cores), BELOW_NORMAL_PRIORITY_CLASS (Windows), <5% average CPU usage, pausable on user activity, yield to user processes

- **Resource Management** → Memory & Disk Limits
  - File: `k0/consolidation/resource_limits.py`
  - Memory cap 256 MB (resource.setrlimit), batch size 1000 events (prevents memory spikes), disk I/O <5 MB/s, ionice idle class, async writes, fsync every 5min, pause if battery <30%, reduce frequency...

#### [ADR-0084c](../../docs/architecture/decisions/0084c-*.md): 0084C Knowledge Graph Consol.

**Components:**

- **Knowledge Graph Consol.** → Entity Extraction
  - File: `k0/consolidation/kg_consolidation.py`
  - 7 entity types (PERSON, PLACE, ORGANIZATION, CONCEPT, EVENT, TEMPORAL, OBJECT), Named Entity Recognition (NER) via linguistic_mapping, embedding clustering (threshold 0.85), canonical entity creati...

- **Knowledge Graph Consol.** → Relationship Inference
  - File: `k0/kg/relation_discovery.py`
  - 6 relationship types (CAUSAL, TEMPORAL, ASSOCIATIVE, HIERARCHICAL, POSSESSIVE, SOCIAL), co-occurrence detection (≥3 instances, temporal proximity <5min), KG_CAUSAL_GRAPH integration, PMI associatio...

- **Knowledge Graph Consol.** → Schema Evolution
  - File: `k0/kg/concept_evolution.py`
  - KG_CONCEPT_EVOLUTION engine, schema change detection (new entity/relation types ≥10/5 instances), concept merge/split, version control (K0::st_kg[schema_versions]), migration with rollback support,...

- **Knowledge Graph Consol.** → Temporal Reasoning
  - File: `k0/kg/temporal.py`
  - KG_TEMPORAL_ENGINE, time-stamped snapshots (node_id, timestamp, properties), 365-day retention, historical state queries ("What were Alice's interests last month?"), temporal range queries (track c...

#### [ADR-0084d](../../docs/architecture/decisions/0084d-*.md): 0084D Dream Exploration

**Components:**

- **Dream Exploration** → Explorative Dreaming
  - File: `k0/consolidation/dream_exploration.py`
  - DREAM_EXPLORATION semantic space random walks, K0::st_vector traversal, temperature-based sampling (0.70 balanced exploration/exploitation), 50 steps per REM phase, novel association detection (sem...

- **Dream Exploration** → Counterfactual Thinking
  - File: `k0/consolidation/counterfactual_simulator.py`
  - SIM_COUNTERFACTUAL integration, decision point identification, alternative sequence generation, KG_CAUSAL_GRAPH outcome prediction, 3-5 scenarios per REM Phase, counterfactual learning (better alte...

- **Dream Exploration** → Mental Rehearsal
  - File: `k0/consolidation/mental_rehearsal.py`
  - DREAM_REHEARSAL motor skill practice, K0::st_sqlite[motor_programs] simulation, procedural memory strengthening (rehearsal_count++, execution_speed *= 0.95, error_rate*= 0.90), 5-10 skills rehearse...

- **Dream Exploration** → Reflection Prompts
  - File: `k0/consolidation/reflection_prompt_generator.py`
  - 5 prompt types (MEMORY_GAP, UNRESOLVED_THREAD, GOAL_PROGRESS, EMOTIONAL_TREND, HABIT_INSIGHT), memory gap detection (expected events not logged), unresolved thread analysis (goals without progress)...


### K0 SSE Event Streaming

#### [ADR-0042a](../../docs/architecture/decisions/0042a-*.md): 0042A Event Production

**Components:**

- **Event Production** → WALReader Cursor-Based
  - File: `k0/sse/wal_reader.py`
  - Reads durable events from K0 WAL (config, receipts, learning, CRDT), 10ms polling interval, continuous background task, batch reading (max 100 events)

- **Event Production** → FanoutManager 1-to-N
  - File: `k0/sse/fanout_manager.py`
  - 1-to-N broadcasting (single K0 event → N K1 instances), topic-based filtering (wildcard patterns), <10ms delivery latency

- **Event Production** → TopicFilter Wildcard
  - File: `k0/sse/topic_filter.py`
  - Wildcard pattern matching (k0.config.* matches all config events), subscription filtering, future-proof subscriptions

- **Event Production** → EventBatcher Compression
  - File: `k0/sse/event_batcher.py`
  - Compression + batching for event delivery, zstd compression level 3, reduces bandwidth 40-60%

#### [ADR-0042d](../../docs/architecture/decisions/0042d-*.md): 0042D Backpressure

**Components:**

- **Backpressure** → K0BackpressureMonitor
  - File: `k0/sse/backpressure_monitor.py`
  - Detect slow consumers (>10K unACKed events OR >30s lag), track lag time (latest event - last ACK timestamp), emit backpressure metrics

- **Backpressure** → ConsumerDisconnector
  - File: `k0/sse/consumer_disconnector.py`
  - Graceful disconnect with reason (backpressure exceeded), protect K0 from slow consumers, K1 reconnects and catches up via replay

- **Persistence** → WALRetentionManager Cloud
  - File: `k0/wal/retention_manager_cloud.py`
  - Cloud Tier: 7-90 day retention policy (77GB WAL), daily compaction, delete old events (reclaim disk space)

- **Persistence** → WALCompactor
  - File: `k0/wal/compactor.py`
  - Delete old events from K0 WAL, reclaim disk space, efficient storage, optimize replay performance


### K1 Core

#### [ADR-0001](../../docs/architecture/decisions/0001-*.md): 0001 Memory Kernel

**Components:**

- **Architecture** → Dual-Kernel
  - File: `contracts/architecture/k0_k1_split.yml`
  - K0 (memory, P01-P20), K1 (intelligence, 52 modules), hybrid architecture, pure actors vs AI agents

#### [ADR-0004](../../docs/architecture/decisions/0004-*.md): 0004 Architecture

**Components:**

- **Architecture** → Layer Definitions
  - File: `contracts/architecture/layer_dependencies.yml`
  - Layer 1-5 structure, 52-module organization, microkernel design, hot path optimization, fault isolation, industry patterns

- **Architecture** → Module Manifest
  - File: `contracts/architecture/module_manifest.yml`
  - 58 modules, 5 layers, module boundaries, single responsibility, component classification, Actor Model

- **Dependencies** → Layer Rules
  - File: `contracts/architecture/layer_dependencies.yml`
  - L1→L5 only, L2→all, L3→L4+L5, L4→L5, L5→none, dependency direction

#### [ADR-0004b](../../docs/architecture/decisions/0004b-*.md): 0004B Dependencies

**Components:**

- **Dependencies** → Import Linting
  - File: `.importlinter`
  - import-linter, layering contracts, pre-commit hooks, CI enforcement, forbidden imports, escape hatches

- **Dependencies** → Layer Rules
  - File: `contracts/architecture/layer_dependencies.yml`
  - L1→L5 only, L2→all, L3→L4+L5, L4→L5, L5→none, dependency direction

#### [ADR-0004d](../../docs/architecture/decisions/0004d-*.md): 0004D Testing

**Components:**

- **Testing** → Integration Tests
  - File: `tests/integration/layer_test_base.py`
  - Layer-specific test suites, WARD framework, contract validation, performance budgets, P95 latency

- **Testing** → Layer 1 Tests
  - File: `tests/integration/layer1/`
  - Event publish, intent classification, stream processing, 3-tier routing, <50ms budget

- **Testing** → Layer 2 Tests
  - File: `tests/integration/layer2/`
  - 3-phase orchestration, planning pipeline, protocol validation, <250ms budget

- **Testing** → Layer 3 Tests
  - File: `tests/integration/layer3/`
  - Agent lifecycle, tool execution, Model Hub, <600ms hire, <3000ms tool call

- **Testing** → Layer 4 Tests
  - File: `tests/integration/layer4/`
  - SessionState serialization, learning loop, saga rollback, <1ms serialize

- **Testing** → Layer 5 Tests
  - File: `tests/integration/layer5/`
  - Event bus delivery, backpressure, thermal placement, <5ms delivery

- **Testing** → End-to-End Tests
  - File: `tests/integration/end_to_end/`
  - User turn, barge-in, multi-agent, <2000ms P95


### K1 Internal Event Bus

#### [ADR-0048](../../docs/architecture/decisions/0048-*.md): 0048 Event Categories

**Components:**

- **Event Categories** → Orchestration Events
  - File: `k1/l2_orchestration/event_bus/orchestration_topics.py`
  - k1.orchestration.* (task.announced, agent.proposal, agent.selected)

- **Event Categories** → Planning Events
  - File: `k1/l2_orchestration/planner/planning_topics.py`
  - k1.planning.* (sketch, expand, validate, commit), 4-stage pipeline

- **K0/K1 Separation** → K1 Ephemeral Only
  - File: `docs/architecture/k0_k1_event_separation.md`
  - K1 events ephemeral (no persistence), K0 SSE durable (config, receipts, learning)


### Learning Loop

#### [ADR-0059](../../docs/architecture/decisions/0059-*.md): 0059 Core Architecture

**Components:**

- **Core Architecture** → K0/K1 Boundary
  - File: `k1/l2_orchestrator/learning_loop/core.py`
  - K1LearningLoop advisory-only, K0 P06 persistence, advisory flow K1→K0→validation→persistence→receipt

- **Core Architecture** → Learning Pipeline
  - File: `k1/l2_orchestrator/learning_loop/core.py`
  - FeedbackSignalCollector, DriftMonitor, AdvisoryEmitter, process_feedback collect→analyze→check→emit

- **Core Architecture** → K0 Gateway
  - File: `k1/l2_orchestrator/learning_loop/core.py`
  - K0P06Gateway: P06AdvisoryRequest, submit_advisory, receipt tracking, AdvisoryRejectedError

- **Core Architecture** → Advisory Types
  - File: `k1/l2_orchestrator/learning_loop/core.py`
  - AdvisoryType: ADAPT/ROLLBACK, DriftStatus is_anomalous reason, recommendation confidence

- **Core Architecture** → Learnable Parameters
  - File: `k1/l2_orchestrator/learning_loop/core.py`
  - LEARNABLE: response_length formality_level use_emoji thresholds proactivity clarification_verbosity

- **Core Architecture** → Forbidden Parameters
  - File: `k1/l2_orchestrator/learning_loop/core.py`
  - FORBIDDEN: safety_thresholds privacy_band_rules refusal_policies audit_trail_settings

#### [ADR-0059a](../../docs/architecture/decisions/0059a-*.md): 0059A Feedback Signals

**Components:**

- **Feedback Signals** → Signal Taxonomy
  - File: `k1/l2_orchestrator/learning_loop/signal_collector.py`
  - FeedbackSignal: signal_id session_id signal_type weight polarity, effective_score = weight * polarity

- **Feedback Signals** → Explicit Signals
  - File: `k1/l2_orchestrator/learning_loop/signal_collector.py`
  - Weight 1.0: THUMBS_UP +1.0, THUMBS_DOWN -1.0, STAR_RATING, EXPLICIT_CORRECTION -0.8

- **Feedback Signals** → Implicit Signals
  - File: `k1/l2_orchestrator/learning_loop/signal_collector.py`
  - Weight 0.5: CLARIFICATION_NEEDED -0.6, TASK_COMPLETION +0.8, TOOL_CALL_SUCCESS +0.7

- **Feedback Signals** → Behavioral Signals
  - File: `k1/l2_orchestrator/learning_loop/signal_collector.py`
  - Weight 0.2: INTERRUPTION -0.4, QUICK_EXIT, DWELL_TIME, COPY_TEXT +0.6

- **Feedback Signals** → Collection Methods
  - File: `k1/l2_orchestrator/learning_loop/signal_collector.py`
  - FeedbackSignalCollector: collect_explicit collect_implicit, capture_context, infer_signal_from_event

- **Feedback Signals** → Metrics
  - File: `k1/l2_orchestrator/learning_loop/signal_collector.py`
  - feedback_signals_collected counter by signal_type weight_tier, SIGNAL_POLARITY dict

#### [ADR-0059b](../../docs/architecture/decisions/0059b-*.md): 0059B Drift Detection

**Components:**

- **Drift Detection** → Multi-Layer Monitor
  - File: `k1/l2_orchestrator/learning_loop/drift_monitor.py`
  - DriftMonitor: StatisticalDriftDetector BehavioralDriftDetector SafetyDriftDetector

- **Drift Detection** → Statistical Detection
  - File: `k1/l2_orchestrator/learning_loop/drift_monitor.py`
  - MAX_Z_SCORE 3.0, MAX_DAILY_CHANGE 0.20, MAX_WEEKLY_CHANGE 0.40, z-score calculation

- **Drift Detection** → Rate of Change
  - File: `k1/l2_orchestrator/learning_loop/drift_monitor.py`
  - calculate_daily_change_rate, parameter history 30 days lookback, time delta 86400s/day

- **Drift Detection** → Anomaly Detection
  - File: `k1/l2_orchestrator/learning_loop/drift_monitor.py`
  - Z-score threshold, statistical anomaly, insufficient data <5 samples, drift severity HIGH/MEDIUM/CRITICAL

- **Drift Detection** → Negative Feedback
  - File: `k1/l2_orchestrator/learning_loop/drift_monitor.py`
  - Negative feedback ratio high→rollback, DriftStatus is_drift reason severity details

- **Drift Detection** → Logging
  - File: `k1/l2_orchestrator/learning_loop/drift_monitor.py`
  - drift_detected_zscore drift_detected_rate warnings, ParameterValue timestamp tracking

#### [ADR-0059c](../../docs/architecture/decisions/0059c-*.md): 0059C Parameter Contracts

**Components:**

- **Parameter Contracts** → Parameter Advisory
  - File: `k1/l2_orchestration/learning_loop/parameter_advisory.py`
  - Advisory-only suggestions, safety-constrained, confidence >0.70 threshold, no override of refusal policies

- **Parameter Contracts** → Allowed Parameters
  - File: `k1/l2_orchestration/learning_loop/allowed_parameters.py`
  - LLM params (temperature 0.0-1.0, max_tokens 50-2000), planning params, confidence params (0.60-0.95), style params, bounds validation

- **Parameter Contracts** → Forbidden Parameters
  - File: `k1/l2_orchestration/learning_loop/forbidden_parameters.py`
  - Safety (refusal policies, safety filters), security (privacy bands, audit logging), infrastructure (NEVER adjusted), violation detection

- **Parameter Contracts** → Suggestion Validator
  - File: `k1/l2_orchestration/learning_loop/suggestion_validator.py`
  - Parameter allowed check, bounds validation, confidence threshold >0.70, safety violation prevention, refusal override protection

- **Parameter Adapters** → Planner Parameter Adapter
  - File: `k1/l2_orchestration/learning_loop/planner_adapter.py`
  - Apply suggestions to planner config, parameter hot-reload, validation before apply, rollback on error

- **Parameter Adapters** → Orchestrator Parameter Adapter
  - File: `k1/l2_orchestration/learning_loop/orchestrator_adapter.py`
  - Orchestrator config hot-reload, zero-downtime updates, atomic config application, <100ms application latency

#### [ADR-0059d](../../docs/architecture/decisions/0059d-*.md): 0059D Audit & Rollback

**Components:**

- **Audit & Rollback** → Audit Trail
  - File: `k1/l2_orchestration/learning_loop/audit_trail.py`
  - K0 WAL query interface, LearningAuditEntry records, authoritative source, 4 query categories (summary, parameter history, recent changes, timeline)

- **Audit & Rollback** → Audit Presenter
  - File: `k1/l2_orchestration/learning_loop/audit_presenter.py`
  - Human-readable formatting, timeline visualization, parameter change summaries, user-facing presentation

- **Audit & Rollback** → Point-in-Time Rollback
  - File: `k1/l2_orchestration/learning_loop/point_in_time_rollback.py`
  - Restore full state to timestamp, K0 WAL replay, rollback validation, <1000ms rollback latency

- **Audit & Rollback** → Selective Rollback
  - File: `k1/l2_orchestration/learning_loop/selective_rollback.py`
  - Undo specific parameter to default, surgical rollback, prevent invalid rollbacks, parameter-level granularity

- **Audit & Rollback** → Forget Me
  - File: `k1/l2_orchestration/learning_loop/forget_me.py`
  - GDPR-compliant deletion, delete learned data (keep audit trail per GDPR), K0 WAL integration, privacy compliance

- **Audit & Rollback** → K0P06 Rollback Handler
  - File: `k0/automation/k0p06_rollback_handler.py`
  - K0-side execution via WAL replay, port P06 integration, background job processing, <200ms rollback execution

#### [ADR-0059e](../../docs/architecture/decisions/0059e-*.md): 0059E Synthetic Data

**Components:**

- **Synthetic Data** → Synthetic Data Pipeline
  - File: `k1/l2_orchestration/learning_loop/synthetic/pipeline.py`
  - End-to-end generation, persona→scenario→feedback flow, regression testing, quality metrics calculation, K0 P06 test storage

- **Synthetic Data** → Persona Generator
  - File: `k1/l2_orchestration/learning_loop/synthetic/persona_generator.py`
  - 5 persona templates (tech professional, senior, parent, student, adversarial), tech_savviness/verbosity/formality parameters, persona variation generation

- **Synthetic Data** → Scenario Generator
  - File: `k1/l2_orchestration/learning_loop/synthetic/scenario_generator.py`
  - Conversation templates, difficulty levels (easy/medium/hard), scenario types (weather_query, meeting_schedule, payment_ambiguous, prompt_injection_attempt), template instantiation

- **Synthetic Data** → Feedback Simulator
  - File: `k1/l2_orchestration/learning_loop/synthetic/feedback_simulator.py`
  - Simulate user reactions based on performance, feedback signal generation, behavioral patterns, implicit/explicit feedback

- **Synthetic Data** → Regression Tester
  - File: `k1/l2_orchestration/learning_loop/synthetic/regression_tester.py`
  - Baseline vs adapted model comparison, regression detection (accuracy drop >5% threshold), performance metrics, quality validation

- **Synthetic Data** → Quality Metrics
  - File: `k1/l2_orchestration/learning_loop/synthetic/quality_metrics.py`
  - Intent accuracy, clarification rate, satisfaction score, safety violations tracking, comprehensive evaluation


### Learning Loop Drift

#### [ADR-0079](../../docs/architecture/decisions/0079-*.md): 0079 Drift Detection

**Components:**

- **Drift Detection** → DriftDetectionAlgorithm
  - File: `k1/l2_orchestration/learning/drift_detector.py`
  - KL divergence threshold 0.05, 3 feedback signals (explicit 1.0, implicit 0.5, behavioral 0.2), 1000-sample warm-up, <5% false positive rate, M5 milestone

- **Drift Detection** → FeedbackSample
  - File: `k1/l2_orchestration/learning/feedback_sample.py`
  - Sample format: signal_type value 0.0-1.0 timestamp trace_id, rolling window 1000 samples, probability distributions

- **Adaptive Response** → AdaptiveResponsePipeline
  - File: `k1/l2_orchestration/learning/adaptive_response.py`
  - 4-level severity: STABLE/WARNING/CRITICAL/EMERGENCY, learning rate adjustment, checkpoint/rollback, <200ms P95 response

- **Adaptive Response** → ModelCheckpoint
  - File: `k1/l2_orchestration/learning/checkpoint.py`
  - Model state snapshots, 10-checkpoint history, rollback <1000ms, operator alerts CRITICAL/EMERGENCY


### Message Queue & Coalescing

#### [ADR-0053](../../docs/architecture/decisions/0053-*.md): 0053 Main

**Components:**

- **Main** → Research Foundation
  - File: `docs/research/message_queue_research.md`
  - Nagle's Algorithm (TCP 1984), SEDA (2001), Token Bucket, Cooperative Cancellation (Go/Rust), Turn-taking pauses (2-3s)

#### [ADR-0053a](../../docs/architecture/decisions/0053a-*.md): 0053A Coalesce Window

**Components:**

- **Coalesce Window** → Rollout Strategy
  - File: `docs/rollout/message_queue_rollout.md`
  - Week 1 internal testing, Week 2 5% canary, Week 3-4 gradual to 100% (72h soak each stage)

- **Coalesce Window** → Future Work
  - File: `docs/roadmap/coalescing_enhancements.md`
  - Adaptive windows per user typing speed, context-aware coalescing (longer for complex), predictive flush (ML model)

#### [ADR-0053b](../../docs/architecture/decisions/0053b-*.md): 0053B Rate Limits

**Components:**

- **Rate Limits** → Future Work
  - File: `docs/roadmap/rate_limiting_enhancements.md`
  - Distributed rate limiting (Redis cross-instance), adaptive per-user limits (fast typers 7 msg/sec), per-tier system (premium/free), smart retry SDK

#### [ADR-0053c](../../docs/architecture/decisions/0053c-*.md): 0053C Cancel Path

**Components:**

- **Cancel Path** → K0 Bridge Integration
  - File: `k1/bridge_k0/k0_bridge_client.py`
  - rollback method (WAL transaction abort), pending_writes dict, logger.info k0_rollback (session_id, write_id)

- **Cancel Path** → Future Work
  - File: `docs/roadmap/cancellation_enhancements.md`
  - Predictive cancellation (ML model), partial result preservation (resume interrupted), cancellation batching (reduce overhead), cross-instance cancellation (distributed Redis)


### Multi-Device Family Sync

#### [ADR-0050](../../docs/architecture/decisions/0050-*.md): 0050 Sync Strategy

**Components:**

- **Sync Strategy** → Hybrid Strategy
  - File: `docs/architecture/multi_device_sync_strategy.md`
  - Phase 1 (LAN <1ms), Phase 2 (Internet <500ms), device-first privacy

- **Sync Strategy** → Device Autonomy
  - File: `docs/architecture/device_autonomy.md`
  - Each device runs K0+K1 full dual-kernel, no cloud intermediary, privacy-first


### Multi-Party Dialogue

#### [ADR-0082](../../docs/architecture/decisions/0082-*.md): 0082 Core Architecture

**Components:**

- **Core Architecture** → 3-Layer Pipeline
  - File: `k1/l1_input/streams/operators/speaker_identifier.py`
  - Speaker Diarization (who speaking), Turn-Taking (overlap handling), Conflict Resolution (opposing requests), multi-speaker awareness, per-speaker context retrieval, 3 allocation strategies (first-s...

#### [ADR-0082b](../../docs/architecture/decisions/0082b-*.md): 0082B Turn-Taking

**Components:**

- **Turn-Taking** → Overlap Detection
  - File: `k1/l3_execution/dialogue/overlapping_detector.py`
  - Timestamp analysis (segment start/end comparison), audio energy thresholding (RMS >0.02), overlap_duration_ms calculation, ignore <100ms overlaps (natural turn-taking), dual-speech validation

- **Turn-Taking** → Allocation Strategies
  - File: `k1/l3_execution/dialogue/multi_party_turn_manager.py`
  - First-Speaker Priority (sequential, +500ms queue), Parallel Processing (2× compute, <200ms both), Priority Preemption (urgency >0.7 interrupts), decision tree (urgency→config→strategy), turn alloca...

- **Turn-Taking** → Speaker Context Retrieval
  - File: `k1/l3_execution/dialogue/speaker_context.py`
  - SessionState Section 2 lookup by speaker_id, per-speaker preferences/recent_queries, KG query with speaker_id parameter, context-aware LLM planning, barge-in handling (multi-speaker vs same-speaker...

- **Turn-Taking** → Urgency Detection
  - File: `k1/l3_execution/dialogue/urgency_analyzer.py`
  - Keyword-based urgency (emergency/help/fire/911), sentiment-based urgency (ADR-0069 integration), combined urgency score (max of keyword/sentiment), urgency thresholds (>0.7 preemption, 0.3-0.7 para...


### OpenAPI 3.1 Specs

#### [ADR-0047](../../docs/architecture/decisions/0047-*.md): 0047 SDK Generation

**Components:**

- **SDK Generation** → OpenAPI Generator Config
  - File: `.openapi-generator/config.yml`
  - TypeScript (typescript-axios), Python (python), Go (go), package names, output dirs

- **SDK Generation** → TypeScript SDK
  - File: `sdks/typescript/`
  - Auto-generated from openapi.json, axios HTTP client, type-safe interfaces

- **SDK Generation** → Python SDK
  - File: `sdks/python/`
  - Auto-generated from openapi.json, requests HTTP client, type hints

- **SDK Generation** → Go SDK
  - File: `sdks/go/`
  - Auto-generated from openapi.json, net/http client, struct definitions

- **Security Schemes** → Bearer JWT
  - File: `k1/api/rest/security.py`
  - bearerAuth security scheme, Authorization header, JWT format, token validation

- **CI/CD** → OpenAPI Validation
  - File: `.github/workflows/openapi-validation.yml`
  - swagger-validator-action, validate spec on push/PR, fail if invalid schema

- **CI/CD** → SDK Generation Test
  - File: `.github/workflows/openapi-validation.yml`
  - Generate TypeScript SDK, test compilation, ensure SDK builds without errors


### PII Detection

#### [ADR-0035c](../../docs/architecture/decisions/0035c-*.md): 0035C Encrypted Vault

**Components:**

- **Encrypted Vault** → AES-256-GCM Encryption
  - File: `k0/pii_vault/encryption.py`
  - Authenticated encryption, 256-bit key, 96-bit nonce, 128-bit auth tag, Quantum-resistant (NIST SP 800-38D)

- **Encrypted Vault** → Key Management
  - File: `k0/pii_vault/key_manager.py`
  - AWS KMS/Azure Key Vault/Google Cloud KMS, 90-day rotation, FIPS 140-2 Level 2 validated, Multi-region replication (DR/BC)

- **Encrypted Vault** → Storage
  - File: `k0/pii_vault/storage.py`
  - 256 bytes per PII entry (ciphertext + metadata), 90-day retention, Soft delete (deleted_at + 30-day grace period)

- **Encrypted Vault** → Performance
  - File: `k0/pii_vault/encryption.py`
  - <2ms encryption, <1ms decryption, <5ms vault write (K0 INSERT), <5ms vault read (K0 SELECT + decrypt)

- **Encrypted Vault** → GDPR Rights
  - File: `k0/pii_vault/gdpr_manager.py`
  - Right to access (retrieve encrypted PII), Right to erasure (soft delete from vault), Defense in depth (key separation from database)

#### [ADR-0035d](../../docs/architecture/decisions/0035d-*.md): 0035D Audit Trail

**Components:**

- **Audit Trail** → Append-Only Logging
  - File: `k0/audit/pii_logger.py`
  - All PII operations logged (detect/redact/vault store/retrieve/delete), Tamper-proof, Who/what/when recorded

- **Audit Trail** → Retention
  - File: `k0/audit/pii_logger.py`
  - 90 days (GDPR minimum), 7 years (HIPAA requirement), Compliance with Article 15/17/20/33

- **Audit Trail** → GDPR Compliance
  - File: `k0/audit/gdpr_compliance.py`
  - Article 15 (right to access, 30-day response), Article 17 (right to erasure), Article 20 (data portability, machine-readable JSON export), Article 33 (breach notification, 72 hours)

- **Audit Trail** → HIPAA Compliance
  - File: `k0/audit/hipaa_compliance.py`
  - 164.308(a)(1)(ii)(D) audit controls, 164.312(b) audit trail (who/what/when), 164.528(a) accounting of disclosures, 6-year retention minimum

- **Audit Trail** → Production Metrics
  - File: `k0/audit/metrics.py`
  - 12,000 PII detections logged (6 months), 47 GDPR requests (45 access + 2 erasure), <1ms audit write (async, no blocking)


### Performance Budgets

#### [ADR-0024](../../docs/architecture/decisions/0024-*.md): 0024 Component-Level Budgets

**Components:**

- **Component-Level Budgets** → Intent Classification
  - File: `k1/l2_orchestrator/intent_classifier.py`
  - <50ms P95 budget, rule-based 10ms (fast path), LLM 45ms (fallback), 100ms timeout

- **Component-Level Budgets** → 3-Phase Orchestration
  - File: `k1/l2_orchestrator/orchestrator.py`
  - <250ms P95 budget, negotiation 100ms + selection 50ms + execution 100ms, 500ms timeout

- **Component-Level Budgets** → Deadline Propagation
  - File: `k1/l2_orchestrator/deadline.py`
  - Pass deadline_ms to components, remaining time budget, timeout enforcement

- **Graceful Degradation** → Skip Optional Processing
  - File: `k1/l2_orchestrator/optional_features.py`
  - Skip persona customization (saves 20ms), skip grounding act (saves 12ms), AMBER tier

- **Graceful Degradation** → Fallback Models
  - File: `k1/l2_orchestrator/intent_classifier.py`
  - Rule-based intent (10ms) vs LLM intent (50ms), fast path fallback, RED tier

#### [ADR-0024b](../../docs/architecture/decisions/0024b-*.md): 0024B Component-Level Budgets

**Components:**

- **Component-Level Budgets** → Intent Classification
  - File: `k1/l2_orchestrator/intent_classifier.py`
  - <50ms P95 budget, rule-based 10ms (fast path), LLM 45ms (fallback), 100ms timeout

- **Component-Level Budgets** → 3-Phase Orchestration
  - File: `k1/l2_orchestrator/orchestrator.py`
  - <250ms P95 budget, negotiation 100ms + selection 50ms + execution 100ms, 500ms timeout

- **Component-Level Budgets** → Deadline Propagation
  - File: `k1/l2_orchestrator/deadline.py`
  - Pass deadline_ms to components, remaining time budget, timeout enforcement

#### [ADR-0024d](../../docs/architecture/decisions/0024d-*.md): 0024D Graceful Degradation

**Components:**

- **Graceful Degradation** → Skip Optional Processing
  - File: `k1/l2_orchestrator/optional_features.py`
  - Skip persona customization (saves 20ms), skip grounding act (saves 12ms), AMBER tier

- **Graceful Degradation** → Fallback Models
  - File: `k1/l2_orchestrator/intent_classifier.py`
  - Rule-based intent (10ms) vs LLM intent (50ms), fast path fallback, RED tier


### Privacy Band Retention

#### [ADR-0039](../../docs/architecture/decisions/0039-*.md): 0039 Band-Specific Policies

**Components:**

- **Band-Specific Policies** → RED Band Override
  - File: `k1/l2_state/session_state/retention_policy.py`
  - RED: 7 days warm + 90 days cold (97 days total, 75% reduction vs 395 days default), Privacy-first deletion (minimize exposure window), GDPR data minimization (Article 5(1)(c))

- **Band-Specific Policies** → GREEN/AMBER Default
  - File: `k1/l2_state/session_state/retention_policy.py`
  - GREEN/AMBER: 30 days warm + 365 days cold (395 days total), Standard retention for non-sensitive data

- **Lifecycle Management** → Automated Cron
  - File: `k1/l2_state/session_state/lifecycle_manager.py`
  - Daily cron job checks retention policies, Warm→Cold after 7/30 days, Cold→Delete after 90/365 days, 100% automation (no manual intervention)

- **Lifecycle Management** → Hard Deletion
  - File: `k1/l2_state/session_state/deletion.py`
  - SessionState + encryption keys deleted from K0 (irreversible), Audit logs retained (GDPR audit trail requirement), Data unrecoverable

- **User Control** → Immediate Deletion API
  - File: `k1/l2_state/session_state/user_control.py`
  - User can request immediate deletion (GDPR Article 17 right to erasure), Override to extended retention (opt-in to 30d/365d), View retention status (API endpoint)

- **Compliance** → GDPR Alignment
  - File: `k1/l2_state/session_state/gdpr_compliance.py`
  - Article 5(1)(c) data minimization ("limited to what is necessary"), Article 5(1)(e) storage limitation ("no longer than necessary"), Article 17 right to erasure ("right to be forgotten")


### Prometheus Metrics

#### [ADR-0029](../../docs/architecture/decisions/0029-*.md): 0029 Component

**Components:**

- **Component** → Orchestrator Metrics
  - File: `k1/l2_orchestrator/orchestrator_metrics.py`
  - Orchestrator_tasks_total (by status), Orchestrator_3phase_latency_ms, Negotiation rounds histogram, Selection/Execution latency, Orchestrator_timeout_total counter

- **Component** → Planner Metrics
  - File: `k1/l2_orchestrator/planner/planner_metrics.py`
  - Planner_plans_total (validated/rejected/fallback), Validation failures counter (by type), Planner_planning_latency_ms (4-stage), Arbiter approvals counter, Planner_fallbacks_total

- **Infrastructure** → KV Cache Metrics
  - File: `k1/l2_state/kv_cache/cache_metrics.py`
  - Kv_cache_hit_rate gauge (>0.75 target), Kv_cache_size_mb (128MB budget), Kv_cache_evictions_total (LRU policy), Kv_cache_entries gauge, Kv_cache_access_latency_ms

- **Infrastructure** → Memory Metrics
  - File: `k1/l2_state/session_state/memory_metrics.py`
  - Session_state_size_kb gauge (64KB budget), K1_memory_total_mb (500MB budget), Session_state_evictions_total, 3-tier eviction tracking, Per-session size tracking

#### [ADR-0029c](../../docs/architecture/decisions/0029c-*.md): 0029C Component

**Components:**

- **Component** → Orchestrator Metrics
  - File: `k1/l2_orchestrator/orchestrator_metrics.py`
  - Orchestrator_tasks_total (by status), Orchestrator_3phase_latency_ms, Negotiation rounds histogram, Selection/Execution latency, Orchestrator_timeout_total counter

- **Component** → Planner Metrics
  - File: `k1/l2_orchestrator/planner/planner_metrics.py`
  - Planner_plans_total (validated/rejected/fallback), Validation failures counter (by type), Planner_planning_latency_ms (4-stage), Arbiter approvals counter, Planner_fallbacks_total

#### [ADR-0029d](../../docs/architecture/decisions/0029d-*.md): 0029D Infrastructure

**Components:**

- **Infrastructure** → KV Cache Metrics
  - File: `k1/l2_state/kv_cache/cache_metrics.py`
  - Kv_cache_hit_rate gauge (>0.75 target), Kv_cache_size_mb (128MB budget), Kv_cache_evictions_total (LRU policy), Kv_cache_entries gauge, Kv_cache_access_latency_ms

- **Infrastructure** → Memory Metrics
  - File: `k1/l2_state/session_state/memory_metrics.py`
  - Session_state_size_kb gauge (64KB budget), K1_memory_total_mb (500MB budget), Session_state_evictions_total, 3-tier eviction tracking, Per-session size tracking


### REST API Dual Format

#### [ADR-0014b](../../docs/architecture/decisions/0014b-*.md): 0014B OpenAPI Generation

**Components:**

- **OpenAPI Generation** → FlatBuffers Parser
  - File: `tools/flatbuffers_parser.py`
  - Parse .fbs files, extract tables/enums/unions, regex-based parsing

- **OpenAPI Generation** → JSON Schema Mapper
  - File: `tools/json_schema_mapper.py`
  - FlatBuffers types → JSON Schema types, union → oneOf discriminator, 100% coverage

- **OpenAPI Generation** → OpenAPI 3.1 Spec
  - File: `api/openapi.json`
  - 8,450 lines auto-generated, 40 REST API schemas, paths + schemas + examples

- **OpenAPI Generation** → CI/CD Validation
  - File: `scripts/validate_openapi_spec.py`
  - Fail build if spec out of sync with schemas, <30s generation, 100% accuracy

#### [ADR-0014d](../../docs/architecture/decisions/0014d-*.md): 0014D Client SDKs

**Components:**

- **Client SDKs** → Python SDK (JSON)
  - File: `sdk/python/k1_client.py`
  - K1Client class, requests library, create_session/start_turn/recall/invoke_tool methods

- **Client SDKs** → Python SDK (FlatBuffers)
  - File: `sdk/python/k1_client_fb.py`
  - K1ClientFlatBuffers class, zero-copy deserialization, 50-100ms faster vs JSON

- **Client SDKs** → TypeScript SDK (JSON)
  - File: `sdk/typescript/k1-client.ts`
  - K1Client class, fetch API, browser + Node.js compatible, type-safe interfaces

- **Client SDKs** → TypeScript SDK (FlatBuffers)
  - File: `sdk/typescript/k1-client-fb.ts`
  - FlatBuffers npm package, Buffer serialization, axios for Node.js

- **Client SDKs** → curl Examples
  - File: `docs/api/curl_examples.md`
  - All 20 REST endpoints, JSON payloads, copy-paste ready, Accept/Content-Type headers

- **Client SDKs** → Migration Guide
  - File: `docs/api/MIGRATION_GUIDE.md`
  - When to use FlatBuffers, performance benchmarks (JSON 50ms vs FlatBuffers 5ms), trade-offs

- **Client SDKs** → Postman Collection
  - File: `api/postman_collection.json`
  - Auto-generated from OpenAPI spec, 20 endpoints, environment variables, examples

- **Client SDKs** → Performance Benchmarks
  - File: `benchmarks/json_vs_flatbuffers.py`
  - 1KB-10KB payloads, latency/size comparison, 50-100ms JSON vs 5-10ms FlatBuffers


### SSE Event Schemas

#### [ADR-0016](../../docs/architecture/decisions/0016-*.md): 0016 Event Taxonomy

**Components:**

- **Event Taxonomy** → Event Types
  - File: `k1/schemas/sse/event_envelope.fbs`
  - 17 event types, 5 categories, EventEnvelope, EventPayload union

- **Event Taxonomy** → Agent Lifecycle Events
  - File: `k1/schemas/sse/agent_events.fbs`
  - AgentHired, AgentFired, AgentCrashed, AgentRestarted (4 events)

- **Event Taxonomy** → Turn Events
  - File: `k1/schemas/sse/turn_events.fbs`
  - TurnStarted, TurnCompleted, TurnFailed, TurnInterrupted (4 events)

- **Event Taxonomy** → Tool Events
  - File: `k1/schemas/sse/tool_events.fbs`
  - ToolCallStarted, ToolCallCompleted, ToolCallFailed, ToolApprovalRequired (4 events)

- **Event Taxonomy** → Session Events
  - File: `k1/schemas/sse/session_events.fbs`
  - SessionCreated, SessionTerminated, SessionCrashed (3 events)

- **Event Taxonomy** → System Events
  - File: `k1/schemas/sse/system_events.fbs`
  - Heartbeat, Error (2 events, keepalive + notifications)

#### [ADR-0016a](../../docs/architecture/decisions/0016a-*.md): 0016A Event Taxonomy

**Components:**

- **Event Taxonomy** → Event Types
  - File: `k1/schemas/sse/event_envelope.fbs`
  - 17 event types, 5 categories, EventEnvelope, EventPayload union

- **Event Taxonomy** → Agent Lifecycle Events
  - File: `k1/schemas/sse/agent_events.fbs`
  - AgentHired, AgentFired, AgentCrashed, AgentRestarted (4 events)

- **Event Taxonomy** → Turn Events
  - File: `k1/schemas/sse/turn_events.fbs`
  - TurnStarted, TurnCompleted, TurnFailed, TurnInterrupted (4 events)

- **Event Taxonomy** → Tool Events
  - File: `k1/schemas/sse/tool_events.fbs`
  - ToolCallStarted, ToolCallCompleted, ToolCallFailed, ToolApprovalRequired (4 events)

- **Event Taxonomy** → Session Events
  - File: `k1/schemas/sse/session_events.fbs`
  - SessionCreated, SessionTerminated, SessionCrashed (3 events)

- **Event Taxonomy** → System Events
  - File: `k1/schemas/sse/system_events.fbs`
  - Heartbeat, Error (2 events, keepalive + notifications)

#### [ADR-0016c](../../docs/architecture/decisions/0016c-*.md): 0016C Filtering

**Components:**

- **Filtering** → Topic Mappings
  - File: `k1/config/sse_topics.yml`
  - 5 topics (agent_lifecycle, turn_execution, tool_execution, session_lifecycle, system_health)

- **Filtering** → Bandwidth Savings
  - File: `docs/architecture/sse_bandwidth_analysis.md`
  - 60-70% savings with topic filtering, all topics 6.5KB → filtered 2.2KB

#### [ADR-0016d](../../docs/architecture/decisions/0016d-*.md): 0016D Browser Integration

**Components:**

- **Browser Integration** → Native EventSource
  - File: `docs/api/sse_examples/vanilla_js.js`
  - Vanilla JS, browser-native, auto-reconnect, no SDK, Last-Event-ID

- **Browser Integration** → React Hook
  - File: `sdk/typescript/use_sse_events.ts`
  - useSSEEvents hook, connection state, onEvent callback, useEffect cleanup

- **Browser Integration** → TypeScript SDK
  - File: `sdk/typescript/k1_sse_client.ts`
  - K1SSEClient, Node.js eventsource polyfill, auth headers, reconnect

- **Browser Integration** → Connection State
  - File: `sdk/typescript/connection_state.ts`
  - CONNECTING/CONNECTED/DISCONNECTED/CLOSED, exponential backoff 3s→30s


### SSE Topic Taxonomy

#### [ADR-0043c](../../docs/architecture/decisions/0043c-*.md): 0043C Topic Routing

**Components:**

- **Topic Routing** → K0TopicRouter
  - File: `k0/sse/topic_router.py`
  - Route events from producers to consumers, subscription lookup, fanout strategy (broadcast vs consumer group), delivery tracking

- **Topic Routing** → At-Least-Once Delivery
  - File: `k0/sse/delivery_guarantees.py`
  - Cursor-based ACK for at-least-once delivery, retry on failure (exponential backoff), dead letter queue (DLQ) for terminal failures after 3 retries

- **Topic Routing** → Fanout Strategies
  - File: `k0/sse/fanout_strategies.py`
  - Broadcast all (all consumers receive event), consumer group one (load balance to one), routing metrics (delivery success rate, latency per topic)

- **Topic Routing** → Dead Letter Queue
  - File: `k0/sse/dlq_manager.py`
  - Store failed events (3 retries exhausted), 7-day DLQ retention, max 10K DLQ entries, supervisor alerts for DLQ overflow


### SSE-WebSocket Bridge

#### [ADR-0046](../../docs/architecture/decisions/0046-*.md): 0046 Configuration

**Components:**

- **Configuration** → Bridge Config
  - File: `k1/config/sse_bridge.yml`
  - Subscribed topics, max connections (10K), send_queue_size (100), backpressure_threshold (90%)


### Saga Error Recovery

#### [ADR-0008](../../docs/architecture/decisions/0008-*.md): 0008 Saga Orchestrator

**Components:**

- **Saga Orchestrator** → Core Orchestration
  - File: `k1/l2_orchestration/saga/orchestrator.py`
  - execute_saga, compensation triggering, LIFO unwinding, audit trail, Garcia-Molina 1987

- **Saga Orchestrator** → Step Execution
  - File: `k1/l2_orchestration/saga/step_executor.py`
  - execute_step_with_retry, status tracking, completion stack, step result recording

- **Saga Orchestrator** → Compensation Runner
  - File: `k1/l2_orchestration/saga/compensation_runner.py`
  - run_compensations, reverse-order execution, best-effort, timeout enforcement (3s)

- **Saga Orchestrator** → Result Aggregation
  - File: `k1/l2_orchestration/saga/result_aggregator.py`
  - SagaResult, completed_steps count, failed_step_idx, user messaging

#### [ADR-0008a](../../docs/architecture/decisions/0008a-*.md): 0008A Compensation Design

**Components:**

- **Compensation Design** → Tool-Based Compensation
  - File: `k1/l2_orchestration/saga/compensations/tool_based.py`
  - ToolCompensation, tool_id, params_mapping, result extraction, timeout 3s

- **Compensation Design** → API-Based Compensation
  - File: `k1/l2_orchestration/saga/compensations/api_based.py`
  - APICompensation, HTTP endpoint, method, payload_mapping, timeout 3s

- **Compensation Design** → Custom Compensation
  - File: `k1/l2_orchestration/saga/compensations/custom.py`
  - CustomCompensation, handler_function, module path, params_mapping

- **Compensation Design** → No-Op Compensation
  - File: `k1/l2_orchestration/saga/compensations/noop.py`
  - NoOpCompensation, read-only tools, instant return, 0ms latency

- **Compensation Registry** → Registry Core
  - File: `k1/l2_orchestration/saga/registry.py`
  - CompensationRegistry, 50+ tool handlers, register/get_handler, O(1) lookup

- **Compensation Registry** → Booking Tools
  - File: `k1/l2_orchestration/saga/registry.py`
  - book_hotel→cancel_booking, reserve_flight→cancel_flight, 3s timeout

- **Compensation Registry** → Calendar Tools
  - File: `k1/l2_orchestration/saga/registry.py`
  - create_event→delete_event, update_event→restore_event, 3s timeout

- **Compensation Registry** → Payment Tools
  - File: `k1/l2_orchestration/saga/registry.py`
  - charge_payment→refund_payment, void_transaction→void_payment, 5s timeout

- **Idempotency** → Idempotency Manager
  - File: `k1/l2_orchestration/saga/idempotency.py`
  - execute_compensation_idempotent, Redis cache, 5-minute TTL, deduplication

- **Idempotency** → Key Generation
  - File: `k1/l2_orchestration/saga/idempotency.py`
  - generate_compensation_idempotency_key, saga_id:step_id:compensation_id, 5-min window

#### [ADR-0008b](../../docs/architecture/decisions/0008b-*.md): 0008B Recovery Strategies

**Components:**

- **Recovery Strategies** → Forward Recovery
  - File: `k1/l2_orchestration/saga/recovery/forward.py`
  - execute_with_retry, exponential backoff, max 5 retries, transient error handling

- **Recovery Strategies** → Backward Recovery
  - File: `k1/l2_orchestration/saga/recovery/backward.py`
  - execute_backward_recovery, LIFO compensation, best-effort, 5 steps × 3s = 15s

- **Recovery Strategies** → Hybrid Recovery
  - File: `k1/l2_orchestration/saga/recovery/hybrid.py`
  - execute_hybrid_recovery, retry forward first, fallback to rollback, ~18s worst-case

- **Failure Classification** → Classifier Core
  - File: `k1/l2_orchestration/saga/failure_classifier.py`
  - classify_error, TRANSIENT/PERMANENT/AMBIGUOUS, HTTP status codes, exception types

- **Failure Classification** → Transient Failures
  - File: `k1/l2_orchestration/saga/failure_classifier.py`
  - Timeout, 429 rate limit, 503 unavailable, connection errors, retry eligible

- **Failure Classification** → Permanent Failures
  - File: `k1/l2_orchestration/saga/failure_classifier.py`
  - 400/401/403/404 errors, ValueError, PermissionError, no retry

- **Failure Classification** → Ambiguous Failures
  - File: `k1/l2_orchestration/saga/failure_classifier.py`
  - Timeout after send, 500/502 errors, network partition, idempotency-based decision

- **Retry Policy** → Retry Configuration
  - File: `k1/l2_orchestration/saga/retry_policy.py`
  - RetryPolicy, max 5 retries, 100-1600ms backoff, 20% jitter, 10s budget

- **Retry Policy** → Exponential Backoff
  - File: `k1/l2_orchestration/saga/retry_policy.py`
  - 100ms→200ms→400ms→800ms→1600ms, jitter ±20%, prevent thundering herd

#### [ADR-0008c](../../docs/architecture/decisions/0008c-*.md): 0008C Distributed State

**Components:**

- **Distributed State** → Saga Log Schema
  - File: `k1/l2_orchestration/saga/log_schema.py`
  - SagaLog FlatBuffers, state machine, steps_completed, compensation_stack, timestamps

- **Distributed State** → State Machine
  - File: `k1/l2_orchestration/saga/state_machine.py`
  - SagaState enum, EXECUTING/COMPENSATING/COMPLETED/ABORTED/CRASHED, transitions

- **Recovery Coordinator** → Crash Detection
  - File: `k1/l2_orchestration/saga/recovery_coordinator.py`
  - _query_crashed_sagas, 60s heartbeat timeout, 30s scan interval, 24h orphan cleanup

- **Recovery Coordinator** → Saga Recovery
  - File: `k1/l2_orchestration/saga/recovery_coordinator.py`
  - _recover_saga, resume compensation, at-least-once delivery, state transitions

- **Recovery Coordinator** → Orphan Cleanup
  - File: `k1/l2_orchestration/saga/recovery_coordinator.py`
  - cleanup_orphaned_sagas, 24-hour threshold, automatic abort, resource leak prevention

- **Heartbeat** → Heartbeat Sender
  - File: `k1/l2_orchestration/saga/heartbeat.py`
  - start_heartbeat, 10s interval, last_heartbeat_at update, K0 WAL write

- **Heartbeat** → Heartbeat Monitor
  - File: `k1/l2_orchestration/saga/heartbeat.py`
  - is_saga_crashed, 60s crash timeout, liveness detection, recovery triggering

#### [ADR-0008d](../../docs/architecture/decisions/0008d-*.md): 0008D Timeout Management

**Components:**

- **Timeout Management** → Timeout Hierarchy
  - File: `k1/l2_orchestration/saga/timeouts.py`
  - 4 levels (step 30s, compensation 3s, saga 120s, session 600s), cascading timeouts

- **Timeout Management** → Step Timeout
  - File: `k1/l2_orchestration/saga/timeouts.py`
  - execute_step_with_timeout, 30s per tool call, asyncio.wait_for, StepTimeoutError

- **Timeout Management** → Compensation Timeout
  - File: `k1/l2_orchestration/saga/timeouts.py`
  - execute_compensation_with_timeout, 3s fail-fast, best-effort continuation

- **Timeout Management** → Saga Timeout
  - File: `k1/l2_orchestration/saga/timeouts.py`
  - execute_saga timeout, 120s total, abort + compensation trigger, timeout calculation

- **Liveness** → Termination Guarantees
  - File: `k1/l2_orchestration/saga/liveness.py`
  - Saga timeout enforcement, max 10 steps, max 5 retries, bounded execution


### Schema Versioning

#### [ADR-0013](../../docs/architecture/decisions/0013-*.md): 0013 SemVer Policy

**Components:**

- **SemVer Policy** → Version Bump Rules
  - File: `k1/config/versioning_policy.yml`
  - MAJOR (breaking: field removal/type change), MINOR (new optional field), PATCH (documentation)

- **SemVer Policy** → 90-Day Deprecation
  - File: `k1/config/deprecation_policy.yml`
  - 90-day minimum window, email/Slack/ADR notifications, (deprecated) attribute

- **SemVer Policy** → Breaking Changes
  - File: `docs/architecture/BREAKING_CHANGES.md`
  - Field removal, type change, new required field, field rename → MAJOR bump

- **SemVer Policy** → Backward Compatibility
  - File: `docs/architecture/COMPATIBILITY.md`
  - MINOR/PATCH versions backward-compatible, old clients ignore new optional fields

#### [ADR-0013a](../../docs/architecture/decisions/0013a-*.md): 0013A Version Registry

**Components:**

- **Version Registry** → Central Registry
  - File: `k1/config/schema_registry.yml`
  - 76 schemas × 3-5 versions = 228+ entries, version metadata, changelog, compatibility matrix

- **Version Registry** → Compatibility Matrix
  - File: `k1/config/schema_registry.yml`
  - Auto-generated: same MAJOR compatible, different MAJOR incompatible, forward/backward rules

- **Version Registry** → Deprecation Schedule
  - File: `k1/config/schema_registry.yml`
  - 90-day countdown per field, usage percentage, migration guide links, removal dates

- **Version Registry** → CLI Tool
  - File: `tools/k1_schema_version.py`
  - k1-schema-version check/deprecations/validate, <100ms latency, cached registry

#### [ADR-0013b](../../docs/architecture/decisions/0013b-*.md): 0013B CI/CD Automation

**Components:**

- **CI/CD Automation** → Schema Diff Analysis
  - File: `scripts/schema_diff_analyzer.py`
  - Parse old/new .fbs files, compute diff, detect MAJOR/MINOR/PATCH changes, <10s analysis

- **CI/CD Automation** → Version Bump Validation
  - File: `ci/validate_version_bump.py`
  - Fail build if version bump incorrect, <30s CI/CD latency, >95% accuracy

- **CI/CD Automation** → Changelog Generation
  - File: `scripts/generate_changelog.py`
  - Auto-generate CHANGELOG.md from schema diff, Git commit messages

- **CI/CD Automation** → GitHub Actions Workflow
  - File: `.github/workflows/schema-version-validation.yml`
  - Run on PR, validate version bumps, fail if incorrect, clear error messages

#### [ADR-0013c](../../docs/architecture/decisions/0013c-*.md): 0013C Deprecation Workflow

**Components:**

- **Deprecation Workflow** → FlatBuffers Annotations
  - File: `k1/schemas/**/*.fbs`
  - // DEPRECATED (date): reason, REMOVAL DATE, MIGRATION, [deprecated] attribute

- **Deprecation Workflow** → CI/CD Extraction
  - File: `scripts/extract_deprecations.py`
  - Daily cron job, parse .fbs files, extract DEPRECATED fields, update registry

- **Deprecation Workflow** → Email Notifications
  - File: `scripts/send_deprecation_emails.py`
  - 90/60/30/7 days before removal, <k1-dev@example.com>, clear migration guidance

- **Deprecation Workflow** → Slack Bot
  - File: `scripts/slack_deprecation_bot.py`
  - @K1-Schema-Bot, #schema-changes channel, interactive buttons, weekly digest

- **Deprecation Workflow** → Grafana Dashboard
  - File: `observability/dashboards/schema_deprecations.json`
  - Deprecation timeline, usage metrics %, 30-day alerts, top deprecated fields

#### [ADR-0013d](../../docs/architecture/decisions/0013d-*.md): 0013D Contract Testing

**Components:**

- **Contract Testing** → Pact-Style Tests
  - File: `tests/schemas/contract_tests.py`
  - Consumer-driven contracts, forward/backward compatibility tests, 228+ test cases

- **Contract Testing** → Forward Compatibility
  - File: `tests/schemas/test_forward_compat.py`
  - Old client v2.0.0 + new schema v2.1.0 → ✅, new optional fields ignored

- **Contract Testing** → Backward Compatibility
  - File: `tests/schemas/test_backward_compat.py`
  - New client v2.1.0 + old schema v2.0.0 → ✅, missing optional fields handled gracefully

- **Contract Testing** → Breaking Change Detection
  - File: `tests/schemas/test_breaking_changes.py`
  - Detect field removal, type change, new required field → fail tests

- **Contract Testing** → Multi-Version Matrix
  - File: `tests/schemas/test_matrix_generator.py`
  - 76 schemas × 3 versions × 2 directions = 456 test cases, parallelized <20 min

- **Contract Testing** → CI/CD Integration
  - File: `.github/workflows/schema-contract-tests.yml`
  - Run on schema PR, fail if breaking change without MAJOR bump


### Turn Boundary Management

#### [ADR-0054](../../docs/architecture/decisions/0054-*.md): 0054 Main

**Components:**

- **Main** → Research Foundation
  - File: `docs/research/turn_taking_research.md`
  - Sacks et al. 1974 turn-taking, TRP pauses 0.5-2.5s, Google/Alexa 1.5-2.5s thresholds, natural conversation flow

#### [ADR-0054a](../../docs/architecture/decisions/0054a-*.md): 0054A Implicit Pause

**Components:**

- **Implicit Pause** → Research Foundation
  - File: `docs/research/turn_taking_research.md`
  - Sacks et al. 1974 TRP 0.5-2.5s, Google 1.5-2.0s, Alexa 2.0-2.5s, Siri 1.8-2.2s silence thresholds

- **Implicit Pause** → Human Perception
  - File: `docs/research/turn_taking_research.md`
  - <1s pause mid-thought (don't interrupt), 1-2s ambiguous, >2s clear turn end (expect response)

- **Implicit Pause** → Future Work
  - File: `docs/roadmap/turn_boundary_enhancements.md`
  - Adaptive pause threshold per user typing speed (fast 1.5s, slow 2.5s), linguistic completeness detection (LLM check)

#### [ADR-0054b](../../docs/architecture/decisions/0054b-*.md): 0054B Explicit Submit

**Components:**

- **Explicit Submit** → Implementation Phases
  - File: `docs/implementation/explicit_submit_rollout.md`
  - Phase 1: WebSocket protocol, Phase 2: Desktop UI, Phase 3: Mobile UI, Phase 4: Voice commands

- **Explicit Submit** → UX Tests
  - File: `tests/ui/test_explicit_submit.py`
  - Send button click triggers submit, Enter key triggers submit, Shift+Enter triggers submit, voice "Send" command triggers submit


### Turn History Retention

#### [ADR-0021c](../../docs/architecture/decisions/0021c-*.md): 0021C Compliance

**Components:**

- **Compliance** → GDPR Article 5(e)
  - File: `docs/compliance/gdpr_retention.md`
  - "No longer than necessary", time-limited retention, 365-day baseline, legal rationale

- **Compliance** → GDPR Article 17
  - File: `docs/compliance/gdpr_deletion.md`
  - Right to erasure, 30-day grace period, user deletion API, compliance reporting

- **Compliance** → Retention Reports
  - File: `reports/retention_compliance.py`
  - Monthly compliance reports, deletion statistics, policy adherence, audit evidence


### Voice Pipeline Implementation

#### [ADR-0056](../../docs/architecture/decisions/0056-*.md): 0056 Pipeline Architecture

**Components:**

- **Pipeline Architecture** → K0ASRPipeline
  - File: `k0/pipelines/p11_asr/asr_pipeline.py`
  - K0 P11 pipeline: ASR frame buffering, VAD, ASR model inference (Whisper), partial transcript streaming

- **Pipeline Architecture** → K0TTSPipeline
  - File: `k0/pipelines/p12_tts/tts_pipeline.py`
  - K0 P12 pipeline: SSML generation, TTS model inference (VITS), audio streaming synthesis, opus/pcm codec

- **Pipeline Architecture** → ASR Frame Processing
  - File: `k0/pipelines/p11_asr/frame_processor.py`
  - 20ms frames, 80ms ring buffer, VAD energy calculation, partial transcript emission

- **Pipeline Architecture** → VAD Integration
  - File: `k0/pipelines/p11_asr/vad_detector.py`
  - 2s silence threshold (ADR-0054 turn boundary), energy_threshold_db=-50, RMS energy calculation

- **Pipeline Architecture** → Partial Transcript Streaming
  - File: `k0/pipelines/p11_asr/asr_pipeline.py`
  - return_partials=True flag, emit intermediate ASR results for typing indicator style, is_partial flag in transcript

- **Pipeline Architecture** → TTS Streaming Synthesis
  - File: `k0/pipelines/p12_tts/tts_pipeline.py`
  - synthesize_streaming method: text → SSML → TTS model → audio chunks, streaming response (async iterator)

- **Pipeline Architecture** → Prosody Controls
  - File: `k0/pipelines/p12_tts/prosody_controller.py`
  - response.prosody: pitch (Hz), rate (words/min), emphasis (stress patterns), SSML generation

- **Performance Budgets** → ASR Latency
  - File: `k0/pipelines/p11_asr/config.yml`
  - asr_frame_processing_ms: 100 (P95 target), asr_final_transcript_ms: 300 (end of speech → final transcript)

- **Performance Budgets** → TTS Latency
  - File: `k0/pipelines/p12_tts/config.yml`
  - tts_synthesis_first_chunk_ms: 200 (TTFA Time to First Audio), tts_synthesis_streaming_ms: 50 (subsequent chunks)

- **Metrics** → ASR Metrics
  - File: `observability/metrics/voice_pipeline_metrics.py`
  - asr_frame_processing_latency_ms histogram (buckets 10/50/100/200/500), K0 P11 owner

- **Metrics** → TTS Metrics
  - File: `observability/metrics/voice_pipeline_metrics.py`
  - tts_synthesis_latency_ms histogram (buckets 50/100/200/500/1000), K0 P12 owner

- **ASR Ingress** → Frame Handling
  - File: `k0/pipelines/p11_asr/frame_handler.py`
  - ADR-0056a: 20ms audio frames, buffering strategy, frame drop policy at 80% capacity

- **ASR Ingress** → VAD Processing
  - File: `k0/pipelines/p11_asr/vad_processor.py`
  - ADR-0056a: Voice Activity Detection, energy threshold -50dB, 2s silence threshold, RMS energy calculation

- **ASR Ingress** → Partial Results
  - File: `k0/pipelines/p11_asr/partial_result_emitter.py`
  - ADR-0056a: Stream intermediate ASR transcripts, is_partial flag, typing indicator UX, final transcript on turn boundary

- **TTS Synthesis** → Prosody Controls
  - File: `k0/pipelines/p12_tts/prosody_generator.py`
  - ADR-0056d: Pitch control (Hz), rate control (words/min), emphasis patterns (stress), SSML generation

- **TTS Synthesis** → SSML Generation
  - File: `k0/pipelines/p12_tts/ssml_generator.py`
  - ADR-0056d: Convert text + prosody to SSML, <prosody> tags, <emphasis> tags, <break> pauses

- **TTS Synthesis** → Streaming Audio
  - File: `k0/pipelines/p12_tts/streaming_synthesizer.py`
  - ADR-0056d: Chunk-based TTS synthesis, 40ms audio chunks, async iterator, VITS model

- **Audio Output** → Buffer Management
  - File: `k0/pipelines/p12_tts/audio_buffer_manager.py`
  - ADR-0056e: Jitter buffer (80ms), frame reordering, packet loss recovery, adaptive buffering

#### [ADR-0056a](../../docs/architecture/decisions/0056a-*.md): 0056A ASR Ingress

**Components:**

- **ASR Ingress** → Frame Handling
  - File: `k0/pipelines/p11_asr/frame_handler.py`
  - ADR-0056a: 20ms audio frames, buffering strategy, frame drop policy at 80% capacity

- **ASR Ingress** → VAD Processing
  - File: `k0/pipelines/p11_asr/vad_processor.py`
  - ADR-0056a: Voice Activity Detection, energy threshold -50dB, 2s silence threshold, RMS energy calculation

- **ASR Ingress** → Partial Results
  - File: `k0/pipelines/p11_asr/partial_result_emitter.py`
  - ADR-0056a: Stream intermediate ASR transcripts, is_partial flag, typing indicator UX, final transcript on turn boundary

#### [ADR-0056d](../../docs/architecture/decisions/0056d-*.md): 0056D TTS Synthesis

**Components:**

- **TTS Synthesis** → Prosody Controls
  - File: `k0/pipelines/p12_tts/prosody_generator.py`
  - ADR-0056d: Pitch control (Hz), rate control (words/min), emphasis patterns (stress), SSML generation

- **TTS Synthesis** → SSML Generation
  - File: `k0/pipelines/p12_tts/ssml_generator.py`
  - ADR-0056d: Convert text + prosody to SSML, <prosody> tags, <emphasis> tags, <break> pauses

- **TTS Synthesis** → Streaming Audio
  - File: `k0/pipelines/p12_tts/streaming_synthesizer.py`
  - ADR-0056d: Chunk-based TTS synthesis, 40ms audio chunks, async iterator, VITS model

#### [ADR-0056e](../../docs/architecture/decisions/0056e-*.md): 0056E Audio Output

**Components:**

- **Audio Output** → Buffer Management
  - File: `k0/pipelines/p12_tts/audio_buffer_manager.py`
  - ADR-0056e: Jitter buffer (80ms), frame reordering, packet loss recovery, adaptive buffering


### WFQ Scheduler

#### [ADR-0028](../../docs/architecture/decisions/0028-*.md): 0028 Priority Queues

**Components:**

- **Priority Queues** → URGENT Queue
  - File: `k1/l2_orchestration/scheduler/priority_queues.py`
  - Weight 10, ≤50ms latency, barge-in/cancel/emergency, preempts all lower priorities, heap-based O(log n)

- **Priority Queues** → REALTIME Queue
  - File: `k1/l2_orchestration/scheduler/priority_queues.py`
  - Weight 5, ≤150ms latency, voice turns/inference/tools, preempts INTERACTIVE/BACKGROUND

- **Priority Queues** → INTERACTIVE Queue
  - File: `k1/l2_orchestration/scheduler/priority_queues.py`
  - Weight 3, ≤300ms latency, UI clicks/text input/config reload, preempts BACKGROUND

- **Priority Queues** → BACKGROUND Queue
  - File: `k1/l2_orchestration/scheduler/priority_queues.py`
  - Weight 1, ≤5000ms latency, learning/sync/cleanup, preemptable by all

- **Virtual Time** → Virtual Time Tracking
  - File: `k1/l2_orchestration/scheduler/virtual_time.py`
  - vtime_finish = vtime_start + (turn_cost_ms / weight), fairness formula, O(1) calculation

- **Virtual Time** → Scheduling Algorithm
  - File: `k1/l2_orchestration/scheduler/wfq_scheduler.py`
  - Select session with smallest virtual finish time, min-heap O(log n) selection, deterministic

- **Virtual Time** → Proportional CPU Allocation
  - File: `k1/l2_orchestration/scheduler/wfq_scheduler.py`
  - URGENT 10× vs BACKGROUND 1×, fairness guarantee, weight-based bandwidth allocation

- **Virtual Time** → Session Priority Weights
  - File: `k1/l2_orchestration/scheduler/session_weights.py`
  - Safety 2.0, Active 1.0, Background 0.3, per-session weighting, multi-session fairness

- **Preemption** → Preemption Rules
  - File: `k1/l2_orchestration/scheduler/preemption_rules.py`
  - URGENT preempts all, REALTIME preempts INTERACTIVE/BACKGROUND, INTERACTIVE preempts BACKGROUND

- **Preemption** → Preemption Flow
  - File: `k1/l2_orchestration/scheduler/preemption_manager.py`
  - Save inference state, interrupt current task, run high priority, resume from checkpoint, <10ms overhead

- **Preemption** → Priority Manager
  - File: `k1/l2_orchestration/scheduler/priority_manager.py`
  - 3 priority classes (SAFETY/ACTIVE/BACKGROUND), preemption rules enforcement, preemption metrics

- **Anti-Starvation** → Age-Based Boosting
  - File: `k1/l2_orchestration/scheduler/starvation_preventer.py`
  - effective_weight = base_weight × (1 + 0.1 × wait_seconds), 10% boost per second, prevents starvation

- **Anti-Starvation** → Forced Scheduling
  - File: `k1/l2_orchestration/scheduler/starvation_preventer.py`
  - Force-schedule sessions waiting >5s, 5-second max wait time, regardless of virtual time

- **Anti-Starvation** → Wait Time Tracking
  - File: `k1/l2_orchestration/scheduler/wait_time_tracker.py`
  - Monitor P50/P95/P99 wait time per priority class, starvation detection, Prometheus metrics

- **Anti-Starvation** → Aging Metrics
  - File: `k1/l2_orchestration/scheduler/starvation_preventer.py`
  - Track age boost factor, forced scheduling events, starvation prevention effectiveness

- **Deadline Tracking** → Per-Task Deadlines
  - File: `k1/l2_orchestration/scheduler/deadline_tracker.py`
  - Deadline = submit_time + max_latency, deadline-aware scheduling, ≤50ms/≤150ms/≤300ms/≤5s

- **Deadline Tracking** → Missed Deadline Alerts
  - File: `k1/l2_orchestration/scheduler/deadline_tracker.py`
  - Log missed deadlines, Prometheus alerts, deadline violation rate tracking

- **Yield Mechanism** → CPU-Bound Yield
  - File: `k1/l2_orchestration/scheduler/yield_manager.py`
  - Yield every 10ms for long-running tasks, resume next cycle, <0.5ms yield overhead

- **Yield Mechanism** → Cooperative Multitasking
  - File: `k1/l2_orchestration/scheduler/yield_manager.py`
  - Explicit yield points, prevent monopolization, single-threaded event loop compatibility

#### [ADR-0028a](../../docs/architecture/decisions/0028a-*.md): 0028A Virtual Time

**Components:**

- **Virtual Time** → Virtual Time Tracking
  - File: `k1/l2_orchestration/scheduler/virtual_time.py`
  - vtime_finish = vtime_start + (turn_cost_ms / weight), fairness formula, O(1) calculation

- **Virtual Time** → Scheduling Algorithm
  - File: `k1/l2_orchestration/scheduler/wfq_scheduler.py`
  - Select session with smallest virtual finish time, min-heap O(log n) selection, deterministic

- **Virtual Time** → Proportional CPU Allocation
  - File: `k1/l2_orchestration/scheduler/wfq_scheduler.py`
  - URGENT 10× vs BACKGROUND 1×, fairness guarantee, weight-based bandwidth allocation

- **Virtual Time** → Session Priority Weights
  - File: `k1/l2_orchestration/scheduler/session_weights.py`
  - Safety 2.0, Active 1.0, Background 0.3, per-session weighting, multi-session fairness

#### [ADR-0028b](../../docs/architecture/decisions/0028b-*.md): 0028B Preemption

**Components:**

- **Preemption** → Preemption Rules
  - File: `k1/l2_orchestration/scheduler/preemption_rules.py`
  - URGENT preempts all, REALTIME preempts INTERACTIVE/BACKGROUND, INTERACTIVE preempts BACKGROUND

- **Preemption** → Preemption Flow
  - File: `k1/l2_orchestration/scheduler/preemption_manager.py`
  - Save inference state, interrupt current task, run high priority, resume from checkpoint, <10ms overhead

- **Preemption** → Priority Manager
  - File: `k1/l2_orchestration/scheduler/priority_manager.py`
  - 3 priority classes (SAFETY/ACTIVE/BACKGROUND), preemption rules enforcement, preemption metrics

#### [ADR-0028c](../../docs/architecture/decisions/0028c-*.md): 0028C Anti-Starvation

**Components:**

- **Anti-Starvation** → Age-Based Boosting
  - File: `k1/l2_orchestration/scheduler/starvation_preventer.py`
  - effective_weight = base_weight × (1 + 0.1 × wait_seconds), 10% boost per second, prevents starvation

- **Anti-Starvation** → Forced Scheduling
  - File: `k1/l2_orchestration/scheduler/starvation_preventer.py`
  - Force-schedule sessions waiting >5s, 5-second max wait time, regardless of virtual time

- **Anti-Starvation** → Wait Time Tracking
  - File: `k1/l2_orchestration/scheduler/wait_time_tracker.py`
  - Monitor P50/P95/P99 wait time per priority class, starvation detection, Prometheus metrics

- **Anti-Starvation** → Aging Metrics
  - File: `k1/l2_orchestration/scheduler/starvation_preventer.py`
  - Track age boost factor, forced scheduling events, starvation prevention effectiveness


### WebSocket Binary Protocol

#### [ADR-0015](../../docs/architecture/decisions/0015-*.md): 0015 Protocol Design

**Components:**

- **Protocol Design** → Message Envelope
  - File: `k1/schemas/websocket/message_envelope.fbs`
  - MessageEnvelope, 17 message types, protocol_version, sequence_number, trace_id

- **Protocol Design** → Message Types
  - File: `k1/schemas/websocket/message_types.fbs`
  - TURN_START, TOKEN_CHUNK, TOOL_CALL, BARGE_IN, PING/PONG (17 types)

- **Protocol Design** → Client→Server Messages
  - File: `k1/schemas/websocket/client_messages.fbs`
  - TurnStart, TurnChunk, BargeIn, ToolApproval (4 types)

- **Protocol Design** → Server→Client Messages
  - File: `k1/schemas/websocket/server_messages.fbs`
  - TokenChunk, ToolCall, ToolResult, StateDelta, GroundingCommit (7 types)

#### [ADR-0015a](../../docs/architecture/decisions/0015a-*.md): 0015A Protocol Design

**Components:**

- **Protocol Design** → Message Envelope
  - File: `k1/schemas/websocket/message_envelope.fbs`
  - MessageEnvelope, 17 message types, protocol_version, sequence_number, trace_id

- **Protocol Design** → Message Types
  - File: `k1/schemas/websocket/message_types.fbs`
  - TURN_START, TOKEN_CHUNK, TOOL_CALL, BARGE_IN, PING/PONG (17 types)

#### [ADR-0015b](../../docs/architecture/decisions/0015b-*.md): 0015B Flow Control

**Components:**

- **Flow Control** → ACK Protocol
  - File: `k1/schemas/websocket/ack.fbs`
  - ACK message, ack_seqno, batch 5 messages or 1s, <5% overhead

- **Flow Control** → ACK Manager Client
  - File: `sdk/typescript/ack_manager.ts`
  - AckManager, batched ACKs, unackedCount, lastAckTime tracking

#### [ADR-0015c](../../docs/architecture/decisions/0015c-*.md): 0015C Reconnection

**Components:**

- **Reconnection** → Resume Protocol
  - File: `k1/schemas/websocket/resume.fbs`
  - RESUME message, last_recv_seqno, ResumeResponse, 5 status codes

- **Reconnection** → Client Reconnect Manager
  - File: `sdk/typescript/reconnect_manager.ts`
  - ReconnectManager, exponential backoff 1s→16s, max 5 attempts

- **Reconnection** → Deduplication Manager
  - File: `sdk/typescript/dedup_manager.ts`
  - DeduplicationManager, 2000 seqno cache, skip replayed messages

#### [ADR-0015d](../../docs/architecture/decisions/0015d-*.md): 0015D Streaming

**Components:**

- **Streaming** → Token Schema
  - File: `k1/schemas/websocket/token_chunk.fbs`
  - TOKEN_CHUNK, chunk_index, logprob, finish_reason, model_id, tokens_generated

#### [ADR-0015e](../../docs/architecture/decisions/0015e-*.md): 0015E Client SDK

**Components:**

- **Client SDK** → TypeScript SDK Core
  - File: `sdk/typescript/k1_websocket.ts`
  - K1WebSocket class, binary WebSocket, FlatBuffers bindings, 1800 lines

- **Client SDK** → Reconnect Manager
  - File: `sdk/typescript/reconnect_manager.ts`
  - ReconnectManager, exponential backoff, RESUME message, 5 attempts max

- **Client SDK** → ACK Manager
  - File: `sdk/typescript/ack_manager.ts`
  - AckManager, batch 5 messages or 1s, flow control, periodic timer

- **Client SDK** → Deduplication Manager
  - File: `sdk/typescript/dedup_manager.ts`
  - DeduplicationManager, Set<number> cache, max 2000 entries, eviction

- **Client SDK** → React Hooks
  - File: `sdk/typescript/use_k1_websocket.ts`
  - useK1WebSocket, useTokenStreaming hooks, connection state, useEffect cleanup

- **Client SDK** → Message Serialization
  - File: `sdk/typescript/serialization.ts`
  - serializeEnvelope, deserializeEnvelope, FlatBuffers builder/reader, ArrayBuffer


---

## Usage Guidelines

1. **Before Development**: Review relevant ADRs to understand architectural decisions and constraints
2. **During Development**: Reference specific ADR sections for implementation details and patterns
3. **Code Reviews**: Verify implementations align with ADR specifications
4. **Updates**: If you modify an ADR, regenerate this file using `python scripts/generate_layer_adr_references.py`

## Legend

- **Family**: High-level architectural area (e.g., Actor Fabric, Bridge, K0 Core)
- **Components**: Specific implementation components covered by the ADR
- **File**: Python module path where component is implemented
- **N/A ADRs**: Cross-cutting concerns that apply to all layers

---

*This file is auto-generated. Do not edit manually. Regenerate using:*
```bash
python scripts/generate_layer_adr_references.py
```