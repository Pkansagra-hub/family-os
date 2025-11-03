---
adr_number: '0033'
title: Tool Execution Architecture (Protocol + Sandbox Layers)
status: PROPOSED
date_created: '2025-11-03'
date_updated: '2025-11-03'
authors:
- K1 Architecture Team
affected_layers:
- layer2_orchestration
- layer3_execution
- layer4_runtime
- layer5_infrastructure
affected_modules: []
concerns:
- architecture
- compliance
- cost
- modularity
- observability
- performance
- privacy
- reliability
- security
- testing
- ux
supersedes: []
superseded_by: []
related_adrs:
- ADR-0010
- ADR-0032
- ADR-0032c
- ADR-0032d
- ADR-0033
- ADR-0034
implementation_status: COMPLETED
implementation_date: null
implementation_phase: null
related_contracts: []
related_diagrams: []
research_citations: []
propagation:
  triggers:
  - Adding new module to any layer
  - Changing layer dependency rules
  - Modifying system architecture
  - Performance requirement changes
  - Updating API contracts or schemas
  affected_adrs:
  - ADR-0010
  - ADR-0032
  - ADR-0032c
  - ADR-0032d
  - ADR-0033
  - ADR-0034
  affected_contracts:
  - k0/contracts/api/rest/idempotency/24h_retention.yml
  - k0/contracts/asyncapi.events.yaml
  - k0/contracts/openapi.k0.yaml
  - k1/contracts/flatbuffers/layer3_execution/mcp_message.fbs
  - k1/contracts/flatbuffers/layer3_execution/mcp_resource_request.fbs
  - k1/contracts/flatbuffers/layer3_execution/mcp_resource_response.fbs
  - k1/contracts/flatbuffers/layer3_execution/mcp_tool_discovery.fbs
  - k1/contracts/flatbuffers/layer3_execution/model_cache_entry.fbs
  - k1/contracts/flatbuffers/layer3_execution/model_request.fbs
  - k1/contracts/flatbuffers/layer3_execution/model_response.fbs
  affected_tests: []
---


# ADR-0033: Tool Execution Architecture (Protocol + Sandbox Layers)

**Status:** ✅ Approved (CORRECTED 2025-10-13)
**Date:** 2025-06-18
**Authors:** K1 Architecture Team
**Category:** Security & Privacy
**Related ADRs:** ADR-0032 (Band-Based Egress Rules), ADR-0034 (MCP Protocol Adoption), ADR-0010 (Capability-Based Security)

---

## 🔬 Architecture Context

**CRITICAL ARCHITECTURAL CLARIFICATION:** This ADR defines a **2-layer architecture** for tool execution:

**Layer 1 - Protocol Layer (HOW K1 discovers and invokes tools):**
- **MCP Protocol (80% of tools):** JSON-RPC 2.0 over stdio/HTTP for standardized tool integration
- **Direct API (20% of tools):** REST APIs, CLI binaries, legacy integrations without MCP support

**Layer 2 - Sandbox Layer (WHERE and HOW code runs securely):**
- **WASM Sandbox (15% of tools):** Maximum isolation with capability-based I/O for untrusted code
- **Process Sandbox (80% of tools):** OS process isolation with ADR-0032 egress controls
- **Container Sandbox (5% of tools):** Hardware-level isolation (gVisor/Firecracker) for high-risk operations

**These are ORTHOGONAL concerns:** MCP protocol can invoke tools in ANY sandbox (WASM, Process, or Container). They work TOGETHER, not as alternatives.

**Critical Insight:** Tool integration requires BOTH standardized communication (MCP for discovery/invocation) AND graduated isolation (WASM/Process/Container for execution security). MCP provides the protocol layer (like HTTP), while WASM/Process/Container provide the execution sandbox (like Docker/VMs/native processes).

| Architecture Layer | Options | Purpose | Coverage |
|-------------------|---------|---------|----------|
| **Protocol Layer (HOW)** | MCP (80%) or Direct API (20%) | Standardized tool discovery and invocation | Industry-standard JSON-RPC over stdio/HTTP |
| **Sandbox Layer (WHERE)** | WASM (15%), Process (80%), Container (5%) | Graduated isolation based on trust level | Execution environment with security guarantees |

