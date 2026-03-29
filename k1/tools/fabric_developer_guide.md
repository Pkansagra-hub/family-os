# Capability Fabric Developer Guide — Building MCP Servers, WASM Tools, and More

> **Audience**: Any developer building tools for the Capability Fabric
> **Prerequisites**: Python 3.13, familiarity with YAML, basic understanding of MCP protocol
> **Last Updated**: 2025-01-XX

---

## Table of Contents

1. [Architecture Overview](#1-architecture-overview)
2. [The Execute Pipeline (9 Steps)](#2-the-execute-pipeline)
3. [Writing a Tool Contract (YAML)](#3-writing-a-tool-contract)
4. [Building an MCP Server (Local — stdio)](#4-building-an-mcp-server-local)
5. [Building an MCP Server (Remote — SSE)](#5-building-an-mcp-server-remote)
6. [Building a WASM Tool](#6-building-a-wasm-tool)
7. [Provider Configuration and Registration](#7-provider-configuration)
8. [How Fabric Discovers Your Tool](#8-how-fabric-discovers-your-tool)
9. [Testing Your Tool](#9-testing-your-tool)
10. [Safety Bands and Policy](#10-safety-bands-and-policy)
11. [Error Handling and Circuit Breakers](#11-error-handling)
12. [Naming Conventions](#12-naming-conventions)
13. [Quick Start Checklist](#13-quick-start-checklist)
14. [Reference: Existing Contracts](#14-reference)

---

## 1. Architecture Overview

The Capability Fabric is the central execution engine for all tool invocations in K1.
It is **stateless per-call**, **policy-driven**, and **provider-agnostic**.

### What the Fabric Does

```
Caller (Orchestrator/Concierge/Agent)
    |
    v
CapabilityRequest  (frozen immutable envelope)
    |
    v
+-------------------------------------------+
|          Capability Fabric                 |
|                                           |
|  1. Event: invoked                        |
|  2. Resolve: Registry -> Policy -> Select |
|  3. Context: SessionState + Prompts       |
|  4. Instantiate: ProviderFactory          |
|  5. Execute: CircuitBreaker(Provider)     |
|  6. Validate: Structural -> Schema -> Sem |
|  7. Event: completed / failed             |
|  8. Metrics: update registry              |
|  9. Event: learning signal                |
+-------------------------------------------+
    |
    v
CapabilityResult  (success with data, or failure with error)
```

### Provider Types

| Type | Description | Transport | Runs Where |
|------|-------------|-----------|------------|
| **MCP** | Model Context Protocol servers | stdio (local) or SSE/HTTP (remote) | Edge device or cloud |
| **WASM** | Sandboxed WebAssembly modules | In-process | Edge device only |
| **Bridge** | Cross-kernel proxy to K0 | K0 Bridge protocol | Cross-device |
| **Agent** | LLM-based sub-agents | Internal | Edge device |
| **Workflow** | Multi-step orchestrated flows | Internal | Edge device |
| **Concierge** | Direct dispatch tier | Internal | Edge device |

**As a tool developer, you will typically build MCP servers or WASM modules.**

### Key Components You Interact With

| Component | What It Does | Your Concern |
|-----------|-------------|--------------|
| **ModuleLoader** | Scans `k1/contracts/` for YAML files on startup | Drop your YAML here |
| **ContractValidator** | Validates your YAML before registration | Your YAML must pass validation |
| **CapabilityRegistry** | Stores registered contracts | Your contract registers automatically |
| **ProviderFactory** | Creates provider instances from ProviderConfig | Configure your provider correctly |
| **MCPProvider** | Executes MCP calls via transport | Implement the MCP server |
| **WASMProvider** | Executes WASM in sandbox | Compile your .wasm module |
| **CircuitBreaker** | Wraps execution with failure detection | Handle errors gracefully |
| **OutputValidationPipeline** | Validates your output against contract schema | Return the right shape |

---

## 2. The Execute Pipeline

When someone calls `fabric.execute(request)`, these 9 steps happen:

### Step 1: Emit Invoked Event
Fabric emits `k1.capability.invoked.v1` with the request ID, capability name, caller, and trace ID.

### Step 2: Resolve Provider
The Resolver pipeline runs:
1. **CapabilityRegistry** — Looks up the contract by `capability_name`
2. **ProviderMatcher** — Finds providers that can handle this capability
3. **PolicyEngine** — Applies safety band, affective routing, cognitive load, QoS
4. **ProviderSelector** — Picks the best provider (by score, latency, availability)

### Step 3: Build Context
ContextBuilder assembles: SessionState snapshot + prompt templates + token budget.

### Step 4: Instantiate Provider
ProviderFactory creates the correct provider (MCP, WASM, etc.) with injected port dependencies.

### Step 5: Execute via CircuitBreaker
The provider's `execute()` is called inside a CircuitBreaker wrapper:
- **Local MCP (stdio)**: 10s timeout, 3 failures trip
- **Remote MCP (SSE/HTTP)**: 15s timeout, 3 failures trip
- **WASM**: Sandbox timeout from config (default 5s)

### Step 6: Validate Output
Three-tier validation on the result:
1. **Structural** — Is it a valid CapabilityResult?
2. **Schema** — Does `result.data` match the contract's `output` JSON Schema?
3. **Semantic** — Domain-specific validation (if defined)

### Step 7-9: Post-Execution
- Emit `k1.capability.completed.v1` or `k1.capability.failed.v1`
- Update registry metrics (latency, success rate)
- Emit `k1.fabric.learning.signal.v1` for the learning loop

---

## 3. Writing a Tool Contract (YAML)

Every tool MUST have a contract YAML file. This is what makes it discoverable and executable.

### File Location

Place your contract in:
```
k1/contracts/tools/<your_tool_name>.yaml
```

The ModuleLoader scans `k1/contracts/tools/`, `k1/contracts/agents/`, `k1/contracts/prompts/`, and `k1/contracts/workflows/` recursively for `.yaml` and `.yml` files.

### Contract Structure (Annotated)

```yaml
# k1/contracts/tools/weather_current.yaml
# Comments explaining purpose and references

tool_contract:                              # Root key (REQUIRED) — must be exactly "tool_contract"
  name: "tool.read.weather.current"         # Capability name (see naming conventions below)
  version: "1.0.0"                          # Semantic version
  domain:                                   # Domain tags for discovery/filtering
    - "WEATHER"
    - "FAMILY"
  description: >                            # Human-readable purpose
    Get current weather conditions for a given location.
    Returns temperature, conditions, humidity, and wind speed.
  capabilities:                             # What this tool can do (for discovery)
    - "weather_lookup"
    - "location_query"
  limitations:                              # What this tool cannot do
    - "read_only"
    - "no_historical_data"
    - "single_location_per_call"

  required_inputs:                          # Parameters the caller MUST provide
    - name: "location"                      # Parameter name (used in request.params)
      type: "STRING"                        # Type: STRING, NUMBER, BOOLEAN, ARRAY[STRING], OBJECT
      description: "City name or lat,lon"   # Human-readable description

  optional_inputs:                          # Parameters with defaults
    - name: "units"
      type: "STRING"
      description: "Temperature units: metric, imperial, kelvin"
      default: "metric"                     # Default value if not provided

  output:                                   # JSON Schema for the result data
    type: "object"
    properties:
      temperature:
        type: "number"
        description: "Temperature in requested units"
      conditions:
        type: "string"
        description: "Weather conditions description"
      humidity:
        type: "number"
        description: "Humidity percentage (0-100)"
      wind_speed:
        type: "number"
        description: "Wind speed in m/s or mph"
      location:
        type: "string"
        description: "Resolved location name"
    required:
      - "temperature"
      - "conditions"
      - "location"

  # --- Provider binding ---
  provider_type: "MCP"                      # MCP, WASM, BRIDGE, AGENT, WORKFLOW, CONCIERGE
  provider_id: "weather_mcp"                # Unique ID matching your provider registration
  safety_band_min: "GREEN"                  # Minimum safety band: GREEN, AMBER, RED, CRISIS
  cost_per_call: 0.001                      # Estimated cost (for budgeting)
  avg_latency_ms: 500                       # Expected average latency
  max_latency_ms: 2000                      # Maximum acceptable latency
  availability: "ONLINE"                    # ONLINE, DEGRADED, OFFLINE
  tags:                                     # Searchable tags
    - "weather"
    - "read_only"
    - "external_api"
```

### Input Types

| Type | Description | Example |
|------|-------------|---------|
| `STRING` | Text value | `"San Francisco"` |
| `NUMBER` | Integer or float | `42`, `3.14` |
| `BOOLEAN` | True/false | `true` |
| `ARRAY[STRING]` | List of strings | `["tag1", "tag2"]` |
| `ARRAY[NUMBER]` | List of numbers | `[1, 2, 3]` |
| `OBJECT` | Nested object (JSON) | `{"key": "value"}` |

### Output Schema

The `output` section uses standard JSON Schema. Your tool's `result.data` MUST conform to this schema. The OutputValidationPipeline checks this automatically.

---

## 4. Building an MCP Server (Local — stdio)

Local MCP servers run as a subprocess on the same device. Fabric spawns them and communicates via stdin/stdout using JSON-RPC.

### Architecture

```
FabricFactory
    |
    +--> MCPProvider (config.transport = "STDIO")
             |
             +--> IMCPTransport (stdio implementation)
                      |
                      +--> subprocess: python -m k1.tools.mcp_servers.calendar.server
                               |
                               stdin/stdout (JSON-RPC)
```

### Step-by-Step

#### 1. Create the Directory

```
k1/tools/mcp_servers/your_tool/
    __init__.py
    server.py          # Entry point — MCP runtime
    handlers.py        # Tool handler functions
    storage.py         # Persistence (SQLite, files, etc.)
    models.py          # Data models (frozen dataclasses)
```

#### 2. Define Data Models (`models.py`)

```python
"""Data models for calendar tool."""
from __future__ import annotations
from dataclasses import dataclass, field
from typing import Optional

@dataclass(frozen=True)
class CalendarEvent:
    """A single calendar event."""
    event_id: str = ""
    title: str = ""
    start_time: str = ""           # ISO 8601
    end_time: str = ""             # ISO 8601
    location: Optional[str] = None
    description: Optional[str] = None
    attendees: tuple[str, ...] = field(default_factory=tuple)
```

#### 3. Implement Handlers (`handlers.py`)

Each handler receives a dict of arguments and returns a dict of results:

```python
"""Tool handlers for calendar MCP server."""
from __future__ import annotations
import logging
from typing import Any, Dict
from .storage import CalendarStorage

logger = logging.getLogger(__name__)

class CalendarHandlers:
    """Handler implementations for calendar tools."""

    def __init__(self, storage: CalendarStorage) -> None:
        self._storage = storage

    async def list_events(self, arguments: Dict[str, Any]) -> Dict[str, Any]:
        """Handle tool.read.calendar.list_events."""
        start_date = arguments["start_date"]
        end_date = arguments["end_date"]
        events = await self._storage.list_events(start_date, end_date)
        return {
            "events": [e.to_dict() for e in events],
            "count": len(events),
        }

    async def create_event(self, arguments: Dict[str, Any]) -> Dict[str, Any]:
        """Handle tool.write.calendar.create_event."""
        event = await self._storage.create_event(
            title=arguments["title"],
            start_time=arguments["start_time"],
            end_time=arguments["end_time"],
            location=arguments.get("location"),
            description=arguments.get("description"),
        )
        return {
            "event_id": event.event_id,
            "status": "created",
        }

    async def delete_event(self, arguments: Dict[str, Any]) -> Dict[str, Any]:
        """Handle tool.write.calendar.delete_event."""
        event_id = arguments["event_id"]
        deleted = await self._storage.delete_event(event_id)
        return {
            "event_id": event_id,
            "status": "deleted" if deleted else "not_found",
        }
```

#### 4. Implement the MCP Server (`server.py`)

The server registers tools and handles JSON-RPC messages over stdio:

```python
"""MCP server for family calendar (stdio transport)."""
from __future__ import annotations
import asyncio
import json
import logging
import sys
from typing import Any, Dict

from .handlers import CalendarHandlers
from .storage import CalendarStorage

logger = logging.getLogger(__name__)

# Tool definitions per MCP spec (tools/list response)
TOOLS = [
    {
        "name": "tool.read.calendar.list_events",
        "description": "List calendar events by date range",
        "inputSchema": {
            "type": "object",
            "properties": {
                "start_date": {"type": "string", "description": "Start date (ISO 8601)"},
                "end_date": {"type": "string", "description": "End date (ISO 8601)"},
            },
            "required": ["start_date", "end_date"],
        },
    },
    {
        "name": "tool.write.calendar.create_event",
        "description": "Create a new calendar event",
        "inputSchema": {
            "type": "object",
            "properties": {
                "title": {"type": "string"},
                "start_time": {"type": "string"},
                "end_time": {"type": "string"},
                "location": {"type": "string"},
                "description": {"type": "string"},
            },
            "required": ["title", "start_time", "end_time"],
        },
    },
    {
        "name": "tool.write.calendar.delete_event",
        "description": "Delete a calendar event by ID",
        "inputSchema": {
            "type": "object",
            "properties": {
                "event_id": {"type": "string"},
            },
            "required": ["event_id"],
        },
    },
]


class CalendarMCPServer:
    """MCP server that communicates over stdio."""

    def __init__(self) -> None:
        self._storage = CalendarStorage()
        self._handlers = CalendarHandlers(self._storage)
        self._tool_map = {
            "tool.read.calendar.list_events": self._handlers.list_events,
            "tool.write.calendar.create_event": self._handlers.create_event,
            "tool.write.calendar.delete_event": self._handlers.delete_event,
        }

    async def handle_message(self, message: Dict[str, Any]) -> Dict[str, Any]:
        """Route a JSON-RPC message to the correct handler."""
        method = message.get("method", "")
        msg_id = message.get("id")

        if method == "initialize":
            return self._response(msg_id, {
                "protocolVersion": "2024-11-05",
                "capabilities": {"tools": {"listChanged": False}},
                "serverInfo": {"name": "calendar-mcp", "version": "1.0.0"},
            })

        if method == "tools/list":
            return self._response(msg_id, {"tools": TOOLS})

        if method == "tools/call":
            params = message.get("params", {})
            tool_name = params.get("name", "")
            arguments = params.get("arguments", {})

            handler = self._tool_map.get(tool_name)
            if handler is None:
                return self._error(msg_id, -32601, f"Unknown tool: {tool_name}")

            try:
                result = await handler(arguments)
                return self._response(msg_id, {
                    "content": [{"type": "text", "text": json.dumps(result)}],
                })
            except Exception as exc:
                return self._error(msg_id, -32000, str(exc))

        if method == "ping":
            return self._response(msg_id, {})

        return self._error(msg_id, -32601, f"Method not found: {method}")

    @staticmethod
    def _response(msg_id: Any, result: Any) -> Dict[str, Any]:
        return {"jsonrpc": "2.0", "id": msg_id, "result": result}

    @staticmethod
    def _error(msg_id: Any, code: int, message: str) -> Dict[str, Any]:
        return {"jsonrpc": "2.0", "id": msg_id, "error": {"code": code, "message": message}}


async def main() -> None:
    """stdio event loop: read JSON-RPC from stdin, write to stdout."""
    server = CalendarMCPServer()
    reader = asyncio.StreamReader()
    protocol = asyncio.StreamReaderProtocol(reader)
    await asyncio.get_event_loop().connect_read_pipe(lambda: protocol, sys.stdin.buffer)

    while True:
        line = await reader.readline()
        if not line:
            break
        try:
            message = json.loads(line.decode())
            response = await server.handle_message(message)
            sys.stdout.write(json.dumps(response) + "\n")
            sys.stdout.flush()
        except json.JSONDecodeError:
            logger.warning("Invalid JSON received: %s", line)


if __name__ == "__main__":
    asyncio.run(main())
```

#### 5. Write the Contract YAML

See Section 3 for the full format.

#### 6. Test

See Section 9.

---

## 5. Building an MCP Server (Remote — SSE)

Remote MCP servers run as standalone HTTP services. Fabric connects to them via Server-Sent Events (SSE) or HTTP streaming.

### Architecture

```
FabricFactory
    |
    +--> MCPProvider (config.transport = "SSE")
             |
             +--> IMCPTransport (SSE implementation)
                      |
                      +--> HTTPS connection to remote endpoint
                               |
                               Server-Sent Events stream
```

### Key Differences from Local

| Aspect | Local (stdio) | Remote (SSE) |
|--------|-------------|-------------|
| Transport | subprocess stdin/stdout | HTTPS SSE stream |
| Timeout | 10s default | 15s default |
| Endpoint | `python -m <module>` | `https://host:port/sse` |
| Network | None (same machine) | Internet required |
| Failure Mode | Process crash | Network timeout, HTTP errors |
| Circuit Breaker | 3 failures/min | 3 failures/min |

### Server Implementation

Remote MCP servers are regular HTTP services. You can build them with any framework (FastAPI, aiohttp, etc.):

```python
"""Weather MCP server (SSE transport)."""
from fastapi import FastAPI, Request
from sse_starlette.sse import EventSourceResponse
import json

app = FastAPI()

@app.get("/sse")
async def sse_endpoint(request: Request):
    """SSE endpoint for MCP protocol."""
    async def event_generator():
        # MCP handshake and message handling over SSE
        ...
    return EventSourceResponse(event_generator())

@app.post("/message")
async def message_endpoint(request: Request):
    """JSON-RPC message endpoint."""
    body = await request.json()
    # Route to handlers, return JSON-RPC response
    ...
```

### ProviderConfig for Remote

```python
ProviderConfig(
    provider_id="weather_mcp",
    provider_type="MCP",
    endpoint="https://weather.familyos.local/sse",
    transport="SSE",                    # or "STREAMABLE_HTTP"
    max_concurrent=5,
    max_execution_ms=15000,             # Remote default
)
```

---

## 6. Building a WASM Tool

WASM tools are sandboxed modules that execute pure computation. No network, no filesystem, strict memory limits.

### Architecture

```
FabricFactory
    |
    +--> WASMProvider (config.module_path from contract)
             |
             +--> IWASMRuntime (AutoDiscoveryWASMRuntime)
                      |
                      +--> Scans k1/tools/wasm_modules/ at startup
                               |
                               +--> <name>/executor.py -> execute(params) -> dict
                               |        (Python executor, auto-discovered)
                               |
                               +--> OR: <name>/build/<name>.wasm (future: compiled WASM)
```

> **Note:** The current implementation uses Python executors (see below).
> Compiled `.wasm` via Rust/C is a future production path. Both are
> auto-discovered by `AutoDiscoveryWASMRuntime`.

### When to Use WASM vs MCP

| Use WASM When | Use MCP When |
|---------------|-------------|
| Pure computation (math, conversions, parsing) | I/O needed (database, files, network) |
| Ultra-low latency required (<100ms) | Latency tolerance (>100ms ok) |
| Untrusted or user-contributed code | Trusted infrastructure code |
| Deterministic output needed | State or side effects involved |
| No external dependencies | External APIs or services |

### Step-by-Step

#### 1. Write the Module (Rust Example)

```rust
// k1/tools/wasm_modules/date_calc/src/lib.rs
use std::ffi::{CStr, CString};
use std::os::raw::c_char;

/// Exported function: called by WASMProvider
#[no_mangle]
pub extern "C" fn execute(input_ptr: *const c_char) -> *mut c_char {
    let input = unsafe { CStr::from_ptr(input_ptr).to_str().unwrap() };
    let params: serde_json::Value = serde_json::from_str(input).unwrap();

    let operation = params["operation"].as_str().unwrap_or("days_between");
    let result = match operation {
        "days_between" => days_between(&params),
        "add_days" => add_days(&params),
        "weekday" => weekday(&params),
        _ => serde_json::json!({"error": "unknown operation"}),
    };

    let output = CString::new(result.to_string()).unwrap();
    output.into_raw()
}

fn days_between(params: &serde_json::Value) -> serde_json::Value {
    // ... implementation
    serde_json::json!({"days": 42})
}
```

#### 2a. Compile to WASM (Future Production Path)

```bash
# Using Rust
cargo build --target wasm32-wasi --release
cp target/wasm32-wasi/release/date_calc.wasm k1/tools/wasm_modules/date_calc/build/
```

#### 2b. Python Executor Pattern (Current — Recommended)

Instead of compiling to WASM, you can write a Python executor. This is the **current standard pattern** used by all existing WASM modules (date_calc, unit_convert).

**Directory layout:**

```
k1/tools/wasm_modules/date_calc/
    __init__.py
    executor.py          # REQUIRED — must export execute(params) -> dict
```

**Write `executor.py`:**

```python
"""Pure computation executor for date_calc WASM tool."""
from __future__ import annotations
from datetime import date, timedelta
from typing import Any, Dict

def execute(params: Dict[str, Any]) -> Dict[str, Any]:
    """
    Entry point called by AutoDiscoveryWASMRuntime.

    Args:
        params: Tool arguments from CapabilityRequest.params
    Returns:
        Dict matching the contract's output JSON Schema
    Raises:
        ValueError: For invalid inputs (caught by WASMProvider)
    """
    operation = params.get("operation", "days_between")

    if operation == "days_between":
        d1 = date.fromisoformat(params["date"])
        d2 = date.fromisoformat(params["date2"])
        return {"result": abs((d2 - d1).days)}

    if operation == "add_days":
        d = date.fromisoformat(params["date"])
        days = int(params.get("days", 0))
        return {"result": (d + timedelta(days=days)).isoformat()}

    raise ValueError(f"Unknown operation: {operation}")
```

**Rules for Python executors:**
- File MUST be named `executor.py`
- MUST export a top-level `execute(params: dict) -> dict` function
- MUST be pure computation: no I/O, no network, no filesystem, no state
- Errors raise exceptions (caught and wrapped by WASMProvider)
- `AutoDiscoveryWASMRuntime` picks this up automatically — zero Fabric code changes

#### 3. Write the Contract

```yaml
tool_contract:
  name: "tool.execute.date_calc"
  version: "1.0.0"
  domain: ["UTILITY", "DATE"]
  description: "Date arithmetic operations"
  capabilities: ["date_calculation"]
  limitations: ["pure_computation", "no_timezone_awareness"]

  required_inputs:
    - name: "operation"
      type: "STRING"
      description: "Operation: days_between, add_days, weekday, is_weekend"
    - name: "date"
      type: "STRING"
      description: "Primary date (ISO 8601)"

  optional_inputs:
    - name: "date2"
      type: "STRING"
      description: "Second date (for days_between)"
    - name: "days"
      type: "NUMBER"
      description: "Number of days to add (for add_days)"
      default: 0

  output:
    type: "object"
    properties:
      result:
        description: "Operation result (days count, date string, weekday, or boolean)"
    required: ["result"]

  provider_type: "WASM"
  provider_id: "date_calc_wasm"
  safety_band_min: "GREEN"
  cost_per_call: 0.0
  avg_latency_ms: 5
  max_latency_ms: 100
  availability: "ONLINE"
  tags: ["utility", "date", "pure_computation"]
```

#### 4. Configure the Provider

```python
ProviderConfig(
    provider_id="date_calc_wasm",
    provider_type="WASM",
    module_path="k1/tools/wasm_modules/date_calc/build/date_calc.wasm",
    sandbox_memory_mb=4,                # Minimal for date math
    max_execution_ms=1000,              # 1 second
)
```

### Sandbox Constraints

| Config | Default | Range | Notes |
|--------|---------|-------|-------|
| `sandbox_memory_mb` | 64 | 1-256 | Memory allocation for the sandbox |
| `max_execution_ms` | 5000 | 100-30000 | Execution timeout |
| Network | NEVER | — | Always disabled |
| Filesystem | NEVER | — | Always disabled |

---

## 7. Provider Configuration and Registration

### ProviderConfig Fields

```python
@dataclass(frozen=True)
class ProviderConfig:
    provider_id: str = ""           # Unique ID (matches contract's provider_id)
    provider_type: str = ""         # MCP, WASM, BRIDGE, AGENT, WORKFLOW, CONCIERGE
    endpoint: str = ""              # MCP: server URL or subprocess command
    transport: str = ""             # MCP: STDIO, SSE, STREAMABLE_HTTP
    module_path: str = ""           # WASM: path to .wasm file
    sandbox_memory_mb: int = 64     # WASM: memory limit
    max_concurrent: int = 1         # Max parallel calls
    max_execution_ms: int = 30000   # Timeout
```

### How Providers Get Created

The `_register_provider_handlers()` function in `factory.py` registers constructor functions for each provider type. When the Resolver selects a provider, `ProviderFactory.create(config)` dispatches to the correct constructor:

| Provider Type | Constructor | Port Dependencies |
|---------------|-----------|-------------------|
| MCP | `_create_mcp` | `mcp_transport: IMCPTransport` |
| WASM | `_create_wasm` | `wasm_runtime: IWASMRuntime` |
| BRIDGE | `_create_bridge` | `bridge_port: IBridgePort` |
| AGENT | `_create_agent` | `model_gateway`, `state_reader`, `delta_bus`, `context_builder` |
| WORKFLOW | `_create_workflow` | `workflow_registry`, `capability_lookup`, `orchestrator` |
| CONCIERGE | `_create_concierge` | `concierge_router` |

Port dependencies are injected at factory construction time (step 9 of the 20-step build). You do NOT need to manage these yourself.

---

## 8. How Fabric Discovers Your Tool

### Auto-Discovery on Startup

```
FabricFactory._construct_fabric()
    |
    +--> Step 4: ModuleLoader(registry, contracts_dir, ...)
    |
    +--> Step 20: module_loader.start(watch=False)
              |
              +--> scan_directory()
                        |
                        +--> Recursively finds *.yaml, *.yml in:
                        |        k1/contracts/tools/
                        |        k1/contracts/agents/
                        |        k1/contracts/prompts/
                        |        k1/contracts/workflows/
                        |
                        +--> For each file:
                                 parse_contract(file) -> ContractValidator -> CapabilityRegistry
```

### Transport & Runtime Auto-Discovery

Fabric has **two levels** of discovery:

1. **Contract Discovery** (above) — finds YAML contracts, registers capabilities
2. **Transport/Runtime Discovery** — finds MCP servers and WASM executors, routes execution

Transport discovery happens at factory construction via auto-discovery adapters:

#### MCP Server Auto-Discovery (`AutoDiscoveryMCPTransport`)

```
FabricFactory._construct_fabric()
    |
    +--> Step 9: AutoDiscoveryMCPTransport(servers_dir="k1/tools/mcp_servers")
              |
              +--> _discover_servers()
                        |
                        +--> Scans k1/tools/mcp_servers/*/server.py
                        |
                        +--> For each server.py, auto-detects pattern:
                        |
                        |    JSON-RPC pattern (Calendar, Weather):
                        |        Class ending with "MCPServer" + handle_message() + TOOLS list
                        |        -> Routes capability names from TOOLS list
                        |
                        |    FastMCP pattern (Notes, Recipes):
                        |        FastMCP instance + @mcp.tool() decorators
                        |        -> Routes by function name (prefix-stripped)
                        |
                        +--> Result: tool_name -> server routing table (zero config)
```

**Convention — adding a new MCP server requires ZERO Fabric code changes:**

1. Create `k1/tools/mcp_servers/<name>/server.py`
2. Use either JSON-RPC or FastMCP pattern (auto-detected)
3. Add YAML contract(s) in `k1/contracts/tools/`
4. Done. `AutoDiscoveryMCPTransport` finds it on next startup.

#### WASM Module Auto-Discovery (`AutoDiscoveryWASMRuntime`)

```
FabricFactory._construct_fabric()
    |
    +--> Step 9: AutoDiscoveryWASMRuntime(modules_dir="k1/tools/wasm_modules")
              |
              +--> _discover_modules()
                        |
                        +--> Scans k1/tools/wasm_modules/*/executor.py
                        |
                        +--> For each executor.py:
                        |        Import module, verify execute() function exists
                        |        Register by directory name (e.g., "date_calc")
                        |
                        +--> Result: module_name -> executor function (zero config)
```

**Convention — adding a new WASM module requires ZERO Fabric code changes:**

1. Create `k1/tools/wasm_modules/<name>/executor.py` with `execute(params) -> dict`
2. Add YAML contract in `k1/contracts/tools/`
3. Done. `AutoDiscoveryWASMRuntime` finds it on next startup.

### Hot-Reload (Development)

When `module_loader.start(watch=True)` is called, a daemon thread polls every 2 seconds:

- **New file** -> parse, validate, register
- **Modified file** -> re-parse, swap in registry (old contract unregistered, new registered)
- **Deleted file** -> unregister from registry

This means during development, you can add/modify contract YAML files and they will be picked up automatically without restarting.

> **Note:** Transport/runtime auto-discovery currently happens at construction time only. Adding a new MCP server or WASM module requires a Fabric restart (or re-construction). Contract hot-reload is independent.

### Programmatic Registration

For dynamic tool discovery (e.g., an MCP server that advertises its tools at runtime):

```python
module_loader.register_from_dict(
    {
        "tool_contract": {
            "name": "tool.read.dynamic_tool",
            "version": "1.0.0",
            ...
        }
    }
)
```

---

## 9. Testing Your Tool

### Use FabricFactory.create_for_testing()

This gives you a fully wired Fabric with test adapters — no external services needed:

```python
import pytest
from k1.fabric.factory import FabricFactory
from k1.fabric.types import CapabilityRequest

@pytest.fixture
def fabric():
    """Create a test Fabric instance (canned responses)."""
    return FabricFactory.create_for_testing(
        contracts_dir="k1/contracts",  # Where your YAML lives
    )

@pytest.mark.asyncio
async def test_calendar_list_events(fabric):
    """Test calendar list events via full Fabric pipeline."""
    request = CapabilityRequest(
        capability_name="tool.read.calendar.list_events",
        params={
            "start_date": "2025-01-01",
            "end_date": "2025-01-31",
        },
        caller="test",
        safety_band="GREEN",
    )

    result = await fabric.facade.execute(request)

    assert result.success
    assert "events" in result.data
    assert isinstance(result.data["events"], list)
```

### Real Sandbox Testing with Auto-Discovery

To test with **real MCP servers and WASM executors** (not canned responses), inject the auto-discovery adapters:

```python
from k1.fabric.factory import FabricFactory
from k1.fabric.adapters import AutoDiscoveryMCPTransport, AutoDiscoveryWASMRuntime

@pytest.fixture
def real_fabric():
    """Create a Fabric instance wired to real tool servers."""
    mcp = AutoDiscoveryMCPTransport(
        servers_dir="k1/tools/mcp_servers",  # Scans all server.py files
    )
    wasm = AutoDiscoveryWASMRuntime(
        modules_dir="k1/tools/wasm_modules",  # Scans all executor.py files
    )
    return FabricFactory.create_for_testing(
        contracts_dir="k1/contracts",
        mcp_transport=mcp,       # Real MCP dispatch
        wasm_runtime=wasm,       # Real WASM execution
    )

@pytest.mark.asyncio
async def test_real_calendar(real_fabric):
    """E2E test hitting the actual calendar MCP server."""
    request = CapabilityRequest(
        capability_name="tool.read.calendar.list_events",
        params={"start_date": "2025-01-01", "end_date": "2025-01-31"},
        caller="test",
        safety_band="GREEN",
    )
    result = await real_fabric.facade.execute(request)
    assert result.success
    assert "events" in result.data
```

> **Tip:** The default `create_for_testing()` (without auto-discovery args) uses canned test adapters for fast, deterministic CI. Use auto-discovery adapters when you want to validate real server behavior.

### Test Checklist Per Tool

| # | Test | What It Validates |
|---|------|-------------------|
| 1 | Contract YAML parses without errors | ContractValidator, parse_contract |
| 2 | Contract registers in CapabilityRegistry | ModuleLoader.scan_directory |
| 3 | execute() returns success with correct data shape | Full 9-step pipeline |
| 4 | execute() with bad params returns failure | Error handling |
| 5 | Output matches contract's JSON Schema | OutputValidationPipeline |
| 6 | Safety band enforcement | PolicyEngine |
| 7 | Timeout enforcement | CircuitBreaker |
| 8 | Events emitted correctly | EventEmitter (captured by test adapter) |

### Asserting on Events

With `create_for_testing(capture_events=True)`, the event adapter captures all emitted events:

```python
async def test_events_emitted(fabric):
    request = CapabilityRequest(
        capability_name="tool.read.calendar.list_events",
        params={"start_date": "2025-01-01", "end_date": "2025-01-31"},
        caller="test",
    )
    await fabric.facade.execute(request)

    events = fabric.event_port.captured_events
    topics = [e["topic"] for e in events]

    assert "k1.capability.invoked.v1" in topics
    assert "k1.capability.completed.v1" in topics
    assert "k1.fabric.learning.signal.v1" in topics
```

---

## 10. Safety Bands and Policy

### Safety Band Hierarchy

| Band | Risk Level | Who Can Call | Examples |
|------|-----------|-------------|---------|
| **GREEN** | Read-only, no side effects | Any caller | List events, search, weather lookup |
| **AMBER** | Write operations, reversible | Orchestrator (confirmed by user intent) | Create event, send message |
| **RED** | Irreversible or high-impact | Orchestrator (explicit user confirmation) | Delete data, make purchases |
| **CRISIS** | Emergency only | System-level with elevated permissions | Emergency contacts, safety protocols |

### How Bands Are Enforced

1. Your contract declares `safety_band_min` (minimum band required)
2. The caller's `CapabilityRequest.safety_band` must be >= `safety_band_min`
3. PolicyEngine checks this during Step 2 (Resolve)
4. If band insufficient -> resolution fails with policy error

### Naming Convention Signals Band

| Prefix | Default Band | Use Case |
|--------|-------------|----------|
| `tool.read.*` | GREEN | Read operations |
| `tool.write.*` | AMBER | Mutations |
| `tool.execute.*` | GREEN | Pure computation |

---

## 11. Error Handling and Circuit Breakers

### Error Types

| Error | When | Retriable |
|-------|------|-----------|
| `MCPServerNotFoundError` | Server unreachable | Yes |
| `MCPToolNotFoundError` | Tool not on server | No |
| `MCPTransportError` | Connection/protocol failure | Yes |
| `ProviderTimeoutError` | Execution exceeded max_execution_ms | Yes |
| `WASMModuleLoadError` | .wasm file not found or corrupt | No |
| `WASMExecutionError` | Runtime error inside sandbox | Depends |
| `WASMMemoryLimitError` | Sandbox memory exceeded | No |

### Circuit Breaker Behavior

```
CLOSED (normal) --[3 failures]--> OPEN (reject all calls)
                                      |
                                [30s cooldown]
                                      |
                               HALF_OPEN (allow 1 test call)
                                   /       \
                            [success]     [failure]
                               |              |
                            CLOSED          OPEN
```

All errors are wrapped in `CapabilityResult.failure_result()` — Fabric **never raises** from `execute()`. Check `result.success` and `result.error`.

---

## 12. Naming Conventions

### Capability Names

```
<type>.<operation>.<domain>.<action>
```

| Segment | Values | Examples |
|---------|--------|---------|
| type | `tool`, `agent`, `workflow`, `concierge` | `tool.read.calendar.list_events` |
| operation | `read`, `write`, `execute` | `tool.write.notes.create` |
| domain | your domain | `calendar`, `weather`, `notes` |
| action | specific action | `list_events`, `forecast`, `convert` |

### Provider IDs

- Must be unique across the entire Fabric
- Use lowercase, underscores
- Convention: `<domain>_<transport>` or `<domain>_<type>`
- Examples: `calendar_mcp`, `weather_mcp_sse`, `date_calc_wasm`

### Contract File Names

- Use the action part of the capability name
- Place in the correct subdirectory
- Examples:
  - `k1/contracts/tools/calendar_list_events.yaml`
  - `k1/contracts/tools/weather_current.yaml`
  - `k1/contracts/tools/date_calc.yaml`

---

## 13. Quick Start Checklist

Starting a new tool? Follow this checklist:

- [ ] **1. Choose provider type**: MCP (I/O, APIs, database) or WASM (pure computation)
- [ ] **2. Choose transport** (MCP only): stdio (local) or SSE (remote)
- [ ] **3. Pick a capability name**: Follow naming convention in Section 12
- [ ] **4. Write the contract YAML**: Drop in `k1/contracts/tools/`
- [ ] **5. Validate the contract**: Run `ContractValidator` or let tests catch errors
- [ ] **6. Implement the server/module**:
  - MCP: Create `server.py` in `k1/tools/mcp_servers/<name>/` (JSON-RPC or FastMCP pattern)
  - WASM: Create `executor.py` in `k1/tools/wasm_modules/<name>/` with `execute(params) -> dict`
- [ ] **7. Verify auto-discovery**: Your tool is found automatically. No Fabric code changes needed.
  - MCP: `AutoDiscoveryMCPTransport` detects `server.py` pattern on startup
  - WASM: `AutoDiscoveryWASMRuntime` detects `executor.py` on startup
  - Contracts: `ModuleLoader` scans `k1/contracts/tools/` on startup
- [ ] **8. Write integration tests**: Use `FabricFactory.create_for_testing()` (canned) or inject `AutoDiscoveryMCPTransport`/`AutoDiscoveryWASMRuntime` (real)
- [ ] **9. Test error paths**: Timeout, bad params, server down
- [ ] **10. Verify events**: Check invoked/completed/learning signals

> **Zero-touch rule:** If you touched any file inside `k1/fabric/` to add your tool, something is wrong. Tools are discovered by convention, not by registration.

---

## 14. Reference: Existing Contracts

Study these existing contracts as templates:

| Contract | Location | Type | Band |
|----------|----------|------|------|
| Build Agent | `k1/contracts/tools/build_agent.yaml` | MCP (write) | AMBER |
| Discover Capabilities | `k1/contracts/tools/discover_capabilities.yaml` | MCP (read) | GREEN |
| Find Prompts | `k1/contracts/tools/find_prompts.yaml` | MCP (read) | GREEN |
| Calendar List Events | `k1/contracts/tools/calendar_list_events.yaml` | MCP stdio (read) | GREEN |
| Calendar Create Event | `k1/contracts/tools/calendar_create_event.yaml` | MCP stdio (write) | AMBER |
| Calendar Delete Event | `k1/contracts/tools/calendar_delete_event.yaml` | MCP stdio (write) | AMBER |
| Weather Current | `k1/contracts/tools/weather_current.yaml` | MCP SSE (read) | GREEN |
| Weather Forecast | `k1/contracts/tools/weather_forecast.yaml` | MCP SSE (read) | GREEN |
| Notes Create | `k1/contracts/tools/notes_create.yaml` | MCP stdio/FastMCP (write) | AMBER |
| Notes List | `k1/contracts/tools/notes_list.yaml` | MCP stdio/FastMCP (read) | GREEN |
| Notes Search | `k1/contracts/tools/notes_search.yaml` | MCP stdio/FastMCP (read) | GREEN |
| Recipes Search | `k1/contracts/tools/recipes_search.yaml` | MCP SSE/FastMCP (read) | GREEN |
| Recipes Get | `k1/contracts/tools/recipes_get.yaml` | MCP SSE/FastMCP (read) | GREEN |
| Date Calc | `k1/contracts/tools/date_calc.yaml` | WASM (execute) | GREEN |
| Unit Convert | `k1/contracts/tools/unit_convert.yaml` | WASM (execute) | GREEN |

### Key Files to Study

| File | Purpose |
|------|---------|
| `k1/fabric/fabric.py` | Main Fabric API — execute() pipeline |
| `k1/fabric/factory.py` | FabricFactory — 20-step wiring |
| `k1/fabric/types.py` | CapabilityRequest, CapabilityResult, ProviderConfig |
| `k1/fabric/providers/mcp_provider.py` | MCPProvider — MCP execution flow |
| `k1/fabric/providers/wasm_provider.py` | WASMProvider — WASM sandbox flow |
| `k1/fabric/core/module_loader.py` | ModuleLoader — contract discovery, hot-reload |
| `k1/fabric/adapters/auto_mcp_transport.py` | AutoDiscoveryMCPTransport — zero-config MCP routing |
| `k1/fabric/adapters/auto_wasm_runtime.py` | AutoDiscoveryWASMRuntime — zero-config WASM execution |
| `k1/contracts/tools/build_agent.yaml` | Example contract (full annotated YAML) |

---

## Appendix A: CapabilityRequest Quick Reference

```python
request = CapabilityRequest(
    capability_name="tool.read.calendar.list_events",  # REQUIRED: matches contract name
    params={"start_date": "2025-01-01"},               # REQUIRED: tool arguments
    caller="orchestrator",                              # REQUIRED: who's calling
    safety_band="GREEN",                                # DEFAULT: GREEN
    tier="MEDIUM",                                      # DEFAULT: MEDIUM
    wfq_priority="INTERACTIVE",                         # DEFAULT: INTERACTIVE
    timeout_ms=30000,                                   # DEFAULT: 30s
    trace_id="auto-generated-uuid",                     # DEFAULT: auto-generated
    session_id="session-123",                           # OPTIONAL: session binding
    plan_id="plan-456",                                 # OPTIONAL: plan correlation
    step_id="step-789",                                 # OPTIONAL: DAG step correlation
)
```

## Appendix B: CapabilityResult Quick Reference

```python
# Success
result.success          # True
result.data             # Dict — your tool's return value
result.provider_id      # Which provider handled it
result.duration_ms      # Total pipeline time
result.execution_time_ms # Provider execution time only
result.trace_id         # Cognitive trace ID

# Failure
result.success          # False
result.error.code       # Error code string
result.error.message    # Human-readable error
result.error.retriable  # Whether caller should retry
```
