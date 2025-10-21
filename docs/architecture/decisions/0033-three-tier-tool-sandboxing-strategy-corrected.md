# ADR-0033: Three-Tier Tool Sandboxing Strategy

**Status:** ✅ Approved  
**Date:** 2025-10-13  
**Decision Owner:** Security Lead  
**Authors:** K1 Architecture Team  
**Category:** Security & Privacy  
**Related ADRs:** ADR-0010 (Capability-Based Security), ADR-0032 (Band-Based Egress Rules), ADR-0034 (MCP Protocol)

---

## Context

**Problem:** K1 executes third-party and first-party tools of varying trust levels. We need graduated isolation to bound blast radius without excessive latency overhead.

**Forces:**

1. **Security:** Untrusted tools must not compromise K1 kernel or access unauthorized resources
2. **Performance:** Sandbox overhead must be proportional to risk (don't use microVMs for simple calculators)
3. **Compatibility:** Must support WASM-compiled tools, native binaries, and legacy OS utilities
4. **Capability Security:** Tools must declare required capabilities (filesystem, network, syscalls)

**Current State:** Without tiered sandboxing:
- In-process execution → Tool crash crashes K1 (unacceptable)
- Single-tier containers → Either too heavy (microVMs for all) or too weak (Docker for untrusted code)
- Per-tool decisions → Inconsistent security posture, manual routing

---

## Decision

**We adopt a three-tier sandboxing strategy with automatic routing based on tool risk band and declared capabilities:**

### Tier A: WASM/WASI Sandbox (Default for AMBER tools)

**When:** Tool is WASM-compiled OR has minimal I/O needs  
**Runtime:** Wasmtime (or equivalent WASM runtime)  
**Isolation:** Capability-based I/O (preopened directories, explicit host APIs)  
**Overhead:** <10ms startup, near-native execution speed  
**Best For:** 80% of tools (calculators, data transformers, simple APIs)

**Example:** weather_api tool compiled to WASM with WASI sockets for HTTP

### Tier B: gVisor Sandboxed Process (Native binaries with POSIX needs)

**When:** Tool requires native binary OR broad POSIX syscalls not available in WASI  
**Runtime:** gVisor (user-space kernel with syscall interception)  
**Isolation:** Syscall filtering, separate process namespace, resource limits (cgroups)  
**Overhead:** ~50ms startup, syscall mediation adds ~10% CPU  
**Best For:** 15% of tools (native binaries, legacy tools, complex filesystem operations)

**Example:** ffmpeg for video transcoding, imagemagick for image processing

### Tier C: Firecracker MicroVM (RED band / high-risk / untrusted)

**When:** Tool handles sensitive data OR is untrusted third-party code OR requires kernel-level isolation  
**Runtime:** Firecracker microVM with minimal device model  
**Isolation:** Hardware-level VM isolation, separate kernel, no shared memory  
**Overhead:** ~125ms cold start (keep hot pools for <50ms)  
**Best For:** 5% of tools (user-submitted plugins, RED band operations, multi-tenant scenarios)

**Example:** User-submitted data analysis plugin with unknown provenance

---

## Routing Policy

**Automatic tier selection based on:**

```yaml
Tool Declaration:
  - capabilities: [filesystem_read, network_http]
  - risk_band: AMBER
  - wasm_available: true

Routing Logic:
  1. Check risk_band:
     - GREEN → Tier A (WASM) if available, else Tier B
     - AMBER → Tier A (WASM) if available, else Tier B
     - RED → Tier C (Firecracker) mandatory
     - BLACK → No execution (isolated compute only)
  
  2. Check capabilities:
     - Minimal I/O (preopened dirs, HTTP only) → Tier A
     - Broad POSIX (fork, exec, raw sockets) → Tier B
     - Kernel access or untrusted → Tier C
  
  3. Select lowest tier that satisfies risk (A < B < C)
```

**Principle:** Use lightest sandbox that meets security requirements. Don't use microVMs for simple math.

---

## Consequences

### Positive

1. **Defense in Depth:** Multiple isolation boundaries (WASM sandbox → gVisor → Firecracker)
2. **Performance Proportional to Risk:** Simple tools run fast (Tier A), dangerous tools isolated (Tier C)
3. **Objective Routing:** Automated tier selection eliminates per-tool manual decisions
4. **Industry Standards:** Leverages mature sandbox technologies (WASM, gVisor, Firecracker)

### Negative

1. **Operational Complexity:** Must maintain three different runtimes (Wasmtime, gVisor, Firecracker)
2. **Image Formats:** Tools must be packaged as WASM modules OR container images OR VM images
3. **VM Pool Management:** Firecracker requires hot pool for acceptable latency (<50ms target)
4. **Learning Curve:** Developers must understand capability model and tier selection

### Risks & Mitigations

| Risk | Mitigation |
|------|-----------|
| WASM runtime escape | Pin Wasmtime version, security audit, upstream CVE monitoring |
| gVisor syscall bypass | Regular updates, seccomp-bpf as second layer (ADR-0032) |
| Firecracker cold start latency | Maintain hot pool (3-5 VMs), 125ms acceptable for RED band |
| Developer confusion | Tool Descriptor schema, automated admission controller |

---

## Alternatives Considered

### Alternative 1: Single-Tier Containers Only

**Approach:** Run all tools in Docker/Podman containers

**Pros:** Simpler operationally, single runtime

**Cons:**
- ❌ Weaker isolation than gVisor (shared kernel, larger attack surface)
- ❌ No microVM-level isolation for RED band
- ❌ Overkill for simple tools (100ms+ startup for calculators)

**Verdict:** ❌ **Rejected** — Insufficient isolation for high-risk tools, excessive overhead for low-risk

### Alternative 2: MicroVMs for Everything

**Approach:** Run all tools in Firecracker microVMs

**Pros:** Maximum isolation, consistent security model

**Cons:**
- ❌ 125ms cold start unacceptable for 80% of tools (latency budget: <50ms)
- ❌ High resource overhead (5MB per VM, memory/CPU allocation)
- ❌ Operational complexity (VM pool management, image distribution)

**Verdict:** ❌ **Rejected** — Overkill latency/resource cost for low-risk tools

### Alternative 3: In-Process Plugins

**Approach:** Load tools as shared libraries (.so/.dll) in K1 process

**Pros:** Zero overhead, simplest integration

**Cons:**
- ❌ **Unacceptable blast radius** — Tool crash crashes entire K1 kernel
- ❌ No isolation — Tool can access all K1 memory and state
- ❌ Violates security principle: untrusted code must be sandboxed

**Verdict:** ❌ **Rejected** — Catastrophic security risk

### Alternative 4: Two-Tier (WASM + Containers)

**Approach:** Only WASM and Docker, no gVisor or Firecracker

**Pros:** Simpler runtime management

**Cons:**
- ❌ Missing middle tier — Jump from WASM straight to full containers (no gVisor)
- ❌ No microVM isolation for RED band — Containers insufficient for untrusted code
- ❌ Forces WASM recompilation for all native tools

**Verdict:** ❌ **Rejected** — Missing graduated isolation for native binaries

---

## Compliance & Acceptance Criteria

### Tool Descriptor Schema

Every tool must declare:

```yaml
tool:
  name: "weather_api"
  risk_band: AMBER
  capabilities:
    - filesystem_read: ["/tmp/weather_cache"]
    - network_http: ["api.openweathermap.org"]
    - time_budget_ms: 5000
  sandbox_preference: wasm  # wasm | native | microvm
  wasm_module: "/opt/k1/tools/weather_api.wasm"  # Optional: WASM build
  native_binary: "/opt/k1/tools/weather_api"     # Optional: native fallback
```

### Admission Controller

Must automatically select tier based on:
1. Risk band (GREEN/AMBER/RED/BLACK)
2. Declared capabilities (filesystem, network, syscalls)
3. WASM availability (prefer Tier A if available)
4. Latency budget (prefer lower tier if acceptable)

### Security Review

- **WASI preopens:** Validate filesystem access limited to declared paths
- **gVisor sec profile:** Validate syscall whitelist matches capabilities
- **Firecracker VM policy:** Validate device model minimized (no GPU, limited network)

---

## Implementation Notes

### Tier A: WASM/WASI Setup

```rust
// k1/tool_runner/wasm_executor.rs
use wasmtime::*;

let engine = Engine::default();
let module = Module::from_file(&engine, "weather_api.wasm")?;

// Pre-open directory (capability grant)
let mut linker = Linker::new(&engine);
let wasi = WasiCtxBuilder::new()
    .preopened_dir(Dir::open_ambient_dir("/tmp/weather_cache", ambient_authority())?, "/cache")?
    .build();

let mut store = Store::new(&engine, wasi);
let instance = linker.instantiate(&mut store, &module)?;
```

**Reference:** [Wasmtime Security](https://docs.wasmtime.dev/security.html)

### Tier B: gVisor Setup

```bash
# Install gVisor runtime
sudo apt-get install runsc

# Docker integration
docker run --runtime=runsc-kvm \
  --cap-drop=ALL \
  --read-only \
  --tmpfs /tmp \
  k1/tools/ffmpeg:latest
```

**Reference:** [gVisor Documentation](https://gvisor.dev/docs/)

### Tier C: Firecracker Setup

```rust
// k1/tool_runner/firecracker_executor.rs
use firecracker_rs::*;

let vm = VirtualMachine::new()
    .boot_source("/opt/k1/vmlinux")
    .root_drive("/opt/k1/tools/user_plugin.ext4")
    .vsock(3, "/tmp/firecracker.sock")
    .mem_size_mib(128)
    .vcpu_count(1)
    .start()?;
```

**Reference:** [Firecracker GitHub](https://firecracker-microvm.github.io/)

---

## Performance Targets

| Tier | Startup (P95) | Execution Overhead | Memory per Tool |
|------|---------------|-------------------|-----------------|
| A: WASM | <10ms | <5% | 10MB |
| B: gVisor | <50ms | ~10% | 50MB |
| C: Firecracker | <125ms (cold), <50ms (hot pool) | <2% (VM overhead) | 128MB |

---

## References

1. **WebAssembly Security** — [webassembly.org/docs/security](https://webassembly.org/docs/security/)
2. **Wasmtime Security Model** — [docs.wasmtime.dev/security.html](https://docs.wasmtime.dev/security.html)
3. **gVisor Documentation** — [gvisor.dev/docs](https://gvisor.dev/docs/)
4. **Firecracker MicroVM** — [firecracker-microvm.github.io](https://firecracker-microvm.github.io/)
5. **WASI Capability Model** — [GitHub: WebAssembly/WASI](https://github.com/WebAssembly/WASI)

---

**Status:** ✅ Ready for implementation  
**Timeline:** 12 weeks (4 weeks per tier)  
**Priority:** ⭐⭐⭐ Critical (Security foundation)
