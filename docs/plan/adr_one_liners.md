# ADR One-Liners — K1 Agentic Kernel Master Reference

**Purpose:** Single-line summaries of all 206 ADRs for quick reference and dependency mapping.
**Last Updated:** 2025-10-16
**Total ADRs:** 206 (0001-0065 + sub-ADRs)
**Format:** ADR_ID | Title | One-Line Purpose

---

## Tier-1: Foundational Architecture (ADR-0001 to ADR-0004)

| ADR | One-Liner |
|-----|-----------|
| **0001** | Dual-kernel microkernel architecture: K0 (memory pipelines) + K1 (agentic orchestration) with clear state boundaries |
| **0001a** | K0-K1 bridge communication protocol supporting dual transports: JSON (primary) + FlatBuffers (binary optimization) |
| **0001b** | Model Hub architecture providing multi-LLM integration layer with model versioning, fallback, and cost-aware placement |
| **0001e** | P21+ integration pipeline layer extending K0 pipeline ecosystem beyond P01-P20 with plugin architecture |
| **0001f** | K0/K1 boundary enforcement mechanism preventing K1 from directly mutating memory state or hosting cognitive pipelines |
| **0002** | Actor Model for agent isolation using message-passing concurrency with supervisor trees and crash recovery |
| **0002a** | Mailbox MPSC queue implementation providing lock-free message buffering with backpressure and ordering guarantees |
| **0002b** | Supervisor monitoring & crash recovery enabling health checks, crash detection, blacklisting, and agent restart |
| **0002c** | Actor router with admission control implementing fair message routing, priority lanes, and load shedding |
| **0002d** | Observability schema for actor messaging capturing metrics, traces, and logs with cognitive trace IDs |
| **0003** | MPST protocol validation framework ensuring protocol safety through multiparty session types with static checking |
| **0003a** | Protocol Definition Language (PDL) specification enabling formal protocol description and automated validation |
| **0003b** | 6 core protocol implementations: Agent Hire, Task Execution, Clarification, Barge-In, Tool Call, Saga Rollback |
| **0003c** | Protocol Monitor runtime implementation enforcing protocol compliance with timeout, state, and role validation |
| **0003d** | Role attestation & capability verification providing role-based security enforcement at runtime |
| **0004** | 52-module 5-layer microkernel architecture organizing K1 into logical layers with defined responsibilities |
| **0004a** | Layer 1-2 event bus communication enabling inter-layer messaging with pub/sub semantics and delivery guarantees |
| **0004b** | Module dependency management with import linting preventing cyclic dependencies and enforcing module boundaries |
| **0004c** | Module README template auto-generating documentation with ADR references, contracts, and integration guidance |
| **0004d** | Per-layer integration testing strategy defining layer-specific WARD test patterns and coverage requirements |

---

## Tier-2: Agent Lifecycle & Orchestration (ADR-0005 to ADR-0006)

| ADR | One-Liner |
|-----|-----------|
| **0005** | Agent Lifecycle FSM with 6 states (PENDING→WARMING→ACTIVE→IDLE→DRAINING→TERMINATED) enabling agent pooling and graceful shutdown |
| **0005a** | Agent WARMING state implementing model preloading, KV cache warming, and capability validation before ACTIVE transition |
| **0005b** | Agent IDLE pooling enabling fast reactivation from idle pool with state retention and minimal transition time |
| **0005c** | Agent DRAINING & graceful shutdown completing pending tasks before termination with forced timeout fallback |
| **0005d** | Supervisor monitoring & blacklist enforcing health checks, crash thresholds, and time-windowed agent blacklisting |
| **0005e** | Agent personality & capability system enabling persona prompts, capability tokens, and skill-based hiring |
| **0006** | 3-phase orchestration (Negotiation→Selection→Execution) using Contract Net Protocol for multi-agent task coordination |
| **0006a** | Contract Net negotiation phase where orchestrator announces tasks and agents submit proposals with binding commitments |
| **0006b** | Multi-criteria proposal scoring combining capability match, latency prediction, cost, and specialization signals |
| **0006c** | Parallel DAG execution enabling concurrent task execution with dependency ordering and resource coordination |
| **0006d** | Saga pattern integration enabling distributed transaction semantics with automatic compensating transaction rollback |
| **0006e** | Multi-agent parallel coordination enabling future multi-agent collaboration with consensus and conflict resolution |

