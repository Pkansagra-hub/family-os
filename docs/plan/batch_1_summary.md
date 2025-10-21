# K1 Kernel Dependency Graph - Batch 1 Complete ✅

## Overview

The **DEPENDENCY_GRAPH.mmd** file has been created in `docs/plan/` and represents the complete K1 5-layer architecture with all 52 modules and their dependencies.

---

## Source ADRs (Batch 1: ADRs 1-5 + Sub-ADRs)

The dependency graph is built from the following ADRs and related specifications:

### **Primary ADRs**
- **ADR-0001:** K0/K1 Kernel Split Architecture (dual microkernel design)
- **ADR-0002:** Actor Model for Agent Isolation (foundation for ALL 52 modules)
- **ADR-0003:** MPST Protocol Validation for Agent Communication (6 core protocols)
- **ADR-0004:** 52-Module 5-Layer Microkernel Architecture (module structure)
- **ADR-0005:** Agent Lifecycle FSM with 6 States (PENDING → WARMING → ACTIVE → IDLE → DRAINING → TERMINATED)

### **Supporting Sub-ADRs**
- **ADR-0005a:** Agent Warming State (model loading, KV cache initialization)
- **ADR-0005b:** Agent Idle Pooling (resource efficiency)
- **ADR-0005c:** Agent Draining Shutdown (graceful termination)
- **ADR-0005d:** Supervisor Blacklist (crash recovery)
- **ADR-0005e:** Agent Personality & Capabilities (skill definition)

### **Related Core ADRs**
- **ADR-0006:** 3-Phase Orchestration with Contract Net Protocol (negotiation → selection → execution)
- **ADR-0007:** 4-Stage Planning Pipeline (sketch → expand → validate → commit)
- **ADR-0008:** Saga Pattern for Error Recovery (compensating transactions)

---

## Diagram Structure

### **5 Layers + External Systems**

#### **Layer 1: Core Kernel (12 modules)** 🏗️ `#ff6b6b`
The brain of K1 - Agent orchestration, protocol validation, error recovery.

**Key Components:**
- **Agent Fabric** (L1_1) — Lifecycle FSM management
- **Orchestrator** (L1_2) — 3-phase Contract Net protocol
- **Planner** (L1_3) — 4-stage planning pipeline (AI agent)
- **Protocol Monitor** (L1_4) — MPST validation for 6 protocols
- **Saga Coordinator** (L1_9) — Compensating transaction coordination
- **Arbiter** (L1_12) — Plan validation & safety checks

**Internal Flow:**
```
L1_1 (Agent proposals) → L1_2 (Orchestrator) → L1_3 (Planner) 
  ↓ (validation)
L1_12 (Arbiter) → L1_2 (Orchestrator decision)
  ↓ (error handling)
L1_9 (Saga Coordinator)
```

**Dependencies:** All Layer 1 components depend on:
- **Mailbox** (L1_7) — MPSC queue for message passing
- **Actor Router** (L1_5) — Message routing
- **Supervisor** (L1_6) — Health monitoring
- **Protocol Monitor** (L1_4) — MPST validation
- **Capability Enforcer** (L1_8) — Permission checks
- **Role Attestation** (L1_11) — Security verification

---

#### **Layer 2: State & Persistence (8 modules)** 💾 `#4ecdc4`
Working memory and durable storage coordination.

**Key Components:**
- **SessionState Manager** (L2_1) — 6-section design (beliefs, scoreboard, control, persona, multimodal, meta)
- **Eviction Manager** (L2_2) — 3-tier eviction strategy (soft → hard → OOM)
- **Hot Tier L1** (L2_3) — RAM in-memory (500MB budget)
- **Warm Tier L2** (L2_4) — SSD local cache
- **Cold Tier L3** (L2_5) — S3 archive
- **K0 Bridge Manager** (L2_8) — K0 integration

**Internal Flow:**
```
L2_1 (SessionState) 
  ↓ (pressure)
L2_2 (Eviction Manager)
  → L2_3 (Hot Tier)
  → L2_4 (Warm Tier)
  → L2_5 (Cold Tier)
  ↓
L2_8 (K0 Bridge)
```

---

#### **Layer 3: Execution & Tools (10 modules)** ⚙️ `#95e77d`
Tool execution, LLM inference, result processing.

