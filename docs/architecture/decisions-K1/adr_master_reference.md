
# K1 Intelligence Module - ADR Master Reference

**Last Updated:** 2025-10-23
**Total ADRs:** 0001-0086 + sub-ADRs across ADR-001 to ADR-0086
**Status:** Complete catalog of all architectural decisions with Layer 5 extensibility

---

## Purpose

This document serves as the **master index** for all Architecture Decision Records (ADRs) in the K1 Intelligence Module project. **ALL development work must reference relevant ADRs before implementation.**

---

## 🚨 CRITICAL RULE FOR ALL DEVELOPMENT 🚨

**BEFORE writing ANY code, documentation, or making architectural changes:**

1. ✅ **READ relevant ADRs first** - Understand existing decisions
2. ✅ **Check for conflicts** - Ensure your changes align with ADRs
3. ✅ **Reference ADR numbers** - Link to ADRs in code comments and PRs
4. ✅ **Update or create ADRs** - Document new architectural decisions

**NO CODE WITHOUT ADR REVIEW - This is mandatory governance.**

---

## ADR Categories & Quick Reference

### 🏗️ Foundational Architecture (0001-0004)

| ADR | Title | Status | Key Decision |
|-----|-------|--------|--------------|
| **0001** | K0/K1 Kernel Split Architecture | ✅ Accepted | Dual-kernel microkernel: K0 (memory) + K1 (intelligence) |
| **0001a** | K0 Bridge Communication Protocol | ✅ Approved | Dual protocol: JSON (primary) + FlatBuffers (optimization) |
| **0001b** | Model Hub Architecture & LLM Integration | 🔄 In Progress | LLM integration layer for AI agents |
| **0001e** | P21+ Integration Pipeline Layer | ✅ Completed | Integration pipeline architecture |
| **0001f** | State Boundary Management (K1 vs K0) | ✅ Completed | Clear state boundaries between kernels |
| **0002** | Actor Model for Agent Isolation | ✅ Accepted | ALL agents use Actor Model for concurrency |
| **0002a** | Mailbox MPSC Queue Implementation | ✅ Completed | Message-passing queue implementation |
| **0002b** | Supervisor Monitoring & Crash Recovery | ✅ Completed | Supervision trees for fault tolerance |
| **0002c** | Actor Router & Admission Control | ✅ Completed | Message routing and load management |
| **0002d** | Observability Schema for Actor Messaging | ✅ Completed | Actor metrics and tracing |
| **0003** | MPST Protocol Validation | ✅ Accepted | Multiparty session types for protocol safety |
| **0003a** | Protocol Definition Language (PDL) | ✅ Completed | Protocol specification language |
| **0003b** | 6 Core Protocol Implementations | ✅ Completed | Agent Hire, Task Execution, Clarification, Barge-In, Tool Call, Saga Rollback |
| **0003c** | Protocol Monitor Runtime | ✅ Completed | Runtime protocol validation engine |
| **0003d** | Role Attestation & Capability Verification | ✅ Completed | Role-based security enforcement |
| **0004** | 52-Module 5-Layer Microkernel | ✅ Accepted | Layer 1 (Kernel) → Layer 5 (Infrastructure) |
| **0004a** | Layer 1-2 Event Bus Communication | ✅ Completed | Inter-layer messaging pattern |
| **0004b** | Module Dependency Management | ✅ Completed | Import linting and dependency control |
| **0004c** | Module README Template | ✅ Completed | Auto-generated module documentation |
| **0004d** | Per-Layer Integration Testing | ✅ Completed | Layer-specific test strategies |

---

### 🤖 Agent Lifecycle & Orchestration (0005-0006)

| ADR | Title | Status | Key Decision |
|-----|-------|--------|--------------|
| **0005** | Agent Lifecycle FSM (6 States) | ✅ Accepted | PENDING → WARMING → ACTIVE → IDLE → DRAINING → TERMINATED |
| **0005a** | Agent WARMING State | ✅ Completed | Model preloading, KV cache warming |
| **0005b** | Agent IDLE Pooling | ✅ Accepted | Fast reactivation from idle pool |
| **0005c** | Agent DRAINING & Graceful Shutdown | ✅ Accepted | Graceful task completion before termination |
| **0005d** | Supervisor Monitoring & Blacklist | ✅ Accepted | Health checks, crash detection, blacklisting |
| **0005e** | Agent Personality & Capability System | ✅ Accepted | Persona prompts + capability tokens |
| **0006** | 3-Phase Orchestration (Contract Net) | ✅ Accepted | Negotiation → Selection → Execution |
| **0006a** | Contract Net Protocol Negotiation | ✅ Accepted | Task announcement, proposal bidding |
| **0006b** | Multi-Criteria Proposal Scoring | ✅ Accepted | Capability, latency, cost, specialization scoring |
| **0006c** | Parallel DAG Execution | ✅ Accepted | Concurrent task execution with dependencies |
| **0006d** | Saga Pattern Integration | ✅ Accepted | Error recovery with compensating transactions |
| **0006e** | Multi-Agent Parallel Coordination | ✅ Accepted | Future: multi-agent collaboration |

---

### 📝 Planning Pipeline (0007)

| ADR | Title | Status | Key Decision |
|-----|-------|--------|--------------|
| **0007** | 4-Stage Planning Pipeline | ✅ Accepted | Sketch → Expand → Validate → Commit |
| **0007a** | Sketch Stage LLM Prompt Engineering | ✅ Approved | LLM-powered plan sketching |
| **0007b** | Expand Stage Tool/Prompt Registry | ✅ Approved | Tool selection and prompt templates |
| **0007c** | Validation Stage 2-Tier Implementation | ✅ Approved | Rule-based + arbiter validation |
| **0007d** | Commit Stage K0 WAL Integration | ✅ Approved | Plan persistence to K0 storage |

