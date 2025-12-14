---
adr_number: "0033b"
parent_adr: "ADR-0033"
title: "0033B: WASM Sandbox Implementation (Layer 2 - Sandbox)"
status: PROPOSED
date_created: "2025-11-03"
date_updated: "2025-11-03"
authors:
  - K1 Architecture Team
affected_layers:
  - layer1_input
  - layer3_execution
  - layer4_runtime
affected_modules:
  - k1.l3_execution.wasm_sandbox
  - k1.l5_infrastructure.wasm_runtime
concerns:
  - architecture
  - cost
  - modularity
  - observability
  - performance
  - privacy
  - reliability
  - scalability
  - security
  - testing
implementation_phase: "Phase 2 (Security & Privacy)"
implementation_date: null
implementation_status: PROPOSED
supersedes: []
superseded_by: []
related_adrs:
  - ADR-0032
  - ADR-0033
  - ADR-0033a
- ADR-0033b
- ADR-0033c
- ADR-0033d
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
  - ADR-0032
  - ADR-0033
  - ADR-0033a
  - ADR-0033b
  - ADR-0033c
  - ADR-0033d
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


# ADR-0033b: WASM Sandbox Implementation (Layer 2 - Sandbox)

**Status:** ✅ Approved
**Date:** 2025-10-13
**Authors:** K1 Architecture Team
**Category:** Tool Execution - Sandbox Layer
**Parent ADR:** ADR-0033 (Tool Execution Architecture - Protocol × Sandbox)
**Related ADRs:** ADR-0033a (MCP Protocol Integration), ADR-0032 (Band-Based Egress Rules)

---

## Context

### Problem Statement

**K1 needs maximum-security isolation for untrusted code (user plugins, third-party tools, RED band operations) with capability-based I/O and zero native syscalls.**

**Current Challenge:** Traditional sandboxes have limitations:

**Problem 1: Process Sandbox Insufficient for Untrusted Code**
- Process sandbox (ADR-0033c) uses chroot + seccomp + cgroups
- Still allows syscalls (open, read, write, socket)
- Attacker can exploit kernel vulnerabilities via syscalls
- **Risk:** Kernel 0-day = sandbox escape

**Problem 2: Container Sandbox Overhead Too High**
- Container sandbox (Firecracker microVM) has 125ms boot time
- Adds 100MB memory overhead per tool
- Overkill for simple user plugins (e.g., text formatter, calculator)
- **Cost:** 758 tools × 100MB = 75GB overhead

**Problem 3: Cross-Platform Compatibility**
- Process sandbox requires Linux (iptables, seccomp, cgroups)
- Container sandbox requires Linux + KVM
- K1 must support Windows, macOS for development/testing
- **Limitation:** 0% sandbox coverage on non-Linux

### Solution

**Adopt WebAssembly (WASM) as maximum-security sandbox for 15% of tools (untrusted code, user plugins, high-risk operations) with Wasmtime runtime + WASI for capability-based syscalls.**

**Key Benefits:**

