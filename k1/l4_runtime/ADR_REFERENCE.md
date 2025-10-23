# ADR Reference Guide: Layer 4 - Runtime

**Generated:** Auto-generated from ADR family map  
**Purpose:** Quick reference for ADRs relevant to Layer 4 - Runtime development

## Overview

This layer manages session state, learning loops, and runtime coordination.

**Total Relevant ADRs:** 154

---

## Quick Reference: All ADRs for Layer 4 - Runtime

| ADR | Title | Family |
|-----|-------|--------|
| [ADR-0001](../../docs/architecture/decisions/0001-*.md) | 0001 Memory Kernel | K0 Core |
| [ADR-0001f](../../docs/architecture/decisions/0001f-*.md) | 0001F State Management | K1 Core |
| [ADR-0002](../../docs/architecture/decisions/0002-*.md) | 0002 Actor Model | Actor Fabric |
| [ADR-0002a](../../docs/architecture/decisions/0002a-*.md) | 0002A Mailbox | Actor Fabric |
| [ADR-0002b](../../docs/architecture/decisions/0002b-*.md) | 0002B Supervisor | Actor Fabric |
| [ADR-0002c](../../docs/architecture/decisions/0002c-*.md) | 0002C Router | Actor Fabric |
| [ADR-0003](../../docs/architecture/decisions/0003-*.md) | 0003 PDL Language | Protocol Validation |
| [ADR-0003a](../../docs/architecture/decisions/0003a-*.md) | 0003A PDL Language | Protocol Validation |
| [ADR-0003b](../../docs/architecture/decisions/0003b-*.md) | 0003B Protocol Definitions | Protocol Validation |
| [ADR-0003c](../../docs/architecture/decisions/0003c-*.md) | 0003C Protocol Monitor | Protocol Validation |
| [ADR-0003d](../../docs/architecture/decisions/0003d-*.md) | 0003D Security | Protocol Validation |
| [ADR-0004](../../docs/architecture/decisions/0004-*.md) | 0004 Architecture | K1 Core |
| [ADR-0004b](../../docs/architecture/decisions/0004b-*.md) | 0004B Dependencies | K1 Core |
| [ADR-0004c](../../docs/architecture/decisions/0004c-*.md) | 0004C Documentation | ADR Notes |
| [ADR-0004d](../../docs/architecture/decisions/0004d-*.md) | 0004D Testing | K1 Core |
| [ADR-0005](../../docs/architecture/decisions/0005-*.md) | 0005 Lifecycle FSM | Agent Lifecycle |
| [ADR-0005b](../../docs/architecture/decisions/0005b-*.md) | 0005B IDLE Pooling | Agent Lifecycle |
| [ADR-0005c](../../docs/architecture/decisions/0005c-*.md) | 0005C DRAINING State | Agent Lifecycle |
| [ADR-0005d](../../docs/architecture/decisions/0005d-*.md) | 0005D Supervisor | Agent Lifecycle |
| [ADR-0005e](../../docs/architecture/decisions/0005e-*.md) | 0005E Personalities | Agent Lifecycle |
| [ADR-0007d](../../docs/architecture/decisions/0007d-*.md) | 0007D Stage 4 Commit | 4-Stage Planning |
| [ADR-0008d](../../docs/architecture/decisions/0008d-*.md) | 0008D Deadlock Handling | Saga Error Recovery |
| [ADR-0010b](../../docs/architecture/decisions/0010b-*.md) | 0010B Assignment Policy | Capability Security |
| [ADR-0010c](../../docs/architecture/decisions/0010c-*.md) | 0010C Runtime Enforcement | Capability Security |
| [ADR-0011a](../../docs/architecture/decisions/0011a-*.md) | 0011A Schema Design | FlatBuffers |
| [ADR-0011b](../../docs/architecture/decisions/0011b-*.md) | 0011B Code Generation | FlatBuffers |
| [ADR-0011c](../../docs/architecture/decisions/0011c-*.md) | 0011C Performance | FlatBuffers |
| [ADR-0011d](../../docs/architecture/decisions/0011d-*.md) | 0011D Schema Evolution | FlatBuffers |
| [ADR-0012](../../docs/architecture/decisions/0012-*.md) | 0012 Schema Taxonomy | FlatBuffers Schemas |
| [ADR-0012d](../../docs/architecture/decisions/0012d-*.md) | 0012D Layer 4 Schemas | FlatBuffers Schemas |
| [ADR-0013](../../docs/architecture/decisions/0013-*.md) | 0013 SemVer Policy | Schema Versioning |
| [ADR-0013a](../../docs/architecture/decisions/0013a-*.md) | 0013A Version Registry | Schema Versioning |
| [ADR-0013b](../../docs/architecture/decisions/0013b-*.md) | 0013B CI/CD Automation | Schema Versioning |
| [ADR-0013c](../../docs/architecture/decisions/0013c-*.md) | 0013C Deprecation Workflow | Schema Versioning |
| [ADR-0013d](../../docs/architecture/decisions/0013d-*.md) | 0013D Contract Testing | Schema Versioning |
| [ADR-0014](../../docs/architecture/decisions/0014-*.md) | 0014 Content Negotiation | REST API |
| [ADR-0014a](../../docs/architecture/decisions/0014a-*.md) | 0014A Content Negotiation | REST API Dual Format |
| [ADR-0014b](../../docs/architecture/decisions/0014b-*.md) | 0014B OpenAPI Generation | REST API Dual Format |
| [ADR-0014c](../../docs/architecture/decisions/0014c-*.md) | 0014C Serialization Pipeline | REST API Dual Format |
| [ADR-0014d](../../docs/architecture/decisions/0014d-*.md) | 0014D Client SDKs | REST API Dual Format |
| [ADR-0015](../../docs/architecture/decisions/0015-*.md) | 0015 Protocol Design | WebSocket Binary Protocol |
| [ADR-0015a](../../docs/architecture/decisions/0015a-*.md) | 0015A Message Routing | WebSocket Binary Protocol |
| [ADR-0015b](../../docs/architecture/decisions/0015b-*.md) | 0015B Flow Control | WebSocket Binary Protocol |
| [ADR-0015c](../../docs/architecture/decisions/0015c-*.md) | 0015C Reconnection | WebSocket Binary Protocol |
| [ADR-0015d](../../docs/architecture/decisions/0015d-*.md) | 0015D Streaming | WebSocket Binary Protocol |
| [ADR-0015e](../../docs/architecture/decisions/0015e-*.md) | 0015E Client SDK | WebSocket Binary Protocol |
| [ADR-0016](../../docs/architecture/decisions/0016-*.md) | 0016 Event Taxonomy | SSE Event Schemas |
| [ADR-0016a](../../docs/architecture/decisions/0016a-*.md) | 0016A Event Taxonomy | SSE Event Schemas |
| [ADR-0016b](../../docs/architecture/decisions/0016b-*.md) | 0016B Serialization | SSE Event Schemas |
| [ADR-0016c](../../docs/architecture/decisions/0016c-*.md) | 0016C Filtering | SSE Event Schemas |
| [ADR-0016d](../../docs/architecture/decisions/0016d-*.md) | 0016D Browser Integration | SSE Event Schemas |
| [ADR-0017](../../docs/architecture/decisions/0017-*.md) | 0017 Overall Architecture | SessionState 6-Section Design |
| [ADR-0017a](../../docs/architecture/decisions/0017a-*.md) | 0017A Beliefs Section | SessionState 6-Section Design |
| [ADR-0017b](../../docs/architecture/decisions/0017b-*.md) | 0017B Scoreboard Section | SessionState 6-Section Design |
| [ADR-0017c](../../docs/architecture/decisions/0017c-*.md) | 0017C Control Section | SessionState 6-Section Design |
| [ADR-0017d](../../docs/architecture/decisions/0017d-*.md) | 0017D Persona Section | SessionState 6-Section Design |
| [ADR-0017e](../../docs/architecture/decisions/0017e-*.md) | 0017E Multimodal Section | SessionState 6-Section Design |
| [ADR-0017f](../../docs/architecture/decisions/0017f-*.md) | 0017F Meta Section | SessionState 6-Section Design |
| [ADR-0018](../../docs/architecture/decisions/0018-*.md) | 0018 Eviction Architecture | 3-Tier Eviction Strategy |
| [ADR-0018a](../../docs/architecture/decisions/0018a-*.md) | 0018A Tier 1 Soft Eviction | 3-Tier Eviction Strategy |
| [ADR-0018b](../../docs/architecture/decisions/0018b-*.md) | 0018B Tier 2 Hard Eviction | 3-Tier Eviction Strategy |
| [ADR-0018c](../../docs/architecture/decisions/0018c-*.md) | 0018C Tier 3 OOM Prevention | 3-Tier Eviction Strategy |
| [ADR-0019](../../docs/architecture/decisions/0019-*.md) | 0019 Serialization Core | FlatBuffers SessionState Serialization |
| [ADR-0019a](../../docs/architecture/decisions/0019a-*.md) | 0019A Schema Definition | FlatBuffers SessionState Serialization |
| [ADR-0019b](../../docs/architecture/decisions/0019b-*.md) | 0019B Serialization Core | FlatBuffers SessionState Serialization |
| [ADR-0019c](../../docs/architecture/decisions/0019c-*.md) | 0019C K0 WAL Integration | FlatBuffers SessionState Serialization |
| [ADR-0019d](../../docs/architecture/decisions/0019d-*.md) | 0019D Serialization Core | FlatBuffers SessionState Serialization |
| [ADR-0020](../../docs/architecture/decisions/0020-*.md) | 0020 Lifecycle Management | Multi-Tier Storage |
| [ADR-0020a](../../docs/architecture/decisions/0020a-*.md) | 0020A Hot Tier (L1 RAM) | Multi-Tier Storage |
| [ADR-0020b](../../docs/architecture/decisions/0020b-*.md) | 0020B Warm Tier (L2 SSD) | Multi-Tier Storage |
| [ADR-0020c](../../docs/architecture/decisions/0020c-*.md) | 0020C Cold Tier (L3 Object) | Multi-Tier Storage |
| [ADR-0021](../../docs/architecture/decisions/0021-*.md) | 0021 Retention Policies | Turn History Retention |
| [ADR-0021c](../../docs/architecture/decisions/0021c-*.md) | 0021C Compliance | Turn History Retention |
| [ADR-0022d](../../docs/architecture/decisions/0022d-*.md) | 0022D FlatBuffers Schema | K0 Bridge Batching |
| [ADR-0023](../../docs/architecture/decisions/0023-*.md) | 0023 Pagination Core | Cursor-Based Pagination |
| [ADR-0023a](../../docs/architecture/decisions/0023a-*.md) | 0023A Cursor Encoding | Cursor-Based Pagination |
| [ADR-0023b](../../docs/architecture/decisions/0023b-*.md) | 0023B REST API | Cursor-Based Pagination |
| [ADR-0023c](../../docs/architecture/decisions/0023c-*.md) | 0023C K0 WAL Query | Cursor-Based Pagination |
| [ADR-0024](../../docs/architecture/decisions/0024-*.md) | 0024 Component-Level Budgets | Performance Budgets |
| [ADR-0024b](../../docs/architecture/decisions/0024b-*.md) | 0024B Component-Level Budgets | Performance Budgets |
| [ADR-0024c](../../docs/architecture/decisions/0024c-*.md) | 0024C Memory Budgets | Performance Budgets |
| [ADR-0024d](../../docs/architecture/decisions/0024d-*.md) | 0024D Graceful Degradation | Performance Budgets |
| [ADR-0026](../../docs/architecture/decisions/0026-*.md) | 0026 User Notifications | Thermal Management |
| [ADR-0026d](../../docs/architecture/decisions/0026d-*.md) | 0026D User Notifications | Thermal Management |
| [ADR-0029](../../docs/architecture/decisions/0029-*.md) | 0029 Turn-Level | Prometheus Metrics |
| [ADR-0029b](../../docs/architecture/decisions/0029b-*.md) | 0029B Turn-Level | Prometheus Metrics |
| [ADR-0037](../../docs/architecture/decisions/0037-*.md) | 0037 Horizontal Scaling | JWT Authentication |
| [ADR-0037a](../../docs/architecture/decisions/0037a-*.md) | 0037A Token Generation | JWT Authentication |
| [ADR-0037b](../../docs/architecture/decisions/0037b-*.md) | 0037B Token Validation | JWT Authentication |
| [ADR-0037c](../../docs/architecture/decisions/0037c-*.md) | 0037C Refresh Token Flow | JWT Authentication |
| [ADR-0037d](../../docs/architecture/decisions/0037d-*.md) | 0037D Session Binding | JWT Authentication |
| [ADR-0040](../../docs/architecture/decisions/0040-*.md) | 0040 Protocol Foundation | WebSocket Realtime Chat |
| [ADR-0040a](../../docs/architecture/decisions/0040a-*.md) | 0040A Connection Management | WebSocket Realtime Chat |
| [ADR-0040b](../../docs/architecture/decisions/0040b-*.md) | 0040B Binary Serialization | WebSocket Realtime Chat |
| [ADR-0040c](../../docs/architecture/decisions/0040c-*.md) | 0040C Backpressure Flow Control | WebSocket Realtime Chat |
| [ADR-0040d](../../docs/architecture/decisions/0040d-*.md) | 0040D Heartbeat Reconnection | WebSocket Realtime Chat |
| [ADR-0041](../../docs/architecture/decisions/0041-*.md) | 0041 RESTful Principles | REST API Session Management |
| [ADR-0041a](../../docs/architecture/decisions/0041a-*.md) | 0041A Session Lifecycle CRUD | REST API Session Management |
| [ADR-0041b](../../docs/architecture/decisions/0041b-*.md) | 0041B Idempotency | REST API Session Management |
| [ADR-0041c](../../docs/architecture/decisions/0041c-*.md) | 0041C Pagination | REST API Session Management |
| [ADR-0041d](../../docs/architecture/decisions/0041d-*.md) | 0041D Documentation | REST API Session Management |
| [ADR-0042a](../../docs/architecture/decisions/0042a-*.md) | 0042A Event Production | K0 SSE Event Streaming |
| [ADR-0042d](../../docs/architecture/decisions/0042d-*.md) | 0042D Backpressure | K0 SSE Event Streaming |
| [ADR-0043c](../../docs/architecture/decisions/0043c-*.md) | 0043C Topic Routing | SSE Topic Taxonomy |
| [ADR-0046](../../docs/architecture/decisions/0046-*.md) | 0046 Bridge Architecture | SSE-WebSocket Bridge |
| [ADR-0047](../../docs/architecture/decisions/0047-*.md) | 0047 Auto-Generation | OpenAPI 3.1 Specs |
| [ADR-0048](../../docs/architecture/decisions/0048-*.md) | 0048 Bus Architecture | K1 Internal Event Bus |
| [ADR-0049](../../docs/architecture/decisions/0049-*.md) | 0049 Configuration | Fast/Smart Lane Router |
| [ADR-0050](../../docs/architecture/decisions/0050-*.md) | 0050 Sync Strategy | Multi-Device Family Sync |
| [ADR-0050a](../../docs/architecture/decisions/0050a-*.md) | 0050A SessionState Coherence | Multi-Device Family Sync |
| [ADR-0052](../../docs/architecture/decisions/0052-*.md) | 0052 Performance | Enhanced HITL Protocols |
| [ADR-0052a](../../docs/architecture/decisions/0052a-*.md) | 0052A Step-by-Step Approval | Enhanced HITL Protocols |
| [ADR-0052b](../../docs/architecture/decisions/0052b-*.md) | 0052B RED Band Approval | Enhanced HITL Protocols |
| [ADR-0052c](../../docs/architecture/decisions/0052c-*.md) | 0052C Nested Clarifications | Enhanced HITL Protocols |
| [ADR-0052d](../../docs/architecture/decisions/0052d-*.md) | 0052D Proactive Confirmation | Enhanced HITL Protocols |
| [ADR-0052e](../../docs/architecture/decisions/0052e-*.md) | 0052E Layer 4 Communication | HITL Schema Integration |
| [ADR-0053](../../docs/architecture/decisions/0053-*.md) | 0053 Main | Message Queue & Coalescing |
| [ADR-0053a](../../docs/architecture/decisions/0053a-*.md) | 0053A Coalesce Window | Message Queue & Coalescing |
| [ADR-0053b](../../docs/architecture/decisions/0053b-*.md) | 0053B Rate Limits | Message Queue & Coalescing |
| [ADR-0053c](../../docs/architecture/decisions/0053c-*.md) | 0053C Cancel Path | Message Queue & Coalescing |
| [ADR-0054](../../docs/architecture/decisions/0054-*.md) | 0054 Main | Turn Boundary Management |
| [ADR-0054a](../../docs/architecture/decisions/0054a-*.md) | 0054A Implicit Pause | Turn Boundary Management |
| [ADR-0054b](../../docs/architecture/decisions/0054b-*.md) | 0054B Explicit Submit | Turn Boundary Management |
| [ADR-0054c](../../docs/architecture/decisions/0054c-*.md) | 0054C MPST Transitions | Turn Boundary Management |
| [ADR-0055](../../docs/architecture/decisions/0055-*.md) | 0055 Main Detection | Context-Switch Detection |
| [ADR-0055a](../../docs/architecture/decisions/0055a-*.md) | 0055A Intent Drift Rules | Context-Switch Detection |
| [ADR-0055b](../../docs/architecture/decisions/0055b-*.md) | 0055B Switch Prompt | Context-Switch Detection |
| [ADR-0055c](../../docs/architecture/decisions/0055c-*.md) | 0055C History Management | Context-Switch Detection |
| [ADR-0056](../../docs/architecture/decisions/0056-*.md) | 0056 Pipeline Architecture | Voice Pipeline Implementation |
| [ADR-0056a](../../docs/architecture/decisions/0056a-*.md) | 0056A ASR Ingress | Voice Pipeline Implementation |
| [ADR-0056b](../../docs/architecture/decisions/0056b-*.md) | 0056B Intent Bridge | Voice Pipeline Implementation |
| [ADR-0056c](../../docs/architecture/decisions/0056c-*.md) | 0056C Tool Interleaving | Voice Pipeline Implementation |
| [ADR-0056d](../../docs/architecture/decisions/0056d-*.md) | 0056D TTS Synthesis | Voice Pipeline Implementation |
| [ADR-0056e](../../docs/architecture/decisions/0056e-*.md) | 0056E Audio Output | Voice Pipeline Implementation |
| [ADR-0057a](../../docs/architecture/decisions/0057a-*.md) | 0057A Frame Drop Policy | Voice Backpressure |
| [ADR-0057b](../../docs/architecture/decisions/0057b-*.md) | 0057B TTS Degradation | Voice Backpressure |
| [ADR-0057c](../../docs/architecture/decisions/0057c-*.md) | 0057C Barge-in Preemption | Voice Backpressure |
| [ADR-0060](../../docs/architecture/decisions/0060-*.md) | 0060 Management Core | Adaptive KV Cache |
| [ADR-0060a](../../docs/architecture/decisions/0060a-*.md) | 0060A Dynamic Placement | Adaptive KV Cache |
| [ADR-0060b](../../docs/architecture/decisions/0060b-*.md) | 0060B Eviction & Recovery | Adaptive KV Cache |
| [ADR-0076](../../docs/architecture/decisions/0076-*.md) | 0076 Compression Tier | KV Cache Optimization |
| [ADR-0077](../../docs/architecture/decisions/0077-*.md) | 0077 Thermal Profiling | Thermal Placement V2 |
| [ADR-0081](../../docs/architecture/decisions/0081-*.md) | 0081 Knowledge Graph | K0 Core |
| [ADR-0081a](../../docs/architecture/decisions/0081a-*.md) | 0081A Knowledge Graph | K0 Core |
| [ADR-0081b](../../docs/architecture/decisions/0081b-*.md) | 0081B Knowledge Graph | K0 Core |
| [ADR-0081c](../../docs/architecture/decisions/0081c-*.md) | 0081C Knowledge Graph | K0 Core |
| [ADR-0081d](../../docs/architecture/decisions/0081d-*.md) | 0081D Knowledge Graph | K0 Core |
| [ADR-0082](../../docs/architecture/decisions/0082-*.md) | 0082 Core Architecture | Multi-Party Dialogue |
| [ADR-0084](../../docs/architecture/decisions/0084-*.md) | 0084 Core Architecture | K0 Memory Consolidation |
| [ADR-0084a](../../docs/architecture/decisions/0084a-*.md) | 0084A Hippocampal Replay | K0 Memory Consolidation |
| [ADR-0084b](../../docs/architecture/decisions/0084b-*.md) | 0084B Sleep State Machine | K0 Memory Consolidation |
| [ADR-0084c](../../docs/architecture/decisions/0084c-*.md) | 0084C Knowledge Graph Consol. | K0 Memory Consolidation |
| [ADR-0084d](../../docs/architecture/decisions/0084d-*.md) | 0084D Dream Exploration | K0 Memory Consolidation |
| [ADR-0085](../../docs/architecture/decisions/0085-*.md) | 0085 Core Architecture | Embodied Awareness |

---

## Detailed Breakdown by Family

### 3-Tier Eviction Strategy

#### [ADR-0018](../../docs/architecture/decisions/0018-*.md): 0018 Eviction Architecture

**Components:**

- **Eviction Architecture** → 3-Tier Strategy
  - File: `k1/l4_runtime/session_state/eviction/eviction_coordinator.py`
  - Soft (64KB), hard (128KB), OOM (256KB) tiers, escalation triggers, coordination

- **Eviction Architecture** → Memory Budgets
  - File: `k1/l4_runtime/session_state/eviction/memory_tracker.py`
  - Per-agent limits, session quotas (64KB soft), global thresholds

- **Eviction Architecture** → Eviction Coordinator
  - File: `k1/l4_runtime/session_state/eviction/eviction_coordinator.py`
  - Tier orchestration, priority algorithms, safety checks, cascading eviction

- **Supporting Infrastructure** → Memory Tracker
  - File: `k1/l4_runtime/session_state/eviction/memory_tracker.py`
  - Per-agent memory (RSS tracking), session totals, thresholds (64KB/128KB/256KB)

- **Supporting Infrastructure** → Eviction Executor
  - File: `k1/l4_runtime/session_state/eviction/eviction_executor.py`
  - Eviction commands, state transitions, supervisor coordination

- **Supporting Infrastructure** → Metrics Collector
  - File: `k1/l4_runtime/session_state/eviction/metrics_collector.py`
  - Eviction counts (per tier), tier breakdown, memory timeseries, Prometheus export