---

### 🔄 Error Recovery & Resilience (0008-0009)

| ADR | Title | Status | Key Decision |
|-----|-------|--------|--------------|
| **0008** | Saga Pattern for Error Recovery | ✅ Accepted | Compensating transactions for rollback |
| **0008a** | Compensating Transaction Design | ✅ Approved | Idempotent compensation handlers |
| **0008b** | Forward vs Backward Recovery | ✅ Approved | Recovery strategy selection |
| **0008c** | Distributed State Management | ✅ Approved | State tracking across agents |
| **0008d** | Timeout & Deadlock Handling | ✅ Approved | Timeout enforcement, deadlock detection |
| **0009** | Circuit Breaker Pattern | ✅ Accepted | Cascading failure prevention |
| **0009a** | Circuit Breaker 3-State FSM | ✅ Accepted | CLOSED → OPEN → HALF_OPEN |
| **0009b** | Per-Service Circuit Configuration | ✅ Accepted | Service-specific thresholds |
| **0009c** | Circuit Breaker Metrics | ✅ Accepted | Observability and alerting |

---

### 🔐 Security & Capabilities (0010, 0032-0038)

| ADR | Title | Status | Key Decision |
|-----|-------|--------|--------------|
| **0010** | Capability-Based Security | ✅ Accepted | Unforgeable tokens, least privilege |
| **0010a** | Capability Token Design & Lifecycle | ✅ Accepted | Token generation, expiry, revocation |
| **0010b** | Agent Capability Assignment Policy | ✅ Accepted | Role-based capability distribution |
| **0010c** | Capability Enforcement at Runtime | ✅ Accepted | Runtime capability checks |
| **0010d** | Capability Revocation & Audit Trail | ✅ Accepted | Revocation logging and auditing |
| **0032** | Band-Based Egress Rules | ✅ Approved | GREEN/AMBER/RED privacy bands |
| **0032a** | Network Egress Control (iptables) | ✅ Approved | Network-level band enforcement |
| **0032b** | Filesystem Egress Control (chroot) | ✅ Approved | Filesystem sandboxing |
| **0032c** | Resource Egress Control (cgroups) | ✅ Approved | Resource isolation |
| **0032d** | Egress Violation Logging | ✅ Approved | Security audit trail |
| **0033** | Tool Execution Architecture | ✅ Approved | Protocol + Sandbox layers |
| **0033a** | MCP Protocol Integration | ✅ Approved | Model Context Protocol Layer 1 |
| **0033b** | WASM Sandbox Implementation | ✅ Approved | WebAssembly sandboxing Layer 2 |
| **0033c** | Process Sandbox Implementation | ✅ Approved | OS-level process sandboxing |
| **0033d** | 2D Selection Logic | ✅ Approved | Protocol × Sandbox selection matrix |
| **0034** | MCP Protocol for Tool Integration | ✅ Approved | MCP standard for tool execution |
| **0034a** | MCP JSON-RPC 2.0 Protocol | ⏳ Pending | JSON-RPC implementation |
| **0034b** | MCP Process Lifecycle | ⏳ Pending | Process management and timeouts |
| **0034c** | MCP Circuit Breaker Integration | ⏳ Pending | Circuit breaker for MCP tools |
| **0034d** | MCP Error Handling & Recovery | ⏳ Pending | Error recovery strategies |
| **0035** | PII Detection & Redaction | ✅ Approved | Automated PII protection |
| **0035a** | Regex Pattern Library | ⏳ Pending | Structured PII detection |
| **0035b** | ML-based NER | ⏳ Pending | Unstructured PII detection |
| **0035c** | Encrypted PII Vault | ⏳ Pending | Secure PII storage |
| **0035d** | Audit Trail & GDPR Compliance | ⏳ Pending | GDPR compliance logging |
| **0036** | E2EE for RED Band | ✅ Approved | End-to-end encryption for sensitive data |
| **0036a** | AES-256-GCM Encryption | ⏳ Pending | Encryption implementation |
| **0036b** | KMS Integration & Key Lifecycle | ⏳ Pending | Key management system |
| **0036c** | Selective Encryption & SessionState | ⏳ Pending | Field-level encryption |
| **0036d** | Audit Trail & Compliance | ⏳ Pending | Encryption audit logging |
| **0037** | JWT Authentication | ✅ Approved | Token-based authentication |
| **0037a** | Token Generation & Signing | ⏳ Pending | JWT generation |
| **0037b** | Token Validation & Verification | ⏳ Pending | JWT validation |
| **0037c** | Refresh Token Flow & Rotation | ⏳ Pending | Token refresh mechanism |
| **0037d** | Session Binding & Authorization | ⏳ Pending | Session-level authorization |
| **0038** | Audit Trail to K0 Receipts | ✅ Approved | Immutable audit logging |
| **0038a** | Receipt Generation & Schema | ⏳ Pending | Receipt schema design |
| **0038b** | K0 WAL Integration & Async Writes | ⏳ Pending | Asynchronous receipt persistence |
| **0038c** | Retention Policies & Auto-Deletion | ⏳ Pending | Receipt retention management |
| **0038d** | Query Interface & Compliance Export | ⏳ Pending | Receipt query API |

---

### 📦 Serialization & Data Formats (0011-0016)

