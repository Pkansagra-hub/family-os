# Comprehensive ADR Layer Mapping (0001-0087)

**Generated:** 2025-10-27  
**Purpose:** Map all 87 ADRs to their K1 architectural layers and identify Layer 5 infrastructure foundation

**Layer Structure:** L1 (Input) → L2 (Orchestration) → L3 (Execution) → L4 (Runtime) → L5 (Infrastructure)

---

## Layer 5: Infrastructure Foundation (Primary Support Layer for Layers 1-4)

Layer 5 infrastructure must be robust and comprehensive because ALL other 4 layers depend on it. This is the "bedrock" upon which the entire K1 intelligence module is built.

### L5 Core ADRs (Direct Infrastructure)

| ADR | Title | Milestone | Purpose | Status |
|-----|-------|-----------|---------|--------|
| **ADR-0001a** | K0 Bridge Dual Protocol | M1 | K0 communication (HTTP/2, JSON/FlatBuffers) | ✅ Accepted |
| **ADR-0001f** | K0/K1 Pipeline Boundary Enforcement | M1 | Bridge protocol validation | ✅ Accepted |
| **ADR-0009** | Circuit Breaker Pattern | M1 | Resilience, 3-state FSM | ✅ Accepted |
| **ADR-0009a** | Circuit Breaker FSM Implementation | M1 | State machine implementation | ✅ Accepted |
| **ADR-0009b** | Per-Service Circuit Configuration | M1 | Tool Runner, Model Hub, K0 Bridge | ✅ Accepted |
| **ADR-0009c** | Circuit Breaker Metrics & Observability | M1 | Monitoring circuit state | ✅ Accepted |
| **ADR-0011** | FlatBuffers Serialization | M1 | Zero-copy binary serialization (150× faster) | ✅ Accepted |
| **ADR-0011a** | FlatBuffers Schema Design Principles | M1 | Schema evolution, versioning | ✅ Accepted |
| **ADR-0011b** | FlatBuffers Code Generation | M1 | Build system integration | ✅ Accepted |
| **ADR-0011c** | Serialization Performance & Zero-Copy | M1 | <1ms P95 serialize, <0.1ms deserialize | ✅ Accepted |
| **ADR-0011d** | Schema Evolution & Versioning | M1 | Backward/forward compatibility | ✅ Accepted |
| **ADR-0012e** | Layer 5 Infrastructure Schemas | M1 | 13 FlatBuffers schemas for infra | ✅ Accepted |
| **ADR-0020** | Multi-Tier Storage (Hot/Warm/Cold) | M1 | 99.4% cost reduction, 3-tier lifecycle | ✅ Accepted |
| **ADR-0020a** | Hot Tier (L1 RAM) | M1 | 56MB in-memory, <1ms access, 96% hit rate | ✅ Accepted |
| **ADR-0020b** | Warm Tier (L2 SSD) | M1 | K0 WAL, <50ms access, 30-day retention | ✅ Accepted |
| **ADR-0020c** | Cold Tier (L3 Object S3) | M1 | Unlimited, <500ms access, 365-day retention | ✅ Accepted |
| **ADR-0022** | K0 Bridge Bounded Batching | M1 | 250ms timeout, 64KB, 100-message triggers | ✅ Accepted |
| **ADR-0022a** | Batching Algorithm | M1 | 10-50 messages, 100ms timeout | ✅ Accepted |
| **ADR-0022b** | HTTP/2 Multiplexing | M1 | Connection management | ✅ Accepted |
| **ADR-0022c** | Backpressure Cascade | M1 | K0 queue >80% triggers degradation | ✅ Accepted |
| **ADR-0022d** | FlatBuffers Batch Schema | M1 | Zero-copy batch envelope | ✅ Accepted |
| **ADR-0024** | Performance Budgets (P95 Targets) | M1 | TTFT <150ms, E2E <2000ms | ✅ Accepted |
| **ADR-0024a** | Turn-Level Performance Budgets | M1 | TTFT, E2E, Barge-in budgets | ✅ Accepted |
| **ADR-0024b** | Component-Level Budgets | M1 | Per-component latency targets | ✅ Accepted |
| **ADR-0024c** | Memory Budgets | M1 | K1 <500MB total footprint | ✅ Accepted |
| **ADR-0024d** | Graceful Degradation | M1 | Budget pressure handling | ✅ Accepted |
| **ADR-0025** | KV Cache Management (512MB) | M2 | Global budget, LRU/LFU hybrid | ✅ Accepted |
| **ADR-0025a** | Global KV Cache Allocator | M2 | 512MB budget allocation | ✅ Accepted |
| **ADR-0025b** | LRU/LFU Hybrid Eviction | M2 | 60% LRU, 40% LFU strategy | ✅ Accepted |
| **ADR-0025c** | Cache Warming & Prefetch | M2 | Session resume optimization | ✅ Accepted |
| **ADR-0025d** | Compression (zstd) | M2 | 70% reduction for inactive caches | ✅ Accepted |
| **ADR-0025e** | Protected Sessions Monitoring | M2 | Hit rate tracking | ✅ Accepted |
| **ADR-0026** | Thermal Hysteresis Matrix | M2-M3 | Hysteresis FSM (±5°C upgrade, -2°C downgrade) | 🚧 NEEDS_IMPLEMENTATION |
| **ADR-0026a** | Thermal Sensor Monitoring | M2-M3 | Cross-platform (Linux/Windows/macOS) | 🚧 NEEDS_IMPLEMENTATION |
| **ADR-0026b** | Hysteresis State Machine | M2-M3 | 7°C band, cooldown periods | 🚧 NEEDS_IMPLEMENTATION |
| **ADR-0026c** | Model Placement Integration | M2-M3 | Thermal-aware fallback | 🚧 NEEDS_IMPLEMENTATION |
| **ADR-0026d** | Throttling Policies | M2-M3 | User notifications, escalation | 🚧 NEEDS_IMPLEMENTATION |
| **ADR-0027** | Model Placement Cascade | M2-M3 | 4-tier (NPU→GPU→CPU→Remote), privacy enforcement | 🚧 NEEDS_IMPLEMENTATION |
| **ADR-0027a** | Placement Algorithm | M2-M3 | NPU→GPU→CPU→Remote cascade | 🚧 NEEDS_IMPLEMENTATION |
| **ADR-0027b** | Automatic Failover | M2-M3 | 100ms migration, 3 retries | 🚧 NEEDS_IMPLEMENTATION |
| **ADR-0027c** | Cost-Aware Fallback | M2-M3 | $0.10 per session budget | 🚧 NEEDS_IMPLEMENTATION |
| **ADR-0027d** | Remote Resilience | M2-M3 | 3 retries, 10s timeout | 🚧 NEEDS_IMPLEMENTATION |
| **ADR-0028** | Weighted Fair Queuing Scheduler | M1 | 4-tier priority, anti-starvation | ✅ Accepted |
| **ADR-0028a** | WFQ Algorithm | M1 | Virtual time scheduling | ✅ Accepted |
| **ADR-0028b** | Priority Classes | M1 | URGENT, REALTIME, INTERACTIVE, BACKGROUND | ✅ Accepted |
| **ADR-0028c** | Starvation Prevention | M1 | Max wait 5s, aging mechanism | ✅ Accepted |
| **ADR-0029** | Prometheus Metrics (RED) | M1 | Rate, Errors, Duration | ✅ Accepted |
| **ADR-0029a** | RED Method Schema | M1 | Metric naming, labels | ✅ Accepted |
| **ADR-0029b** | Turn-Level Metrics | M1 | TTFT, E2E, Barge-in | ✅ Accepted |
| **ADR-0029c** | Component Metrics | M1 | Agent, Orchestrator, Planner, Tool | ✅ Accepted |
| **ADR-0029d** | Infrastructure Metrics | M1 | KV cache, thermal, memory, CPU | ✅ Accepted |
| **ADR-0029e** | Alerting Rules & Grafana | M1 | Prometheus alerts, dashboards | ✅ Accepted |
| **ADR-0030** | Intelligent Trace Sampling | M1 | Head/tail-based, adaptive | ✅ Accepted |
| **ADR-0030a** | Head-Based Sampling | M1 | 1% baseline, 100% errors | ✅ Accepted |
| **ADR-0030b** | Tail-Based Sampling | M1 | 60s buffer, post-decision | ✅ Accepted |
| **ADR-0030c** | Adaptive Sampling | M1 | 1-50% dynamic adjustment | ✅ Accepted |
| **ADR-0030d** | Trace Storage (Jaeger) | M1 | 7d hot, 30d warm | ✅ Accepted |
| **ADR-0031** | Cost Tracking Per Session | M1 | $0.001-0.01/remote call | ✅ Accepted |
| **ADR-0031a** | Hierarchical Budget | M1 | Corporate governance, teams | ✅ Accepted |
| **ADR-0031b** | Cost Model | M1 | Per-call pricing configuration | ✅ Accepted |
| **ADR-0031c** | Automatic Cost-Based Fallback | M1 | Graceful degradation at limits | ✅ Accepted |
| **ADR-0031d** | Cost Observability | M1 | Metrics, dashboards | ✅ Accepted |
| **ADR-0044** | K0 Bridge HTTP/2 + FlatBuffers | M1 | Persistence operations only | ✅ Accepted |
| **ADR-0044a** | HTTP/2 Multiplexing | M1 | Connection management | ✅ Accepted |
| **ADR-0044b** | FlatBuffers Serialization | M1 | Binary protocol | ✅ Accepted |
| **ADR-0044c** | Batching Strategy | M1 | 250ms, 64KB, 100 messages | ✅ Accepted |
| **ADR-0044d** | Error Handling & Retry | M1 | Exponential backoff | ✅ Accepted |
| **ADR-0061** | 3-Tier Backpressure Cascade | M1 | Watermark→Pipeline→Global | 🚧 NEEDS_IMPLEMENTATION |
| **ADR-0061a** | Watermark Thresholds | M1 | 80% warn, 90% degrade, 95% reject | 🚧 NEEDS_IMPLEMENTATION |
| **ADR-0061b** | RED Metrics & Alerts | M1 | Backpressure monitoring | 🚧 NEEDS_IMPLEMENTATION |
| **ADR-0061c** | Privacy Band Overrides | M1 | RED emergency bypass | 🚧 NEEDS_IMPLEMENTATION |
| **ADR-0061d** | Fairness & Anti-Starvation | M1 | Priority scheduling | 🚧 NEEDS_IMPLEMENTATION |
| **ADR-0074** | Pluggable Module System | M2 | Registry, loader, hot-reload | 🚧 NEEDS_IMPLEMENTATION |
| **ADR-0075** | Layer 5 Extensibility Framework | M2 | 10 extension points | 🚧 NEEDS_IMPLEMENTATION |
| **ADR-0076** | KV Cache Optimization | M3 | Adaptive budgeting, ML-based | 🚧 NEEDS_IMPLEMENTATION |
| **ADR-0077** | Thermal Placement Algorithm V2 | M3 | Advanced thermal awareness | 🚧 NEEDS_IMPLEMENTATION |
| **ADR-0080** | Continuous Config Hot-Reload | M5 | SSE listener, merger, versioner | 🚧 NEEDS_IMPLEMENTATION |