---

## Tier-2: Planning Pipeline (ADR-0007)

| ADR | One-Liner |
|-----|-----------|
| **0007** | 4-stage planning pipeline (Sketch→Expand→Validate→Commit) combining LLM creativity with deterministic validation |
| **0007a** | Sketch stage LLM prompt engineering generating initial plan sketches with tool hints and constraint awareness |
| **0007b** | Expand stage tool/prompt registry integration selecting tools, building tool invocations, and expanding tool chains |
| **0007c** | Validation stage 2-tier implementation using rule-based checks + arbiter for safety, compliance, and feasibility |
| **0007d** | Commit stage K0 WAL integration persisting validated plans to K0 write-ahead log with durability guarantees |

---

## Tier-3: Error Recovery & Resilience (ADR-0008 to ADR-0009)

| ADR | One-Liner |
|-----|-----------|
| **0008** | Saga pattern for error recovery enabling atomic multi-step operations with backward recovery via compensating transactions |
| **0008a** | Compensating transaction design ensuring idempotent compensation handlers with deterministic state rollback |
| **0008b** | Forward vs backward recovery strategy selecting appropriate recovery approach based on failure type and idempotency |
| **0008c** | Distributed state management tracking saga state across agents with coordinator oversight and timeout handling |
| **0008d** | Timeout & deadlock handling enforcing timeouts, detecting deadlocks, and triggering compensating transactions |
| **0009** | Circuit Breaker pattern preventing cascading failures with automatic failover and graceful degradation |
| **0009a** | Circuit Breaker 3-state FSM (CLOSED→OPEN→HALF_OPEN) with state transitions based on failure thresholds |
| **0009b** | Per-service circuit configuration enabling service-specific thresholds, recovery times, and degradation policies |
| **0009c** | Circuit Breaker metrics & observability exposing state transitions, failure rates, and recovery metrics |

---

## Tier-3: Security & Capabilities (ADR-0010, ADR-0032-0038)

| ADR | One-Liner |
|-----|-----------|
| **0010** | Capability-based security using unforgeable tokens for least-privilege access without ambient authority |
| **0010a** | Capability token design & lifecycle managing token generation, expiration, revocation, and delegation |
| **0010b** | Agent capability assignment policy distributing capabilities based on role and task requirements |
| **0010c** | Capability enforcement at runtime validating capabilities at every permission check with audit logging |
| **0010d** | Capability revocation & audit trail enabling immediate revocation with comprehensive audit history |
| **0032** | Band-based egress rules (GREEN/AMBER/RED) implementing privacy-aware resource access control |
| **0032a** | Network egress control using iptables to enforce band-based network restrictions per agent |
| **0032b** | Filesystem egress control using chroot/seccomp to sandbox filesystem access per privacy band |
| **0032c** | Resource egress control using cgroups to enforce resource limits and prevent resource starvation |
| **0032d** | Egress violation logging capturing all egress violations with context for security audit and compliance |
| **0033** | Three-tier sandbox strategy layering Protocol (MCP) + Sandbox (WASM/Process) + Band enforcement |
| **0033a** | MCP protocol integration providing standard Model Context Protocol layer for tool communication |
| **0033b** | WASM sandbox implementation enabling sandboxed tool execution within WebAssembly virtual machine |
| **0033c** | Process sandbox implementation providing OS-level process isolation with seccomp and namespace isolation |
| **0033d** | 2D selection logic (Protocol × Sandbox) selecting optimal sandbox layer based on tool requirements |
| **0034** | MCP protocol for tool sandboxing implementing MCP JSON-RPC 2.0 with process lifecycle management |
| **0034a** | MCP JSON-RPC 2.0 protocol implementing JSON-RPC 2.0 specification with MCP-specific extensions |
| **0034b** | MCP process lifecycle managing tool process startup, monitoring, and graceful shutdown |
| **0034c** | MCP circuit breaker integration applying circuit breaker pattern to MCP tool invocations |
| **0034d** | MCP error handling & recovery implementing retry logic, timeout handling, and graceful degradation |
| **0035** | PII detection & redaction automatically detecting and protecting personally identifiable information |
| **0035a** | Regex pattern library providing structured PII detection patterns for common data types |
| **0035b** | ML-based NER enabling unstructured PII detection using Named Entity Recognition models |
| **0035c** | Encrypted PII vault securing detected PII with encryption and KMS key management |
| **0035d** | Audit trail & GDPR compliance logging PII operations for compliance reporting and data subject rights |
| **0036** | E2EE for RED band implementing end-to-end encryption for highest privacy classifications |
| **0036a** | AES-256-GCM encryption implementing authenticated encryption with AES-256 in GCM mode |
| **0036b** | KMS integration & key lifecycle managing encryption keys with centralized key management service |
| **0036c** | Selective encryption & SessionState integration encrypting sensitive SessionState fields at field level |
| **0036d** | Audit trail & compliance logging recording all encryption operations for compliance audits |
| **0037** | JWT authentication implementing token-based authentication with JWT specifications |
| **0037a** | Token generation & signing generating JWT tokens signed with asymmetric cryptography |
| **0037b** | Token validation & verification validating JWT signatures and checking expiration/claims |
| **0037c** | Refresh token flow & rotation managing token refresh with automatic rotation and expiration |
| **0037d** | Session binding & authorization binding tokens to sessions and enforcing authorization rules |
| **0038** | Audit trail to K0 receipts creating immutable audit trail via K0 receipt persistence |
| **0038a** | Receipt generation & schema defining receipt format capturing operation, actor, and result |
| **0038b** | K0 WAL integration & async writes persisting receipts to K0 storage asynchronously |
| **0038c** | Retention policies & auto-deletion managing receipt lifecycle with configurable retention |
| **0038d** | Query interface & compliance export providing query API and compliance data export |