| ADR | Title | Status | Key Decision |
|-----|-------|--------|--------------|
| **0011** | FlatBuffers for All K1 Serialization | ✅ Accepted | Zero-copy binary serialization |
| **0011a** | FlatBuffers Schema Design Principles | ✅ Accepted | Schema design guidelines |
| **0011b** | FlatBuffers Code Generation | ✅ Accepted | Build-time code generation |
| **0011c** | Serialization Performance & Zero-Copy | ✅ Accepted | <1ms serialization target |
| **0011d** | Schema Evolution & Versioning | ✅ Accepted | Backward/forward compatibility |
| **0012** | 76 FlatBuffers Schemas | ✅ Accepted | Complete type system |
| **0012a** | Layer 1 Core Kernel Schemas (15) | ✅ Accepted | Agent, Task, Protocol schemas |
| **0012b** | Layer 2 State & Persistence (18) | ✅ Accepted | SessionState, Receipt schemas |
| **0012c** | Layer 3 Execution & Tools (16) | ✅ Accepted | Tool, MCP, Sandbox schemas |
| **0012d** | Layer 4 Ingress & Voice (14) | ✅ Accepted | WebSocket, Voice schemas |
| **0012e** | Layer 5 Infrastructure (13) | ✅ Accepted | Config, Metrics, Thermal schemas |
| **0013** | Pipeline Versioning Policy | ✅ Accepted | Semantic versioning + 90-day deprecation |
| **0013a** | Schema Version Registry | ✅ Accepted | Compatibility matrix |
| **0013b** | Automated Version Bump Validation | ✅ Accepted | CI/CD version checks |
| **0013c** | 90-Day Deprecation Workflow | ✅ Accepted | Deprecation notifications |
| **0013d** | Contract Testing & Validation | ✅ Accepted | Schema compatibility tests |
| **0014** | JSON for REST API (Dual Format) | ✅ Accepted | JSON + FlatBuffers support |
| **0014a** | Content Negotiation Middleware | ✅ Accepted | Format detection |
| **0014b** | OpenAPI 3.1 Spec Generation | ✅ Accepted | Auto-generated API docs |
| **0014c** | Request/Response Serialization | ✅ Accepted | Serialization pipeline |
| **0014d** | Client SDK Examples & Migration | ✅ Accepted | Client SDK documentation |
| **0015** | WebSocket Binary Protocol | ✅ Accepted | FlatBuffers over WebSocket |
| **0015a** | WebSocket Message Envelope | ✅ Accepted | Message routing schema |
| **0015b** | Flow Control & Backpressure | ✅ Accepted | Backpressure propagation |
| **0015c** | Reconnection & Session Resume | ✅ Accepted | Stateful reconnection |
| **0015d** | Streaming Token Delivery | ✅ Accepted | Real-time token streaming |
| **0015e** | TypeScript Client SDK | ✅ Accepted | Browser WebSocket client |
| **0016** | SSE Event Schemas (17 Types) | ✅ Accepted | Server-Sent Events |
| **0016a** | SSE Event Taxonomy | ⏳ In Progress | Event type definitions |
| **0016b** | FlatBuffers-to-JSON for SSE | ⏳ In Progress | SSE serialization |
| **0016c** | SSE Topic-Based Filtering | ⏳ In Progress | Event subscriptions |
| **0016d** | Browser EventSource Integration | ⏳ In Progress | Browser SSE client |

---

### 💾 SessionState & Storage (0017-0023)

| ADR | Title | Status | Key Decision |
|-----|-------|--------|--------------|
| **0017** | SessionState 6-Section Design | ✅ Accepted | Beliefs, Scoreboard, Control, Persona, Multimodal, Meta |
| **0017a** | Beliefs Section | ⏳ In Progress | User facts & preferences |
| **0017b** | Scoreboard Section | ⏳ In Progress | Common ground & QUD |
| **0017c** | Control Section | ⏳ In Progress | Agent leases & flow state |
| **0017d** | Persona Section | ⏳ In Progress | Personality model & style |
| **0017e** | Multimodal Section | ⏳ In Progress | Audio/vision state |
| **0017f** | Meta Section | ⏳ In Progress | Telemetry & metrics |
| **0018** | 3-Tier Eviction Strategy | ✅ Accepted | Soft → Hard → OOM Prevention |
| **0018a** | Tier 1 Soft Eviction (64KB → 80KB) | ⏳ In Progress | Gentle eviction |
| **0018b** | Tier 2 Hard Eviction (128KB → 192KB) | ⏳ In Progress | Aggressive eviction |
| **0018c** | Tier 3 OOM Prevention (256KB Kill) | ⏳ In Progress | Hard limit enforcement |
| **0019** | FlatBuffers SessionState Serialization | ✅ Accepted | <1ms serialization |
| **0019a** | SessionState FlatBuffers Schema | ⏳ In Progress | Schema definition |
| **0019b** | Delta Serialization Pipeline | ⏳ In Progress | <1ms delta serialization |
| **0019c** | K0 WAL Integration | ⏳ In Progress | Checkpoint every 5 minutes |
| **0019d** | Zero-Copy Deserialization | ⏳ In Progress | Performance optimization |
| **0020** | Multi-Tier Storage (Hot/Warm/Cold) | ✅ Accepted | L1 RAM → L2 SSD → L3 S3 |
| **0020a** | Hot Tier (L1 RAM) | ⏳ In Progress | In-memory SessionState |
| **0020b** | Warm Tier (L2 SSD) | ⏳ In Progress | K0 WAL storage |
| **0020c** | Cold Tier (L3 Object Storage) | ⏳ In Progress | S3 archive |
| **0021** | Turn History Retention Policies | ✅ Accepted | Lifecycle management |
| **0021a** | Retention Policy Engine | ⏳ In Progress | Lifecycle rules |
| **0021b** | Privacy Band Retention Overrides | ⏳ In Progress | Band-specific retention |
| **0021c** | Compliance Reporting & Audit | ⏳ In Progress | Audit trail |
| **0022** | K0 Bridge Bounded Batching | ✅ Accepted | 10-50 messages, 100ms timeout |
| **0022a** | Batching Algorithm | ⏳ In Progress | Batch optimization |
| **0022b** | HTTP/2 Multiplexing | ⏳ In Progress | Connection management |
| **0022c** | Backpressure Cascade (K0 >80%) | ⏳ In Progress | Queue backpressure |
| **0022d** | FlatBuffers Batch Schema | ⏳ In Progress | Batch serialization |
| **0023** | Cursor-Based Turn Pagination | ✅ Accepted | Opaque cursor pagination |
| **0023a** | Cursor Encoding & Opaque Tokens | ⏳ In Progress | Token design |
| **0023b** | Pagination REST API | ⏳ In Progress | /turns API |
| **0023c** | K0 WAL Cursor Query Optimization | ⏳ In Progress | Query performance |

