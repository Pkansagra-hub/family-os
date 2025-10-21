# ADR-0034b: MCP Process Lifecycle & Timeout Enforcement

**Status:** ⏳ Pending Implementation
**Date:** 2025-10-13
**Authors:** K1 Architecture Team
**Parent ADR:** ADR-0034 (MCP Protocol for Tool Integration)
**Priority:** ⭐⭐⭐ CRITICAL
**Estimated Effort:** 8 weeks

---

## Context

**Parent Problem:** ADR-0034 defines MCP protocol with 98% crash isolation (tool crash ≠ K1 crash). This sub-ADR focuses on **MCP server process lifecycle management** - spawning, monitoring, timeout enforcement, and graceful shutdown.

**Why Process Lifecycle Management?**
- **Crash isolation:** Each MCP server runs in separate process (separate PID, no shared memory)
- **Timeout enforcement:** K1 kills runaway tool after configurable timeout (5s for calculator, 300s for video)
- **Resource cleanup:** Graceful shutdown closes connections, flushes logs, releases resources
- **State tracking:** Lifecycle FSM tracks process state (SPAWNING → RUNNING → TERMINATING → TERMINATED)

**Current Challenge:** Without process lifecycle management:
- No timeout enforcement (runaway tool blocks K1 indefinitely)
- No graceful shutdown (tool process orphaned, resources leaked)
- No crash detection (tool crash = silent failure, no K1 notification)
- No restart logic (crashed tool not automatically restarted)

**Real-World Impact:**
```
Tool: video_transcoder (no timeout enforcement)
K1 starts process: PID 12345
Tool enters infinite loop (bug in transcoding algorithm)
K1 waits forever (blocking user session)
Problem: No timeout → No kill → User stuck
```

**Desired Behavior (With Process Lifecycle):**
```
Tool: video_transcoder (timeout: 300s)
K1 starts process: PID 12345 (SPAWNING → RUNNING)
Tool enters infinite loop (bug)
K1 detects timeout after 300s
K1 sends SIGTERM → waits 5s → sends SIGKILL (TERMINATING)
Process killed, K1 continues (TERMINATED)
User notified: "Video transcoding timed out"
Problem: ✅ Timeout enforced, K1 remains responsive
```

---

## Decision

**We will implement MCP server process lifecycle management with state tracking (FSM), configurable timeout enforcement (per tool), and graceful shutdown (SIGTERM → 5s → SIGKILL).**

### Core Principles

1. **Lifecycle FSM (5 States):**
   - **SPAWNING:** Process starting (subprocess.Popen called, waiting for initialize)
   - **RUNNING:** Process healthy (initialized, ready for tools/call)
   - **TERMINATING:** Graceful shutdown initiated (SIGTERM sent, waiting for exit)
   - **TERMINATED:** Process exited (exit code available)
   - **CRASHED:** Process died unexpectedly (non-zero exit, signal)

2. **Timeout Enforcement:**
   - Per-tool timeout configuration (calculator: 5s, video: 300s, default: 30s)
   - Timeout tracked per tools/call request (not process uptime)
   - asyncio.wait_for wraps request execution
   - On timeout: SIGTERM → 5s wait → SIGKILL

3. **Graceful Shutdown:**
   - K1 sends `shutdown` JSON-RPC request (MCP protocol)
   - Server has 5s to close connections, flush logs, cleanup
   - If not exited after 5s: SIGTERM (interrupt signal)
   - If not exited after another 5s: SIGKILL (force kill)

4. **Crash Detection:**
   - Monitor process exit code (0 = clean exit, non-zero = error)
   - Monitor signals (SIGSEGV, SIGABRT = crash)
   - Emit crash event to K1 (supervisor notified)

5. **Resource Cleanup:**
   - Close stdin/stdout pipes (prevent PIPE buffer leaks)
   - Wait for process to exit (prevent zombies)
   - Release file descriptors

---

## Implementation

### Lifecycle FSM