---

## Tier-3: Serialization & Data Formats (ADR-0011-0016)

| ADR | One-Liner |
|-----|-----------|
| **0011** | FlatBuffers serialization framework providing efficient binary serialization with zero-copy deserialization |
| **0011a** | FlatBuffers schema design principles defining best practices for schema design and evolution |
| **0011b** | FlatBuffers code generation integration automating schema-to-code generation and type safety |
| **0011c** | Serialization performance & zero-copy enabling zero-copy deserialization and minimal memory overhead |
| **0011d** | Schema evolution & versioning managing schema changes with backward/forward compatibility |
| **0012** | 76 FlatBuffers schemas across 5 layers providing comprehensive schema coverage for all K1 components |
| **0012a** | Layer1 core kernel schemas (15 schemas) defining actor, orchestrator, planner, protocol monitor schemas |
| **0012b** | Layer2 state persistence schemas (18 schemas) defining SessionState, storage, and cache schemas |
| **0012c** | Layer3 execution & tools schemas (16 schemas) defining tool, model, execution plan schemas |
| **0012d** | Layer4 ingress & voice schemas (14 schemas) defining API, WebSocket, SSE, voice schemas |
| **0012e** | Layer5 infrastructure schemas (13 schemas) defining observability, bridge, config schemas |
| **0013** | Pipeline versioning & compatibility policy managing version evolution with deprecation workflow |
| **0013a** | Schema version registry & compatibility matrix tracking versions and validating compatibility |
| **0013b** | Automated version bump & validation automatically bumping versions and validating compatibility |
| **0013c** | 90-day deprecation workflow & notifications providing deprecation timeline and notifications |
| **0013d** | Contract testing & compatibility validation using Pact-style contract tests for compatibility |
| **0014** | JSON REST API with dual format support supporting both JSON and FlatBuffers formats |
| **0014a** | Content negotiation & format detection automatically selecting serialization format based on client |
| **0014b** | OpenAPI spec generation from FlatBuffers auto-generating OpenAPI specs from schemas |
| **0014c** | Request/response serialization pipeline implementing serialization for REST endpoints |
| **0014d** | Client SDK examples & migration guides providing SDKs and migration documentation |
| **0015** | WebSocket binary protocol implementing binary protocol for WebSocket communication |
| **0015a** | WebSocket message envelope & routing defining message format and routing rules |
| **0015b** | Flow control & backpressure implementing credit-based flow control for WebSocket |
| **0015c** | Reconnection & session resume enabling graceful reconnection with session state recovery |
| **0015d** | Streaming token delivery & heartbeat streaming tokens with heartbeat to maintain connection |
| **0015e** | TypeScript client SDK for browser providing browser-based TypeScript client library |
| **0016** | SSE event schemas & streaming implementing Server-Sent Events for real-time updates |
| **0016a** | SSE event taxonomy & schema design defining event types and schema structure |
| **0016b** | FlatBuffers to JSON serialization for SSE converting FlatBuffers to JSON for SSE delivery |
| **0016c** | SSE topic-based filtering enabling topic subscriptions and content filtering |
| **0016d** | Browser EventSource integration integrating with browser EventSource API |