---

### ⚡ Performance & Resource Management (0024-0031)

| ADR | Title | Status | Key Decision |
|-----|-------|--------|--------------|
| **0024** | Performance Budgets (P95) | ✅ Accepted | TTFT <150ms, E2E <2000ms |
| **0024a** | Turn-Level Budgets | ⏳ In Progress | TTFT, E2E, Barge-In |
| **0024b** | Component-Level Budgets | ⏳ In Progress | Per-component targets |
| **0024c** | Memory Budgets & Resource Limits | ⏳ In Progress | SessionState, KV Cache limits |
| **0024d** | Graceful Degradation | ⏳ In Progress | Budget pressure handling |
| **0025** | KV Cache Management (512MB) | ✅ Accepted | Global KV cache budget |
| **0025a** | Global KV Cache Allocator | ⏳ In Progress | Per-session allocation |
| **0025b** | LRU/LFU Hybrid Eviction | ⏳ In Progress | 60% recency, 40% frequency |
| **0025c** | Cache Warming & Prefetch | ⏳ In Progress | Session resume optimization |
| **0025d** | zstd Compression for Inactive | ⏳ In Progress | 70% compression |
| **0025e** | Protected Sessions Monitoring | ⏳ In Progress | Cache hit rate tracking |
| **0026** | Thermal Hysteresis Matrix | ✅ Approved | Temperature-based throttling |
| **0026a** | Thermal Sensor Monitoring | ✅ Accepted | State detection |
| **0026b** | Hysteresis State Machine (5°C) | ✅ Accepted | Temperature buffering |
| **0026c** | Model Placement Integration | ✅ Accepted | Thermal cascade |
| **0026d** | Throttling Policies & Notifications | ✅ Accepted | User notifications |
| **0027** | Model Placement Cascade | ✅ Approved | NPU→GPU→CPU→Remote |
| **0027a** | Placement Algorithm | ✅ Accepted | 4-tier placement |
| **0027b** | Automatic Failover (<100ms) | ✅ Accepted | Fast migration |
| **0027c** | Cost-Aware Fallback ($0.10/session) | ✅ Accepted | Budget enforcement |
| **0027d** | Remote Resilience (3 retries) | ✅ Accepted | Retry strategy |
| **0028** | Weighted Fair Queuing Scheduler | ✅ Approved | QoS scheduling |
| **0028a** | WFQ Algorithm & Virtual Time | ✅ Accepted | Fair scheduling |
| **0028b** | Priority Classes & Preemption | ✅ Accepted | Priority-based execution |
| **0028c** | Starvation Prevention (5s max) | ✅ Accepted | Fairness guarantee |
| **0029** | Prometheus Metrics (RED Method) | ✅ Approved | Rate, Errors, Duration |
| **0029a** | RED Method Metric Schema | ✅ Accepted | Metric structure |
| **0029b** | Turn-Level Metrics | ✅ Accepted | TTFT, E2E metrics |
| **0029c** | Component Metrics | ✅ Accepted | Per-component metrics |
| **0029d** | Infrastructure Metrics | ✅ Accepted | KV Cache, Thermal, Memory |
| **0029e** | Alerting Rules & Grafana | ✅ Accepted | Dashboards and alerts |
| **0030** | Intelligent Trace Sampling | ✅ Approved | Adaptive sampling |
| **0030a** | Head-Based Sampling (1% baseline) | ✅ Accepted | Upfront sampling |
| **0030b** | Tail-Based Sampling (60s buffer) | ✅ Accepted | Post-decision sampling |
| **0030c** | Adaptive Sampling (1%-50%) | ✅ Accepted | Dynamic rate adjustment |
| **0030d** | Trace Storage & Jaeger (7d/30d) | ✅ Accepted | Trace retention |
| **0031** | Cost Tracking Per Session | ✅ Approved | Session-level cost tracking |
| **0031a** | Hierarchical Budget Enforcement | ✅ Approved | Corporate governance |
| **0031b** | Cost Model & Pricing Config | ✅ Approved | Usage tracking |
| **0031c** | Automatic Cost-Based Fallback | ✅ Approved | Budget degradation |
| **0031d** | Cost Observability & Metrics | ✅ Approved | Cost dashboards |

---

### 🔌 Backpressure & APIs (0039-0041)

| ADR | Title | Status | Key Decision |
|-----|-------|--------|--------------|
| **0039** | Privacy Band Overrides | ✅ Approved | Band-specific overrides |
| **0039a** | Tier Triggers & Watermarks | ✅ Accepted | Backpressure thresholds |
| **0039b** | Backpressure Propagation | ✅ Accepted | Signal flow |
| **0039c** | Recovery & Gradual Resume | ✅ Accepted | Graceful recovery |
| **0040** | WebSocket for Real-Time Chat | ✅ Approved | WebSocket API |
| **0040a** | Connection Management | ⏳ Pending | Authentication |
| **0040b** | Message Framing & FlatBuffers | ⏳ Pending | Protocol design |
| **0040c** | Backpressure & Flow Control | ⏳ Pending | Flow control |
| **0040d** | Heartbeat & Reconnection | ⏳ Pending | Connection resilience |
| **0041** | REST API for Session Management | ✅ Approved | RESTful API |
| **0041a** | Session CRUD & Resource Design | ✅ Approved | Resource-oriented design |
| **0041b** | Idempotency Keys | ✅ Approved | State synchronization |
| **0041c** | Cursor-Based Pagination | ✅ Approved | Efficient listing |
| **0041d** | OpenAPI Spec & RFC 7807 Errors | ✅ Approved | Error handling |