**Key Components:**
- **Tool Runner** (L3_1) — 3-tier sandbox orchestration
- **MCP Gateway** (L3_2) — JSON-RPC protocol handler
- **WASM Sandbox** (L3_3) — Trusted code execution
- **Process Sandbox** (L3_4) — OS-level isolation
- **Model Hub** (L3_5) — Multi-LLM integration & KV cache management
- **Streaming Engine** (L3_6) — Token stream processing

**Internal Flow:**
```
L3_1 (Tool Runner)
  → L3_2 (MCP) | L3_3 (WASM) | L3_4 (Process)
    ↓
  L3_7 (Tool Registry)
    ↓
  L3_8 (Result Processor)
    → L3_9 (Error Handler)
```

---

#### **Layer 4: Ingress & Voice (12 modules)** 🌐 `#ffd43b`
User input, voice processing, event streaming.

**Key Components:**
- **API Gateway** (L4_1) — REST/WebSocket/SSE entry point
- **WebSocket Manager** (L4_2) — Connection management
- **Voice Pipeline** (L4_5) — ASR → Intent → TTS
- **Barge-In Handler** (L4_9) — Interruption handling
- **Clarification Handler** (L4_10) — HITL (Human-in-the-Loop)

**Internal Flow:**
```
L4_11 (Microphone)
  → L4_6 (ASR)
  → L4_7 (Intent Classifier)
  → L4_5 (Voice Pipeline)
    → L4_8 (TTS)
    → L4_12 (Speaker)
```

---

#### **Layer 5: Infrastructure (10 modules)** 🔧 `#ff922b`
Security, resource management, observability.

**Key Components:**
- **Authenticator** (L5_1) — JWT auth
- **Band Manager** (L5_2) — Privacy bands (GREEN/AMBER/RED)
- **Thermal Manager** (L5_5) — Temperature monitoring
- **Model Placement** (L5_6) — NPU → GPU → CPU → Remote fallback
- **KV Cache Manager** (L5_7) — 512MB cache allocation
- **Backpressure Manager** (L5_8) — Load control

---

#### **External Systems** 🔗 `#b197fc`
- **K0 Memory Microkernel** — Durable storage backend
- **Cost Tracker** — Budget enforcement

---

## Edge Patterns (Dependency Types)

### **Within Layer 1 (Orchestration)**
```
L1_1 --proposals--> L1_2 --announces--> L1_1  (bidirectional)
L1_3 --submits plans--> L1_2
L1_12 --approves/denies--> L1_2
L1_9 --error recovery--> L1_2
L1_4 --validates protocol--> L1_1, L1_2, L1_3
```

### **Layer 1 → Layer 2 (State Management)**
```
L1_1 --context--> L2_1
L1_2 --task results--> L2_1
L1_3 --updates beliefs--> L2_1
L1_1, L1_2, L1_3 --audit logs--> L2_7
```

### **Layer 1 → Layer 3 (Execution)**
```
L1_1 --tool invoke--> L3_1
L1_1 --LLM query--> L3_5 (Model Hub)
L1_3 --LLM sketch--> L3_5 (Planner uses LLM)
L1_12 --validation rules--> L3_8
```

### **Layer 4 → Layer 1 (User Input)**
```
L4_1 --user message--> L1_3 (Planner)
L4_5 --intent trigger--> L1_3
L4_10 --pause execution--> L1_2
L4_9 --barge-in signal--> L1_2
```

### **Layer 5 → Layers 1-4 (Governance)**
```
L5_2 --band rules--> L1_8, L1_12 (permissions)
L5_5 --thermal state--> L5_6 (model placement)
L5_6 --placement decision--> L3_5 (Model Hub)
L5_8 --backpressure--> L2_2, L4_1 (load shedding)
```

---

## Key Design Decisions

### **1. Actor Model Foundation (ADR-0002)**
- ALL 52 modules are actors with:
  - Private state (no shared memory)
  - Mailboxes for message passing (MPSC queues)
  - Supervision trees for fault isolation
  - Location transparency (component ID routing)

### **2. Hybrid AI Architecture (ADR-0001, ADR-0004)**
- **4 AI Agents:** Concierge, Planner, Researcher, Safety Watch
  - Use Model Hub (L3_5) for LLM inference
  - Hybrid Actor + LLM reasoning