#### [ADR-0018a](../../docs/architecture/decisions/0018a-*.md): 0018A Tier 1 Soft Eviction

**Components:**

- **Tier 1 Soft Eviction** → LRU Policy
  - File: `k1/l4_runtime/session_state/eviction/tier1_evictor.py`
  - Least recently used, aging algorithm, access tracking, last_accessed_ms

- **Tier 1 Soft Eviction** → Priority Eviction
  - File: `k1/l4_runtime/session_state/eviction/tier1_evictor.py`
  - Meta section first, old turns (4+), expired entities, old grounding acts

- **Tier 1 Soft Eviction** → Graceful Eviction
  - File: `k1/l4_runtime/session_state/eviction/tier1_evictor.py`
  - 64KB→80KB trigger, evict low-priority, <5ms latency, minimal UX impact

- **Tier 1 Soft Eviction** → Size Estimation
  - File: `k1/l4_runtime/session_state/eviction/tier1_evictor.py`
  - Cached section sizes <100μs, no re-serialization, threshold check

- **Tier 1 Soft Eviction** → Metrics Collection
  - File: `k1/l4_runtime/session_state/eviction/tier1_evictor.py`
  - eviction_tier1_total, eviction_tier1_bytes, eviction_tier1_latency_ms

#### [ADR-0018b](../../docs/architecture/decisions/0018b-*.md): 0018B Tier 2 Hard Eviction

**Components:**

- **Tier 2 Hard Eviction** → Memory Pressure Detection
  - File: `k1/l4_runtime/session_state/eviction/tier2_evictor.py`
  - 128KB→192KB trigger, 50% buffer, watermark monitoring, hysteresis

- **Tier 2 Hard Eviction** → Beliefs LRU
  - File: `k1/l4_runtime/session_state/eviction/tier2_evictor.py`
  - Least recently accessed facts, target 15KB, sort by last_accessed_ms

- **Tier 2 Hard Eviction** → Scoreboard LRU
  - File: `k1/l4_runtime/session_state/eviction/tier2_evictor.py`
  - Least salient entities, target 4KB, sort by salience score

- **Tier 2 Hard Eviction** → Multimodal Compression
  - File: `k1/l4_runtime/session_state/eviction/tier2_evictor.py`
  - zstd compression (level 3), 70% size reduction, <3ms latency

- **Tier 2 Hard Eviction** → UX Impact Tracking
  - File: `k1/l4_runtime/session_state/eviction/tier2_evictor.py`
  - UX impact score (0.0-1.0), context loss measurement, eviction frequency (0.1%)

#### [ADR-0018c](../../docs/architecture/decisions/0018c-*.md): 0018C Tier 3 OOM Prevention

**Components:**

- **Tier 3 OOM Prevention** → OOM Detection
  - File: `k1/l4_runtime/session_state/eviction/tier3_oom_prevention.py`
  - 256KB threshold, kernel pressure signals, emergency triggers

- **Tier 3 OOM Prevention** → Critical State Save
  - File: `k1/l4_runtime/session_state/eviction/tier3_oom_prevention.py`
  - Save beliefs + persona to K0, recovery_token (UUID), <10ms save

- **Tier 3 OOM Prevention** → User Notification
  - File: `k1/l4_runtime/session_state/eviction/tier3_oom_prevention.py`
  - SSE event (session.terminated), reason=OOM, recovery instructions

- **Tier 3 OOM Prevention** → Session Termination
  - File: `k1/l4_runtime/session_state/eviction/tier3_oom_prevention.py`
  - Graceful kill, cleanup resources, destroy session, <20ms total

- **Tier 3 OOM Prevention** → Prometheus Alerts
  - File: `k1/l4_runtime/session_state/eviction/tier3_oom_prevention.py`
  - session_oom_terminated_total, CRITICAL alert (should be zero), investigation trigger


### 4-Stage Planning

#### [ADR-0007d](../../docs/architecture/decisions/0007d-*.md): 0007D Stage 4 Commit

**Components:**

- **Stage 4 Commit** → SessionState Locking
  - File: `k1/l4_runtime/session_state/locking.py`
  - current_flow field, flow_id, concurrent plan prevention, <0.1ms


### ADR Notes

#### [ADR-0004c](../../docs/architecture/decisions/0004c-*.md): 0004C Documentation

**Components:**

- **Documentation** → Module READMEs
  - File: `tools/k1_doc_gen.py`
  - k1-doc-gen, README template, auto-generation, docstring extraction, metadata parsing, CI enforcement


### Actor Fabric

#### [ADR-0002](../../docs/architecture/decisions/0002-*.md): 0002 Actor Model

**Components:**

- **Actor Model** → Core Implementation
  - File: `k1/l4_runtime/actor_fabric/actor.py`
  - Isolated actors, message passing, no shared memory, supervision trees

- **Actor Model** → Hybrid Architecture
  - File: `k1/l4_runtime/actor_fabric/hybrid.py`
  - AI agents (4), pure actors (54), mailboxes, deterministic vs LLM

#### [ADR-0002a](../../docs/architecture/decisions/0002a-*.md): 0002A Mailbox

**Components:**

- **Mailbox** → MPSC Queue
  - File: `k1/l4_runtime/actor_fabric/mailbox/mpsc_queue.py`
  - Ring buffer, 4-tier priority, WFQ scheduler, backpressure, DLQ, TTL

- **Mailbox** → Priority Scheduling
  - File: `k1/l4_runtime/actor_fabric/mailbox/scheduler.py`
  - URGENT/REALTIME/INTERACTIVE/BACKGROUND, aging, starvation prevention, virtual time

- **Mailbox** → Backpressure
  - File: `k1/l4_runtime/actor_fabric/mailbox/backpressure.py`
  - High watermark (50), low watermark (25), overflow policies, DROP_OLDEST

- **Mailbox** → Dead Letter Queue
  - File: `k1/l4_runtime/actor_fabric/mailbox/dlq.py`
  - 100 messages, 5 min retention, dropped reasons, debugging

#### [ADR-0002b](../../docs/architecture/decisions/0002b-*.md): 0002B Supervisor

**Components:**

- **Supervisor** → Health Check
  - File: `k1/l4_runtime/actor_fabric/supervisor/health_check.py`
  - 1Hz ping, 1.5s timeout, event-loop heartbeat (200ms)

- **Supervisor** → Crash Detection
  - File: `k1/l4_runtime/actor_fabric/supervisor/crash_detection.py`
  - Process termination, ping timeout, event-loop stall, <2s detection

- **Supervisor** → Blacklist
  - File: `k1/l4_runtime/actor_fabric/supervisor/blacklist.py`
  - 3 crashes in 10 min, 1 hour duration, per-version

- **Supervisor** → Restart Strategies
  - File: `k1/l4_runtime/actor_fabric/supervisor/restart.py`
  - Exponential backoff (200ms→30s), max 5 attempts, reset after 10 min

#### [ADR-0002c](../../docs/architecture/decisions/0002c-*.md): 0002C Router

**Components:**

- **Router** → Actor Router
  - File: `k1/l4_runtime/actor_fabric/router/router.py`
  - Location transparency, routing table, admission control, 5-check pipeline

- **Router** → Admission Control
  - File: `k1/l4_runtime/actor_fabric/router/admission.py`
  - Capability verification, role attestation, token bucket, in-flight limits, session quotas

- **Router** → Token Bucket
  - File: `k1/l4_runtime/actor_fabric/router/token_bucket.py`
  - 100 msg/s sustained, 150 burst, per-sender, refill rate

- **Router** → Capability Verification
  - File: `k1/l4_runtime/actor_fabric/router/capability_verifier.py`
  - HMAC-SHA256, lease signature, expiration, sender/receiver match


### Adaptive KV Cache

#### [ADR-0060](../../docs/architecture/decisions/0060-*.md): 0060 Management Core

**Components:**

- **Management Core** → Dynamic Placement
  - File: `k1/l4_runtime/kv_cache/adaptive_manager.py`
  - Adaptive KV-cache: thermal workload backpressure-based placement, session state agent count metrics sizing

- **Management Core** → Eviction Policies
  - File: `k1/l4_runtime/kv_cache/adaptive_manager.py`
  - Hot/cold eviction: immediate removal under stress, gradual removal on inactivity, recovery with rollback

- **Management Core** → Integration
  - File: `k1/l4_runtime/kv_cache/adaptive_manager.py`
  - Thermal manager integration, backpressure cascade integration, session state boundaries

- **Management Core** → Observability
  - File: `k1/l4_runtime/kv_cache/adaptive_manager.py`
  - Prometheus metrics OpenTelemetry tracing, config agent_fabric.yml sessionstate.yml, capability-based access

#### [ADR-0060a](../../docs/architecture/decisions/0060a-*.md): 0060A Dynamic Placement

**Components:**

- **Dynamic Placement** → Region Assignment
  - File: `k1/l4_runtime/kv_cache/placement.py`
  - Cache region per agent/session, thermal_manager.get_score workload backpressure placement

- **Dynamic Placement** → Sizing Algorithm
  - File: `k1/l4_runtime/kv_cache/placement.py`
  - assign_cache_region adjust_cache_size, kv_cache.set_region, agent migration session handoff

- **Dynamic Placement** → Optimization
  - File: `k1/l4_runtime/kv_cache/placement.py`
  - Cache hit rate optimization, thrashing prevention, thermal overload prevention

- **Dynamic Placement** → Metrics
  - File: `k1/l4_runtime/kv_cache/placement.py`
  - Prometheus cache region usage hit/miss rate, OpenTelemetry cache migration resizing handoff

#### [ADR-0060b](../../docs/architecture/decisions/0060b-*.md): 0060B Eviction & Recovery

**Components:**

- **Eviction & Recovery** → Hot Eviction
  - File: `k1/l4_runtime/kv_cache/eviction.py`
  - Immediate removal: thermal_manager.is_overloaded backpressure_cascade.is_stressed triggers, kv_cache.evict hot mode

- **Eviction & Recovery** → Cold Eviction
  - File: `k1/l4_runtime/kv_cache/eviction.py`
  - Gradual removal: kv_cache.is_inactive memory_manager.is_pressure triggers, persist_state_to_k0

- **Eviction & Recovery** → Recovery
  - File: `k1/l4_runtime/kv_cache/eviction.py`
  - kv_cache.restore rollback_if_needed, session reactivation trigger, migrate_agent_or_session

- **Eviction & Recovery** → Metrics & Tracing
  - File: `k1/l4_runtime/kv_cache/eviction.py`
  - Eviction/recovery metrics Prometheus counters, OpenTelemetry spans, eviction mode hot/cold tracking


### Agent Lifecycle

#### [ADR-0005](../../docs/architecture/decisions/0005-*.md): 0005 Lifecycle FSM

**Components:**

- **Lifecycle FSM** → State Machine Core
  - File: `k1/l4_runtime/agent_lifecycle/lifecycle.py`
  - 6-state FSM, transition guards, monotonic clock, single-writer pattern

- **Lifecycle FSM** → State Definitions
  - File: `k1/l4_runtime/agent_lifecycle/states.py`
  - PENDING, WARMING, ACTIVE, IDLE, DRAINING, TERMINATED states

- **Lifecycle FSM** → Transition Guards
  - File: `k1/l4_runtime/agent_lifecycle/guards.py`
  - Precondition checks, lease validation, quiescence detection (200ms)

- **Lifecycle FSM** → Supervisor Authority
  - File: `k1/l4_runtime/agent_lifecycle/supervisor_authority.py`
  - Single-writer, intent-based transitions, monotonic deadlines

#### [ADR-0005b](../../docs/architecture/decisions/0005b-*.md): 0005B IDLE Pooling

**Components:**

- **IDLE Pooling** → Idle Pool Manager
  - File: `k1/l4_runtime/agent_lifecycle/idle_pool_manager.py`
  - TTL tracking (5 min default), reactivation (<50ms P95), pool hit rate >80%

- **IDLE Pooling** → Memory Optimization
  - File: `k1/l4_runtime/agent_lifecycle/memory_optimizer.py`
  - 42% footprint reduction (90MB vs 155MB), prompt release, KV cache retained

- **IDLE Pooling** → Reactivation Handler
  - File: `k1/l4_runtime/agent_lifecycle/reactivation.py`
  - Prompt reload (8ms), IDLE→ACTIVE transition, 5× faster than cold start

#### [ADR-0005c](../../docs/architecture/decisions/0005c-*.md): 0005C DRAINING State

**Components:**

- **DRAINING State** → Draining Coordinator
  - File: `k1/l4_runtime/agent_lifecycle/draining_coordinator.py`
  - 3-phase drain (stop tasks, complete in-flight, cleanup), 5s timeout

- **DRAINING State** → Task Completion
  - File: `k1/l4_runtime/agent_lifecycle/task_completion.py`
  - In-flight completion (95% in 3s), force terminate after timeout

- **DRAINING State** → Resource Cleanup
  - File: `k1/l4_runtime/agent_lifecycle/resource_cleanup.py`
  - Model unload (200ms), KV cache free (100ms), metrics flush (50ms)

#### [ADR-0005d](../../docs/architecture/decisions/0005d-*.md): 0005D Supervisor

**Components:**

- **Supervisor** → Heartbeat Monitor
  - File: `k1/l4_runtime/actor_fabric/supervisor/heartbeat_monitor.py`
  - 1s interval, 3s timeout, event-loop heartbeat (200ms), <1% CPU overhead

- **Supervisor** → Crash Detector
  - File: `k1/l4_runtime/actor_fabric/supervisor/crash_detector.py`
  - <100ms detection, crash logging, replacement spawning, failure classification

- **Supervisor** → Blacklist Manager
  - File: `k1/l4_runtime/actor_fabric/supervisor/blacklist_manager.py`
  - 3 crashes in 10 min threshold, 1 hour duration, per-version, 88% reduction repeated crashes

- **Supervisor** → State Tracker
  - File: `k1/l4_runtime/actor_fabric/supervisor/state_tracker.py`
  - FSM transition logging, state validation, metrics emission

#### [ADR-0005e](../../docs/architecture/decisions/0005e-*.md): 0005E Personalities

**Components:**

- **Personalities** → Pure Actor Personalities
  - File: `k1/l4_runtime/actor_fabric/personalities/`
  - Orchestrator, Router, Tool Runner, SessionState (54 pure actors)

- **Personalities** → Capability System
  - File: `k1/l4_runtime/agent_fabric/capability_system.py`
  - 5 capability types (TOOL_CALL, MEMORY_READ, MEMORY_WRITE, MODEL_CALL, NETWORK_ACCESS)

- **Personalities** → Capability Enforcement
  - File: `k1/l4_runtime/agent_fabric/capability_enforcer.py`
  - <1ms runtime checks, hash table lookup, LLM budget enforcement


### Capability Security

#### [ADR-0010b](../../docs/architecture/decisions/0010b-*.md): 0010B Assignment Policy

**Components:**

- **Assignment Policy** → Policy Engine
  - File: `k1/l4_runtime/agent_fabric/capability_policy.py`
  - Policy evaluation, role-based rules, trust level mapping, escalation criteria

- **Assignment Policy** → Agent Capability Mapper
  - File: `k1/l4_runtime/agent_fabric/agent_capability_mapper.py`
  - Per-agent capability assignment, 5 types (TOOL_CALL, MEMORY_READ, MEMORY_WRITE, MODEL_CALL, NETWORK_ACCESS)

#### [ADR-0010c](../../docs/architecture/decisions/0010c-*.md): 0010C Runtime Enforcement

**Components:**

- **Runtime Enforcement** → Capability Enforcer
  - File: `k1/l4_runtime/agent_fabric/capability_enforcer.py`
  - validate_capability, 7-step validation, <0.5ms P95, cache integration, reference monitor

- **Runtime Enforcement** → Validation Cache
  - File: `k1/l4_runtime/agent_fabric/validation_cache.py`
  - In-memory cache, 10s TTL, >80% hit rate, <0.05ms cached checks

- **Runtime Enforcement** → Memory Access Enforcement
  - File: `k1/l4_runtime/session_state/capability_check.py`
  - Memory Manager capability validation, MEMORY resource type, read/write permissions


### Context-Switch Detection

#### [ADR-0055](../../docs/architecture/decisions/0055-*.md): 0055 Main Detection

**Components:**

- **Main Detection** → 3-Stage Detection
  - File: `k1/l4_runtime/intent_switch/context_switch_detector.py`
  - 3-stage flow: (1) intent drift analysis, (2) discourse markers, (3) user confirmation, ContextSwitchDetector class

- **Main Detection** → ContextSwitchDetector Class
  - File: `k1/l4_runtime/intent_switch/context_switch_detector.py`
  - category_hierarchy dict (9 top-level domains), session_history dict (last 3 turns), detect_switch method

- **Main Detection** → Intent Category Analysis
  - File: `k1/l4_runtime/intent_switch/context_switch_detector.py`
  - calculate_category_drift method, recent_intents parameter, new_intent parameter, returns drift_score 0.0-2.0

- **Main Detection** → Category Hierarchy
  - File: `k1/l4_runtime/intent_switch/schemas/category_hierarchy.yml`
  - 9 domains: productivity, information, communication, entertainment, smart_home, commerce, travel, health, system

- **Main Detection** → Drift Score Calculation
  - File: `k1/l4_runtime/intent_switch/drift_calculator.py`
  - 0.0 same subcategory (no drift), 1.0 same category different subcategory (minor), 2.0 different domain (major)

- **Main Detection** → Discourse Marker Detection
  - File: `k1/l4_runtime/intent_switch/discourse_markers.py`
  - Regex patterns: never mind/forget it/scratch that/actually, wait/hold on/first, by the way/also/oh, no/not that/wrong

- **Main Detection** → Confidence Drop Analysis
  - File: `k1/l4_runtime/intent_switch/confidence_analyzer.py`
  - prev_confidence - new_confidence > 0.2 indicates user ambiguity/uncertainty, additional switch signal

- **Main Detection** → SwitchSignal Dataclass
  - File: `k1/l4_runtime/intent_switch/schemas/switch_signal_schema.fbs`
  - session_id, previous_intent, new_intent, drift_score, has_marker bool, confidence_drop bool, detection_method

- **Main Detection** → User Confirmation Flow
  - File: `k1/l2_orchestrator/protocol_monitor/switch_confirmation_protocol.py`
  - MPST: USER_TURN → SWITCH_DETECTED → AWAITING_CONFIRMATION → CONFIRMED/AUTO_TIMEOUT (5s assume continue)

- **Main Detection** → Confirmation Prompts
  - File: `k1/l4_runtime/intent_switch/prompt_generator.py`
  - Explicit marker prompt: "Got it — switching from {prev} to {new}. Start new conversation?", implicit detection variant

- **Main Detection** → History Strategies
  - File: `k1/l4_runtime/session_state/session_manager.py`
  - Option 1: New session (clean context, archive previous), Option 2: Continue (append, maintain context), Option 3: Go back (restore previous)

- **Main Detection** → False Positive Mitigation
  - File: `k1/l4_runtime/intent_switch/false_positive_detector.py`
  - Corrections (same intent parameter change), Clarifications (answering system question), Elaborations (providing missing params)

- **Main Detection** → Edge Cases
  - File: `k1/l4_runtime/intent_switch/edge_case_handlers.py`
  - False positive corrections, rapid topic switching (3 switches warning), multi-turn task preservation (book flight → digression)

- **Main Detection** → Metrics
  - File: `observability/metrics/context_switch_metrics.py`
  - context_switches_detected_total by detection_method, switch_confirmation_choice by choice (new/continue/go_back), false_positive_reports

- **Main Detection** → Target Metrics
  - File: `k1/config/context_switch.yml`
  - Detection accuracy ≥85%, false positive rate ≤5%, user choice distribution 60% new, 30% continue, 10% go_back

- **Main Detection** → Research Foundation
  - File: `docs/research/context_switch_research.md`
  - Schiffrin 1987 discourse markers (67% topic shifts within 2 turns, 45% explicit markers), Schegloff 1992 conversation repair

#### [ADR-0055a](../../docs/architecture/decisions/0055a-*.md): 0055A Intent Drift Rules

**Components:**

- **Intent Drift Rules** → 3-Level Taxonomy
  - File: `k1/l4_runtime/intent_switch/schemas/intent_taxonomy.yml`
  - Level 1: Domain (9 categories), Level 2: Category (mid-level), Level 3: Subcategory (specific intent)

- **Intent Drift Rules** → Domain Categories
  - File: `k1/l4_runtime/intent_switch/schemas/intent_taxonomy.yml`
  - productivity (calendar/email/reminders/tasks), information (weather/news/search/qa), communication (messaging/calls/contacts), entertainment, smart_home, commerce, travel, health, system

- **Intent Drift Rules** → Category Subcategories
  - File: `k1/l4_runtime/intent_switch/schemas/intent_taxonomy.yml`
  - productivity.calendar (create_event/list_events/update_event/delete_event), information.weather (current/forecast/alerts), etc.

- **Intent Drift Rules** → DriftCalculator Class
  - File: `k1/l4_runtime/intent_switch/drift_calculator.py`
  - domain_distance dict (distance matrix 0=same 1=related 2=unrelated), calculate_drift method, is_multi_step_task method

- **Intent Drift Rules** → Drift Score Algorithm
  - File: `k1/l4_runtime/intent_switch/drift_calculator.py`
  - Level 1 domain check (different domain → domain_distance 0-2), Level 2 category check (different category → 1.0), Level 3 subcategory check (multi-step → 0.0 else 1.0)

- **Intent Drift Rules** → Domain Distance Matrix
  - File: `k1/l4_runtime/intent_switch/schemas/domain_distance_matrix.yml`
  - (productivity, productivity)=0, (productivity, information)=2, (productivity, communication)=1, (information, entertainment)=2, etc.