---

### 🚀 Phase 4 Q1-Q2: Multi-Device Family Sync (0050 Family - Device-First, Privacy-First Architecture)

**Latest Updates (2025-10-16):** Complete hybrid strategy finalized with zero-cloud approach

| ADR | Title | Status | Key Decision | Implementation Timeline |
|-----|-------|--------|--------------|------------------------|
| **0049** | Fast/Smart Lane Router Policy | ✅ Accepted | K0 Bridge lane selection with scoring | Completed |
| **0050** | Multi-Device Family Sync Strategy (Parent) | ✅ Accepted | **Device-first, hybrid: Phase 1 (LAN <1ms) + Phase 2 (Internet E2EE <500ms)** - Zero cloud intermediary, CRDT merge, per-device coherence, automatic fallback | M2-M5 |
| **0050a** | SessionState Coherence Guarantees | ✅ Accepted | **Per-device guarantees:** Read-Your-Writes (<5ms), Monotonic Reads/Writes, Writes-Follow-Reads, Bounded Staleness (250ms), Crash Recovery (<2s) - Sequence numbers + delta journal + group commit | M2-M3 |
| **0050b** | CRDT Device-to-Device Merge Protocol | ✅ Accepted | **Last-Write-Wins with device ID ordering + vector clocks:** Deterministic, commutative, idempotent merge for simultaneous writes; device order: ipad < iphone < laptop < tablet; causality via vector clocks | M2-M3 |
| **0050c** | LAN-First Sync Implementation (Phase 1) | ✅ Accepted | **mDNS discovery + TCP P07 + CRDT merge:** Service name `familyos-{device-id}._tcp.local`; 5s continuous sync interval; manual "Sync Now" button for remote devices (Phase 1 MVP); <50ms latency per change | M2-M3 (4-5 weeks) |
| **0050d** | P2P E2EE Internet Sync (Phase 2) | ✅ Accepted (Future) | **Device certificates (Ed25519+X25519) + STUN NAT traversal + QUIC tunnel + ChaCha20-Poly1305 AEAD:** Automatic LAN preference, E2EE no intermediary, certificate pinning, signature verification, 90-day cert rotation; <500ms latency | M4-M5 (8-9 weeks) |

**Architecture:** Hybrid device-centric (no cloud). Phase 1 unblocks M2 MVP with clear Phase 2 path. Both phases use same CRDT logic, P07 protocol, auto-fallback.

**Privacy Model:** Each device runs full K0+K1 locally; no vendor lock-in, no data leaves family devices, offline-capable throughout.

---

### 🔒 Enhanced HITL & Approval Protocols (0052 Family)

| ADR | Title | Status | Key Decision |
|-----|-------|--------|--------------|
| **0052** | Enhanced HITL Protocols | ✅ Accepted | Step-by-step approval with RED band 2-person rule |
| **0052a** | Step-by-Step Approval Protocol | ✅ Approved | Multi-stage confirmation for complex tasks |
| **0052b** | RED Band Approval - Two-Person Rule | ✅ Approved | Mandatory dual-signature for sensitive operations |
| **0052c** | Nested Clarification Chains & History | ✅ Approved | Context preservation for multi-turn confirmations |
| **0052d** | Proactive Risk Confirmation | ✅ Approved | Pre-action risk assessment and user consent |

---

### 🔄 Message Queue & Turn Management (0053-0054)

| ADR | Title | Status | Key Decision |
|-----|-------|--------|--------------|
| **0053** | Message Queue Coalescing | ✅ Accepted | Intelligent batching with adaptive windowing |
| **0053a** | Coalesce Window Limits | ✅ Approved | Configurable time windows (10-100ms) for message batching |
| **0053b** | Rate Limits & Bursts | ✅ Approved | Token bucket algorithm with burst allowance |
| **0053c** | Cancel Path P95 (<100ms) | ✅ Approved | Fast cancellation with sub-100ms latency |
| **0054** | Turn Boundary Management | ✅ Accepted | Explicit vs implicit turn transitions |
| **0054a** | Implicit Pause Strategy (2s timeout) | ✅ Approved | Auto-turn-boundary after 2s silence |
| **0054b** | Explicit Submit UX | ✅ Approved | User-driven turn submission |
| **0054c** | MPST Turn Transitions | ✅ Approved | Protocol-enforced turn state machine |

---

### 🧠 Intent & Context Management (0055-0058)

