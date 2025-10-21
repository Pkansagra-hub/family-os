# ADR-0033a: MCP Protocol Integration (Layer 1 - Protocol)

**Status:** ✅ Approved
**Date:** 2025-10-13
**Last Updated:** 2025-01-15 (M4 Context: See ADR-0078 for tool call batching + execution)
**Authors:** K1 Architecture Team
**Category:** Tool Integration - Protocol Layer
**Parent ADR:** ADR-0033 (Tool Execution Architecture - Protocol × Sandbox)
**Related ADRs:** ADR-0034 (MCP Protocol for Tool Integration), ADR-0032 (Band-Based Egress Rules), ADR-0078 (Tool Call Batching Pipeline - **NEW M4**)

---

## Context

### Problem Statement

**K1 needs a standardized protocol implementation for tool communication that works with ANY execution sandbox (WASM, Process, Container).**

**Current Challenge:** Without a protocol standard:

**Problem 1: Custom Integration Per Tool**
- Every tool has unique interface (REST API, CLI, library call)
- K1 must implement custom adapter for each tool
- 758 tools = 758 adapters = maintenance nightmare

**Problem 2: Sandbox Coupling**
- Some solutions couple protocol with sandbox (e.g., "MCP is a sandbox tier")
- This prevents flexibility (e.g., running MCP server in WASM vs Process)
- **ADR-0033 establishes:** Protocol (Layer 1) is INDEPENDENT from Sandbox (Layer 2)

**Problem 3: No Industry Standard**
- OpenAI uses function calling (JSON schema only, no protocol)
- LangChain uses Python classes (language-specific, no cross-system)
- No common protocol means tools written for one system don't work elsewhere

### Solution

**Adopt Model Context Protocol (MCP, Anthropic 2024) as Layer 1 protocol for 80% of tools, with MCP servers capable of running in ANY Layer 2 sandbox (WASM, Process, Container).**

**Key Insight:** MCP is a PROTOCOL (like HTTP), not a sandbox. MCP servers can run:
- **In WASM sandbox** (10%): user_plugin.wasm with MCP server in WASM
- **In Process sandbox** (70%): weather_api.py with MCP server as native process
- **In Container sandbox** (<1%): high_risk_tool with MCP server in Firecracker microVM

This ADR defines the **protocol implementation** (Layer 1), independent of sandbox choice (Layer 2, see ADR-0033b/c).

---

## Decision

**We will implement MCPClient as the primary protocol handler for K1, supporting stdio and HTTP transports with timeout enforcement, circuit breaker resilience, and full JSON-RPC 2.0 compliance.**

### Core Principles

1. **Protocol-Sandbox Independence:**
   - MCPClient communicates via JSON-RPC 2.0 (protocol standard)
   - Sandbox choice (WASM/Process/Container) is orthogonal to protocol
   - Same MCPClient works with MCP servers in any sandbox

2. **Transport Flexibility:**
   - **stdio Transport (70%):** JSON-RPC over stdin/stdout for process-based servers
   - **HTTP Transport (10%):** JSON-RPC over POST for WASM/remote servers

3. **Timeout Enforcement:**
   - Per-tool timeout configuration (5s - 300s)
   - Automatic process kill on timeout
   - Graceful cleanup (SIGTERM → 5s → SIGKILL)

4. **Circuit Breaker Resilience:**
   - CLOSED/OPEN/HALF_OPEN states
   - Failure threshold (5 failures → OPEN for 30s)
   - Automatic recovery testing

5. **Observable:**
   - Prometheus metrics for all operations
   - OpenTelemetry tracing with cognitive_trace_id
   - Structured logging with error context

---

## Architecture

### Layer 1 (Protocol) - This ADR