---

## Tier-4: SessionState & Storage (ADR-0017-0023)

| ADR | One-Liner |
|-----|-----------|
| **0017** | SessionState 6-section design organizing state into Beliefs, Scoreboard, Control, Persona, Multimodal, Meta |
| **0017a** | Beliefs section capturing user facts, preferences, and domain knowledge with schema validation |
| **0017b** | Scoreboard section capturing common ground, question under discussion, and topic tracking |
| **0017c** | Control section managing agent leases, flow control, and execution state |
| **0017d** | Persona section encoding personality traits, communication style, and behavioral preferences |
| **0017e** | Multimodal section capturing audio features, vision embeddings, and temporal alignment |
| **0017f** | Meta section recording telemetry, metrics, and observability data |
| **0018** | 3-tier eviction strategy (soft/hard/OOM) providing graceful degradation as memory pressure increases |
| **0018a** | Tier 1 soft eviction reducing cache size and prefetching less frequently accessed data |
| **0018b** | Tier 2 hard eviction evicting entire session caches with user notification |
| **0018c** | Tier 3 OOM prevention emergency eviction preventing out-of-memory crashes |
| **0019** | FlatBuffers SessionState serialization efficiently serializing SessionState with delta encoding |
| **0019a** | SessionState FlatBuffers schema defining schema for 6-section SessionState structure |
| **0019b** | Delta serialization pipeline enabling efficient incremental updates via delta compression |
| **0019c** | K0 WAL integration persisting SessionState to K0 write-ahead log with durability |
| **0019d** | Zero-copy deserialization enabling in-place access without copying deserialized data |
| **0020** | Multi-tier storage (L1/L2/L3) implementing hot/warm/cold storage strategy |
| **0020a** | Hot tier L1 (RAM) managing in-memory active sessions with LRU eviction |
| **0020b** | Warm tier L2 (SSD K0 WAL) persisting warm sessions to SSD for fast retrieval |
| **0020c** | Cold tier L3 (Object store S3) archiving cold sessions to S3 for long-term retention |
| **0021** | Turn history retention policies managing retention based on policy engine and compliance rules |
| **0021a** | Retention policy engine executing lifecycle rules for automatic turn cleanup |
| **0021b** | Privacy band retention overrides enabling special retention rules for sensitive privacy bands |
| **0021c** | Compliance reporting & audit trail generating compliance reports and audit trails |
| **0022** | K0 bridge bounded batching (10-50 msgs 100ms) batching messages for efficient K0 communication |
| **0022a** | Batching algorithm implementing 10-50 message batching with 100ms timeout |
| **0022b** | HTTP/2 multiplexing enabling connection multiplexing for efficient bandwidth usage |
| **0022c** | Backpressure cascade triggering backpressure when K0 queue exceeds 80% |
| **0022d** | FlatBuffers batch schema & zero-copy enabling zero-copy batch serialization |
| **0023** | Cursor-based turn pagination enabling efficient pagination of turn history |
| **0023a** | Cursor encoding & opaque token design defining cursor format and encoding |
| **0023b** | Pagination REST API (turns cursor limit) implementing pagination endpoint |
| **0023c** | K0 WAL cursor-based query optimization optimizing cursor queries on K0 WAL |

---

## Tier-5: Performance & Infrastructure (ADR-0024-0031)