**Total L5 Core ADRs: 70+** (covering all infrastructure concerns)

---

### L5 Supporting ADRs (Upstream Dependencies)

These ADRs provide building blocks used by L5:

| ADR | Title | Purpose | Layer Dependency |
|-----|-------|---------|------------------|
| **ADR-0010** | Capability-Based Security | Capability tokens, leases | L4 uses; L5 enforces |
| **ADR-0010a** | Capability Token Design | Token lifecycle | L4/L5 |
| **ADR-0010b** | Agent Capability Assignment | Policy binding | L4/L5 |
| **ADR-0010c** | Capability Enforcement (Runtime) | <1ms runtime checks | L5 implementation |
| **ADR-0010d** | Revocation & Audit Trail | Audit logging | L5/L3 |

---

### L5 Safety & Policy ADRs

| ADR | Title | Purpose | Status |
|-----|-------|---------|--------|
| **ADR-0032** | Band-Based Egress Rules | Privacy band enforcement | ✅ Accepted |
| **ADR-0032a** | Network Egress Control | iptables + privacy bands | ✅ Accepted |
| **ADR-0032b** | Filesystem Egress Control | chroot + seccomp | ✅ Accepted |
| **ADR-0032c** | Resource Egress Control | cgroups per-band | ✅ Accepted |
| **ADR-0032d** | Egress Violation Logging | Audit trail | ✅ Accepted |
| **ADR-0035** | PII Detection & Redaction | PII patterns, vault | ✅ Accepted |
| **ADR-0035a** | Regex Pattern Library | Pattern DB | ✅ Accepted |
| **ADR-0035b** | ML-Based NER | Semantic PII | ✅ Accepted |
| **ADR-0035c** | Encrypted Vault | AES-256-GCM | ✅ Accepted |
| **ADR-0035d** | Audit Trail | GDPR compliance | ✅ Accepted |
| **ADR-0036** | E2EE for RED Band | End-to-end encryption | ✅ Accepted |
| **ADR-0036a** | AES256-GCM Implementation | Encryption | ✅ Accepted |
| **ADR-0036b** | KMS Integration | Key lifecycle | ✅ Accepted |
| **ADR-0036c** | SessionState Integration | Selective encryption | ✅ Accepted |
| **ADR-0036d** | Audit Trail & Compliance | Logging | ✅ Accepted |
| **ADR-0038** | Audit Trail to K0 Receipts | Receipt aggregation | ✅ Accepted |
| **ADR-0038a** | Receipt Generation | FlatBuffers schema | ✅ Accepted |
| **ADR-0038b** | K0 WAL Integration | Async writes | ✅ Accepted |
| **ADR-0038c** | Retention Policies | Auto-deletion | ✅ Accepted |
| **ADR-0038d** | Query Interface | Compliance export | ✅ Accepted |