- **48 Pure Actors:** Orchestrator, Supervisor, Router, Tool Runner, etc.
  - Deterministic message processing
  - No LLM calls

### **3. 5-Layer Separation (ADR-0004)**
- **Hot Path:** Layers 1-3 (protocol-driven, <150ms latency budget)
- **Cold Path:** Layer 4-5 (async background, API/voice, observability)
- **Clear Boundaries:** No Layer 5 → Layer 1 direct calls (always async)

### **4. 3-Phase Orchestration (ADR-0006)**
- **Phase 1:** Negotiation (broadcast to agents, collect bids)
- **Phase 2:** Selection (weighted scoring, agent assignment)
- **Phase 3:** Execution (DAG execution with Saga rollback)

### **5. Error Recovery (ADR-0008)**
- **Saga Pattern:** Compensating transactions on failure
- **LIFO Unwinding:** Reverse-order compensation execution
- **Best-Effort:** Compensations logged but not required to succeed

---

## Performance Budgets (from ADRs)

| Component | Budget | ADR |
|-----------|--------|-----|
| TTFT (Time to First Token) | <150ms P95 | ADR-0024 |
| Agent cold start | <250ms P95 | ADR-0005 |
| Intent classification (T2) | <5ms P95 | ADR-0004 |
| Planning (Stage 1-4) | <100ms P95 | ADR-0007 |
| Orchestration (Phase 1-2) | <80ms P95 | ADR-0006 |
| Tool execution | <3000ms | ADR-0024 |
| Total E2E turn latency | <2000ms P95 | ADR-0024 |
| SessionState size | <64KB soft | ADR-0017 |
| KV Cache total | 512MB | ADR-0025 |
| K1 memory total | <500MB | ADR-0024 |

---

## Cross-Reference to Contracts

The following K1 contracts define the binding requirements for each layer:

- **contracts/agent_lifecycle/** — ADR-0005 implementation requirements
- **contracts/orchestration/3phase/** — ADR-0006 implementation requirements
- **contracts/planning/** — ADR-0007 implementation requirements
- **contracts/error_recovery/** — ADR-0008 implementation requirements
- **contracts/protocols/** — ADR-0003 MPST validation requirements
- **contracts/sessionstate/** — ADR-0017 6-section design requirements
- **contracts/performance/** — ADR-0024 latency budgets

---

## Next Batch (Planned)

The dependency graph covers **Batch 1 (ADRs 1-8)** comprehensively. Future batches will extend the graph:

- **Batch 2 (ADRs 9-14):** Circuit Breaker, Capability Security, FlatBuffers Serialization, Pipeline Versioning, JSON/REST, WebSocket
- **Batch 3 (ADRs 15-20):** SSE Events, SessionState Details, Multi-Tier Storage, Turn History, K0 Bridge Batching, Cursor Pagination
- **Batch 4 (ADRs 21+):** Performance, KV Cache, Thermal Management, Model Placement, Observability, Learning Loop

---

## Validation Checklist

✅ **Diagram Format:** Mermaid flowchart with no extraneous text or brackets
✅ **Node Naming:** Clean, readable names with emoji prefixes
✅ **Layer Organization:** 5 subgraphs with clear color coding
✅ **Dependencies:** All cross-layer and intra-layer relationships mapped
✅ **Edge Labels:** Clear, descriptive labels for all edges
✅ **Class Styling:** Layer1-Layer5 + External system styling
✅ **ADR Coverage:** Batch 1 (ADRs 1-8) comprehensively represented

---

## Usage

To view the diagram:

1. **In VS Code:** Use the Mermaid preview extension to render `DEPENDENCY_GRAPH.mmd`
2. **In Browser:** Paste content into [mermaid.live](https://mermaid.live)
3. **Command Line:** Use `mermaid-cli` to convert to PNG/SVG

```bash
# Install mermaid-cli
npm install -g mermaid-cli

# Convert to PNG
mmdc -i docs/plan/DEPENDENCY_GRAPH.mmd -o dependency_graph.png
```

---

## Files Created This Session

- `docs/plan/DEPENDENCY_GRAPH.mmd` — 282-line Mermaid dependency graph (Batch 1 complete)
- `docs/plan/BATCH_1_SUMMARY.md` — This document (comprehensive reference)

---

**Status:** ✅ **Batch 1 Complete** | Next: Batch 2 (ADRs 9-14) when ready