| ADR | One-Liner |
|-----|-----------|
| **0024** | Performance budgets & P95 targets defining latency and memory budgets for all components |
| **0024a** | Turn-level performance budgets (TTFT E2E Barge-in) defining end-to-end turn latency budgets |
| **0024b** | Component-level performance budgets defining per-component latency targets |
| **0024c** | Memory budgets & resource limits defining per-session and global memory limits |
| **0024d** | Graceful degradation & budget pressure handling responding to budget pressure with quality reduction |
| **0025** | KV cache management (512MB budget) managing attention caches within 512MB global budget |
| **0025a** | Global KV cache allocator implementing centralized cache allocation with quota enforcement |
| **0025b** | LRU-LFU hybrid eviction (60-40) combining LRU and LFU for optimal cache hit rate |
| **0025c** | Cache warming & prefetch enabling session resume via proactive cache prefetching |
| **0025d** | Zstd compression for inactive caches compressing inactive caches achieving 70% reduction |
| **0025e** | Protected sessions & hit rate monitoring protecting high-value sessions and monitoring cache health |
| **0026** | Thermal hysteresis matrix managing thermal state transitions with 5C buffer |
| **0026a** | Thermal sensor monitoring detecting thermal state and publishing events |
| **0026b** | Hysteresis state machine implementing state machine with 5C buffer to prevent oscillation |
| **0026c** | Model placement integration triggering model migration on thermal state change |
| **0026d** | Throttling policies & user notifications notifying users of thermal throttling |
| **0027** | Model placement cascade cascading model placement based on thermal and cost signals |
| **0027a** | Placement algorithm (NPU GPU CPU Remote) selecting placement based on availability and performance |
| **0027b** | Automatic failover (100ms migration) enabling failover with <100ms migration time |
| **0027c** | Cost-aware fallback using cost signals to select cost-effective placement |
| **0027d** | Remote resilience (3 retries 10s timeout) providing resilience for remote execution |
| **0028** | Weighted Fair Queuing scheduler implementing WFQ scheduler for fair task scheduling |
| **0028a** | WFQ scheduler algorithm implementing virtual time algorithm for weighted fairness |
| **0028b** | Priority classes & preemption enabling priority-based preemption of lower priority tasks |
| **0028c** | Starvation prevention (Max Wait 5s) preventing task starvation with 5s max wait guarantee |
| **0029** | Prometheus metrics (RED Method) exposing metrics using RED method (Rate Errors Duration) |
| **0029a** | RED method metric schema (Rate Errors Duration) defining RED metric structure |
| **0029b** | Turn-level metrics (TTFT E2E Barge-in) exposing turn-level performance metrics |
| **0029c** | Component metrics (Agent Orchestrator Planner Tool) exposing component-specific metrics |
| **0029d** | Infrastructure metrics (KV Cache Thermal Memory CPU) exposing infrastructure metrics |
| **0029e** | Alerting rules & Grafana dashboards defining alert rules and dashboard templates |
| **0030** | Intelligent trace sampling intelligently sampling traces based on multiple strategies |
| **0030a** | Head-based sampling (1% baseline 100% errors) sampling at ingestion time |
| **0030b** | Tail-based sampling (60s buffering post-decision) buffering spans for tail-based decisions |
| **0030c** | Adaptive sampling (1%-50% dynamic) adapting sample rate based on system load |
| **0030d** | Trace storage Jaeger (7d hot 30d warm) storing traces with tiered retention |
| **0031** | Cost tracking per-session tracking costs across sessions and budget levels |
| **0031a** | Hierarchical budget enforcement enforcing budgets at corporate/team/user levels |
| **0031b** | Cost model & pricing configuration defining cost model and pricing |
| **0031c** | Automatic cost-based fallback falling back on cost constraints |
| **0031d** | Cost observability & metrics exposing cost metrics and reporting |

---

## Tier-4: API Contracts (ADR-0040-0041)

| ADR | One-Liner |
|-----|-----------|
| **0040** | WebSocket realtime chat API implementing WebSocket protocol for real-time chat |
| **0040a** | Connection management & authentication managing WebSocket connections and authentication |
| **0040b** | Message framing & FlatBuffers protocol defining WebSocket message format and framing |
| **0040c** | Backpressure & flow control implementing credit-based flow control for WebSocket |
| **0040d** | Heartbeat & reconnection implementing heartbeat and automatic reconnection |
| **0041** | REST API session management implementing REST API for session CRUD operations |
| **0041a** | Session CRUD & resource design defining session resource and CRUD operations |
| **0041b** | Idempotency & state synchronization ensuring idempotent operations with state sync |
| **0041c** | Cursor-based pagination (listing) implementing cursor-based pagination for list endpoints |
| **0041d** | OpenAPI spec & RFC7807 errors defining OpenAPI spec and error format |

---

## Tier-5: K0 Integration & Bridge (ADR-0042-0048)