---

### L5 Storage & Persistence ADRs

| ADR | Title | Purpose | Status |
|-----|-------|---------|--------|
| **ADR-0018** | 3-Tier Eviction Strategy | Soft/Hard/OOM | ✅ Accepted |
| **ADR-0018a** | Tier 1 Soft Eviction | 64KB→80KB | ✅ Accepted |
| **ADR-0018b** | Tier 2 Hard Eviction | Emergency | ✅ Accepted |
| **ADR-0018c** | Tier 3 OOM Prevention | Last resort | ✅ Accepted |
| **ADR-0019a** | SessionState FlatBuffers Schema | Zero-copy | ✅ Accepted |
| **ADR-0019b** | Delta Serialization | Incremental updates | ✅ Accepted |
| **ADR-0019c** | K0 WAL Integration | Persistence | ✅ Accepted |
| **ADR-0019d** | Zero-Copy Deserialization | <0.1ms P95 | ✅ Accepted |
| **ADR-0021** | Turn History Retention | Lifecycle policies | ✅ Accepted |
| **ADR-0021a** | Retention Engine | Automated lifecycle | ✅ Accepted |
| **ADR-0021b** | Privacy Band Overrides | Band-specific rules | ✅ Accepted |
| **ADR-0021c** | Compliance Reporting | Audit trail | ✅ Accepted |