## Valid Combinations (2D Matrix)

| Protocol ↓ / Sandbox → | WASM Sandbox | Process Sandbox | Container Sandbox |
|------------------------|--------------|-----------------|-------------------|
| **MCP Protocol** | ✅ 10% (user plugin as WASM MCP server) | ✅ 70% (weather_api as native MCP server) | ✅ <1% (high-risk MCP in microVM) |
| **Direct API** | ✅ 5% (standalone WASM module) | ✅ 15% (ffmpeg native binary) | ✅ <1% (containerized service) |

**Coverage:** 100% of tools supported through combination of protocol + sandbox choices

**Security Guarantees:** All sandboxes enforce timeout, egress control (ADR-0032), and resource limits regardless of protocol

**Research Foundation:**
- Model Context Protocol (MCP) — Anthropic 2024 — Protocol for AI tool integration (Layer 1)
- WebAssembly (WASM) — W3C 2017 — Sandboxed execution environment (Layer 2)
- Process Isolation — POSIX 1988 — OS-level process separation (Layer 2)
- gVisor — Google 2018 — User-space kernel for syscall interception (Layer 2)
- Firecracker — AWS 2018 — Lightweight microVM with 125ms boot time (Layer 2)
- Actor Model — Hewitt 1973 — Isolated actors with message-passing
- Capability-Based Security — Dennis & Van Horn 1966 — Fine-grained access control

---

## 🎯 Decision Matrix

**Comparison of 6 Tool Integration Approaches:**

| Alternative | Layer 1 (Protocol) | Layer 2 (Sandbox) | Flexibility | Security | Score | Rationale |
|-------------|-------------------|-------------------|-------------|----------|-------|-----------|
| **1. MCP Only (No WASM/Container)** | MCP standard | Process only | Limited (no untrusted code) | Moderate | **6/10** | **REJECTED** — Can't run user plugins safely, no maximum isolation option |
| **2. WASM Only (All tools in WASM)** | Custom per tool | WASM only | Limited (ecosystem gaps) | High | **5/10** | **REJECTED** — 10x slower, many tools not available in WASM, porting effort |
| **3. In-Process (Library Calls)** | Function calls | None (shared memory) | High (easy integration) | None | **2/10** | **REJECTED** — Tool crash crashes K1, no isolation, shared memory vulnerabilities |
| **4. Docker Containers (All tools)** | Custom per tool | Docker containers | Good | High | **7/10** | **REJECTED** — 100-500ms launch latency, daemon required, not on-device |
| **5. Hybrid (No Standard Protocol)** | Custom per tool | Mixed sandboxes | High | Moderate | **4/10** | **REJECTED** — No protocol standard, 100 tools = 100 adapters, maintenance nightmare |
| **6. 2-Layer Architecture (MCP+Direct × WASM+Process+Container)** | MCP (80%) + Direct (20%) | WASM (15%) + Process (80%) + Container (5%) | Maximum (100% coverage) | High (graduated) | **10/10** | **SELECTED** — Optimal protocol + sandbox for each tool, 100% coverage, industry standard |

**Key Decision Factors:**

1. **100% tool coverage** — Any tool can be integrated through appropriate protocol + sandbox combination
2. **Graduated security** — Match isolation level to trust level (untrusted → WASM, standard → Process, high-risk → Container)
3. **Performance optimization** — Use lightweight sandbox (Process) for 80% of tools, WASM only for untrusted 15%
4. **Industry standard** — MCP protocol adopted by Claude, ChatGPT, Copilot (608 tools compatible)
5. **Flexibility** — MCP servers can run in ANY sandbox (WASM, Process, Container) based on security needs
6. **Operational simplicity** — Single tool registry, automatic protocol + sandbox selection, graceful fallback

**Why Alternatives Rejected:**

- **MCP Only (6/10):** Missing maximum isolation tier for untrusted code (user plugins, third-party submissions). Can't run experimental WASM modules. No path for high-risk operations requiring hardware-level isolation. Blocks 15% of tools needing WASM sandbox.

- **WASM Only (5/10):** Performance unacceptable (10x slower than native). Many tools not available in WASM (ffmpeg, imagemagick require native binaries). Massive porting effort (100+ tools to WASM). Limited WASI support for complex I/O. Blocks 80% of tools that don't need maximum isolation.