```python
from enum import Enum
from dataclasses import dataclass
import time

class ProcessState(Enum):
    """MCP server process lifecycle states"""
    SPAWNING = "SPAWNING"        # Starting process
    RUNNING = "RUNNING"          # Healthy, ready for requests
    TERMINATING = "TERMINATING"  # Graceful shutdown in progress
    TERMINATED = "TERMINATED"    # Process exited cleanly
    CRASHED = "CRASHED"          # Process crashed (non-zero exit/signal)

@dataclass
class ProcessInfo:
    """MCP server process information"""
    pid: int
    state: ProcessState
    started_at: float          # Timestamp when process spawned
    terminated_at: float = 0   # Timestamp when process terminated
    exit_code: int = None      # Process exit code (0=success)
    signal: int = None         # Signal that killed process (SIGTERM, SIGKILL)
    total_requests: int = 0    # Total tools/call requests handled
    total_timeouts: int = 0    # Total requests that timed out

    def uptime_seconds(self) -> float:
        """Calculate process uptime"""
        if self.state in (ProcessState.TERMINATED, ProcessState.CRASHED):
            return self.terminated_at - self.started_at
        return time.time() - self.started_at

    def is_alive(self) -> bool:
        """Check if process is alive"""
        return self.state in (ProcessState.SPAWNING, ProcessState.RUNNING, ProcessState.TERMINATING)
```

---

### Process Spawner