| ADR | Title | Status | Key Decision |
|-----|-------|--------|--------------|
| **0055** | Context Switch Detection | ✅ Accepted | Real-time intent drift detection and recovery |
| **0055a** | Intent Drift Rules | ✅ Approved | Heuristics for detecting conversation direction changes |
| **0055b** | Context Switch Prompt | ✅ Approved | Dynamic re-prompting on context boundaries |
| **0055c** | History Keep/Clear Strategy | ✅ Approved | Selective history retention during context switches |
| **0056** | Voice Pipeline Implementation | ✅ Accepted | 5-stage voice processing: ASR → Intent → Bridge → Tool → TTS |
| **0056a** | ASR Ingress | ✅ Approved | Real-time speech recognition integration |
| **0056b** | Intent Bridge | ✅ Approved | Voice-to-text intent routing |
| **0056c** | Tool Interleaving | ✅ Approved | Parallel tool execution during voice processing |
| **0056d** | TTS Synthesis | ✅ Approved | Real-time text-to-speech output |
| **0056e** | Audio Output Management | ✅ Approved | Audio routing and device management |
| **0057** | Voice-Specific Backpressure | ✅ Accepted | Audio stream flow control |
| **0057a** | ASR Frame Drop Strategy | ✅ Approved | Graceful degradation under load |
| **0057b** | TTS Degradation Ladder | ✅ Approved | Quality fallback (full → fast → cached) |
| **0057c** | Barge-In Preemption | ✅ Approved | User interruption handling (<120ms) |
| **0058** | Intent Classification in Voice | ✅ Accepted | High-confidence voice intent recognition |
| **0058a** | Confidence Thresholds | ✅ Approved | Adaptive confidence scoring |
| **0058b** | Safety Hooks | ✅ Approved | Pre-execution safety validation |

---

### 🔬 Learning Loop & Adaptive Intelligence (0059-0060)

| ADR | Title | Status | Key Decision |
|-----|-------|--------|--------------|
| **0059** | Learning Loop Framework | ✅ Accepted | Feedback integration with drift detection and rollback |
| **0059a** | Feedback Signal Taxonomy | ✅ Approved | Explicit, implicit, and behavioral signal classification |
| **0059b** | Drift Detection Algorithm | ✅ Approved | Statistical divergence from baseline performance |
| **0059c** | Planner Parameter Contracts | ✅ Approved | Parameter versioning and compatibility |
| **0059d** | Audit & Rollback Mechanisms | ✅ Approved | Parameter change auditing and safe rollback |
| **0059e** | Synthetic Data Pipeline | ✅ Approved | Bootstrapping learning with synthetic examples |
| **0060** | Adaptive KV Cache Management | ✅ Accepted | Dynamic cache sizing based on workload patterns |
| **0060a** | Dynamic Placement & Sizing | ✅ Approved | Per-session cache allocation optimization |
| **0060b** | Hot/Cold Eviction & Recovery | ✅ Approved | Intelligent eviction with rapid re-warming |

---

### 💧 Backpressure & Resource Cascade (0061)

| ADR | Title | Status | Key Decision |
|-----|-------|--------|--------------|
| **0061** | 3-Tier Backpressure Cascade | ✅ Accepted | Graceful degradation under extreme load |
| **0061a** | Watermark Thresholds & Triggers | ✅ Approved | Memory, CPU, and latency-based watermarks |
| **0061b** | RED Metrics & Alerting | ✅ Approved | Real-time backpressure visibility |
| **0061c** | Privacy Band Overrides | ✅ Approved | Band-specific cascade policies |
| **0061d** | Fairness & Anti-Starvation | ✅ Approved | QoS maintenance during cascade |

---

### ✨ Product Craft & UX (0065-0070)

| ADR | Title | Status | Key Decision |
|-----|-------|--------|--------------|
| **0065** | Product Craft - UX Micro-Interactions | ✅ Accepted | Typing animations, device handoff, quick actions |
| **0065a** | Streaming Text with Typing Effect | ✅ Approved | Real-time token streaming visualization |
| **0065b** | Session Continuity & Device Handoff | ✅ Approved | Seamless cross-device conversation transfer |
| **0065c** | Quick Actions & Suggested Replies | ✅ Approved | Contextual action suggestions |
| **0065d** | Costly Action Confirmation | ✅ Approved | Two-step confirmation for high-impact actions |
| **0066** | Developer Testing & Simulation Harness | ✅ Accepted | Deterministic testing without production simulation |
| **0067** | Conversational Delight Factors | ✅ Accepted | Personality, humor, and engagement patterns |
| **0068** | Voice Quality Measurement | ✅ Accepted | MOS scores and audio fidelity tracking |
| **0069** | P08 Affect Modulation (K0 Implementation) | ✅ Accepted | Emotional response tuning in K0 kernel |
| **0070** | Observability Evaluation Infrastructure | ✅ Accepted | LLM performance and safety monitoring |

---

### 🌐 Advanced Features & Extensibility (0071-0080)

