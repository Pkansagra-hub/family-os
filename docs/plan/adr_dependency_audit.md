# ADR Dependency Audit - Availability Status

**Document Purpose:** Complete inventory of all ADRs (main + sub) from `docs/architecture/decisions/` directory with availability status in `DEPENDENCY_MAP.md`

**Last Generated:** 2025-10-17
**Total ADRs:** 143 (1 Master + 0 Template + 142 Decision ADRs)

---

## TABLE 1: MAIN ADRs & AVAILABILITY STATUS

| # | ADR | Title | Available in DEPENDENCY_MAP | Status |
|---|-----|-------|------------------------------|--------|
| 1 | ADR-0001 | K0/K1 Kernel Split | YES | âœ… Section 1.1 |
| 2 | ADR-0002 | Actor Model for Agent Isolation | YES | âœ… Section 2.1 |
| 3 | ADR-0003 | MPST Protocol Validation | YES | âœ… Section 2.5 |
| 4 | ADR-0004 | 52-Module 5-Layer Architecture | YES | âœ… Section 2.8 |
| 5 | ADR-0005 | Agent Lifecycle FSM (6 States) | YES | âœ… Section 2.10 |
| 6 | ADR-0006 | 3-Phase Orchestration | YES | âœ… Section 2.11 |
| 7 | ADR-0007 | 4-Stage Planning Pipeline | YES | âœ… Section 2.12 |
| 8 | ADR-0008 | Saga Pattern Error Recovery | YES | âœ… Section 13.1 |
| 9 | ADR-0009 | Circuit Breaker Pattern | YES | âœ… Section 13.2 |
| 10 | ADR-0010 | Capability-Based Security | YES | âœ… Section 13.3 |
| 11 | ADR-0011 | FlatBuffers Serialization | YES | âœ… Section 14.1 |
| 12 | ADR-0012 | 76 FlatBuffers Schemas | YES | âœ… Section 14.2 |
| 13 | ADR-0013 | Pipeline Versioning Policy | NO | ❌ MISSING |
| 14 | ADR-0014 | JSON REST API Dual Format | YES | âœ… Section 14.3 |
| 15 | ADR-0015 | WebSocket Binary Protocol | YES | âœ… Section 14.4 |
| 16 | ADR-0016 | SSE Event Schemas | YES | âœ… Section 14.5 |
| 17 | ADR-0017 | SessionState 6-Section Design | YES | âœ… Section 3.1 & 14.6 |
| 18 | ADR-0018 | 3-Tier Eviction Strategy | YES | âœ… Section 3.2 & 14.7 |
| 19 | ADR-0019 | FlatBuffers SessionState Serialization | YES | âœ… Section 3.3 |
| 20 | ADR-0020 | Multi-Tier Storage | YES | âœ… Section 3.4 & 14.8 |
| 21 | ADR-0021 | Turn History Retention Policies | YES | âœ… Section 15.1 |
| 22 | ADR-0022 | K0 Bridge Bounded Batching | YES | âœ… Section 4.1 & 15.2 |
| 23 | ADR-0023 | Cursor-Based Turn Pagination | YES | âœ… Section 4.2 & 15.3 |
| 24 | ADR-0024 | Performance Budgets P95 Targets | YES | âœ… Section 15.4 |
| 25 | ADR-0025 | KV Cache Management 512MB | YES | âœ… Section 7.1 & 15.5 |
| 26 | ADR-0026 | Thermal Hysteresis Matrix | YES | âœ… Section 7.2 & 15.6 |
| 27 | ADR-0027 | Model Placement Cascade | YES | âœ… Section 7.2 & 15.7 |
| 28 | ADR-0028 | Weighted Fair Queuing Scheduler | YES | âœ… Section 7.3 & 15.8 |
| 29 | ADR-0029 | Prometheus Metrics RED Method | YES | âœ… Section 7.4 & 15.9 |
| 30 | ADR-0030 | Intelligent Trace Sampling | YES | âœ… Section 7.5 & 15.10 |
| 31 | ADR-0031 | Cost Tracking Per Session | YES | âœ… Section 8.2 & 16.1 |
| 32 | ADR-0032 | Band-Based Egress Rules | YES | âœ… Section 8.2 & 16.2 |
| 33 | ADR-0033 | 3-Tier Tool Execution | YES | âœ… Section 16.3 |
| 34 | ADR-0034 | MCP Protocol for Tool Integration | YES | âœ… Section 16.4 |
| 35 | ADR-0035 | PII Detection & Redaction | YES | âœ… Section 16.5 |
| 36 | ADR-0036 | E2EE for RED Band | YES | âœ… Section 16.6 |
| 37 | ADR-0037 | JWT Authentication | YES | âœ… Section 16.7 |
| 38 | ADR-0038 | Audit Trail to K0 Receipts | YES | âœ… Section 16.8 |
| 39 | ADR-0039 | Privacy Band Overrides | YES | âœ… Section 16.9 |
| 40 | ADR-0040 | WebSocket Real-Time Chat | YES | âœ… Section 16.10 |
| 41 | ADR-0041 | REST API Session Management | PARTIAL | âš ï¸ Section 17.1 (Title only) |
| 42 | ADR-0042 | K0 SSE Event Streaming | PARTIAL | âš ï¸ Section 17.2 (Title only) |
| 43 | ADR-0043 | SSE Topic Taxonomy | PARTIAL | âš ï¸ Section 17.3 (Title only) |
| 44 | ADR-0044 | K0 Bridge HTTP/2 + FlatBuffers | PARTIAL | âš ï¸ Section 17.4 (Title only) |
| 45 | ADR-0045 | Agent-to-Agent SSE Coordination | NO | ❌ MISSING |
| 46 | ADR-0046 | SSE WebSocket Bridge | NO | ❌ MISSING |
| 47 | ADR-0047 | OpenAPI 3.1 REST Specs | NO | ❌ MISSING |
| 48 | ADR-0048 | K1 Internal Event Bus | NO | ❌ MISSING |
| 49 | ADR-0049 | Fast Smart Lane Router Policy | NO | ❌ MISSING |
| 50 | ADR-0050 | Multi-Device Family Sync Strategy | NO | ❌ MISSING |
| 51 | ADR-0052 | Enhanced HITL Protocols | NO | ❌ MISSING |
| 52 | ADR-0053 | Message Queue Coalescing | NO | ❌ MISSING |
| 53 | ADR-0054 | Turn Boundary Management | NO | ❌ MISSING |
| 54 | ADR-0055 | Context Switch Detection | NO | ❌ MISSING |
| 55 | ADR-0056 | Voice Pipeline Implementation | NO | ❌ MISSING |
| 56 | ADR-0057 | Voice-Specific Backpressure | NO | ❌ MISSING |
| 57 | ADR-0058 | Intent Classification Voice | NO | ❌ MISSING |
| 58 | ADR-0059 | Learning Loop | NO | ❌ MISSING |
| 59 | ADR-0060 | Adaptive KV Cache Management | NO | ❌ MISSING |
| 60 | ADR-0061 | 3-Tier Backpressure Cascade | NO | ❌ MISSING |
| 61 | ADR-0065 | Product Craft UX Micro-Interactions | NO | ❌ MISSING |
| 62 | ADR-0066 | Developer Testing Simulation Harness | NO | ❌ MISSING |
| 63 | ADR-0067 | Conversational Delight Factors | NO | ❌ MISSING |
| 64 | ADR-0068 | Voice Quality Measurement | NO | ❌ MISSING |
| 65 | ADR-0069 | P08 Affect Modulation K0 Implementation | NO | ❌ MISSING |
| 66 | ADR-0070 | Observability Evaluation Infrastructure | NO | ❌ MISSING |
| 67 | ADR-0071 | Multilingual Code Switching | NO | ❌ MISSING |