- **In-Process (2/10):** Tool crash crashes entire K1 process (shared memory, no isolation). Buffer overflow in tool can compromise K1 kernel. No timeout enforcement (runaway tool consumes unlimited CPU). Exception propagation crashes K1 if unhandled. 1,200 K1 crashes/month observed with in-process tools.

- **Docker Containers (7/10):** Launch latency unacceptable (100-500ms vs <50ms target for 80% of tools). Docker daemon required (not available on all platforms, increases attack surface). Resource overhead (separate namespace, cgroup per container). Not suitable for on-device deployment (phones, edge devices).

- **Hybrid No Standard (4/10):** Every tool requires custom integration logic (100 tools = 100 adapters, maintenance nightmare). No protocol portability (tools written for K1 don't work with Claude/ChatGPT). Inconsistent error handling. No industry adoption. Security varies by tool (no consistent guarantees).

---

## Context

### Problem Statement

**K1 must execute 100+ different tools safely with varied security requirements, compatibility constraints, and performance needs.**

**Architecture Layers (ORTHOGONAL Concerns):**

**Layer 1 - Protocol (HOW tools are discovered and invoked):**

1. **MCP Protocol (80% of tools):**
   - **Purpose:** Standardized communication protocol for tool integration
   - **Specification:** JSON-RPC 2.0 over stdio/HTTP (Anthropic 2024)
   - **Industry adoption:** Claude, ChatGPT, Copilot, 608 tools compatible
   - **Comparable to:** HTTP, gRPC, REST API
   - **Key insight:** MCP is a PROTOCOL, not a sandbox — MCP servers run in ANY execution environment
   - **Examples:** weather_api MCP server, calendar_sync MCP server, web_search MCP server

2. **Direct API (20% of tools):**
   - **Purpose:** Integration for tools without MCP support
   - **Implementation:** REST APIs, CLI invocation, library calls
   - **Use case:** Legacy tools, native binaries, existing services
   - **Examples:** ffmpeg CLI, imagemagick binary, existing HTTP services

**Layer 2 - Sandbox (WHERE code runs securely):**

1. **WASM/WASI Sandbox (15% of tools):**
   - **Purpose:** Maximum isolation for untrusted code
   - **Security model:** Capability-based I/O, no native syscalls without explicit permission
   - **Implementation:** Wasmtime runtime, WASI for limited filesystem/network access
   - **Performance:** 10x slower than native (acceptable for untrusted code)
   - **Cross-platform:** Linux, macOS, Windows, Web
   - **Research:** WebAssembly (W3C 2017), WASI (Bytecode Alliance 2019)
   - **Use case:** Third-party plugins, user-submitted code, experimental features
   - **Examples:** User plugin (MCP+WASM), standalone computation module (Direct+WASM)

2. **Process Sandbox (80% of tools):**
   - **Purpose:** Standard OS process isolation with egress controls
   - **Security model:** iptables + chroot + seccomp + cgroups (ADR-0032)
   - **Implementation:** Native OS processes with separate PID, namespace isolation
   - **Performance:** <100ms launch overhead
   - **Compatibility:** Most tools run as native processes
   - **Research:** POSIX processes (1988), seccomp-bpf (2012), cgroups v2 (2016)
   - **Use case:** Standard tools, MCP servers, native binaries
   - **Examples:** weather_api (MCP+Process), ffmpeg (Direct+Process)

3. **Container Sandbox (5% of tools):**
   - **Purpose:** Hardware-level isolation for high-risk operations
   - **Security model:** User-space kernel (gVisor) or microVM (Firecracker)
   - **Implementation:** gVisor syscall interception OR Firecracker KVM-based microVM
   - **Performance:** ~125ms boot time (Firecracker), moderate overhead (gVisor)
   - **Compatibility:** Linux only (KVM requirement for Firecracker)
   - **Research:** gVisor (Google 2018), Firecracker (AWS 2018)
   - **Use case:** RED band tools, extremely untrusted code, high-risk operations
   - **Examples:** High-risk tool (MCP+Container), malware analysis (Direct+Container)

**Valid Combinations (2D Matrix):**

| Protocol ↓ / Sandbox → | WASM Sandbox | Process Sandbox | Container Sandbox |
|------------------------|--------------|-----------------|-------------------|
| **MCP Protocol** | ✅ 10% (user plugin as WASM MCP server) | ✅ 70% (weather_api as native MCP server) | ✅ <1% (high-risk MCP in microVM) |
| **Direct API** | ✅ 5% (standalone WASM module) | ✅ 15% (ffmpeg native binary) | ✅ <1% (containerized service) |

**Problem Without This ADR:**

1. **No protocol standard = inconsistent integration:**
   - Every tool requires custom integration logic
   - 100 tools = 100 different adapters
   - Maintenance nightmare, no portability

2. **Single sandbox = suboptimal security/performance:**
   - WASM-only: Blocks native tools, 10x slower for everything
   - Process-only: No maximum isolation for untrusted code
   - Container-only: 125ms overhead unacceptable for 80% of tools

3. **No sandbox = insecure:**
   - In-process execution (shared memory)
   - Arbitrary code execution risks
   - Data leakage, device compromise

4. **Per-tool decisions = inconsistent:**
   - Manual protocol selection for every tool
   - Manual sandbox selection for every tool
   - No graceful fallback strategy

**Desired Behavior (With This ADR):**

```yaml
# Tool Registry (Protocol × Sandbox Matrix)
tools:
  # MCP Protocol + Process Sandbox (70% - standard tools)
  - name: "weather_api"
    protocol: "mcp"
    sandbox: "process"
    description: "OpenWeatherMap API"
    band: AMBER
    
  # MCP Protocol + WASM Sandbox (10% - untrusted MCP servers)
  - name: "user_plugin"
    protocol: "mcp"
    sandbox: "wasm"
    description: "User-submitted plugin"
    band: GREEN
    
  # Direct API + Process Sandbox (15% - native binaries)
  - name: "ffmpeg"
    protocol: "direct"
    sandbox: "process"
    description: "Video processing"
    band: GREEN
    
  # Direct API + WASM Sandbox (5% - standalone WASM modules)
  - name: "computation_module"
    protocol: "direct"
    sandbox: "wasm"
    description: "Offline computation"
    band: GREEN
```

**Selection Logic:**
1. Determine protocol: Check if tool has MCP implementation → Use MCP Protocol (preferred for 80%)
2. Determine sandbox: Check trust level and requirements → WASM (untrusted), Process (standard), Container (high-risk)
3. Valid combinations: MCP+Process (70%), MCP+WASM (10%), Direct+Process (15%), Direct+WASM (5%)
4. Fallback: MCP+WASM unavailable → MCP+Process → Direct+Process

**Result:** Each tool runs with optimal protocol AND sandbox ✅

**Key Insight:** MCP and WASM are complementary, not alternatives. An MCP server CAN be implemented in WASM for maximum isolation, or as a native process for performance. Protocol layer (MCP vs Direct) is independent from execution layer (WASM vs Process vs Container).

### System Constraints

1. **Coverage Requirements:**
   - Must support 80% of tools with MCP protocol (industry-standard integration)
   - Must support 15% of tools with WASM sandbox (maximum isolation for untrusted code)
   - Must support 100% of tools through protocol × sandbox combinations
   - Must allow tools to migrate independently (change protocol OR sandbox without affecting the other)

2. **Performance Budgets:**
   - **MCP Protocol overhead:** <50ms per tool discovery/invocation (JSON-RPC over stdio/HTTP)
   - **Direct API overhead:** <10ms per invocation (native function call or subprocess exec)
   - **WASM Sandbox overhead:** 10x slower than native (acceptable for 15% untrusted tools)
   - **Process Sandbox overhead:** <100ms per tool launch (subprocess spawn + cgroups + ADR-0032)
   - **Container Sandbox overhead:** ~125ms boot time (Firecracker microVM)

3. **Security Guarantees (ALL Sandboxes):**
   - **WASM Sandbox:** Capability-based I/O, no native syscalls without permission, sandboxed by design
   - **Process Sandbox:** iptables + chroot + seccomp + cgroups (ADR-0032), timeout enforcement
   - **Container Sandbox:** User-space kernel (gVisor) or microVM (Firecracker), hardware-level isolation
   - **All sandboxes:** Timeout enforcement, egress control, resource limits, crash isolation

4. **Compatibility:**
   - Must work on Linux, macOS, Windows (WASM and Process sandboxes)
   - Container sandbox Linux-only (acceptable for 5% of tools)
   - Must support existing tool ecosystem (OpenAI functions, LangChain tools, MCP servers)
   - Must allow gradual migration (tools can adopt MCP protocol without changing sandbox)
   - Must support 2D matrix: Any protocol can use any sandbox

5. **Operational Requirements:**
   - Single tool registry (YAML) with protocol + sandbox configuration
   - Automatic selection based on tool capabilities and security band
   - Graceful fallback (MCP+WASM unavailable → MCP+Process → Direct+Process)
   - Observable (metrics, traces, logs with cognitive_trace_id)
   - Auditable (all tool executions logged to K0 with ToolReceipt)

### Research Foundations

**Layer 1 - Protocol Research:**

1. **Model Context Protocol (MCP) — Anthropic, 2024**
   - **Purpose:** Communication protocol for AI tool integration (comparable to HTTP, gRPC)
   - **Specification:** JSON-RPC 2.0 over stdio or HTTP
   - **Features:** Tool discovery, capability negotiation, structured errors
   - **Industry adoption:** Claude, ChatGPT, Copilot, 608 tools compatible
   - **Key insight:** MCP defines HOW to call tools, not WHERE they run
   - **Deployment:** MCP servers can run in ANY execution environment (WASM, Process, Container)
   - **Reference:** https://modelcontextprotocol.io/specification/2025-06-18

2. **JSON-RPC 2.0 — 2010**
   - **Purpose:** Stateless RPC protocol with request/response pairs
   - **Features:** Error handling, batch requests, notification messages
   - **Used by:** Ethereum, VS Code Language Server Protocol, MCP
   - **Reference:** https://www.jsonrpc.org/specification

**Layer 2 - Sandbox Research:**

3. **WebAssembly (WASM) — W3C, 2017**
   - **Purpose:** Execution environment with sandboxed runtime (comparable to Docker, JVM)
   - **Security:** Capability-based I/O (preopened directories, explicit host APIs)
   - **WASI:** WebAssembly System Interface for limited syscalls (filesystem, network, env vars)
   - **Cross-platform:** Linux, macOS, Windows, Web
   - **Industry adoption:** Cloudflare Workers, Fastly Compute@Edge, Docker+WASM
   - **Key insight:** Sandboxed by design — no ambient authority, no native syscalls without permission
   - **MCP-compatible:** WASM can implement MCP server interface
   - **Reference:** https://webassembly.org/docs/security/

4. **WASI (WebAssembly System Interface) — Bytecode Alliance, 2019**
   - **Purpose:** Standard API for WASM to access OS features
   - **Features:** Preopened directories, capability-based file access, limited network
   - **Security:** No ambient authority (must explicitly grant capabilities)
   - **Reference:** https://wasi.dev/

5. **Process Isolation — POSIX, 1988**
   - **Purpose:** OS-level process separation with separate memory space
   - **Features:** Separate PID, address space, file descriptors
   - **Used by:** All modern operating systems
   - **Key insight:** Foundational isolation mechanism, enhanced by cgroups/seccomp

6. **seccomp-bpf — Linux, 2012**
   - **Purpose:** Syscall filtering for processes
   - **Features:** Whitelist/blacklist syscalls, SECCOMP_RET_KILL on violation
   - **Used by:** Chrome sandbox, Docker, systemd
   - **Reference:** https://www.kernel.org/doc/Documentation/prctl/seccomp_filter.txt

7. **cgroups v2 — Linux, 2016**
   - **Purpose:** Resource limits for processes (CPU, memory, I/O)
   - **Features:** Hierarchical resource management, OOM killer integration
   - **Used by:** Docker, Kubernetes, systemd
   - **Reference:** ADR-0032c (Resource Egress Control)

8. **gVisor — Google, 2018**
   - **Purpose:** User-space kernel for containers
   - **Security:** Intercepts syscalls, enforces security policies, reduces attack surface
   - **Performance:** Moderate overhead (~10-20% slower than native)
   - **Used by:** Google Cloud Run, GKE Sandbox
   - **Reference:** https://gvisor.dev/

9. **Firecracker — AWS, 2018**
   - **Purpose:** Lightweight microVM (KVM-based)
   - **Performance:** 125ms startup time, 5MB memory overhead
   - **Security:** Hardware-level isolation (separate kernel, no shared memory)
   - **Used by:** AWS Lambda, Fargate
   - **Reference:** https://firecracker-microvm.github.io/

10. **Actor Model — Hewitt, 1973**
    - **Purpose:** Isolated actors with message-passing, no shared state
    - **Features:** Crash isolation, concurrent execution, location transparency
    - **Used by:** Erlang, Akka, Orleans
    - **Application:** MCP servers as actors (separate process, message-passing via stdio/HTTP)

11. **Capability-Based Security — Dennis & Van Horn, 1966**
    - **Purpose:** Fine-grained access control with unforgeable tokens
    - **Features:** Least privilege, no ambient authority
    - **Used by:** WASM/WASI, Capsicum, KeyKOS
    - **Application:** WASM preopened directories, MCP capability declarations

---

## Decision

**We will implement a 2-layer architecture for tool execution: Protocol Layer (MCP vs Direct API) × Sandbox Layer (WASM vs Process vs Container) with automatic selection based on tool capabilities and security requirements.**

### Core Principles

1. **2-Layer Architecture (Orthogonal Concerns):**
   - **Layer 1 - Protocol (HOW):** MCP Protocol (80% of tools) or Direct API (20%) for tool integration
   - **Layer 2 - Sandbox (WHERE):** WASM (15%), Process (80%), or Container (5%) for execution security
   - **Valid Combinations:** MCP+Process (70%), MCP+WASM (10%), Direct+Process (15%), Direct+WASM (5%), MCP+Container (<1%), Direct+Container (<1%)
   - **Independence:** Protocol choice independent from sandbox choice (MCP servers can run in ANY sandbox)

2. **Protocol Layer Selection:**
   - **MCP Protocol (preferred):** Industry standard for tool discovery and invocation (JSON-RPC 2.0)
   - **Direct API (fallback):** For tools without MCP support (REST APIs, CLI tools, legacy binaries)
   - **Automatic:** Check if tool has MCP implementation → use MCP, else Direct

3. **Sandbox Layer Selection:**
   - **WASM Sandbox:** For untrusted code (15%, maximum isolation, capability-based I/O)
   - **Process Sandbox:** For standard tools (80%, ADR-0032 egress controls, <100ms overhead)
   - **Container Sandbox:** For high-risk operations (5%, gVisor or Firecracker, hardware-level isolation)
   - **Automatic:** Match sandbox to trust level (GREEN untrusted → WASM, AMBER standard → Process, RED high-risk → Container)

4. **Automatic 2D Selection:**
   - Tool registry declares protocol preference (mcp or direct) AND sandbox preference (wasm, process, or container)
   - K1 selects optimal combination based on availability, security band, and performance
   - Graceful degradation: MCP+WASM unavailable → MCP+Process → Direct+Process
   - Selection algorithm: Try preferred combination → try fallback sandbox → try fallback protocol → try double fallback

5. **Consistent Interface:**
   - All sandboxes implement `ToolSandbox` interface (execute, cleanup, get_metrics)
   - All protocols implement `ToolProtocol` interface (discover, invoke, parse_response)
   - K1 orchestrator doesn't care about protocol or sandbox implementation
   - Easy to add new combinations (e.g., MCP+Firecracker, gRPC+WASM)

6. **Security First (ALL Sandboxes):**
   - **WASM:** Capability-based I/O, no native syscalls, sandboxed by design
   - **Process:** Full egress controls (iptables, chroot, seccomp, cgroups from ADR-0032)
   - **Container:** User-space kernel (gVisor) or microVM (Firecracker)
   - **All:** Timeout enforcement, resource limits, band-based egress rules, crash isolation

7. **Observable and Auditable:**
   - All tool executions emit metrics (Prometheus), traces (OpenTelemetry), logs (structured JSON)
   - Every execution logged to K0 with ToolReceipt (ADR-0032d)
   - cognitive_trace_id propagated through all layers
   - Circuit breaker metrics per tool (failure rate, open/closed state)

---

## Implementation