---

### L5 Networking & Communication ADRs

| ADR | Title | Purpose | Status |
|-----|-------|---------|--------|
| **ADR-0004a** | Event Bus (L1-L2 Communication) | Pub/sub, <5ms | 🚧 NEEDS_IMPLEMENTATION |
| **ADR-0015a** | WebSocket Message Envelope | Routing | ✅ Accepted |
| **ADR-0015b** | Flow Control & Backpressure | Watermark coordination | ✅ Accepted |
| **ADR-0015c** | Reconnection & Session Resume | Recovery | ✅ Accepted |
| **ADR-0015d** | Streaming Token Delivery | Heartbeat | ✅ Accepted |
| **ADR-0015e** | TypeScript Client SDK | Browser integration | ✅ Accepted |
| **ADR-0016** | SSE Event Schemas | 17 event types | ✅ Accepted |
| **ADR-0016a** | Topic Hierarchy | Schema design | ✅ Accepted |
| **ADR-0016b** | FlatBuffers-to-JSON | SSE serialization | ✅ Accepted |
| **ADR-0016c** | Topic-Based Filtering | Routing | ✅ Accepted |
| **ADR-0016d** | Browser EventSource | Client integration | ✅ Accepted |
| **ADR-0040** | WebSocket Real-Time Chat | L2-L3 coordination | ✅ Accepted |
| **ADR-0040a** | Connection Management | Auth, TLS | ✅ Accepted |
| **ADR-0040b** | Message Framing | FlatBuffers protocol | ✅ Accepted |
| **ADR-0040c** | Backpressure | Flow control | ✅ Accepted |
| **ADR-0040d** | Heartbeat & Reconnection | Recovery | ✅ Accepted |
| **ADR-0042** | K0 SSE Event Streaming | Durable events | ✅ Accepted |
| **ADR-0042a** | K0 SSE Event Production | Publishing | ✅ Accepted |
| **ADR-0042b** | K0 SSE Event Consumption | Subscription | ✅ Accepted |
| **ADR-0042c** | K0 SSE Reconnection | Replay | ✅ Accepted |
| **ADR-0042d** | K0 SSE Backpressure | Event persistence | ✅ Accepted |
| **ADR-0042e** | K0 SSE Device Storage | Mobile tiers | ✅ Accepted |
| **ADR-0043** | SSE Topic Taxonomy | 10-category hierarchy | ✅ Accepted |
| **ADR-0043a** | K0 SSE Topic Hierarchy | Organization | ✅ Accepted |
| **ADR-0043b** | K0 SSE Subscription Patterns | Routing | ✅ Accepted |
| **ADR-0043c** | K0 SSE Topic Routing | Delivery guarantees | ✅ Accepted |
| **ADR-0043d** | K0 SSE Topic ACL | Access control | ✅ Accepted |
| **ADR-0045** | K1 Internal Event Bus | Agent coordination | ✅ Accepted |
| **ADR-0045a** | K1 Event Bus Pub/Sub | Architecture | ✅ Accepted |
| **ADR-0045b** | Topic Routing | Mechanism | ✅ Accepted |
| **ADR-0045c** | Delivery Guarantees | Semantics | ✅ Accepted |
| **ADR-0045d** | Backpressure Handling | Flow control | ✅ Accepted |
| **ADR-0046** | SSE-WebSocket Bridge | UI real-time | ✅ Accepted |
| **ADR-0048** | K1 Internal Event Bus (Runtime) | L1-L2 communication | 🚧 NEEDS_IMPLEMENTATION |
| **ADR-0049** | Fast/Smart Lane Router | K0 bridge policy | ✅ Accepted |