```
┌─────────────────────────────────────────────────────────────┐
│                      K1 Orchestrator                        │
└──────────────────────┬──────────────────────────────────────┘
                       │
                       │ calls
                       ▼
┌─────────────────────────────────────────────────────────────┐
│                      MCPClient                              │
│  ┌────────────────────────────────────────────────────┐    │
│  │  Protocol Layer (This ADR)                         │    │
│  │  - JSON-RPC 2.0 request/response                   │    │
│  │  - Transport: stdio or HTTP                        │    │
│  │  - Timeout enforcement                             │    │
│  │  - Circuit breaker integration                     │    │
│  └────────────────────────────────────────────────────┘    │
└──────────────────────┬──────────────────────────────────────┘
                       │
                       │ JSON-RPC 2.0
                       │ (stdio pipes or HTTP POST)
                       ▼
┌─────────────────────────────────────────────────────────────┐
│                   MCP Server                                │
│  (Runs in Layer 2 Sandbox - see ADR-0033b/c)              │
│  - WASM Sandbox (ADR-0033b)                                │
│  - Process Sandbox (ADR-0033c)                             │
│  - Container Sandbox (ADR-0033)                            │
└─────────────────────────────────────────────────────────────┘
```

### Protocol Flow

```
1. K1 discovers MCP servers (tool_registry.yml)
   └─> Tool definition specifies: protocol=mcp, sandbox=process/wasm/container

2. K1 starts MCP server in chosen sandbox (Layer 2)
   └─> Sandbox choice handled by Layer 2 (ADR-0033b/c)

3. MCPClient sends "initialize" request (JSON-RPC 2.0)
   └─> Server responds with capabilities

4. MCPClient sends "tools/list" request
   └─> Server responds with available tools (JSON Schema)

5. MCPClient sends "tools/call" request
   └─> Server executes tool, returns result

6. MCPClient sends "shutdown" request
   └─> Server gracefully terminates
```

---

## Implementation

### JSON-RPC 2.0 Protocol

**Specification:** https://www.jsonrpc.org/specification

**Request Format:**
```json
{
  "jsonrpc": "2.0",
  "id": "req_12345",
  "method": "tools/call",
  "params": {
    "name": "get_weather",
    "arguments": {
      "city": "Seattle",
      "units": "metric"
    }
  }
}
```

**Response Format (Success):**
```json
{
  "jsonrpc": "2.0",
  "id": "req_12345",
  "result": {
    "city": "Seattle",
    "temperature": 18.5,
    "units": "metric",
    "description": "Partly cloudy"
  }
}
```

**Response Format (Error):**
```json
{
  "jsonrpc": "2.0",
  "id": "req_12345",
  "error": {
    "code": -32601,
    "message": "Tool not found: get_weather",
    "data": {
      "available_tools": ["get_forecast", "get_alerts"]
    }
  }
}
```