```python
import asyncio
import signal
from typing import Optional

class MCPProcessSpawner:
    """
    Spawn and manage MCP server processes.

    Responsibilities:
    - Spawn subprocess (asyncio.create_subprocess_exec)
    - Track process state (lifecycle FSM)
    - Monitor process exit (wait_closed task)
    - Enforce timeout (asyncio.wait_for)
    - Graceful shutdown (SIGTERM → SIGKILL)
    """

    def __init__(self, server_path: str, timeout_seconds: int = 30):
        """
        Initialize process spawner.

        Args:
            server_path: Path to MCP server executable (e.g., "/opt/familyos/mcp_servers/weather_api.py")
            timeout_seconds: Default timeout for tools/call requests
        """
        self.server_path = server_path
        self.timeout_seconds = timeout_seconds

        self.process: Optional[asyncio.subprocess.Process] = None
        self.info: Optional[ProcessInfo] = None
        self.monitor_task: Optional[asyncio.Task] = None

    async def spawn(self) -> ProcessInfo:
        """
        Spawn MCP server process.

        Returns:
            ProcessInfo: Process information (PID, state)

        Raises:
            RuntimeError: If process fails to start
        """
        # Spawn subprocess
        self.process = await asyncio.create_subprocess_exec(
            "python3", self.server_path,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )

        # Initialize process info
        self.info = ProcessInfo(
            pid=self.process.pid,
            state=ProcessState.SPAWNING,
            started_at=time.time()
        )

        # Start background monitor
        self.monitor_task = asyncio.create_task(self._monitor_process())

        print(f"[MCPProcessSpawner] Spawned MCP server: PID {self.process.pid}, path {self.server_path}")

        return self.info

    async def wait_for_ready(self, timeout: float = 5.0):
        """
        Wait for MCP server to initialize (SPAWNING → RUNNING).

        Sends 'initialize' request and waits for response.

        Args:
            timeout: Max time to wait for initialization

        Raises:
            TimeoutError: If initialization exceeds timeout
            RuntimeError: If process crashes during initialization
        """
        from .jsonrpc import MCPClient, TransportType

        # Create JSON-RPC client
        client = MCPClient(TransportType.STDIO, process=self.process)

        try:
            # Send initialize request with timeout
            server_info = await asyncio.wait_for(
                client.initialize(),
                timeout=timeout
            )

            # Transition to RUNNING
            self.info.state = ProcessState.RUNNING

            print(f"[MCPProcessSpawner] MCP server ready: {server_info}")

        except asyncio.TimeoutError:
            # Kill process on initialization timeout
            await self.kill()
            raise TimeoutError(f"MCP server initialization timed out after {timeout}s")

        except Exception as e:
            # Kill process on initialization error
            await self.kill()
            raise RuntimeError(f"MCP server initialization failed: {e}")

    async def terminate(self, timeout: float = 5.0):
        """
        Gracefully terminate MCP server process.

        Shutdown sequence:
        1. Send 'shutdown' JSON-RPC request (graceful)
        2. Wait up to 5s for process to exit
        3. If not exited: send SIGTERM (interrupt)
        4. Wait up to 5s for process to exit
        5. If not exited: send SIGKILL (force kill)

        Args:
            timeout: Max time to wait for graceful shutdown
        """
        if not self.process or not self.info.is_alive():
            return

        # Transition to TERMINATING
        self.info.state = ProcessState.TERMINATING

        print(f"[MCPProcessSpawner] Terminating MCP server PID {self.process.pid}")

        # Step 1: Send 'shutdown' JSON-RPC request
        try:
            from .jsonrpc import MCPClient, TransportType
            client = MCPClient(TransportType.STDIO, process=self.process)
            await asyncio.wait_for(client.shutdown(), timeout=2.0)
        except:
            pass  # Ignore errors (server may already be dead)

        # Step 2: Wait for process to exit gracefully
        try:
            await asyncio.wait_for(self.process.wait(), timeout=timeout)
            print(f"[MCPProcessSpawner] MCP server exited gracefully: PID {self.process.pid}")
            self.info.state = ProcessState.TERMINATED
            self.info.terminated_at = time.time()
            self.info.exit_code = self.process.returncode
            return
        except asyncio.TimeoutError:
            pass  # Proceed to SIGTERM

        # Step 3: Send SIGTERM (interrupt signal)
        print(f"[MCPProcessSpawner] Sending SIGTERM to MCP server PID {self.process.pid}")
        self.process.send_signal(signal.SIGTERM)

        # Wait for process to exit
        try:
            await asyncio.wait_for(self.process.wait(), timeout=timeout)
            print(f"[MCPProcessSpawner] MCP server exited after SIGTERM: PID {self.process.pid}")
            self.info.state = ProcessState.TERMINATED
            self.info.terminated_at = time.time()
            self.info.exit_code = self.process.returncode
            self.info.signal = signal.SIGTERM
            return
        except asyncio.TimeoutError:
            pass  # Proceed to SIGKILL

        # Step 4: Send SIGKILL (force kill)
        print(f"[MCPProcessSpawner] Sending SIGKILL to MCP server PID {self.process.pid}")
        self.process.kill()

        # Wait for process to exit (should always succeed)
        await self.process.wait()
        print(f"[MCPProcessSpawner] MCP server killed: PID {self.process.pid}")
        self.info.state = ProcessState.TERMINATED
        self.info.terminated_at = time.time()
        self.info.exit_code = self.process.returncode
        self.info.signal = signal.SIGKILL

    async def kill(self):
        """
        Immediately kill MCP server process (SIGKILL).

        Use this for timeout enforcement, not graceful shutdown.
        """
        if not self.process or not self.info.is_alive():
            return

        print(f"[MCPProcessSpawner] Killing MCP server PID {self.process.pid}")
        self.process.kill()
        await self.process.wait()

        self.info.state = ProcessState.TERMINATED
        self.info.terminated_at = time.time()
        self.info.exit_code = self.process.returncode
        self.info.signal = signal.SIGKILL

    async def _monitor_process(self):
        """
        Background task: monitor process exit.

        Detects crashes (non-zero exit, signals).
        """
        exit_code = await self.process.wait()

        # Check if already terminated by K1
        if self.info.state == ProcessState.TERMINATING:
            return

        # Unexpected exit (crash)
        self.info.state = ProcessState.CRASHED
        self.info.terminated_at = time.time()
        self.info.exit_code = exit_code

        if exit_code < 0:
            # Killed by signal
            self.info.signal = -exit_code
            print(f"[MCPProcessSpawner] MCP server crashed (signal {-exit_code}): PID {self.process.pid}")
        else:
            # Non-zero exit code
            print(f"[MCPProcessSpawner] MCP server crashed (exit code {exit_code}): PID {self.process.pid}")

        # Emit crash event
        await self._emit_crash_event()

    async def _emit_crash_event(self):
        """Emit crash event to K1 supervisor"""
        # TODO: Integrate with supervisor (ADR-0002b)
        print(f"[MCPProcessSpawner] Crash event: PID {self.process.pid}, exit_code {self.info.exit_code}")
```