**Summary (Main ADRs Only):**
- âœ… Available: 40
- âš ï¸ Partial: 4
- ❌ Missing: 23
- **Availability Rate: 60.3% (40/67)**

---

## TABLE 2: SUB-ADRs & AVAILABILITY STATUS

| ADR # | Sub # | Full ID | Title | Available in DEPENDENCY_MAP | Status |
|-------|-------|---------|-------|------------------------------|--------|
| 0001 | a | ADR-0001a | K0 Bridge Communication Protocol | YES | âœ… Section 1.2 |
| 0001 | b | ADR-0001b | Model Hub Architecture | YES | âœ… Section 1.2 & 5.2 |
| 0001 | e | ADR-0001e | P21+ Integration Pipeline Layer | YES | âœ… Section 1.2 |
| 0001 | f | ADR-0001f | K0/K1 Pipeline Boundary Enforcement | YES | âœ… Section 1.2 |
| 0002 | a | ADR-0002a | Mailbox MPSC Queue Implementation | YES | âœ… Section 2.2 & 2.3 |
| 0002 | b | ADR-0002b | Supervisor Monitoring & Crash Recovery | YES | âœ… Section 2.2 & 2.4 |
| 0002 | c | ADR-0002c | Actor Router & Admission Control | YES | âœ… Section 2.2 |
| 0002 | d | ADR-0002d | Observability Schema (Actor Messaging) | YES | âœ… Section 2.2 |
| 0003 | a | ADR-0003a | Protocol Definition Language (PDL) | YES | âœ… Section 2.6 |
| 0003 | b | ADR-0003b | 6 Core Protocol Implementations | YES | âœ… Section 2.6 |
| 0003 | c | ADR-0003c | Protocol Monitor Runtime | YES | âœ… Section 2.6 & 2.7 |
| 0003 | d | ADR-0003d | Role Attestation & Capability Verification | YES | âœ… Section 2.6 |
| 0004 | a | ADR-0004a | Layer 1-2 Event Bus Communication | NO | ❌ MISSING |
| 0004 | b | ADR-0004b | Module Dependency Management | NO | ❌ MISSING |
| 0004 | c | ADR-0004c | Module README Template | NO | ❌ MISSING |
| 0004 | d | ADR-0004d | Per-Layer Integration Testing | NO | ❌ MISSING |
| 0005 | a | ADR-0005a | Agent Warming State | YES | âœ… Section 2.10 |
| 0005 | b | ADR-0005b | Agent Idle Pooling | YES | âœ… Section 2.10 |
| 0005 | c | ADR-0005c | Agent Draining & Shutdown | YES | âœ… Section 2.10 |
| 0005 | d | ADR-0005d | Supervisor Blacklist | YES | âœ… Section 2.10 |
| 0005 | e | ADR-0005e | Agent Personality & Capabilities | YES | âœ… Section 2.10 |
| 0006 | a | ADR-0006a | Contract Net Negotiation | YES | âœ… Section 2.12 |
| 0006 | b | ADR-0006b | Multi-Criteria Scoring (Selection) | YES | âœ… Section 2.12 |
| 0006 | c | ADR-0006c | Parallel DAG Execution | YES | âœ… Section 2.12 |
| 0006 | d | ADR-0006d | Saga Pattern Integration | YES | âœ… Section 2.12 |
| 0006 | e | ADR-0006e | Multi-Agent Coordination | YES | âœ… Section 2.12 |
| 0007 | a | ADR-0007a | Sketch Stage (LLM Prompt Engineering) | YES | âœ… Section 2.12 |
| 0007 | b | ADR-0007b | Expand Stage (Tool Registry Integration) | YES | âœ… Section 2.12 |
| 0007 | c | ADR-0007c | Validation Stage (2-Tier Implementation) | YES | âœ… Section 2.12 |
| 0007 | d | ADR-0007d | Commit Stage (K0 WAL Integration) | YES | âœ… Section 2.12 |
| 0008 | a | ADR-0008a | Compensating Transaction Design | NO | ❌ MISSING |
| 0008 | b | ADR-0008b | Forward vs Backward Recovery | NO | ❌ MISSING |
| 0008 | c | ADR-0008c | Distributed State Management | NO | ❌ MISSING |
| 0008 | d | ADR-0008d | Timeout & Deadlock Handling | NO | ❌ MISSING |
| 0009 | a | ADR-0009a | Circuit Breaker FSM Implementation | NO | ❌ MISSING |
| 0009 | b | ADR-0009b | Per-Service Circuit Configuration | NO | ❌ MISSING |
| 0009 | c | ADR-0009c | Circuit Breaker Metrics & Observability | NO | ❌ MISSING |
| 0010 | a | ADR-0010a | Capability Token Design | NO | ❌ MISSING |
| 0010 | b | ADR-0010b | Agent Capability Assignment Policy | NO | ❌ MISSING |
| 0010 | c | ADR-0010c | Capability Enforcement Runtime | NO | ❌ MISSING |
| 0010 | d | ADR-0010d | Capability Revocation & Audit Trail | NO | ❌ MISSING |
| 0011 | a | ADR-0011a | FlatBuffers Schema Design Principles | NO | ❌ MISSING |
| 0011 | b | ADR-0011b | FlatBuffers Code Generation | NO | ❌ MISSING |
| 0011 | c | ADR-0011c | Serialization Performance Zero-Copy | NO | ❌ MISSING |
| 0011 | d | ADR-0011d | Schema Evolution & Versioning | NO | ❌ MISSING |
| 0012 | a | ADR-0012a | Layer 1 Core Kernel Schemas | NO | ❌ MISSING |
| 0012 | b | ADR-0012b | Layer 2 State Persistence Schemas | NO | ❌ MISSING |
| 0012 | c | ADR-0012c | Layer 3 Execution Tools Schemas | NO | ❌ MISSING |
| 0012 | d | ADR-0012d | Layer 4 Ingress Voice Schemas | NO | ❌ MISSING |
| 0012 | e | ADR-0012e | Layer 5 Infrastructure Schemas | NO | ❌ MISSING |
| 0013 | a | ADR-0013a | Schema Version Registry | NO | ❌ MISSING |
| 0013 | b | ADR-0013b | Automated Version Bump Validation | NO | ❌ MISSING |
| 0013 | c | ADR-0013c | 90-Day Deprecation Workflow | NO | ❌ MISSING |
| 0013 | d | ADR-0013d | Contract Testing Compatibility | NO | ❌ MISSING |
| 0014 | a | ADR-0014a | Content Negotiation Middleware | NO | ❌ MISSING |
| 0014 | b | ADR-0014b | OpenAPI Spec Generation | NO | ❌ MISSING |
| 0014 | c | ADR-0014c | Request-Response Serialization | NO | ❌ MISSING |
| 0014 | d | ADR-0014d | Client SDK & Migration Guides | NO | ❌ MISSING |
| 0015 | a | ADR-0015a | WebSocket Message Envelope | NO | ❌ MISSING |
| 0015 | b | ADR-0015b | Flow Control & Backpressure | NO | ❌ MISSING |
| 0015 | c | ADR-0015c | Reconnection & Session Resume | NO | ❌ MISSING |
| 0015 | d | ADR-0015d | Streaming Token Delivery | YES | âœ… Section 5.3 |
| 0015 | e | ADR-0015e | TypeScript Client SDK | NO | ❌ MISSING |
| 0016 | a | ADR-0016a | SSE Event Taxonomy | NO | ❌ MISSING |
| 0016 | b | ADR-0016b | FlatBuffers to JSON Serialization | NO | ❌ MISSING |
| 0016 | c | ADR-0016c | SSE Topic-Based Filtering | NO | ❌ MISSING |
| 0016 | d | ADR-0016d | Browser EventSource Integration | NO | ❌ MISSING |
| 0017 | a | ADR-0017a | Beliefs Section | NO | ❌ MISSING |
| 0017 | b | ADR-0017b | Scoreboard Section | NO | ❌ MISSING |
| 0017 | c | ADR-0017c | Control Section | NO | ❌ MISSING |
| 0017 | d | ADR-0017d | Persona Section | NO | ❌ MISSING |
| 0017 | e | ADR-0017e | Multimodal Section | NO | ❌ MISSING |
| 0017 | f | ADR-0017f | Meta Section | NO | ❌ MISSING |
| 0018 | a | ADR-0018a | Tier 1 Soft Eviction | NO | ❌ MISSING |
| 0018 | b | ADR-0018b | Tier 2 Hard Eviction | NO | ❌ MISSING |
| 0018 | c | ADR-0018c | Tier 3 OOM Prevention | NO | ❌ MISSING |
| 0019 | a | ADR-0019a | SessionState FlatBuffers Schema | NO | ❌ MISSING |
| 0019 | b | ADR-0019b | Delta Serialization Pipeline | NO | ❌ MISSING |
| 0019 | c | ADR-0019c | K0 WAL Integration | NO | ❌ MISSING |
| 0019 | d | ADR-0019d | Zero-Copy Deserialization | NO | ❌ MISSING |
| 0020 | a | ADR-0020a | Hot Tier L1 RAM | NO | ❌ MISSING |
| 0020 | b | ADR-0020b | Warm Tier L2 SSD | NO | ❌ MISSING |
| 0020 | c | ADR-0020c | Cold Tier L3 S3 Archive | NO | ❌ MISSING |
| 0021 | a | ADR-0021a | Retention Policy Engine | NO | ❌ MISSING |
| 0021 | b | ADR-0021b | Privacy Band Retention Overrides | NO | ❌ MISSING |
| 0021 | c | ADR-0021c | Compliance Reporting & Audit | NO | ❌ MISSING |
| 0022 | a | ADR-0022a | Batching Algorithm 10-50 100ms | NO | ❌ MISSING |
| 0022 | b | ADR-0022b | HTTP/2 Multiplexing | NO | ❌ MISSING |
| 0022 | c | ADR-0022c | Backpressure Cascade | NO | ❌ MISSING |
| 0022 | d | ADR-0022d | FlatBuffers Batch Schema | NO | ❌ MISSING |
| 0023 | a | ADR-0023a | Cursor Encoding | NO | ❌ MISSING |
| 0023 | b | ADR-0023b | Pagination REST API | NO | ❌ MISSING |
| 0023 | c | ADR-0023c | K0 WAL Cursor Optimization | NO | ❌ MISSING |
| 0024 | a | ADR-0024a | Turn-Level Performance Budgets | NO | ❌ MISSING |
| 0024 | b | ADR-0024b | Component-Level Budgets | NO | ❌ MISSING |
| 0024 | c | ADR-0024c | Memory Budgets | NO | ❌ MISSING |
| 0024 | d | ADR-0024d | Graceful Degradation | NO | ❌ MISSING |
| 0025 | a | ADR-0025a | Global KV Cache Allocator | NO | ❌ MISSING |
| 0025 | b | ADR-0025b | LRU LFU Hybrid Eviction | NO | ❌ MISSING |
| 0025 | c | ADR-0025c | Cache Warming & Prefetch | NO | ❌ MISSING |
| 0025 | d | ADR-0025d | Zstd Compression | NO | ❌ MISSING |
| 0025 | e | ADR-0025e | Protected Sessions Hit Rate | NO | ❌ MISSING |
| 0026 | a | ADR-0026a | Thermal Sensor Monitoring | NO | ❌ MISSING |
| 0026 | b | ADR-0026b | Hysteresis State Machine | NO | ❌ MISSING |
| 0026 | c | ADR-0026c | Model Placement Integration | NO | ❌ MISSING |
| 0026 | d | ADR-0026d | Throttling Policies | NO | ❌ MISSING |
| 0027 | a | ADR-0027a | Placement Algorithm | NO | ❌ MISSING |
| 0027 | b | ADR-0027b | Automatic Failover | NO | ❌ MISSING |
| 0027 | c | ADR-0027c | Cost-Aware Fallback | NO | ❌ MISSING |
| 0027 | d | ADR-0027d | Remote Resilience | NO | ❌ MISSING |
| 0028 | a | ADR-0028a | WFQ Scheduler Algorithm | NO | ❌ MISSING |
| 0028 | b | ADR-0028b | Priority Classes & Preemption | NO | ❌ MISSING |
| 0028 | c | ADR-0028c | Starvation Prevention | NO | ❌ MISSING |
| 0029 | a | ADR-0029a | RED Method Metric Schema | NO | ❌ MISSING |
| 0029 | b | ADR-0029b | Turn-Level Metrics | NO | ❌ MISSING |
| 0029 | c | ADR-0029c | Component Metrics | NO | ❌ MISSING |
| 0029 | d | ADR-0029d | Infrastructure Metrics | NO | ❌ MISSING |
| 0029 | e | ADR-0029e | Alerting Rules & Grafana | NO | ❌ MISSING |
| 0030 | a | ADR-0030a | Head-Based Sampling Strategy | NO | ❌ MISSING |
| 0030 | b | ADR-0030b | Tail-Based Sampling | NO | ❌ MISSING |
| 0030 | c | ADR-0030c | Adaptive Sampling Rate | NO | ❌ MISSING |
| 0030 | d | ADR-0030d | Trace Storage Jaeger | NO | ❌ MISSING |
| 0031 | a | ADR-0031a | Hierarchical Budget Enforcement | NO | ❌ MISSING |
| 0031 | b | ADR-0031b | Cost Model Pricing | NO | ❌ MISSING |
| 0031 | c | ADR-0031c | Automatic Cost-Based Fallback | NO | ❌ MISSING |
| 0031 | d | ADR-0031d | Cost Observability | NO | ❌ MISSING |
| 0032 | a | ADR-0032a | Network Egress Control | NO | ❌ MISSING |
| 0032 | b | ADR-0032b | Filesystem Egress Control | NO | ❌ MISSING |
| 0032 | c | ADR-0032c | Resource Egress Control | NO | ❌ MISSING |
| 0032 | d | ADR-0032d | Egress Violation Logging | NO | ❌ MISSING |
| 0033 | a | ADR-0033a | MCP Protocol Integration | NO | ❌ MISSING |
| 0033 | b | ADR-0033b | WASM Sandbox | NO | ❌ MISSING |
| 0033 | c | ADR-0033c | Process Sandbox | NO | ❌ MISSING |
| 0033 | d | ADR-0033d | 2D Selection Logic | NO | ❌ MISSING |
| 0034 | a | ADR-0034a | MCP JSON-RPC Protocol | NO | ❌ MISSING |
| 0034 | b | ADR-0034b | MCP Process Lifecycle | NO | ❌ MISSING |
| 0034 | c | ADR-0034c | MCP Circuit Breaker | NO | ❌ MISSING |
| 0034 | d | ADR-0034d | MCP Error Handling | NO | ❌ MISSING |
| 0035 | a | ADR-0035a | Regex Pattern Library | NO | ❌ MISSING |
| 0035 | b | ADR-0035b | ML-Based NER | NO | ❌ MISSING |
| 0035 | c | ADR-0035c | Encrypted Vault | NO | ❌ MISSING |
| 0035 | d | ADR-0035d | Audit Trail GDPR | NO | ❌ MISSING |
| 0036 | a | ADR-0036a | AES256GCM Encryption | NO | ❌ MISSING |
| 0036 | b | ADR-0036b | KMS Integration | NO | ❌ MISSING |
| 0036 | c | ADR-0036c | Selective Encryption | NO | ❌ MISSING |
| 0036 | d | ADR-0036d | Audit Trail Compliance | NO | ❌ MISSING |
| 0037 | a | ADR-0037a | Token Generation & Signing | NO | ❌ MISSING |
| 0037 | b | ADR-0037b | Token Validation & Verification | NO | ❌ MISSING |
| 0037 | c | ADR-0037c | Refresh Token Flow | NO | ❌ MISSING |
| 0037 | d | ADR-0037d | Session Binding Authorization | NO | ❌ MISSING |
| 0038 | a | ADR-0038a | Receipt Generation Schema | NO | ❌ MISSING |
| 0038 | b | ADR-0038b | K0 WAL Integration | NO | ❌ MISSING |
| 0038 | c | ADR-0038c | Retention Policies | NO | ❌ MISSING |
| 0038 | d | ADR-0038d | Query Interface | NO | ❌ MISSING |
| 0039 | a | ADR-0039a | Tier Triggers & Watermarks | NO | ❌ MISSING |
| 0039 | b | ADR-0039b | Backpressure Propagation | NO | ❌ MISSING |
| 0039 | c | ADR-0039c | Recovery & Gradual Resume | NO | ❌ MISSING |
| 0040 | a | ADR-0040a | Connection Management | NO | ❌ MISSING |
| 0040 | b | ADR-0040b | Message Framing | NO | ❌ MISSING |
| 0040 | c | ADR-0040c | Backpressure & Flow Control | NO | ❌ MISSING |
| 0040 | d | ADR-0040d | Heartbeat & Reconnection | NO | ❌ MISSING |
| 0041 | a | ADR-0041a | Session CRUD Resource Design | NO | ❌ MISSING |
| 0041 | b | ADR-0041b | Idempotency & State Sync | NO | ❌ MISSING |
| 0041 | c | ADR-0041c | Pagination | NO | ❌ MISSING |
| 0041 | d | ADR-0041d | OpenAPI RFC7807 Errors | NO | ❌ MISSING |
| 0042 | a | ADR-0042a | K0 SSE Event Production | NO | ❌ MISSING |
| 0042 | b | ADR-0042b | K0 SSE Event Consumption | NO | ❌ MISSING |
| 0042 | c | ADR-0042c | K0 SSE Reconnection | NO | ❌ MISSING |
| 0042 | d | ADR-0042d | K0 SSE Backpressure | NO | ❌ MISSING |
| 0042 | e | ADR-0042e | K0 SSE Device Storage Tiers | NO | ❌ MISSING |
| 0043 | a | ADR-0043a | K0 SSE Topic Hierarchy | NO | ❌ MISSING |
| 0043 | b | ADR-0043b | K0 SSE Topic Subscription | NO | ❌ MISSING |
| 0043 | c | ADR-0043c | K0 SSE Topic Routing | NO | ❌ MISSING |
| 0043 | d | ADR-0043d | K0 SSE Topic ACL | NO | ❌ MISSING |
| 0044 | a | ADR-0044a | HTTP/2 Multiplexing | NO | ❌ MISSING |
| 0044 | b | ADR-0044b | FlatBuffers Serialization | NO | ❌ MISSING |
| 0044 | c | ADR-0044c | Batching Strategy | NO | ❌ MISSING |
| 0044 | d | ADR-0044d | Error Handling & Retry | NO | ❌ MISSING |
| 0045 | a | ADR-0045a | K1 Event Bus PubSub | NO | ❌ MISSING |
| 0045 | b | ADR-0045b | Topic Routing | NO | ❌ MISSING |
| 0045 | c | ADR-0045c | Delivery Guarantees | NO | ❌ MISSING |
| 0045 | d | ADR-0045d | Backpressure Handling | NO | ❌ MISSING |
| 0046 | - | ADR-0046 | SSE WebSocket Bridge | NO | ❌ MISSING |
| 0047 | - | ADR-0047 | OpenAPI 3.1 REST Specs | NO | ❌ MISSING |
| 0048 | - | ADR-0048 | K1 Internal Event Bus | NO | ❌ MISSING |
| 0049 | - | ADR-0049 | Fast Smart Lane Router | NO | ❌ MISSING |
| 0050 | a | ADR-0050a | SessionState Coherence Guarantees | NO | ❌ MISSING |
| 0050 | b | ADR-0050b | CRDT Device-to-Device Merge | NO | ❌ MISSING |
| 0050 | c | ADR-0050c | LAN-First Sync | NO | ❌ MISSING |
| 0050 | d | ADR-0050d | P2P E2EE Internet Sync | NO | ❌ MISSING |
| 0052 | a | ADR-0052a | Step-by-Step Approval | NO | ❌ MISSING |
| 0052 | b | ADR-0052b | Two-Person Rule | NO | ❌ MISSING |
| 0052 | c | ADR-0052c | Nested Clarification Chains | NO | ❌ MISSING |
| 0052 | d | ADR-0052d | Proactive Risk Confirmation | NO | ❌ MISSING |
| 0053 | a | ADR-0053a | Coalesce Window Limits | NO | ❌ MISSING |
| 0053 | b | ADR-0053b | Rate Limits & Bursts | NO | ❌ MISSING |
| 0053 | c | ADR-0053c | Cancel Path P95 | NO | ❌ MISSING |
| 0054 | a | ADR-0054a | Implicit Pause 2s | NO | ❌ MISSING |
| 0054 | b | ADR-0054b | Explicit Submit UX | NO | ❌ MISSING |
| 0054 | c | ADR-0054c | MPST Turn Transitions | NO | ❌ MISSING |
| 0055 | a | ADR-0055a | Intent Drift Rules | NO | ❌ MISSING |
| 0055 | b | ADR-0055b | Switch Prompt | NO | ❌ MISSING |
| 0055 | c | ADR-0055c | History Keep Clear | NO | ❌ MISSING |
| 0056 | a | ADR-0056a | ASR Ingress | NO | ❌ MISSING |
| 0056 | b | ADR-0056b | Intent Bridge | NO | ❌ MISSING |
| 0056 | c | ADR-0056c | Tool Interleaving | NO | ❌ MISSING |
| 0056 | d | ADR-0056d | TTS Synthesis | NO | ❌ MISSING |
| 0056 | e | ADR-0056e | Audio Out | NO | ❌ MISSING |
| 0057 | a | ADR-0057a | ASR Frame Drop | NO | ❌ MISSING |
| 0057 | b | ADR-0057b | TTS Degradation Ladder | NO | ❌ MISSING |
| 0057 | c | ADR-0057c | Barge-In Preemption | YES | âœ… Section 6.2 |
| 0058 | a | ADR-0058a | Confidence Thresholds | NO | ❌ MISSING |
| 0058 | b | ADR-0058b | Safety Hooks | NO | ❌ MISSING |
| 0059 | a | ADR-0059a | Feedback Signal Taxonomy | NO | ❌ MISSING |
| 0059 | b | ADR-0059b | Drift Detection | NO | ❌ MISSING |
| 0059 | c | ADR-0059c | Planner Parameter Contracts | NO | ❌ MISSING |
| 0059 | d | ADR-0059d | Audit Rollback | NO | ❌ MISSING |
| 0059 | e | ADR-0059e | Synthetic Data Pipeline | NO | ❌ MISSING |
| 0060 | a | ADR-0060a | Dynamic Placement & Sizing | NO | ❌ MISSING |
| 0060 | b | ADR-0060b | Hot Cold Eviction Recovery | NO | ❌ MISSING |
| 0061 | a | ADR-0061a | Watermark Thresholds | NO | ❌ MISSING |
| 0061 | b | ADR-0061b | RED Metrics & Alerts | NO | ❌ MISSING |
| 0061 | c | ADR-0061c | Privacy Band Overrides | NO | ❌ MISSING |
| 0061 | d | ADR-0061d | Fairness & Anti-Starvation | NO | ❌ MISSING |
| 0065 | a | ADR-0065a | Streaming Text Typing | NO | ❌ MISSING |
| 0065 | b | ADR-0065b | Session Continuity | NO | ❌ MISSING |
| 0065 | c | ADR-0065c | Quick Actions | NO | ❌ MISSING |
| 0065 | d | ADR-0065d | Costly Action Confirmation | NO | ❌ MISSING |
| 0066 | - | ADR-0066 | Developer Testing Harness | NO | ❌ MISSING |
| 0067 | - | ADR-0067 | Conversational Delight Factors | NO | ❌ MISSING |
| 0068 | - | ADR-0068 | Voice Quality Measurement | NO | ❌ MISSING |
| 0069 | - | ADR-0069 | P08 Affect Modulation | NO | ❌ MISSING |
| 0070 | - | ADR-0070 | Observability Evaluation | NO | ❌ MISSING |
| 0071 | - | ADR-0071 | Multilingual Code Switching | NO | ❌ MISSING |