| ADR | Title | Status | Key Decision |
|-----|-------|--------|--------------|
| **0071** | Multilingual Code-Switching | ✅ Accepted | Real-time language detection and handling |
| **0072** | ~~Dynamic Agent Creation Subsystem~~ | ❌ DELETED | Duplicate of ADR-0001 (renamed to ADR-0086) |
| **0073** | Agent Lifecycle FSM Enhancements | ✅ Accepted | Extended states for advanced agent management |
| **0074** | Pluggable Module System | ✅ Accepted | Hot-loadable modules with version management |
| **0075** | Layer 5 Extensibility Framework | ✅ Accepted | Plugin architecture for infrastructure customization |
| **0076** | KV Cache Optimization Strategy | ✅ Accepted | Advanced eviction and compression techniques |
| **0077** | Thermal Placement Algorithm v2 | ✅ Accepted | ML-informed thermal management |
| **0078** | Tool Call Batching Pipeline | ✅ Accepted | Parallel tool execution with dependency resolution |
| **0079** | Learning Loop - Drift Detection v2 | ✅ Accepted | Enhanced anomaly detection with multi-signal fusion |
| **0080** | Continuous Config Hot-Reload | ✅ Accepted | Zero-downtime configuration updates |
| **0081** | K0 Knowledge Graph Architecture | 🔄 Proposed | **Structured family relationships** - Temporal graph, relationship queries, event-based queries |
| **0081a** | Temporal Graph Schema Design | 🔄 Proposed | Graph schema with temporal properties for family relationships |
| **0081b** | Graph Query API & Traversal Algorithms | 🔄 Proposed | Query interface and graph traversal for relationship discovery |
| **0081c** | Episodic Memory KG Integration | 🔄 Proposed | Integration with K0 episodic memory system |
| **0081d** | KG Visualization & Debugging Tools | 🔄 Proposed | Developer tools for graph inspection and debugging |
| **0082** | Multi-Party Dialogue Coordination | 🔄 Proposed | **Multi-speaker conversations** - Speaker attribution, overlapping turns, conflict resolution |
| **0082a** | Speaker Diarization & Voice Biometrics | 🔄 Proposed | Audio-based speaker identification and tracking |
| **0082b** | Multi-Party Turn-Taking Coordination | 🔄 Proposed | Turn management for simultaneous speech and speaker switching |
| **0082c** | Conflict Resolution Strategies | 🔄 Proposed | Mediation for opposing requests from multiple speakers |
| **0083** | Ambient Sensor Fusion Architecture | 🔄 Proposed | **Room occupancy detection** - Privacy-aware responses, contextual awareness |
| **0083a** | Multi-Modal Sensor Integration | 🔄 Proposed | Integration of motion, light, camera, and environmental sensors |
| **0083b** | Sensor Fusion Algorithms | 🔄 Proposed | Probabilistic fusion for occupancy and context detection |
| **0084** | K0 Memory Consolidation Pipeline (P03) | 🔄 Proposed | **Dream-like reflection** - Offline learning, episodic→semantic conversion |
| **0084a** | Sleep Cycle Memory Replay Algorithms | 🔄 Proposed | Hippocampal replay patterns for memory consolidation |
| **0084b** | Offline Consolidation Scheduler | 🔄 Proposed | Nightly consolidation triggers during system idle time |
| **0084c** | Knowledge Graph Consolidation | 🔄 Proposed | KG integration for pattern extraction and relationship discovery |
| **0084d** | Dream-Like Exploration & Reflection | 🔄 Proposed | Creative problem-solving and counterfactual thinking |
| **0085** | Embodied Awareness & Device Presence | 🔄 Proposed | **Cross-device presence sensing** - Device handoff, location awareness, BLE proximity |
| **0085a** | Device Presence Detection & Location Awareness | 🔄 Proposed | Online/offline tracking, GPS, WiFi triangulation |
| **0085b** | BLE Proximity & Active Session Tracking | 🔄 Proposed | Proximity zones and active device detection |
| **0085c** | Cross-Device Context Sharing | 🔄 Proposed | Notification coordination and device preference management |
| **0086** | Dynamic Agent Creation Subsystem (Parent) | ✅ Accepted | **58+ dynamic agent types** - Runtime spawning with composition (Prompt + Tools + Persona) |
| **0086a** | Agent Factory Pattern | ✅ Approved | AgentFactory singleton, ID generation, O(1) lookup, <100ms creation |
| **0086b** | Agent Template System | ✅ Approved | JSON Schema validation, LRU cache (128), 3-level inheritance, <10ms P95 |
| **0086c** | Resource Reservation System | ✅ Approved | Atomic allocation, 512MB budget, thermal placement (NPU→GPU→CPU→Remote) |
| **0086d** | Agent Composition Pattern | ✅ Approved | CompositionEngine: Prompt + Tools + Persona, injection protection, <5ms P95 |
| **0086e** | Prompt Directory & Template Management | ✅ Approved | Jinja2 rendering, token validation, <5ms P95 |
| **0086f** | Dynamic Agent Lifecycle Integration | ✅ Approved | Factory↔hire_fire, IDLE pooling, <10ms reactivation, >60% hit rate |
| **0086g** | Agent Registry Extension | ✅ Approved | Multi-index registry, 58+ agent specs, O(1) lookups, <2ms P95 |
| **0086h** | Agent Metrics & Observability | ✅ Approved | 25+ Prometheus metrics, OpenTelemetry tracing, 3 Grafana dashboards |

---

## How to Use This Reference

### For New Features

1. **Search this document** for relevant ADRs by category
2. **Read linked ADRs** in `docs/architecture/decisions/`
3. **Check dependencies** - ADRs often reference other ADRs
4. **Verify alignment** - Ensure your design fits existing decisions
5. **Create new ADR** if making new architectural choice

### For Bug Fixes

1. **Identify affected component** from Layer architecture (ADR-0004)
2. **Check performance budgets** (ADR-0024) if performance-related
3. **Review error handling** (ADR-0008, ADR-0009) if resilience issue
4. **Verify observability** (ADR-0029, ADR-0030) for debugging

### For Code Review

1. **Verify ADR compliance** - Check if code follows relevant ADRs
2. **Check for new decisions** - Flag undocumented architectural choices
3. **Validate performance** - Ensure budgets from ADR-0024 are met
4. **Security review** - Check ADR-0010, ADR-0032-0038 compliance

---

## ADR Statistics

- **Total ADRs:** 110 (including 24 sub-ADRs)
- **Foundational (0001-0004):** 20 ADRs
- **Agent Lifecycle (0005-0006):** 12 ADRs
- **Planning Pipeline (0007):** 5 ADRs
- **Error Recovery (0008-0009):** 8 ADRs
- **Security (0010, 0032-0038):** 41 ADRs
- **Serialization (0011-0016):** 33 ADRs
- **SessionState (0017-0023):** 34 ADRs
- **Performance (0024-0031):** 40 ADRs
- **Backpressure & APIs (0039-0041):** 13 ADRs
- **Multi-Device Sync (0049-0050):** 6 ADRs
- **Enhanced HITL (0052):** 5 ADRs
- **Message Queue & Turn Management (0053-0054):** 8 ADRs
- **Intent & Context Management (0055-0058):** 14 ADRs
- **Learning Loop & Adaptive Intelligence (0059-0060):** 11 ADRs
- **Backpressure Cascade (0061):** 5 ADRs
- **Product Craft & UX (0065-0070):** 6 ADRs
- **Advanced Features & Extensibility (0071-0086):** 40 ADRs (including 21 sub-ADRs across 0081-0086)