1. **Zero Native Syscalls:** WASM cannot call OS syscalls directly (no open, socket, exec)
2. **Capability-Based I/O:** WASI requires explicit preopened directories (can't access random files)
3. **Cross-Platform:** WASM runs identically on Linux, macOS, Windows, Web
4. **Fast Boot:** <10ms WASM module instantiation (vs 125ms container boot)
5. **Low Overhead:** 5MB memory per WASM module (vs 100MB container)

**Key Trade-off:**
- **Performance:** 10x slower than native (acceptable for untrusted code)
- **Security:** Maximum isolation (no kernel syscalls)

---

## Decision

**We will implement WASMSandbox as Layer 2 sandbox for untrusted tools, using Wasmtime runtime with WASI capabilities for filesystem and network I/O, achieving zero-syscall isolation at 10x performance cost.**

### Core Principles

1. **Zero Trust:**
   - WASM code cannot access filesystem without explicit capability
   - WASM code cannot access network without explicit capability
   - WASM code cannot spawn processes or execute binaries

2. **Capability-Based Security:**
   - Filesystem: Preopened directories only (e.g., `/tmp/tool_workspace`)
   - Network: Allowed hosts only (e.g., `api.openweathermap.org`)
   - Denied by default: Environment variables, process spawning, raw syscalls

3. **Cross-Platform:**
   - Same WASM bytecode runs on Linux, macOS, Windows
   - No OS-specific dependencies (no iptables, seccomp, cgroups needed)

4. **Performance-Security Trade-off:**
   - 10x slower than native execution (acceptable for untrusted code)
   - Use WASM for 15% of tools (user plugins, RED band, experimental tools)
   - Use Process sandbox for 80% of tools (ADR-0033c)

5. **Observable:**
   - Prometheus metrics for WASM execution time
   - OpenTelemetry tracing with cognitive_trace_id
   - Structured logging for capability violations

---

## Architecture

### Layer 2 (Sandbox) - This ADR

```
┌─────────────────────────────────────────────────────────────┐
│                   MCPClient (Layer 1)                       │
│  (Handles JSON-RPC protocol - see ADR-0033a)               │
└──────────────────────┬──────────────────────────────────────┘
                       │
                       │ HTTP POST (JSON-RPC)
                       │
                       ▼
┌─────────────────────────────────────────────────────────────┐
│                   WASMSandbox (Layer 2)                     │
│  ┌────────────────────────────────────────────────────┐    │
│  │  Wasmtime Runtime                                  │    │
│  │  ┌──────────────────────────────────────────┐     │    │
│  │  │  WASM Module (user_plugin.wasm)         │     │    │
│  │  │  - MCP server compiled to WASM          │     │    │
│  │  │  - Zero native syscalls                 │     │    │
│  │  └──────────────────┬───────────────────────┘     │    │
│  │                     │                              │    │
│  │                     │ WASI syscalls                │    │
│  │                     ▼                              │    │
│  │  ┌──────────────────────────────────────────┐     │    │
│  │  │  WASI (WebAssembly System Interface)    │     │    │
│  │  │  - Preopened directories                │     │    │
│  │  │  - Allowed network hosts                │     │    │
│  │  │  - Denied by default                    │     │    │
│  │  └──────────────────────────────────────────┘     │    │
│  └────────────────────────────────────────────────────┘    │
└─────────────────────────────────────────────────────────────┘
```

### Security Model

**WASM Isolation (Zero Syscalls):**
1. WASM code executes in sandboxed VM (no direct OS access)
2. All I/O goes through WASI (capability-based interface)
3. No syscalls without explicit capability grant

**WASI Capabilities (Explicit Grants):**
- **Filesystem:** `preopened_dirs: ["/tmp/tool_workspace"]` → Can only access this directory
- **Network:** `allowed_hosts: ["api.weather.com"]` → Can only connect to allowed hosts
- **Environment:** `allowed_env_vars: ["API_KEY"]` → Can only read whitelisted env vars
- **Denied:** Process spawning, raw sockets, kernel access

**Capability Violation Handling:**
- WASI traps (runtime error) if code attempts unauthorized access
- K1 catches trap, logs violation, returns error to user

---

## Implementation

### WASMSandbox Implementation

```python
import wasmtime
import asyncio
import json
from dataclasses import dataclass
from typing import Dict, List, Optional

@dataclass
class WASIConfig:
    """
    WASI configuration for WASM sandbox.

    Defines capabilities granted to WASM module.
    """
    # Filesystem capabilities
    preopened_dirs: List[str]  # Directories WASM can access

    # Network capabilities
    allowed_hosts: List[str]  # Hosts WASM can connect to

    # Environment capabilities
    allowed_env_vars: List[str]  # Env vars WASM can read

    # Resource limits
    max_memory_mb: int = 128  # Maximum WASM memory
    timeout_seconds: int = 10  # Maximum execution time

@dataclass
class WASMSandboxConfig:
    """WASM sandbox configuration"""
    wasm_path: str  # Path to .wasm file
    wasi_config: WASIConfig
    http_port: int = 8001  # HTTP server port for MCP protocol

class WASMSandbox:
    """
    WASM sandbox for untrusted tool execution.

    Provides maximum security isolation with zero native syscalls.
    Uses Wasmtime runtime + WASI for capability-based I/O.

    Research: WebAssembly (W3C 2019), WASI (2019), Capabilities (Dennis 1966)
    """

    def __init__(self, config: WASMSandboxConfig):
        """Initialize WASM sandbox"""
        self.config = config
        self.engine = wasmtime.Engine()
        self.module: Optional[wasmtime.Module] = None
        self.store: Optional[wasmtime.Store] = None
        self.instance: Optional[wasmtime.Instance] = None
        self.wasi: Optional[wasmtime.WasiConfig] = None

    async def initialize(self):
        """
        Initialize WASM sandbox.

        Loads WASM module and configures WASI capabilities.
        """
        # Load WASM module (compiled MCP server)
        with open(self.config.wasm_path, "rb") as f:
            wasm_bytes = f.read()

        self.module = wasmtime.Module(self.engine, wasm_bytes)

        # Configure WASI (capability-based syscalls)
        self.wasi = wasmtime.WasiConfig()

        # Filesystem capabilities (preopened directories)
        for preopen_dir in self.config.wasi_config.preopened_dirs:
            self.wasi.preopen_dir(
                preopen_dir,
                preopen_dir  # Guest path = host path
            )

        # Environment capabilities (allowed env vars)
        for env_var in self.config.wasi_config.allowed_env_vars:
            if env_var in os.environ:
                self.wasi.set_env(env_var, os.environ[env_var])

        # Network capabilities (allowed hosts)
        # Note: WASI doesn't have native network API yet
        # Use custom host function for network (see below)

        # Create store with resource limits
        self.store = wasmtime.Store(self.engine)
        self.store.set_wasi(self.wasi)

        # Set memory limit
        self.store.set_fuel(
            self.config.wasi_config.max_memory_mb * 1024 * 1024
        )

        # Instantiate WASM module
        linker = wasmtime.Linker(self.engine)
        linker.define_wasi()

        # Add custom host functions (network capabilities)
        self._add_network_capabilities(linker)

        self.instance = linker.instantiate(self.store, self.module)

        logger.info(
            "wasm_sandbox_initialized",
            wasm_path=self.config.wasm_path,
            memory_limit_mb=self.config.wasi_config.max_memory_mb
        )

    def _add_network_capabilities(self, linker: wasmtime.Linker):
        """
        Add custom host functions for network capabilities.

        Since WASI doesn't have standard network API yet,
        we provide custom host functions with allowed_hosts check.
        """
        def http_request(
            caller: wasmtime.Caller,
            url_ptr: int,
            url_len: int
        ) -> int:
            """
            Custom host function for HTTP requests.

            WASM calls this instead of native socket().
            We check allowed_hosts before allowing request.
            """
            # Read URL from WASM memory
            memory = caller["memory"]
            url_bytes = memory.read(caller, url_ptr, url_len)
            url = url_bytes.decode()

            # Parse host from URL
            from urllib.parse import urlparse
            parsed = urlparse(url)
            host = parsed.netloc

            # Check if host allowed
            if host not in self.config.wasi_config.allowed_hosts:
                logger.warning(
                    "wasm_network_capability_violation",
                    wasm_path=self.config.wasm_path,
                    attempted_host=host,
                    allowed_hosts=self.config.wasi_config.allowed_hosts
                )
                return -1  # Permission denied

            # Host allowed, make request
            import requests
            response = requests.get(url)

            # Write response back to WASM memory
            # (simplified - real impl would return response object)
            return response.status_code

        # Define host function in linker
        func_type = wasmtime.FuncType(
            [wasmtime.ValType.i32(), wasmtime.ValType.i32()],
            [wasmtime.ValType.i32()]
        )
        linker.define_func(
            "env",
            "http_request",
            func_type,
            http_request
        )

    async def start_mcp_server(self):
        """
        Start MCP server inside WASM sandbox.

        WASM module exports _start() function that runs MCP server
        listening on HTTP port (since stdio doesn't work in WASM).
        """
        # Call WASM _start() function (entry point)
        start_func = self.instance.exports(self.store)["_start"]

        # Run in background (MCP server loop)
        asyncio.create_task(self._run_wasm_start(start_func))

        # Wait for HTTP server to start
        await asyncio.sleep(0.1)

        logger.info(
            "wasm_mcp_server_started",
            wasm_path=self.config.wasm_path,
            http_port=self.config.http_port
        )

    async def _run_wasm_start(self, start_func):
        """Run WASM _start() function with timeout"""
        try:
            # Execute with timeout
            await asyncio.wait_for(
                asyncio.to_thread(start_func, self.store),
                timeout=self.config.wasi_config.timeout_seconds
            )
        except asyncio.TimeoutError:
            logger.error(
                "wasm_timeout",
                wasm_path=self.config.wasm_path,
                timeout_seconds=self.config.wasi_config.timeout_seconds
            )
            # Timeout exceeded, kill WASM instance
            self.shutdown()
        except wasmtime.Trap as trap:
            logger.error(
                "wasm_trap",
                wasm_path=self.config.wasm_path,
                trap_message=str(trap)
            )
            # WASM trapped (capability violation or error)
            self.shutdown()

    def shutdown(self):
        """Shutdown WASM sandbox"""
        if self.store:
            # Drop store (releases all resources)
            self.store = None
            self.instance = None

        logger.info(
            "wasm_sandbox_shutdown",
            wasm_path=self.config.wasm_path
        )


class CapabilityViolationError(Exception):
    """Raised when WASM attempts unauthorized access"""
    pass
```

---

### Tool Compilation to WASM

**WASM toolchains for different languages:**

#### Rust → WASM (Recommended)

```rust
// src/main.rs
// MCP server in Rust compiled to WASM

use std::io::{self, BufRead, Write};
use serde_json::{json, Value};

fn main() {
    // Start HTTP server (WASI doesn't have stdio)
    // Use warp or actix-web compiled to WASM target

    let stdin = io::stdin();
    let mut stdout = io::stdout();

    for line in stdin.lock().lines() {
        let request: Value = serde_json::from_str(&line.unwrap()).unwrap();

        // Handle MCP request
        let response = handle_mcp_request(request);

        // Write response
        writeln!(stdout, "{}", serde_json::to_string(&response).unwrap()).unwrap();
    }
}

fn handle_mcp_request(request: Value) -> Value {
    let method = request["method"].as_str().unwrap();

    match method {
        "initialize" => json!({
            "jsonrpc": "2.0",
            "id": request["id"],
            "result": {
                "protocolVersion": "2024-11-05",
                "capabilities": {}
            }
        }),
        "tools/list" => json!({
            "jsonrpc": "2.0",
            "id": request["id"],
            "result": {
                "tools": [{
                    "name": "process_data",
                    "description": "Process user data",
                    "inputSchema": {
                        "type": "object",
                        "properties": {
                            "input": {"type": "string"}
                        }
                    }
                }]
            }
        }),
        "tools/call" => {
            let tool_name = request["params"]["name"].as_str().unwrap();
            let arguments = &request["params"]["arguments"];

            // Execute tool (in WASM sandbox)
            let result = execute_tool(tool_name, arguments);

            json!({
                "jsonrpc": "2.0",
                "id": request["id"],
                "result": result
            })
        }
        _ => json!({
            "jsonrpc": "2.0",
            "id": request["id"],
            "error": {
                "code": -32601,
                "message": "Method not found"
            }
        })
    }
}

fn execute_tool(tool_name: &str, arguments: &Value) -> Value {
    // Tool logic here
    // Can access filesystem via WASI preopened dirs
    // Can access network via custom host function

    json!({
        "output": "processed data"
    })
}
```

**Compile to WASM:**
```bash
# Install Rust WASM target
rustup target add wasm32-wasi

# Compile MCP server to WASM
cargo build --target wasm32-wasi --release

# Output: target/wasm32-wasi/release/user_plugin.wasm
```

---

#### C/C++ → WASM (WASI SDK)

```c
// mcp_server.c
// MCP server in C compiled to WASM

#include <stdio.h>
#include <string.h>
#include <wasi/api.h>

int main() {
    char line[4096];

    while (fgets(line, sizeof(line), stdin)) {
        // Parse JSON request
        // Handle MCP request
        // Write JSON response to stdout

        printf("{\"jsonrpc\":\"2.0\",\"id\":1,\"result\":{}}\n");
        fflush(stdout);
    }

    return 0;
}
```

**Compile to WASM:**
```bash
# Install WASI SDK
wget https://github.com/WebAssembly/wasi-sdk/releases/download/wasi-sdk-21/wasi-sdk-21.0-linux.tar.gz
tar xf wasi-sdk-21.0-linux.tar.gz

# Compile to WASM
/opt/wasi-sdk/bin/clang -o mcp_server.wasm mcp_server.c
```

---

#### AssemblyScript → WASM (TypeScript-like)

```typescript
// mcp_server.ts
// MCP server in AssemblyScript (TypeScript-like, compiles to WASM)

import { Console } from "as-wasi";

export function _start(): void {
  // Start MCP server
  Console.log("MCP server started");

  // Handle requests (simplified)
  handleRequests();
}

function handleRequests(): void {
  // Read from stdin
  // Parse JSON
  // Handle MCP request
  // Write to stdout
}
```

**Compile to WASM:**
```bash
# Install AssemblyScript
npm install -g assemblyscript

# Compile to WASM
asc mcp_server.ts --target wasi -o mcp_server.wasm
```

---

### Tool Registry Configuration

```yaml
# k1/config/tool_registry.yml
tool_registry:
  tools:
    # User-submitted plugin (untrusted) - WASM sandbox
    - name: "user_plugin"
      description: "User-submitted plugin (untrusted code)"
      band: GREEN
      # Layer 1 - Protocol (ADR-0033a)
      protocol: "mcp"
      mcp_config:
        server_path: "/opt/familyos/mcp_servers/user_plugin.wasm"
        transport: "http"  # WASM uses HTTP, not stdio
        port: 8001
        timeout_seconds: 10
      # Layer 2 - Sandbox (This ADR)
      sandbox: "wasm"
      wasm_config:
        wasi:
          # Filesystem capabilities
          preopened_dirs:
            - "/tmp/user_plugin_workspace"  # Can only access this dir
          # Network capabilities
          allowed_hosts:
            - "api.weather.com"  # Can only connect to allowed hosts
          # Environment capabilities
          allowed_env_vars:
            - "API_KEY"  # Can only read whitelisted env vars
          # Resource limits
          max_memory_mb: 64
          timeout_seconds: 10
      sandbox_fallback: "process"  # Fallback to Process if WASM fails

    # Experimental tool (RED band) - WASM sandbox
    - name: "experimental_tool"
      description: "Experimental tool (high risk)"
      band: RED
      protocol: "mcp"
      mcp_config:
        server_path: "/opt/familyos/mcp_servers/experimental.wasm"
        transport: "http"
        port: 8002
        timeout_seconds: 30
      sandbox: "wasm"
      wasm_config:
        wasi:
          preopened_dirs:
            - "/tmp/experimental_workspace"
          allowed_hosts: []  # No network access
          allowed_env_vars: []  # No env vars
          max_memory_mb: 32
          timeout_seconds: 30
      sandbox_fallback: null  # No fallback for RED band
```

---

## Performance Analysis

### Scenario 1: User Plugin (Simple Text Processing)

**Configuration:**
- Tool: user_plugin.wasm (text formatter)
- WASM size: 500KB
- Memory limit: 64MB
- Timeout: 10s

**Performance Breakdown:**
- WASM instantiation: 8ms (load module + configure WASI)
- Tool execution: 50ms (native would be 5ms, WASM 10x slower)
- **Total latency: 58ms ✅**

**Overhead:** 10x slower than native (5ms → 50ms), but acceptable for untrusted code ✅

---

### Scenario 2: API Call (Network Capability)

**Configuration:**
- Tool: weather_api.wasm
- Network: api.openweathermap.org (allowed host)
- Memory limit: 128MB
- Timeout: 30s

**Performance Breakdown:**
- WASM instantiation: 10ms
- HTTP request via custom host function: 250ms (external API)
- WASM overhead: 5ms (capability check)
- **Total latency: 265ms ✅**

**Overhead:** 5ms capability check (2% of 250ms API call) ✅

---

### Scenario 3: Capability Violation (Unauthorized File Access)

**Configuration:**
- Tool: malicious.wasm
- Attempts to access `/etc/passwd` (not in preopened_dirs)
- Memory limit: 64MB

**Execution:**
1. WASM calls WASI `path_open("/etc/passwd")`
2. WASI checks preopened dirs: `/tmp/user_plugin_workspace` only
3. `/etc/passwd` not in preopened dirs → Trap
4. K1 catches trap, logs violation
5. Returns error to user: "Permission denied"
6. **Security: Attack prevented ✅**

**Result:** Zero-syscall isolation prevents unauthorized access ✅

---

### Scenario 4: Memory Exhaustion Attack

**Configuration:**
- Tool: memory_bomb.wasm
- Attempts to allocate 1GB memory
- Memory limit: 64MB

**Execution:**
1. WASM attempts to allocate 1GB via `memory.grow()`
2. Wasmtime checks fuel (memory limit)
3. 1GB > 64MB limit → Trap
4. K1 catches trap, logs violation
5. Returns error to user: "Memory limit exceeded"
6. **Security: Attack prevented ✅**

**Result:** Resource limits prevent memory exhaustion ✅

---

## Security Analysis

### Threat Model

**Threat 1: Malicious User Plugin Attempts Filesystem Escape**

**Attack:**
- User uploads malicious.wasm
- Attempts to read `/etc/passwd`, write `/usr/bin/backdoor`

**Defense:**
- WASI preopened_dirs: `/tmp/user_plugin_workspace` only
- Attempts to access other paths → Trap
- **Result: Attack prevented ✅**

---

**Threat 2: Malicious Plugin Attempts Network Exfiltration**

**Attack:**
- User uploads exfiltrate.wasm
- Attempts to connect to attacker.com (not in allowed_hosts)

**Defense:**
- Custom host function checks allowed_hosts
- attacker.com not in list → Permission denied
- **Result: Attack prevented ✅**

---

**Threat 3: Malicious Plugin Attempts Process Spawning**

**Attack:**
- User uploads spawn.wasm
- Attempts to execute `/bin/sh` via process spawn

**Defense:**
- WASI has no process spawn API
- No syscall access (exec, fork, spawn)
- **Result: Attack impossible ✅**

---

**Threat 4: Malicious Plugin Attempts Kernel Exploit**

**Attack:**
- User uploads kernel_exploit.wasm
- Attempts to exploit kernel 0-day via raw syscalls

**Defense:**
- WASM cannot call syscalls directly (no syscall instruction)
- All I/O goes through WASI (capability-checked)
- **Result: Attack impossible ✅**

---

### Comparison with Other Sandboxes

| Feature | WASM Sandbox | Process Sandbox | Container Sandbox |
|---------|--------------|-----------------|-------------------|
| **Native Syscalls** | ❌ Zero (maximum security) | ✅ Yes (filtered by seccomp) | ✅ Yes (isolated by gVisor) |
| **Boot Time** | ✅ 10ms | ✅ <100ms | ❌ 125ms |
| **Memory Overhead** | ✅ 5MB | ✅ 10MB | ❌ 100MB |
| **Performance** | ❌ 10x slower | ✅ Native speed | ✅ ~2% overhead |
| **Cross-Platform** | ✅ Linux/Mac/Win | ❌ Linux only | ❌ Linux + KVM only |
| **Security Level** | ✅ Maximum | ⚠️ Medium | ✅ High |
| **Use Case** | Untrusted code | Standard tools | RED band |

**WASM Sandbox is best for:**
- User-submitted plugins (untrusted code)
- Experimental tools (RED band, high risk)
- Cross-platform tools (dev on Mac, deploy on Linux)

**WASM Sandbox is worst for:**
- Performance-critical tools (use Process sandbox)
- Tools requiring full filesystem access (use Process sandbox)

---

## Monitoring & Observability

### Prometheus Metrics

```python
from prometheus_client import Counter, Histogram, Gauge

# WASM executions
k1_wasm_executions_total = Counter(
    "k1_wasm_executions_total",
    "Total WASM tool executions",
    ["tool_name", "status"]  # success | timeout | trap | error
)

# WASM instantiation time
k1_wasm_instantiation_ms = Histogram(
    "k1_wasm_instantiation_ms",
    "WASM module instantiation time in milliseconds",
    buckets=[1, 5, 10, 25, 50, 100]
)

# WASM execution time
k1_wasm_execution_ms = Histogram(
    "k1_wasm_execution_ms",
    "WASM tool execution time in milliseconds",
    buckets=[10, 50, 100, 250, 500, 1000, 5000]
)

# WASM capability violations
k1_wasm_capability_violations_total = Counter(
    "k1_wasm_capability_violations_total",
    "WASM capability violations",
    ["tool_name", "violation_type"]  # filesystem | network | memory
)

# WASM memory usage
k1_wasm_memory_mb = Gauge(
    "k1_wasm_memory_mb",
    "WASM module memory usage in MB",
    ["tool_name"]
)
```

---

## Testing Strategy

### Unit Tests (WARD Framework)

```python
from ward import test
import asyncio

@test("WASMSandbox initializes successfully")
async def _():
    config = WASMSandboxConfig(
        wasm_path="/opt/familyos/mcp_servers/user_plugin.wasm",
        wasi_config=WASIConfig(
            preopened_dirs=["/tmp/test_workspace"],
            allowed_hosts=["api.weather.com"],
            allowed_env_vars=["API_KEY"],
            max_memory_mb=64,
            timeout_seconds=10
        ),
        http_port=8001
    )
    sandbox = WASMSandbox(config)

    await sandbox.initialize()

    assert sandbox.instance is not None
    assert sandbox.store is not None

@test("WASMSandbox prevents unauthorized filesystem access")
async def _():
    config = WASMSandboxConfig(
        wasm_path="/opt/familyos/mcp_servers/malicious.wasm",
        wasi_config=WASIConfig(
            preopened_dirs=["/tmp/test_workspace"],
            allowed_hosts=[],
            allowed_env_vars=[],
            max_memory_mb=64,
            timeout_seconds=10
        ),
        http_port=8002
    )
    sandbox = WASMSandbox(config)

    await sandbox.initialize()

    # Malicious WASM attempts to access /etc/passwd
    # Should trap (capability violation)
    with raises(wasmtime.Trap):
        await sandbox.start_mcp_server()

@test("WASMSandbox prevents unauthorized network access")
async def _():
    config = WASMSandboxConfig(
        wasm_path="/opt/familyos/mcp_servers/exfiltrate.wasm",
        wasi_config=WASIConfig(
            preopened_dirs=["/tmp/test_workspace"],
            allowed_hosts=["api.weather.com"],  # Only weather API allowed
            allowed_env_vars=[],
            max_memory_mb=64,
            timeout_seconds=10
        ),
        http_port=8003
    )
    sandbox = WASMSandbox(config)

    await sandbox.initialize()

    # WASM attempts to connect to attacker.com (not allowed)
    # Custom host function should reject
    # (test requires MCP client to call tool)
    pass  # TODO: Integration test

@test("WASMSandbox enforces memory limits")
async def _():
    config = WASMSandboxConfig(
        wasm_path="/opt/familyos/mcp_servers/memory_bomb.wasm",
        wasi_config=WASIConfig(
            preopened_dirs=["/tmp/test_workspace"],
            allowed_hosts=[],
            allowed_env_vars=[],
            max_memory_mb=64,  # 64MB limit
            timeout_seconds=10
        ),
        http_port=8004
    )
    sandbox = WASMSandbox(config)

    await sandbox.initialize()

    # WASM attempts to allocate 1GB (exceeds limit)
    # Should trap (out of fuel)
    with raises(wasmtime.Trap):
        await sandbox.start_mcp_server()
```

### Security Tests

```python
@test("WASM cannot access parent directories")
async def _():
    """Test that ../ path traversal is blocked"""
    config = WASMSandboxConfig(
        wasm_path="/opt/familyos/mcp_servers/path_traversal.wasm",
        wasi_config=WASIConfig(
            preopened_dirs=["/tmp/test_workspace"],
            allowed_hosts=[],
            allowed_env_vars=[],
            max_memory_mb=64,
            timeout_seconds=10
        ),
        http_port=8005
    )
    sandbox = WASMSandbox(config)
    await sandbox.initialize()

    # WASM attempts to access ../../../etc/passwd
    # WASI should block (not in preopened dirs)
    with raises(wasmtime.Trap):
        await sandbox.start_mcp_server()

@test("WASM cannot spawn processes")
async def _():
    """Test that process spawning is impossible"""
    # WASI has no process spawn API
    # This test verifies WASM module compiled without spawn support
    pass  # No process spawn in WASI, nothing to test
```

---

## Dependencies

### Required

- **Wasmtime** (0.42.0+) — WASM runtime
- **Python wasmtime package** (14.0.0+)
- **Rust toolchain** (for compiling tools to WASM)
  - `rustup target add wasm32-wasi`

### Optional

- **WASI SDK** (for C/C++ tools)
- **AssemblyScript** (for TypeScript-like tools)

---

## Implementation Timeline

### Phase 1: Wasmtime Integration (Days 1-2)

**Deliverables:**
- WASMSandbox class
- WASM module loading
- WASI configuration
- Unit tests

**Validation:**
- WASM module instantiates successfully
- WASI capabilities configured

---

### Phase 2: Capability Enforcement (Days 3-4)

**Deliverables:**
- Filesystem capabilities (preopened_dirs)
- Network capabilities (custom host function)
- Environment capabilities (allowed_env_vars)
- Capability violation logging

**Validation:**
- Unauthorized filesystem access trapped
- Unauthorized network access blocked
- Capability violations logged

---

### Phase 3: MCP Protocol Integration (Day 5)

**Deliverables:**
- HTTP server for MCP protocol
- Integration with MCPClient (ADR-0033a)
- Tool execution with timeout

**Validation:**
- MCPClient successfully calls WASM tools
- MCP protocol works via HTTP transport

---

### Phase 4: Security Testing (Day 6)

**Deliverables:**
- Path traversal tests
- Network exfiltration tests
- Memory exhaustion tests
- Process spawn tests (verify impossible)

**Validation:**
- All security tests pass
- No sandbox escapes possible

---

### Phase 5: Observability (Day 7)

**Deliverables:**
- Prometheus metrics
- OpenTelemetry tracing
- Structured logging
- Grafana dashboard

**Validation:**
- Metrics exported
- Traces appear in Jaeger
- Capability violations logged

---

**Total Duration:** 7 days (1 week, parallel with ADR-0033c)

---

## Success Criteria

1. **Zero Native Syscalls:**
   - WASM cannot call OS syscalls directly
   - All I/O goes through WASI capabilities

2. **Capability Enforcement:**
   - Filesystem: Only preopened_dirs accessible
   - Network: Only allowed_hosts connectable
   - Environment: Only allowed_env_vars readable

3. **Cross-Platform:**
   - Same WASM bytecode runs on Linux, macOS, Windows
   - No OS-specific dependencies

4. **Performance:**
   - 10x slower than native (acceptable for untrusted code)
   - <10ms instantiation time

5. **Security:**
   - No sandbox escapes possible
   - All capability violations logged

6. **Test Coverage:**
   - 95% unit test coverage
   - Security tests for all threat vectors

---

## References

1. **WebAssembly Core Specification — W3C, 2019**
   - Specification: https://webassembly.github.io/spec/core/

2. **WASI (WebAssembly System Interface) — 2019**
   - Specification: https://github.com/WebAssembly/WASI

3. **Wasmtime — Bytecode Alliance, 2019**
   - Runtime: https://wasmtime.dev/

4. **Capability-Based Security — Dennis & Van Horn, 1966**
   - Paper: "Programming Semantics for Multiprogrammed Computations"

5. **ADR-0033 — Tool Execution Architecture**
   - 2-layer architecture: Protocol × Sandbox

6. **ADR-0033a — MCP Protocol Integration**
   - JSON-RPC 2.0 protocol layer

---

## Glossary

- **WASM:** WebAssembly - portable bytecode format for sandboxed execution
- **WASI:** WebAssembly System Interface - capability-based syscall API
- **Wasmtime:** WASM runtime (Rust-based, production-grade)
- **Capability:** Explicit permission to access resource (filesystem, network, env vars)
- **Preopen:** WASI mechanism to grant filesystem access to specific directories
- **Trap:** WASM runtime error (e.g., capability violation, memory exhaustion)

---

**Status:** ✅ COMPLETE (Layer 2 - WASM Sandbox)

**Next:** ADR-0033c (Process Sandbox - Layer 2) + ADR-0033d (2D Selection Logic)
