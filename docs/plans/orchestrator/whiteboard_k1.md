# K1 Kernel Whiteboard

## Overview

K1 (Agentic Intelligence Kernel) is the real-time AI orchestration layer in FamilyOS's dual-kernel microkernel architecture. It's designed for fast, concurrent processing of intelligent tasks while maintaining fault isolation from the durable memory layer (K0).

## Key Characteristics

- **Purpose**: Handles multi-agent coordination, LLM inference, tool execution, and real-time streams
- **Architecture**: Built on the Actor Model for concurrency and fault isolation, with a hybrid design mixing AI agents (LLM-powered) and pure actors (deterministic coordination)
- **Components**:
  - AI Agents: Concierge, Planner, Researcher, Safety Watch (use LLMs for reasoning)
  - Pure Actors: Orchestrator, Supervisor, Router, etc. (deterministic logic, no LLM calls)
- **Performance Focus**: Optimized for low latency (TTFT <150ms P95), rapid evolution, and independent scaling from K0
- **Communication**: Uses a bridge to K0 for memory operations via defined ports (P01-P20) with FlatBuffers serialization

## Why This Design

The split from K0 provides fault isolation (AI crashes don't corrupt memory), independent evolution (K1 can iterate on AI features rapidly), and clear boundaries between durable storage and intelligent processing. It's research-backed by microkernel principles and the Actor Model, enabling a production-ready cognitive OS for family use cases.

## Architecture Layers

- Layer 1: Input (sensors, voice, text)
- Layer 2: Orchestration (agent coordination)
- Layer 3: Execution (tool running, LLM calls)
- Layer 4: Runtime (actor lifecycle, supervision)
- Layer 5: Infrastructure (model hub, session state)

## Key Decisions

- Dual-kernel split for fault isolation and independent scaling
- Actor Model for all components (concurrency, isolation)
- Hybrid AI agents + pure actors for efficiency (LLMs only where needed)
- Bridge protocol with FlatBuffers for K0 communication
- 5-layer microkernel architecture within K1

## K1 Architecture Decision Records Hierarchy

### 00-meta/ *(Meta and tooling for ADRs)*

- adr_index.json
- MIGRATION_PROCESS.md
- propagation_maps/

### 01-foundation/ *(Core architectural foundations)*

- 0001-k0-k1-kernel-split/ *(Dual-kernel architecture split)*
- 0002-actor-model-agent-isolation/ *(Actor Model for concurrency/isolation)*
- 0003-mpst-protocol-validation/ *(Multi-party session type protocols)*
- 0004-56-module-5-layer-architecture/ *(5-layer microkernel design)*
- index.yml

### 02-layer1-input/ *(Input processing and ingestion)*

- 0056-voice-pipeline-implementation/ *(Voice input pipeline)*
- 0057-voice-specific-backpressure/ *(Voice backpressure handling)*
- 0068-voice-quality-measurement/ *(Voice quality metrics)*
- 0069-p08-affect-modulation-k0-impl/ *(Affect/emotion modulation)*
- 0071-multilingual-code-switching/ *(Language switching support)*
- 0083-ambient-sensor-fusion/ *(Sensor data fusion)*
- index.yml

### 03-layer2-orchestration/ *(Agent coordination and orchestration)*

- 0005-agent-lifecycle-fsm/ *(Agent lifecycle management)*
- 0006-3-phase-orchestration/ *(3-phase agent negotiation)*
- 0007-4stage-planning-pipeline/ *(4-stage planning process)*
- 0008-saga-pattern-error-recovery/ *(Error recovery patterns)*
- 0017-sessionstate-6-section-design/ *(Session state management)*
- 0028-weighted-fair-queuing-scheduler/ *(Task scheduling)*
- 0045-k1-event-bus-coordination/ *(Internal event coordination)*
- 0048-k1-internal-event-bus/ *(Event bus architecture)*
- 0049-fast-smart-lane-router-policy/ *(Message routing policies)*
- 0073-agent-lifecycle-fsm-enhancements/ *(Enhanced agent lifecycle)*
- 0082-multi-party-dialogue-coordination/ *(Multi-agent dialogue)*
- 0086-dynamic-agent-creation-subsystem/ *(Dynamic agent spawning)*
- 0093-conciergeagent-pattern-(master-coordinator-with-11-meta-intents)/ *(Concierge agent design)*
- index.yml

### 04-layer3-execution/ *(Tool execution and model inference)*

- 0027-model-placement-cascade/ *(LLM model placement strategy)*
- 0033-three-tier-sandbox-strategy/ *(Execution sandboxing)*
- 0058-intent-classification-voice/ *(Voice intent classification)*
- 0059-learning-loop/ *(Continuous learning feedback)*
- 0078-tool-call-batching-pipeline/ *(Tool execution batching)*
- 0079-learning-loop-drift-detection/ *(Learning drift monitoring)*
- index.yml

### 05-layer4-runtime/ *(Runtime management and caching)*

- 0018-3-tier-eviction-strategy/ *(Cache eviction policies)*
- 0021-turn-history-retention-policies/ *(Conversation history retention)*
- 0025-kv-cache-management-512mb/ *(KV cache limits)*
- 0031-cost-tracking-per-session/ *(Usage cost tracking)*
- 0039-backpressure-cascade-3-tier/ *(Runtime backpressure)*
- 0060-adaptive-kv-cache-management/ *(Adaptive caching)*
- 0076-kv-cache-optimization-strategy/ *(Cache optimization)*
- index.yml

### 06-layer5-infrastructure/ *(Infrastructure and observability)*

- 0009-circuit-breaker-pattern/ *(Fault tolerance patterns)*
- 0020-multi-tier-storage/ *(Storage tiering)*
- 0024-performance-budgets-p95-targets/ *(Performance targets)*
- 0026-thermal-hysteresis-matrix/ *(Thermal management)*
- 0029-prometheus-metrics-red-method/ *(Metrics collection)*
- 0030-intelligent-trace-sampling/ *(Distributed tracing)*
- 0038-audit-trail-to-k0-receipts/ *(Audit logging)*
- 0050-multi-device-family-sync-strategy/ *(Device synchronization)*
- 0061-3-tier-backpressure-cascade/ *(Infrastructure backpressure)*
- 0070-observability-evaluation-infrastructure/ *(Observability setup)*
- 0074-pluggable-module-system/ *(Extensible modules)*
- 0075-layer5-extensibility-framework/ *(Infrastructure extensibility)*
- 0077-thermal-placement-algorithm-v2/ *(Thermal optimization)*
- 0080-continuous-config-hot-reload/ *(Configuration management)*
- 0081-k0-knowledge-graph-architecture/ *(Knowledge graph integration)*
- 0084-k0-memory-consolidation-pipeline/ *(Memory consolidation)*
- 0087-kg-mcp-semantic-enhancement/ *(Semantic enhancements)*
- 0088-k0-local-env-paths-migration/ *(Environment migration)*
- 0090-deployment-strategy-edge-rollout/ *(Deployment strategies)*
- 0091-k0-observability-architecture/ *(K0 observability)*
- 0092-remediation-service-separation/ *(Error remediation)*
- index.yml

### 07-contracts-serialization/ *(Data contracts and schemas)*

- 0011-flatbuffers-serialization/ *(FlatBuffers usage)*
- 0012-76-flatbuffers-schemas/ *(Schema definitions)*
- 0013-pipeline-versioning-policy/ *(Version management)*
- 0019-flatbuffers-sessionstate-serialization/ *(Session state schemas)*
- 0047-openapi-3-1-rest-specs/ *(API specifications)*
- index.yml

### 08-security-privacy/ *(Security foundations)*

- 0010-capability-based-security/ *(Capability security model)*
- index.yml

### 08-user-interaction/ *(User interaction patterns)*

- 0052-enhanced-hitl-protocols/ *(Human-in-the-loop)*
- 0053-message-queue-coalescing/ *(Message optimization)*
- 0054-turn-boundary-management/ *(Conversation turns)*
- 0055-context-switch-detection/ *(Context awareness)*
- 0065-product-craft-ux-micro-interactions/ *(UX interactions)*
- 0066-developer-testing-simulation-harness/ *(Testing tools)*
- 0067-conversational-delight-factors/ *(Conversation quality)*
- 0085-embodied-awareness-device-presence/ *(Device presence)*
- index.yml

### 09-communication/ *(Communication protocols)*

- 0014-json-rest-api-dual-format/ *(REST API design)*
- 0015-websocket-binary-protocol/ *(WebSocket protocols)*
- 0016-sse-event-schemas/ *(Server-sent events)*
- 0022-k0-bridge-bounded-batching/ *(Bridge communication)*
- 0023-cursor-based-turn-pagination/ *(Pagination strategies)*
- 0034-mcp-protocol-adoption/ *(MCP protocol integration)*
- 0040-websocket-realtime-chat/ *(Real-time chat)*
- 0041-rest-api-session-management/ *(Session management)*
- 0042-k0-sse-event-streaming/ *(Event streaming)*
- 0043-sse-topic-taxonomy/ *(Event topics)*
- 0044-k0-bridge-http2-flatbuffers/ *(Bridge protocols)*
- 0046-sse-websocket-bridge/ *(Protocol bridging)*
- index.yml

### 10-multi-device-sync/ *(Multi-device synchronization)*

- index.yml *(Empty - no ADRs yet)*

### 10-security-privacy/ *(Advanced security)*

- 0032-band-based-egress-rules/ *(Network security)*
- 0035-pii-detection-and-redaction/ *(PII handling)*
- 0036-e2ee-for-red-band/ *(End-to-end encryption)*
- 0037-jwt-authentication/ *(Authentication)*
- 0089-k0-bridge-policy-enforcement/ *(Policy enforcement)*
- index.yml

### 10-user-interaction/ *(Advanced user interaction)*

- 0094-add-query_k0_finance-tool-to-poc-tool-registry-and-mock-mcp/ *(Tool integration)*
- index.yml

### 11-ux-product/ *(UX and product design)*

- index.yml *(Empty - no ADRs yet)*

### 13-advanced/ *(Advanced features)*

- index.yml *(Empty - no ADRs yet)*

## Detailed ADR Master Reference

**Last Updated:** 2025-10-23
**Total ADRs:** 110 (including 24 sub-ADRs)
**Status:** Complete catalog of all architectural decisions with Layer 5 extensibility

### Foundational Architecture (0001-0004)

| ADR | Title | Status | Key Decision |
| --- | --- | --- | --- |
| **0001** | K0/K1 Kernel Split Architecture | ✅ Accepted | Dual-kernel microkernel: K0 (memory) + K1 (intelligence) |
| **0001a** | K0 Bridge Communication Protocol | ✅ Approved | Dual protocol: JSON (primary) + FlatBuffers (optimization) |
| **0001b** | Model Hub Architecture & LLM Integration | 🔄 In Progress | LLM integration layer for AI agents |
| **0001c** | K0/K1 Pipeline Boundary Enforcement | 🚨 CRITICAL | Hard-coded boundaries: K0 owns ALL pipelines P01-P20, K1 has ZERO pipelines |
| **0001d** | State Boundary Management (K1 vs K0) | ✅ Completed | K1 ephemeral working memory (64KB) vs K0 durable long-term memory (unbounded) |
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
| **0004f** | Stream Switch Multi-Modal Bus | ⏳ Proposed | Unified cross-modal input handling with <5ms transition latency |

### Agent Lifecycle & Orchestration (0005-0006)

| ADR | Title | Status | Key Decision |
| --- | --- | --- | --- |
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
| **0006f** | 3-Phase Orchestration with Contract Net Protocol | ✅ Completed | Negotiation → Selection → Execution with contract net protocol |

### Planning Pipeline (0007)

| ADR | Title | Status | Key Decision |
| --- | --- | --- | --- |
| **0007** | 4-Stage Planning Pipeline | ✅ Accepted | Sketch → Expand → Validate → Commit |
| **0007a** | Sketch Stage LLM Prompt Engineering | ✅ Approved | LLM-powered plan sketching |
| **0007b** | Expand Stage Tool/Prompt Registry | ✅ Approved | Tool selection and prompt templates |
| **0007c** | Validation Stage 2-Tier Implementation | ✅ Approved | Rule-based + arbiter validation |
| **0007d** | Commit Stage K0 WAL Integration | ✅ Approved | Plan persistence to K0 storage |

### Error Recovery & Resilience (0008-0009)

| ADR | Title | Status | Key Decision |
| --- | --- | --- | --- |
| **0008** | Saga Pattern for Error Recovery | ✅ Accepted | Compensating transactions for rollback |
| **0008a** | Compensating Transaction Design | ✅ Approved | Idempotent compensation handlers |
| **0008b** | Forward vs Backward Recovery | ✅ Approved | Recovery strategy selection |
| **0008c** | Distributed State Management | ✅ Approved | State tracking across agents |
| **0008d** | Timeout & Deadlock Handling | ✅ Approved | Timeout enforcement, deadlock detection |
| **0009** | Circuit Breaker Pattern | ✅ Accepted | Cascading failure prevention |
| **0009a** | Circuit Breaker 3-State FSM | ✅ Accepted | CLOSED → OPEN → HALF_OPEN |
| **0009b** | Per-Service Circuit Configuration | ✅ Accepted | Service-specific thresholds |
| **0009c** | Circuit Breaker Metrics | ✅ Accepted | Observability and alerting |

### Security & Capabilities (0010, 0032-0038)

| ADR | Title | Status | Key Decision |
| --- | --- | --- | --- |
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

### Serialization & Data Formats (0011-0016)

| ADR | Title | Status | Key Decision |
| --- | --- | --- | --- |
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

### SessionState & Storage (0017-0023)

| ADR | Title | Status | Key Decision |
| --- | --- | --- | --- |
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
| **0020c** | Cold Tier (L3 S3) | ⏳ In Progress | S3 archive |
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

### Performance & Resource Management (0024-0031)

| ADR | Title | Status | Key Decision |
| --- | --- | --- | --- |
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

### Communication Protocols (0042-0048)

| ADR | Title | Status | Key Decision |
| --- | --- | --- | --- |
| **0042** | K0 SSE Event Streaming | ✅ Accepted | Server-Sent Events for real-time K0 data streaming |
| **0042a** | K0 SSE Event Production | ✅ Accepted | Event generation and publishing from K0 |
| **0042b** | K0 SSE Event Consumption | ✅ Accepted | Client-side event processing and handling |
| **0042c** | K0 SSE Reconnection Replay | ✅ Accepted | Stateful reconnection with event replay |
| **0042d** | K0 SSE Backpressure Persistence | ✅ Accepted | Backpressure handling for SSE streams |
| **0042e** | K0 SSE Device Storage Tiers | ✅ Accepted | Multi-tier storage for SSE event persistence |
| **0043** | SSE Topic Taxonomy | ✅ Accepted | Hierarchical topic structure for SSE events |
| **0043a** | K0 SSE Topic Hierarchy | ✅ Accepted | Topic naming and organization structure |
| **0043b** | K0 SSE Topic Subscription | ✅ Accepted | Client subscription management |
| **0043c** | K0 SSE Topic Routing | ✅ Accepted | Event routing based on topic hierarchy |
| **0043d** | K0 SSE Topic ACL | ✅ Accepted | Access control for topic-based events |
| **0044** | K0 Bridge HTTP2 FlatBuffers | ✅ Accepted | HTTP/2 protocol for K0-K1 communication |
| **0044a** | HTTP2 Multiplexing | ✅ Accepted | Connection multiplexing for efficiency |
| **0044b** | FlatBuffers Serialization | ✅ Accepted | Binary serialization over HTTP/2 |
| **0044c** | Batching Strategy | ✅ Accepted | Message batching for performance |
| **0044d** | Error Handling & Retry | ✅ Accepted | Robust error recovery mechanisms |
| **0045** | K1 Event Bus Coordination | ✅ Accepted | Internal event coordination within K1 |
| **0045a** | K1 Event Bus PubSub | ✅ Accepted | Publish-subscribe pattern for K1 events |
| **0045b** | Topic Routing Mechanism | ✅ Accepted | Event routing within K1 architecture |
| **0045c** | Delivery Guarantees | ✅ Accepted | Reliability guarantees for event delivery |
| **0045d** | Backpressure Handling | ✅ Accepted | Flow control for event streams |
| **0046** | SSE WebSocket Bridge | ✅ Accepted | Protocol bridging between SSE and WebSocket |
| **0047** | OpenAPI 3.1 REST Specs | ✅ Accepted | REST API specification for K1 services |
| **0048** | K1 Internal Event Bus | ✅ Accepted | Event bus architecture for K1 components |

### User Interaction (0052e, 0054d, 0056f)

| ADR | Title | Status | Key Decision |
| --- | --- | --- | --- |
| **0052e** | K1 User Interaction Framework | ✅ Accepted | Framework for user interaction patterns |
| **0054d** | K1 User State Management | ✅ Accepted | User state persistence and management |
| **0056f** | K1 User Context Persistence | ✅ Accepted | Long-term user context storage |

### Backpressure & APIs (0039-0041)

| ADR | Title | Status | Key Decision |
| --- | --- | --- | --- |
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

### Multi-Device Family Sync (0049-0050)

| ADR | Title | Status | Key Decision | Implementation Timeline |
| --- | --- | --- | --- | --- |
| **0049** | Fast/Smart Lane Router Policy | ✅ Accepted | K0 Bridge lane selection with scoring | Completed |
| **0050** | Multi-Device Family Sync Strategy (Parent) | ✅ Accepted | **Device-first, hybrid: Phase 1 (LAN <1ms) + Phase 2 (Internet E2EE <500ms)** - Zero cloud intermediary, CRDT merge, per-device coherence, automatic fallback | M2-M5 |
| **0050a** | SessionState Coherence Guarantees | ✅ Accepted | **Per-device guarantees:** Read-Your-Writes (<5ms), Monotonic Reads/Writes, Writes-Follow-Reads, Bounded Staleness (250ms), Crash Recovery (<2s) - Sequence numbers + delta journal + group commit | M2-M3 |
| **0050b** | CRDT Device-to-Device Merge Protocol | ✅ Accepted | **Last-Write-Wins with device ID ordering + vector clocks:** Deterministic, commutative, idempotent merge for simultaneous writes; device order: ipad < iphone < laptop < tablet; causality via vector clocks | M2-M3 |
| **0050c** | LAN-First Sync Implementation (Phase 1) | ✅ Accepted | **mDNS discovery + TCP P07 + CRDT merge:** Service name `familyos-{device-id}._tcp.local`; 5s continuous sync interval; manual "Sync Now" button for remote devices (Phase 1 MVP); <50ms latency per change | M2-M3 (4-5 weeks) |
| **0050d** | P2P E2EE Internet Sync (Phase 2) | ✅ Accepted (Future) | **Device certificates (Ed25519+X25519) + STUN NAT traversal + QUIC tunnel + ChaCha20-Poly1305 AEAD:** Automatic LAN preference, E2EE no intermediary, certificate pinning, signature verification, 90-day cert rotation; <500ms latency | M4-M5 (8-9 weeks) |

### Enhanced HITL & Approval Protocols (0052)

| ADR | Title | Status | Key Decision |
| --- | --- | --- | --- |
| **0052** | Enhanced HITL Protocols | ✅ Accepted | Step-by-step approval with RED band 2-person rule |
| **0052a** | Step-by-Step Approval Protocol | ✅ Approved | Multi-stage confirmation for complex tasks |
| **0052b** | RED Band Approval - Two-Person Rule | ✅ Approved | Mandatory dual-signature for sensitive operations |
| **0052c** | Nested Clarification Chains & History | ✅ Approved | Context preservation for multi-turn confirmations |
| **0052d** | Proactive Risk Confirmation | ✅ Approved | Pre-action risk assessment and user consent |

### Message Queue & Turn Management (0053-0054)

| ADR | Title | Status | Key Decision |
| --- | --- | --- | --- |
| **0053** | Message Queue Coalescing | ✅ Accepted | Intelligent batching with adaptive windowing |
| **0053a** | Coalesce Window Limits | ✅ Approved | Configurable time windows (10-100ms) for message batching |
| **0053b** | Rate Limits & Bursts | ✅ Approved | Token bucket algorithm with burst allowance |
| **0053c** | Cancel Path P95 (<100ms) | ✅ Approved | Fast cancellation with sub-100ms latency |
| **0054** | Turn Boundary Management | ✅ Accepted | Explicit vs implicit turn transitions |
| **0054a** | Implicit Pause Strategy (2s timeout) | ✅ Approved | Auto-turn-boundary after 2s silence |
| **0054b** | Explicit Submit UX | ✅ Approved | User-driven turn submission |
| **0054c** | MPST Turn Transitions | ✅ Approved | Protocol-enforced turn state machine |

### Intent & Context Management (0055-0058)

| ADR | Title | Status | Key Decision |
| --- | --- | --- | --- |
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

### Learning Loop & Adaptive Intelligence (0059-0060)

| ADR | Title | Status | Key Decision |
| --- | --- | --- | --- |
| **0059** | Learning Loop Framework | ✅ Accepted | Feedback integration with drift detection and rollback |
| **0059a** | Feedback Signal Taxonomy | ✅ Approved | Explicit, implicit, and behavioral signal classification |
| **0059b** | Drift Detection Algorithm | ✅ Approved | Statistical divergence from baseline performance |
| **0059c** | Planner Parameter Contracts | ✅ Approved | Parameter versioning and compatibility |
| **0059d** | Audit & Rollback Mechanisms | ✅ Approved | Parameter change auditing and safe rollback |
| **0059e** | Synthetic Data Pipeline | ✅ Approved | Bootstrapping learning with synthetic examples |
| **0060** | Adaptive KV Cache Management | ✅ Accepted | Dynamic cache sizing based on workload patterns |
| **0060a** | Dynamic Placement & Sizing | ✅ Approved | Per-session cache allocation optimization |
| **0060b** | Hot/Cold Eviction & Recovery | ✅ Approved | Intelligent eviction with rapid re-warming |

### Backpressure Cascade (0061)

| ADR | Title | Status | Key Decision |
| --- | --- | --- | --- |
| **0061** | 3-Tier Backpressure Cascade | ✅ Accepted | Graceful degradation under extreme load |
| **0061a** | Watermark Thresholds & Triggers | ✅ Approved | Memory, CPU, and latency-based watermarks |
| **0061b** | RED Metrics & Alerting | ✅ Approved | Real-time backpressure visibility |
| **0061c** | Privacy Band Overrides | ✅ Approved | Band-specific cascade policies |
| **0061d** | Fairness & Anti-Starvation | ✅ Approved | QoS maintenance during cascade |

### Product Craft & UX (0065-0070)

| ADR | Title | Status | Key Decision |
| --- | --- | --- | --- |
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

### Advanced Features & Extensibility (0071-0086)

| ADR | Title | Status | Key Decision |
| --- | --- | --- | --- |
| **0071** | Multilingual Code-Switching | ✅ Accepted | Real-time language detection and handling |
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
| **0083c** | Privacy-Aware Context Enrichment | 🔄 Proposed | Ambient sensor fusion with privacy band enforcement |
| **0087** | Knowledge Graph MCP Semantic Enhancement | ✅ Accepted | AI agent enablement for KG queries |
| **0088** | K0 Local Environment Paths Migration | ✅ Accepted | Environment helpers migration from k0/deployment to k0/deploy |
| **0090** | Deployment Strategy Edge Rollout | ✅ Accepted | Edge deployment orchestration and version management |
| **0091** | K0 Observability Architecture | ✅ Accepted | Comprehensive observability framework for K0 |
| **0092** | Remediation Service Separation & Microkernel Purity | ✅ Accepted | Service separation for error remediation |
| **0093** | ConciergeAgent Pattern (Master Coordinator with 11 Meta-Intents) | ✅ Accepted | Master coordinator for conversational workflows |
| **0094** | Add query_k0_finance tool to POC Tool Registry and Mock MCP | ⏳ Draft | Finance tool integration for POC testing |

## ADR Statistics

- **Total ADRs:** 119 (including 24 sub-ADRs)
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
- **Advanced Features & Extensibility (0071-0094):** 49 ADRs (including 21 sub-ADRs across 0081-0086)

## Thinking process

┌─────────────────────────────────────────────────────────────────────────────────┐
│                           K1 INTELLIGENCE KERNEL                               │
│                    CORRECTED PROCESS FLOW DIAGRAM                              │
└─────────────────────────────────────────────────────────────────────────────────┘

╔═════════════════════════════════════════════════════════════════════════════════╗
║                    🎯 USER-BOUND COGNITIVE ARCHITECTURE                      ║
╚═════════════════════════════════════════════════════════════════════════════════╝

┌─────────────────────────────────────────────────────────────────────────────┐
│  🌐 EXTERNAL UI/APIS (IGNORED - JUST EXPOSED ENDPOINTS)                     │
│                                                                             │
│  UI Clients → K1 REST/WebSocket/SSE APIs → Message Routing                  │
└─────────────────────────────────────────┬─────────────────────────────────────┘
                                          │
                                          ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│  🧠 L1: CONCIERGE (DEEP AI AGENT - PRIMARY BRAIN)                          │
│                                                                             │
│  • Receives user messages via mailbox                                       │
│  • LLM-powered with personality & conversational style                      │
│  • Has TOOL CALLS to Orchestrator (not direct execution)                   │
│  • Session owner & high-level reasoning                                     │
│  • FIRST: Calls "list_available_resources" tool                             │
└─────────────────────────────────────────┬─────────────────────────────────────┘
                                          │
                                          ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│  🎭 L2: ORCHESTRATOR (PURE ACTOR - EXECUTION COORDINATOR)                  │
│                                                                             │
│  • Receives tool calls from Concierge                                       │
│  • Has ALL capabilities: Subagents, MCP toolboxes, DAG engine, Planner     │
│  • Deterministic coordination (no LLM)                                      │
│  • Manages agent spawning, tool execution, planning                         │
│  • Uses shared SessionState & mailboxes                                     │
└─────────────────────────────────────────┬─────────────────────────────────────┘
                                          │
                                          ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│  📋 L3: PLANNER ENGINE (WHEN PLANNING INTENT DETECTED)                     │
│                                                                             │
│  3-STEP PROCESS:                                                            │
│  1. 📝 GATHER REQUIREMENTS from Concierge (via mailbox)                     │
│  2. 🤖 SPAWN AGENTS/TOOLS (if current agents not sufficient)                │
│  3. 🔗 CREATE & EXECUTE DAG PLAN                                           │
│                                                                             │
│  • LLM tool calls for agent/tool spawning decisions                         │
│  • DAG execution with dependency resolution                                 │
│  • Continuous human-in-the-loop feedback                                    │
└─────────────────────────────────────────┬─────────────────────────────────────┘
                                          │
                                          ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│  🤖 L4: SPAWNED SUB-AGENTS & TOOLS (ON-DEMAND EXECUTION)                   │
│                                                                             │
│  • Dynamic agent spawning (58+ types)                                       │
│  • MCP toolboxes execution                                                  │
│  • Tool runners (WASM sandbox)                                              │
│  • Model inference cascade (NPU→GPU→CPU→Remote)                            │
│  • All communicate via shared mailboxes                                     │
└─────────────────────────────────────────┬─────────────────────────────────────┘
                                          │
                                          ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│  💾 L5: SHARED SESSIONSTATE (CENTRAL WORKING MEMORY)                       │
│                                                                             │
│  • Single source of truth for all actors/agents                             │
│  • Beliefs, Scoreboard, Control, Persona, Multimodal Context                │
│  • Turn History, Messages, Telemetry                                        │
│  • FlatBuffers serialization                                                │
│  • Periodic K0 checkpoints                                                  │
└─────────────────────────────────────────┬─────────────────────────────────────┘
                                          │
                                          ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│  🗄️ L6: K0 DURABLE BRIDGE (LONG-TERM MEMORY)                               │
│                                                                             │
│  • Memory operations via P01-P20 ports                                      │
│  • FlatBuffers over HTTP/2                                                  │
│  • PostgreSQL persistence                                                   │
└─────────────────────────────────────────────────────────────────────────────┘

╔═════════════════════════════════════════════════════════════════════════════════╗
║                      🔄 HUMAN-IN-THE-LOOP FEEDBACK LOOPS                     ║
╚═════════════════════════════════════════════════════════════════════════════════╝

Concierge ↔ User (every step - conversational feedback)
Planner ↔ User (requirement clarification, plan approval)
Sub-Agents ↔ User (progress updates, decision points)
Orchestrator ↔ User (resource allocation, execution approval)

╔═════════════════════════════════════════════════════════════════════════════════╗
║                          📝 EXAMPLE FLOW: FINANCE QUERY                       ║
╚═════════════════════════════════════════════════════════════════════════════════╝

1. 🎯 User: "What does my finance this month look like?"

2. 📨 Message → Concierge mailbox

3. 🧠 Concierge: Analyzes intent, calls "list_available_resources" tool
   → Orchestrator responds with: agents, prompts, tools, connectors

4. 🧠 Concierge: Calls "spawn_planner" tool on Orchestrator
   → Orchestrator spawns Planner Engine

5. 📋 Planner: Gathers requirements from Concierge (via mailbox)
   → "Need financial data analysis - check user approval?"

6. 👤 Human-in-loop: User approves/ clarifies requirements

7. 📋 Planner: Spawns Finance Agent + Data Connector tools
   → Creates DAG: Query K0 → Analyze → Summarize

8. 🤖 Sub-Agents: Execute DAG steps using shared SessionState
   → Finance Agent queries K0 memory
   → Data tools process information
   → All communicate via mailboxes

9. 📋 Planner: Monitors execution, updates Concierge
   → "Analysis complete - show to user?"

10. 👤 Human-in-loop: User reviews/requests changes

11. 🧠 Concierge: Formats final response conversationally

╔═════════════════════════════════════════════════════════════════════════════════╗
║                          🔧 KEY ARCHITECTURAL PRINCIPLES                     ║
╚═════════════════════════════════════════════════════════════════════════════════╝

• 🧠 **Concierge**: AI brain with tool calls (never executes directly)
• 🎭 **Orchestrator**: Pure actor with all execution capabilities
• 📋 **Planner**: 3-step planning when complex coordination needed
• 🤖 **Sub-Agents**: Spawned on-demand for specific tasks
• 💾 **Shared State**: Single SessionState for all actors/agents
• 📬 **Mailboxes**: All communication via actor mailboxes
• 👤 **Human-in-Loop**: User involvement at every major decision point
• 🔄 **Feedback Loops**: Non-linear, user-bound process flow

This creates a truly intelligent, user-centric system where the Concierge is the conversational interface and the Orchestrator handles all the complex coordination behind the scenes!



k1/
├── __init__.py                          # Exports: ConciergeAgent, OrchestratorActor, EventBus, SessionState, DeltaBus, MailboxRouter
├── main.py                              # Wiring only: Load config (pydantic), instantiate actors/buses/bridges, connect Event Bus/Delta Bus, start supervisors, handle shutdown (signal handlers)
├── README.md                            # Full spec: Layers (L0-L6), flows (e.g., 3-phase orchestration, Delta aggregation), ADRs (e.g., ADR-0005, ADR-0006), setup (deps, env vars), usage (API endpoints), troubleshooting (common errors, logs)
├── pyproject.toml                       # Deps: flatbuffers, pydantic, aiohttp, pykka (actors), aiokafka (Event Bus), opentelemetry (tracing), pytest (tests), uvicorn (if web APIs needed)
├── contracts/                           # Existing: Schemas & interfaces (expanded per diagram)
│   ├── schemas/                         # FlatBuffers .fbs (SessionState.fbs, Event.fbs, Agent.fbs, Delta.fbs)
│   ├── modules/                         # YAML contracts (concierge.yaml, orchestrator.yaml, etc.) - define interfaces, events, syscalls
│   └── events/                          # JSON schemas for topics (e.g., k1.orchestration.task.announced.v1, k1.agent.lifecycle.spawn)
├── concierge/                           # L1: The Chatty Brain (Concierge as single writer to SessionState)
│   ├── __init__.py                      # Exports: ConciergeAgent, ConciergeMailbox
│   ├── README.md                        # Purpose: User interface, state writer. Interfaces: Tool adapters, mailbox. ADRs: ADR-0093 (tool calls)
│   ├── agent.py                         # class ConciergeAgent(Actor): async def handle_message(msg). LLM calls via mailbox. Single writer to SessionState. Handles 11 meta-intents.
│   ├── mailbox.py                       # class ConciergeMailbox: WFQ queue (REALTIME priority). async def send/receive. Integrates with MailboxRouter.
│   ├── tools/                           # Thin adapters only (delegate to Event Bus/tools - no implementation)
│   │   ├── list_resources.py             # def list_available_resources() -> emit k1.tool.query to EventBus
│   │   ├── spawn_planner.py              # def spawn_planner() -> emit k1.agent.lifecycle.spawn to EventBus
│   │   ├── delegate_task.py              # def delegate_task(intent) -> emit k1.orchestration.task.announced to EventBus
│   │   ├── check_safety.py               # def check_safety(input) -> emit k1.agent.safety.check to EventBus
│   │   └── update_state.py               # def update_session_state(delta) -> emit to DeltaBus (via DeltaAggregationWindow)
│   ├── persona.py                       # class PersonaEngine: Manage traits (static, rarely changes)
│   ├── style.py                         # class ConversationalStyle: Tone/length control
│   └── aggregation.py                   # class DeltaAggregationWindow: 500ms batching, conflict resolution (timestamp + confidence scoring)
├── orchestrator/                        # L2: The Coordinator (Pure Actor - no LLM)
│   ├── __init__.py                      # Exports: OrchestratorActor, OrchestratorMailbox
│   ├── README.md                        # Purpose: Execution logic. Interfaces: 3-phase orchestration, agent spawning. ADRs: ADR-0006 (3-phase), ADR-0086 (spawning)
│   ├── actor.py                         # class OrchestratorActor(Actor): Pure logic. async def negotiate/select/execute. Tool call translation to DAG/agent factories.
│   ├── mailbox.py                       # class OrchestratorMailbox: WFQ REALTIME
│   ├── orchestration/                   # 3-Phase (ADR-0006, ADR-0006a-d)
│   │   ├── negotiation.py               # class ContractNet: Announce tasks (k1.orchestration.task.announced), collect proposals (k1.orchestration.proposal.submitted)
│   │   ├── selection.py                 # class MultiCriteriaScorer: Score proposals (capability + latency + cost + specialization) (k1.orchestration.proposals.scored)
│   │   └── execution.py                 # class DAGExecutor: Parallel tasks with dependencies, Saga recovery (k1.orchestration.execution.dag.started, k1.orchestration.saga.rollback)
│   └── spawning/                        # ADR-0086
│       ├── registry.py                  # class AgentRegistry (58+ types, O(1) lookups), PromptRegistry (Jinja2 templates), ToolRegistry (MCP + direct)
│       ├── factory.py                   # class AgentFactory: Singleton, resource reservation, ID generation (k1.agent.factory.create)
│       └── composition.py               # class CompositionEngine: Inject prompts/tools/persona, injection protection (k1.agent.composition.build)
├── planner/                             # L3: The Strategist (Conditional - LLM-powered)
│   ├── __init__.py                      # Exports: PlannerAgent, PlannerMailbox
│   ├── README.md                        # Purpose: Conditional planning. Interfaces: 4-stage pipeline, HITL. ADRs: ADR-0007 (4-stage)
│   ├── agent.py                         # class PlannerAgent(Actor): LLM-powered planning
│   ├── mailbox.py                       # class PlannerMailbox: WFQ INTERACTIVE
│   ├── pipeline/                        # ADR-0007
│   │   ├── sketch.py                    # class SketchStage: LLM plan sketch, high-level intent analysis
│   │   ├── expand.py                    # class ExpandStage: Lookup prompts/tools from registries
│   │   ├── validate.py                  # class ValidateStage: Rule-based + arbiter validation, safety/feasibility checks
│   │   └── commit.py                    # class CommitStage: Persist to K0 WAL (k1.planning.commit)
│   └── hil/                             # HITL (ADR-0052)
│       ├── clarification.py             # class RequirementClarifier: User clarification (k1.user.feedback.planning)
│       ├── approval.py                  # class PlanApprover: Plan approval
│       └── monitoring.py                # class ExecutionMonitor: Progress monitoring
├── agents/                              # L4: The Workers (Dynamic Sub-Agents & Tools)
│   ├── __init__.py                      # Exports: BaseAgent, AgentLifecycleFSM
│   ├── README.md                        # Purpose: Dynamic execution. Interfaces: FSM, tools. ADRs: ADR-0005 (lifecycle FSM)
│   ├── lifecycle.py                     # class AgentLifecycleFSM: States (PENDING→WARMING→ACTIVE→IDLE→DRAINING→TERMINATED)
│   ├── base.py                          # class BaseAgent(Actor): Mailbox, hooks, tool execution
│   ├── dynamic/                        # Instances
│   │   ├── planner_instance.py          # class PlannerAgentInstance: Spawned planner
│   │   ├── researcher.py                # class ResearcherAgent: Background priority
│   │   ├── safety.py                    # class SafetyWatchAgent: URGENT priority
│   │   └── custom.py                    # class CustomAgent: Prompt + tools + persona
│   └── mailboxes/                       # Dynamic allocation
│       ├── pool.py                      # class MailboxPool: MPSC queues, WFQ integration
├── tools/                               # Shared Tool Infrastructure (Centralized - L4)
│   ├── __init__.py                      # Exports: MCPToolRunner, WASMSandbox, ModelInferenceCascade
│   ├── README.md                        # Purpose: Execution infra. Interfaces: Run tools. ADRs: ADR-0078 (batching)
│   ├── mcp_runners.py                   # class MCPToolRunner: Sandbox MCP tools
│   ├── wasm_sandbox.py                  # class WASMSandbox: Execute WASM
│   └── model_inference.py               # class ModelInferenceCascade: NPU→GPU→CPU→Remote with thermal hysteresis
├── sessionstate/                        # L5: The Memory (Multi-Tier Storage)
│   ├── __init__.py                      # Exports: SessionState
│   ├── README.md                        # Purpose: Shared state. Interfaces: Read/write, tiers. ADRs: ADR-0017 (concurrency), ADR-0020 (tiers), ADR-0021 (retention)
│   ├── store.py                         # class SessionState: Single-writer (Concierge), multi-reader, 6 sections, LRU eviction
│   ├── sections/                        # 6 Sections
│   │   ├── beliefs.py                   # class BeliefsSection: Facts/preferences (LRU Medium)
│   │   ├── scoreboard.py                # class ScoreboardSection: QUD/commitments (LRU High)
│   │   ├── control.py                   # class ControlSection: Flow/agent leases (LRU Critical, ephemeral)
│   │   ├── persona.py                   # class PersonaSection: Static traits
│   │   ├── multimodal.py                # class MultimodalSection: Context (LRU Medium)
│   │   ├── history.py                   # class HistorySection: Conversation continuity
│   │   └── telemetry.py                 # class TelemetrySection: Costs/meta (LRU Low)
│   └── tiers/                           # ADR-0020
│       ├── hot.py                       # class HotTier: RAM <1ms, capacity >56MB → evict to Warm
│       ├── warm.py                      # class WarmTier: SSD <50ms, 30d retention (GREEN/AMBER), 7d (RED)
│       └── cold.py                      # class ColdTier: Object storage <500ms, 365d (GREEN/AMBER), 90d (RED)
├── k0_bridge/                          # L6: The Archive (Durable Kernel Bridge)
│   ├── __init__.py                      # Exports: K0Bridge
│   ├── README.md                        # Purpose: Durable ops. Interfaces: P01-P20 ports. ADRs: ADR-0018 (memory writer)
│   ├── bridge.py                        # class K0Bridge: aiohttp client, FlatBuffers/JSON, 3-retry failover
│   ├── protocol.py                      # class BridgeProtocol: Serialization
│   ├── services/                        # K0 Services
│   │   ├── memory.py                    # class K0MemoryOps: Query/write
│   │   ├── persistence.py               # class K0Persistence: WAL
│   │   ├── receipts.py                  # class K0Receipts: Audit trail
│   │   └── learning_bridge.py           # class K0K1LearningBridge: SSE events, proactive spawns (k1.k0.bridge.learning)
│   └── backends/                        # K0 Backends
│       ├── wal.py                       # class K0WALBackend: SQLite WAL
│       └── object.py                    # class K0ObjectBackend: MinIO/S3
├── bus/                                 # Coordination: The Nervous System
│   ├── __init__.py                      # Exports: EventBus, DeltaBus, MailboxRouter
│   ├── README.md                        # Purpose: Routing. Interfaces: Pub/sub, direct. ADRs: ADR-0048 (routing), ADR-0017 (Delta Bus)
│   ├── event_bus.py                     # class EventBus: aiokafka pub/sub (topics: k1.orchestration.*, k1.agent.*, etc.)
│   ├── delta_bus.py                     # class DeltaBus: Dumb transport for state deltas (no aggregation - delegates to DeltaAggregationWindow)
│   └── mailbox_router.py                # class MailboxRouter: UUID → mailbox, location transparent
├── scheduler/                           # Top-Level: Performance Scheduling
│   ├── __init__.py                      # Exports: WFQScheduler
│   ├── README.md                        # Purpose: Priority/latency. Interfaces: Queue tasks. ADRs: ADR-0028 (WFQ)
│   ├── wfq.py                           # class WFQScheduler: Priority queues (URGENT=4, REALTIME=3, INTERACTIVE=2, BACKGROUND=1)
│   ├── latency.py                       # class LatencyBalancer: AI <500ms, pure actors <5ms
│   └── placement.py                     # class ModelPlacement: Cascade with hysteresis
├── supervision/                         # Top-Level: Failure Recovery
│   ├── __init__.py                      # Exports: Supervisor
│   ├── README.md                        # Purpose: Monitoring/recovery. Interfaces: Health checks. ADRs: ADR-0002b (recovery), ADR-0005d (FSM)
│   ├── supervisor.py                    # class Supervisor: <2s detection, 1Hz ping, exponential backoff
│   ├── cleanup.py                       # class SessionStateCleanup: Remove leases, mark flows interrupted
│   └── blacklist.py                     # class BlacklistManager: 3 crashes/10min → 1hr ban
├── learning/                            # Top-Level: Learning Loop
│   ├── __init__.py                      # Exports: FeedbackSignalCollector, etc.
│   ├── README.md                        # Purpose: Adaptation. Interfaces: Signals, updates. ADRs: ADR-0059 (learning), ADR-0059a-e
│   ├── signal_collector.py              # class FeedbackSignalCollector: 3-tier signals (explicit/implicit/behavioral)
│   ├── drift_detector.py                # class DriftDetector: Statistical divergence
│   ├── advisory_emitter.py              # class AdvisoryEmitter: Parameter recommendations (k1.learning.advisory.emitted)
│   ├── parameter_updater.py             # class ParameterUpdater: Adjust thresholds/temperature
│   ├── proactive_spawner.py             # class ProactiveAgentSpawner: LLM questions, feedback (k1.agent.proactive.spawned)
│   ├── rollback_handler.py              # class AuditRollbackHandler: Safety, rollback
│   └── synthetic_pipeline.py            # class SyntheticDataPipeline: Bootstrapping examples
├── memory_writer/                       # Top-Level: Memory Writer System
│   ├── __init__.py                      # Exports: MemoryWriterAgent
│   ├── README.md                        # Purpose: Durable memory. Interfaces: Summarize, emit. ADRs: ADR-0018 (writer), ADR-0018a-b
│   ├── agents.py                        # class MemoryWriterAgent: LLM summarizers (Episodic/Semantic/KG/Procedural/Prospective/Social/Vector)
│   ├── delta_emitter.py                 # class StateDeltaEmitter: 250ms batch to K0 (P02, P05, P06)
│   └── aggregator.py                    # class DeltaAggregator: Dedupe, compress, priority queuing
├── cache/                               # Top-Level: Adaptive KV Cache
│   ├── __init__.py                      # Exports: CacheSizeAllocator
│   ├── README.md                        # Purpose: Cache management. Interfaces: Size, eviction. ADRs: ADR-0060 (cache), ADR-0060a-b
│   ├── size_allocator.py                # class CacheSizeAllocator: Dynamic allocation
│   ├── evictor.py                       # class HotColdEvictor: LRU with thermal data
│   ├── rewarmer.py                      # class RapidRewarmer: <50ms reactivation
│   └── thermal_integrator.py            # class ThermalCacheIntegrator: Temperature adjustments
├── hitl/                                # Top-Level: HITL Feedback Loops
│   ├── __init__.py                      # Exports: ConciergeUserLoop
│   ├── README.md                        # Purpose: User feedback. Interfaces: Bidirectional. ADRs: ADR-0052 (HITL)
│   ├── concierge_loop.py                # class ConciergeUserLoop: Conversational feedback (k1.user.feedback.conversational)
│   ├── planner_loop.py                  # class PlannerUserLoop: Planning feedback
│   ├── subagents_loop.py                # class SubAgentsUserLoop: Execution feedback
│   └── orchestrator_loop.py             # class OrchestratorUserLoop: Resource feedback
├── config/                              # The Settings
│   ├── __init__.py                      # Exports: settings
│   ├── settings.py                      # pydantic BaseSettings: Env vars, config files
├── scripts/                             # Utilities
│   ├── sync_architecture.py             # Run governance sync (GATE 0/5)
│   ├── migrate_sessionstate.py          # Tier migrations (ADR-0020)
│   └── benchmark_inference.py           # Latency tests (ADR-0028)
└── docs/                                # Knowledge
    └── runbooks/                        # Guides: Setup, troubleshooting, performance tuning
