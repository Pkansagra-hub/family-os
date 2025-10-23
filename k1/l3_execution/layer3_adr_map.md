# Layer 3 (Execution) — ADR Family Map

**Complete end-to-end ADR references for K1 Layer 3 modules**

---

## 📋 Overview

**Layer 3 Purpose:** Execution (Agents, Model Hub, Tools, Dialogue)
**Performance Budget:** Model Hub <50ms P95, Tools <3000ms P95, Agent Hire <600ms P95
**Modules:** 24 modules across 4 categories (8 agents + 7 model_hub + 5 tools + 4 dialogue)
**Primary Function:** Agent lifecycle + AI integration + tool execution + dialogue management

---

## 🗺️ Layer 3 Architecture

### Core ADRs

| ADR | Title | Status | Priority | Coverage |
|-----|-------|--------|----------|----------|
| **ADR-0004** | 52-Module 5-Layer Architecture | ✅ Complete | 🔴 CRITICAL | Layer 3 definition, 22-module execution layer |
| **ADR-0005** | Agent Lifecycle (6-State FSM) | ✅ Complete | 🔴 CRITICAL | PENDING/WARMING/ACTIVE/IDLE/DRAINING/TERMINATED |
| **ADR-0001b** | Model Hub Architecture | ✅ Complete | 🔴 CRITICAL | 7 modules, 4 AI agents, local-first LLM |
| **ADR-0033** | Tool Execution (2D Selection) | ✅ Complete | 🔴 CRITICAL | MCP + WASM + Process sandboxing |
| **ADR-0034** | MCP Protocol | ✅ Complete | 🟡 HIGH | JSON-RPC 2.0, 608 MCP-compatible tools |
| **ADR-0086** | Dynamic Agent Creation Subsystem | ✅ Complete | 🟡 HIGH | On-demand agent spawning, 58+ agent types, composition pattern |
| **ADR-0004d** | Layer 3 Integration Tests | ✅ Complete | 🟡 HIGH | Agent lifecycle, tool execution, Model Hub, <600ms hire, <3000ms tool |

---

## 📁 Module-by-Module ADR Map

## Category 1: agents/ (8 modules)

### **Module 1.1: agents/registry/**

**Purpose:** Agent YAML specifications
**Location:** `k1/l3_execution/agents/registry/`
**Performance:** <1ms lookup (hash table)

#### Primary ADRs

- **ADR-0005** — Agent Lifecycle (6-state FSM)
- **ADR-0005e** — Agent Personalities (4 AI agents + 54 pure actors)

#### Related ADRs

- **ADR-0002** — Actor Model (all agents are actors)
- **ADR-0010** — Capability Security (agent capability declarations)

#### Key Responsibilities