---

## Related Resources

### Architecture Diagrams

- `architecture_diagrams/k1_architecture_diagram.mmd` - Complete K1 architecture
- `architecture_diagrams/k0_k1_integration_architecture.mmd` - K0/K1 integration
- `architecture_diagrams/k1_agent_lifecycle_fsm.mmd` - Agent lifecycle FSM
- `architecture_diagrams/k1_orchestrator_3phase.mmd` - 3-phase orchestration
- `architecture_diagrams/k1_planner_pipeline.mmd` - 4-stage planning pipeline

### Key Documentation

- `docs/whiteboard.md` - Complete K1 specifications (21K lines)
- `docs/k1_module_analysis.md` - Module structure (52 modules, 758 files)
- `docs/architecture/K0_K1_INTEGRATION_SUMMARY.md` - Integration summary
- `docs/architecture/README.md` - Architecture overview

### Development Guides

- `docs/development/getting-started.md` - Setup instructions
- `docs/development/contribution-guide.md` - How to contribute
- `docs/development/testing-guide.md` - Testing with WARD framework

---

## Maintenance

**This document is the master catalog for all ADRs in the K1 Intelligence Module.**

**Update triggers:**

- New ADR created → Add to relevant category with status and description
- ADR status changes → Update status column (Pending → Approved → Accepted → Completed)
- Major ADR revisions → Update key decision description with latest details
- Quarterly review → Verify all links, add new category sections, update statistics

**Last reviewed:** 2025-10-23
**Last major update:** 2025-10-23 (ADR-0086 Dynamic Agent Creation with 8 comprehensive sub-ADRs)
**Next review:** 2026-01-23 (Quarterly)
**Maintenance owner:** Architecture Team

**Recent Changes:**

- **2025-10-23:** ADR-0081 through ADR-0085 documented with sub-ADRs:
  - ADR-0081 (K0 Knowledge Graph): 4 sub-ADRs (0081a-d) for structured family relationships
  - ADR-0082 (Multi-Party Dialogue): 3 sub-ADRs (0082a-c) for multi-speaker coordination
  - ADR-0083 (Ambient Sensor Fusion): 2 sub-ADRs (0083a-b) for room occupancy detection
  - ADR-0084 (K0 Memory Consolidation): 4 sub-ADRs (0084a-d) for dream-like reflection
  - ADR-0085 (Embodied Awareness): 3 sub-ADRs (0085a-c) for cross-device presence sensing
  - Total: 16 new sub-ADRs documented (0081-0085 families)
- **2025-10-23:** ADR-0086 Dynamic Agent Creation Subsystem finalized with 8 sub-ADRs:
  - ADR-0001 renamed to ADR-0086 (consolidated numbering)
  - ADR-0072 deleted (duplicate)
  - 5 M1 Required sub-ADRs: 0086a (Factory), 0086b (Templates), 0086c (Resources), 0086d (Composition), 0086e (Prompts)
  - 3 M2 Optional sub-ADRs: 0086f (Lifecycle), 0086g (Registry), 0086h (Metrics)
  - Total: 7,254 lines of implementation specifications, 43 WARD test cases, 31 days implementation timeline
  - 58+ dynamic agent types documented with complete composition pattern (Prompt + Tools + Persona)
- **2025-10-16:** ADR-0050 family (0050, 0050a, 0050b, 0050c, 0050d) completely revised with comprehensive hybrid architecture (LAN Phase 1 + Internet E2EE Phase 2)
- Implementation timeline and latency targets updated
- SessionState coherence (0050a) enhanced with sequence numbers, delta journal, group commit
- CRDT merge (0050b) documented with vector clocks for causality
- Phase 1 LAN sync (0050c) ready for M2 implementation
- Phase 2 internet E2EE (0050d) designed for M4-M5 build

**Notes:**

- ADRs 0042-0086 represent Phase 4 features and extensibility layer
- ADR-0001 has been **renamed to ADR-0086** (Dynamic Agent Creation Subsystem)
- ADR-0072 **deleted** as duplicate of ADR-0086
- **ADR-0081 through ADR-0086 include 24 comprehensive sub-ADRs:**
  - ADR-0081: 4 sub-ADRs (Knowledge Graph Architecture)
  - ADR-0082: 3 sub-ADRs (Multi-Party Dialogue Coordination)
  - ADR-0083: 2 sub-ADRs (Ambient Sensor Fusion)
  - ADR-0084: 4 sub-ADRs (K0 Memory Consolidation Pipeline)
  - ADR-0085: 3 sub-ADRs (Embodied Awareness & Device Presence)
  - ADR-0086: 8 sub-ADRs (Dynamic Agent Creation - with full implementation specs)
- See LAYER5-ADRS-COMPREHENSIVE-REFERENCE.md for detailed Layer 5 architecture
- ADR-0050 family is **production-ready** for Phase 1 MVP (M2-M3)
- ADR-0086 family ready for **M1 implementation** (5 required sub-ADRs, 17 days) and **M2 implementation** (3 optional sub-ADRs, 14 days)
- ADR-0081 through ADR-0085 are **Proposed** status - Post-MVP v1.1 features

---

## Quick Links

- 📁 [All ADRs in /decisions](.)
- 🏗️ [Architecture Diagrams](../../../architecture_diagrams)
- 📖 [Complete Specs](../whiteboard.md)
- 🧪 [Development Docs](../../development)
- 📊 [K1 Module Analysis](../../k1_module_analysis.md)

---

**END OF MASTER REFERENCE**