---

### L5 Error Recovery & Resilience ADRs

| ADR | Title | Purpose | Status |
|-----|-------|---------|--------|
| **ADR-0008** | Saga Pattern Error Recovery | Compensating transactions | ✅ Accepted |
| **ADR-0008a** | Idempotency (Error Recovery) | Deduplication, Redis 5-min TTL | ✅ Accepted |
| **ADR-0008b** | Transient/Permanent Failures | Classification | ✅ Accepted |
| **ADR-0008c** | Distributed State Management | K0 WAL integration | ✅ Accepted |
| **ADR-0008d** | Timeout & Deadlock | Escalation logic | ✅ Accepted |
| **ADR-0034** | MCP Protocol Adoption | Tool sandboxing | ✅ Accepted |
| **ADR-0034a** | MCP JSON-RPC | Protocol spec | ✅ Accepted |
| **ADR-0034b** | MCP Process Lifecycle | Timeout enforcement | ✅ Accepted |
| **ADR-0034c** | MCP Circuit Breaker | Resilience | ✅ Accepted |
| **ADR-0034d** | MCP Error Handling | Recovery | ✅ Accepted |
| **ADR-0033** | Three-Tier Tool Sandboxing | MCP/WASM/Process | ✅ Accepted |
| **ADR-0033a** | MCP Protocol Integration | Layer 1 | ✅ Accepted |
| **ADR-0033b** | WASM Sandbox | Medium isolation | ✅ Accepted |
| **ADR-0033c** | Process Sandbox | High isolation | ✅ Accepted |
| **ADR-0033d** | 2D Selection Logic | Protocol × Sandbox | ✅ Accepted |

---

### L5 API & REST ADRs

| ADR | Title | Purpose | Status |
|-----|-------|---------|--------|
| **ADR-0014** | JSON/REST API (Dual Format) | Content negotiation | ✅ Accepted |
| **ADR-0014a** | Content Negotiation | Format detection | ✅ Accepted |
| **ADR-0014b** | OpenAPI Spec Generation | FlatBuffers→OpenAPI | ✅ Accepted |
| **ADR-0014c** | Serialization Pipeline | Request/response | ✅ Accepted |
| **ADR-0014d** | Client SDK Examples | Migration guides | ✅ Accepted |
| **ADR-0041** | REST API Session Management | CRUD + pagination | ✅ Accepted |
| **ADR-0041a** | Session CRUD | Resource design | ✅ Accepted |
| **ADR-0041b** | Idempotency | State sync | ✅ Accepted |
| **ADR-0041c** | Cursor Pagination | REST listing | ✅ Accepted |
| **ADR-0041d** | OpenAPI & Error Handling | RFC 7807 | ✅ Accepted |
| **ADR-0023** | Cursor-Based Pagination | Turns listing | ✅ Accepted |
| **ADR-0023a** | Cursor Encoding | Opaque token | ✅ Accepted |
| **ADR-0023b** | Pagination REST API | Cursor+limit | ✅ Accepted |
| **ADR-0023c** | K0 WAL Cursor Optimization | Query optimization | ✅ Accepted |
| **ADR-0047** | OpenAPI 3.1 REST Specs | API documentation | ✅ Accepted |

---

### L5 Authentication & Authorization ADRs