**Summary (Sub-ADRs Only):**
- âœ… Available: 28
- âš ï¸ Partial: 0
- ❌ Missing: 138
- **Availability Rate: 16.9% (28/166)**

---

## OVERALL SUMMARY

| Category | Count | Percentage |
|----------|-------|-----------|
| **Total ADRs (Main + Sub)** | 209 | 100% |
| **Available in DEPENDENCY_MAP** | 68 | 32.5% |
| **Partially Documented** | 4 | 1.9% |
| **Missing from DEPENDENCY_MAP** | 137 | 65.6% |

### Key Findings

1. **Main ADRs Coverage:** 60.3% (40/67) main ADRs are documented in DEPENDENCY_MAP.md
   - Well covered: ADR-0001 through ADR-0040 (Kernel, Architecture, Serialization, State, Infrastructure, Security, APIs)
   - Partially covered: ADR-0041 through ADR-0044 (titles only, no details)
   - Missing: ADR-0045 onward (Agent coordination, Voice, Learning, Product/UX, Developer experience)

2. **Sub-ADRs Coverage:** 16.9% (28/166) sub-ADRs are documented
   - Most sub-ADRs are missing detail sections
   - Only foundational sub-ADRs (0001a-f, 0002a-d, 0003a-d, 0005a-e, 0006a-e, 0007a-d, 0015d, 0057c) are documented