---

### Timeout Enforcer

```python
class TimeoutEnforcer:
    """
    Enforce timeout for MCP tools/call requests.

    Wraps asyncio.wait_for for timeout enforcement.
    On timeout: kills MCP server process.
    """

    def __init__(self, spawner: MCPProcessSpawner):
        """
        Initialize timeout enforcer.

        Args:
            spawner: MCP process spawner (for killing process)
        """
        self.spawner = spawner

    async def call_tool_with_timeout(
        self,
        client,
        tool_name: str,
        arguments: dict,
        timeout: float = None
    ) -> dict:
        """
        Call tool with timeout enforcement.

        Args:
            client: MCPClient instance
            tool_name: Tool name
            arguments: Tool arguments
            timeout: Timeout in seconds (None = use spawner default)

        Returns:
            dict: Tool result

        Raises:
            TimeoutError: If tool exceeds timeout (process killed)
            JsonRpcError: If tool returns error
        """
        if timeout is None:
            timeout = self.spawner.timeout_seconds

        # Track request
        self.spawner.info.total_requests += 1

        start = time.time()
        try:
            # Execute with timeout
            result = await asyncio.wait_for(
                client.call_tool(tool_name, arguments),
                timeout=timeout
            )

            # Success
            latency_ms = (time.time() - start) * 1000
            print(f"[TimeoutEnforcer] Tool {tool_name} completed in {latency_ms:.1f}ms")

            return result

        except asyncio.TimeoutError:
            # Timeout: kill process
            self.spawner.info.total_timeouts += 1

            print(f"[TimeoutEnforcer] Tool {tool_name} timed out after {timeout}s, killing process PID {self.spawner.process.pid}")

            await self.spawner.kill()

            raise TimeoutError(f"Tool {tool_name} timed out after {timeout}s")
```

---

### Lifecycle Manager (Full Integration)

```python
class MCPLifecycleManager:
    """
    Full MCP server lifecycle management.

    Combines:
    - Process spawning (MCPProcessSpawner)
    - JSON-RPC client (MCPClient)
    - Timeout enforcement (TimeoutEnforcer)
    - Graceful shutdown

    Usage:
        manager = MCPLifecycleManager("/path/to/mcp_server.py", timeout=30)
        await manager.start()
        result = await manager.call_tool("get_weather", {"city": "Seattle"})
        await manager.stop()
    """

    def __init__(self, server_path: str, timeout_seconds: int = 30):
        """
        Initialize lifecycle manager.

        Args:
            server_path: Path to MCP server executable
            timeout_seconds: Default timeout for tools/call
        """
        self.server_path = server_path
        self.timeout_seconds = timeout_seconds

        self.spawner: Optional[MCPProcessSpawner] = None
        self.client: Optional[MCPClient] = None
        self.enforcer: Optional[TimeoutEnforcer] = None

    async def start(self):
        """
        Start MCP server lifecycle.

        Sequence:
        1. Spawn process (SPAWNING)
        2. Wait for initialization (RUNNING)
        3. Create JSON-RPC client
        4. Create timeout enforcer
        """
        # Spawn process
        self.spawner = MCPProcessSpawner(self.server_path, self.timeout_seconds)
        await self.spawner.spawn()

        # Wait for initialization
        await self.spawner.wait_for_ready(timeout=5.0)

        # Create JSON-RPC client
        from .jsonrpc import MCPClient, TransportType
        self.client = MCPClient(TransportType.STDIO, process=self.spawner.process)

        # Create timeout enforcer
        self.enforcer = TimeoutEnforcer(self.spawner)

        print(f"[MCPLifecycleManager] MCP server started: {self.server_path}")

    async def call_tool(self, tool_name: str, arguments: dict, timeout: float = None) -> dict:
        """
        Call tool with timeout enforcement.

        Args:
            tool_name: Tool name
            arguments: Tool arguments
            timeout: Timeout (None = use default)

        Returns:
            dict: Tool result

        Raises:
            TimeoutError: If tool times out
            JsonRpcError: If tool returns error
            RuntimeError: If lifecycle not started
        """
        if not self.enforcer:
            raise RuntimeError("Lifecycle not started (call start() first)")

        return await self.enforcer.call_tool_with_timeout(
            self.client,
            tool_name,
            arguments,
            timeout=timeout
        )

    async def stop(self):
        """
        Stop MCP server lifecycle.

        Graceful shutdown sequence:
        1. Send 'shutdown' JSON-RPC request
        2. Wait 5s for graceful exit
        3. SIGTERM → wait 5s
        4. SIGKILL (force kill)
        """
        if self.spawner:
            await self.spawner.terminate(timeout=5.0)
            print(f"[MCPLifecycleManager] MCP server stopped: {self.server_path}")

    def get_info(self) -> ProcessInfo:
        """Get process information"""
        if not self.spawner:
            raise RuntimeError("Lifecycle not started")
        return self.spawner.info
```