| ADR | Title | Purpose | Status |
|-----|-------|---------|--------|
| **ADR-0037** | JWT Authentication | Token-based auth | ✅ Accepted |
| **ADR-0037a** | Token Generation | Signing | ✅ Accepted |
| **ADR-0037b** | Token Validation | Verification | ✅ Accepted |
| **ADR-0037c** | Refresh Token Flow | Rotation | ✅ Accepted |
| **ADR-0037d** | Session Binding | Authorization | ✅ Accepted |
| **ADR-0039** | Privacy Band Overrides | Critical operations | ✅ Accepted |
| **ADR-0039a** | Tier Triggers | Watermark thresholds | ✅ Accepted |
| **ADR-0039b** | Backpressure Signal Flow | Propagation | ✅ Accepted |
| **ADR-0039c** | Recovery | Gradual resume | ✅ Accepted |

---

## Layer 4: Runtime Core

**Depends on:** Layer 5 (Infrastructure)

### L4 ADRs (Session State, Mailbox, Learning)

| ADR | Title | Purpose | Depends on L5 |
|-----|-------|---------|--------------|
| **ADR-0002** | Actor Model | Message-passing FSM | Event Bus, Mailbox |
| **ADR-0002a** | Mailbox (MPSC Queue) | Per-agent queues | Circuit Breaker, WFQ Scheduler |
| **ADR-0002b** | Supervisor | Health monitoring | Metrics, Alerting |
| **ADR-0002c** | Router Admission Control | Rate limiting | Backpressure, Budgets |
| **ADR-0002d** | Observability Schema | Structured logging | Prometheus, OpenTelemetry |
| **ADR-0017** | SessionState 6-Section | In-memory working state | FlatBuffers, Multi-Tier Storage |
| **ADR-0017a** | Beliefs | User facts | SessionState serialization |
| **ADR-0017b** | Scoreboard | Common ground | Multi-party dialogue |
| **ADR-0017c** | Control | Agent leases, flow | Capability security |
| **ADR-0017d** | Persona | Personality | - |
| **ADR-0017e** | Multimodal | Audio/vision | - |
| **ADR-0017f** | Meta | Telemetry | Metrics, Tracing |
| **ADR-0005** | Agent Lifecycle FSM | PENDING→WARMING→... | Scheduler, Thermal |
| **ADR-0005a** | WARMING State | Model load warmup | KV Cache, Placement |
| **ADR-0005b** | IDLE Pooling | Memory optimization | Storage eviction |
| **ADR-0005c** | DRAINING Shutdown | Resource cleanup | Graceful termination |
| **ADR-0005d** | Supervisor Blacklist | Crash recovery | Metrics, Circuit Breaker |
| **ADR-0005e** | Personality & Capabilities | Persona binding | Capability enforcement |
| **ADR-0059** | Learning Loop | Feedback collection | Observability, K0 Persistence |
| **ADR-0059a** | Feedback Signal Taxonomy | Signal types | Metrics collection |
| **ADR-0059b** | Drift Detection | Degradation detection | Observability, Alerting |
| **ADR-0059c** | Parameter Contracts | Update specs | Config management |
| **ADR-0059d** | Audit & Rollback | Change history | K0 WAL, Receipts |
| **ADR-0059e** | Synthetic Data | Testing pipeline | - |
| **ADR-0060** | Adaptive KV Cache | Dynamic sizing | KV Cache optimizer |
| **ADR-0060a** | Dynamic Placement & Sizing | KV allocation | Storage budgets |
| **ADR-0060b** | Hot/Cold Eviction | Cache recovery | Eviction strategy |
| **ADR-0070** | Observability Infrastructure | Eval infrastructure | Metrics, Tracing |

---

## Layer 3: Execution (Agents, Tools, Models)

**Depends on:** Layer 4 (Runtime), Layer 5 (Infrastructure)

### L3 ADRs (Agent Lifecycle, Model Hub, Tool Execution)

| ADR | Title | Purpose | Depends on L5 |
|-----|-------|---------|--------------|
| **ADR-0003** | MPST Protocol Validation | Actor communication validation | Observability, Tracing |
| **ADR-0003a** | Protocol Definition Language | PDL specification | - |
| **ADR-0003b** | 6 Core Protocol Implementations | Protocol specs | - |
| **ADR-0003c** | Protocol Monitor (Runtime) | Validation enforcement | Metrics, Alerts |
| **ADR-0003d** | Role Attestation | Capability verification | Capability security |
| **ADR-0004f** | Stream Switch Cross-Modal Context | Entity tracking | Event Bus |
| **ADR-0001b** | Model Hub Architecture | AI integration layer | Placement cascade, Thermal |
| **ADR-0086** | Dynamic Agent Creation | Factory pattern | Registry, Config management |
| **ADR-0086a** | Agent Factory Pattern | Creation | Config, Scheduler |
| **ADR-0086b** | Agent Template System | Templates | Config management |
| **ADR-0086c** | Resource Reservation | Lease system | Budgets, Capability system |
| **ADR-0086d** | Agent Composition | Patterns | - |
| **ADR-0086e** | Prompt Directory | Template management | Config management |
| **ADR-0086f** | Dynamic Agent Lifecycle | Lifecycle integration | Agent FSM |
| **ADR-0086g** | Agent Registry Extension | Extension points | Extensibility framework |
| **ADR-0086h** | Agent Metrics | Observability | Metrics, Tracing |