| ADR | One-Liner |
|-----|-----------|
| **0042** | K0 SSE event streaming implementing Server-Sent Events for K0 event publication |
| **0042a** | K0 SSE event production publishing events to SSE topics with ordering guarantees |
| **0042b** | K0 SSE event consumption consuming events from SSE with subscription management |
| **0042c** | K0 SSE reconnection & replay enabling reconnection with event replay from checkpoint |
| **0042d** | K0 SSE backpressure & persistence implementing backpressure and persistent queue |
| **0042e** | K0 SSE device storage tiers storing SSE events in device storage tiers |
| **0043** | SSE topic taxonomy defining topic hierarchy and naming conventions for K0 SSE |
| **0043a** | K0 SSE topic hierarchy organizing topics into hierarchy for organization |
| **0043b** | K0 SSE topic subscription managing topic subscriptions and filtering |
| **0043c** | K0 SSE topic routing routing topics to subscribers with filtering |
| **0043d** | K0 SSE topic ACLs enforcing access control on topic subscriptions |
| **0044** | K0 bridge HTTP/2 & FlatBuffers implementing K0 bridge over HTTP/2 |
| **0044a** | HTTP/2 multiplexing enabling multiplexing over HTTP/2 streams |
| **0044b** | FlatBuffers serialization serializing bridge messages with FlatBuffers |
| **0044c** | Batching strategy batching messages for efficient transmission |
| **0044d** | Error handling & retry implementing retry and error handling |
| **0045** | Agent-agent SSE coordination enabling agent-to-agent coordination via SSE |
| **0045a** | K1 internal event bus (pub/sub) implementing pub/sub for internal events |
| **0045b** | Topic routing mechanism routing events to subscribers by topic |
| **0045c** | Delivery guarantees enforcing delivery semantics (at-least-once) |
| **0045d** | Backpressure handling implementing backpressure in event bus |
| **0046** | SSE WebSocket bridge bridging SSE and WebSocket protocols |
| **0047** | OpenAPI 3.1 REST specifications auto-generating OpenAPI specs |
| **0048** | K1 internal event bus implementing internal pub/sub event bus for K1 |
| **0049** | Fast/smart lane router policy implementing fast/smart lane router policies |
| **0050** | Multi-Device Family Sync Strategy coordinating multi-device sync across LAN and E2EE internet phases |
| **0050a** | SessionState Coherence Guarantees ensuring per-device coherence (RYW, Monotonic, Bounded) prerequisite for multi-device sync |
| **0050b** | CRDT Device-to-Device Merge implementing deterministic merge algorithm (LWW + vector clocks) for state convergence |
| **0050c** | LAN-First Sync Implementation enabling Phase 1 sync via mDNS discovery + TCP P07 + 5s polling loop |
| **0050d** | P2P E2EE Internet Sync enabling Phase 2 sync with device certificates + STUN + QUIC + ChaCha20-Poly1305 |

---

## Tier-0: HITL Extensions (ADR-0052-0055)

| ADR | One-Liner |
|-----|-----------|
| **0052** | Enhanced HITL protocols (umbrella) consolidating human-in-the-loop protocol extensions |
| **0052a** | Step-by-step approval protocol enabling user approval at each plan step |
| **0052b** | Red-band two-person approval enforcing two-person rule for RED band actions |
| **0052c** | Nested clarification chains enabling clarification requests during execution |
| **0052d** | Proactive risk confirmation asking users to confirm uncertain actions |
| **0053** | Message queue & coalescing coalescing rapid user messages into batches |
| **0053a** | Coalesce window & limits defining coalescing window and batch limits |
| **0053b** | Rate limits & bursts implementing rate limiting with burst allowance |
| **0053c** | Cancel path P95 achieving P95 cancel latency target |
| **0054** | Turn boundary management managing implicit/explicit turn boundaries |
| **0054a** | Implicit pause (2s) pausing on 2s user silence |
| **0054b** | Explicit submit UX providing explicit submit button for turn submission |
| **0054c** | MPST turn transitions implementing protocol transitions at turn boundaries |
| **0055** | Context switch detection detecting user intent changes during session |
| **0055a** | Intent drift rules defining rules for intent change detection |
| **0055b** | Switch prompt prompting user on detected intent change |
| **0055c** | History keep/clear clearing history on intent switch if needed |

---

## Tier-1: Production Extensions (ADR-0056-0061)