3. **Critical Gaps:**
   - **No detailed coverage:** Batch 6-7 (ADR-0041 to ADR-0071) - 31 main ADRs missing
   - **Learning Loop:** ADR-0059 completely missing (feedback, drift detection, rollback)
   - **Voice Pipeline:** ADR-0056 through ADR-0058 missing (ASR, TTS, voice-specific backpressure)
   - **Multi-Device Sync:** ADR-0050 missing (CRDT, family sync, device coherence)
   - **Product & Developer Experience:** ADR-0065 through ADR-0071 all missing

### Recommendations

1. **Immediate Actions:**
   - Complete ADR-0041 through ADR-0044 (finish partial documentation)
   - Document Batch 6 (ADR-0041 to ADR-0050) - Critical ingress/coordination layer
   - Document Batch 7 (ADR-0051 to ADR-0071) - Voice, Learning, Product features

2. **Documentation Priority:**
   - **CRITICAL:** ADR-0045 (Agent coordination), ADR-0048 (K1 event bus), ADR-0056 (Voice)
   - **HIGH:** ADR-0050 (Multi-device sync), ADR-0059 (Learning loop)
   - **MEDIUM:** ADR-0065+ (Product features, developer experience)

3. **Sub-ADR Documentation:**
   - Add detail sections for all 138 missing sub-ADRs
   - Create standardized template for sub-ADR documentation
   - Link sub-ADRs to parent ADRs with explicit parent-child relationships