- **Intent Drift Rules** → Multi-Step Task Detection
  - File: `k1/l4_runtime/intent_switch/multi_step_patterns.py`
  - multi_step_patterns dict: calendar.create_event → [calendar.datetime, calendar.location], travel.booking → [travel.datetime, travel.destination], email.send → [email.recipient, email.subject, email...

- **Intent Drift Rules** → Drift Threshold Rules
  - File: `k1/l4_runtime/intent_switch/drift_rules.py`
  - Rule 1 (drift_score ≥2.0: different domains, HIGH confidence 0.95, prompt_user), Rule 2 (drift_score=1.0: CHECK discourse markers, track consecutive_minor_drifts ≥2), Rule 3 (drift_score=0.0: NO sw...

- **Intent Drift Rules** → Confidence Scoring
  - File: `k1/l4_runtime/intent_switch/confidence_scorer.py`
  - 5 factors: drift magnitude 0-0.4 (≥2.0 add 0.4, ≥1.0 add 0.2), discourse marker 0-0.2 (if present add 0.2), intent classifier confidence 0-0.2 (>0.8 add 0.2, <0.5 subtract 0.2), temporal proximity ...

- **Intent Drift Rules** → False Positive Patterns
  - File: `k1/l4_runtime/intent_switch/false_positive_detector.py`
  - is_correction method (check "actually"/"no wait"/"i mean" + same category subcategory parameter change), is_clarification (system question + expected_answer_categories), is_elaboration (prev.requir...

- **Intent Drift Rules** → Performance Targets
  - File: `k1/config/context_switch.yml`
  - Drift calculation <10ms per turn, false positive rate <5%, true positive rate >85%

- **Intent Drift Rules** → Metrics
  - File: `observability/metrics/context_switch_metrics.py`
  - drift_score_distribution histogram (buckets 0.0/0.5/1.0/1.5/2.0), switch_confidence_distribution histogram (0.5-1.0), false_positive_corrections counter by pattern (correction/clarification/elabora...

#### [ADR-0055b](../../docs/architecture/decisions/0055b-*.md): 0055B Switch Prompt

**Components:**

- **Switch Prompt** → Prompt Template System
  - File: `k1/l4_runtime/intent_switch/prompt_generator.py`
  - 3 templates based on signal.confidence: high_confidence ≥0.85, medium_confidence ≥0.65, low_confidence <0.65

- **Switch Prompt** → SwitchPromptGenerator Class
  - File: `k1/l4_runtime/intent_switch/prompt_generator.py`
  - templates dict, generate method (select template, fill task names), humanize_intent method (intent → human-readable name)

- **Switch Prompt** → High-Confidence Template
  - File: `k1/l4_runtime/intent_switch/templates/prompt_templates.yml`
  - "I noticed you switched from __{prev_task}__ to __{new_task}__. Would you like to: 1️⃣ Start new conversation, 2️⃣ Continue with {prev_task}, 3️⃣ Go back to previous topic"

- **Switch Prompt** → Medium-Confidence Template
  - File: `k1/l4_runtime/intent_switch/templates/prompt_templates.yml`
  - "It looks like you're moving from __{prev_task}__ to __{new_task}__. Should I: 1️⃣ Start fresh, 2️⃣ Keep going with {prev_task}, 3️⃣ Return to earlier topic"

- **Switch Prompt** → Low-Confidence Template
  - File: `k1/l4_runtime/intent_switch/templates/prompt_templates.yml`
  - "Just checking — are you still working on __{prev_task}__, or did you want to switch to __{new_task}__? 1️⃣ Switch to new, 2️⃣ Stay with {prev_task}, 3️⃣ Go back"

- **Switch Prompt** → Voice Prompt Variants
  - File: `k1/l4_runtime/intent_switch/voice_prompt_generator.py`
  - Shorter for auditory working memory: "Switching from {prev} to {new}. Say 'new', 'continue', or 'go back'."

- **Switch Prompt** → Voice Recognition
  - File: `k1/l4_runtime/intent_switch/voice_response_parser.py`
  - parse_voice_response: direct matches ("new"/"start new" → "new", "continue"/"keep going" → "continue", "go back"/"back" → "go_back"), fuzzy matches

- **Switch Prompt** → Text Prompt UX
  - File: `k1/l4_runtime/intent_switch/text_prompt_renderer.py`
  - Interactive buttons HTML: btn-primary "🆕 Start New", btn-secondary "▶️ Continue", btn-tertiary "⬅️ Go Back", keyboard shortcuts (1/n → New, 2/c → Continue, 3/b → Go Back, Esc → Cancel=continue)

- **Switch Prompt** → MPST Protocol Integration
  - File: `k1/l2_orchestrator/protocol_monitor/switch_confirmation_protocol.py`
  - State machine: USER_TURN → SWITCH_DETECTED → AWAITING_CONFIRMATION → USER_CHOICE/TIMEOUT → AGENT_TURN

- **Switch Prompt** → SwitchConfirmationProtocol Class
  - File: `k1/l2_orchestrator/protocol_monitor/switch_confirmation_protocol.py`
  - state dict (session_id → State.AWAITING_CONFIRMATION), timers dict, prompt_for_confirmation method (generate, send, start 10s timeout), on_user_choice method (cancel timer, execute choice), on_time...

- **Switch Prompt** → Localization
  - File: `k1/l4_runtime/intent_switch/templates/localized_prompts.yml`
  - Multi-language support: en-US "I noticed you switched", es-ES "Noté que cambiaste", fr-FR "J'ai remarqué que vous êtes passé", localized option text

- **Switch Prompt** → Edge Cases
  - File: `k1/l4_runtime/intent_switch/edge_case_handlers.py`
  - User ignores prompt (10s timeout auto-continue), rapid repeated switches (3 in 1 minute prompt "You've switched topics 3 times. Would you like help?"), low-confidence detection (<0.65 less assertive)

- **Switch Prompt** → Performance Targets
  - File: `k1/config/context_switch.yml`
  - Prompt generation <50ms, voice parsing <30ms, button click → action <100ms

- **Switch Prompt** → Metrics
  - File: `observability/metrics/context_switch_metrics.py`
  - switch_prompts_sent_total by confidence_bucket (high/medium/low), switch_choice_selected by choice (target 60%/30%/10%), switch_timeouts_total (target <10%), switch_prompt_latency_ms histogram (buc...

#### [ADR-0055c](../../docs/architecture/decisions/0055c-*.md): 0055C History Management

**Components:**

- **History Management** → Session Strategy
  - File: `k1/l4_runtime/session_state/session_manager.py`
  - 3 session states: active_sessions dict, archived_sessions dict, session_stack dict for "go back"

- **History Management** → SessionManager Class
  - File: `k1/l4_runtime/session_state/session_manager.py`
  - active_sessions Dict[user_id, Session], archived_sessions Dict[user_id, List[Session]], session_stack Dict[user_id, List[Session]], handle_switch_choice method (choice: new/continue/go_back)

- **History Management** → Choice 1: New
  - File: `k1/l4_runtime/session_state/session_manager.py`
  - start_new_session method: (1) archive current (status=ARCHIVED, archived_at, archive_reason="user_context_switch"), (2) push to session_stack for go back, (3) create new session (empty conversation...

- **History Management** → New Session Preservation
  - File: `k1/l4_runtime/session_state/session_manager.py`
  - Preserved: user preferences (persona, style), privacy band, authentication state. NOT preserved: conversation history, pending tasks, SessionState (beliefs, scoreboard)

- **History Management** → Session Archiving
  - File: `k1/l4_runtime/session_state/session_archiver.py`
  - Archive data: full conversation transcript, SessionState snapshot, task completion status, metadata (timestamps, intents)

- **History Management** → Choice 2: Continue
  - File: `k1/l4_runtime/session_state/session_manager.py`
  - continue_with_context method: (1) mark topic boundary in history (Turn role="system" type="topic_boundary" text="[Topic shift: X → Y]"), (2) update session metadata (topic_switches++, current_inten...

- **History Management** → Context Pollution Mitigation
  - File: `k1/l4_runtime/session_state/context_window_manager.py`
  - get_context_window method: find last topic_boundary in history, include only turns after last_boundary_idx, limit to max_turns=10

- **History Management** → Topic Boundary Marker
  - File: `k1/l4_runtime/session_state/schemas/turn_schema.fbs`
  - Turn role="system", type="topic_boundary", text="[Topic shift: {prev_category} → {new_category}]", metadata {drift_score, previous_intent, new_intent}

- **History Management** → Choice 3: Go Back
  - File: `k1/l4_runtime/session_state/session_manager.py`
  - restore_previous_session method: (1) get current, (2) pop previous from session_stack (if empty warning log fallback continue), (3) archive current (status=ABANDONED, archive_reason="user_go_back")...

- **History Management** → Go Back Limitations
  - File: `k1/l4_runtime/session_state/session_manager.py`
  - Stack depth max 5 sessions (prevent infinite nesting), timeout >1 hour old cannot restore, stateful tasks cannot undo partially executed actions (e.g., email half-sent)

- **History Management** → SessionState Coordination
  - File: `k1/bridge_k0/session_state_bridge.py`
  - new: clear_session_sections beliefs/scoreboard/control preserve persona, continue: add_metadata topic_boundary timestamp/prev_topic/new_topic, go_back: rollback_to_snapshot previous_snapshot_id

- **History Management** → Privacy Band Inheritance
  - File: `k1/l4_runtime/session_state/privacy_band_manager.py`
  - New session inherits privacy_band (GREEN→GREEN, AMBER→AMBER, RED→RED), if RED band warning log "red_band_session_switch"

- **History Management** → Archived Retention
  - File: `k1/l4_runtime/session_state/retention_policy.py`
  - ADR-0010 privacy band retention policies: GREEN 90 days, AMBER 30 days, RED 7 days then shred

- **History Management** → K0 Integration
  - File: `k1/bridge_k0/session_state_bridge.py`
  - commit_session (on archive), init_session (on new), rollback_session (on go_back), clear_session_sections (on new choice), rollback_to_snapshot (on go_back), add_metadata (on continue choice)

- **History Management** → Performance Targets
  - File: `k1/config/context_switch.yml`
  - Session archiving <100ms, restore latency <500ms, K0 coordination <200ms

- **History Management** → Metrics
  - File: `observability/metrics/context_switch_metrics.py`
  - session_switch_actions by action (new/continue/go_back), session_stack_depth histogram (buckets 1-5), archived_sessions_total by reason (context_switch/abandoned), session_restore_latency_ms histog...


### Cursor-Based Pagination

#### [ADR-0023](../../docs/architecture/decisions/0023-*.md): 0023 Pagination Core

**Components:**

- **Pagination Core** → Cursor Token Design
  - File: `k1/l4_ingress/api_gateway/pagination/cursor_encoder.py`
  - Opaque Base64 token, encodes turn_id + timestamp_ms + session_id, stateless, <256 bytes

- **Pagination Core** → O(1) Index Seek
  - File: `k1/l4_ingress/api_gateway/pagination/query_builder.py`
  - WHERE turn_id > :cursor, (session_id, turn_id) index, O(1) seek, <50ms P95 query

- **Pagination Core** → Consistent Results
  - File: `k1/l4_ingress/api_gateway/pagination/query_builder.py`
  - No skipped/duplicate records, cursor captures exact position, vs offset shifts with concurrent inserts

- **Pagination Core** → Bidirectional Support
  - File: `k1/l4_ingress/api_gateway/pagination/query_builder.py`
  - Forward (oldest → newest) and backward (newest → oldest), direction flag in cursor

- **Pagination Core** → REST API Endpoint
  - File: `k1/l4_ingress/api_gateway/history_api.py`
  - GET /k1/history/turns?cursor={cursor}&limit=20, JSON response, next_cursor + prev_cursor

#### [ADR-0023a](../../docs/architecture/decisions/0023a-*.md): 0023A Cursor Encoding

**Components:**

- **Cursor Encoding** → HMAC Signature
  - File: `k1/l4_ingress/api_gateway/pagination/cursor_encoder.py`
  - HMAC SHA-256 with secret key, prevent tampering, constant-time comparison, <500μs compute

- **Cursor Encoding** → Base64 Encoding
  - File: `k1/l4_ingress/api_gateway/pagination/cursor_encoder.py`
  - URL-safe Base64, opaque to clients, <1ms encode/decode, compact format

- **Cursor Encoding** → Cursor Versioning
  - File: `k1/l4_ingress/api_gateway/pagination/cursor_encoder.py`
  - Version field (v1, v2, etc.), support format evolution, backward compatibility

- **Cursor Encoding** → TurnCursor Data Class
  - File: `k1/l4_ingress/api_gateway/pagination/cursor.py`
  - turn_id, timestamp_ms, session_id, version, to_dict/from_dict methods, JSON serialization

#### [ADR-0023b](../../docs/architecture/decisions/0023b-*.md): 0023B REST API

**Components:**

- **REST API** → Pagination Metadata
  - File: `k1/l4_ingress/api_gateway/history_api.py`
  - has_more (boolean), next_cursor, prev_cursor, <1ms compute, check if result count = limit

- **REST API** → Total Count (Optional)
  - File: `k1/l4_ingress/api_gateway/history_api.py`
  - Separate COUNT query (expensive), <200ms for large sessions, 5-minute cache TTL

- **REST API** → Error Handling
  - File: `k1/l4_ingress/api_gateway/history_api.py`
  - 400 Bad Request (invalid cursor), 404 Not Found (expired cursor), always JSON errors

- **REST API** → Rate Limiting
  - File: `k1/l4_ingress/api_gateway/rate_limiter.py`
  - 100 requests/min per session, cursor-based (can't bypass), token bucket algorithm

#### [ADR-0023c](../../docs/architecture/decisions/0023c-*.md): 0023C K0 WAL Query

**Components:**

- **K0 WAL Query** → Query Optimization
  - File: `k1/l4_ingress/api_gateway/pagination/wal_query.py`
  - WHERE session_id = ? AND turn_id > ?, LIMIT 21 (detect has_more), prepared statement

- **K0 WAL Query** → Warm Tier Performance
  - File: `k1/l4_ingress/api_gateway/pagination/wal_query.py`
  - <50ms P95 (L2 SSD), 20 turns/page, efficient seek, SQLite FTS5 support

- **K0 WAL Query** → Cold Tier Fallback
  - File: `k1/l4_ingress/api_gateway/pagination/wal_query.py`
  - Query S3 if >30 days old, <500ms P95, reconstruct from cold tier, cache in warm tier

- **K0 WAL Query** → SQLite Index
  - File: `k0/wal_storage/indexes.sql`
  - CREATE INDEX idx_session_turn ON turns (session_id, turn_id), <50ms P95 indexed query


### Embodied Awareness

#### [ADR-0085](../../docs/architecture/decisions/0085-*.md): 0085 Core Architecture

**Components:**

- **Core Architecture** → Multi-Device Presence
  - File: `k1/l1_input/streams/operators/device_presence.py`
  - 7 presence mechanisms (device presence, location awareness, BLE proximity, active session, motion sensors, power state, cross-device sharing), K0 P07 CRDT sync integration (ADR-0050), SessionState ...

- **SessionState Extension** → Multimodal Context
  - File: `k1/l4_runtime/session_state/multimodal_context.py`
  - Section 5 extension, active_device (most recently active device_id), all_devices (List[DevicePresenceState]), device_switch_timestamp, current_location, location_history (last 10), coarse_location ...


### Enhanced HITL Protocols

#### [ADR-0052](../../docs/architecture/decisions/0052-*.md): 0052 Performance

**Components:**

- **Performance** → Step-by-Step Checkpoint
  - File: `k1/l4_runtime/session_state/workflow_state.py`
  - <10ms P95 to K0 WAL (state persistence after each step), FlatBuffers serialization

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

- **Step-by-Step Approval** → K0 WAL Checkpoint
  - File: `k1/l4_runtime/session_state/workflow_checkpoint.py`
  - Persist WorkflowState to K0 WAL <10ms P95 (ADR-0007d), 24-hour retention for ephemeral workflows

- **Step-by-Step Approval** → WorkflowState FSM
  - File: `k1/l4_runtime/session_state/workflow_state.py`
  - 6-state FSM: RUNNING, PAUSED, COMPLETED, ABORTED, FAILED, TERMINATED

- **Step-by-Step Approval** → WorkflowStatus Enum
  - File: `k1/l4_runtime/session_state/workflow_state.py`
  - 5 states: RUNNING (active), PAUSED (user paused), COMPLETED (success), ABORTED (cancelled), FAILED (error)

- **Step-by-Step Approval** → StepHistoryItem
  - File: `k1/l4_runtime/session_state/workflow_state.py`
  - Tracking: step_id, description, status (PENDING/APPROVED/EXECUTED/FAILED/ROLLED_BACK), timestamps, duration

- **Step-by-Step Approval** → Checkpoint Performance
  - File: `k1/l4_runtime/session_state/workflow_checkpoint.py`
  - <10ms P95 state persistence, <2KB per workflow, <500ms rollback per step

#### [ADR-0052b](../../docs/architecture/decisions/0052b-*.md): 0052B RED Band Approval

**Components:**

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

- **Nested Clarifications** → Clarification History Stack
  - File: `k1/l4_runtime/session_state/clarification_history.py`
  - LIFO stack (deque maxlen=3), max depth 3 (prevent infinite loops), push/pop operations <50ms P95

- **Nested Clarifications** → QUD Stack Integration
  - File: `k1/l4_runtime/session_state/scoreboard.py`
  - Questions Under Discussion stack (ADR-0017b), clarification history persisted in SessionState Scoreboard

- **Nested Clarifications** → ClarificationHistory
  - File: `k1/l4_runtime/session_state/clarification_history.py`
  - Data structure: deque maxlen=3, current_depth, root_question, push/pop/peek methods, to_summary()

- **Nested Clarifications** → ClarificationItem
  - File: `k1/l4_runtime/session_state/clarification_history.py`
  - Schema: clarification_id, question, answer, timestamp, depth (1-3), clarification_type (512 bytes per item)

- **Nested Clarifications** → Context Preservation
  - File: `k1/l4_runtime/session_state/clarification_history.py`
  - Parent clarification context retained when nesting deeper, history stack preserves all levels

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

#### [ADR-0012d](../../docs/architecture/decisions/0012d-*.md): 0012D Layer 4 Schemas

**Components:**

- **Layer 4 Schemas** → API Gateway
  - File: `k1/l4_ingress/api_gateway/schemas/`
  - HTTPRequest HREQ, HTTPResponse HRSP, WebSocketMessage WSMG, SSEEvent SSEV

- **Layer 4 Schemas** → Voice Pipeline
  - File: `k1/l4_ingress/voice_pipeline/schemas/`
  - AudioFrame AUDF, ASRResult ASRR, TTSRequest TTSR, TTSAudioChunk TTSA

- **Layer 4 Schemas** → Barge-In
  - File: `k1/l4_ingress/barge_in/schemas/`
  - BargeInEvent BGIN, BargeInResponse BGRS, VADState VADS

- **Layer 4 Schemas** → WebSocket Protocol
  - File: `k1/l4_ingress/websocket/schemas/`
  - WSConnectionInit WSIN, WSTurnMessage WSTM, WSHeartbeat WSHB


### FlatBuffers SessionState Serialization

#### [ADR-0019](../../docs/architecture/decisions/0019-*.md): 0019 Serialization Core

**Components:**

- **Serialization Core** → Full Serialization
  - File: `k1/l4_runtime/session_state/serialization/full_serializer.py`
  - Serialize entire SessionState (48KB median), <1ms P95 (64KB), session start snapshots

- **Serialization Core** → Delta Serialization
  - File: `k1/l4_runtime/session_state/serialization/delta_serializer.py`
  - Serialize only changed sections, <0.5ms P95 (12KB median), 60-80% size reduction

- **Serialization Core** → Zero-Copy Deserialization
  - File: `k1/l4_runtime/session_state/serialization/zero_copy_deserializer.py`
  - Direct buffer access, <0.1ms P95 field access, 100x reads per write

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

#### [ADR-0019b](../../docs/architecture/decisions/0019b-*.md): 0019B Serialization Core

**Components:**

- **Serialization Core** → Delta Serialization
  - File: `k1/l4_runtime/session_state/serialization/delta_serializer.py`
  - Serialize only changed sections, <0.5ms P95 (12KB median), 60-80% size reduction

- **Delta Pipeline** → Dirty Flag Tracking
  - File: `k1/l4_runtime/session_state/sections/base_section.py`
  - Boolean flag per section, mutation-driven tracking, mark_dirty on mutations

- **Delta Pipeline** → Change Detection
  - File: `k1/l4_runtime/session_state/serialization/delta_serializer.py`
  - Detect changed sections (check dirty flags), <100μs P95, O(6) dirty flag checks

- **Delta Pipeline** → Selective Serialization
  - File: `k1/l4_runtime/session_state/serialization/delta_serializer.py`
  - Only serialize sections with dirty=true, <500μs per section, typical 1-2 sections

- **Delta Pipeline** → Dirty Flag Reset
  - File: `k1/l4_runtime/session_state/sections/base_section.py`
  - Clear dirty flags after checkpoint, session_state.clear_dirty_flags(), prevent re-serialization

- **Delta Pipeline** → FlatBuffers Builder
  - File: `k1/l4_runtime/session_state/serialization/delta_serializer.py`
  - Reuse FlatBuffers builder, 16KB initial buffer, avoid reallocation overhead

#### [ADR-0019c](../../docs/architecture/decisions/0019c-*.md): 0019C K0 WAL Integration

**Components:**

- **K0 WAL Integration** → Checkpoint Interval
  - File: `k1/l4_runtime/session_state/persistence/k0_checkpointer.py`
  - 5 minutes (300s), configurable via k1.yml, durability vs performance balance

- **K0 WAL Integration** → K0 Checkpointer
  - File: `k1/l4_runtime/session_state/persistence/k0_checkpointer.py`
  - Background asyncio task, checkpoint all active sessions, <1s for 100 sessions

- **K0 WAL Integration** → Sequence Numbers
  - File: `k1/l4_runtime/session_state/model.py`
  - Monotonic sequence per session (session.meta.sequence_number), detect gaps, recovery ordering

- **K0 WAL Integration** → Recovery Logic
  - File: `k1/l4_runtime/session_state/persistence/k0_wal_recovery.py`
  - Replay deltas from K0 WAL, session resume on reconnect, <500ms recovery for 12 deltas

#### [ADR-0019d](../../docs/architecture/decisions/0019d-*.md): 0019D Serialization Core

**Components:**

- **Serialization Core** → Zero-Copy Deserialization
  - File: `k1/l4_runtime/session_state/serialization/zero_copy_deserializer.py`
  - Direct buffer access, <0.1ms P95 field access, 100x reads per write

- **Zero-Copy Optimization** → Direct Buffer Access
  - File: `k1/l4_runtime/session_state/serialization/zero_copy_deserializer.py`
  - Memory-map buffers, vtable offsets, pointer arithmetic, 150× faster vs JSON

- **Zero-Copy Optimization** → Lazy Section Proxies
  - File: `k1/l4_runtime/session_state/sections/lazy_section.py`
  - LazySection class with __getattr__, defer deserialization until accessed, <500μs first access

- **Zero-Copy Optimization** → Buffer Lifecycle
  - File: `k1/l4_runtime/session_state/model.py`
  - Keep FlatBuffers buffer alive via _fb_buffer reference, prevent garbage collection, dangling pointer prevention

- **Zero-Copy Optimization** → Field Access Caching
  - File: `k1/l4_runtime/session_state/sections/lazy_section.py`
  - Cache expensive field accesses, _deserialized cached object, <1μs subsequent accesses

- **Zero-Copy Optimization** → String Interning
  - File: `k1/l4_runtime/session_state/serialization/zero_copy_deserializer.py`
  - sys.intern() for repeated strings, 10-15% memory reduction, common field names cached

- **Zero-Copy Optimization** → Buffer Reuse
  - File: `k1/l4_runtime/session_state/serialization/delta_serializer.py`
  - Reuse FlatBuffers builder, builder.Clear(), avoid reallocation, 1.4× speedup


### HITL Schema Integration

#### [ADR-0052e](../../docs/architecture/decisions/0052e-*.md): 0052E Layer 4 Communication

**Components:**

- **Layer 4 Communication** → Clarification Schema
  - File: `k1/contracts/flatbuffers/layer4_ingress/clarification.fbs`
  - Clarification request/response, timeout handling, escalation to RED band, WSTurnMessageType extension

- **Layer 4 Communication** → Step-by-Step Schema
  - File: `k1/contracts/flatbuffers/layer4_ingress/step_by_step_request.fbs`
  - Step-by-step guidance requests, user preferences, progressive disclosure, HITL_REQUEST message type

- **Layer 4 Communication** → RED Band Schema
  - File: `k1/contracts/flatbuffers/layer4_ingress/red_band_request.fbs`
  - RED band approval requests, arbiter integration, 7-year audit retention, HITL_RESPONSE message type

- **Protocol Extension** → WSTurnMessage Extension
  - File: `k1/contracts/flatbuffers/layer4_ingress/ws_turn_message.fbs`
  - 2 new message types (HITL_REQUEST, HITL_RESPONSE), extends WSTurnMessageType enum (82 total vs 80 original), namespace k1.websocket.hitl


### JWT Authentication

#### [ADR-0037](../../docs/architecture/decisions/0037-*.md): 0037 Horizontal Scaling

**Components:**

- **Horizontal Scaling** → Stateless Validation
  - File: `k1/l4_ingress/api_gateway/auth/stateless_validator.py`
  - Any server can validate JWT with public key, No sticky sessions required, No session replication, 100% stateless routing

- **Horizontal Scaling** → Public Key Distribution
  - File: `k1/l4_ingress/api_gateway/auth/pubkey_distributor.py`
  - Public key distributed to all API Gateway instances, 90-day key rotation, Seamless key rollover (old + new keys valid during transition)

- **OAuth 2.0 Compatibility** → Bearer Token Protocol
  - File: `k1/l4_ingress/api_gateway/auth/oauth2.py`
  - RFC 6749 compliant (OAuth 2.0 Authorization Framework), Bearer token in Authorization header, 100% third-party integration (OpenID Connect, OAuth providers)

- **Integration** → Token Revocation
  - File: `k1/l4_ingress/api_gateway/auth/revocation.py`
  - Redis blacklist with TTL = token expiry, <10ms blacklist check, 100% revocation enforcement, Immediate revocation on logout

#### [ADR-0037a](../../docs/architecture/decisions/0037a-*.md): 0037A Token Generation

**Components:**

- **Token Generation** → RS256 Signing
  - File: `k1/l4_ingress/api_gateway/auth/token_signer.py`
  - RSA Signature with SHA-256, 2048-bit RSA key pair, Private key in KMS (AWS KMS/Azure Key Vault), Public key distributed to API Gateway

- **Token Generation** → Token Lifecycle
  - File: `k1/l4_ingress/api_gateway/auth/token_manager.py`
  - Access token (1h expiry, short-lived), Refresh token (7d expiry, long-lived), Format: header.payload.signature (Base64URL encoded)

- **Token Generation** → Claims Structure
  - File: `k1/l4_ingress/api_gateway/auth/claims_builder.py`
  - Standard claims (sub/iat/exp/iss/aud/jti), Custom claims (space_id/roles/privacy_band/capabilities), No sensitive data (no PII/PHI)

- **Token Generation** → Performance
  - File: `k1/l4_ingress/api_gateway/auth/token_signer.py`
  - <50ms access token signing, <50ms refresh token signing, <5ms serialization (JSON to Base64URL)

- **Token Generation** → Production Metrics
  - File: `k1/l4_ingress/api_gateway/auth/metrics.py`
  - 500K access tokens issued (6 months), 50K refresh tokens issued, 30ms avg signing latency

#### [ADR-0037b](../../docs/architecture/decisions/0037b-*.md): 0037B Token Validation

**Components:**

- **Token Validation** → Signature Verification
  - File: `k1/l4_ingress/api_gateway/auth/token_validator.py`
  - RS256 with public key (<1ms), Reject forged tokens (invalid signature), Constant-time execution (prevent timing attacks)

- **Token Validation** → Expiry Check
  - File: `k1/l4_ingress/api_gateway/auth/token_validator.py`
  - Compare exp claim with current time (<0.1ms), Reject expired tokens (exp < now)

- **Token Validation** → Claims Extraction
  - File: `k1/l4_ingress/api_gateway/auth/token_validator.py`
  - Parse JWT payload (<0.2ms), Extract user_id/space_id/roles/privacy_band/capabilities

- **Token Validation** → Blacklist Check
  - File: `k1/l4_ingress/api_gateway/auth/blacklist.py`
  - Redis lookup for revoked tokens (<1ms cached), Reject revoked tokens (jti in blacklist), Immediate revocation support

- **Token Validation** → Performance
  - File: `k1/l4_ingress/api_gateway/auth/token_validator.py`
  - <2ms total validation (P95), 2.5× faster than 5ms Redis session lookup, 50M validations (6 months), 1.5ms avg latency

- **Token Validation** → Error Handling
  - File: `k1/l4_ingress/api_gateway/auth/error_handler.py`
  - 401 Unauthorized (expired/forged/revoked), 403 Forbidden (valid but insufficient permissions), Structured error messages for debugging

#### [ADR-0037c](../../docs/architecture/decisions/0037c-*.md): 0037C Refresh Token Flow

**Components:**

- **Refresh Token Flow** → Single-Use Security
  - File: `k1/l4_ingress/api_gateway/auth/refresh_manager.py`
  - Rotate refresh token on each use, Stored in Redis (7-day TTL), Deleted on logout, Detect token reuse (stolen token scenario)

- **Refresh Token Flow** → Refresh Endpoint
  - File: `k1/l4_ingress/api_gateway/auth/refresh_endpoint.py`
  - POST /auth/refresh with refresh_token, Validate (RS256 + expiry + not revoked), Issue new access + refresh tokens, Delete old refresh token from Redis

- **Refresh Token Flow** → Performance
  - File: `k1/l4_ingress/api_gateway/auth/refresh_manager.py`
  - <100ms refresh endpoint, <50ms token signing (2 tokens), <5ms Redis delete + insert

- **Refresh Token Flow** → Security
  - File: `k1/l4_ingress/api_gateway/auth/security_detector.py`
  - Revoke entire refresh token family on suspicious activity, Rate limit 10 requests/minute per user, 5K reuse detected (10%) in 6 months

- **Refresh Token Flow** → Production Metrics
  - File: `k1/l4_ingress/api_gateway/auth/metrics.py`
  - 50K refresh token issuances (6 months), 45K successful refreshes (90% success rate), 45ms avg latency

#### [ADR-0037d](../../docs/architecture/decisions/0037d-*.md): 0037D Session Binding

**Components:**

- **Session Binding** → Space Isolation
  - File: `k1/l4_ingress/api_gateway/auth/space_isolator.py`
  - Every user assigned to one space, Agents inherit space_id from session, API endpoints validate space_id matches session

- **Authorization** → RBAC
  - File: `k1/l4_ingress/api_gateway/auth/rbac_enforcer.py`
  - Roles (admin/operator/user), Admin (full system access), Operator (session/agent management), User (basic operations)

- **Authorization** → Privacy Band Enforcement
  - File: `k1/l4_ingress/api_gateway/auth/privacy_band_enforcer.py`
  - Hierarchy RED > AMBER > GREEN, AMBER users can't access RED, GREEN users can't access AMBER/RED, Ties to ADR-0032 (Egress Control)

- **Authorization** → Capability-Based Permissions
  - File: `k1/l4_ingress/api_gateway/auth/capability_enforcer.py`
  - TOOL_CALL (execute tool calls), AGENT_HIRE (hire new agents), MCP_CALL (call MCP servers), SESSION_ADMIN (modify session state), Checked per operation

- **Authorization** → Performance
  - File: `k1/l4_ingress/api_gateway/auth/authorization.py`
  - <1ms authorization checks (in-memory), <5ms SessionState population, No external calls for authorization (all in JWT)


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

#### [ADR-0001f](../../docs/architecture/decisions/0001f-*.md): 0001F State Management

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

#### [ADR-0001f](../../docs/architecture/decisions/0001f-*.md): 0001F State Management

**Components:**

- **State Management** → SessionState Model
  - File: `k1/l4_runtime/session_state/model.py`
  - 6 sections (beliefs, scoreboard, control, persona, multimodal, meta), 64KB soft limit

- **State Management** → State Boundaries
  - File: `k1/l4_runtime/session_state/boundaries.py`
  - K1 ephemeral (working memory), K0 durable (long-term), batch flush (250ms)

- **State Management** → Recovery
  - File: `k1/l4_runtime/session_state/recovery.py`
  - WAL replay, <5s recovery, checkpoint snapshots (every 10 turns)

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

#### [ADR-0048](../../docs/architecture/decisions/0048-*.md): 0048 Bus Architecture

**Components:**

- **Bus Architecture** → Actor Model Integration
  - File: `k1/l4_runtime/actor_fabric/event_bus_adapter.py`
  - Mailbox-based delivery, MPSC queue push, supervision tree resilience

- **Bus Architecture** → Direct Messaging
  - File: `k1/l4_runtime/actor_fabric/mailbox/direct_send.py`
  - 1-to-1 agent proposals, mailbox enqueue, <1ms latency

- **Event Categories** → Agent Lifecycle Events
  - File: `k1/l4_runtime/agent_lifecycle/lifecycle_topics.py`
  - k1.agent.* (PENDING, WARMING, ACTIVE, IDLE, DRAINING, TERMINATED)

- **Event Categories** → Barge-In Events
  - File: `k1/l4_ingress/voice_pipeline/barge_in_topics.py`
  - k1.barge_in.* (user interrupt detected), VAD signals

- **Event Categories** → Memory Cache Events
  - File: `k1/l4_runtime/session_state/cache_topics.py`
  - k1.memory.* (eviction, warming), session state operations

- **K0/K1 Separation** → K1 Ephemeral Only
  - File: `docs/architecture/k0_k1_event_separation.md`
  - K1 events ephemeral (no persistence), K0 SSE durable (config, receipts, learning)


### KV Cache Optimization

#### [ADR-0076](../../docs/architecture/decisions/0076-*.md): 0076 Compression Tier

**Components:**

- **Compression Tier** → KVCacheEntry Compression
  - File: `k1/l4_runtime/kv_cache/compression.py`
  - ZSTD primary (25-35% ratio), LZ4 fallback, 1KB threshold, XXHASH64 validation, <1ms P95 compression, M3 milestone

- **Compression Tier** → Decompress-on-Access
  - File: `k1/l4_runtime/kv_cache/decompression.py`
  - Lazy decompression, decompressed cache LRU, <5ms P95 decompression, checksum validation

- **Eviction Tier** → Priority-Aware LRU
  - File: `k1/l4_runtime/kv_cache/eviction.py`
  - 3 tiers: HOT (1.0) WARM (0.7) COLD (0.3), access frequency + recency + thermal adjustment, 110MB soft limit 128MB hard limit

- **Eviction Tier** → KVCacheManager
  - File: `k1/l4_runtime/kv_cache/manager.py`
  - Entry priority calculation, eviction budget enforcement, thermal state integration ADR-0026, 75%+ target hit rate


### Message Queue & Coalescing

#### [ADR-0053](../../docs/architecture/decisions/0053-*.md): 0053 Main

**Components:**

- **Main** → Message Queue Architecture
  - File: `k1/l4_ingress/websocket/message_queue.py`
  - FIFO per-session queues, bounded capacity 10 messages, priority lanes (RED bypass), cancellation tokens

- **Main** → Coalescing Engine
  - File: `k1/l4_ingress/websocket/coalescing_engine.py`
  - 2-second window, 5-message limit, coalesce text fragments, join with space delimiter

- **Main** → Rate Limiter
  - File: `k1/l4_ingress/websocket/rate_limiter.py`
  - Token Bucket algorithm, 5 msg/sec baseline, 3-message burst, HTTP 429 rejection

- **Main** → Cancellation Protocol
  - File: `k1/l4_ingress/websocket/cancellation_manager.py`
  - P95 ≤120ms latency, 4-stage cascade (signal/abort/cleanup/rollback), safety guarantees

- **Main** → Queue Properties
  - File: `k1/l4_ingress/websocket/message_queue.py`
  - Per-session isolation, bounded capacity (prevent exhaustion), priority lanes, cancellation tokens per message

- **Main** → Coalesce Window
  - File: `k1/config/message_queue.yml`
  - 2-second window (aligns with turn-taking pauses), resets on each new message arrival

- **Main** → Message Limit
  - File: `k1/config/message_queue.yml`
  - 5-message count limit (force processing), prevents unbounded buffering, matches fast typing

- **Main** → Coalescing Rules
  - File: `k1/l4_ingress/websocket/coalescing_engine.py`
  - Text only (voice handled by ASR), preserve message order, RED band bypass, context-switch trigger immediate

- **Main** → Baseline Rate
  - File: `k1/config/rate_limit.yml`
  - 5 messages/second (covers 60 WPM typing), prevents accidental DDoS from UI bugs

- **Main** → Burst Allowance
  - File: `k1/config/rate_limit.yml`
  - 3 messages above baseline, burst tokens replenish at 1 token/second, 600ms full recovery

- **Main** → Rate Limit Actions
  - File: `k1/l4_ingress/websocket/rate_limiter.py`
  - 80% capacity warning log, 100% capacity HTTP 429 rejection with retry_after_ms, Retry-After header

- **Main** → Cancellation Triggers
  - File: `k1/l4_ingress/websocket/cancellation_manager.py`
  - New message arrival, explicit stop button, voice barge-in (ADR-0057c), context-switch detection (ADR-0055)

- **Main** → Cancellation Propagation
  - File: `k1/l4_ingress/websocket/cancellation_manager.py`
  - WebSocket → queue → orchestrator → planner → model hub → streaming → tools → K0, atomic flag checks

- **Main** → Cancellation Latency Budget
  - File: `k1/l4_ingress/websocket/cancellation_manager.py`
  - 120ms total: 20ms signal, 30ms abort, 40ms cleanup, 20ms rollback, 10ms ack, 250ms hard timeout

- **Main** → Integration Points
  - File: `k1/l4_ingress/websocket/websocket_queue_integration.py`
  - WebSocket ingress (ADR-0015), Intent classifier (ADR-0021), Backpressure (ADR-0039), Turn boundary (ADR-0054), Barge-in (ADR-0057c)

- **Main** → Research Foundation
  - File: `docs/research/message_queue_research.md`
  - Nagle's Algorithm (TCP 1984), SEDA (2001), Token Bucket, Cooperative Cancellation (Go/Rust), Turn-taking pauses (2-3s)

#### [ADR-0053a](../../docs/architecture/decisions/0053a-*.md): 0053A Coalesce Window

**Components:**

- **Coalesce Window** → Time-Based Threshold
  - File: `k1/l4_ingress/websocket/coalescing_engine.py`
  - 2-second window aligns with natural turn-taking pauses (2-3s in conversation), reset timer on each message

- **Coalesce Window** → Count-Based Threshold
  - File: `k1/l4_ingress/websocket/coalescing_engine.py`
  - 5-message limit prevents unbounded buffering, average utterance 5-10 words, memory safety <5KB per session

- **Coalesce Window** → Bypass Conditions
  - File: `k1/l4_ingress/websocket/coalescing_engine.py`
  - RED band (safety-critical immediate), explicit submit (Enter key), context switch (topic change), voice input (ASR coalesced)

- **Coalesce Window** → Coalescing Algorithm
  - File: `k1/l4_ingress/websocket/coalescing_engine.py`
  - FIFO queue, timer reset on enqueue, flush on timer expiry or count limit, join messages with space

- **Coalesce Window** → CoalesceTimer Class
  - File: `k1/l4_ingress/websocket/coalesce_timer.py`
  - window_ms, timer handle, messages list, on_message (reset timer), process (flush coalesced)

- **Coalesce Window** → MessageCoalescer Class
  - File: `k1/l4_ingress/websocket/message_coalescer.py`
  - window_ms=2000, max_messages=5, queue list, timer, enqueue (bypass checks), flush (join and emit metrics)

- **Coalesce Window** → Edge Case Handling
  - File: `k1/l4_ingress/websocket/message_coalescer.py`
  - Empty messages rejected at ingress, single message flush after timer, rapid context switches separate processing, cancellation clears queue

- **Coalesce Window** → Logging
  - File: `k1/l4_ingress/websocket/coalescing_engine.py`
  - message_coalesced (session_id, message_count, window_duration_ms, trace_id), coalesce_bypass (reason), coalesce_queue_cleared (cancellation)

- **Coalesce Window** → Rollout Strategy
  - File: `docs/rollout/message_queue_rollout.md`
  - Week 1 internal testing, Week 2 5% canary, Week 3-4 gradual to 100% (72h soak each stage)

- **Coalesce Window** → Future Work
  - File: `docs/roadmap/coalescing_enhancements.md`
  - Adaptive windows per user typing speed, context-aware coalescing (longer for complex), predictive flush (ML model)

#### [ADR-0053b](../../docs/architecture/decisions/0053b-*.md): 0053B Rate Limits

**Components:**

- **Rate Limits** → Token Bucket Algorithm
  - File: `k1/l4_ingress/websocket/rate_limiter.py`
  - Chosen over leaky bucket/fixed window/sliding log, allows bursts, low memory (2 ints/session), industry-proven (AWS/Google)

- **Rate Limits** → Baseline Rate
  - File: `k1/config/rate_limit.yml`
  - 5 messages/second covers fast typing (60 WPM = 1 word/sec), 2× safety margin, prevents bots (100+ msg/sec)

- **Rate Limits** → Burst Allowance
  - File: `k1/config/rate_limit.yml`
  - 3 messages above baseline, replenish 1 token every 200ms, full burst recovery 600ms, handle rapid corrections

- **Rate Limits** → Token Bucket State
  - File: `k1/l4_ingress/websocket/rate_limiter.py`
  - Per-session state: tokens (current count), last_update (timestamp), baseline_rate (5.0), burst_capacity (3)

- **Rate Limits** → TokenBucketRateLimiter Class
  - File: `k1/l4_ingress/websocket/token_bucket_limiter.py`
  - rate=5.0, burst=3, sessions dict, allow_message (returns allowed, retry_after_ms), token refill logic

- **Rate Limits** → Bypass Conditions
  - File: `k1/l4_ingress/websocket/rate_limiter.py`
  - RED band messages (up to 10 msg/sec hard limit), system-initiated messages, barge-in cancellations (UX-critical)

- **Rate Limits** → Rate Limit Actions
  - File: `k1/l4_ingress/websocket/rate_limiter.py`
  - 100% capacity: HTTP 429 rejection, 80% capacity: warning log + metric, rate_limit_rejections_total counter

- **Rate Limits** → HTTP 429 Response
  - File: `k1/l4_ingress/websocket/rate_limit_response.py`
  - Retry-After header (seconds), X-RateLimit-* headers (limit/remaining/reset), JSON body (error, retry_after_ms, rate_limit details)

- **Rate Limits** → Integration Points
  - File: `k1/l4_ingress/websocket/websocket_rate_limit_integration.py`
  - WebSocket ingress (earliest check), Backpressure cascade (independent operation), Privacy bands (RED bypass check), Observability (metrics)

- **Rate Limits** → Session Cleanup
  - File: `k1/l4_ingress/websocket/rate_limiter.py`
  - Idle threshold 300s (5 minutes), cleanup_idle_sessions method, prevent memory leak (>10,000 sessions alert)

- **Rate Limits** → DDoS Protection
  - File: `k1/l4_ingress/websocket/rate_limiter.py`
  - Blocks bots (100+ msg/sec), fair resource allocation (no session monopoly), 99.9% reduction in attack effectiveness

- **Rate Limits** → Accidental Abuse Prevention
  - File: `k1/l4_ingress/websocket/rate_limiter.py`
  - UI bug message storms auto-throttled, infinite retry loops broken, prevents cascading failures

- **Rate Limits** → Logging
  - File: `k1/l4_ingress/websocket/rate_limiter.py`
  - rate_limit_exceeded (session_id, retry_after_ms, tokens_remaining, trace_id), rate_limit_bypassed (reason), rate_limit_sessions_cleaned (count)

- **Rate Limits** → Future Work
  - File: `docs/roadmap/rate_limiting_enhancements.md`
  - Distributed rate limiting (Redis cross-instance), adaptive per-user limits (fast typers 7 msg/sec), per-tier system (premium/free), smart retry SDK

#### [ADR-0053c](../../docs/architecture/decisions/0053c-*.md): 0053C Cancel Path

**Components:**

- **Cancel Path** → Cancellation Trigger Mechanisms
  - File: `k1/l4_ingress/websocket/cancellation_manager.py`
  - New message arrival (implicit), explicit stop button (highest priority), voice barge-in (UX-critical), context switch detection (automatic)

- **Cancel Path** → CancellationToken Class
  - File: `k1/l4_ingress/websocket/cancellation_token.py`
  - token_id, session_id, trigger, timestamp, is_cancelled flag (atomic), cancel() and check() methods, wait(timeout) for blocking

- **Cancel Path** → Token Propagation
  - File: `k1/l4_ingress/websocket/cancellation_manager.py`
  - WebSocket → message queue → orchestrator → planner → model hub → streaming engine → tool runner → K0 bridge → KV cache, shared memory flag

- **Cancel Path** → 4-Stage Cancellation Cascade
  - File: `k1/l4_ingress/websocket/cancellation_manager.py`
  - Signal 20ms + Abort 30ms + Cleanup 40ms + Rollback 30ms = 120ms P95 total, 250ms hard timeout fail-safe

- **Cancel Path** → Stage 1 Signal Propagation
  - File: `k1/l4_ingress/websocket/cancellation_manager.py`
  - 20ms: WebSocket signal receive (5ms), token creation (1ms), broadcast to all layers (10ms), logging (4ms)

- **Cancel Path** → Stage 2 Task Abort
  - File: `k1/l4_ingress/websocket/cancellation_manager.py`
  - 30ms: streaming abort SIGTERM (10ms), LLM inference stop (5ms), tool process SIGTERM (10ms), agent negotiation cancel (5ms)

- **Cancel Path** → Stage 3 Resource Cleanup
  - File: `k1/l4_ingress/websocket/cancellation_manager.py`
  - 40ms: KV cache eviction marking (15ms), SessionState rollback (10ms), tool connection close (10ms), K0 query cancellation (5ms)

- **Cancel Path** → Stage 4 State Rollback
  - File: `k1/l4_ingress/websocket/cancellation_manager.py`
  - 30ms: K0 WAL rollback (15ms), SessionState restore from checkpoint (5ms), acknowledgment send (5ms), message queue clear (5ms)

- **Cancel Path** → Cancellation Safety Guarantees
  - File: `k1/l4_ingress/websocket/cancellation_manager.py`
  - No partial K0 writes (WAL atomicity), complete resource cleanup (RAII pattern), SessionState consistency (COW checkpointing), idempotent cancellation

- **Cancel Path** → Edge Case Handling
  - File: `k1/l4_ingress/websocket/cancellation_manager.py`
  - During LLM inference +10ms, during K0 write +15ms (WAL rollback), during tool execution +50ms (SIGTERM → SIGKILL), after completion no-op, duplicate no-op

- **Cancel Path** → Integration Points
  - File: `k1/l4_ingress/websocket/websocket_cancellation_integration.py`
  - WebSocket ingress, message queue clear, orchestrator abort, planner stop, model hub abort, streaming engine stop, tool runner terminate, K0 bridge rollback, KV cache evict

- **Cancel Path** → CancellationManager Class
  - File: `k1/l4_ingress/websocket/cancellation_manager.py`
  - active_tokens dict (session_id → token), trigger_cancellation (trigger, create token, broadcast, log), broadcast_token (propagate to all components)

- **Cancel Path** → Streaming Engine Integration
  - File: `k1/l4_ingress/streaming/streaming_engine.py`
  - set_token method, stream_response with token check per chunk, abort on cancel (break loop), logger.info streaming_aborted

- **Cancel Path** → KV Cache Integration
  - File: `k1/l4_runtime/kv_cache/cache_manager.py`
  - release_cache method (mark entries evictable), async cleanup (not synchronous delete), logger.info kv_cache_released

- **Cancel Path** → SessionState Integration
  - File: `k1/l4_runtime/session_state/state_manager.py`
  - checkpoint method (COW copy), rollback method (restore from checkpoint), checkpoints dict per session

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

#### [ADR-0050a](../../docs/architecture/decisions/0050a-*.md): 0050A SessionState Coherence

**Components:**

- **SessionState Coherence** → Per-Device Guarantees
  - File: `k1/l4_runtime/session_state/coherence.py`
  - Read-your-writes, monotonic reads/writes, <5ms propagation, session guarantees (Terry 1994)

- **SessionState Coherence** → Delta Journal
  - File: `k1/l4_runtime/session_state/delta_journal.py`
  - Append-only WAL, per-section checksum, sequence numbers, 25ms group commit

- **SessionState Coherence** → Crash Recovery
  - File: `k1/l4_runtime/session_state/crash_recovery.py`
  - Journal replay <2s, idempotent operations, conflict arbiter, version vectors


### Multi-Party Dialogue

#### [ADR-0082](../../docs/architecture/decisions/0082-*.md): 0082 Core Architecture

**Components:**

- **Core Architecture** → SessionState Extension
  - File: `k1/l4_runtime/session_state/scoreboard.py`
  - Per-speaker context in Section 2 Scoreboard, speaker_id keyed state, preferences/recent_queries/active status, conversation_mode (single_user/multi_party), active_speakers list

- **Core Architecture** → Turn Boundary Extension
  - File: `k1/l4_runtime/turn_boundary/multi_party.py`
  - Multi-speaker turn state, segment attribution per speaker, overlap detection (timestamp+energy), allocation_strategy field, speaker context retrieval API


### Multi-Tier Storage

#### [ADR-0020](../../docs/architecture/decisions/0020-*.md): 0020 Lifecycle Management

**Components:**

- **Lifecycle Management** → Hot→Warm Migration
  - File: `k1/l4_runtime/storage/hot_tier.py`
  - Evict LRU (capacity >56MB) or inactive (60min idle), checkpoint to K0 WAL, transparent migration

- **Lifecycle Management** → Warm→Cold Migration
  - File: `k1/l4_runtime/storage/warm_tier.py`
  - Migrate sessions >30 days, daily batch job, query+archive+delete, 100 sessions per batch

#### [ADR-0020a](../../docs/architecture/decisions/0020a-*.md): 0020A Hot Tier (L1 RAM)

**Components:**

- **Hot Tier (L1 RAM)** → HotTier Class
  - File: `k1/l4_runtime/storage/hot_tier.py`
  - In-memory SessionState dict, OrderedDict for LRU, 56MB capacity, <1ms access, Python dataclass storage

- **Hot Tier (L1 RAM)** → LRU Tracking
  - File: `k1/l4_runtime/storage/hot_tier.py`
  - Track last access time, OrderedDict move_to_end, evict LRU when >56MB, <5ms eviction

- **Hot Tier (L1 RAM)** → Inactive Timeout
  - File: `k1/l4_runtime/storage/hot_tier.py`
  - 60 minutes idle detection, background eviction task every 5 min, move to warm tier

- **Hot Tier (L1 RAM)** → Checkpoint Coordination
  - File: `k1/l4_runtime/storage/hot_tier.py`
  - Work with K0Checkpointer, 5-minute checkpoint interval, durability via K0 WAL

- **Hot Tier (L1 RAM)** → HotTier Manager
  - File: `k1/l4_runtime/storage/hot_tier_manager.py`
  - Background eviction task, asyncio task lifecycle, graceful shutdown, 5-minute interval

#### [ADR-0020b](../../docs/architecture/decisions/0020b-*.md): 0020B Warm Tier (L2 SSD)

**Components:**

- **Warm Tier (L2 SSD)** → WarmTier Class
  - File: `k1/l4_runtime/storage/warm_tier.py`
  - K0 WAL queries, delta reconstruction, 100MB capacity 30-day retention, <50ms access

- **Warm Tier (L2 SSD)** → Delta Reconstruction
  - File: `k1/l4_runtime/storage/warm_tier.py`
  - Replay delta chain from K0 WAL, _reconstruct_from_deltas, <20ms for 10 deltas, sequential replay

- **Warm Tier (L2 SSD)** → 30-Day Lifecycle
  - File: `k1/l4_runtime/storage/warm_tier.py`
  - Migrate sessions >30 days to cold tier, background task 24h interval, query_sessions_before, cleanup

- **Warm Tier (L2 SSD)** → WarmTier Manager
  - File: `k1/l4_runtime/storage/warm_tier_manager.py`
  - Background migration task, daily archival job 2 AM, batch_size 100, asyncio lifecycle

#### [ADR-0020c](../../docs/architecture/decisions/0020c-*.md): 0020C Cold Tier (L3 Object)

**Components:**

- **Cold Tier (L3 Object)** → ColdTier Class
  - File: `k1/l4_runtime/storage/cold_tier.py`
  - S3-compatible API (boto3), unlimited capacity, <500ms access, $0.02/GB/month STANDARD

- **Cold Tier (L3 Object)** → S3 boto3 Integration
  - File: `k1/l4_runtime/storage/cold_tier.py`
  - boto3 client, S3 GET/PUT/DELETE, AWS S3 or MinIO, endpoint_url configuration, IAM role support

- **Cold Tier (L3 Object)** → Object Key Structure
  - File: `k1/l4_runtime/storage/cold_tier.py`
  - sessions/{session_id}/state.fb, flat hierarchy, FlatBuffers binary, efficient retrieval

- **Cold Tier (L3 Object)** → Storage Class Optimization
  - File: `k1/l4_runtime/storage/cold_tier.py`
  - STANDARD ($0.023/GB/mo frequent access) vs GLACIER ($0.004/GB/mo compliance 1+ year)

- **Cold Tier (L3 Object)** → Lifecycle Policies
  - File: `k1/l4_runtime/storage/cold_tier_lifecycle.py`
  - Automatic STANDARD → GLACIER after 1 year, ColdTierLifecyclePolicy class, S3 lifecycle API

- **Cold Tier (L3 Object)** → Rare Retrieval
  - File: `k1/l4_runtime/storage/cold_tier.py`
  - 0.1% daily access rate, <500ms P95 (S3 GET 300ms + deserialize 100ms), cache in warm/hot tier


### OpenAPI 3.1 Specs

#### [ADR-0047](../../docs/architecture/decisions/0047-*.md): 0047 Auto-Generation

**Components:**

- **Auto-Generation** → FastAPI Code Annotations
  - File: `k1/api/rest/sessions.py`
  - Pydantic models, Field() descriptions, Config.schema_extra examples, auto-generated from code

- **Auto-Generation** → OpenAPI Schema Generator
  - File: `k1/api/rest/openapi_generator.py`
  - FastAPI app.openapi(), components/schemas, paths, security schemes, servers config

- **Auto-Generation** → Pydantic Models
  - File: `k1/api/rest/models.py`
  - CreateSessionRequest, Session, Turn, Conversation, schema validation

- **Interactive Documentation** → Swagger UI
  - File: `k1/api/rest/swagger_ui.py`
  - /docs endpoint, interactive sandbox, JWT authentication, Try it out button

- **Interactive Documentation** → ReDoc
  - File: `k1/api/rest/redoc.py`
  - /redoc endpoint, clean documentation, schema explorer, search functionality

- **Spec Endpoints** → JSON Spec
  - File: `k1/api/rest/openapi_json.py`
  - /v1/openapi.json endpoint, machine-readable spec, SDK generation source

- **Spec Endpoints** → YAML Spec
  - File: `k1/api/rest/openapi_yaml.py`
  - /v1/openapi.yaml endpoint, human-readable spec, review-friendly format

- **Schema Validation** → Pydantic Validation
  - File: `k1/api/rest/validation.py`
  - Request/response schema enforcement, 400 Bad Request on invalid JSON, ge/le/pattern constraints

- **Schema Validation** → Field Constraints
  - File: `k1/api/rest/models.py`
  - Field(ge=1000, le=300000, pattern regex), Pydantic validators, enum constraints

- **FlatBuffers Annotations** → Binary Format Docs
  - File: `k1/api/rest/flatbuffers_docs.py`
  - Content-Type application/flatbuffers, FlatBuffers schema references, performance notes

- **FlatBuffers Annotations** → Dual Format Support
  - File: `k1/api/rest/dual_format_handler.py`
  - JSON (application/json) + FlatBuffers (application/flatbuffers), Content-Type negotiation

- **Versioning** → URL-Based Versioning
  - File: `k1/api/rest/versioning.py`
  - /v1/ prefix, /v2/ future versions, deprecation notices, sunset headers

- **Versioning** → Deprecation Metadata
  - File: `k1/api/rest/deprecation.py`
  - Deprecated: true in OpenAPI schema, x-sunset-date custom extension, migration guides

- **Security Schemes** → Security Requirements
  - File: `k1/api/rest/auth_decorator.py`
  - security parameter in @router.post(), enforce JWT on endpoints, 401 Unauthorized

- **Caching** → OpenAPI Cache
  - File: `k1/api/rest/openapi_cache.py`
  - @lru_cache(maxsize=1), 1-hour cache (timestamp rounded to hour), Cache-Control header

- **Configuration** → OpenAPI Metadata
  - File: `k1/api/rest/metadata.py`
  - title, version, description, contact info, servers (production, staging)

- **Configuration** → Custom OpenAPI
  - File: `k1/api/rest/custom_openapi.py`
  - custom_openapi() function, FlatBuffers annotations, x-* custom extensions

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


### Performance Budgets

#### [ADR-0024](../../docs/architecture/decisions/0024-*.md): 0024 Component-Level Budgets

**Components:**

- **Component-Level Budgets** → Grounding Act Update
  - File: `k1/l4_runtime/session_state/grounding_act.py`
  - <30ms P95 budget, SessionState section update, 100ms timeout

- **Memory Budgets** → SessionState Soft Limit
  - File: `k1/l4_runtime/session_state/memory_limits.py`
  - <64KB soft limit, trigger eviction at 80% (51KB), GREEN tier

- **Memory Budgets** → SessionState Hard Limit
  - File: `k1/l4_runtime/session_state/memory_limits.py`
  - 128KB hard limit, force eviction (COLD items), AMBER tier

- **Memory Budgets** → SessionState OOM Threshold
  - File: `k1/l4_runtime/session_state/memory_limits.py`
  - 256KB OOM threshold, reject turn + evict WARM items, RED tier, kill session if exceeded

- **Graceful Degradation** → Backpressure Propagation
  - File: `k1/l4_ingress/api_gateway/backpressure.py`
  - Reject turns when E2E sustained >2500ms, return 503, CRITICAL tier

- **Graceful Degradation** → User Transparency
  - File: `k1/l4_ingress/api_gateway/degradation_notification.py`
  - Notify user about degraded mode, "System under heavy load", transparent communication

#### [ADR-0024b](../../docs/architecture/decisions/0024b-*.md): 0024B Component-Level Budgets

**Components:**

- **Component-Level Budgets** → Grounding Act Update
  - File: `k1/l4_runtime/session_state/grounding_act.py`
  - <30ms P95 budget, SessionState section update, 100ms timeout

#### [ADR-0024c](../../docs/architecture/decisions/0024c-*.md): 0024C Memory Budgets

**Components:**

- **Memory Budgets** → SessionState Soft Limit
  - File: `k1/l4_runtime/session_state/memory_limits.py`
  - <64KB soft limit, trigger eviction at 80% (51KB), GREEN tier

- **Memory Budgets** → SessionState Hard Limit
  - File: `k1/l4_runtime/session_state/memory_limits.py`
  - 128KB hard limit, force eviction (COLD items), AMBER tier

- **Memory Budgets** → SessionState OOM Threshold
  - File: `k1/l4_runtime/session_state/memory_limits.py`
  - 256KB OOM threshold, reject turn + evict WARM items, RED tier, kill session if exceeded

#### [ADR-0024d](../../docs/architecture/decisions/0024d-*.md): 0024D Graceful Degradation

**Components:**

- **Graceful Degradation** → Backpressure Propagation
  - File: `k1/l4_ingress/api_gateway/backpressure.py`
  - Reject turns when E2E sustained >2500ms, return 503, CRITICAL tier

- **Graceful Degradation** → User Transparency
  - File: `k1/l4_ingress/api_gateway/degradation_notification.py`
  - Notify user about degraded mode, "System under heavy load", transparent communication


### Prometheus Metrics

#### [ADR-0029](../../docs/architecture/decisions/0029-*.md): 0029 Turn-Level

**Components:**

- **Turn-Level** → TTFT Metrics
  - File: `k1/l4_runtime/turn_pipeline/ttft_metrics.py`
  - TTFT latency histogram (150ms P95 budget), Turn_ttft_ms, Histogram buckets (10/50/100/150/200/250/500ms), User responsiveness

- **Turn-Level** → E2E Metrics
  - File: `k1/l4_runtime/turn_pipeline/e2e_metrics.py`
  - E2E turn latency (2000ms P95 budget), Turn_e2e_latency_ms, Histogram buckets (100/250/500/1000/1500/2000/2500/5000ms), Total wait time

- **Turn-Level** → Barge-In Metrics
  - File: `k1/l4_runtime/turn_pipeline/barge_in_metrics.py`
  - Barge-in cancellation latency (120ms P95 budget), Barge_in_cancel_latency_ms, VAD detection + signal propagation + TTS stop, Voice UX responsiveness

- **Turn-Level** → Turn Rate
  - File: `k1/l4_runtime/turn_pipeline/turn_metrics.py`
  - Turn_turns_total counter, Status labels (success/error/timeout/cancelled), Privacy band labels (GREEN/AMBER/RED), Intent type labels

#### [ADR-0029b](../../docs/architecture/decisions/0029b-*.md): 0029B Turn-Level

**Components:**

- **Turn-Level** → TTFT Metrics
  - File: `k1/l4_runtime/turn_pipeline/ttft_metrics.py`
  - TTFT latency histogram (150ms P95 budget), Turn_ttft_ms, Histogram buckets (10/50/100/150/200/250/500ms), User responsiveness

- **Turn-Level** → E2E Metrics
  - File: `k1/l4_runtime/turn_pipeline/e2e_metrics.py`
  - E2E turn latency (2000ms P95 budget), Turn_e2e_latency_ms, Histogram buckets (100/250/500/1000/1500/2000/2500/5000ms), Total wait time

- **Turn-Level** → Barge-In Metrics
  - File: `k1/l4_runtime/turn_pipeline/barge_in_metrics.py`
  - Barge-in cancellation latency (120ms P95 budget), Barge_in_cancel_latency_ms, VAD detection + signal propagation + TTS stop, Voice UX responsiveness

- **Turn-Level** → Turn Rate
  - File: `k1/l4_runtime/turn_pipeline/turn_metrics.py`
  - Turn_turns_total counter, Status labels (success/error/timeout/cancelled), Privacy band labels (GREEN/AMBER/RED), Intent type labels


### Protocol Validation

#### [ADR-0003](../../docs/architecture/decisions/0003-*.md): 0003 PDL Language

**Components:**

- **PDL Language** → PDL Parser
  - File: `k1/l4_runtime/protocol_monitor/pdl_parser.py`
  - YAML protocol parser, type system validation, state transition rules, message schema definitions, <5ms P95 parse latency

- **PDL Language** → Compiler Pipeline
  - File: `k1/l4_runtime/protocol_monitor/pdl_compiler.py`
  - PDL→FSM compilation, protocol composition, timeout injection, error state generation, MPST theory validation (Honda et al. 2008)

- **Protocol Definitions** → Hire Protocol
  - File: `k1/protocols/hire.pdl.yml`
  - 4-state FSM (IDLE→OFFER→ACCEPT→HIRED), Contract Net Protocol (Smith 1980), manager-contractor roles, timeout 3000ms, capability matching

- **Protocol Definitions** → Task Protocol
  - File: `k1/protocols/task.pdl.yml`
  - 5-state FSM (IDLE→ANNOUNCE→BID→EXECUTING→COMPLETE), 3-phase orchestration integration, weighted selection, timeout 5000ms

- **Protocol Definitions** → Clarification Protocol
  - File: `k1/protocols/clarification.pdl.yml`
  - 4-state FSM (IDLE→REQUEST→RESPOND→RESOLVED), user-agent interaction, timeout 30000ms, escalation to HITL

- **Protocol Definitions** → Barge-In Protocol
  - File: `k1/protocols/barge_in.pdl.yml`
  - 4-state FSM (IDLE→INTERRUPT→CANCEL→RESUMED), user interrupt handling, token cancellation, graceful degradation

- **Protocol Definitions** → Tool Call Protocol
  - File: `k1/protocols/tool_call.pdl.yml`
  - 5-state FSM (IDLE→PREPARE→EXECUTE→SUCCESS→COMPLETE), parallel execution, timeout 3000ms per tool, error isolation

- **Protocol Definitions** → Saga Protocol
  - File: `k1/protocols/saga.pdl.yml`
  - 6-state FSM (IDLE→TRANSACTION→COMPENSATE→ROLLBACK→SUCCESS→COMPLETE), compensating transactions, rollback on failure, ACID semantics

- **Protocol Monitor** → FSM Registry
  - File: `k1/l4_runtime/protocol_monitor/fsm_registry.py`
  - Compiled FSM storage, protocol lookup by name, version management, hot-reload support

- **Protocol Monitor** → Session Tracker
  - File: `k1/l4_runtime/protocol_monitor/session_tracker.py`
  - Active session tracking, state per session, timeout enforcement, session lifecycle management

- **Protocol Monitor** → Validator
  - File: `k1/l4_runtime/protocol_monitor/validator.py`
  - Message validation against FSM, state transition checks, <5ms P95 validation latency, violation detection

- **Protocol Monitor** → Violation Handler
  - File: `k1/l4_runtime/protocol_monitor/violation_handler.py`
  - Protocol violation logging, recovery strategies, session termination, audit trail integration

- **Protocol Monitor** → Timeout Enforcer
  - File: `k1/l4_runtime/protocol_monitor/timeout_enforcer.py`
  - Per-protocol timeout tracking, LLM timeout handling (5000ms), timeout callbacks, graceful degradation

- **Protocol Monitor** → Composition Manager
  - File: `k1/l4_runtime/protocol_monitor/composition_manager.py`
  - Multi-protocol coordination, nested protocol support, parallel protocol execution, deadlock detection

- **Security Integration** → Role Verifier
  - File: `k1/l4_runtime/protocol_monitor/role_verifier.py`
  - Agent role validation, capability-based access control, role mismatch detection, security audit logging

- **Security Integration** → Agent Lease
  - File: `k1/l4_runtime/protocol_monitor/agent_lease.py`
  - Agent authorization tokens, lease expiration, renewal workflows, revocation support

- **Security Integration** → Message Signer
  - File: `k1/l4_runtime/protocol_monitor/message_signer.py`
  - Message integrity verification, signature validation, tamper detection, cryptographic signing

#### [ADR-0003a](../../docs/architecture/decisions/0003a-*.md): 0003A PDL Language

**Components:**

- **PDL Language** → PDL Parser
  - File: `k1/l4_runtime/protocol_monitor/pdl_parser/parser.py`
  - YAML parsing, syntax validation, semantic validation, FSM generation

- **PDL Language** → Compiler Pipeline
  - File: `k1/l4_runtime/protocol_monitor/pdl_parser/compiler.py`
  - YAML→FSM, deadlock detection (Tarjan), FlatBuffers serialization, <100ms compilation

- **PDL Language** → PDL Specification
  - File: `k1/protocols/*.pdl.yml`
  - YAML schema, states, transitions, timeouts, violations, roles, messages

#### [ADR-0003b](../../docs/architecture/decisions/0003b-*.md): 0003B Protocol Definitions

**Components:**

- **Protocol Definitions** → Agent Hire Protocol
  - File: `k1/protocols/hire.pdl.yml`
  - 6 states, 8 transitions, Contract Net, 500ms negotiation, 100ms selection

- **Protocol Definitions** → Task Execution Protocol
  - File: `k1/protocols/task.pdl.yml`
  - 5 states, 10 transitions, AI planning, 5000ms LLM timeout, 10000ms execution

- **Protocol Definitions** → Clarification Protocol
  - File: `k1/protocols/clarification.pdl.yml`
  - 4 states, 6 transitions, nested protocol, 30000ms user timeout, human-in-loop

- **Protocol Definitions** → Barge-In Protocol
  - File: `k1/protocols/barge_in.pdl.yml`
  - 3 states, 5 transitions, interrupt handling, 200ms decision, VAD detection

- **Protocol Definitions** → Tool Call Protocol
  - File: `k1/protocols/tool_call.pdl.yml`
  - 4 states, 7 transitions, MCP/WASM sandbox, 3000ms execution timeout

- **Protocol Definitions** → Saga Rollback Protocol
  - File: `k1/protocols/saga.pdl.yml`
  - 5 states, 9 transitions, compensation, 5000ms compensate, 2000ms rollback

#### [ADR-0003c](../../docs/architecture/decisions/0003c-*.md): 0003C Protocol Monitor

**Components:**

- **Protocol Monitor** → FSM Registry
  - File: `k1/l4_runtime/protocol_monitor/fsm_registry.py`
  - Load 6 protocols from FlatBuffers, <100ms per protocol, reachability check

- **Protocol Monitor** → Session FSM Tracker
  - File: `k1/l4_runtime/protocol_monitor/session_tracker.py`
  - Per-session state, RwLock concurrency, hash table, cleanup

- **Protocol Monitor** → Protocol Validator
  - File: `k1/l4_runtime/protocol_monitor/validator.py`
  - Receive-side validation, <5ms P95 mailbox budget, <2ms validation

- **Protocol Monitor** → Violation Handler
  - File: `k1/l4_runtime/protocol_monitor/violation_handler.py`
  - BLOCK, WARN, DLQ, REPAIR, FALLBACK, ABORT actions

- **Protocol Monitor** → Timeout Enforcer
  - File: `k1/l4_runtime/protocol_monitor/timeout_enforcer.py`
  - Background task, 100ms poll, auto-transitions, progress guarantees

- **Protocol Monitor** → Composition Manager
  - File: `k1/l4_runtime/protocol_monitor/composition_manager.py`
  - Pause/resume/interrupt/abort, protocol stack, nested protocols

#### [ADR-0003d](../../docs/architecture/decisions/0003d-*.md): 0003D Security

**Components:**

- **Security** → Role Verifier
  - File: `k1/l4_runtime/protocol_monitor/role_verifier.py`
  - HMAC-SHA256 verification, <1ms P95, lease lookup, capability check

- **Security** → Agent Lease
  - File: `k1/l4_runtime/agent_fabric/lease.py`
  - Lease metadata, capabilities, signature_secret (32 bytes), 3600s duration

- **Security** → Message Signer
  - File: `k1/l4_runtime/actor_fabric/message_signer.py`
  - HMAC-SHA256 signing, sender envelope, signature verification

- **Security** → 2-Phase Validation
  - File: `k1/l4_runtime/protocol_monitor/two_phase_validator.py`
  - Phase 1 (role <1ms) + Phase 2 (protocol <2ms) = <3ms total


### REST API

#### [ADR-0014](../../docs/architecture/decisions/0014-*.md): 0014 Content Negotiation

**Components:**

- **Content Negotiation** → Accept/Content-Type Parser
  - File: `k1/api_gateway/content_negotiation.py`
  - HTTP header parsing, format detection (JSON default, FlatBuffers optional), quality parameter handling, <1ms parsing latency

- **Serializers** → JSON Serializer
  - File: `k1/api_gateway/serializers/json_serializer.py`
  - FlatBuffers→JSON conversion, 2.1ms P95 serialization, 20 REST endpoints, 95% usage (developer-friendly default)

- **Serializers** → FlatBuffers Serializer
  - File: `k1/api_gateway/serializers/flatbuffers_serializer.py`
  - Zero-copy passthrough, 0.7ms P95 serialization, 34% payload reduction, 5% usage (native clients)

- **OpenAPI Generation** → Spec Generator
  - File: `k1/api_gateway/openapi_generator.py`
  - Auto-derive from .fbs schemas, 8,450 lines OpenAPI 3.1 spec, type mappings, example generation

- **Validation** → JSON Schema Validator
  - File: `k1/api_gateway/validators/json_validator.py`
  - Request/response validation, error reporting, schema compliance checks, <2ms validation latency


### REST API Dual Format

#### [ADR-0014a](../../docs/architecture/decisions/0014a-*.md): 0014A Content Negotiation

**Components:**

- **Content Negotiation** → Accept Header Parsing
  - File: `k1/l4_ingress/api_gateway/content_negotiation.py`
  - Parse Accept header, quality values (q=), sort by priority, <0.2ms latency

- **Content Negotiation** → FastAPI Middleware
  - File: `k1/l4_ingress/api_gateway/dual_format_middleware.py`
  - DualFormatMiddleware, request/response format detection, 406/415 errors

- **Content Negotiation** → Error Handling
  - File: `k1/l4_ingress/api_gateway/error_handlers.py`
  - 406 Not Acceptable, 415 Unsupported Media Type, always JSON errors

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

#### [ADR-0014c](../../docs/architecture/decisions/0014c-*.md): 0014C Serialization Pipeline

**Components:**

- **Serialization Pipeline** → JSON → FlatBuffers Converter
  - File: `k1/l4_ingress/api_gateway/json_to_fb_converter.py`
  - Parse JSON, validate, construct FlatBuffers builder, Pack() method

- **Serialization Pipeline** → FlatBuffers → JSON Converter
  - File: `k1/l4_ingress/api_gateway/fb_to_json_converter.py`
  - Unpack() method, zero-copy deserialization, <5ms overhead P95

- **Serialization Pipeline** → Request Deserialization
  - File: `k1/l4_ingress/api_gateway/request_parser.py`
  - FastAPI dependency injection, parse JSON/FlatBuffers, 400 errors for invalid input

- **Serialization Pipeline** → Response Serialization
  - File: `k1/l4_ingress/api_gateway/response_builder.py`
  - DualFormatResponse class, Content-Type header, JSON/FlatBuffers selection

- **Serialization Pipeline** → Error Normalization
  - File: `k1/l4_ingress/api_gateway/error_normalizer.py`
  - All errors JSON format (406/415/500), even if FlatBuffers requested

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


### REST API Session Management

#### [ADR-0041](../../docs/architecture/decisions/0041-*.md): 0041 RESTful Principles

**Components:**

- **RESTful Principles** → Stateless Architecture
  - File: `k1/l4_ingress/rest_api/stateless.py`
  - No server-side session state (JWT in Authorization header ADR-0037), serverless-friendly (AWS Lambda/Cloud Functions), Roy Fielding REST constraints (2000)

- **RESTful Principles** → HTTP Caching
  - File: `k1/l4_ingress/rest_api/caching.py`
  - ETag + Last-Modified headers, 80% cache hit rate (3M GET requests → 8ms cached vs 100ms uncached), Cache-Control for CDN

- **RESTful Principles** → Resource-Oriented Design
  - File: `k1/l4_ingress/rest_api/resources.py`
  - /v1/sessions resource pattern (not /createSession), HTTP verbs (GET/POST/PATCH/DELETE), standard status codes (200/201/404/409)

- **RESTful Principles** → HATEOAS Links
  - File: `k1/l4_ingress/rest_api/hateoas.py`
  - Hypermedia links (self/next/prev/related), client API discoverability (no hardcoded URLs), evolvable API without breaking clients

#### [ADR-0041a](../../docs/architecture/decisions/0041a-*.md): 0041A Session Lifecycle CRUD

**Components:**

- **Session Lifecycle CRUD** → POST Create Session
  - File: `k1/l4_ingress/rest_api/sessions/create.py`
  - POST /v1/sessions creates new session, returns session_id + JWT token, <500ms creation, stateless (no server state)

- **Session Lifecycle CRUD** → GET Read Session
  - File: `k1/l4_ingress/rest_api/sessions/read.py`
  - GET /v1/sessions/{id} returns session details (status/agents/metadata), ETag caching (82% hit rate = 8ms response), <100ms uncached

- **Session Lifecycle CRUD** → PATCH Update Session
  - File: `k1/l4_ingress/rest_api/sessions/update.py`
  - PATCH /v1/sessions/{id} updates metadata (partial update), If-Match header for optimistic locking, conflict detection (409 Conflict)

- **Session Lifecycle CRUD** → DELETE Terminate Session
  - File: `k1/l4_ingress/rest_api/sessions/delete.py`
  - DELETE /v1/sessions/{id} terminates session, cleanup resources, 204 No Content response, retention policy integration (ADR-0039)

#### [ADR-0041b](../../docs/architecture/decisions/0041b-*.md): 0041B Idempotency

**Components:**

- **Idempotency** → Idempotency-Key Header
  - File: `k1/l4_ingress/rest_api/idempotency/key_handler.py`
  - Client-generated unique key (UUID/ulid) for safe retries, 24-hour key retention in Redis, 8% duplicate rate = 120K deduped requests in 6 months

- **Idempotency** → State Synchronization
  - File: `k1/l4_ingress/rest_api/idempotency/state_sync.py`
  - REST API + WebSocket share SessionState (ADR-0012), consistent state across channels, sync/async turn modes (sync <5000ms, async 202 Accepted with webhook)

#### [ADR-0041c](../../docs/architecture/decisions/0041c-*.md): 0041C Pagination

**Components:**

- **Pagination** → Cursor-Based Pagination
  - File: `k1/l4_ingress/rest_api/pagination/cursor.py`
  - Opaque cursor from last item ID, O(1) index lookup vs O(n) offset scan, <100ms pagination (78ms P95 actual), default limit 20 (max 100)

- **Pagination** → Infinite Scrolling Support
  - File: `k1/l4_ingress/rest_api/pagination/infinite_scroll.py`
  - has_more flag, next_cursor/prev_cursor links, mobile app infinite scroll support, consistent results during concurrent writes

#### [ADR-0041d](../../docs/architecture/decisions/0041d-*.md): 0041D Documentation

**Components:**

- **Documentation** → OpenAPI 3.1 Spec
  - File: `k1/l4_ingress/rest_api/openapi/spec_generator.py`
  - Machine-readable API docs for 21 REST endpoints, auto-generated SDKs (TypeScript/Python), Swagger UI integration, type-safe client libraries

- **Documentation** → RFC 7807 Problem Details
  - File: `k1/l4_ingress/rest_api/errors/problem_details.py`
  - Standardized error format (type/title/status/detail/instance), typed errors (404 SessionNotFound, 429 RateLimitExceeded, 409 Conflict, 400 InvalidInput), <0.5% error rate (0.3% actual)


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

#### [ADR-0016b](../../docs/architecture/decisions/0016b-*.md): 0016B Serialization

**Components:**

- **Serialization** → FlatBuffers→JSON Serializer
  - File: `k1/l4_ingress/sse_gateway/serializer.py`
  - SSESerializer, PascalCase→snake_case, <2ms P95, 17 event types

- **Serialization** → Event-Specific Serializers
  - File: `k1/l4_ingress/sse_gateway/event_serializers.py`
  - 17 serializers, zero-copy read, manual dict build, enum→string

- **Serialization** → SSE Formatter
  - File: `k1/l4_ingress/sse_gateway/formatter.py`
  - SSEFormatter, text/event-stream, event/id/data fields, UTF-8 encoding

- **Serialization** → String Interning
  - File: `k1/l4_ingress/sse_gateway/serializer.py`
  - sys.intern(), 10-15% memory reduction, common field names cached

- **Serialization** → Compact JSON
  - File: `k1/l4_ingress/sse_gateway/serializer.py`
  - separators=(',',':'), no whitespace, 30-40% smaller vs pretty-print

#### [ADR-0016c](../../docs/architecture/decisions/0016c-*.md): 0016C Filtering

**Components:**

- **Filtering** → Topic-Based Filter
  - File: `k1/l4_ingress/sse_gateway/filter.py`
  - TopicFilter, set membership <1ms, 5 topics → 17 events

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

#### [ADR-0046](../../docs/architecture/decisions/0046-*.md): 0046 Bridge Architecture

**Components:**

- **Bridge Architecture** → Bridge Coordinator
  - File: `k1/api/websocket/sse_bridge.py`
  - SSEWebSocketBridge, Transform SSE→WebSocket, Session-based filtering, <20ms combined latency

- **Bridge Architecture** → Event Transformation
  - File: `k1/api/websocket/sse_bridge.py`
  - SSE JSON→WebSocket FlatBuffers, 10 event types, 5ms transform P95

- **Bridge Architecture** → Connection Registry
  - File: `k1/api/websocket/sse_bridge.py`
  - Register/unregister WebSocket connections, session_id → Set[WebSocketConnection], lifecycle management

- **Bridge Architecture** → Broadcast Engine
  - File: `k1/api/websocket/sse_bridge.py`
  - Parallel broadcast, asyncio.gather, 15ms broadcast P95, 1000 events/sec

- **Event Mapping** → Memory Formation
  - File: `k1/api/websocket/transformers/memory_formation.py`
  - memory.formation.* → AgentMessageChunk, streaming response chunks, chunk_text/chunk_index/is_final

- **Event Mapping** → Turn Committed
  - File: `k1/api/websocket/transformers/turn_committed.py`
  - cognitive.memory.write.committed → TurnCommitted, turn_id/receipt_id, persistence ACK

- **Event Mapping** → Agent Selected
  - File: `k1/api/websocket/transformers/agent_selected.py`
  - cognitive.arbitration.decision.made → AgentSelected, selected_agent/confidence, orchestration decision

- **Event Mapping** → Presence Update
  - File: `k1/api/websocket/transformers/presence_update.py`
  - presence.* → PresenceUpdate, user_id/status (online/offline), device status

- **Event Mapping** → Workspace Broadcast
  - File: `k1/api/websocket/transformers/workspace_broadcast.py`
  - workspace.* → WorkspaceBroadcast, workspace-wide notifications, maintenance alerts

- **Event Mapping** → Job Progress
  - File: `k1/api/websocket/transformers/job_progress.py`
  - job.* → JobProgress, job_id/progress (0.0-1.0), background job updates

- **Event Mapping** → Learning Update
  - File: `k1/api/websocket/transformers/learning_update.py`
  - intelligence.learning.* → LearningUpdate, learning feedback confirmation

- **Event Mapping** → Emergency Alert
  - File: `k1/api/websocket/transformers/emergency_alert.py`
  - family.emergency.* → EmergencyAlert, critical family notifications

- **Event Mapping** → Safety Alert
  - File: `k1/api/websocket/transformers/safety_alert.py`
  - infra.security.* → SafetyAlert, PII detection, RED band violations

- **Connection Lifecycle** → WebSocket Endpoint
  - File: `k1/api/websocket/endpoint.py`
  - /v1/websocket endpoint, JWT authentication, bidirectional communication

- **Connection Lifecycle** → WebSocket Connection
  - File: `k1/api/websocket/connection.py`
  - WebSocketConnection class, send_queue (100 messages), backpressure detection

- **Connection Lifecycle** → Connection Pool
  - File: `k1/api/websocket/connection_pool.py`
  - 10,000 concurrent connections, session_id → Set[WebSocketConnection], register/unregister

- **Connection Lifecycle** → Backpressure Handler
  - File: `k1/api/websocket/backpressure.py`
  - Bounded send queue (100 max), drop oldest if full, slow client detection, 0.1s timeout

- **SSE Subscription** → Topic Subscription
  - File: `k1/api/websocket/sse_subscription.py`
  - Subscribe 10 topic categories (memory.*, cognitive.*, presence.*, workspace.*, job.*)

- **SSE Subscription** → Session Filtering
  - File: `k1/api/websocket/session_filter.py`
  - Filter SSE events by session_id, 90% bandwidth savings, only broadcast to relevant connections

- **Configuration** → Bridge Config
  - File: `k1/config/sse_bridge.yml`
  - Subscribed topics, max connections (10K), send_queue_size (100), backpressure_threshold (90%)


### Saga Error Recovery

#### [ADR-0008d](../../docs/architecture/decisions/0008d-*.md): 0008D Deadlock Handling

**Components:**

- **Deadlock Handling** → Resource Ordering
  - File: `k1/l4_runtime/saga/resource_lock.py`
  - acquire_multiple, sorted resource IDs, deterministic ordering, deadlock prevention

- **Deadlock Handling** → Deadlock Detection
  - File: `k1/l4_runtime/saga/deadlock_detector.py`
  - Timeout-based detection, 5s acquisition timeout, DeadlockError, metrics emission


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

- **Version Registry** → REST API Endpoint
  - File: `k1/l4_ingress/api_gateway/schema_registry_api.py`
  - GET /api/v1/schemas/registry, runtime compatibility queries, <20ms P95

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


### SessionState 6-Section Design

#### [ADR-0017](../../docs/architecture/decisions/0017-*.md): 0017 Overall Architecture

**Components:**

- **Overall Architecture** → 6-Section Design
  - File: `k1/l4_runtime/session_state/model.py`
  - 64KB soft limit, ephemeral working memory, delta batching to K0, section boundaries

- **Overall Architecture** → SessionState Model
  - File: `k1/l4_runtime/session_state/model.py`
  - 6 sections (beliefs, scoreboard, control, persona, multimodal, meta), FlatBuffers serialization <1ms

- **Overall Architecture** → Section Boundaries
  - File: `k1/l4_runtime/session_state/boundaries.py`
  - Size budgets per section, validation rules, overflow policies, eviction priority

- **Persona Section** → Voice Continuity (Amendment #1)
  - File: `k1/l4_runtime/session_state/sections/persona_manager.py`
  - voice_prosody (pitch/rate/volume controls), voice_history (last 10 snapshots), emotional_state (affect tracking with 24hr decay), self_model (capability awareness), personality_traits (trait dimens...

- **Multimodal Section** → Ambient & Multi-Party (Amendment #1)
  - File: `k1/l4_runtime/session_state/sections/multimodal_manager.py`
  - ambient_context (room occupancy, PIR/mmWave sensors), occupancy_history (last 20 events), active_speakers (current speakers in multi-party conversation), speaker_profiles (voice biometrics, 768-dim...

#### [ADR-0017a](../../docs/architecture/decisions/0017a-*.md): 0017A Beliefs Section

**Components:**

- **Beliefs Section** → User Facts
  - File: `k1/l4_runtime/session_state/sections/beliefs_manager.py`
  - Fact storage, confidence scores (0.0-1.0), temporal decay, K0 persistence

- **Beliefs Section** → Preferences
  - File: `k1/l4_runtime/session_state/sections/beliefs_manager.py`
  - User preferences, priority weights (0.0-1.0), adaptation rules

- **Beliefs Section** → History
  - File: `k1/l4_runtime/session_state/sections/beliefs_manager.py`
  - Turn summaries, episodic memory references, last 3-5 turns

- **Beliefs Section** → Fact Fusion
  - File: `k1/l4_runtime/session_state/sections/beliefs_manager.py`
  - Multi-source facts, conflict resolution, truth maintenance

- **Beliefs Section** → LRU Eviction
  - File: `k1/l4_runtime/session_state/sections/beliefs_manager.py`
  - Least recently used facts, evict when >20KB, last_accessed_ms tracking

- **Beliefs Section** → Source Tracking
  - File: `k1/l4_runtime/session_state/sections/beliefs_manager.py`
  - user_stated, inferred, system provenance, confidence updates

#### [ADR-0017b](../../docs/architecture/decisions/0017b-*.md): 0017B Scoreboard Section

**Components:**

- **Scoreboard Section** → Common Ground
  - File: `k1/l4_runtime/session_state/sections/scoreboard_manager.py`
  - Shared beliefs, mutual knowledge, grounding acts, Clark & Brennan 1991

- **Scoreboard Section** → QUD Stack
  - File: `k1/l4_runtime/session_state/sections/scoreboard_manager.py`
  - Questions Under Discussion, stack discipline, priority ordering, Roberts 1996

- **Scoreboard Section** → Turn State
  - File: `k1/l4_runtime/session_state/sections/scoreboard_manager.py`
  - Current turn phase, speaker roles, dialogue acts

- **Scoreboard Section** → Discourse Markers
  - File: `k1/l4_runtime/session_state/sections/scoreboard_manager.py`
  - Topic shifts, clarifications, interruptions, barge-in

- **Scoreboard Section** → Entity Tracking
  - File: `k1/l4_runtime/session_state/sections/scoreboard_manager.py`
  - Entities (person, document, event), salience (0.0-1.0), last_mentioned_turn

- **Scoreboard Section** → Referent Resolution
  - File: `k1/l4_runtime/session_state/sections/scoreboard_manager.py`
  - Pronoun mapping (it, that), entity_id lookup <200μs, anaphora resolution

- **Scoreboard Section** → Salience Decay
  - File: `k1/l4_runtime/session_state/sections/scoreboard_manager.py`
  - Exponential decay (0.9 per turn), evict salience <0.01, temporal fading

#### [ADR-0017c](../../docs/architecture/decisions/0017c-*.md): 0017C Control Section

**Components:**

- **Control Section** → Agent Leases
  - File: `k1/l4_runtime/session_state/sections/control_manager.py`
  - Lease tracking, expiration times (30s default), capability grants, HMAC signatures

- **Control Section** → Flow Control
  - File: `k1/l4_runtime/session_state/sections/control_manager.py`
  - Resource locks, orchestrator coordination, admission control, turn lock

- **Control Section** → Flow State
  - File: `k1/l4_runtime/session_state/sections/control_manager.py`
  - 3-phase (negotiation, selection, execution), turn_id, timeout enforcement (60s)

- **Control Section** → Timeout Detection
  - File: `k1/l4_runtime/session_state/sections/control_manager.py`
  - Lease expiration check (1s interval), turn timeout detection, expired agent cleanup

- **Control Section** → Turn Lock
  - File: `k1/l4_runtime/session_state/sections/control_manager.py`
  - Boolean flag, turn_id, prevent concurrent turns, critical section

- **Control Section** → Budget Tracker
  - File: `k1/l4_runtime/session_state/sections/control_manager.py`
  - Latency, tokens, tool calls, cost budgets, utilization tracking

#### [ADR-0017d](../../docs/architecture/decisions/0017d-*.md): 0017D Persona Section

**Components:**

- **Persona Section** → Personality Traits
  - File: `k1/l4_runtime/session_state/sections/persona_manager.py`
  - Big Five (OCEAN), trait scores (0.0-1.0), consistency, Goldberg 1993

- **Persona Section** → Communication Style
  - File: `k1/l4_runtime/session_state/sections/persona_manager.py`
  - Tone (casual, formal), verbosity (0.0-1.0), humor level, vocabulary

- **Persona Section** → User Modeling
  - File: `k1/l4_runtime/session_state/sections/persona_manager.py`
  - User preferences, affect tracking, adaptation strategies

- **Persona Section** → LLM Prompt Injection
  - File: `k1/l4_runtime/session_state/sections/persona_manager.py`
  - Format traits as system prompt, trait formatting <5ms, LLM integration

- **Persona Section** → Trait Storage
  - File: `k1/l4_runtime/session_state/sections/persona_manager.py`
  - Key-value pairs, confidence tracking (0.0-1.0), static data (low eviction priority)

#### [ADR-0017e](../../docs/architecture/decisions/0017e-*.md): 0017E Multimodal Section

**Components:**

- **Multimodal Section** → Audio Context
  - File: `k1/l4_runtime/session_state/sections/multimodal_manager.py`
  - Voice activity detection, speaker diarization, prosody, ASR buffers

- **Multimodal Section** → Vision Context
  - File: `k1/l4_runtime/session_state/sections/multimodal_manager.py`
  - Image descriptions, OCR results, object detection, bounding boxes

- **Multimodal Section** → Modal Fusion
  - File: `k1/l4_runtime/session_state/sections/multimodal_manager.py`
  - Cross-modal references, attention mechanisms, fusion strategies

- **Multimodal Section** → Audio Buffers
  - File: `k1/l4_runtime/session_state/sections/multimodal_manager.py`
  - K0 blob storage pointers, chunk index, duration_ms, LRU eviction

- **Multimodal Section** → Vision Embeddings
  - File: `k1/l4_runtime/session_state/sections/multimodal_manager.py`
  - CLIP embeddings (512-dim), K0 blob pointers, image_id, dimensions

- **Multimodal Section** → Streaming State
  - File: `k1/l4_runtime/session_state/sections/multimodal_manager.py`
  - Active stream_id, codec metadata, sample_rate, stream status

#### [ADR-0017f](../../docs/architecture/decisions/0017f-*.md): 0017F Meta Section

**Components:**

- **Meta Section** → Telemetry
  - File: `k1/l4_runtime/session_state/sections/meta_manager.py`
  - Session duration, turn counts, agent hires, last_active_ms

- **Meta Section** → Performance Metrics
  - File: `k1/l4_runtime/session_state/sections/meta_manager.py`
  - Avg TTFT (P95), avg E2E latency, token usage, incremental averages

- **Meta Section** → Diagnostics
  - File: `k1/l4_runtime/session_state/sections/meta_manager.py`
  - Error rates, retry counts, cache hits, health scores

- **Meta Section** → Prometheus Export
  - File: `k1/l4_runtime/session_state/sections/meta_manager.py`
  - Exposition format, /metrics endpoint, session_id labels, counter/gauge/histogram

- **Meta Section** → Turn Counters
  - File: `k1/l4_runtime/session_state/sections/meta_manager.py`
  - Total turns, successful turns, failed turns, increment <50μs


### Thermal Management

#### [ADR-0026](../../docs/architecture/decisions/0026-*.md): 0026 User Notifications

**Components:**

- **User Notifications** → Emergency Notifications
  - File: `k1/l4_ingress/api_gateway/thermal_notifications.py`
  - "Device cooling down, please wait", WebSocket/SSE event, once per EMERGENCY entry, recovery notification

#### [ADR-0026d](../../docs/architecture/decisions/0026d-*.md): 0026D User Notifications

**Components:**

- **User Notifications** → Emergency Notifications
  - File: `k1/l4_ingress/api_gateway/thermal_notifications.py`
  - "Device cooling down, please wait", WebSocket/SSE event, once per EMERGENCY entry, recovery notification


### Thermal Placement V2

#### [ADR-0077](../../docs/architecture/decisions/0077-*.md): 0077 Thermal Profiling

**Components:**

- **Thermal Profiling** → ThermalProfiler
  - File: `k1/l4_runtime/thermal/profiler.py`
  - Per-device metrics CPU/GPU/NPU/Remote, 100ms sampling, temperature power throttling, 60s rolling window, M3 milestone

- **Thermal Profiling** → ThermalMetrics
  - File: `k1/l4_runtime/thermal/metrics.py`
  - Temperature trend °C/sec, throttling level 0.0-1.0, device state COOL/WARM/HOT/CRITICAL, 30s trajectory prediction

- **Placement Engine** → DevicePlacementScore
  - File: `k1/l4_runtime/thermal/placement_score.py`
  - Composite scoring: 50% thermal 30% workload 20% latency, agent thermal signature, cooldown 30s, ≥85% placement accuracy

- **Placement Engine** → ThermalAwarePlacementEngine
  - File: `k1/l4_runtime/thermal/placement_engine.py`
  - Multi-criteria placement, fallback logic, circuit breaker integration, <50ms P95 placement latency


### Turn Boundary Management

#### [ADR-0054](../../docs/architecture/decisions/0054-*.md): 0054 Main

**Components:**

- **Main** → Turn Boundary Definition
  - File: `k1/l4_ingress/websocket/turn_boundary_detector.py`
  - Point when user input complete, system may respond, dual-signal detection (implicit pause ≥2s OR explicit submit)

- **Main** → Two Signals
  - File: `k1/config/turn_boundary.yml`
  - Implicit pause ≥2s (timer-based text/VAD voice), explicit submit (Enter key/Send button), both equally valid

- **Main** → Turn Boundary State Machine
  - File: `k1/l4_ingress/websocket/turn_state_machine.py`
  - TURN_START → USER_TURN_ACTIVE → TURN_BOUNDARY_DETECTED → AGENT_TURN_ACTIVE → TURN_COMPLETE, deterministic transitions

- **Main** → TURN_START State
  - File: `k1/l4_ingress/websocket/turn_state_machine.py`
  - No active input, system idle, entry on startup/previous complete, exit on first message

- **Main** → USER_TURN_ACTIVE State
  - File: `k1/l4_ingress/websocket/turn_state_machine.py`
  - Messages arriving, pause timer running, exit on pause ≥2s OR explicit submit

- **Main** → TURN_BOUNDARY_DETECTED State
  - File: `k1/l4_ingress/websocket/turn_state_machine.py`
  - <50ms transition state, turn boundary confirmed, ready for agent response

- **Main** → AGENT_TURN_ACTIVE State
  - File: `k1/l4_ingress/websocket/turn_state_machine.py`
  - LLM inference, tool execution, TTS streaming, exit on response complete OR user barge-in

- **Main** → TURN_COMPLETE State
  - File: `k1/l4_ingress/websocket/turn_state_machine.py`
  - <100ms cleanup state, conversation history committed, turn metadata logged, ready for next turn

- **Main** → Turn Boundary Detection Algorithm
  - File: `k1/l4_ingress/websocket/turn_boundary_detector.py`
  - Text: pause timer reset on message, voice: VAD silence detection (energy threshold -50dB)

- **Main** → TurnBoundaryDetector Class
  - File: `k1/l4_ingress/websocket/turn_boundary_detector.py`
  - pause_threshold_sec=2.0, timers dict per session, on_message (reset timer), on_turn_boundary (emit event)

- **Main** → VoiceEndpointDetector Class
  - File: `k1/l4_ingress/voice/voice_endpoint_detector.py`
  - silence_threshold_sec=2.0, energy_threshold_db=-50, VAD energy calculation, silence detection

- **Main** → Turn Boundary Events
  - File: `k1/schemas/flatbuffers/turn_boundary_event.fbs`
  - JSON: session_id, signal_type (implicit_pause/explicit_submit/voice_silence), user_messages, coalesced_text, turn_duration_ms, message_count

- **Main** → Integration with Coalescing
  - File: `k1/l4_ingress/websocket/turn_and_coalesce_manager.py`
  - Same 2s timer shared between turn detection + coalescing, flush on turn boundary, explicit submit triggers both

- **Main** → TurnAndCoalesceManager
  - File: `k1/l4_ingress/websocket/turn_and_coalesce_manager.py`
  - shared_timer dict, coalescer + turn_detector coordination, single timer serves both purposes

- **Main** → MPST Integration
  - File: `k1/l2_orchestrator/protocol_monitor/turn_transitions.py`
  - IDLE → USER_SPEAKING on message, USER_SPEAKING → AGENT_TURN on turn_boundary, AGENT_TURN → IDLE on response_complete

- **Main** → Protocol Validation
  - File: `k1/l2_orchestrator/protocol_monitor/turn_transitions.py`
  - Invalid transitions rejected, timeout enforcement (30s USER_SPEAKING, 60s AGENT_TURN)

- **Main** → Research Foundation
  - File: `docs/research/turn_taking_research.md`
  - Sacks et al. 1974 turn-taking, TRP pauses 0.5-2.5s, Google/Alexa 1.5-2.5s thresholds, natural conversation flow

#### [ADR-0054a](../../docs/architecture/decisions/0054a-*.md): 0054A Implicit Pause

**Components:**

- **Implicit Pause** → 2-Second Pause Threshold
  - File: `k1/config/turn_boundary.yml`
  - Text: stops typing, voice: stops speaking, wait 2s → respond, aligns with natural turn-taking pauses

- **Implicit Pause** → Text Pause Detection
  - File: `k1/l4_ingress/websocket/implicit_pause_detector.py`
  - ImplicitPauseDetector class, pause_threshold_sec=2.0, timer reset on each new message arrival

- **Implicit Pause** → Voice Pause Detection
  - File: `k1/l4_ingress/voice/voice_activity_detector.py`
  - VoiceActivityDetector class, VAD silence detection, energy threshold -50dB, frame_size_ms=20

- **Implicit Pause** → Timer Coordination
  - File: `k1/l4_ingress/websocket/turn_and_coalesce_manager.py`
  - TurnAndCoalesceManager, single shared timer for both turn boundary + message coalescing, consistency guarantee

- **Implicit Pause** → ImplicitPauseDetector Class
  - File: `k1/l4_ingress/websocket/implicit_pause_detector.py`
  - last_message_time dict, pause_timers dict per session, on_message (cancel + restart timer), on_pause_detected (emit turn boundary)

- **Implicit Pause** → VoiceActivityDetector Class
  - File: `k1/l4_ingress/voice/voice_activity_detector.py`
  - silence_threshold_sec=2.0, energy_threshold_db=-50, frame_size_ms=20, silence_start dict, process_frame method

- **Implicit Pause** → VAD Energy Calculation
  - File: `k1/l4_ingress/voice/voice_activity_detector.py`
  - RMS energy in decibels, calculate_energy_db method, numpy processing (frombuffer int16, sqrt mean square, 20*log10)

- **Implicit Pause** → Shared Timer Architecture
  - File: `k1/l4_ingress/websocket/turn_and_coalesce_manager.py`
  - Both turn detection + coalescing use same 2s window, avoids duplicate timers, ensures consistent behavior

- **Implicit Pause** → Edge Cases
  - File: `k1/l4_ingress/websocket/implicit_pause_detector.py`
  - Slow typing >2s between words (separate turn boundaries), voice pauses mid-sentence (ASR buffering), network delay (use timestamps not arrival)

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

- **Explicit Submit** → Explicit Submit Mechanisms
  - File: `k1/l4_ingress/websocket/explicit_submit_handler.py`
  - Enter key (single-line submit), Shift+Enter (multi-line newline), Send button (always available), Cmd/Ctrl+Enter (keyboard shortcut)

- **Explicit Submit** → Text Input Desktop
  - File: `k1/l4_ingress/websocket/explicit_submit_handler.py`
  - Enter key submit (single-line), Shift+Enter submit (multi-line), Send button visual affordance, keyboard shortcuts (Cmd/Ctrl+Enter)

- **Explicit Submit** → Text Input Mobile
  - File: `k1/l4_ingress/websocket/explicit_submit_handler.py`
  - Send button primary (large touch target), keyboard action "Send" key, voice dictation "Send" spoken command

- **Explicit Submit** → Voice Input
  - File: `k1/l4_ingress/voice/voice_submit_handler.py`
  - Spoken commands ("Send"/"Submit"/"That's all"), manual "Stop Listening" button in UI, override VAD silence detection

- **Explicit Submit** → WebSocket Protocol Extension
  - File: `k1/l4_ingress/websocket/protocol_handler.py`
  - is_explicit_submit flag (boolean), submit_method field (enter_key/send_button/keyboard_shortcut/voice_command)

- **Explicit Submit** → UI/UX Contract A
  - File: `k1/ui/send_button_component.py`
  - Send button always visible, bottom-right placement (RTL: bottom-left), enabled when input non-empty, ARIA label "Send message"

- **Explicit Submit** → UI/UX Contract B
  - File: `k1/ui/input_handlers.py`
  - Enter behavior context-aware: single-line input submit, multi-line input newline, Shift+Enter submit multi-line

- **Explicit Submit** → UI/UX Contract C
  - File: `k1/ui/send_button_component.py`
  - Visual feedback: before enabled blue, on submit disabled spinner/loading state, after submit input cleared button disabled

- **Explicit Submit** → UI/UX Contract D
  - File: `k1/ui/mobile_send_button.py`
  - Mobile touch targets: min 44x44pt (iOS), 48x48dp (Android), thumb-reachable zone (bottom 1/3), haptic feedback (light tap vibration)

- **Explicit Submit** → Keyboard Shortcut Specification
  - File: `k1/ui/keyboard_shortcuts.py`
  - Primary Enter/Shift+Enter, alternative Cmd/Ctrl+Enter (submit anywhere), cancel Esc (clear input/cancel draft)

- **Explicit Submit** → Conflict Resolution
  - File: `k1/ui/input_handlers.py`
  - Enter in multi-line always newline (prevent accidental submit), Shift+Enter submits (explicit intent), Cmd/Ctrl+Enter power user preference

- **Explicit Submit** → Voice Command Detection
  - File: `k1/l4_ingress/voice/voice_command_detector.py`
  - English: Send/Submit/That's all/Go ahead, Spanish: Enviar/Mandar/Eso es todo, French: Envoyer/Soumettre/C'est tout, localized phrases

- **Explicit Submit** → ASR Integration
  - File: `k1/l4_ingress/voice/asr_submit_handler.py`
  - Check for submit command in ASR transcript, treat as explicit submit (not user message), submit_method = "voice_command"

- **Explicit Submit** → Implementation Phases
  - File: `docs/implementation/explicit_submit_rollout.md`
  - Phase 1: WebSocket protocol, Phase 2: Desktop UI, Phase 3: Mobile UI, Phase 4: Voice commands

- **Explicit Submit** → UX Tests
  - File: `tests/ui/test_explicit_submit.py`
  - Send button click triggers submit, Enter key triggers submit, Shift+Enter triggers submit, voice "Send" command triggers submit

#### [ADR-0054c](../../docs/architecture/decisions/0054c-*.md): 0054C MPST Transitions

**Components:**

- **MPST Transitions** → Turn-Based State Machine
  - File: `k1/l2_orchestrator/protocol_monitor/turn_protocol_monitor.py`
  - IDLE → USER_SPEAKING → AGENT_TURN → IDLE, deterministic transitions, validation at each step

- **MPST Transitions** → IDLE State
  - File: `k1/l2_orchestrator/protocol_monitor/turn_protocol_monitor.py`
  - No active conversation turn, entry on startup OR previous turn complete, valid events: user_message_start, no timeout (can persist indefinitely)

- **MPST Transitions** → USER_SPEAKING State
  - File: `k1/l2_orchestrator/protocol_monitor/turn_protocol_monitor.py`
  - User actively inputting (typing/speaking), entry on first message, valid events: turn_boundary/more_input, timeout 30s (force turn end)

- **MPST Transitions** → AGENT_TURN State
  - File: `k1/l2_orchestrator/protocol_monitor/turn_protocol_monitor.py`
  - Agent generating response (LLM/tools/TTS), entry on turn_boundary, valid events: response_complete/user_barge_in, timeout 60s (error)

- **MPST Transitions** → State Transition Event 1
  - File: `k1/l2_orchestrator/protocol_monitor/turn_protocol_monitor.py`
  - user_message_start: IDLE → USER_SPEAKING, validation always valid from IDLE, first message arrival triggers

- **MPST Transitions** → State Transition Event 2
  - File: `k1/l2_orchestrator/protocol_monitor/turn_protocol_monitor.py`
  - turn_boundary_detected: USER_SPEAKING → AGENT_TURN, validation ≥1 user message buffered, implicit pause OR explicit submit

- **MPST Transitions** → State Transition Event 3
  - File: `k1/l2_orchestrator/protocol_monitor/turn_protocol_monitor.py`
  - response_complete: AGENT_TURN → IDLE, validation response non-empty, agent finishes generation

- **MPST Transitions** → State Transition Event 4
  - File: `k1/l2_orchestrator/protocol_monitor/turn_protocol_monitor.py`
  - user_barge_in: AGENT_TURN → USER_SPEAKING, abort agent response (ADR-0053c), validation new message from same session

- **MPST Transitions** → TurnProtocolMonitor Class
  - File: `k1/l2_orchestrator/protocol_monitor/turn_protocol_monitor.py`
  - states dict (session_id → State), transition_log (list), transition/is_valid_transition/compute_next_state methods

- **MPST Transitions** → Transition Validation
  - File: `k1/l2_orchestrator/protocol_monitor/turn_protocol_monitor.py`
  - is_valid_transition method, valid_transitions dict per state (IDLE/USER_SPEAKING/AGENT_TURN → allowed events), reject invalid

- **MPST Transitions** → Next State Computation
  - File: `k1/l2_orchestrator/protocol_monitor/turn_protocol_monitor.py`
  - compute_next_state method, transitions dict ((state, event) → next_state), deterministic state machine

- **MPST Transitions** → USER_SPEAKING Timeout
  - File: `k1/l2_orchestrator/protocol_monitor/turn_protocol_monitor.py`
  - 30s timeout force turn boundary if inactive, warning log, automatic transition to AGENT_TURN, prevent hung state

- **MPST Transitions** → AGENT_TURN Timeout
  - File: `k1/l2_orchestrator/protocol_monitor/turn_protocol_monitor.py`
  - 60s timeout error if no agent response, error log, automatic transition to IDLE, send "Request timed out" error to user

- **MPST Transitions** → SessionState Coordination
  - File: `k1/l4_runtime/session_state/protocol_state_sync.py`
  - Update protocol_state field on transition, commit conversation turn on IDLE entry, rollback on failed transition

- **MPST Transitions** → Transition Logging
  - File: `k1/l2_orchestrator/protocol_monitor/turn_protocol_monitor.py`
  - Transition dataclass: session_id, from_state, to_state, event, timestamp, metadata, append to transition_log for debugging

- **MPST Transitions** → TransitionResult
  - File: `k1/l2_orchestrator/protocol_monitor/turn_protocol_monitor.py`
  - success (bool), previous_state, current_state, error (optional), returned by transition method


### Turn History Retention

#### [ADR-0021](../../docs/architecture/decisions/0021-*.md): 0021 Retention Policies

**Components:**

- **Retention Policies** → User Deletion Rights
  - File: `k1/l4_ingress/api_gateway/deletion_api.py`
  - Right to erasure (GDPR Article 17), 30-day grace period, soft delete → hard delete, recovery window

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


### Voice Backpressure

#### [ADR-0057a](../../docs/architecture/decisions/0057a-*.md): 0057A Frame Drop Policy

**Components:**

- **Frame Drop Policy** → Two-Tier Management
  - File: `k1/l4_ingress/voice_pipeline/asr_backpressure.py`
  - Tier 1: 80-90% drop frames, Tier 2: 90%+ downsample, FrameDropPolicy class

- **Frame Drop Policy** → Alternating Drop
  - File: `k1/l4_ingress/voice_pipeline/asr_backpressure.py`
  - AlternatingFrameDrop class, 50% reduction, every other frame, frame_count tracking

- **Frame Drop Policy** → Adaptive Rates
  - File: `k1/l4_ingress/voice_pipeline/asr_backpressure.py`
  - Adaptive drop: 0% <80%, 25% 80-85%, 50% 85-90%, 67% 90%+, load-based

- **Frame Drop Policy** → Downsample Ladder
  - File: `k1/l4_ingress/voice_pipeline/asr_backpressure.py`
  - DownsampleStrategy: 16kHz → 12kHz → 8kHz, anti-aliasing filter scipy.signal.decimate

- **Frame Drop Policy** → Quality Impact
  - File: `k1/l4_ingress/voice_pipeline/asr_backpressure.py`
  - WER degradation: 5% baseline → 8% at 8kHz, quality recovery threshold 0.70

- **Frame Drop Policy** → Frame Metrics
  - File: `k1/l4_ingress/voice_pipeline/asr_backpressure.py`
  - frames_dropped_total, frames_downsampled_total, asr_wer_degradation gauge

#### [ADR-0057b](../../docs/architecture/decisions/0057b-*.md): 0057B TTS Degradation

**Components:**

- **TTS Degradation** → 5-Level Ladder
  - File: `k1/l4_ingress/voice_pipeline/tts_degradation.py`
  - TTSDegradationLadder: Full/High/Medium/Low/Emergency, MOS 4.3→2.7, latency 200ms→80ms

- **TTS Degradation** → Level 0 Full
  - File: `k1/l4_ingress/voice_pipeline/tts_degradation.py`
  - 32 kbps, 24kHz, full prosody, MOS 4.3, 200ms latency, optimal quality

- **TTS Degradation** → Level 1 High
  - File: `k1/l4_ingress/voice_pipeline/tts_degradation.py`
  - 24 kbps, 24kHz, medium prosody, MOS 4.1, 180ms latency, minor degradation

- **TTS Degradation** → Level 2 Medium
  - File: `k1/l4_ingress/voice_pipeline/tts_degradation.py`
  - 24 kbps, 16kHz, low prosody, MOS 3.7, 150ms latency, moderate degradation

- **TTS Degradation** → Level 3 Low
  - File: `k1/l4_ingress/voice_pipeline/tts_degradation.py`
  - 16 kbps, 16kHz, no prosody, MOS 3.2, 100ms latency, high degradation

- **TTS Degradation** → Level 4 Emergency
  - File: `k1/l4_ingress/voice_pipeline/tts_degradation.py`
  - 12 kbps, 8kHz, no prosody, MOS 2.7, 80ms latency, maximum degradation

- **TTS Degradation** → Thermal Awareness
  - File: `k1/l4_ingress/voice_pipeline/tts_degradation.py`
  - Thermal multipliers: COOL 1.0, WARM 1.1, HOT 1.2, CRITICAL 1.3, load-based selection

- **TTS Degradation** → Model Switching
  - File: `k1/l4_ingress/voice_pipeline/tts_degradation.py`
  - ModelSelector: vits_full 500MB, vits_lite 250MB, tacotron2_lite 150MB, hot-swap

- **TTS Degradation** → Quality Monitoring
  - File: `k1/l4_ingress/voice_pipeline/tts_degradation.py`
  - MOS monitoring PESQ, quality transitions 1s/500ms steps, bitrate_changes metrics

#### [ADR-0057c](../../docs/architecture/decisions/0057c-*.md): 0057C Barge-in Preemption

**Components:**

- **Barge-in Preemption** → Detection
  - File: `k1/l4_ingress/voice_pipeline/barge_in.py`
  - BargeInDetector: VAD-based, active_synthesis tracking, user voice during agent synthesis

- **Barge-in Preemption** → Fast Stop
  - File: `k1/l4_ingress/voice_pipeline/barge_in.py`
  - TTSPreemption: 4-step stop <120ms (cancel <20ms, stream <30ms, buffers <20ms, signal <50ms)

- **Barge-in Preemption** → Context Preservation
  - File: `k1/l4_ingress/voice_pipeline/barge_in.py`
  - InterruptedContext: partial_response, completed_sentences, pending_tool_calls, ContextPreserver

- **Barge-in Preemption** → Tool Cancellation
  - File: `k1/l4_ingress/voice_pipeline/barge_in.py`
  - ToolCancellation: cancel_tools method, 1s timeout, tools_cancelled_total metrics

- **Barge-in Preemption** → Recovery Pipeline
  - File: `k1/l4_ingress/voice_pipeline/barge_in.py`
  - BargeInRecovery: 6-step (detect → stop → preserve → cancel → MPST → process)

- **Barge-in Preemption** → Performance SLA
  - File: `k1/l4_ingress/voice_pipeline/barge_in.py`
  - Stop <120ms P95, preserve <50ms, cancel <100ms, barge_in_latency_ms metrics


### Voice Pipeline Implementation

#### [ADR-0056](../../docs/architecture/decisions/0056-*.md): 0056 Pipeline Architecture

**Components:**

- **Pipeline Architecture** → 5-Stage Pipeline
  - File: `k1/l4_runtime/voice_pipeline/pipeline_manager.py`
  - Audio In → ASR (P11) → Intent (K1) → Tools (K1) → TTS (P12) → Audio Out, end-to-end voice interaction flow

- **Pipeline Architecture** → VoicePipelineManager Class
  - File: `k1/l4_runtime/voice_pipeline/pipeline_manager.py`
  - asr_pipeline (K0ASRPipeline), tts_pipeline (K0TTSPipeline), k1_orchestrator, handle_voice_session method (full-duplex WebSocket)

- **Pipeline Architecture** → Full-Duplex WebSocket
  - File: `k1/l4_runtime/voice_pipeline/websocket_handler.py`
  - Bidirectional coordination: inbound (Audio → ASR → Intent → K1), outbound (K1 → TTS → Audio), async tasks

- **Pipeline Architecture** → Inbound Pipeline
  - File: `k1/l4_runtime/voice_pipeline/inbound_handler.py`
  - Audio input → Transcript: asr_pipeline.process (audio_chunk, session_id, return_partials=True), emit_partial for streaming, classify_intent on final transcript

- **Pipeline Architecture** → Outbound Pipeline
  - File: `k1/l4_runtime/voice_pipeline/outbound_handler.py`
  - Response → Audio output: k1_orchestrator.response_stream → tts_pipeline.synthesize_streaming (text, prosody, session_id) → send_bytes audio chunks

- **Pipeline Architecture** → Intent Bridge
  - File: `k1/l3_execution/intent_classifier/voice_intent_bridge.py`
  - k1_orchestrator.classify_intent (transcript.text), stateless advisory classification (ADR-0021 integration)

- **Performance Budgets** → Intent Classification Latency
  - File: `k1/config/intent_classifier.yml`
  - intent_classification_ms: 50 (P95 target, ADR-0021 alignment)

- **Performance Budgets** → E2E Voice Turn
  - File: `k1/config/voice_pipeline.yml`
  - e2e_voice_turn_ms: 500 (P95 target: user stops speaking → agent starts speaking)

- **Performance Budgets** → Throughput Targets
  - File: `k1/config/voice_pipeline.yml`
  - asr_frames_per_sec: 50 (20ms frames = 50 FPS), tts_audio_chunks_per_sec: 25 (40ms chunks = 25 CPS), concurrent_voice_sessions: 50 per K1 instance

- **Error Handling** → ASR Errors
  - File: `k1/l4_runtime/voice_pipeline/error_handlers.py`
  - If asr_confidence < 0.3: send_clarification "Sorry, I didn't catch that. Could you repeat?"

- **Error Handling** → Intent Errors
  - File: `k1/l4_runtime/voice_pipeline/error_handlers.py`
  - If intent.confidence < 0.5: request_clarification (ADR-0003b clarification protocol)

- **Error Handling** → TTS Errors
  - File: `k1/l4_runtime/voice_pipeline/error_handlers.py`
  - Try synthesize, catch TTSError, fallback send text response: {"type": "text_fallback", "text": text, "reason": "tts_unavailable"}

- **Integration Points** → Turn Boundary Detection
  - File: `k1/l2_orchestrator/protocol_monitor/turn_protocol_monitor.py`
  - ADR-0054 VAD 2s silence → implicit turn boundary, voice "Send" command → explicit turn boundary, shared timer with message coalescing

- **Integration Points** → Backpressure Cascade
  - File: `k1/l5_infrastructure/backpressure/cascade_manager.py`
  - ADR-0039 ADR-0057: ASR frame drop at 80% capacity, TTS degradation at 90% capacity, barge-in preemption support

- **Integration Points** → Tool Interleaving
  - File: `k1/l4_runtime/voice_pipeline/tool_interleaver.py`
  - ADR-0056c: Execute tools while streaming TTS, insert tool results mid-stream, handle tool timeouts gracefully

- **Metrics** → Intent Metrics
  - File: `observability/metrics/voice_pipeline_metrics.py`
  - voice_intent_confidence histogram (buckets 0.3/0.5/0.7/0.8/0.9/1.0), K1 owner

- **Metrics** → E2E Metrics
  - File: `observability/metrics/voice_pipeline_metrics.py`
  - voice_turn_e2e_latency_ms histogram (buckets 200/500/1000/2000/5000), end-to-end voice turn latency

- **Intent Bridge** → Voice Intent Classification
  - File: `k1/l3_execution/intent_classifier/voice_intent_classifier.py`
  - ADR-0056b: Voice-specific intent classification, acoustic features integration, confidence threshold 0.8

- **Intent Bridge** → Confidence Tuning
  - File: `k1/l3_execution/intent_classifier/confidence_tuner.py`
  - ADR-0056b: Voice confidence calibration, ASR confidence multiplier, threshold adjustment for voice vs text

- **Intent Bridge** → DM Router Integration
  - File: `k1/l2_orchestrator/routing/dm_router.py`
  - ADR-0056b: Route voice intents to dialogue manager, voice-specific routing rules, fallback to text mode

- **Tool Interleaving** → Parallel Execution
  - File: `k1/l3_execution/tools/parallel_tool_executor.py`
  - ADR-0056c: Execute tools while streaming TTS, up to 3 parallel tools, task coordination

- **Tool Interleaving** → Result Streaming
  - File: `k1/l3_execution/tools/result_streamer.py`
  - ADR-0056c: Stream tool results as they complete, insert results mid-TTS, result prioritization

- **Tool Interleaving** → Timeout Handling
  - File: `k1/l3_execution/tools/timeout_manager.py`
  - ADR-0056c: Tool timeout policy (3s default), graceful degradation, partial result handling

- **Audio Output** → Device Handshake
  - File: `k1/l4_runtime/voice_pipeline/device_manager.py`
  - ADR-0056e: WebSocket device capability negotiation, codec selection (opus/pcm), sample rate agreement

- **Audio Output** → Codec Negotiation
  - File: `k1/l4_runtime/voice_pipeline/codec_negotiator.py`
  - ADR-0056e: Opus codec (default), PCM fallback, bitrate selection (16-64 kbps), sample rate (8/16/48 kHz)

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

#### [ADR-0056b](../../docs/architecture/decisions/0056b-*.md): 0056B Intent Bridge

**Components:**

- **Intent Bridge** → Voice Intent Classification
  - File: `k1/l3_execution/intent_classifier/voice_intent_classifier.py`
  - ADR-0056b: Voice-specific intent classification, acoustic features integration, confidence threshold 0.8

- **Intent Bridge** → Confidence Tuning
  - File: `k1/l3_execution/intent_classifier/confidence_tuner.py`
  - ADR-0056b: Voice confidence calibration, ASR confidence multiplier, threshold adjustment for voice vs text

- **Intent Bridge** → DM Router Integration
  - File: `k1/l2_orchestrator/routing/dm_router.py`
  - ADR-0056b: Route voice intents to dialogue manager, voice-specific routing rules, fallback to text mode

#### [ADR-0056c](../../docs/architecture/decisions/0056c-*.md): 0056C Tool Interleaving

**Components:**

- **Tool Interleaving** → Parallel Execution
  - File: `k1/l3_execution/tools/parallel_tool_executor.py`
  - ADR-0056c: Execute tools while streaming TTS, up to 3 parallel tools, task coordination

- **Tool Interleaving** → Result Streaming
  - File: `k1/l3_execution/tools/result_streamer.py`
  - ADR-0056c: Stream tool results as they complete, insert results mid-TTS, result prioritization

- **Tool Interleaving** → Timeout Handling
  - File: `k1/l3_execution/tools/timeout_manager.py`
  - ADR-0056c: Tool timeout policy (3s default), graceful degradation, partial result handling

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

- **Audio Output** → Device Handshake
  - File: `k1/l4_runtime/voice_pipeline/device_manager.py`
  - ADR-0056e: WebSocket device capability negotiation, codec selection (opus/pcm), sample rate agreement

- **Audio Output** → Codec Negotiation
  - File: `k1/l4_runtime/voice_pipeline/codec_negotiator.py`
  - ADR-0056e: Opus codec (default), PCM fallback, bitrate selection (16-64 kbps), sample rate (8/16/48 kHz)

- **Audio Output** → Buffer Management
  - File: `k0/pipelines/p12_tts/audio_buffer_manager.py`
  - ADR-0056e: Jitter buffer (80ms), frame reordering, packet loss recovery, adaptive buffering


### WebSocket Binary Protocol

#### [ADR-0015](../../docs/architecture/decisions/0015-*.md): 0015 Protocol Design

**Components:**

- **Protocol Design** → Binary Protocol Strategy
  - File: `k1/l4_ingress/websocket_gateway/protocol.py`
  - FlatBuffers-only, zero-copy, 5-10× faster than JSON, 30-50% smaller payloads

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

#### [ADR-0015a](../../docs/architecture/decisions/0015a-*.md): 0015A Message Routing

**Components:**

- **Message Routing** → Envelope Router
  - File: `k1/l4_ingress/websocket_gateway/envelope_router.py`
  - EnvelopeRouter, hash table routing <1ms, 17 handlers, async dispatch

- **Message Routing** → Sequence Tracker
  - File: `k1/l4_ingress/websocket_gateway/sequence_tracker.py`
  - SequenceTracker, monotonic seqno, gap detection <10, duplicate prevention

- **Message Routing** → Frame Validator
  - File: `k1/l4_ingress/websocket_gateway/frame_validator.py`
  - FrameValidator, magic number FBWS, schema identifier MENV, <0.5ms P95

- **Message Routing** → Error Handler
  - File: `k1/l4_ingress/websocket_gateway/error_handler.py`
  - ErrorHandler, ERROR message, close connection, 6 error codes

- **Protocol Design** → Message Envelope
  - File: `k1/schemas/websocket/message_envelope.fbs`
  - MessageEnvelope, 17 message types, protocol_version, sequence_number, trace_id

- **Protocol Design** → Message Types
  - File: `k1/schemas/websocket/message_types.fbs`
  - TURN_START, TOKEN_CHUNK, TOOL_CALL, BARGE_IN, PING/PONG (17 types)

#### [ADR-0015b](../../docs/architecture/decisions/0015b-*.md): 0015B Flow Control

**Components:**

- **Flow Control** → Window-Based Control
  - File: `k1/l4_ingress/websocket_gateway/flow_control.py`
  - FlowControlManager, window size 10, unacked tracking, adaptive 5-50

- **Flow Control** → Send Buffer
  - File: `k1/l4_ingress/websocket_gateway/send_buffer.py`
  - SendBuffer, LIFO queue, max 100 messages, drop oldest on overflow

- **Flow Control** → Backpressure Manager
  - File: `k1/l4_ingress/websocket_gateway/backpressure_manager.py`
  - BackpressureManager, cascade upstream K1 kernel, <50ms propagation

- **Flow Control** → Adaptive Window Sizing
  - File: `k1/l4_ingress/websocket_gateway/flow_control.py`
  - Adjust window based on RTT (<50ms fast→50, >200ms slow→5)

- **Flow Control** → ACK Protocol
  - File: `k1/schemas/websocket/ack.fbs`
  - ACK message, ack_seqno, batch 5 messages or 1s, <5% overhead

- **Flow Control** → ACK Manager Client
  - File: `sdk/typescript/ack_manager.ts`
  - AckManager, batched ACKs, unackedCount, lastAckTime tracking

#### [ADR-0015c](../../docs/architecture/decisions/0015c-*.md): 0015C Reconnection

**Components:**

- **Reconnection** → Message Buffer
  - File: `k1/l4_ingress/websocket_gateway/message_buffer.py`
  - MessageBuffer, circular 1000 messages, replay on reconnect, 10MB per session

- **Reconnection** → Session Manager
  - File: `k1/l4_ingress/websocket_gateway/session_manager.py`
  - SessionManager, 60s timeout, cleanup task 10s interval, session state

- **Reconnection** → Resume Handler
  - File: `k1/l4_ingress/websocket_gateway/resume_handler.py`
  - ResumeHandler, RESUME message, message replay, <5s reconnect target

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

- **Streaming** → Token Streaming
  - File: `k1/l4_ingress/websocket_gateway/streaming_handler.py`
  - StreamingHandler, TOKEN_CHUNK delivery, async generator, <50ms P95

- **Streaming** → Barge-In Handler
  - File: `k1/l4_ingress/websocket_gateway/barge_in_handler.py`
  - BargeInHandler, interrupt flag, <120ms P95, STOP/INTERRUPT_WITH_NEW_TURN

- **Streaming** → Heartbeat Manager
  - File: `k1/l4_ingress/websocket_gateway/heartbeat_manager.py`
  - HeartbeatManager, PING/PONG 30s, 10s timeout, RTT measurement

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


### WebSocket Realtime Chat

#### [ADR-0037](../../docs/architecture/decisions/0037-*.md): 0037 Horizontal Scaling

**Components:**

- **Connection Management** → JWT Authentication
  - File: `k1/l4_ingress/websocket/connection/auth.py`
  - JWT in query param or Sec-WebSocket-Protocol header, RS256 signature validation, extract claims (user_id/session_id/space_id), <50ms validation, reject 403 if invalid

#### [ADR-0040](../../docs/architecture/decisions/0040-*.md): 0040 Protocol Foundation

**Components:**

- **Protocol Foundation** → RFC 6455 Full-Duplex
  - File: `k1/l4_ingress/websocket/protocol.py`
  - Bidirectional single TCP connection, <200ms TTFT streaming, HTTP Upgrade handshake (101 Switching Protocols), WebSocket frames (RFC 6455 §5.2)

- **Protocol Foundation** → Performance vs Alternatives
  - File: `k1/l4_ingress/websocket/comparison.py`
  - 5-25× faster than HTTP polling (1-5s → <200ms), full-duplex vs SSE (unidirectional), 2× bandwidth efficiency (FlatBuffers vs JSON), single auth vs 120 req/min

- **Binary Serialization** → FlatBuffers Protocol
  - File: `k1/l4_ingress/websocket/flatbuffers/`
  - 17 message types (Connection/Conversation/User/Agent/Tool/Clarification/Error), 2× smaller than JSON, <1ms serialization (10× faster), zero-copy deserialization

- **Binary Serialization** → Delta-Based Streaming
  - File: `k1/l4_ingress/websocket/streaming.py`
  - AgentMessageChunk with text_delta (only new tokens), 90% bandwidth reduction (vs full text), token-by-token appearance, <200ms TTFT

#### [ADR-0040a](../../docs/architecture/decisions/0040a-*.md): 0040A Connection Management

**Components:**

- **Connection Management** → HTTP to WebSocket Upgrade
  - File: `k1/l4_ingress/websocket/connection/upgrade.py`
  - HTTP GET with Upgrade header, Sec-WebSocket-Key/Accept handshake, 101 Switching Protocols response, <500ms establishment

- **Connection Management** → JWT Authentication
  - File: `k1/l4_ingress/websocket/connection/auth.py`
  - JWT in query param or Sec-WebSocket-Protocol header, RS256 signature validation, extract claims (user_id/session_id/space_id), <50ms validation, reject 403 if invalid

- **Connection Management** → Connection Registry
  - File: `k1/l4_ingress/websocket/connection/registry.py`
  - In-memory HashMap (session_id → WebSocketConnection), WebSocketConnection struct (session_id/user_id/tx channel/last_heartbeat), Arc<RwLock<HashMap>> thread-safe

- **Connection Management** → TLS 1.3 Encryption
  - File: `k1/l4_ingress/websocket/connection/tls.py`
  - wss:// protocol (WebSocket Secure), valid SSL certificate, TLS_AES_256_GCM_SHA384 cipher, <200ms TLS handshake

- **Connection Management** → Graceful Disconnect
  - File: `k1/l4_ingress/websocket/connection/disconnect.py`
  - RFC 6455 close codes (1000 normal, 1008 policy violation, 1011 server error), Goodbye message before close, connection registry cleanup

#### [ADR-0040b](../../docs/architecture/decisions/0040b-*.md): 0040B Binary Serialization

**Components:**

- **Binary Serialization** → FlatBuffers Protocol
  - File: `k1/l4_ingress/websocket/flatbuffers/`
  - 17 message types (Connection/Conversation/User/Agent/Tool/Clarification/Error), 2× smaller than JSON, <1ms serialization (10× faster), zero-copy deserialization

- **Binary Serialization** → Delta-Based Streaming
  - File: `k1/l4_ingress/websocket/streaming.py`
  - AgentMessageChunk with text_delta (only new tokens), 90% bandwidth reduction (vs full text), token-by-token appearance, <200ms TTFT

- **Message Framing** → 17 Message Types
  - File: `k1/l4_ingress/websocket/messages/`
  - Connection (ConnectionEstablished/Heartbeat/HeartbeatAck/RefreshToken/Disconnect/Goodbye), Conversation (StartConversation/ConversationCreated/SwitchConversation/CloseConversation/ConversationClose...

- **Message Framing** → Message Routing
  - File: `k1/l4_ingress/websocket/router.py`
  - Route by message type enum, handler per type, type-safe deserialization, <0.1ms routing latency

- **Message Framing** → Schema Evolution
  - File: `k1/l4_ingress/websocket/schema/`
  - FlatBuffers backward/forward compatibility, add fields without breaking clients, versioned schemas

#### [ADR-0040c](../../docs/architecture/decisions/0040c-*.md): 0040C Backpressure Flow Control

**Components:**

- **Backpressure Flow Control** → Async Message Queue
  - File: `k1/l4_ingress/websocket/backpressure/queue.py`
  - mpsc::channel with 100 capacity, bounded queue (prevents infinite growth), non-blocking send (agent doesn't wait), <1ms queue insert

- **Backpressure Flow Control** → Slow Client Handling
  - File: `k1/l4_ingress/websocket/backpressure/flow_control.py`
  - Monitor queue depth, warning at 90% full (90 messages), drop strategy: drop oldest messages (FIFO), prevents server OOM

- **Backpressure Flow Control** → Message Buffering
  - File: `k1/l4_ingress/websocket/backpressure/buffer.py`
  - Buffer last 100 messages (5-minute TTL), used for reconnection (client requests missed messages), evict messages older than 5 minutes

- **Backpressure Flow Control** → TTFT Streaming
  - File: `k1/l4_ingress/websocket/backpressure/streaming_engine.py`
  - <200ms time to first token (P95), token-by-token streaming (delta-based), measure latency per token, Prometheus metrics

#### [ADR-0040d](../../docs/architecture/decisions/0040d-*.md): 0040D Heartbeat Reconnection

**Components:**

- **Heartbeat Reconnection** → Ping/Pong Mechanism
  - File: `k1/l4_ingress/websocket/heartbeat/ping_pong.py`
  - 30s interval heartbeat, server sends Ping (Heartbeat message), client sends Pong (HeartbeatAck message), RFC 6455 §5.5.2 frames

- **Heartbeat Reconnection** → Connection Health Monitoring
  - File: `k1/l4_ingress/websocket/heartbeat/health.py`
  - 90s timeout threshold (3× heartbeat interval), close connection if no HeartbeatAck after 90s, detect network failures and zombie connections

- **Heartbeat Reconnection** → Auto-Reconnect
  - File: `k1/l4_ingress/websocket/heartbeat/reconnect.py`
  - Exponential backoff (1s, 2s, 4s, 8s, 16s max), max 5 attempts (stop after 31s), include last_message_id in reconnect request, >95% success rate

- **Heartbeat Reconnection** → Missed Message Replay
  - File: `k1/l4_ingress/websocket/heartbeat/replay.py`
  - Client sends last_message_id on reconnect, server replays buffered messages (last 100, 5-minute TTL from ADR-0040c), 0 lost messages on reconnect


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