1. **Agent Specifications:** YAML manifest per agent type (registry/*.agent.yml)
2. **Capability Declaration:** Tool access, memory access, model access, network access
3. **Personality Traits:** Concierge (50ms), Planner (5000ms), Researcher (3000ms), Safety Watch (100ms)
4. **O(1) Lookup:** Hash table by agent_type, <1ms retrieval

**Performance Metrics:**
- Agent lookup: <1ms P95
- Registry size: 58 agent types (4 AI + 54 pure actors)
- Specification parsing: <10ms at startup

---

### **Module 1.2: agents/hire_fire/**
**Purpose:** Agent lifecycle FSM manager
**Location:** `k1/l3_execution/agents/hire_fire/`
**Performance:** <600ms P95 (hire), <50ms P95 (fire)

#### Primary ADRs

- **ADR-0005** — Agent Lifecycle (6-state FSM: PENDING→WARMING→ACTIVE→IDLE→DRAINING→TERMINATED)
- **ADR-0005a** — WARMING State (dual-path warmup: AI vs pure actors)
- **ADR-0005b** — IDLE Pooling (TTL tracking, reactivation <50ms)
- **ADR-0005c** — DRAINING State (3-phase drain, 5s timeout)

#### Related ADRs

- **ADR-0002** — Actor Model (hire_fire is pure actor)
- **ADR-0006** — 3-Phase Orchestration (hire triggered by negotiation)
- **ADR-0024** — Performance Budgets (hire <600ms P95)
- **ADR-0027** — Model Placement (thermal-aware placement)
- **ADR-0029** — Prometheus Metrics (hire latency, crash rate)

#### Key Responsibilities

**Agent Hiring (<600ms P95):**
1. **PENDING→WARMING:** Trigger warmup, spawn process/thread
2. **WARMING→ACTIVE:** Load model (AI) or config (pure actor)
   - **AI Agent Warmup (150-200ms):** Model load, prompt cache, KV cache init
   - **Pure Actor Warmup (10-20ms):** Config load, mailbox init, supervisor registration
3. **Placement Planner:** Thermal-aware placement (NPU→GPU→CPU→Remote)
4. **Lease Issuance:** Generate capability token (HMAC-SHA256 signature)

**Agent Firing (<50ms P95):**
1. **ACTIVE→DRAINING:** Stop accepting new tasks
2. **DRAINING→TERMINATED:** Complete in-flight tasks (5s timeout), cleanup
3. **Resource Cleanup:** Model unload (200ms), KV cache free (100ms), metrics flush (50ms)

**IDLE Pooling:**
- TTL tracking (5 min default)
- Reactivation <50ms P95 (5× faster than cold start)
- Pool hit rate >80%
- Memory optimization (42% footprint reduction: 90MB vs 155MB)

**Performance Metrics:**
- Agent hire (cold start): 300-600ms P95 (AI), 50-100ms P95 (pure actor)
- Agent hire (warm pool): <50ms P95 (reactivation)
- Agent fire: <50ms P95
- IDLE pool hit rate: >80%

---

### **Module 1.3: agents/supervisor/**
**Purpose:** Health monitoring & crash detection
**Location:** `k1/l3_execution/agents/supervisor/`
**Performance:** <100ms crash detection

#### Primary ADRs

- **ADR-0005d** — Supervisor (heartbeat monitoring, crash detection, blacklist)
- **ADR-0002b** — Actor Fabric Supervisor

#### Related ADRs

- **ADR-0029** — Prometheus Metrics (crash rate, blacklist)

#### Key Responsibilities

1. **Heartbeat Monitoring:** 1s interval ping, 3s timeout, event-loop heartbeat (200ms)
2. **Crash Detection:** <100ms detection, crash logging, replacement spawning
3. **Blacklist Manager:** 3 crashes in 10 min threshold, 1 hour duration, per-version, 88% reduction repeated crashes
4. **State Tracking:** FSM transition logging, state validation, metrics emission

**Performance Metrics:**
- Heartbeat overhead: <1% CPU
- Crash detection: <100ms
- Blacklist enforcement: <1ms lookup
- Supervisor overhead: <5ms per agent per second

---

### **Module 1.4: agents/personality/**
**Purpose:** Persona adaptation
**Location:** `k1/l3_execution/agents/personality/`
**Performance:** <5ms trait formatting

#### Primary ADRs

- **ADR-0005e** — Agent Personalities (4 AI agents, capability system)
- **ADR-0017d** — SessionState Persona Section

#### Related ADRs

- **ADR-0001b** — Model Hub (personality → LLM prompt injection)
- **ADR-0010** — Capability Security (personality-based capabilities)

#### Key Responsibilities

1. **AI Agent Personalities:**
   - **Concierge (50ms):** NLU, intent classification
   - **Planner (5000ms):** Task planning, LLM inference
   - **Researcher (3000ms):** Knowledge synthesis, retrieval
   - **Safety Watch (100ms):** Content filtering, PII detection

2. **Trait Formatting:** Format SessionState persona section as LLM system prompt (<5ms)
3. **Capability Assignment:** 5 capability types (TOOL_CALL, MEMORY_READ, MEMORY_WRITE, MODEL_CALL, NETWORK_ACCESS)

**Performance Metrics:**
- Trait formatting: <5ms
- LLM prompt injection: <1ms overhead
- Personality consistency: >95% (trait adherence)

---

### **Module 1.5: agents/mailbox/**
**Purpose:** Inter-agent messaging (MPSC queues)
**Location:** `k1/l3_execution/agents/mailbox/`
**Performance:** <1ms enqueue/dequeue

#### Primary ADRs

- **ADR-0002a** — Actor Fabric Mailbox (MPSC queue, 4-tier priority)
- **ADR-0028** — WFQ Scheduler (priority-based scheduling)

#### Related ADRs

- **ADR-0024** — Performance Budgets (mailbox <1ms)
- **ADR-0029** — Prometheus Metrics (mailbox depth, message rate)

#### Key Responsibilities

1. **MPSC Queue:** Ring buffer, 4-tier priority (URGENT/REALTIME/INTERACTIVE/BACKGROUND)
2. **Backpressure:** High watermark (50), low watermark (25), overflow policies (DROP_OLDEST)
3. **Dead Letter Queue:** 100 messages, 5 min retention, dropped reasons
4. **WFQ Scheduling:** Weight-based fairness (URGENT 10×, BACKGROUND 1×)

**Performance Metrics:**
- Enqueue: <1ms P95
- Dequeue: <0.5ms P95
- Mailbox depth: <10 typical, <50 high watermark
- Message throughput: 1000+ msgs/sec

---

### **Module 1.6: agents/active_roster/**
**Purpose:** Runtime agent tracking
**Location:** `k1/l3_execution/agents/active_roster/`
**Performance:** <1ms lookup/insert/remove

#### Primary ADRs

- **ADR-0005** — Agent Lifecycle (active roster integration)

#### Related ADRs

- **ADR-0029** — Prometheus Metrics (active agent count)

#### Key Responsibilities

1. **Agent Registry:** Hash table by agent_id, O(1) lookup
2. **State Tracking:** Current FSM state, last heartbeat, uptime
3. **Roster Operations:** Insert (hire), remove (fire), lookup (<1ms)

**Performance Metrics:**
- Lookup: <1ms P95
- Insert/remove: <1ms P95
- Active agent count: 5-20 typical

---

### **Module 1.7: agents/concierge/** (🤖 AI Agent)
**Purpose:** NLU & intent classification
**Location:** `k1/l3_execution/agents/concierge/`
**Performance:** <50ms P95

#### Primary ADRs

- **ADR-0005e** — Agent Personalities (Concierge: 50ms budget)
- **ADR-0001b** — Model Hub Integration (Concierge uses Model Hub)

#### Related ADRs

- **ADR-0024** — Performance Budgets (Concierge <50ms)
- **ADR-0027** — Model Placement (local-first SLM)
- **ADR-0031** — Cost Tracking (Concierge token usage)

#### Key Responsibilities

1. **Intent Classification:** NLU, intent extraction (T2/T3 fallback from Layer 1)
2. **Entity Extraction:** Named entity recognition (NER)
3. **Dialogue Act Classification:** Question, command, statement, clarification

**Performance Metrics:**
- Intent classification: <50ms P95
- Accuracy: >90% (intent), >85% (entity extraction)
- Model: Phi-3-mini (3.8B) on NPU/GPU

---

### **Module 1.8: agents/researcher/** (🤖 AI Agent)
**Purpose:** Knowledge synthesis & retrieval
**Location:** `k1/l3_execution/agents/researcher/`
**Performance:** <3000ms P95

#### Primary ADRs

- **ADR-0005e** — Agent Personalities (Researcher: 3000ms budget)
- **ADR-0001b** — Model Hub Integration (Researcher uses Model Hub)

#### Related ADRs

- **ADR-0001** — K0 Integration (multi-store retrieval)
- **ADR-0024** — Performance Budgets (Researcher <3000ms)
- **ADR-0027** — Model Placement (local-first, fallback remote)
- **ADR-0031** — Cost Tracking (Researcher token usage)

#### Key Responsibilities

1. **Knowledge Retrieval:** Multi-store query (episodic, semantic, procedural, KG)
2. **Synthesis:** Fuse results from multiple sources, generate coherent response
3. **Fact-Checking:** Validate retrieved information, confidence scoring

**Performance Metrics:**
- Knowledge retrieval: <3000ms P95
- Synthesis quality: >85% (human evaluation)
- Model: GPT-4o-mini or Claude-3-Haiku (local/remote)

---

### **Module 1.9: agents/factory/** (🔧 Dynamic Agent Creation)
**Purpose:** Agent factory pattern (on-demand spawning)
**Location:** `k1/l3_execution/agents/factory.py`
**Performance:** <100ms P95 creation

#### Primary ADRs

- **ADR-0086** — Dynamic Agent Creation Subsystem (58+ agent types, composition pattern)
- **ADR-0086a** — Agent Factory Pattern (singleton, ID generation, O(1) lookup)

#### Related ADRs

- **ADR-0005** — Agent Lifecycle (FSM integration)
- **ADR-0027** — Model Placement (thermal-aware placement)

#### Key Responsibilities

1. **Agent Creation:**
   - Create agents dynamically based on user requests
   - ID generation: `agent-{session_id}-{timestamp_ms}-{counter:06d}`
   - Factory singleton pattern (thread-safe)

2. **Agent Lookup:**
   - O(1) hash table lookup by agent_id
   - Registry integration (58+ agent types)

3. **Resource Integration:**
   - Thermal-aware accelerator placement
   - Resource reservation before spawn

**Performance Metrics:**
- Agent creation: <100ms P95
- Agent lookup: <1ms P95
- Factory overhead: <5ms

---

### **Module 1.10: agents/templates/** (🔧 Dynamic Agent Creation)
**Purpose:** Agent template system
**Location:** `k1/config/agent_templates/*.agent.yml`
**Performance:** <10ms P95 (cached)

#### Primary ADRs

- **ADR-0086b** — Template System (JSON Schema validation, LRU cache, inheritance)

#### Related ADRs

- **ADR-0086a** — Agent Factory (template consumer)

#### Key Responsibilities

1. **Template Management:**
   - JSON Schema v7 validation
   - LRU cache (128 templates, >80% hit rate)
   - 3-level inheritance: base_agent → base_ai_agent → specialist

2. **Template Loading:**
   - TemplateLoader class
   - Cached rendering <10ms P95, uncached <50ms

**Performance Metrics:**
- Template loading (cached): <10ms P95
- Template loading (uncached): <50ms P95
- Cache hit rate: >80%

---

### **Module 1.11: agents/resource_reserver/** (🔧 Dynamic Agent Creation)
**Purpose:** Resource reservation system
**Location:** `k1/l3_execution/agents/resource_reserver.py`
**Performance:** <50ms P95 reservation

#### Primary ADRs

- **ADR-0086c** — Resource Reservation (512MB budget, thermal placement, atomic allocation)

#### Related ADRs

- **ADR-0027** — Model Placement (accelerator allocation)
- **ADR-0026** — Thermal Management (thermal-aware placement)

#### Key Responsibilities

1. **Resource Allocation:**
   - Memory budget: 512MB global, 256MB per-agent max
   - Accelerator slots: NPU (2), GPU (1), CPU (4), Remote (∞)
   - Atomic allocation (RAII pattern)

2. **Thermal-Aware Placement:**
   - NPU → GPU → CPU → Remote fallback cascade
   - Thermal zone integration

**Performance Metrics:**
- Reservation: <50ms P95
- Release: <20ms P95
- Allocation success rate: >95%

---

### **Module 1.12: agents/composition/** (🔧 Dynamic Agent Creation)
**Purpose:** Agent composition pattern
**Location:** `k1/l3_execution/agents/composition.py`
**Performance:** <5ms P95 (cached)

#### Primary ADRs

- **ADR-0086d** — Agent Composition Pattern (prompt + tools + persona)

#### Related ADRs

- **ADR-0086e** — Prompt Directory (prompt source)
- **ADR-0010** — Capability Security (tool filtering)

#### Key Responsibilities

1. **Composition:**
   - Prompt (from prompt library) + Tools (capability-filtered) + Persona (traits)
   - Security: 10+ prompt injection patterns, token validation

2. **Tool Filtering:**
   - Capability-based tool selection (758 tools total)
   - Per-agent tool whitelist

**Performance Metrics:**
- Composition (cached): <5ms P95
- Composition (uncached): <30ms P95
- Tool filtering: <10ms

---

### **Module 1.13: model_hub/prompt_library/agent_prompts/** (🔧 Dynamic Agent Creation)
**Purpose:** Agent prompt directory
**Location:** `k1/l3_execution/model_hub/prompt_library/agent_prompts/`
**Performance:** <5ms P95 rendering

#### Primary ADRs

- **ADR-0086e** — Prompt Directory & Template Management (Jinja2 rendering, metadata)

#### Related ADRs

- **ADR-0086d** — Agent Composition (prompt consumer)

#### Key Responsibilities

1. **Prompt Library:**
   - Jinja2 template rendering
   - Metadata extraction (version, max_tokens, author, changelog)
   - Token validation (1 token ≈ 4 chars)

2. **Example Templates:**
   - `health_specialist.prompt.j2` (320 tokens)
   - `code_assistant.prompt.j2` (280 tokens)

**Performance Metrics:**
- Rendering: <5ms P95
- Template count: 58+ prompts

---

## Category 2: model_hub/ (7 modules)

### **Module 2.1: model_hub/router/**
**Purpose:** Model request routing
**Location:** `k1/l3_execution/model_hub/router/`
**Performance:** <5ms routing decision

#### Primary ADRs

- **ADR-0001b** — Model Hub Architecture (router as entry point)
- **ADR-0027** — Model Placement Cascade (4-tier: NPU→GPU→CPU→Remote)

#### Related ADRs

- **ADR-0024** — Performance Budgets (Model Hub <50ms)
- **ADR-0029** — Prometheus Metrics (routing decisions, model usage)
- **ADR-0031** — Cost Tracking (per-model token costs)

#### Key Responsibilities

1. **Request Routing:** Route ModelRequest to appropriate adapter (OpenAI, Anthropic, vLLM, Ollama)
2. **Model Selection:** Choose model based on request (task, budget, privacy band)
3. **Load Balancing:** Distribute across NPU/GPU/CPU resources

**Performance Metrics:**
- Routing decision: <5ms P95
- Routing accuracy: >99% (correct model selection)

---

### **Module 2.2: model_hub/placement_planner/**
**Purpose:** Thermal-aware placement
**Location:** `k1/l3_execution/model_hub/placement_planner/`
**Performance:** <10ms placement decision

#### Primary ADRs

- **ADR-0027** — Model Placement Cascade (NPU→GPU→CPU→Remote, thermal-aware)
- **ADR-0026** — Thermal Management (hysteresis matrix, 4-tier placement)
- **ADR-0005a** — WARMING State (placement integration)

#### Related ADRs

- **ADR-0024** — Performance Budgets (placement <10ms)
- **ADR-0029** — Prometheus Metrics (placement decisions)

#### Key Responsibilities

1. **Thermal-Aware Placement:** Monitor device temperature, choose accelerator
2. **4-Tier Cascade:** NPU (30ms, 10W) → GPU (50ms, 12W) → CPU (120ms, 15W) → Remote (500ms, 5W)
3. **Emergency Jump:** Critical temperature ≥85°C → immediate Remote placement
4. **KV Cache Transfer:** Copy cached tensors on failover (<30ms)

**Performance Metrics:**
- Placement decision: <10ms P95
- Failover latency: <100ms (detection 20ms + transfer 30ms + loading 50ms)
- Thermal compliance: 100% (respect thermal zones)

---

### **Module 2.3: model_hub/adapters/**
**Purpose:** Provider adapters (OpenAI, Anthropic, vLLM, Ollama)
**Location:** `k1/l3_execution/model_hub/adapters/`
**Performance:** Adapter overhead <5ms

#### Primary ADRs

- **ADR-0001b** — Model Hub Architecture (adapter pattern)
- **ADR-0027** — Model Placement (provider selection)

#### Related ADRs

- **ADR-0009** — Circuit Breaker (adapter resilience)
- **ADR-0024** — Performance Budgets (adapter <5ms overhead)

#### Key Responsibilities

1. **Unified Interface:** Consistent API across providers
2. **Provider Adapters:**
   - **OpenAI:** GPT-4o, GPT-4o-mini (remote)
   - **Anthropic:** Claude-3-Haiku, Claude-3-Sonnet (remote)
   - **vLLM:** Gemma-2-9B (local GPU)
   - **Ollama:** Phi-3-mini (local NPU/CPU)
3. **Request Translation:** Convert ModelRequest to provider format
4. **Response Normalization:** Standardize ModelResponse format

**Performance Metrics:**
- Adapter overhead: <5ms P95
- Provider support: 4 providers (OpenAI, Anthropic, vLLM, Ollama)

---

### **Module 2.4: model_hub/kv_cache_broker/**
**Purpose:** Global KV cache management (512MB budget)
**Location:** `k1/l3_execution/model_hub/kv_cache_broker/`
**Performance:** <2ms allocation

#### Primary ADRs

- **ADR-0025** — KV Cache Management (global allocator, hybrid eviction)
- **ADR-0025a** — Global Allocator (512MB device-wide budget)
- **ADR-0025b** — Hybrid Eviction (60% LRU + 40% LFU)
- **ADR-0025c** — Cache Warming (prefetch last 3 turns)
- **ADR-0025d** — Compression (zstd level 3, 70% reduction)
- **ADR-0025e** — Protection (never evict active turn)

#### Related ADRs

- **ADR-0024** — Performance Budgets (cache <2ms allocation)
- **ADR-0029** — Prometheus Metrics (hit rate >75%, eviction rate)

#### Key Responsibilities

1. **Global Allocator:** 512MB device-wide budget, per-session min 32MB, max 256MB
2. **Hybrid Eviction:** 60% recency weight + 40% frequency weight, >75% hit rate target
3. **Cache Warming:** Resume detection, prefetch last 3 turns (<50ms), async background
4. **Compression:** zstd level 3 (70% reduction), compress inactive >10 min, decompress <20ms
5. **Protection:** Never evict active turn, low priority (recently used), normal (inactive 5-30 min), high priority (inactive >30 min)

**Performance Metrics:**
- Allocation: <2ms P95
- Eviction decision: <5ms
- Hit rate: >75% target
- Miss penalty: 100-200ms (80-90% slower)
- Compression: <15ms (70% size reduction)
- Decompression: <20ms

---

### **Module 2.5: model_hub/prompt_library/**
**Purpose:** Prompt templates (Jinja2)
**Location:** `k1/l3_execution/model_hub/prompt_library/`
**Performance:** <5ms template rendering

#### Primary ADRs

- **ADR-0001b** — Model Hub Architecture (prompt library)
- **ADR-0007a** — Stage 1 Sketch (prompt engineering)

#### Related ADRs

- **ADR-0005e** — Agent Personalities (agent-specific prompts)

#### Key Responsibilities

1. **Prompt Templates:** Jinja2 templates, semantic versioning
2. **Agent Prompts:** agent_prompts/ directory (4 AI agents: Concierge, Planner, Researcher, Safety Watch)
3. **Template Rendering:** Fill template with context (<5ms)

**Performance Metrics:**
- Template rendering: <5ms P95
- Template count: 20+ templates (agent-specific + system)

---

### **Module 2.6: model_hub/fallback_cascade/**
**Purpose:** Model fallback routing
**Location:** `k1/l3_execution/model_hub/fallback_cascade/`
**Performance:** <10ms fallback decision

#### Primary ADRs

- **ADR-0027** — Model Placement Cascade (4-tier fallback)
- **ADR-0009** — Circuit Breaker (failure detection)

#### Related ADRs

- **ADR-0024** — Performance Budgets (fallback <10ms)
- **ADR-0031** — Cost Tracking (fallback cost impact)

#### Key Responsibilities

1. **Fallback Strategy:** NPU→GPU→CPU→Remote (automatic on failure)
2. **Failure Detection:** Timeout, exception, crash (<20ms detection)
3. **Circuit Breaker:** 5 consecutive failures → open circuit, 30s cooldown
4. **Max Retries:** 2 retries per target, 5s total cascade timeout

**Performance Metrics:**
- Fallback decision: <10ms P95
- Cascade success rate: >99% (at least one tier succeeds)
- Circuit breaker effectiveness: 92% cascade prevention

---

### **Module 2.7: model_hub/safety_filter/** (🤖 AI Agent)
**Purpose:** Content safety filtering
**Location:** `k1/l3_execution/model_hub/safety_filter/`
**Performance:** <100ms P95

#### Primary ADRs

- **ADR-0001b** — Model Hub Architecture (safety filter: 3-tier)
- **ADR-0005e** — Agent Personalities (Safety Watch: 100ms budget)

#### Related ADRs

- **ADR-0024** — Performance Budgets (Safety Watch <100ms)
- **ADR-0035** — PII Detection (integration)

#### Key Responsibilities

1. **3-Tier Safety:**
   - **Pre-filter:** PII detection, harmful keywords (<5ms)
   - **Post-filter:** Output validation, toxicity detection (<50ms)
   - **Safety Watch Agent:** LLM-based safety check (<100ms)

2. **PII Detection:** Regex (structured PII) + BERT-NER (unstructured PII)
3. **Harmful Content:** Hate speech, violence, sexual content detection

**Performance Metrics:**
- Pre-filter: <5ms P95
- Post-filter: <50ms P95
- Safety Watch: <100ms P95 (LLM invocation)
- False positive rate: <1%

---

## Category 3: tools/ (5 modules)

### **Module 3.1: tools/runner/**
**Purpose:** Tool execution engine (MCP/WASM/Process)
**Location:** `k1/l3_execution/tools/runner/`
**Performance:** <3000ms P95

#### Primary ADRs

- **ADR-0033** — Tool Execution (2D selection: protocol × sandbox)
- **ADR-0034** — MCP Protocol (JSON-RPC 2.0, 608 tools)

#### Related ADRs

- **ADR-0024** — Performance Budgets (tools <3000ms)
- **ADR-0029** — Prometheus Metrics (tool execution latency, success rate)
- **ADR-0032** — Egress Control (sandbox integration)

#### Key Responsibilities

1. **Tool Execution:** Execute tool via selected protocol+sandbox
2. **Timeout Enforcement:** Per-tool timeout (5s-300s), SIGTERM→5s→SIGKILL
3. **Result Collection:** Capture stdout/stderr, parse JSON response

**Performance Metrics:**
- Tool execution: <3000ms P95
- Timeout compliance: 95% (12K enforcements)
- Execution success rate: >90%

---

### **Module 3.2: tools/sandbox/**
**Purpose:** Isolation layers (MCP/WASM/Process/Container)
**Location:** `k1/l3_execution/tools/sandbox/`
**Performance:** <100ms sandbox setup

#### Primary ADRs

- **ADR-0033** — Tool Execution (sandbox selection)
- **ADR-0033b** — WASM Sandbox (Wasmtime runtime)
- **ADR-0033c** — Process Sandbox (4-layer defense)
- **ADR-0032** — Egress Control (network, filesystem, resource)

#### Related ADRs

- **ADR-0024** — Performance Budgets (sandbox <100ms)

#### Key Responsibilities

1. **WASM Sandbox:** Wasmtime runtime, zero native syscalls, WASI capabilities, <10ms instantiation
2. **Process Sandbox:** OS process isolation, 4-layer defense (network, filesystem, resource, audit)
3. **Container Sandbox:** Firecracker MicroVM (125ms boot), gVisor (user-space kernel)

**Performance Metrics:**
- WASM instantiation: <10ms
- Process spawn: <100ms
- Firecracker boot: 125ms
- Sandbox overhead: 10× slower (WASM), 1× (Process)

---

### **Module 3.3: tools/registry/**
**Purpose:** Tool catalog (JSON specs)
**Location:** `k1/l3_execution/tools/registry/`
**Performance:** <1ms lookup

#### Primary ADRs

- **ADR-0033** — Tool Execution (registry integration)
- **ADR-0007b** — Stage 2 Expand (tool registry lookup)

#### Related ADRs

- **ADR-0010** — Capability Security (tool capability declarations)

#### Key Responsibilities

1. **Tool Catalog:** 608 MCP-compatible tools + 150 direct API tools = 758 total
2. **ToolSpec:** schema_in, schema_out, latency_hint, cost_hint, band_required, capabilities
3. **O(1) Lookup:** Hash table by tool_id

**Performance Metrics:**
- Tool lookup: <1ms P95
- Registry size: 758 tools
- Specification parsing: <50ms at startup

---

### **Module 3.4: tools/adapters/**
**Purpose:** Protocol adapters (MCP, REST, CLI)
**Location:** `k1/l3_execution/tools/adapters/`
**Performance:** Adapter overhead <5ms

#### Primary ADRs

- **ADR-0033** — Tool Execution (protocol selection)
- **ADR-0034** — MCP Protocol (JSON-RPC adapter)

#### Key Responsibilities

1. **MCP Adapter:** JSON-RPC 2.0 client, stdio/HTTP transport (80% of tools)
2. **REST Adapter:** HTTP client, JSON payloads (15% of tools)
3. **CLI Adapter:** Subprocess invocation, stdin/stdout (5% of tools)

**Performance Metrics:**
- Adapter overhead: <5ms P95
- Protocol support: 3 protocols (MCP, REST, CLI)

---

### **Module 3.5: tools/control/**
**Purpose:** Runtime tool management
**Location:** `k1/l3_execution/tools/control/`
**Performance:** <10ms control operation

#### Primary ADRs

- **ADR-0033** — Tool Execution (control integration)
- **ADR-0009** — Circuit Breaker (tool resilience)

#### Key Responsibilities

1. **Tool Lifecycle:** Start, stop, restart tool processes
2. **Circuit Breaker:** 5 failures → open 30s (per tool)
3. **Health Monitoring:** Tool heartbeat, crash detection

**Performance Metrics:**
- Control operation: <10ms P95
- Circuit breaker effectiveness: 92% cascade prevention

---

## Category 4: dialogue/ (4 modules)

### **Module 4.1: dialogue/scoreboard/**
**Purpose:** Common ground tracking (QUD, referents)
**Location:** `k1/l3_execution/dialogue/scoreboard/`
**Performance:** <5ms update

#### Primary ADRs

- **ADR-0017b** — SessionState Scoreboard Section (QUD stack, entity tracking)

#### Related ADRs

- **ADR-0019** — SessionState Serialization (scoreboard section)

#### Key Responsibilities

1. **Questions Under Discussion (QUD):** Stack discipline, priority ordering (Roberts 1996)
2. **Entity Tracking:** Salience (0.0-1.0), last_mentioned_turn, pronoun mapping
3. **Common Ground:** Shared beliefs, grounding acts (Clark & Brennan 1991)

**Performance Metrics:**
- Scoreboard update: <5ms P95
- Salience decay: Exponential (0.9 per turn)
- Referent resolution: <200μs

---

### **Module 4.2: dialogue/state_tracker/**
**Purpose:** Dialogue state (beliefs, slots)
**Location:** `k1/l3_execution/dialogue/state_tracker/`
**Performance:** <5ms update

#### Primary ADRs

- **ADR-0017** — SessionState 6-Section Design (beliefs section)
- **ADR-0017a** — Beliefs Section (fact storage, confidence)

#### Related ADRs

- **ADR-0019** — SessionState Serialization (beliefs section)

#### Key Responsibilities

1. **Dialogue State:** Track user beliefs, intent history, slot filling
2. **Slot Tracking:** Extractvalues for structured tasks (flight booking, calendar event)
3. **Belief Updates:** Confidence scores, temporal decay, source tracking

**Performance Metrics:**
- State update: <5ms P95
- Slot filling accuracy: >90%

---

### **Module 4.3: dialogue/turn_manager/**
**Purpose:** Turn-taking logic, barge-in
**Location:** `k1/l3_execution/dialogue/turn_manager/`
**Performance:** <10ms turn transition

#### Primary ADRs

- **ADR-0003b** — Barge-In Protocol (3 states, 5 transitions)
- **ADR-0015d** — Token Streaming, Barge-In Handling

#### Related ADRs

- **ADR-0024** — Performance Budgets (barge-in <120ms)

#### Key Responsibilities

1. **Turn Management:** Track current speaker, turn boundaries
2. **Barge-In Detection:** VAD-based interrupt detection (<20ms)
3. **Cancellation:** SIGTERM to inference, stop TTS, stop audio (<120ms P95)

**Performance Metrics:**
- Turn transition: <10ms P95
- Barge-in detection: <20ms (VAD)
- Cancellation latency: <120ms P95 (total pipeline)

---

### **Module 4.4: dialogue/repair/**
**Purpose:** Conversation repair
**Location:** `k1/l3_execution/dialogue/repair/`
**Performance:** <10ms repair decision

#### Primary ADRs

- **ADR-0003b** — Clarification Protocol (4 states, 6 transitions, nested)

#### Key Responsibilities

1. **Repair Strategies:** Clarification request, rephrasing, confirmation
2. **Error Detection:** Misunderstanding, ambiguity, incomplete information
3. **Repair Triggering:** Automatic or user-initiated

**Performance Metrics:**
- Repair decision: <10ms P95
- Repair success rate: >85%

---

## 🔗 Cross-Cutting ADRs (Affect All Layer 3 Modules)

### **Architecture & Design**
- **ADR-0002** — Actor Model (all Layer 3 modules are actors: 4 AI agents + 18 pure actors)
- **ADR-0004** — 52-Module 5-Layer Architecture (Layer 3 definition)
- **ADR-0004b** — Import Linting (L3→L4/L5 only, no L3→L1/L2 imports)
- **ADR-0004d** — Layer 3 Integration Tests

### **Serialization & Data**
- **ADR-0011** — FlatBuffers Serialization (ModelRequest, ToolCallRequest, AgentState)
- **ADR-0012** — FlatBuffers Schemas (ModelRequest, ModelResponse, ToolDefinition, AgentHireRequest)
- **ADR-0013** — Schema Versioning
- **ADR-0019** — SessionState Serialization (Layer 3 reads beliefs, scoreboard, persona sections)

### **Observability**
- **ADR-0029** — Prometheus Metrics (agent lifecycle, Model Hub, tool execution, dialogue)
- **ADR-0030** — Trace Sampling (cognitive_trace_id propagation)

### **Performance & Reliability**
- **ADR-0024** — Performance Budgets (Layer 3: Model Hub <50ms, Tools <3000ms, Agent Hire <600ms)
- **ADR-0025** — KV Cache Management (512MB global budget, hybrid eviction)
- **ADR-0026** — Thermal Management (placement planner integration)
- **ADR-0027** — Model Placement Cascade (NPU→GPU→CPU→Remote)
- **ADR-0028** — WFQ Scheduler (Layer 3 uses REALTIME/INTERACTIVE queues)
- **ADR-0009** — Circuit Breaker (agent hire, Model Hub, tool execution resilience)

### **Security & Privacy**
- **ADR-0010** — Capability Security (agent capabilities, tool capabilities)
- **ADR-0032** — Egress Control (tool sandbox integration)
- **ADR-0035** — PII Detection (safety filter integration)

### **Cost & Resource Management**
- **ADR-0031** — Cost Tracking (Model Hub token usage, tool costs)

---

## 🎯 Layer 3 Performance Budget Breakdown

### **Total Layer 3 Budget: Varies by operation**

| Component | Budget | Typical | P95 | ADR |
|-----------|--------|---------|-----|-----|
| Agent hire (cold) | 600ms | 400ms | 600ms | ADR-0005 |
| Agent hire (warm pool) | 50ms | 30ms | 50ms | ADR-0005b |
| Agent fire | 50ms | 30ms | 50ms | ADR-0005c |
| Model Hub routing | 5ms | 3ms | 5ms | ADR-0001b |
| Model Hub inference (local) | 50ms | 30ms | 50ms | ADR-0027 |
| Model Hub inference (remote) | 500ms | 300ms | 500ms | ADR-0027 |
| Tool execution | 3000ms | 1500ms | 3000ms | ADR-0033 |
| Tool sandbox setup | 100ms | 50ms | 100ms | ADR-0033 |
| Dialogue state update | 5ms | 3ms | 5ms | ADR-0017 |
| Barge-in cancellation | 120ms | 80ms | 120ms | ADR-0024 |

---

## 🔄 Layer 3 Integration Points

### **Layer 3 ← Layer 2 (Agent Hire & Task Assignment)**

```
Layer 2 sends:                  Layer 3 receives:
──────────────                  ────────────────
AgentHireRequest         →      agents/hire_fire (spawn agent)
TaskAssignment           →      agent mailbox (execute step)
ToolCallRequest          →      tools/runner (execute tool)
```

### **Layer 3 → Layer 4 (SessionState & Runtime)**

```
Layer 3 writes:                 Layer 4 manages:
───────────────                 ────────────────
AgentState               →      session_state/control section
Scoreboard updates       →      session_state/scoreboard section
Belief updates           →      session_state/beliefs section
```

### **Layer 3 → Layer 5 (Infrastructure)**

```
Layer 3 calls:                  Layer 5 provides:
──────────────                  ────────────────
Thermal placement        →      thermal/placement_planner
KV cache allocation      →      kv_cache_broker
Circuit breaker          →      resilience/circuit_breaker
```

**Key Constraints:**
1. **Allowed imports:** L3→L4/L5 only (no L3→L1/L2)
2. **Direct calls L2→L3:** Agent hire, tool execution (synchronous)
3. **Async SessionState writes:** Batched updates (250ms interval)

---

## 🧪 Layer 3 Testing Strategy (ADR-0004d)

### **Integration Tests**

**Location:** `tests/integration/layer3/`

1. **Agent Lifecycle Tests:**
   - 6-state FSM transitions
   - WARMING: AI vs pure actor warmup
   - IDLE pooling: reactivation <50ms
   - DRAINING: 3-phase drain
   - Performance: hire <600ms, fire <50ms

2. **Model Hub Tests:**
   - Model routing (4 providers)
   - Placement planner (thermal-aware)
   - KV cache (allocation, eviction, hit rate >75%)
   - Fallback cascade (NPU→GPU→CPU→Remote)
   - Performance: inference <50ms (local), <500ms (remote)

3. **Tool Execution Tests:**
   - MCP protocol (JSON-RPC 2.0)
   - WASM sandbox (<10ms instantiation)
   - Process sandbox (4-layer defense)
   - Timeout enforcement (95% compliance)
   - Performance: execution <3000ms

4. **Dialogue Tests:**
   - Scoreboard updates (QUD, entity tracking)
   - State tracking (beliefs, slots)
   - Turn management (barge-in <120ms)
   - Conversation repair

5. **End-to-End Tests:**
   - Agent hire → tool execution → response
   - Multi-agent coordination
   - Error handling (crash, timeout, failure)
   - Performance: <5000ms P95 (full execution)

---

## 📊 Layer 3 Observability (ADR-0029)

### **Prometheus Metrics**

| Metric | Type | Labels | Description | ADR |
|--------|------|--------|-------------|-----|
| `layer3_agent_hire_latency_ms` | Histogram | agent_type, warmup_type (cold/warm) | Agent hire latency | ADR-0029 |
| `layer3_agent_crash_rate` | Counter | agent_type | Agent crashes | ADR-0029 |
| `layer3_model_hub_inference_ms` | Histogram | model, accelerator (NPU/GPU/CPU/Remote) | Model Hub inference latency | ADR-0029 |
| `layer3_kv_cache_hit_rate` | Gauge | - | KV cache hit rate (>75% target) | ADR-0029 |
| `layer3_tool_execution_ms` | Histogram | tool_id, sandbox (MCP/WASM/Process) | Tool execution latency | ADR-0029 |
| `layer3_tool_success_rate` | Gauge | tool_id | Tool execution success rate | ADR-0029 |
| `layer3_dialogue_repair_rate` | Counter | repair_type | Conversation repair events | ADR-0029 |

### **Grafana Dashboards**

**Layer 3 Overview Dashboard:**
- Agent lifecycle states (PENDING/WARMING/ACTIVE/IDLE/DRAINING/TERMINATED)
- Model Hub inference latency (local vs remote)
- KV cache metrics (hit rate, eviction rate)
- Tool execution success rate (per tool)
- Dialogue state evolution (beliefs, scoreboard)

---

## 📚 Complete ADR Reference List

### **Primary Layer 3 ADRs**

- **ADR-0004** — 52-Module 5-Layer Architecture
- **ADR-0005** — Agent Lifecycle (6-State FSM)
- **ADR-0001b** — Model Hub Architecture
- **ADR-0033** — Tool Execution (2D Selection)
- **ADR-0034** — MCP Protocol

### **Agent Lifecycle ADRs (Category 1: agents/)**

- **ADR-0002** — Actor Model (all agents are actors)
- **ADR-0002a** — Actor Fabric Mailbox (MPSC queue, 4-tier priority)
- **ADR-0002b** — Actor Fabric Supervisor (health monitoring)
- **ADR-0005** — Agent Lifecycle (6-State FSM)
- **ADR-0005a** — WARMING State (dual-path warmup)
- **ADR-0005b** — IDLE Pooling (TTL tracking, reactivation <50ms)
- **ADR-0005c** — DRAINING State (3-phase drain, 5s timeout)
- **ADR-0005d** — Supervisor (heartbeat monitoring, crash detection, blacklist)
- **ADR-0005e** — Agent Personalities (4 AI agents + 54 pure actors)
- **ADR-0010** — Capability Security (agent capability declarations)
- **ADR-0017d** — SessionState Persona Section (personality integration)
- **ADR-0028** — WFQ Scheduler (priority-based scheduling)
- **ADR-0086** — Dynamic Agent Creation Subsystem (on-demand agent spawning, 58+ types)
- **ADR-0086a** — Agent Factory Pattern (singleton factory, <100ms creation, O(1) lookup)
- **ADR-0086b** — Template System (JSON Schema, LRU cache, template inheritance)
- **ADR-0086c** — Resource Reservation (512MB budget, thermal placement, atomic allocation)
- **ADR-0086d** — Agent Composition Pattern (prompt + tools + persona, injection protection)
- **ADR-0086e** — Prompt Directory (Jinja2 rendering, token validation, <5ms P95)

### **Model Hub ADRs (Category 2: model_hub/)**

- **ADR-0001** — K0 Integration (multi-store retrieval)
- **ADR-0001b** — Model Hub Architecture (router, placement, adapters, KV cache, prompts, fallback, safety)
- **ADR-0007a** — Stage 1 Sketch (prompt engineering)
- **ADR-0009** — Circuit Breaker (failure detection, resilience)
- **ADR-0024** — Performance Budgets (Model Hub <50ms P95)
- **ADR-0025** — KV Cache Management (512MB global budget, hybrid eviction)
- **ADR-0025a** — Global Allocator (device-wide budget allocation)
- **ADR-0025b** — Hybrid Eviction (60% LRU + 40% LFU)
- **ADR-0025c** — Cache Warming (prefetch last 3 turns)
- **ADR-0025d** — Compression (zstd level 3, 70% reduction)
- **ADR-0025e** — Protection (never evict active turn)
- **ADR-0026** — Thermal Management (hysteresis matrix, 4-tier placement)
- **ADR-0027** — Model Placement Cascade (NPU→GPU→CPU→Remote)
- **ADR-0028** — WFQ Scheduler (preemption with KV cache checkpoint)
- **ADR-0028b** — Preemption (KV cache checkpoint <50ms)
- **ADR-0029** — Prometheus Metrics (model inference latency, placement decisions)
- **ADR-0031** — Cost Tracking (per-model token costs)
- **ADR-0035** — PII Detection (safety filter integration)

### **Tool Execution ADRs (Category 3: tools/)**

- **ADR-0007b** — Stage 2 Expand (tool registry lookup)
- **ADR-0009** — Circuit Breaker (tool resilience, 5 failures → 30s cooldown)
- **ADR-0010** — Capability Security (tool capability declarations)
- **ADR-0024** — Performance Budgets (tools <3000ms P95)
- **ADR-0029** — Prometheus Metrics (tool execution latency, success rate)
- **ADR-0032** — Egress Control (sandbox integration, network/filesystem/resource)
- **ADR-0033** — Tool Execution (2D selection: protocol × sandbox)
- **ADR-0033a** — MCP Protocol (JSON-RPC 2.0, stdio/HTTP transport)
- **ADR-0033b** — WASM Sandbox (Wasmtime runtime, <10ms instantiation)
- **ADR-0033c** — Process Sandbox (4-layer defense, band enforcement)
- **ADR-0033d** — Selection Logic (2D algorithm, fallback cascade)
- **ADR-0034** — MCP Protocol (JSON-RPC 2.0, 608 MCP-compatible tools)
- **ADR-0078** — Tool Call Batching (50ms window, dependency graph, parallel execution)

### **Dialogue ADRs (Category 4: dialogue/)**

- **ADR-0003b** — Barge-In Protocol (3 states, 5 transitions)
- **ADR-0003b** — Clarification Protocol (4 states, 6 transitions, nested)
- **ADR-0015d** — Token Streaming (barge-in handling)
- **ADR-0017** — SessionState 6-Section Design (beliefs, scoreboard, persona)
- **ADR-0017a** — Beliefs Section (fact storage, confidence)
- **ADR-0017b** — Scoreboard Section (QUD stack, entity tracking)
- **ADR-0019** — SessionState Serialization (beliefs, scoreboard sections)
- **ADR-0021c** — Turn History Retention Compliance (GDPR Article 5(e), 365-day baseline)
- **ADR-0024** — Performance Budgets (barge-in <120ms P95)
- **ADR-0054** — Turn Boundary Management (research foundation)
- **ADR-0054a** — Implicit Pause (TRP 0.5-2.5s)
- **ADR-0054b** — Explicit Submit (send button, Enter key)

### **FlatBuffers Serialization ADRs**

- **ADR-0011** — FlatBuffers Serialization (ModelRequest, ToolCallRequest, AgentState)
- **ADR-0012** — FlatBuffers Schemas (ModelRequest, ModelResponse, ToolDefinition, AgentHireRequest)
- **ADR-0013** — Schema Versioning (SemVer policy, 90-day deprecation)
- **ADR-0013a** — Version Registry (76 schemas × 3-5 versions = 228+ entries)
- **ADR-0013b** — CI/CD Automation (schema diff analysis, version bump validation)
- **ADR-0013c** — Deprecation Workflow (FlatBuffers annotations, notifications)
- **ADR-0013d** — Contract Testing (Pact-style tests, forward/backward compatibility)

### **WebSocket & SSE Communication ADRs**

- **ADR-0015** — WebSocket Binary Protocol (message envelope, 17 message types)
- **ADR-0015a** — Protocol Design (message types, client/server messages)
- **ADR-0015b** — Flow Control (ACK protocol, batch 5 messages or 1s)
- **ADR-0015c** — Reconnection (resume protocol, exponential backoff)
- **ADR-0015d** — Streaming (model inference integration, TTFT <150ms)
- **ADR-0015e** — Client SDK (TypeScript SDK, React hooks)
- **ADR-0016** — SSE Event Taxonomy (17 event types, 5 categories)
- **ADR-0016a** — Event Taxonomy (agent lifecycle, turn, tool, session, system events)
- **ADR-0016c** — Filtering (topic mappings, 60-70% bandwidth savings)
- **ADR-0016d** — Browser Integration (native EventSource, React hook)
- **ADR-0043c** — SSE Topic Routing (K0TopicRouter, at-least-once delivery)
- **ADR-0046** — SSE-WebSocket Bridge Configuration (max 10K connections)

### **Voice Pipeline ADRs**

- **ADR-0056** — Voice Pipeline Architecture (K0 P11 ASR, K0 P12 TTS)
- **ADR-0056a** — ASR Ingress (20ms frames, VAD, partial results)
- **ADR-0056d** — TTS Synthesis (prosody controls, SSML, streaming audio)
- **ADR-0056e** — Audio Output (jitter buffer 80ms, packet loss recovery)
- **ADR-0068** — Voice Quality (WER calculation, MOS estimation)

### **Cross-Cutting ADRs**

- **ADR-0002** — Actor Model (all Layer 3 modules are actors)
- **ADR-0004** — 52-Module 5-Layer Architecture (Layer 3 definition)
- **ADR-0004b** — Import Linting (L3→L4/L5 only, no L3→L1/L2 imports)
- **ADR-0004d** — Layer 3 Integration Tests (agent lifecycle, Model Hub, tools, dialogue)
- **ADR-0009** — Circuit Breaker (agent hire, Model Hub, tool execution resilience)
- **ADR-0010** — Capability Security (agent/tool capabilities)
- **ADR-0011** — FlatBuffers Serialization (Layer 3 schemas)
- **ADR-0012** — FlatBuffers Schemas (ModelRequest, ToolDefinition, AgentState)
- **ADR-0013** — Schema Versioning (SemVer policy)
- **ADR-0019** — SessionState Serialization (Layer 3 reads beliefs, scoreboard, persona)
- **ADR-0024** — Performance Budgets (Layer 3: Model Hub <50ms, Tools <3000ms, Agent Hire <600ms)
- **ADR-0028** — WFQ Scheduler (Layer 3 uses REALTIME/INTERACTIVE queues)
- **ADR-0029** — Prometheus Metrics (agent lifecycle, Model Hub, tool execution, dialogue)
- **ADR-0030** — Trace Sampling (cognitive_trace_id propagation)
- **ADR-0031** — Cost Tracking (Model Hub token usage, tool costs)
- **ADR-0032** — Egress Control (tool sandbox integration)
- **ADR-0035** — PII Detection (safety filter integration)

---

## 📊 ADR Statistics

**Total ADRs:** 121 (covering Layer 3 execution components)

**By Category:**

- Agent Lifecycle: 18 ADRs (includes ADR-0086, 0086a-e for dynamic agent creation)
- Model Hub: 18 ADRs
- Tool Execution: 13 ADRs
- Dialogue: 12 ADRs
- FlatBuffers: 8 ADRs
- WebSocket/SSE: 11 ADRs
- Voice Pipeline: 5 ADRs
- Cross-Cutting: 36 ADRs

**By Status:**

- ✅ Complete: 115 ADRs (100%)
- 🚧 In Progress: 0 ADRs
- 📋 Planned: 0 ADRs

**By Priority:**

- 🔴 CRITICAL: 5 ADRs (primary Layer 3 ADRs)
- 🟡 HIGH: 40 ADRs (core functionality)
- 🟢 MEDIUM: 50 ADRs (supporting features)
- ⚪ LOW: 20 ADRs (optimization, quality)

---

**Status:** ✅ **COMPLETE** — All Layer 3 ADRs mapped end-to-end
**Last Updated:** October 2025
**Total ADRs:** 121 ADRs covering Layer 3 execution (agents, model_hub, tools, dialogue, supporting infrastructure)
**Coverage:** 100% of Layer 3 modules (27/27 modules mapped across 4 categories, including 5 dynamic agent creation modules)
**Source:** Auto-generated from adr_reference.md component-level mappings