| ADR | One-Liner |
|-----|-----------|
| **0056** | Voice pipeline implementation implementing end-to-end voice interaction pipeline |
| **0056a** | ASR (Automatic Speech Recognition) implementing speech-to-text conversion |
| **0056b** | Intent bridge bridging ASR output to intent classification |
| **0056c** | Tool interleaving enabling tool invocation during voice interaction |
| **0056d** | TTS synthesis implementing text-to-speech synthesis |
| **0056e** | Audio output streaming synthesized audio to user |
| **0057** | Voice-specific backpressure implementing backpressure strategies for voice |
| **0057a** | ASR frame drop dropping ASR frames on input overload |
| **0057b** | TTS degradation ladder degrading TTS quality on resource constraints |
| **0057c** | Barge-in preemption preempting speech on user barge-in |
| **0058** | Intent classification (voice) classifying intent from voice input |
| **0058a** | Confidence thresholds defining confidence thresholds for intent classification |
| **0058b** | Safety hooks enforcing safety constraints in voice intent classification |
| **0059** | Learning loop (K0 advisory) enabling K1 to provide learning signals to K0 |
| **0059a** | Feedback signal taxonomy defining feedback signal types and semantics |
| **0059b** | Drift detection detecting model drift in K0 pipelines |
| **0059c** | Planner parameter contracts defining planner parameter adaptation contracts |
| **0059d** | Audit & rollback enabling audit and rollback of parameter changes |
| **0059e** | Synthetic data pipeline generating synthetic training data from interactions |
| **0060** | Adaptive KV cache management adaptively resizing KV cache based on usage |
| **0060a** | Dynamic placement & sizing dynamically placing and sizing KV caches |
| **0060b** | Hot/cold eviction & recovery evicting and recovering cache tiers |
| **0061** | 3-tier backpressure cascade implementing 3-tier backpressure strategy |
| **0061a** | Watermark thresholds defining watermark thresholds for backpressure tiers |
| **0061b** | RED metrics & alerts exposing metrics and firing alerts for backpressure |
| **0061c** | Privacy band overrides overriding band restrictions under backpressure |
| **0061d** | Fairness & anti-starvation preventing fairness violations and starvation |

---

## Tier-3: Product & UX (ADR-0065)

| ADR | One-Liner |
|-----|-----------|
| **0065** | Product craft UX micro-interactions consolidating UX micro-interaction guidelines |
| **0065a** | Streaming text typing animation animating text streaming with typing effect |
| **0065b** | Session continuity & device handoff enabling session handoff between devices |
| **0065c** | Quick actions & suggested replies providing quick action and reply suggestions |
| **0065d** | Costly action confirmation confirming costly operations before execution |

---

## Tier-1: Developer Tooling & Quality Assurance (ADR-0066)

| ADR | One-Liner |
|-----|-----------|
| **0066** | Developer testing & simulation harness providing testing infrastructure for AI agent interactions and LLM eval |
| **0066a** | LLM eval framework & prompt testing enabling prompt versioning, output comparison, and quality metric tracking |
| **0066b** | Synthetic user simulation generating synthetic user personas for diverse conversation scenarios |
| **0066c** | Regression testing & quality metrics detecting quality degradation with automated threshold validation |

---

## Tier-1: User Experience & Personality (ADR-0067)

| ADR | One-Liner |
|-----|-----------|
| **0067** | Conversational delight factors balancing personality warmth with appropriateness (10% humor optimal) |
| **0067a** | Template-based humor & Easter eggs curating 50+ humor templates with randomness control and rotation |
| **0067b** | Family-age-mix content filtering filtering delight content based on family age distribution |
| **0067c** | Delight frequency & randomness control tuning frequency (10% target) and preventing joke repetition |

---

## Tier-1: Voice Quality & Measurement (ADR-0068)

| ADR | One-Liner |
|-----|-----------|
| **0068** | Voice quality measurement (ASR WER + TTS MOS) automating ASR accuracy and TTS naturalness evaluation |
| **0068a** | ASR WER evaluation & regression detection computing word error rate with edit distance and regression alerts |
| **0068b** | TTS MOS estimation & monitoring estimating mean opinion score for TTS quality assessment |
| **0068c** | Environmental sensitivity analysis tracking voice quality by environment (quiet/noisy) for adaptive degradation |

---

## Tier-1: K0 Pipeline - Emotion & Social Intelligence (ADR-0069)