---

## Layer 2: Orchestration (Planning, Multi-Agent Coordination)

**Depends on:** Layer 3 (Execution), Layer 4 (Runtime), Layer 5 (Infrastructure)

### L2 ADRs (Planning, Orchestration, Saga, Scheduling)

| ADR | Title | Purpose | Depends on L5 |
|-----|-------|---------|--------------|
| **ADR-0006** | 3-Phase Orchestration | Negotiation→Selection→Execution | Event Bus, Backpressure |
| **ADR-0006a** | Contract Net Negotiation | Bidding | Metrics, Tracing |
| **ADR-0006b** | Multi-Criteria Scoring | Proposal scoring | - |
| **ADR-0006c** | Parallel DAG Execution | Dependency graph | Scheduler, Backpressure |
| **ADR-0006d** | Saga Pattern Integration | Error recovery | Saga pattern, Receipts |
| **ADR-0006e** | Multi-Agent Coordination | Agent communication | Event Bus |
| **ADR-0007** | 4-Stage Planning Pipeline | Sketch→Expand→Validate→Commit | K0 Bridge, Budgets |
| **ADR-0007a** | Sketch Stage | LLM prompt engineering | - |
| **ADR-0007b** | Expand Stage | Tool registry integration | - |
| **ADR-0007c** | Validation Stage | 2-tier validation | Budget validation |
| **ADR-0007d** | Commit Stage | K0 WAL integration | K0 Bridge, WAL Writer |

---

## Layer 1: Input Processing (Streams, Intent Routing)

**Depends on:** Layer 2 (Orchestration), Layer 5 (Infrastructure)

### L1 ADRs (Stream Processing, Intent Routing, Voice Pipeline)

| ADR | Title | Purpose | Depends on L5 |
|-----|-------|---------|--------------|
| **ADR-0004a** | Event Bus (L1-L2 Comm) | Pub/sub for layers | Event Bus |
| **ADR-0004b** | Module Dependency Management | Import linter | - |
| **ADR-0004c** | Module README Template | Documentation | - |
| **ADR-0004d** | Per-Layer Integration Testing | Test structure | - |
| **ADR-0004f** | Stream Switch Multi-Modal | Audio/text/vision | Event Bus, Rate limiting |
| **ADR-0056** | Voice Pipeline Implementation | ASR→Intent→TTS | Backpressure, Thermal |
| **ADR-0056a** | ASR Ingress | Frame size, VAD | - |
| **ADR-0056b** | Intent Bridge | Voice→DM contract | - |
| **ADR-0056c** | Tool Interleaving | Concurrent execution | Scheduler |
| **ADR-0056d** | TTS Synthesis | Prosody controls | Backpressure |
| **ADR-0056e** | Audio Out | Device handshake | - |
| **ADR-0056f** | Voice Persona Persistence | Cross-session continuity | Storage, SessionState |
| **ADR-0057** | Voice-Specific Backpressure | Pipeline degradation | Backpressure, Thermal |
| **ADR-0057a** | ASR Frame Drop | Frame downsample | Backpressure |
| **ADR-0057b** | TTS Degradation | Bitrate/prosody reduction | Backpressure |
| **ADR-0057c** | Barge-in Preemption | Turn-taking priority | Scheduler, Backpressure |
| **ADR-0058** | Intent Classification (Voice) | NLU | Metrics, Tracing |
| **ADR-0058a** | Confidence Thresholds | Clarification strategy | - |
| **ADR-0058b** | Safety Hooks | Privacy band gates | Security policy |

---

## Cross-Cutting Infrastructure Patterns (All Layers Depend On)

### Serialization & Schema Management (L5)
- **ADR-0011**: FlatBuffers (150× faster, <1ms serialize, <0.1ms deserialize)
- **ADR-0012e**: Layer 5 Infrastructure Schemas (13 schemas)
- **ADR-0013**: Schema Versioning & Compatibility