**Standard Error Codes:**
- `-32700`: Parse error (invalid JSON)
- `-32600`: Invalid request (missing required fields)
- `-32601`: Method not found (tool doesn't exist)
- `-32602`: Invalid params (arguments don't match schema)
- `-32603`: Internal error (tool execution failed)

---

### MCPClient Implementation

```python
import asyncio
import json
import time
import uuid
from dataclasses import dataclass
from typing import Optional, Dict, List
from enum import Enum

class ProtocolType(Enum):
    """Protocol types (Layer 1)"""
    MCP = "mcp"
    DIRECT = "direct"

class TransportType(Enum):
    """MCP transport mechanisms"""
    STDIO = "stdio"
    HTTP = "http"

@dataclass
class MCPServerConfig:
    """
    MCP server configuration (protocol layer only).

    Note: Sandbox configuration is in Layer 2 (ADR-0033b/c).
    """
    server_path: str
    transport: TransportType  # stdio or http
    timeout_seconds: int
    port: Optional[int] = None  # For HTTP transport

    # Sandbox configuration is separate (Layer 2)
    # See ADR-0033b (WASM), ADR-0033c (Process)

@dataclass
class JsonRpcRequest:
    """JSON-RPC 2.0 request"""
    jsonrpc: str = "2.0"
    id: str = ""
    method: str = ""
    params: Dict = None

    def __post_init__(self):
        if not self.id:
            self.id = str(uuid.uuid4())
        if self.params is None:
            self.params = {}

@dataclass
class JsonRpcResponse:
    """JSON-RPC 2.0 response"""
    jsonrpc: str
    id: str
    result: Optional[Dict] = None
    error: Optional[Dict] = None

class MCPClient:
    """
    MCP protocol client for K1 (Layer 1).

    Handles JSON-RPC 2.0 communication over stdio or HTTP.
    Works with MCP servers in ANY sandbox (WASM, Process, Container).

    Research: Model Context Protocol (Anthropic 2024), JSON-RPC 2.0 (2010)
    """

    def __init__(self, config: MCPServerConfig, circuit_breaker: 'CircuitBreaker'):
        """Initialize MCP client"""
        self.config = config
        self.circuit_breaker = circuit_breaker
        self.process: Optional[asyncio.subprocess.Process] = None
        self.request_id = 0

    async def initialize(self) -> Dict:
        """
        Initialize MCP server and send initialize request.

        Note: Server process is started by Layer 2 sandbox.
        This method only handles protocol handshake.
        """
        if self.config.transport == TransportType.STDIO:
            # For stdio, assume server process already started by sandbox
            # (see ADR-0033c for Process sandbox startup)
            pass

        # Send initialize request
        request = JsonRpcRequest(
            method="initialize",
            params={
                "protocolVersion": "2024-11-05",
                "clientInfo": {
                    "name": "k1_orchestrator",
                    "version": "1.0.0"
                }
            }
        )

        response = await self._send_request(request)

        if response.error:
            raise RuntimeError(f"MCP initialize failed: {response.error}")

        return response.result

    async def list_tools(self) -> List[Dict]:
        """
        List available tools from MCP server.

        Returns:
            List of tool definitions with JSON Schema
        """
        request = JsonRpcRequest(
            method="tools/list",
            params={}
        )

        response = await self._send_request(request)

        if response.error:
            raise RuntimeError(f"MCP tools/list failed: {response.error}")

        return response.result.get("tools", [])

    async def call_tool(
        self,
        tool_name: str,
        arguments: Dict,
        trace_id: str
    ) -> Dict:
        """
        Call tool via MCP server.

        Args:
            tool_name: Tool name
            arguments: Tool arguments (JSON-serializable)
            trace_id: Cognitive trace ID for observability

        Returns:
            dict: Tool result

        Raises:
            RuntimeError: If tool execution fails
            TimeoutError: If tool exceeds timeout
            CircuitBreakerOpenError: If circuit breaker is OPEN
        """
        # Check circuit breaker
        if not self.circuit_breaker.allow_request(tool_name):
            raise CircuitBreakerOpenError(
                f"Circuit breaker OPEN for {tool_name}"
            )

        start_time = time.time()

        try:
            # Send tools/call request with timeout
            request = JsonRpcRequest(
                method="tools/call",
                params={
                    "name": tool_name,
                    "arguments": arguments
                }
            )

            response = await asyncio.wait_for(
                self._send_request(request),
                timeout=self.config.timeout_seconds
            )

            # Check for errors
            if response.error:
                self.circuit_breaker.record_failure(tool_name)
                raise RuntimeError(
                    f"Tool {tool_name} failed: {response.error}"
                )

            # Success
            self.circuit_breaker.record_success(tool_name)
            latency_ms = (time.time() - start_time) * 1000

            # Log success (OpenTelemetry)
            logger.info(
                "mcp_tool_call_success",
                tool_name=tool_name,
                latency_ms=latency_ms,
                trace_id=trace_id
            )

            return response.result

        except asyncio.TimeoutError:
            self.circuit_breaker.record_failure(tool_name)
            latency_ms = (time.time() - start_time) * 1000

            # Log timeout (OpenTelemetry)
            logger.error(
                "mcp_tool_call_timeout",
                tool_name=tool_name,
                timeout_seconds=self.config.timeout_seconds,
                latency_ms=latency_ms,
                trace_id=trace_id
            )

            # Kill runaway server (handled by sandbox layer)
            # See ADR-0033c for Process sandbox kill

            raise TimeoutError(
                f"Tool {tool_name} exceeded timeout "
                f"({self.config.timeout_seconds}s)"
            )

    async def shutdown(self):
        """Shutdown MCP server gracefully"""
        try:
            request = JsonRpcRequest(
                method="shutdown",
                params={}
            )

            await asyncio.wait_for(
                self._send_request(request),
                timeout=5.0
            )
        except asyncio.TimeoutError:
            logger.warning("MCP shutdown request timed out")

    async def _send_request(self, request: JsonRpcRequest) -> JsonRpcResponse:
        """
        Send JSON-RPC request to MCP server.

        Transport is abstracted (stdio or HTTP).
        """
        if self.config.transport == TransportType.STDIO:
            return await self._send_stdio_request(request)
        elif self.config.transport == TransportType.HTTP:
            return await self._send_http_request(request)
        else:
            raise ValueError(f"Unknown transport: {self.config.transport}")

    async def _send_stdio_request(
        self,
        request: JsonRpcRequest
    ) -> JsonRpcResponse:
        """
        Send JSON-RPC request via stdio (stdin/stdout pipes).

        Used for process-based MCP servers (70% of tools).
        """
        # Serialize request
        request_json = json.dumps({
            "jsonrpc": request.jsonrpc,
            "id": request.id,
            "method": request.method,
            "params": request.params
        })

        # Write to stdin (one line = one request)
        self.process.stdin.write(request_json.encode() + b"\n")
        await self.process.stdin.drain()

        # Read from stdout (one line = one response)
        response_line = await self.process.stdout.readline()
        response_data = json.loads(response_line.decode())

        # Parse response
        return JsonRpcResponse(
            jsonrpc=response_data["jsonrpc"],
            id=response_data["id"],
            result=response_data.get("result"),
            error=response_data.get("error")
        )

    async def _send_http_request(
        self,
        request: JsonRpcRequest
    ) -> JsonRpcResponse:
        """
        Send JSON-RPC request via HTTP POST.

        Used for WASM/remote MCP servers (10% of tools).
        """
        import aiohttp

        url = f"http://localhost:{self.config.port}/jsonrpc"

        request_json = {
            "jsonrpc": request.jsonrpc,
            "id": request.id,
            "method": request.method,
            "params": request.params
        }

        async with aiohttp.ClientSession() as session:
            async with session.post(url, json=request_json) as resp:
                response_data = await resp.json()

        # Parse response
        return JsonRpcResponse(
            jsonrpc=response_data["jsonrpc"],
            id=response_data["id"],
            result=response_data.get("result"),
            error=response_data.get("error")
        )


class CircuitBreakerOpenError(Exception):
    """Raised when circuit breaker is OPEN"""
    pass
```

---

### Circuit Breaker Integration

```python
from dataclasses import dataclass
from typing import Dict
from enum import Enum
import time

class CircuitState(Enum):
    """Circuit breaker states"""
    CLOSED = "closed"    # Normal operation
    OPEN = "open"        # Failing, reject requests
    HALF_OPEN = "half_open"  # Testing recovery

@dataclass
class CircuitConfig:
    """Circuit breaker configuration"""
    failure_threshold: int = 5      # 5 failures → OPEN
    timeout_seconds: int = 30       # OPEN for 30s
    half_open_attempts: int = 1     # 1 test request

class CircuitBreaker:
    """
    Circuit breaker for MCP tools (prevent cascading failures).

    Research: Circuit Breaker Pattern (Nygard 2007)
    """

    def __init__(self, config: CircuitConfig):
        """Initialize circuit breaker"""
        self.config = config
        self.state: Dict[str, CircuitState] = {}
        self.failure_count: Dict[str, int] = {}
        self.last_failure_time: Dict[str, float] = {}
        self.circuit_open_time: Dict[str, float] = {}

    def allow_request(self, tool_name: str) -> bool:
        """
        Check if circuit breaker allows request.

        Returns:
            bool: True if request allowed, False if OPEN
        """
        state = self.state.get(tool_name, CircuitState.CLOSED)

        if state == CircuitState.CLOSED:
            return True

        elif state == CircuitState.OPEN:
            # Check if timeout elapsed
            open_time = self.circuit_open_time.get(tool_name, 0)
            if time.time() - open_time >= self.config.timeout_seconds:
                # Transition to HALF_OPEN (test recovery)
                self.state[tool_name] = CircuitState.HALF_OPEN
                logger.info(
                    "circuit_breaker_half_open",
                    tool_name=tool_name
                )
                return True
            else:
                # Still OPEN, reject request
                return False

        elif state == CircuitState.HALF_OPEN:
            # Allow test request
            return True

        return False

    def record_success(self, tool_name: str):
        """
        Record tool success.

        If HALF_OPEN, transition to CLOSED (recovery successful).
        """
        state = self.state.get(tool_name, CircuitState.CLOSED)

        if state == CircuitState.HALF_OPEN:
            # Test succeeded, close circuit
            self.state[tool_name] = CircuitState.CLOSED
            self.failure_count[tool_name] = 0
            logger.info(
                "circuit_breaker_closed",
                tool_name=tool_name,
                reason="test_success"
            )

    def record_failure(self, tool_name: str):
        """
        Record tool failure.

        If threshold exceeded, transition to OPEN.
        If HALF_OPEN, transition back to OPEN (test failed).
        """
        state = self.state.get(tool_name, CircuitState.CLOSED)

        if state == CircuitState.CLOSED:
            # Increment failure count
            self.failure_count[tool_name] = \
                self.failure_count.get(tool_name, 0) + 1
            self.last_failure_time[tool_name] = time.time()

            # Check if threshold exceeded
            if self.failure_count[tool_name] >= self.config.failure_threshold:
                # Transition to OPEN
                self.state[tool_name] = CircuitState.OPEN
                self.circuit_open_time[tool_name] = time.time()
                logger.warning(
                    "circuit_breaker_open",
                    tool_name=tool_name,
                    failure_count=self.failure_count[tool_name]
                )

        elif state == CircuitState.HALF_OPEN:
            # Test failed, back to OPEN
            self.state[tool_name] = CircuitState.OPEN
            self.circuit_open_time[tool_name] = time.time()
            logger.warning(
                "circuit_breaker_open",
                tool_name=tool_name,
                reason="test_failure"
            )
```

---

### Tool Registry Configuration

```yaml
# k1/config/tool_registry.yml
tool_registry:
  tools:
    # MCP + Process Sandbox (70% of tools)
    - name: "weather_api"
      description: "Fetch weather data from OpenWeatherMap"
      band: AMBER
      # Layer 1 - Protocol (This ADR)
      protocol: "mcp"
      mcp_config:
        server_path: "/opt/familyos/mcp_servers/weather_api.py"
        transport: "stdio"
        timeout_seconds: 30
      # Layer 2 - Sandbox (ADR-0033c)
      sandbox: "process"
      sandbox_fallback: "wasm"

    # MCP + WASM Sandbox (10% of tools)
    - name: "user_plugin"
      description: "User-submitted plugin (untrusted)"
      band: GREEN
      # Layer 1 - Protocol (This ADR)
      protocol: "mcp"
      mcp_config:
        server_path: "/opt/familyos/mcp_servers/user_plugin.wasm"
        transport: "http"  # WASM uses HTTP transport
        port: 8001
        timeout_seconds: 10
      # Layer 2 - Sandbox (ADR-0033b)
      sandbox: "wasm"
      sandbox_fallback: "process"

    # MCP + Container Sandbox (<1% of tools)
    - name: "high_risk_tool"
      description: "High-risk operation requiring hardware isolation"
      band: RED
      # Layer 1 - Protocol (This ADR)
      protocol: "mcp"
      mcp_config:
        server_path: "/opt/familyos/mcp_servers/high_risk.py"
        transport: "stdio"
        timeout_seconds: 60
      # Layer 2 - Sandbox (ADR-0033)
      sandbox: "container"  # Firecracker microVM
      sandbox_fallback: null  # No fallback for RED band
```

---

## Performance Analysis

### Scenario 1: MCP + Process (stdio, 70% of tools)

**Configuration:**
- Tool: weather_api
- Transport: stdio (JSON-RPC over stdin/stdout)
- Timeout: 30s

**Performance Breakdown:**
- MCP protocol overhead: 10ms (JSON serialization + stdio I/O)
- Tool execution: 200ms (external API call)
- **Total latency: 210ms ✅**

**Overhead:** 10ms (MCP) vs 200ms (actual work) = 5% overhead ✅

---

### Scenario 2: MCP + WASM (HTTP, 10% of tools)

**Configuration:**
- Tool: user_plugin
- Transport: HTTP (JSON-RPC over POST)
- Timeout: 10s

**Performance Breakdown:**
- HTTP connection: 20ms (TCP handshake)
- MCP protocol overhead: 15ms (JSON + HTTP)
- Tool execution: 150ms (WASM 10x slower)
- **Total latency: 185ms ✅**

**Overhead:** 35ms (MCP + HTTP) vs 150ms (WASM work) = 23% overhead ✅

---

### Scenario 3: Timeout Enforcement

**Configuration:**
- Tool: infinite_loop
- Transport: stdio
- Timeout: 5s

**Execution:**
1. MCPClient sends tools/call request (5ms)
2. Tool enters infinite loop (never responds)
3. asyncio.wait_for triggers timeout (5000ms)
4. MCPClient raises TimeoutError
5. Sandbox layer kills process (see ADR-0033c)
6. **Total time: 5005ms ✅ (timeout enforced)**

**Result:** K1 continues running, tool killed by sandbox ✅

---

### Scenario 4: Circuit Breaker (Repeated Failures)

**Configuration:**
- Tool: flaky_api (fails 80% of requests)
- Failure threshold: 5 failures
- Timeout: 30s

**Execution:**
1. Request 1-5: Fail (circuit: CLOSED)
2. Request 5: 5th failure → Circuit OPEN
3. Request 6: Rejected immediately (circuit OPEN, no execution)
4. Wait 30s (cooldown)
5. Request 7: Test (circuit HALF_OPEN)
6. If success → Circuit CLOSED, if failure → Circuit OPEN (30s cooldown)

**Result:** Fail fast, prevent cascading failures ✅

---

## Monitoring & Observability

### Prometheus Metrics

```python
from prometheus_client import Counter, Histogram, Gauge

# Tool executions
k1_mcp_tool_executions_total = Counter(
    "k1_mcp_tool_executions_total",
    "Total MCP tool executions",
    ["tool_name", "status"]  # success | timeout | error
)

# Tool latency (MCP protocol overhead only)
k1_mcp_protocol_latency_ms = Histogram(
    "k1_mcp_protocol_latency_ms",
    "MCP protocol overhead in milliseconds",
    ["tool_name", "transport"],  # stdio | http
    buckets=[1, 5, 10, 25, 50, 100]
)

# Circuit breaker state
k1_mcp_circuit_breaker_state = Gauge(
    "k1_mcp_circuit_breaker_state",
    "Circuit breaker state (0=CLOSED, 1=OPEN, 2=HALF_OPEN)",
    ["tool_name"]
)

# MCP transport usage
k1_mcp_transport_total = Counter(
    "k1_mcp_transport_total",
    "MCP transport usage",
    ["transport"]  # stdio | http
)
```

### OpenTelemetry Tracing

```python
from opentelemetry import trace

tracer = trace.get_tracer(__name__)

async def call_tool(self, tool_name: str, arguments: Dict, trace_id: str):
    """Call tool with distributed tracing"""
    with tracer.start_as_current_span(
        "mcp_tool_call",
        attributes={
            "tool.name": tool_name,
            "protocol.type": "mcp",
            "transport.type": self.config.transport.value,
            "cognitive.trace_id": trace_id
        }
    ) as span:
        # Send tools/call request
        result = await self._call_tool_internal(tool_name, arguments)

        # Record latency
        span.set_attribute("tool.latency_ms", result.latency_ms)
        span.set_attribute("tool.status", "success")

        return result
```

---

## Testing Strategy

### Unit Tests (WARD Framework)

```python
from ward import test
import asyncio

@test("MCPClient initializes successfully")
async def _():
    config = MCPServerConfig(
        server_path="/opt/familyos/mcp_servers/weather_api.py",
        transport=TransportType.STDIO,
        timeout_seconds=30
    )
    circuit_breaker = CircuitBreaker(CircuitConfig())
    client = MCPClient(config, circuit_breaker)

    # Initialize
    result = await client.initialize()

    assert result["protocolVersion"] == "2024-11-05"
    assert "capabilities" in result

@test("MCPClient lists tools")
async def _():
    config = MCPServerConfig(
        server_path="/opt/familyos/mcp_servers/weather_api.py",
        transport=TransportType.STDIO,
        timeout_seconds=30
    )
    circuit_breaker = CircuitBreaker(CircuitConfig())
    client = MCPClient(config, circuit_breaker)

    await client.initialize()
    tools = await client.list_tools()

    assert len(tools) > 0
    assert tools[0]["name"] == "get_weather"
    assert "inputSchema" in tools[0]

@test("MCPClient enforces timeout")
async def _():
    config = MCPServerConfig(
        server_path="/opt/familyos/mcp_servers/infinite_loop.py",
        transport=TransportType.STDIO,
        timeout_seconds=1  # 1 second timeout
    )
    circuit_breaker = CircuitBreaker(CircuitConfig())
    client = MCPClient(config, circuit_breaker)

    await client.initialize()

    # Should timeout
    with raises(TimeoutError):
        await client.call_tool("infinite_loop", {}, "trace_123")

@test("Circuit breaker opens after repeated failures")
async def _():
    config = MCPServerConfig(
        server_path="/opt/familyos/mcp_servers/flaky_api.py",
        transport=TransportType.STDIO,
        timeout_seconds=30
    )
    circuit_config = CircuitConfig(failure_threshold=3)
    circuit_breaker = CircuitBreaker(circuit_config)
    client = MCPClient(config, circuit_breaker)

    await client.initialize()

    # Trigger 3 failures
    for i in range(3):
        try:
            await client.call_tool("fail_always", {}, f"trace_{i}")
        except RuntimeError:
            pass

    # Circuit should be OPEN
    assert not circuit_breaker.allow_request("fail_always")

    # Next request should fail immediately
    with raises(CircuitBreakerOpenError):
        await client.call_tool("fail_always", {}, "trace_4")
```

### Integration Tests

```python
@test("MCP + Process Sandbox integration")
async def _():
    """
    Test MCP protocol with Process sandbox (Layer 2).

    See ADR-0033c for Process sandbox implementation.
    """
    # This test validates that MCPClient (Layer 1) works
    # correctly with ProcessSandbox (Layer 2)

    config = MCPServerConfig(
        server_path="/opt/familyos/mcp_servers/weather_api.py",
        transport=TransportType.STDIO,
        timeout_seconds=30
    )
    circuit_breaker = CircuitBreaker(CircuitConfig())
    client = MCPClient(config, circuit_breaker)

    await client.initialize()

    # Call tool (executed in Process sandbox)
    result = await client.call_tool(
        "get_weather",
        {"city": "Seattle"},
        "trace_123"
    )

    assert "temperature" in result
    assert "city" in result

@test("MCP + WASM Sandbox integration")
async def _():
    """
    Test MCP protocol with WASM sandbox (Layer 2).

    See ADR-0033b for WASM sandbox implementation.
    """
    # This test validates that MCPClient (Layer 1) works
    # correctly with WASMSandbox (Layer 2)

    config = MCPServerConfig(
        server_path="/opt/familyos/mcp_servers/user_plugin.wasm",
        transport=TransportType.HTTP,
        port=8001,
        timeout_seconds=10
    )
    circuit_breaker = CircuitBreaker(CircuitConfig())
    client = MCPClient(config, circuit_breaker)

    await client.initialize()

    # Call tool (executed in WASM sandbox)
    result = await client.call_tool(
        "process_data",
        {"input": "test"},
        "trace_456"
    )

    assert "output" in result
```

---

## Dependencies

### Required

- **Python 3.10+** (asyncio, subprocess)
- **aiohttp** (for HTTP transport)
- **Prometheus client** (for metrics)
- **OpenTelemetry** (for tracing)

### Layer 2 Dependencies

- **ADR-0033b:** WASM Sandbox (for MCP+WASM combination)
- **ADR-0033c:** Process Sandbox (for MCP+Process combination)
- **ADR-0033:** Container Sandbox (for MCP+Container combination)

---

## Implementation Timeline

### Phase 1: JSON-RPC 2.0 Implementation (Days 1-2)

**Deliverables:**
- JsonRpcRequest/JsonRpcResponse dataclasses
- JSON serialization/deserialization
- Error code constants
- Unit tests (95% coverage)

**Validation:**
- JSON-RPC 2.0 spec compliance
- Error codes match specification

---

### Phase 2: MCPClient (stdio transport) (Days 3-4)

**Deliverables:**
- MCPClient class with stdio transport
- initialize, list_tools, call_tool, shutdown methods
- Timeout enforcement with asyncio.wait_for
- Unit tests

**Validation:**
- Stdio communication works (stdin/stdout pipes)
- Timeout kills runaway tools
- Integration with weather_api.py (MCP+Process)

---

### Phase 3: MCPClient (HTTP transport) (Day 5)

**Deliverables:**
- HTTP transport implementation
- aiohttp integration
- Port management
- Unit tests

**Validation:**
- HTTP communication works (JSON-RPC over POST)
- Integration with user_plugin.wasm (MCP+WASM)

---

### Phase 4: Circuit Breaker Integration (Day 6)

**Deliverables:**
- CircuitBreaker class
- CLOSED/OPEN/HALF_OPEN state machine
- Failure threshold and cooldown
- Unit tests

**Validation:**
- Circuit opens after 5 failures
- Circuit tests recovery after 30s
- Circuit closes on successful test

---

### Phase 5: Observability (Day 7)

**Deliverables:**
- Prometheus metrics
- OpenTelemetry tracing
- Structured logging
- Grafana dashboard

**Validation:**
- Metrics exported to Prometheus
- Traces appear in Jaeger/Zipkin
- Logs include cognitive_trace_id

---

**Total Duration:** 7 days (1 week)

---

## Success Criteria

1. **JSON-RPC 2.0 Compliance:**
   - All requests/responses match specification
   - Standard error codes used

2. **Transport Flexibility:**
   - stdio transport works (70% of tools)
   - HTTP transport works (10% of tools)

3. **Timeout Enforcement:**
   - Tools exceeding timeout are killed
   - <50ms protocol overhead

4. **Circuit Breaker:**
   - Opens after threshold failures
   - Tests recovery after cooldown
   - Closes on successful recovery

5. **Layer Independence:**
   - MCPClient works with ANY sandbox (WASM, Process, Container)
   - No coupling between protocol and sandbox

6. **Observability:**
   - 100% of tool calls emit metrics
   - 100% of tool calls traced
   - All errors logged with context

7. **Test Coverage:**
   - 95% unit test coverage
   - Integration tests with all sandboxes

---

## References

1. **Model Context Protocol (MCP) — Anthropic, 2024**
   - Specification: https://modelcontextprotocol.io/specification/2025-06-18

2. **JSON-RPC 2.0 — 2010**
   - Specification: https://www.jsonrpc.org/specification

3. **Circuit Breaker Pattern — Michael Nygard, 2007**
   - Book: "Release It!"

4. **ADR-0033 — Tool Execution Architecture**
   - 2-layer architecture: Protocol × Sandbox

5. **ADR-0034 — MCP Protocol for Tool Integration**
   - MCP adoption rationale, industry standard

---

## Glossary

- **MCP:** Model Context Protocol (Anthropic 2024) - JSON-RPC 2.0 based protocol
- **JSON-RPC:** Remote procedure call protocol using JSON
- **Layer 1:** Protocol layer (HOW tools are invoked) - this ADR
- **Layer 2:** Sandbox layer (WHERE tools execute) - ADR-0033b/c
- **Transport:** Communication mechanism (stdio or HTTP)
- **Circuit Breaker:** Resilience pattern to prevent cascading failures

---

**Status:** ✅ COMPLETE (Layer 1 - Protocol Implementation)

**Next:** ADR-0033b (WASM Sandbox - Layer 2) + ADR-0033c (Process Sandbox - Layer 2)