---

### Per-Tool Timeout Configuration

```yaml
# k1/config/tool_timeouts.yml
tool_timeouts:
  # Fast tools (5-10s)
  calculator: 5
  unit_converter: 5
  text_search: 10

  # Medium tools (30-60s)
  weather_api: 30
  web_search: 30
  calendar_sync: 60

  # Slow tools (120-300s)
  video_transcoder: 300
  image_processor: 120
  llm_inference: 120

  # Default timeout (if tool not specified)
  default: 30
```

```python
import yaml

class TimeoutConfig:
    """Load per-tool timeout configuration"""

    def __init__(self, config_path: str = "k1/config/tool_timeouts.yml"):
        with open(config_path) as f:
            data = yaml.safe_load(f)

        self.timeouts: dict[str, int] = data["tool_timeouts"]
        self.default_timeout: int = self.timeouts.get("default", 30)

    def get_timeout(self, tool_name: str) -> int:
        """Get timeout for tool (fallback to default)"""
        return self.timeouts.get(tool_name, self.default_timeout)

# Usage
timeout_config = TimeoutConfig()
weather_timeout = timeout_config.get_timeout("weather_api")  # 30s
video_timeout = timeout_config.get_timeout("video_transcoder")  # 300s
unknown_timeout = timeout_config.get_timeout("unknown_tool")  # 30s (default)
```

---

## Performance Analysis

### Scenario 1: Normal Tool Execution (No Timeout)

**Configuration:**
- Tool: weather_api
- Timeout: 30s
- Actual execution: 250ms

**Performance:**
- Process spawn: 30ms
- Initialize (wait_for_ready): 50ms (JSON-RPC initialize)
- tools/call execution: 250ms (actual work)
- Process termination: 20ms (graceful shutdown)
- **Total lifecycle: 350ms**

**Overhead:** 100ms (spawn + init + terminate) / 350ms = 28.5% overhead

---

### Scenario 2: Timeout Enforcement (Runaway Tool)

**Configuration:**
- Tool: infinite_loop_tool
- Timeout: 10s
- Actual execution: infinite loop (never completes)

**Performance:**
- Process spawn: 30ms
- Initialize: 50ms
- tools/call execution: 10,000ms (timeout triggered)
- Process kill: 10ms (SIGKILL immediate)
- **Total: 10,090ms (timeout enforced ✅)**

**Result:** K1 remains responsive, tool killed, user notified

---

### Scenario 3: Graceful Shutdown (Clean Exit)