| ADR | One-Liner |
|-----|-----------|
| **0069** | P08 AffectModulation (K0 implementation) detecting emotion, computing valence, and generating empathy responses in K0 |
| **0069a** | Emotion detection & valence computation detecting emotional state from input signals (prosody, words, sentiment) |
| **0069b** | Empathy response generation generating context-appropriate empathy responses based on detected affect |
| **0069c** | Affect state persistence & learning persisting affect state to SessionState scoreboard and learning emotional preferences |

---

## Tier-1: Observability & Evaluation (ADR-0070)

| ADR | One-Liner |
|-----|-----------|
| **0070** | Observability evaluation infrastructure enabling continuous quality measurement, A/B testing, and regression detection |
| **0070a** | Quality labeling & dataset collection collecting conversation quality labels for supervised evaluation |
| **0070b** | A/B testing framework & statistical significance implementing statistical rigor for feature experimentation |
| **0070c** | Regression detection & quality gates establishing regression thresholds and deployment gates |

---

## Tier-1: Internationalization & Multilingual (ADR-0071)

| ADR | One-Liner |
|-----|-----------|
| **0071** | Multilingual & code-switching supporting mixed-language conversations and family language diversity |
| **0071a** | Language detection & preference management detecting active language and respecting per-member preferences |
| **0071b** | Code-switching & mixed-language support parsing and responding to language mixing patterns (e.g., "¿Cómo weather?") |
| **0071c** | Agent code-switching & multilingual responses enabling agent to respond in appropriate language or code-mix naturally |

---

## Cross-ADR Dependency Patterns

### Core Foundation Chain
`0001 → 0002 → 0003 → 0004` — K0/K1 split → Actor Model → MPST → Module architecture

### Agent Lifecycle Chain
`0005 → 0005a/0005b/0005c/0005d/0005e` — FSM with 5 sub-ADRs covering all states

### Orchestration Chain
`0006 → 0006a/0006b/0006c/0006d → 0008/0009` — 3-phase orchestration + error recovery

### Planning Chain
`0007 → 0007a/0007b/0007c/0007d` — 4-stage planning with each stage as sub-ADR

### Security Chain
`0010 → 0010a/0010b/0010c/0010d` + `0032-0038` — Capabilities + band-based egress + encryption

### Serialization Chain
`0011 → 0011a/0011b/0011c/0011d` + `0012a-0012e` + `0013a-0013d` — FlatBuffers framework + 76 schemas + versioning

### API Chain
`0014/0015/0016` + `0040/0041` — REST/WebSocket/SSE + Chat/Session APIs

### Storage Chain
`0017a-0017f` + `0018a-0018c` + `0019a-0019d` + `0020a-0020c` + `0021a-0021c` + `0023a-0023c` — SessionState 6-section + eviction + serialization + multi-tier + retention + pagination

### Performance Chain
`0024-0031` — Budgets → KV Cache → Thermal → Placement → WFQ → Metrics → Tracing → Cost

### K0 Integration Chain
`0042-0046` — SSE streaming + topics + bridge + agent coordination

### HITL Chain
`0052-0055` — Approval workflows + message queue + turn boundary + context switch

### Voice Chain
`0056-0058` — Voice pipeline + backpressure + intent classification

### Learning Chain
`0059-0061` — Learning loop + adaptive cache + backpressure cascade

### Developer Tooling Chain
`0066 → 0066a/0066b/0066c` — Testing harness + LLM eval + synthetic users + regression testing

### Delight & Personality Chain
`0067 → 0067a/0067b/0067c` — Conversational delight + humor templates + family filtering + frequency control

### Voice Quality Chain
`0068 → 0068a/0068b/0068c` — Voice quality measurement + ASR WER + TTS MOS + environmental analysis

### K0 Affect Pipeline Chain
`0069 → 0069a/0069b/0069c` — P08 AffectModulation (K0 feature) + emotion detection + empathy generation + affect persistence

### Observability Evaluation Chain
`0070 → 0070a/0070b/0070c` — Eval infrastructure + quality labeling + A/B testing + regression gates

### Internationalization Chain
`0071 → 0071a/0071b/0071c` — Multilingual support + language detection + code-switching + agent responses

---

**Generated:** 2025-10-16
**Updated:** 2025-10-16 (added ADR-0066 through ADR-0071)
**Status:** Complete ADR landscape with 309 entries — Ready for roadmap generation
**Next:** COMPONENT_CONNECTIONS.md mapping upstream/downstream dependencies