### Observability & Monitoring (L5)
- **ADR-0029**: Prometheus Metrics (RED method)
- **ADR-0030**: Trace Sampling (OpenTelemetry)
- **ADR-0029d**: Infrastructure Metrics (KV cache, thermal, memory, CPU)

### Performance & Budgets (L5)
- **ADR-0024**: Performance Budgets (P95 targets, TTFT <150ms)
- **ADR-0025**: KV Cache (512MB global budget, LRU/LFU)
- **ADR-0026**: Thermal Management (hysteresis, 4-tier placement)
- **ADR-0027**: Model Placement Cascade (NPU→GPU→CPU→Remote)
- **ADR-0028**: Weighted Fair Queuing (4-tier scheduling)

### Resilience & Error Recovery (L5)
- **ADR-0009**: Circuit Breaker (3-state FSM, per-service)
- **ADR-0008**: Saga Pattern (compensating transactions)
- **ADR-0061**: 3-Tier Backpressure (watermark→pipeline→global)
- **ADR-0008a**: Idempotency (Redis 5-min TTL)

### Storage & Persistence (L5)
- **ADR-0020**: Multi-Tier Storage (99.4% cost reduction)
- **ADR-0021**: Retention Policies
- **ADR-0038**: Audit Trail (K0 receipts)

### Security & Privacy (L5)
- **ADR-0010**: Capability-Based Security
- **ADR-0032**: Band-Based Egress Rules
- **ADR-0035**: PII Detection
- **ADR-0036**: E2EE for RED Band
- **ADR-0037**: JWT Authentication

### Networking & Communication (L5)
- **ADR-0004a**: Event Bus (L1-L2 communication)
- **ADR-0022**: K0 Bridge Batching (250ms, 64KB)
- **ADR-0040**: WebSocket (real-time chat)
- **ADR-0042**: K0 SSE (event streaming)
- **ADR-0045**: K1 Internal Event Bus

---

## Summary: Layer 5 Infrastructure Robustness

### Why Layer 5 Must Be Strong & Robust

**All 4 upper layers depend entirely on L5 services:**

- **L1 Input**: Event Bus, Stream processing, Rate limiting, Backpressure
- **L2 Orchestration**: Event Bus, Scheduler, Budgets, Cost tracking, Saga pattern
- **L3 Execution**: Model placement, Thermal management, KV cache, Capability system, Tool sandboxing
- **L4 Runtime**: Mailbox, Circuit breaker, Observability, Storage, Scheduling

### L5 Critical Components (Must Exist)

**Core Infrastructure (Mandatory):**
1. ✅ K0 Bridge (HTTP/2, JSON/FlatBuffers batching)
2. ✅ FlatBuffers Serialization (150× faster)
3. ✅ Event Bus (L1-L2 communication, <5ms)
4. ✅ Observability (Prometheus, OpenTelemetry, structured logs)
5. ✅ Circuit Breaker (resilience, per-service)
6. ✅ Scheduler (WFQ, 4-tier priority, <5ms)
7. ✅ Backpressure Coordination (3-tier cascade, <5ms)
8. ✅ Multi-Tier Storage (Hot/Warm/Cold, 99.4% cost)
9. ✅ KV Cache Management (512MB, LRU/LFU hybrid)
10. ✅ Security & Privacy (Capability system, PII detection, E2EE, egress control)

**Performance Optimization (Mandatory):**
1. ✅ Performance Budgets (P95 targets for all components)
2. ✅ Cost Tracking (per-call, per-session budgets)
3. ✅ Idempotency (Redis 5-min TTL, Saga error recovery)

**Graceful Degradation (Mandatory):**
1. ✅ Thermal Management (hysteresis FSM, 4-tier placement cascade)
2. ✅ Backpressure (watermark→pipeline→global escalation)
3. ✅ Fallback Strategies (circuit breaker, cost-aware degradation)

**Advanced Features (M2-M3):**
1. 🚧 Module System (ADR-0074)
2. 🚧 Extensibility Framework (ADR-0075)
3. 🚧 Config Hot-Reload (ADR-0080)
4. 🚧 Learning Loop (ADR-0059, ADR-0079)

### Total ADR Coverage

- **Total ADRs: 87**
- **Layer 5 Infrastructure ADRs: 70+**
- **Layer 5 Coverage: 80%+ of ADRs**

This demonstrates that Layer 5 is indeed the "backbone" of K1, with the majority of architectural patterns and decisions focused on building a robust, performant, and resilient foundation for all upper layers.