**Configuration:**
- Tool: weather_api
- Shutdown sequence: shutdown JSON-RPC → wait 5s

**Performance:**
- Send 'shutdown' JSON-RPC: 5ms
- Server cleanup: 50ms (close connections, flush logs)
- Process exit: 10ms (clean exit code 0)
- **Total shutdown: 65ms ✅**

**Result:** Clean shutdown, no resource leaks

---

### Scenario 4: Force Kill (Unresponsive Server)

**Configuration:**
- Tool: hung_tool (doesn't respond to shutdown)
- Shutdown sequence: shutdown → 5s timeout → SIGTERM → 5s → SIGKILL

**Performance:**
- Send 'shutdown' JSON-RPC: 5ms (no response)
- Wait 5s: 5,000ms (timeout)
- Send SIGTERM: 5ms (no response)
- Wait 5s: 5,000ms (timeout)
- Send SIGKILL: 5ms (immediate kill)
- **Total shutdown: 10,015ms (force kill ✅)**

**Result:** Process killed, no zombies, resources released

---

## Testing Strategy (WARD Framework)

### Unit Tests

```python
from ward import test
import asyncio

@test("ProcessInfo calculates uptime correctly")
def _():
    info = ProcessInfo(
        pid=12345,
        state=ProcessState.RUNNING,
        started_at=time.time() - 10.0  # Started 10 seconds ago
    )

    uptime = info.uptime_seconds()
    assert 9.9 < uptime < 10.1  # ~10 seconds

@test("ProcessInfo detects alive processes")
def _():
    info = ProcessInfo(pid=12345, state=ProcessState.RUNNING, started_at=time.time())
    assert info.is_alive() == True

    info.state = ProcessState.TERMINATED
    assert info.is_alive() == False

@test("MCPProcessSpawner spawns subprocess")
async def _():
    spawner = MCPProcessSpawner("mock_mcp_server.py", timeout_seconds=30)
    info = await spawner.spawn()

    assert info.pid > 0
    assert info.state == ProcessState.SPAWNING

    # Cleanup
    await spawner.kill()

@test("MCPProcessSpawner waits for initialization")
async def _():
    spawner = MCPProcessSpawner("mock_mcp_server.py", timeout_seconds=30)
    await spawner.spawn()

    await spawner.wait_for_ready(timeout=5.0)

    assert spawner.info.state == ProcessState.RUNNING

    # Cleanup
    await spawner.terminate()

@test("MCPProcessSpawner terminates gracefully")
async def _():
    spawner = MCPProcessSpawner("mock_mcp_server.py", timeout_seconds=30)
    await spawner.spawn()
    await spawner.wait_for_ready()

    # Terminate
    await spawner.terminate(timeout=5.0)

    assert spawner.info.state == ProcessState.TERMINATED
    assert spawner.info.exit_code == 0

@test("TimeoutEnforcer kills process on timeout")
async def _():
    spawner = MCPProcessSpawner("mock_infinite_loop.py", timeout_seconds=1)
    await spawner.spawn()
    await spawner.wait_for_ready()

    from .jsonrpc import MCPClient, TransportType
    client = MCPClient(TransportType.STDIO, process=spawner.process)

    enforcer = TimeoutEnforcer(spawner)

    # Call tool with 1s timeout (tool runs forever)
    with raises(TimeoutError):
        await enforcer.call_tool_with_timeout(client, "infinite_loop", {}, timeout=1.0)

    # Process should be killed
    assert spawner.info.state == ProcessState.TERMINATED
    assert spawner.info.total_timeouts == 1
```

### Integration Tests

```python
@test("MCPLifecycleManager full lifecycle")
async def _():
    manager = MCPLifecycleManager("mock_mcp_server.py", timeout_seconds=30)

    # Start
    await manager.start()
    info = manager.get_info()
    assert info.state == ProcessState.RUNNING

    # Call tool
    result = await manager.call_tool("get_weather", {"city": "Seattle"})
    assert "temperature" in result

    # Stop
    await manager.stop()
    info = manager.get_info()
    assert info.state == ProcessState.TERMINATED

@test("MCPLifecycleManager enforces timeout")
async def _():
    manager = MCPLifecycleManager("mock_infinite_loop.py", timeout_seconds=1)

    await manager.start()

    # Call tool with 1s timeout
    with raises(TimeoutError):
        await manager.call_tool("infinite_loop", {}, timeout=1.0)

    # Process should be killed
    info = manager.get_info()
    assert info.state == ProcessState.TERMINATED
    assert info.total_timeouts == 1

@test("MCPLifecycleManager handles crashed server")
async def _():
    manager = MCPLifecycleManager("mock_crash_server.py", timeout_seconds=30)

    await manager.start()

    # Call tool that crashes server
    with raises(RuntimeError):
        await manager.call_tool("crash_tool", {})

    # Process should be crashed
    info = manager.get_info()
    assert info.state == ProcessState.CRASHED
    assert info.exit_code != 0
```

---

## Monitoring & Observability

### Prometheus Metrics

```python
from prometheus_client import Counter, Histogram, Gauge

# Process spawns
mcp_process_spawns_total = Counter(
    "mcp_process_spawns_total",
    "Total MCP process spawns",
    ["tool_name"]
)

# Process exits
mcp_process_exits_total = Counter(
    "mcp_process_exits_total",
    "Total MCP process exits",
    ["tool_name", "exit_reason"]  # clean | timeout | crash
)

# Process uptime
mcp_process_uptime_seconds = Histogram(
    "mcp_process_uptime_seconds",
    "MCP process uptime in seconds",
    ["tool_name"],
    buckets=[1, 10, 60, 300, 600, 1800, 3600]
)

# Timeout enforcements
mcp_timeouts_total = Counter(
    "mcp_timeouts_total",
    "Total MCP timeout enforcements",
    ["tool_name"]
)

# Graceful shutdowns
mcp_graceful_shutdowns_total = Counter(
    "mcp_graceful_shutdowns_total",
    "Total MCP graceful shutdowns",
    ["tool_name", "success"]  # success: true | false
)

# Process state
mcp_process_state = Gauge(
    "mcp_process_state",
    "MCP process state (0=SPAWNING, 1=RUNNING, 2=TERMINATING, 3=TERMINATED, 4=CRASHED)",
    ["tool_name", "pid"]
)
```

### Grafana Dashboard

```json
{
  "panels": [
    {
      "title": "MCP Process Spawns",
      "type": "graph",
      "targets": [
        {
          "expr": "rate(mcp_process_spawns_total[5m])",
          "legendFormat": "{{tool_name}}"
        }
      ]
    },
    {
      "title": "MCP Timeout Rate",
      "type": "graph",
      "targets": [
        {
          "expr": "rate(mcp_timeouts_total[5m])",
          "legendFormat": "{{tool_name}}"
        }
      ]
    },
    {
      "title": "MCP Process Uptime (P95)",
      "type": "graph",
      "targets": [
        {
          "expr": "histogram_quantile(0.95, rate(mcp_process_uptime_seconds_bucket[5m]))",
          "legendFormat": "{{tool_name}}"
        }
      ]
    },
    {
      "title": "MCP Process State",
      "type": "table",
      "targets": [
        {
          "expr": "mcp_process_state"
        }
      ]
    }
  ]
}
```

---

## Implementation Plan

### Phase 1: Lifecycle FSM (Weeks 1-2)

**Deliverables:**
- ProcessState enum (5 states)
- ProcessInfo dataclass (pid, state, timestamps, counters)
- State transition logic (SPAWNING → RUNNING → TERMINATING → TERMINATED)

**Acceptance Criteria:**
- Unit tests pass (state transitions)
- Uptime calculation correct

---

### Phase 2: Process Spawner (Weeks 2-4)

**Deliverables:**
- MCPProcessSpawner class (spawn, wait_for_ready, terminate, kill)
- Background monitor (_monitor_process for crash detection)
- Graceful shutdown sequence (shutdown → SIGTERM → SIGKILL)

**Acceptance Criteria:**
- Process spawns successfully
- Initialization timeout enforced
- Graceful shutdown works (5s → SIGTERM → 5s → SIGKILL)
- Crash detection works (non-zero exit, signals)

---

### Phase 3: Timeout Enforcer (Weeks 4-5)

**Deliverables:**
- TimeoutEnforcer class (call_tool_with_timeout)
- asyncio.wait_for integration
- Process kill on timeout

**Acceptance Criteria:**
- Timeout enforcement works (tool killed after timeout)
- Timeout counter tracked (info.total_timeouts)
- User notified of timeout

---

### Phase 4: Lifecycle Manager (Weeks 5-6)

**Deliverables:**
- MCPLifecycleManager class (start, call_tool, stop)
- Full integration (spawner + client + enforcer)
- Per-tool timeout configuration (YAML)

**Acceptance Criteria:**
- Full lifecycle works (start → call_tool → stop)
- Per-tool timeouts loaded from config
- Graceful shutdown on stop()

---

### Phase 5: Monitoring & Production (Weeks 7-8)

**Deliverables:**
- Prometheus metrics (spawns, exits, timeouts, uptime, state)
- Grafana dashboard (4 panels)
- Production documentation

**Acceptance Criteria:**
- Metrics exported correctly
- Dashboard visualizes process health
- Production deployment successful

---

## Dependencies

**Upstream (Must Complete First):**
- 0034a: JSON-RPC Protocol (MCPClient for initialize/shutdown)

**Downstream (Depends on This):**
- 0034c: Circuit Breaker (wraps lifecycle manager)
- 0034d: Error Handling (handles process crashes)

**Parallel Work:**
- Can develop in parallel with ADR-0033 sub-ADRs

---

## Success Criteria

**Functional:**
- ✅ Process spawning works (subprocess.Popen with stdio pipes)
- ✅ Initialization timeout enforced (5s default)
- ✅ Tool execution timeout enforced (per-tool config)
- ✅ Graceful shutdown works (shutdown → SIGTERM → SIGKILL)
- ✅ Crash detection works (non-zero exit, signals)

**Performance:**
- ✅ Process spawn <50ms P95
- ✅ Graceful shutdown <100ms P95 (clean exit)
- ✅ Force kill <10s (worst case: shutdown → 5s → SIGTERM → 5s → SIGKILL)
- ✅ Timeout enforcement accurate (within 100ms of timeout)

**Reliability:**
- ✅ No zombie processes (all processes waited)
- ✅ No resource leaks (pipes closed, FDs released)
- ✅ Crash isolation (tool crash ≠ K1 crash)

**Observability:**
- ✅ Prometheus metrics (6 metrics)
- ✅ Grafana dashboard (4 panels)
- ✅ Process state tracking (lifecycle FSM)

---

## References

### Research & Standards

1. **Unix Process Management**
   - fork/exec model, signals (SIGTERM, SIGKILL)
   - Zombie processes, wait() system call

2. **asyncio subprocess — Python 3.10**
   - https://docs.python.org/3/library/asyncio-subprocess.html
   - Non-blocking process spawning and management

3. **Graceful Shutdown Pattern — Martin Fowler**
   - https://martinfowler.com/articles/patterns-of-distributed-systems/graceful-shutdown.html
   - Shutdown hooks, resource cleanup

---

## Glossary

- **Process lifecycle:** Sequence of states (SPAWNING → RUNNING → TERMINATING → TERMINATED)
- **Timeout enforcement:** Killing process if execution exceeds time limit
- **Graceful shutdown:** Allowing process time to cleanup before force kill
- **SIGTERM:** Interrupt signal (graceful termination request)
- **SIGKILL:** Force kill signal (immediate termination, no cleanup)
- **Zombie process:** Terminated process not yet waited by parent
- **Process uptime:** Time since process spawned

---

**End of ADR-0034b**
