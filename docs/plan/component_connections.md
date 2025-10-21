# COMPONENT_CONNECTIONS.md — K1 Architecture Dependency Map

**Purpose:** Logical upstream↔downstream dependency map showing component interactions, data flows, and communication patterns.
**Last Updated:** 2025-10-16
**Source:** ADR-0004 (52-Module 5-Layer Architecture), contracts/, architecture_diagrams/
**Format:** Layer → Module → Upstream/Downstream dependencies

---

## Overview: K1 Architecture Layers

```
Layer 5: Infrastructure (10 modules) — System services, observability, governance
    ↓ (depends on)
Layer 4: Ingress & Voice (12 modules) — User I/O, API gateways, voice pipeline
    ↓ (depends on)
Layer 3: Execution & Tools (10 modules) — Tool runners, model hub, MCP gateway
    ↓ (depends on)
Layer 2: State & Persistence (8 modules) — SessionState, storage, receipts
    ↓ (depends on)
Layer 1: Core Kernel (12 modules) — Agents, orchestration, planning, protocols
```

---

## Layer 1: Core Kernel (12 Modules)

### Module 1.1: Agent Fabric
- **Purpose:** Agent lifecycle management (6-state FSM: PENDING→WARMING→ACTIVE→IDLE→DRAINING→TERMINATED)
- **Primary ADRs:** ADR-0005, ADR-0005a-e
- **Contracts:** agent_lifecycle/*, protocols/agent_hire.pdl.yml
- **Downstream Dependencies:**
  - **Orchestrator Core** — Agents provide proposals in negotiation phase
  - **Protocol Monitor** — State transitions validated by MPST rules
  - **Supervisor** (internal) — Health monitoring and crash recovery
  - **Model Hub** — Model loading during WARMING state
- **Upstream Dependencies:**
  - **Orchestrator Core** — Receives task announcements and selection results
  - **K0 Bridge** — Fetches agent personality from K0 SessionState
  - **Tool Runner** — Agent may invoke tools during task execution

**Data Flow:**
```
Orchestrator → Task Announcement → Agent Fabric (PENDING)
              ↓
           WARMING (load model + KV cache) → ready for ACTIVE
              ↓
           ACTIVE (execute tasks) → generate proposals for orchestration
              ↓
           IDLE (pooling) OR DRAINING (cleanup) → TERMINATED
```

---

### Module 1.2: Orchestrator Core
- **Purpose:** 3-phase orchestration (Negotiation→Selection→Execution) with Contract Net Protocol
- **Primary ADRs:** ADR-0006, ADR-0006a-e
- **Contracts:** orchestration/*, protocols/task_execution.pdl.yml
- **Downstream Dependencies:**
  - **Agent Fabric** — Announces tasks, selects agents, monitors execution
  - **Planner Agent** — Receives validated plans to orchestrate
  - **Protocol Monitor** — All phases validated against MPST rules
  - **Storage** (Layer 2) — Logs task progress and results
- **Upstream Dependencies:**
  - **Planner Agent** — Receives validated task plans
  - **K0 Bridge** — Sends task results back to K0
  - **Clarification Protocol** — May pause execution for clarifications
  - **Barge-In Protocol** — May preempt execution on user input

**Data Flow:**
```
Planner → Validated Plan → Orchestrator (Phase 1: Negotiation)
                                ↓
                    Announce task to Agent Fabric
                                ↓
                    Agent Proposals → Score & Select (Phase 2)
                                ↓
                    Execute with Selected Agent (Phase 3)
                                ↓
                    Capture Results → Storage Layer 2
```

---

### Module 1.3: Planner Agent
- **Purpose:** 4-stage planning (Sketch→Expand→Validate→Commit)
- **Primary ADRs:** ADR-0007, ADR-0007a-d
- **Contracts:** planning/*, protocols/task_execution.pdl.yml
- **Downstream Dependencies:**
  - **Model Hub** — LLM calls for Sketch stage
  - **Tool Registry** (Layer 3) — Tool selection in Expand stage
  - **Arbiter** (internal) — Validation in Validate stage
  - **Orchestrator Core** — Submits validated plans for execution
  - **K0 Bridge** — Persists plans via K0 WAL integration
- **Upstream Dependencies:**
  - **Voice Pipeline** (Layer 4) → Intent classification triggers planning
  - **API Gateway** (Layer 4) → User message triggers planning
  - **K0 Bridge** → Recalls context from K0 SessionState
  - **Clarification Protocol** → May trigger re-planning

**Data Flow:**
```
User Intent → Planner (Sketch)
                ↓
            LLM generates plan sketch
                ↓
            Planner (Expand) → Tool Registry selects tools
                ↓
            Planner (Validate) → Arbiter validates + rules
                ↓
            Planner (Commit) → K0 WAL persists plan
                ↓
            Orchestrator executes
```

---

### Module 1.4: Protocol Monitor
- **Purpose:** MPST protocol validation for 6 core protocols
- **Primary ADRs:** ADR-0003, ADR-0003a-d
- **Contracts:** protocols/*, actor_model/router_admission.yaml
- **Downstream Dependencies:**
  - **All Layer 1 modules** — Every state transition validated
  - **Tool Runner** (Layer 3) → Validates Tool Call protocol
  - **Barge-In Handler** (Layer 4) → Validates Barge-In protocol
  - **Clarification Handler** (Layer 4) → Validates Clarification protocol
- **Upstream Dependencies:**
  - **Actor Router** (Layer 1) → Routes protocol messages
  - **Protocol Monitor** is autonomous — monitors all agents

**Protocol Matrix:**
```
1. Agent Hire (Agent Fabric ↔ Orchestrator)
2. Task Execution (Orchestrator → Agents)
3. Clarification (Planner ↔ Voice Pipeline)
4. Barge-In (Voice Pipeline → Orchestrator)
5. Tool Call (Agents → Tool Runner)
6. Saga Rollback (Error Recovery → Agents)
```

---

### Module 1.5: Actor Router
- **Purpose:** Fair message routing with admission control and backpressure
- **Primary ADRs:** ADR-0002c, ADR-0002d
- **Contracts:** actor_model/router_admission.yaml, mailbox_contract.yaml
- **Downstream Dependencies:**
  - **All Layer 1 agents** — Routes messages to agent mailboxes
  - **Router Policies** (Layer 5) → Selection algorithm for fast/smart lane
- **Upstream Dependencies:**
  - **All Layer 1 modules** → Send messages through router
  - **API Gateway** (Layer 4) → Routes ingress messages to planner

**Message Types Routed:**
```
Task announcements → Agent Fabric
Tool results → Orchestrator
Plan receipts → Voice Pipeline
Clarification requests → all agents
```

---

### Module 1.6: Supervisor
- **Purpose:** Agent health monitoring, crash detection, blacklisting
- **Primary ADRs:** ADR-0002b, ADR-0005d
- **Contracts:** agent_lifecycle/supervisor/*, actor_model/supervisor_protocol.yaml
- **Downstream Dependencies:**
  - **Agent Fabric** — Monitors agent health, triggers restart on crash
  - **Blacklist Manager** (internal) → Maintains crash-based blacklist
- **Upstream Dependencies:**
  - **Agent Fabric** — Reports health status
  - **Thermal Manager** (Layer 5) — May trigger agent shutdown on thermal pressure

---

### Modules 1.7-1.12: Supporting Layer 1 Components

| Module | Purpose | Key ADR | Downstream | Upstream |
|--------|---------|---------|-----------|----------|
| 1.7: Mailbox | Message buffering MPSC queue | ADR-0002a | Actor Router | All Layer 1 |
| 1.8: Capability Enforcer | Runtime permission checks | ADR-0010c | All Layer 1 ops | All layers |
| 1.9: Saga Coordinator | Distributed transaction mgmt | ADR-0008, 0008a-d | Error recovery | Orchestrator |
| 1.10: Circuit Breaker | Failure cascade prevention | ADR-0009, 0009a-c | Tool Runner, Model Hub | All layers |
| 1.11: Role Attestation | Role-based security checks | ADR-0003d | Capability Enforcer | All layers |
| 1.12: Arbiter | Plan validation (rules + ML) | ADR-0007c | Planner Agent | Protocol Monitor |

---

## Layer 2: State & Persistence (8 Modules)

### Module 2.1: SessionState Manager
- **Purpose:** Manage 6-section SessionState (Beliefs, Scoreboard, Control, Persona, Multimodal, Meta)
- **Primary ADRs:** ADR-0017, ADR-0017a-f
- **Related Q1 ADRs:** ADR-0050, ADR-0050a (Per-device coherence guarantees), ADR-0050b (CRDT merge)
- **Contracts:** sessionstate/*.yaml
- **Downstream Dependencies:**
  - **Eviction Manager** (2.2) → Manages eviction under memory pressure
  - **Storage Layer** (2.3-2.5) → Persists SessionState tiers
  - **K0 Bridge** → Delta serialization to K0
- **Upstream Dependencies:**
  - **Planner Agent** (L1) → Updates Beliefs, Scoreboard sections
  - **Voice Pipeline** (L4) → Updates Multimodal section
  - **All Layer 1 agents** → Read SessionState for context

**Q1 Multi-Device Sync Context:**
- ADR-0050a specifies per-device coherence guarantees (Read-Your-Writes, Monotonic Reads, Monotonic Writes, Writes-Follow-Reads, Bounded Staleness 250ms)
- SessionState must track vector clocks for each device to enable CRDT merge (ADR-0050b)
- Per-device coherence is prerequisite for Phase 1 (LAN, M2-M3) and Phase 2 (E2EE, M4-M5)

**Data Flow:**
```
Agent reads Beliefs section → Context for planning
User input → Update Scoreboard (QUD tracking)
   ↓
Planner updates Beliefs with new facts
   ↓
[Q1] For multi-device: Track device ID + vector clock for each write
   ↓
SessionState eviction triggers on memory pressure
   ↓
Delta serialization to K0 Bridge
   ↓
[Q1] On merge: CRDT merge logic converges state across devices
```

---

### Module 2.2: Eviction Manager
- **Purpose:** 3-tier eviction (soft/hard/OOM) with memory pressure response
- **Primary ADRs:** ADR-0018, ADR-0018a-c
- **Contracts:** sessionstate/eviction_strategy.yaml, 3_tier_eviction.yaml
- **Downstream Dependencies:**
  - **Warm Tier Storage** → Moves evicted sessions to SSD
  - **Cold Tier Storage** → Moves cold sessions to S3
  - **Backpressure Manager** (L5) → Escalates pressure signals
- **Upstream Dependencies:**
  - **SessionState Manager** → Requests eviction on threshold
  - **Performance Monitor** (L5) → Reports memory metrics
  - **Thermal Manager** (L5) → Triggers eviction on thermal pressure

---

### Module 2.3: Hot Tier (L1 RAM) Storage
- **Purpose:** In-memory active session storage with LRU eviction
- **Primary ADRs:** ADR-0020a
- **Contracts:** storage/multi_tier_storage.yaml
- **Downstream Dependencies:**
  - **Warm Tier Storage** (2.4) → Eviction destination
- **Upstream Dependencies:**
  - **SessionState Manager** → Active session data
  - **Eviction Manager** → Eviction triggers

---

### Module 2.4: Warm Tier (L2 SSD K0 WAL) Storage
- **Purpose:** SSD-backed warm session storage for fast retrieval
- **Primary ADRs:** ADR-0020b
- **Contracts:** storage/multi_tier_storage.yaml, k0_bridge/batching/
- **Downstream Dependencies:**
  - **Cold Tier Storage** (2.5) → Archive destination
- **Upstream Dependencies:**
  - **Hot Tier Storage** (2.3) → Eviction source
  - **K0 Bridge** → Async batched writes to K0 WAL
  - **Eviction Manager** → Eviction policy

---

### Module 2.5: Cold Tier (L3 S3 Archive) Storage
- **Purpose:** S3-backed cold session archival for retention
- **Primary ADRs:** ADR-0020c
- **Contracts:** storage/multi_tier_storage.yaml
- **Upstream Dependencies:**
  - **Warm Tier Storage** (2.4) → Archive source
  - **Retention Policy Engine** (2.6) → Lifecycle management

---

### Module 2.6: Retention Policy Engine
- **Purpose:** Lifecycle management with compliance rules
- **Primary ADRs:** ADR-0021, ADR-0021a-c
- **Contracts:** storage/retention_policies.yaml
- **Downstream Dependencies:**
  - **Cold Tier Storage** (2.5) → Lifecycle actions
  - **Audit Trail** (2.7) → Logs retention actions
- **Upstream Dependencies:**
  - **Privacy Band Manager** (L5) → Band-specific retention rules
  - **Compliance Monitor** (L5) → Compliance requirements

---

### Module 2.7: Receipt Manager (Audit Trail)
- **Purpose:** Immutable audit trail of all operations
- **Primary ADRs:** ADR-0038, ADR-0038a-d
- **Contracts:** security/audit_trail.yaml
- **Downstream Dependencies:**
  - **K0 Bridge** → Async writes to K0 receipts
- **Upstream Dependencies:**
  - **All Layer 1 modules** → Generate receipts for operations
  - **Compliance Monitor** → Queries receipts for compliance reports

---

### Module 2.8: K0 Bridge Manager
- **Purpose:** Dual-protocol communication with K0 (JSON + FlatBuffers)
- **Primary ADRs:** ADR-0001a, ADR-0044-0046
- **Related Q1 ADRs:** ADR-0050 (Multi-device sync), ADR-0050c (LAN Phase 1), ADR-0050d (E2EE Phase 2)
- **Contracts:** k0_bridge/, flatbuffers/
- **Downstream Dependencies:**
  - **K0 Kernel** (external) — All K0 pipelines P01-P20
  - **SSE Event Manager** (L4) — K0 SSE events
- **Upstream Dependencies:**
  - **All Layer 1 modules** → Query/command K0
  - **SessionState Manager** (2.1) → Delta serialization
  - **Receipt Manager** (2.7) → Audit persistence
  - **Storage Layers** (2.3-2.5) → Batched persistence

**Q1 Multi-Device Sync Context:**
- Device roster stored in K0 memory (which devices are synced)
- Bounded batching (10-50 msgs, 100ms timeout) for sync message batches
- Device certificates (0050d Phase 2) managed via K0 storage
- Sync messages flow through K0 Bridge → K0 SSE events → subscribed devices

**Data Flow:**
```
Layer 1 agent needs context
    ↓
K0 Bridge → K0 Query port (P01 Recall)
    ↓
K0 returns memory results
    ↓
Agent uses results for planning
    ↓
Agent updates SessionState
    ↓
K0 Bridge → Batched delta to K0 WAL
    ↓
[Q1] Sync message batch: includes device roster, vector clocks, CRDT merge deltas
    ↓
[Q1] K0 disseminates to other devices via SSE or direct P2P (Phase 2)
```

---

## Layer 3: Execution & Tools (10 Modules)

### Module 3.1: Tool Runner
- **Purpose:** Execute tools via 3-tier sandbox (MCP/WASM/Process)
- **Primary ADRs:** ADR-0033, ADR-0033a-d, ADR-0034, ADR-0034a-d
- **Contracts:** tools/*, protocols/tool_call.pdl.yml
- **Downstream Dependencies:**
  - **Tool Sandbox** (3.2-3.4) → Sandbox execution
  - **Circuit Breaker** (L1.10) → Failure handling
  - **Storage** → Tool result logging
- **Upstream Dependencies:**
  - **Agents** (L1) → Tool invocation requests
  - **Protocol Monitor** → Tool Call protocol validation

**Sandbox Selection (2D Matrix):**
```
Tool Type × Risk Profile → Sandbox Layer
  ├─ MCP Protocol: Standard tools (web, APIs, services)
  ├─ WASM: Medium risk (custom code)
  └─ Process: High risk (untrusted code)
```

---

### Module 3.2: MCP Protocol Gateway
- **Purpose:** Model Context Protocol implementation (JSON-RPC 2.0)
- **Primary ADRs:** ADR-0034, ADR-0034a-d
- **Contracts:** tools/mcp_protocol.json, protocols/tool_call.pdl.yml
- **Downstream Dependencies:**
  - **Tool runners** → Execute MCP tools
- **Upstream Dependencies:**
  - **Tool Runner** (3.1) → MCP request routing

---

### Module 3.3: WASM Sandbox
- **Purpose:** WebAssembly sandboxing for trusted custom tools
- **Primary ADRs:** ADR-0033b
- **Contracts:** tools/sandbox_matrix.yaml
- **Downstream Dependencies:**
  - **Storage** (L2) → Result logging
- **Upstream Dependencies:**
  - **Tool Runner** (3.1) → WASM tool execution requests

---

### Module 3.4: Process Sandbox
- **Purpose:** OS-level process sandboxing with seccomp/cgroups
- **Primary ADRs:** ADR-0033c, ADR-0032a-c
- **Contracts:** tools/sandbox_matrix.yaml, security/band_based_egress.yaml
- **Downstream Dependencies:**
  - **Resource Manager** (L5) → cgroups enforcement
- **Upstream Dependencies:**
  - **Tool Runner** (3.1) → Process tool execution requests
  - **Band Manager** (L5) → Privacy band rules

---

### Module 3.5: Model Hub
- **Purpose:** Multi-LLM integration with versioning, fallback, cost-aware placement
- **Primary ADRs:** ADR-0001b
- **Contracts:** flatbuffers/layer3_execution/model_hub_*.fbs
- **Downstream Dependencies:**
  - **Thermal Manager** (L5) → Placement decisions
  - **Cost Tracker** (L5) → Cost-aware fallback
  - **KV Cache Manager** (L5) → Cache allocation per model
- **Upstream Dependencies:**
  - **Planner Agent** (L1) → LLM calls (Sketch stage)
  - **Intent Classifier** (L4) → Intent classification
  - **Agent Fabric** (L1) → Model loading during WARMING

**Model Selection Cascade:**
```
Primary model (low cost, high capability)
    ↓ on cost pressure → Mid-tier fallback
    ↓ on thermal pressure → CPU offload
    ↓ on latency pressure → Remote execution
```

---

### Module 3.6: Streaming Engine
- **Purpose:** Token streaming for real-time response generation
- **Primary ADRs:** ADR-0015d (WebSocket streaming), ADR-0042a-b (K0 SSE streaming)
- **Contracts:** api/websocket/streaming.yaml, k0_sse/event_production.yaml
- **Downstream Dependencies:**
  - **API Gateway** (L4) → WebSocket streaming
  - **Voice Pipeline** (L4) → TTS streaming
  - **K0 Bridge** → K0 SSE event streaming
- **Upstream Dependencies:**
  - **Model Hub** (3.5) → Token generation
  - **Agents** (L1) → Result streaming

---

### Modules 3.7-3.10: Supporting Layer 3 Components

| Module | Purpose | Key ADR | Downstream | Upstream |
|--------|---------|---------|-----------|----------|
| 3.7: Tool Registry | Tool catalog and prompt templates | ADR-0007b | Planner Agent | Tool Runner |
| 3.8: Result Processor | Tool result parsing and validation | ADR-0033d | Agents | Tool Runner |
| 3.9: Error Handler | Tool-specific error recovery | ADR-0009b | Circuit Breaker | Tool Runner |
| 3.10: Cost Estimator | Tool cost prediction | ADR-0031b | Model Hub | Tool Runner |

---

## Layer 4: Ingress & Voice (12 Modules)

### Module 4.1: API Gateway
- **Purpose:** REST/WebSocket/SSE ingress with authentication and content negotiation
- **Primary ADRs:** ADR-0014-0016, ADR-0040-0041
- **Contracts:** api/rest/*, api/websocket/*, api/sse/*, openapi_3_1_specs/
- **Downstream Dependencies:**
  - **Planner Agent** (L1) → Route user messages
  - **WebSocket Manager** (4.2) → Connection management
  - **SSE Manager** (4.3) → Event streaming
- **Upstream Dependencies:**
  - **Authenticator** (L5) → JWT validation
  - **Capability Enforcer** (L1) → Permission checks

**API Contract by Protocol:**
```
REST: JSON/FlatBuffers request-response
    ├─ POST /sessions — Create session
    ├─ POST /sessions/{id}/messages — Send message
    └─ GET /sessions/{id}/turns — Get history

WebSocket: Binary framing with FlatBuffers
    ├─ Open connection with JWT
    ├─ Send/receive messages
    └─ Automatic reconnection on close

SSE: Server-sent events via K0 SSE bridge
    ├─ Subscribe to topics
    └─ Stream events
```

---

### Module 4.2: WebSocket Manager
- **Purpose:** WebSocket protocol management with reconnection and flow control
- **Primary ADRs:** ADR-0015, ADR-0015a-e
- **Contracts:** api/websocket/*, bridge_integration/sse_websocket_bridge.yaml
- **Downstream Dependencies:**
  - **Flow Control** (L5) → Backpressure handling
  - **Streaming Engine** (L3.6) → Token streaming
- **Upstream Dependencies:**
  - **API Gateway** (4.1) → Connection acceptance
  - **Authenticator** (L5) → Session binding

---

### Module 4.3: SSE Manager
- **Purpose:** Server-Sent Events for K0 real-time updates
- **Primary ADRs:** ADR-0016, ADR-0042-0043, ADR-0046
- **Contracts:** k0_sse/*, event_schemas.yaml
- **Downstream Dependencies:**
  - **K0 Bridge** (L2.8) → Subscribe to K0 SSE events
  - **Topic Router** (4.4) → Route events by topic
- **Upstream Dependencies:**
  - **API Gateway** (4.1) → Connection acceptance
  - **K0 Bridge** → Event consumption

---

### Module 4.4: Topic Router
- **Purpose:** Route K0 SSE events to subscribers with filtering
- **Primary ADRs:** ADR-0043a-d
- **Contracts:** k0_sse/topic_hierarchy.yaml, event_schemas.yaml
- **Downstream Dependencies:**
  - **SSE Manager** (4.3) → Event delivery
- **Upstream Dependencies:**
  - **K0 Bridge** (L2.8) → Topic hierarchy from K0
  - **SSE Manager** (4.3) → Subscription management

---

### Module 4.5: Voice Pipeline
- **Purpose:** End-to-end voice interaction (ASR→Intent→Planning→TTS)
- **Primary ADRs:** ADR-0056, ADR-0056a-e
- **Contracts:** voice_pipeline/*, protocols/clarification.pdl.yml
- **Downstream Dependencies:**
  - **ASR Engine** (4.6) → Speech-to-text
  - **Intent Classifier** (4.7) → Intent extraction
  - **Planner Agent** (L1) → Planning trigger
  - **TTS Engine** (4.8) → Speech synthesis
  - **Barge-In Handler** (4.9) → Interruption handling
- **Upstream Dependencies:**
  - **Audio Input** (L5) → Microphone/audio stream
  - **SessionState Manager** (L2.1) → Multimodal context

**Voice Flow:**
```
Audio Input (microphone)
    ↓
ASR Engine → Text hypothesis
    ↓
Intent Classifier → Intent + confidence
    ↓
if confidence > threshold:
    Planner Agent → Generate response
else:
    Clarification → Ask user
    ↓
TTS Engine → Synthesize response
    ↓
Audio Output (speaker)
```

---

### Module 4.6: ASR Engine (Automatic Speech Recognition)
- **Purpose:** Convert speech to text with confidence scoring
- **Primary ADRs:** ADR-0056a
- **Contracts:** voice_pipeline/asr_contract.yaml
- **Downstream Dependencies:**
  - **Intent Classifier** (4.7) → Text transmission
- **Upstream Dependencies:**
  - **Voice Pipeline** (4.5) → ASR trigger
  - **Audio Input** (L5) → Audio stream

---

### Module 4.7: Intent Classifier
- **Purpose:** Extract user intent from text/speech
- **Primary ADRs:** ADR-0058, ADR-0058a-b
- **Contracts:** voice_pipeline/intent_classifier.yaml
- **Downstream Dependencies:**
  - **Planner Agent** (L1) → Intent routing
  - **Clarification Handler** (4.10) → Low-confidence routing
- **Upstream Dependencies:**
  - **Voice Pipeline** (4.5) → Trigger
  - **Model Hub** (L3.5) → LLM intent classification
  - **SessionState Manager** (L2.1) → Context for intent resolution

---

### Module 4.8: TTS Engine (Text-to-Speech)
- **Purpose:** Synthesize speech from text with streaming
- **Primary ADRs:** ADR-0056d
- **Contracts:** voice_pipeline/tts_contract.yaml
- **Downstream Dependencies:**
  - **Audio Output** (L5) → Speaker output
  - **Streaming Engine** (L3.6) → Token streaming for TTS
- **Upstream Dependencies:**
  - **Voice Pipeline** (4.5) → TTS trigger
  - **Thermal Manager** (L5) → Degradation on thermal pressure

---

### Module 4.9: Barge-In Handler
- **Purpose:** Detect user speech and preempt agent speech
- **Primary ADRs:** ADR-0003b (protocol), ADR-0057c
- **Contracts:** protocols/barge_in.pdl.yml
- **Downstream Dependencies:**
  - **TTS Engine** (4.8) → Stop playback
  - **ASR Engine** (4.6) → Resume listening
- **Upstream Dependencies:**
  - **Voice Pipeline** (4.5) → Barge-in detection
  - **Audio Input** (L5) → Microphone level monitoring

---

### Module 4.10: Clarification Handler
- **Purpose:** Handle clarification requests during execution
- **Primary ADRs:** ADR-0003b (protocol), ADR-0052c
- **Contracts:** protocols/clarification.pdl.yml
- **Downstream Dependencies:**
  - **Orchestrator Core** (L1.2) → Pause execution
  - **Voice Pipeline** (4.5) → Clarification interaction
- **Upstream Dependencies:**
  - **Planner Agent** (L1) → Clarification needs
  - **Intent Classifier** (4.7) → Low-confidence intents

---

### Modules 4.11-4.12: Supporting Layer 4 Components

| Module | Purpose | Key ADR | Downstream | Upstream |
|--------|---------|---------|-----------|----------|
| 4.11: Audio Input | Microphone/audio stream management | (voice I/O) | Voice Pipeline | Device drivers |
| 4.12: Audio Output | Speaker/audio output management | (voice I/O) | Voice Pipeline | TTS Engine |

---

## Layer 5: Infrastructure (10 Modules)

### Module 5.1: Authenticator
- **Purpose:** JWT authentication with session binding
- **Primary ADRs:** ADR-0037, ADR-0037a-d
- **Contracts:** security/jwt_auth.yaml
- **Downstream Dependencies:**
  - **All layers** → Permission checks
- **Upstream Dependencies:**
  - **API Gateway** (L4.1) → JWT validation
  - **Capability Enforcer** (L1) → Authorization

---

### Module 5.2: Band Manager (Privacy Bands)
- **Purpose:** GREEN/AMBER/RED privacy classification and enforcement
- **Primary ADRs:** ADR-0032, ADR-0032a-d
- **Contracts:** security/privacy_bands.yaml, band_based_egress.yaml
- **Downstream Dependencies:**
  - **Process Sandbox** (L3.4) → Band-based restrictions
  - **Encryption Manager** (5.3) → RED band encryption
  - **PII Redactor** (5.4) → Data protection by band
  - **Retention Engine** (L2.6) → Band-specific retention
- **Upstream Dependencies:**
  - **All layers** → Query band classification
  - **SessionState Manager** (L2.1) → Beliefs/Control sections

---

### Module 5.3: Encryption Manager
- **Purpose:** E2EE for RED band with KMS key management
- **Primary ADRs:** ADR-0036, ADR-0036a-d
- **Contracts:** security/e2ee_encryption.yaml
- **Downstream Dependencies:**
  - **Storage** (L2) → Encrypted persistence
  - **K0 Bridge** (L2.8) → Encrypted transmission
- **Upstream Dependencies:**
  - **Band Manager** (5.2) → RED band classification
  - **All layers** → Encryption/decryption requests

---

### Module 5.4: PII Redactor
- **Purpose:** Detect and redact personally identifiable information
- **Primary ADRs:** ADR-0035, ADR-0035a-d
- **Contracts:** security/pii_detection.yaml
- **Downstream Dependencies:**
  - **All layers** → PII protection
  - **Audit Trail** (L2.7) → Redacted logging
- **Upstream Dependencies:**
  - **Band Manager** (5.2) → Band classification
  - **Planner Agent** (L1) → Redaction on output

---

### Module 5.5: Thermal Manager
- **Purpose:** Thermal state management with hysteresis and cascading degradation
- **Primary ADRs:** ADR-0026, ADR-0026a-d
- **Contracts:** performance/thermal_management.yaml
- **Downstream Dependencies:**
  - **Model Placement** (5.6) → Placement decisions
  - **KV Cache Manager** (5.7) → Cache degradation
  - **Backpressure Manager** (5.8) → Backpressure signals
  - **Throttle Manager** (5.10) → User notifications
- **Upstream Dependencies:**
  - **Performance Monitor** (5.9) → Thermal metrics
  - **Hardware sensors** → Temperature readings

**Thermal Cascade:**
```
Normal (< 50°C) → All agents active, full performance
Warm (50-55°C) → KV cache compression (Zstd)
Hot (55-60°C) → Model downgrade (NPU → GPU)
Critical (> 60°C) → Forced slowdown + backpressure
```

---

### Module 5.6: Model Placement
- **Purpose:** Cascade model placement (NPU→GPU→CPU→Remote) based on thermal and cost
- **Primary ADRs:** ADR-0027, ADR-0027a-d
- **Contracts:** performance/model_placement.yaml
- **Downstream Dependencies:**
  - **Model Hub** (L3.5) → Placement execution
- **Upstream Dependencies:**
  - **Thermal Manager** (5.5) → Thermal signals
  - **Cost Tracker** (5.11) → Cost signals
  - **Performance Monitor** (5.9) → Latency metrics

---

### Module 5.7: KV Cache Manager
- **Purpose:** 512MB KV cache with LRU-LFU hybrid eviction and compression
- **Primary ADRs:** ADR-0025, ADR-0025a-e
- **Contracts:** performance/kv_cache_management.yaml
- **Downstream Dependencies:**
  - **Model Hub** (L3.5) → Cache allocation
  - **Thermal Manager** (5.5) → Compression on thermal pressure
- **Upstream Dependencies:**
  - **All agents** (L1) → Cache allocation requests
  - **SessionState Manager** (L2.1) → Session cache sizing

---

### Module 5.8: Backpressure Manager
- **Purpose:** 3-tier backpressure cascade (Tier 1→2→3) with band overrides
- **Primary ADRs:** ADR-0022c, ADR-0061, ADR-0061a-d
- **Contracts:** performance/backpressure_cascade.yaml
- **Downstream Dependencies:**
  - **Band Manager** (5.2) → Band-specific overrides
  - **Throttle Manager** (5.10) → User notifications
  - **Flow Control** (internal) → Backpressure signals
- **Upstream Dependencies:**
  - **Thermal Manager** (5.5) → Thermal backpressure
  - **Performance Monitor** (5.9) → Queue depth signals
  - **K0 Bridge** (L2.8) → K0 queue depth

**Backpressure Tiers:**
```
Tier 1 (Low): Reduce batch sizes, compress caches
Tier 2 (Medium): Drop non-essential tasks, degrade quality
Tier 3 (High): Reject new requests, emergency eviction
```

---

### Module 5.9: Performance Monitor
- **Purpose:** Prometheus metrics (RED method) with intelligent trace sampling
- **Primary ADRs:** ADR-0029-0030
- **Contracts:** observability/prometheus_metrics.yaml, trace_sampling.yaml
- **Downstream Dependencies:**
  - **Alerting Engine** (internal) → Alert firing
  - **Dashboards** (Grafana) → Metrics visualization
- **Upstream Dependencies:**
  - **All layers** → Emit metrics
  - **Thermal Manager** (5.5) → Thermal metrics
  - **KV Cache Manager** (5.7) → Cache metrics

**Metrics Exposed:**
```
Turn-level: TTFT, E2E latency, barge-in latency
Component: Agent count, orchestration duration, plan validation time
Infrastructure: KV cache hit rate, thermal state, memory usage
Cost: Per-session cost, monthly budget tracking
```

---

### Module 5.10: Throttle Manager & Notifications
- **Purpose:** User notifications for thermal throttling and QoS degradation
- **Primary ADRs:** ADR-0026d
- **Contracts:** performance/degradation_policies.yaml
- **Downstream Dependencies:**
  - **API Gateway** (L4.1) → Send notifications
  - **Voice Pipeline** (L4) → Audio notifications
- **Upstream Dependencies:**
  - **Thermal Manager** (5.5) → Throttle events
  - **Backpressure Manager** (5.8) → QoS events

---

### Module 5.11: Cost Tracker
- **Purpose:** Per-session and hierarchical cost tracking with budget enforcement
- **Primary ADRs:** ADR-0031, ADR-0031a-d
- **Contracts:** performance/cost_tracking.yaml
- **Downstream Dependencies:**
  - **Model Placement** (5.6) → Cost-aware placement
  - **Backpressure Manager** (5.8) → Cost-based degradation
- **Upstream Dependencies:**
  - **All layers** → Cost reporting
  - **Model Hub** (L3.5) → Model costs
  - **Tool Runner** (L3.1) → Tool costs

---

## Cross-Layer Communication Patterns

### Pattern 1: Context Recall (Layer 1 ← Layer 2 ← K0)
```
Agent needs context
    ↓
Query K0 Bridge (L2.8) → Query K0 via P01 Recall
    ↓
K0 returns memory + embeddings
    ↓
SessionState Manager (L2.1) updates Beliefs section
    ↓
Agent uses context for planning
```

### Pattern 2: User Message Processing (Layer 4 → Layer 1 → Layer 3 → Layer 4)
```
User message via API (L4.1)
    ↓
Router → Planner (L1.3)
    ↓
Planner queries context via K0 Bridge (L2.8)
    ↓
Planner generates plan → Orchestrator (L1.2)
    ↓
Orchestrator selects agent → Agent Fabric (L1.1)
    ↓
Agent executes tasks via Tool Runner (L3.1)
    ↓
Results stream via Streaming Engine (L3.6) → WebSocket (L4.2)
```

### Pattern 3: Thermal Degradation (Layer 5 → Layers 3,4,5)
```
Thermal Manager detects hot temperature
    ↓
Cascade: Model Downgrade → KV Cache Compression → Backpressure
    ↓
Model Placement (L5.6) moves models from NPU→GPU
    ↓
KV Cache Manager (L5.7) compresses inactive caches
    ↓
Backpressure Manager (L5.8) reduces load
    ↓
Throttle Manager (L5.10) notifies user
```

### Pattern 4: Error Recovery (Layer 1 ↔ Layer 3, Layer 2)
```
Tool execution fails
    ↓
Tool Runner (L3.1) triggers Circuit Breaker (L1.10)
    ↓
Saga Coordinator (L1.9) generates compensation plan
    ↓
Orchestrator (L1.2) executes compensation via agents
    ↓
Receipt Manager (L2.7) logs error and recovery
```

### Pattern 5: Privacy Band Enforcement (Layer 5 → Layers 3,4,1)
```
SessionState indicates RED band data
    ↓
Band Manager (L5.2) classifies as RED
    ↓
Encryption Manager (L5.3) enables E2EE
    ↓
Process Sandbox (L3.4) restricts egress
    ↓
PII Redactor (L5.4) redacts on output
    ↓
API Gateway (L4.1) returns encrypted response
```

---

## Cross-Cutting Components (ADR-0066 through ADR-0071)

### Module: Developer Testing & Simulation Harness
- **Purpose:** Testing infrastructure for AI agent interactions with LLM eval framework and synthetic users
- **Primary ADRs:** ADR-0066, ADR-0066a-c
- **Contracts:** developer_testing/*, testing/integration_standards.yaml
- **Interconnections:**
  - **Planner Agent** (L1.3) — Test planning pipeline with prompt versioning
  - **Orchestrator Core** (L1.2) — Test orchestration workflows and agent selection
  - **Agent Fabric** (L1.1) — Simulate agent states and lifecycle transitions
  - **Protocol Monitor** (L1.4) — Validate protocol compliance in tests
  - **Performance Monitor** (L5.9) — Track regression in test metrics
- **Integration Points:**
  - **Input:** WARD test framework, synthetic conversation data, prompt versions
  - **Output:** Quality metrics, regression alerts, test coverage reports
  - **External Dependencies:** LLM providers (for eval), dataset management

**Test Coverage:**
```
Planning: Sketch/Expand/Validate/Commit stages
Orchestration: Task announcement, negotiation, selection, execution
Agents: State transitions, capability matching, recovery
Protocols: All 6 core protocols validation
Performance: Latency regression detection (<5% tolerance)
```

---

### Module: Conversational Delight & Personality
- **Purpose:** Personality warmth and engagement with template-based humor and family-appropriate filtering
- **Primary ADRs:** ADR-0067, ADR-0067a-c
- **Contracts:** experience/conversational_delight.yaml
- **Interconnections:**
  - **Planner Agent** (L1.3) — Delight injection during planning
  - **Model Hub** (L3.5) — LLM-generated delight (optional expansion)
  - **Agent Personality** (L1.1.e) — Personality-driven delight selection
  - **SessionState** (L2.1) — Delight frequency tracking per session
  - **Performance Monitor** (L5.9) — Delight engagement metrics
- **Integration Points:**
  - **Input:** Agent personality, user age/preferences, delight templates, random seed
  - **Output:** Delight-injected responses, engagement metrics
  - **Storage:** Delight templates in config, frequency tracking in SessionState

**Delight Patterns:**
```
Frequency: ~10% of responses (tunable per family)
Family Filtering: Age-appropriate templates based on family mix
Randomness: Avoid joke repetition with diversity tracking
Metrics: Engagement, sentiment, user feedback signals
```

---

### Module: Voice Quality Measurement
- **Purpose:** Automated measurement of voice interaction quality (ASR WER + TTS MOS)
- **Primary ADRs:** ADR-0068, ADR-0068a-c
- **Contracts:** observability/voice_quality.yaml
- **Interconnections:**
  - **Voice Pipeline** (L4.3) — ASR/TTS quality measurement
  - **Performance Monitor** (L5.9) — Expose WER/MOS metrics
  - **Observability Evaluation** (cross-cutting) — Quality labeling integration
- **Integration Points:**
  - **Input:** Speech recognition hypotheses, TTS audio output, reference transcripts
  - **Output:** WER score, MOS estimate, environmental labels
  - **External Dependencies:** Reference transcripts (for WER), MOS estimation models

**Quality Metrics:**
```
ASR Accuracy: Word Error Rate (WER) via edit distance
TTS Quality: Mean Opinion Score (MOS) via automated estimation
Environment: Quiet/Noisy/Echo environment classification
Regression: Alert on WER >5% or MOS <3.5 degradation
```

---

### Module: P08 AffectModulation (K0 Pipeline)
- **Purpose:** K0-based emotion detection, valence computation, and empathy response generation
- **Primary ADRs:** ADR-0069, ADR-0069a-c (⚠️ **K0 FEATURE - NOT K1**)
- **Contracts:** k0_bridge/affect_modulation.yaml (K0 contract)
- **Interconnections (K1 → K0):**
  - **K0 Bridge** (L2.8) — Query API for affect state (read-only)
  - **SessionState Manager** (L2.1) — Store affect in Scoreboard section
  - **Planner Agent** (L1.3) — Read affect for empathy-aware planning (via K0 Query API)
  - **Voice Pipeline** (L4.3) — Prosody features → K0 emotion detection
- **Integration Points:**
  - **K1 Input:** SessionState affect state via K0 Query API (read-only)
  - **K1 Output:** Affect signals for empathy response shaping (stateless)
  - **K0 Storage:** Affect state persisted in SessionState Scoreboard
  - **K0 Learning:** K0 P06 learns emotional preferences from feedback

**⚠️ K0/K1 Boundary:**
```
K0 OWNS: Emotion detection, valence computation, empathy generation, affect storage
K1 MAY USE: Read-only affect queries (not stateful)
K1 CANNOT: Store affect, issue receipts, modify K0 affect state
Data Flow: User input (prosody/text) → K0 emotion detection → K0 SessionState → K1 reads via Query API
```

---

### Module: Observability & Evaluation Infrastructure
- **Purpose:** Continuous quality measurement, A/B testing, and regression detection
- **Primary ADRs:** ADR-0070, ADR-0070a-c
- **Contracts:** observability/eval_infrastructure.yaml
- **Interconnections:**
  - **Performance Monitor** (L5.9) — Collect real-time metrics
  - **Voice Quality Measurement** (cross-cutting) — Voice quality labels
  - **Developer Testing** (cross-cutting) — Quality metric synthesis
  - **K0 Bridge** (L2.8) → Label storage via K0 receipts
- **Integration Points:**
  - **Input:** Conversation transcripts, quality labels, experiment configurations
  - **Output:** Quality metrics, A/B test results, regression alerts
  - **Analysis:** Statistical significance testing, quality trend analysis

**Evaluation Framework:**
```
Quality Labeling: Manual/automated labels for supervised evaluation
A/B Testing: Statistically rigorous feature experimentation
Regression Gates: Deployment gates requiring quality metrics >threshold
Analysis: BLEU/ROUGE/BERTScore metrics, LLM-as-evaluator
```

---

### Module: Multilingual & Code-Switching Support
- **Purpose:** Multi-language support and code-switching (language mixing) for multi-generational families
- **Primary ADRs:** ADR-0071, ADR-0071a-c
- **Contracts:** internationalization/multilingual.yaml
- **Interconnections:**
  - **Voice Pipeline** (L4.3) — Language detection on ASR input, TTS output
  - **Planner Agent** (L1.3) — Multilingual prompt adaptation
  - **SessionState** (L2.1) → Store per-user language preferences
  - **Model Hub** (L3.5) → Multilingual model selection
  - **Performance Monitor** (L5.9) → Language-specific metrics
- **Integration Points:**
  - **Input:** User language preferences, ASR output, detected language
  - **Output:** Language-aware responses, code-mixed responses
  - **Storage:** Language preferences in SessionState Persona section
  - **External:** Language detection API, multilingual LLM APIs

**Language Features:**
```
Detection: Automatic language detection from user input (ASR confidence)
Preferences: Per-family-member language settings (English, Spanish, Mandarin, etc.)
Code-Switching: Support mixed-language input ("¿Cómo está the weather?")
Agent Response: Agent responds in appropriate language or naturally code-mixes
Supported: 50+ languages via multilingual models
```

---

## Dependency Statistics (Updated)

| Metric | Value |
|--------|-------|
| Total modules (core) | 52 |
| Cross-cutting components | 6 (ADR-0066, 0067, 0068, 0069, 0070, 0071) |
| Total ADRs referenced | 309 (was 206) |
| Layer 1 modules | 12 |
| Layer 2 modules | 8 |
| Layer 3 modules | 10 |
| Layer 4 modules | 12 |
| Layer 5 modules | 10 |
| Intra-layer dependencies | ~120 |
| Inter-layer dependencies | ~80 |
| K0 bridge connection points | 8 (L2.8 primary) |
| External system interfaces | 3 (K0, hardware, external APIs) |
| Testing/Quality interfaces | 4 (Developer Testing, Voice Quality, Eval Infra, Multilingual) |

---

## Key Design Principles

1. **Layered architecture** — Clear separation of concerns with defined interfaces
2. **Protocol-driven** — MPST validation ensures state machine safety
3. **Memory-aware** — Multi-tier storage with intelligent eviction
4. **Thermally adaptive** — Cascade degradation on thermal pressure
5. **Performance budgeted** — All operations have latency targets
6. **Privacy-preserving** — Band-based classification with encryption
7. **Audit-trailable** — Receipt trail for all operations
8. **K0-integrated** — Dual-protocol bridge for seamless K0 communication

---

**Generated:** 2025-10-16
**Updated:** 2025-10-16 (added ADR-0066 through ADR-0071 cross-cutting components)
**Cross-References:** ADR-0004 (52-module architecture), ADR-0066-0071 (new cross-cutting), contracts/*, architecture_diagrams/
**Next:** DEPENDENCY_GRAPH.mmd (visual Mermaid rendering)
