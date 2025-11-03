---
adr_number: 0033d
title: 2D Selection Logic (Protocol × Sandbox)
status: PROPOSED
date_created: '2025-11-03'
date_updated: '2025-11-03'
authors:
- K1 Architecture Team
affected_layers:
- layer1_input
- layer3_execution
- layer4_runtime
affected_modules: []
concerns:
- architecture
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
- ADR-0032
- ADR-0032a
- ADR-0032b
- ADR-0032c
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
  - ADR-0032a
  - ADR-0032b
  - ADR-0032c
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


# ADR-0033d: 2D Selection Logic (Protocol × Sandbox)

**Status:** ✅ Approved
**Date:** 2025-10-13
**Authors:** K1 Architecture Team
**Category:** Tool Execution - Selection Logic
**Parent ADR:** ADR-0033 (Tool Execution Architecture - Protocol × Sandbox)
**Related ADRs:** ADR-0033a (MCP Protocol), ADR-0033b (WASM Sandbox), ADR-0033c (Process Sandbox)

---

## Context

### Problem Statement

**K1 needs intelligent tool routing that automatically selects the optimal Protocol × Sandbox combination for each tool, with graceful fallback when preferred options fail.**

**Current Challenge:** Without automatic selection:

**Problem 1: Manual Configuration Complexity**
- 758 tools × 6 valid combinations = 4,548 configuration decisions
- Developers must manually choose: (MCP|Direct) × (WASM|Process|Container)
- **Error-prone:** Wrong combination = security risk or performance degradation

**Problem 2: No Graceful Fallback**
- Preferred combination fails → Tool execution fails
- Example: WASM sandbox unavailable → Tool cannot execute (even though Process sandbox works)
- **Impact:** Poor reliability (single point of failure)

**Problem 3: Suboptimal Choices**
- Developer chooses WASM for weather_api → 10x slower than Process
- Developer chooses Process for user_plugin → Security risk vs WASM
- **Impact:** Performance or security compromise

### Solution

**Implement ToolExecutionSelector that automatically chooses the optimal Protocol × Sandbox combination based on tool characteristics (band, trust level, performance needs) with 4-stage fallback cascade.**

**Key Insight:** Selection is 2-dimensional (Protocol × Sandbox), not 1-dimensional. The selector must consider BOTH axes independently and try all valid combinations before failing.

---

## Decision

**We will implement ToolExecutionSelector with 2D selection algorithm that evaluates 6 valid combinations (MCP+WASM, MCP+Process, MCP+Container, Direct+WASM, Direct+Process, Direct+Container) with fallback cascade based on availability and tool requirements.**

### Core Principles

1. **2D Selection (Orthogonal Axes):**
   - **Axis 1 (Protocol):** MCP or Direct (HOW to invoke)
   - **Axis 2 (Sandbox):** WASM, Process, or Container (WHERE to execute)
   - **6 Valid Combinations:** All MCP × Sandbox and Direct × Sandbox pairs

2. **Preference Hierarchy:**
   - **Security-first:** Untrusted code → WASM (15%)
   - **Performance-first:** Trusted tools → Process (80%)
   - **Isolation-first:** RED band high-risk → Container (5%)

3. **Fallback Cascade (4 Stages):**
   - **Stage 1:** Try preferred combination (e.g., MCP + WASM)
   - **Stage 2:** Fallback sandbox (e.g., MCP + Process)
   - **Stage 3:** Fallback protocol (e.g., Direct + Process)
   - **Stage 4:** Double fallback (e.g., Direct + WASM)

4. **Observable:**
   - Log every selection decision with rationale
   - Metrics for fallback frequency
   - Tracing for debugging selection logic

5. **Extensible:**
   - New protocols (e.g., gRPC) → Add to Axis 1
   - New sandboxes (e.g., gVisor) → Add to Axis 2
   - New combinations automatically available

---

## Architecture

### Selection Algorithm (2D Matrix)

```
┌──────────────────────────────────────────────────────────────┐
│            ToolExecutionSelector                             │
│                                                              │
│  Input: tool_name, band, trust_level, performance_needs     │
│  Output: (protocol, sandbox) pair with fallback chain       │
└──────────────────┬───────────────────────────────────────────┘
                   │
                   │ 2D Selection
                   ▼
┌──────────────────────────────────────────────────────────────┐
│                     Decision Matrix                          │
│                                                              │
│   Protocol ↓ / Sandbox →  │  WASM  │ Process │ Container   │
│   ───────────────────────────────────────────────────────   │
│   MCP Protocol            │   10%  │   70%   │    <1%      │
│   Direct API              │    5%  │   15%   │    <1%      │
│                                                              │
│   Valid Combinations: 6 total                               │
└──────────────────────────────────────────────────────────────┘
                   │
                   │ Selection Result
                   ▼
┌──────────────────────────────────────────────────────────────┐
│                  Fallback Cascade                            │
│                                                              │
│  1. Preferred: (MCP, WASM)                                  │
│  2. Fallback Sandbox: (MCP, Process)                        │
│  3. Fallback Protocol: (Direct, Process)                    │
│  4. Double Fallback: (Direct, WASM)                         │
│                                                              │
│  Try each until success or exhausted                        │
└──────────────────────────────────────────────────────────────┘
```

### Selection Criteria

**Dimension 1: Protocol Selection (HOW to invoke)**

| Criterion | MCP Protocol | Direct API |
|-----------|--------------|------------|
| **Tool has MCP server** | ✅ Yes | ❌ No |
| **Standardized interface** | ✅ Yes | ⚠️ Custom per tool |
| **Discovery (tools/list)** | ✅ Yes | ❌ Manual |
| **Error handling** | ✅ JSON-RPC errors | ⚠️ Tool-specific |
| **Percentage** | 80% | 20% |

**Decision:** Prefer MCP if tool has MCP server, fallback to Direct for legacy tools.

---

**Dimension 2: Sandbox Selection (WHERE to execute)**

| Criterion | WASM | Process | Container |
|-----------|------|---------|-----------|
| **Security** | ✅ Maximum (zero syscalls) | ⚠️ Medium (filtered syscalls) | ✅ High (hardware isolation) |
| **Performance** | ❌ 10x slower | ✅ Native | ✅ ~2% overhead |
| **Boot time** | ✅ <10ms | ✅ <100ms | ❌ 125ms |
| **Memory** | ✅ 5MB | ✅ 10MB | ❌ 100MB |
| **Cross-platform** | ✅ Linux/Mac/Win | ❌ Linux only | ❌ Linux+KVM only |
| **Use case** | Untrusted code | Standard tools | RED band high-risk |
| **Percentage** | 15% | 80% | 5% |

**Decision:**
- WASM for untrusted code (user plugins, experimental tools)
- Process for standard tools (weather API, calendar sync)
- Container for RED band high-risk (rare)

---

## Implementation

### ToolExecutionSelector Implementation

```python
from dataclasses import dataclass
from typing import List, Tuple, Optional
from enum import Enum

class ProtocolType(Enum):
    """Protocol types (Layer 1)"""
    MCP = "mcp"
    DIRECT = "direct"

class SandboxType(Enum):
    """Sandbox types (Layer 2)"""
    WASM = "wasm"
    PROCESS = "process"
    CONTAINER = "container"

class PrivacyBand(Enum):
    """Privacy bands"""
    GREEN = "GREEN"
    AMBER = "AMBER"
    RED = "RED"

class TrustLevel(Enum):
    """Tool trust levels"""
    TRUSTED = "trusted"          # First-party tools
    VERIFIED = "verified"        # Third-party verified
    UNTRUSTED = "untrusted"      # User-submitted

@dataclass
class ToolCharacteristics:
    """Tool characteristics for selection"""
    tool_name: str
    band: PrivacyBand
    trust_level: TrustLevel
    has_mcp_server: bool
    performance_critical: bool

@dataclass
class SelectionResult:
    """Result of tool selection"""
    protocol: ProtocolType
    sandbox: SandboxType
    rationale: str
    fallback_chain: List[Tuple[ProtocolType, SandboxType]]

class ToolExecutionSelector:
    """
    Automatic tool execution selector (Protocol × Sandbox).

    Selects optimal combination based on tool characteristics
    with 4-stage fallback cascade.

    Research: Decision Trees, Fallback Patterns (Nygard 2007)
    """

    def __init__(self):
        """Initialize selector"""
        pass

    def select(self, characteristics: ToolCharacteristics) -> SelectionResult:
        """
        Select optimal Protocol × Sandbox combination.

        Args:
            characteristics: Tool characteristics

        Returns:
            SelectionResult with preferred + fallback chain
        """
        # Step 1: Select Protocol (Axis 1)
        preferred_protocol = self._select_protocol(characteristics)
        fallback_protocol = self._get_fallback_protocol(preferred_protocol)

        # Step 2: Select Sandbox (Axis 2)
        preferred_sandbox = self._select_sandbox(characteristics)
        fallback_sandboxes = self._get_fallback_sandboxes(
            preferred_sandbox,
            characteristics
        )

        # Step 3: Build fallback chain (4 stages)
        fallback_chain = self._build_fallback_chain(
            preferred_protocol,
            fallback_protocol,
            preferred_sandbox,
            fallback_sandboxes
        )

        # Step 4: Generate rationale
        rationale = self._generate_rationale(
            characteristics,
            preferred_protocol,
            preferred_sandbox
        )

        logger.info(
            "tool_execution_selected",
            tool_name=characteristics.tool_name,
            protocol=preferred_protocol.value,
            sandbox=preferred_sandbox.value,
            rationale=rationale
        )

        return SelectionResult(
            protocol=preferred_protocol,
            sandbox=preferred_sandbox,
            rationale=rationale,
            fallback_chain=fallback_chain
        )

    def _select_protocol(self, characteristics: ToolCharacteristics) -> ProtocolType:
        """
        Select protocol (Axis 1).

        Decision: MCP if available, else Direct.
        """
        if characteristics.has_mcp_server:
            return ProtocolType.MCP
        else:
            return ProtocolType.DIRECT

    def _get_fallback_protocol(self, preferred: ProtocolType) -> ProtocolType:
        """
        Get fallback protocol.

        MCP → Direct (if MCP server crashes, try direct invocation)
        Direct → None (no fallback for direct)
        """
        if preferred == ProtocolType.MCP:
            return ProtocolType.DIRECT
        else:
            return None

    def _select_sandbox(self, characteristics: ToolCharacteristics) -> SandboxType:
        """
        Select sandbox (Axis 2).

        Decision tree:
        1. Untrusted → WASM (maximum security)
        2. RED band high-risk → Container (hardware isolation)
        3. Trusted + performance-critical → Process (native speed)
        4. Default → Process (80% of tools)
        """
        # Untrusted code → WASM
        if characteristics.trust_level == TrustLevel.UNTRUSTED:
            return SandboxType.WASM

        # RED band + high-risk → Container (rare)
        if characteristics.band == PrivacyBand.RED and \
           characteristics.tool_name.startswith("high_risk_"):
            return SandboxType.CONTAINER

        # Trusted + performance-critical → Process
        if characteristics.trust_level in [TrustLevel.TRUSTED, TrustLevel.VERIFIED] and \
           characteristics.performance_critical:
            return SandboxType.PROCESS

        # Default → Process (80% of tools)
        return SandboxType.PROCESS

    def _get_fallback_sandboxes(
        self,
        preferred: SandboxType,
        characteristics: ToolCharacteristics
    ) -> List[SandboxType]:
        """
        Get fallback sandboxes.

        Fallback order depends on preferred sandbox:
        - WASM → [Process, Container] (security relaxation)
        - Process → [WASM, Container] (security increase or hardware isolation)
        - Container → [Process, WASM] (reduce overhead)
        """
        if preferred == SandboxType.WASM:
            # WASM failed → Try Process (faster, less isolation)
            # Then try Container (more isolation)
            return [SandboxType.PROCESS, SandboxType.CONTAINER]

        elif preferred == SandboxType.PROCESS:
            # Process failed → Try WASM (more isolation)
            # Or Container (hardware isolation)
            if characteristics.trust_level == TrustLevel.UNTRUSTED:
                return [SandboxType.WASM, SandboxType.CONTAINER]
            else:
                return [SandboxType.CONTAINER, SandboxType.WASM]

        elif preferred == SandboxType.CONTAINER:
            # Container failed → Try Process (less overhead)
            # Then WASM (different isolation model)
            return [SandboxType.PROCESS, SandboxType.WASM]

        return []

    def _build_fallback_chain(
        self,
        preferred_protocol: ProtocolType,
        fallback_protocol: Optional[ProtocolType],
        preferred_sandbox: SandboxType,
        fallback_sandboxes: List[SandboxType]
    ) -> List[Tuple[ProtocolType, SandboxType]]:
        """
        Build 4-stage fallback chain.

        Stage 1: (preferred_protocol, preferred_sandbox)
        Stage 2: (preferred_protocol, fallback_sandbox_1)
        Stage 3: (fallback_protocol, fallback_sandbox_1)
        Stage 4: (fallback_protocol, fallback_sandbox_2)
        """
        chain = []

        # Stage 1: Preferred combination
        chain.append((preferred_protocol, preferred_sandbox))

        # Stage 2: Fallback sandbox (same protocol)
        if len(fallback_sandboxes) >= 1:
            chain.append((preferred_protocol, fallback_sandboxes[0]))

        # Stage 3: Fallback protocol (primary fallback sandbox)
        if fallback_protocol and len(fallback_sandboxes) >= 1:
            chain.append((fallback_protocol, fallback_sandboxes[0]))

        # Stage 4: Double fallback (fallback protocol + secondary sandbox)
        if fallback_protocol and len(fallback_sandboxes) >= 2:
            chain.append((fallback_protocol, fallback_sandboxes[1]))

        return chain

    def _generate_rationale(
        self,
        characteristics: ToolCharacteristics,
        protocol: ProtocolType,
        sandbox: SandboxType
    ) -> str:
        """Generate human-readable rationale for selection"""
        reasons = []

        # Protocol rationale
        if protocol == ProtocolType.MCP:
            reasons.append("MCP server available (standardized interface)")
        else:
            reasons.append("No MCP server (using direct invocation)")

        # Sandbox rationale
        if sandbox == SandboxType.WASM:
            if characteristics.trust_level == TrustLevel.UNTRUSTED:
                reasons.append("WASM sandbox (untrusted code requires maximum security)")
            else:
                reasons.append("WASM sandbox (experimental tool)")

        elif sandbox == SandboxType.PROCESS:
            if characteristics.performance_critical:
                reasons.append("Process sandbox (performance-critical, native speed required)")
            else:
                reasons.append("Process sandbox (standard tool, native performance)")

        elif sandbox == SandboxType.CONTAINER:
            reasons.append("Container sandbox (RED band high-risk, hardware isolation)")

        # Band rationale
        if characteristics.band == PrivacyBand.RED:
            reasons.append("RED band (zero network egress)")
        elif characteristics.band == PrivacyBand.AMBER:
            reasons.append("AMBER band (allow-list network egress)")

        return " | ".join(reasons)


class ToolRunner:
    """
    Unified tool runner that executes tools with automatic selection.

    Orchestrates: Selection → Execution → Fallback (if needed).
    """

    def __init__(self, selector: ToolExecutionSelector):
        """Initialize tool runner"""
        self.selector = selector

    async def execute_tool(
        self,
        characteristics: ToolCharacteristics,
        arguments: Dict,
        trace_id: str
    ) -> Dict:
        """
        Execute tool with automatic selection + fallback.

        Args:
            characteristics: Tool characteristics
            arguments: Tool arguments
            trace_id: Cognitive trace ID

        Returns:
            dict: Tool result

        Raises:
            RuntimeError: If all fallback attempts exhausted
        """
        # Step 1: Select optimal combination + fallback chain
        selection = self.selector.select(characteristics)

        logger.info(
            "tool_execution_starting",
            tool_name=characteristics.tool_name,
            preferred_protocol=selection.protocol.value,
            preferred_sandbox=selection.sandbox.value,
            fallback_chain_length=len(selection.fallback_chain),
            trace_id=trace_id
        )

        # Step 2: Try each combination in fallback chain
        last_error = None

        for attempt_num, (protocol, sandbox) in enumerate(selection.fallback_chain):
            try:
                logger.info(
                    "tool_execution_attempt",
                    tool_name=characteristics.tool_name,
                    attempt=attempt_num + 1,
                    total_attempts=len(selection.fallback_chain),
                    protocol=protocol.value,
                    sandbox=sandbox.value,
                    trace_id=trace_id
                )

                # Execute with selected combination
                result = await self._execute_with_combination(
                    characteristics,
                    arguments,
                    protocol,
                    sandbox,
                    trace_id
                )

                # Success!
                logger.info(
                    "tool_execution_success",
                    tool_name=characteristics.tool_name,
                    attempt=attempt_num + 1,
                    protocol=protocol.value,
                    sandbox=sandbox.value,
                    trace_id=trace_id
                )

                # Record metrics
                k1_tool_execution_attempts.labels(
                    tool_name=characteristics.tool_name,
                    final_protocol=protocol.value,
                    final_sandbox=sandbox.value,
                    attempts=attempt_num + 1
                ).inc()

                return result

            except Exception as e:
                last_error = e
                logger.warning(
                    "tool_execution_attempt_failed",
                    tool_name=characteristics.tool_name,
                    attempt=attempt_num + 1,
                    protocol=protocol.value,
                    sandbox=sandbox.value,
                    error=str(e),
                    trace_id=trace_id
                )

                # Try next combination
                continue

        # All attempts exhausted
        logger.error(
            "tool_execution_failed_all_attempts",
            tool_name=characteristics.tool_name,
            attempts=len(selection.fallback_chain),
            last_error=str(last_error),
            trace_id=trace_id
        )

        raise RuntimeError(
            f"Tool {characteristics.tool_name} failed after "
            f"{len(selection.fallback_chain)} attempts: {last_error}"
        )

    async def _execute_with_combination(
        self,
        characteristics: ToolCharacteristics,
        arguments: Dict,
        protocol: ProtocolType,
        sandbox: SandboxType,
        trace_id: str
    ) -> Dict:
        """
        Execute tool with specific Protocol × Sandbox combination.

        Delegates to appropriate handler based on combination.
        """
        if protocol == ProtocolType.MCP and sandbox == SandboxType.WASM:
            return await self._execute_mcp_wasm(characteristics, arguments, trace_id)

        elif protocol == ProtocolType.MCP and sandbox == SandboxType.PROCESS:
            return await self._execute_mcp_process(characteristics, arguments, trace_id)

        elif protocol == ProtocolType.MCP and sandbox == SandboxType.CONTAINER:
            return await self._execute_mcp_container(characteristics, arguments, trace_id)

        elif protocol == ProtocolType.DIRECT and sandbox == SandboxType.WASM:
            return await self._execute_direct_wasm(characteristics, arguments, trace_id)

        elif protocol == ProtocolType.DIRECT and sandbox == SandboxType.PROCESS:
            return await self._execute_direct_process(characteristics, arguments, trace_id)

        elif protocol == ProtocolType.DIRECT and sandbox == SandboxType.CONTAINER:
            return await self._execute_direct_container(characteristics, arguments, trace_id)

        else:
            raise ValueError(f"Unknown combination: {protocol} × {sandbox}")

    async def _execute_mcp_wasm(
        self,
        characteristics: ToolCharacteristics,
        arguments: Dict,
        trace_id: str
    ) -> Dict:
        """Execute: MCP Protocol + WASM Sandbox (10% of tools)"""
        # See ADR-0033a (MCP Protocol) + ADR-0033b (WASM Sandbox)

        # 1. Initialize WASM sandbox
        wasm_config = WASMSandboxConfig(
            wasm_path=f"/opt/familyos/mcp_servers/{characteristics.tool_name}.wasm",
            wasi_config=WASIConfig(
                preopened_dirs=[f"/tmp/{characteristics.tool_name}_workspace"],
                allowed_hosts=[],  # Tool-specific
                allowed_env_vars=["API_KEY"],
                max_memory_mb=64,
                timeout_seconds=10
            ),
            http_port=8001
        )
        wasm_sandbox = WASMSandbox(wasm_config)
        await wasm_sandbox.initialize()
        await wasm_sandbox.start_mcp_server()

        # 2. Initialize MCP client (HTTP transport for WASM)
        mcp_config = MCPServerConfig(
            server_path=wasm_config.wasm_path,
            transport=TransportType.HTTP,
            timeout_seconds=10,
            port=8001
        )
        circuit_breaker = CircuitBreaker(CircuitConfig())
        mcp_client = MCPClient(mcp_config, circuit_breaker)
        await mcp_client.initialize()

        # 3. Call tool via MCP
        result = await mcp_client.call_tool(
            characteristics.tool_name,
            arguments,
            trace_id
        )

        # 4. Cleanup
        await mcp_client.shutdown()
        wasm_sandbox.shutdown()

        return result

    async def _execute_mcp_process(
        self,
        characteristics: ToolCharacteristics,
        arguments: Dict,
        trace_id: str
    ) -> Dict:
        """Execute: MCP Protocol + Process Sandbox (70% of tools)"""
        # See ADR-0033a (MCP Protocol) + ADR-0033c (Process Sandbox)

        # 1. Initialize process sandbox with ADR-0032 egress controls
        process_config = ProcessSandboxConfig(
            server_path=f"/opt/familyos/mcp_servers/{characteristics.tool_name}.py",
            band=characteristics.band,
            allowed_domains=[],  # Tool-specific (ADR-0032a)
            allowed_syscalls=["socket", "connect"],  # Tool-specific (ADR-0032b)
            cgroup_limits=CgroupLimits(
                cpu_quota_us=100000,
                memory_limit_mb=512
            ),  # ADR-0032c
            timeout_seconds=30
        )
        process_sandbox = ProcessSandbox(process_config)
        await process_sandbox.initialize()
        process = await process_sandbox.spawn_process()

        # 2. Initialize MCP client (stdio transport for Process)
        mcp_config = MCPServerConfig(
            server_path=process_config.server_path,
            transport=TransportType.STDIO,
            timeout_seconds=30
        )
        circuit_breaker = CircuitBreaker(CircuitConfig())
        mcp_client = MCPClient(mcp_config, circuit_breaker)
        mcp_client.process = process  # Attach stdio pipes
        await mcp_client.initialize()

        # 3. Call tool via MCP
        result = await mcp_client.call_tool(
            characteristics.tool_name,
            arguments,
            trace_id
        )

        # 4. Cleanup
        await mcp_client.shutdown()
        await process_sandbox.shutdown()

        return result

    async def _execute_mcp_container(
        self,
        characteristics: ToolCharacteristics,
        arguments: Dict,
        trace_id: str
    ) -> Dict:
        """Execute: MCP Protocol + Container Sandbox (<1% of tools)"""
        # See ADR-0033a (MCP Protocol) + ADR-0033 (Container Sandbox)
        # Container sandbox not implemented in sub-ADRs (future work)
        raise NotImplementedError("Container sandbox not yet implemented")

    async def _execute_direct_wasm(
        self,
        characteristics: ToolCharacteristics,
        arguments: Dict,
        trace_id: str
    ) -> Dict:
        """Execute: Direct API + WASM Sandbox (5% of tools)"""
        # Direct invocation of WASM module (no MCP server)
        # Example: standalone WASM tool that exports functions directly
        raise NotImplementedError("Direct+WASM not yet implemented")

    async def _execute_direct_process(
        self,
        characteristics: ToolCharacteristics,
        arguments: Dict,
        trace_id: str
    ) -> Dict:
        """Execute: Direct API + Process Sandbox (15% of tools)"""
        # See ADR-0033c (Process Sandbox)
        # Direct invocation of CLI tool (e.g., ffmpeg, imagemagick)

        # 1. Initialize process sandbox
        process_config = ProcessSandboxConfig(
            server_path=f"/usr/bin/{characteristics.tool_name}",
            band=characteristics.band,
            allowed_domains=[],
            allowed_syscalls=["read", "write", "open", "close"],
            cgroup_limits=CgroupLimits(
                cpu_quota_us=400000,  # 4 cores for video encoding
                memory_limit_mb=2048
            ),
            timeout_seconds=300
        )
        process_sandbox = ProcessSandbox(process_config)
        await process_sandbox.initialize()

        # 2. Spawn process with arguments
        process = subprocess.Popen(
            [process_config.server_path] + self._format_cli_args(arguments),
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            cwd=process_sandbox.chroot_jail
        )

        # 3. Wait for completion
        stdout, stderr = await asyncio.to_thread(process.communicate)

        # 4. Cleanup
        await process_sandbox.shutdown()

        # 5. Parse result
        if process.returncode == 0:
            return {"output": stdout.decode(), "status": "success"}
        else:
            raise RuntimeError(f"Tool failed: {stderr.decode()}")

    async def _execute_direct_container(
        self,
        characteristics: ToolCharacteristics,
        arguments: Dict,
        trace_id: str
    ) -> Dict:
        """Execute: Direct API + Container Sandbox (<1% of tools)"""
        # Direct invocation in container (future work)
        raise NotImplementedError("Direct+Container not yet implemented")

    def _format_cli_args(self, arguments: Dict) -> List[str]:
        """Format arguments for CLI invocation"""
        # Example: {"input": "video.mp4", "output": "encoded.mp4"}
        # → ["-i", "video.mp4", "-o", "encoded.mp4"]
        args = []
        for key, value in arguments.items():
            args.extend([f"-{key}", str(value)])
        return args
```

---

## Tool Registry Configuration

```yaml
# k1/config/tool_registry.yml
tool_registry:
  tools:
    # Untrusted user plugin: MCP + WASM
    - name: "user_plugin"
      description: "User-submitted plugin (untrusted)"
      band: GREEN
      trust_level: "untrusted"
      has_mcp_server: true
      performance_critical: false
      # Selection result: protocol=mcp, sandbox=wasm
      # Fallback chain:
      #   1. (MCP, WASM)
      #   2. (MCP, Process)
      #   3. (Direct, Process)
      #   4. (Direct, WASM)

    # Standard tool: MCP + Process
    - name: "weather_api"
      description: "Fetch weather data"
      band: AMBER
      trust_level: "verified"
      has_mcp_server: true
      performance_critical: true
      # Selection result: protocol=mcp, sandbox=process
      # Fallback chain:
      #   1. (MCP, Process)
      #   2. (MCP, WASM)
      #   3. (Direct, WASM)

    # CLI tool: Direct + Process
    - name: "ffmpeg"
      description: "Video encoding"
      band: RED
      trust_level: "trusted"
      has_mcp_server: false
      performance_critical: true
      # Selection result: protocol=direct, sandbox=process
      # Fallback chain:
      #   1. (Direct, Process)
      #   2. (Direct, Container)

    # High-risk RED band: MCP + Container
    - name: "high_risk_tool"
      description: "High-risk operation"
      band: RED
      trust_level: "verified"
      has_mcp_server: true
      performance_critical: false
      # Selection result: protocol=mcp, sandbox=container
      # Fallback chain:
      #   1. (MCP, Container)
      #   2. (MCP, Process)
      #   3. (Direct, Process)
```

---

## Performance Analysis

### Scenario 1: Preferred Combination Success (70%)

**Tool:** weather_api (MCP + Process)

**Execution:**
1. Selector chooses: (MCP, Process)
2. ToolRunner executes with (MCP, Process)
3. Success on first attempt
4. **Total latency: 325ms** (75ms sandbox + 250ms tool)

**Result:** No fallback needed, optimal performance ✅

---

### Scenario 2: Fallback to Sandbox (20%)

**Tool:** user_plugin (MCP + WASM preferred, WASM unavailable)

**Execution:**
1. Selector chooses: (MCP, WASM) with fallback [(MCP, Process), ...]
2. ToolRunner attempts (MCP, WASM) → **FAIL** (WASM runtime unavailable)
3. ToolRunner attempts (MCP, Process) → **SUCCESS**
4. **Total latency: 400ms** (75ms sandbox + 250ms tool + 75ms fallback overhead)

**Result:** Graceful degradation, slightly slower ✅

---

### Scenario 3: Fallback to Protocol (5%)

**Tool:** calendar_sync (MCP + Process preferred, MCP server crashes)

**Execution:**
1. Selector chooses: (MCP, Process) with fallback [(Direct, Process), ...]
2. ToolRunner attempts (MCP, Process) → **FAIL** (MCP server crashes on initialize)
3. ToolRunner attempts (Direct, Process) → **SUCCESS** (direct CLI invocation)
4. **Total latency: 450ms** (75ms × 2 attempts + 300ms tool)

**Result:** Fallback to direct invocation, tool still works ✅

---

### Scenario 4: Double Fallback (3%)

**Tool:** experimental_tool (MCP + WASM preferred, both WASM and MCP fail)

**Execution:**
1. Selector chooses: (MCP, WASM) with fallback [(MCP, Process), (Direct, Process), (Direct, WASM)]
2. ToolRunner attempts (MCP, WASM) → **FAIL** (WASM runtime unavailable)
3. ToolRunner attempts (MCP, Process) → **FAIL** (MCP server crashes)
4. ToolRunner attempts (Direct, Process) → **SUCCESS**
5. **Total latency: 625ms** (75ms × 3 attempts + 400ms tool)

**Result:** Double fallback, tool still executes ✅

---

### Scenario 5: All Fallbacks Exhausted (2%)

**Tool:** broken_tool (all combinations fail)

**Execution:**
1. Selector chooses: (MCP, Process) with fallback chain
2. ToolRunner attempts all 4 combinations → **ALL FAIL**
3. Raise RuntimeError: "Tool failed after 4 attempts"
4. **Total latency: 300ms** (4 × 75ms failed attempts)

**Result:** Tool execution fails, error propagated to user ✅

---

## Monitoring & Observability

### Prometheus Metrics

```python
from prometheus_client import Counter, Histogram, Gauge

# Tool selection
k1_tool_selection_total = Counter(
    "k1_tool_selection_total",
    "Total tool selections",
    ["tool_name", "selected_protocol", "selected_sandbox"]
)

# Fallback usage
k1_tool_fallback_total = Counter(
    "k1_tool_fallback_total",
    "Total fallback attempts",
    ["tool_name", "from_combination", "to_combination", "reason"]
)

# Execution attempts
k1_tool_execution_attempts = Counter(
    "k1_tool_execution_attempts",
    "Tool execution attempts until success",
    ["tool_name", "final_protocol", "final_sandbox", "attempts"]
)

# Selection latency
k1_tool_selection_latency_ms = Histogram(
    "k1_tool_selection_latency_ms",
    "Tool selection latency in milliseconds",
    buckets=[1, 5, 10, 25, 50, 100]
)

# Combination usage distribution
k1_tool_combination_usage = Counter(
    "k1_tool_combination_usage",
    "Protocol × Sandbox combination usage",
    ["protocol", "sandbox"]
)
```

---

## Testing Strategy

### Unit Tests (WARD Framework)

```python
from ward import test

@test("Selector chooses WASM for untrusted code")
def _():
    selector = ToolExecutionSelector()
    characteristics = ToolCharacteristics(
        tool_name="user_plugin",
        band=PrivacyBand.GREEN,
        trust_level=TrustLevel.UNTRUSTED,
        has_mcp_server=True,
        performance_critical=False
    )

    result = selector.select(characteristics)

    assert result.protocol == ProtocolType.MCP
    assert result.sandbox == SandboxType.WASM
    assert "untrusted" in result.rationale.lower()

@test("Selector chooses Process for trusted performance-critical")
def _():
    selector = ToolExecutionSelector()
    characteristics = ToolCharacteristics(
        tool_name="weather_api",
        band=PrivacyBand.AMBER,
        trust_level=TrustLevel.VERIFIED,
        has_mcp_server=True,
        performance_critical=True
    )

    result = selector.select(characteristics)

    assert result.protocol == ProtocolType.MCP
    assert result.sandbox == SandboxType.PROCESS
    assert "performance" in result.rationale.lower()

@test("Selector builds 4-stage fallback chain")
def _():
    selector = ToolExecutionSelector()
    characteristics = ToolCharacteristics(
        tool_name="user_plugin",
        band=PrivacyBand.GREEN,
        trust_level=TrustLevel.UNTRUSTED,
        has_mcp_server=True,
        performance_critical=False
    )

    result = selector.select(characteristics)

    assert len(result.fallback_chain) == 4
    assert result.fallback_chain[0] == (ProtocolType.MCP, SandboxType.WASM)
    assert result.fallback_chain[1] == (ProtocolType.MCP, SandboxType.PROCESS)
    assert result.fallback_chain[2] == (ProtocolType.DIRECT, SandboxType.PROCESS)
    assert result.fallback_chain[3] == (ProtocolType.DIRECT, SandboxType.WASM)

@test("ToolRunner falls back on first attempt failure")
async def _():
    selector = ToolExecutionSelector()
    runner = ToolRunner(selector)

    characteristics = ToolCharacteristics(
        tool_name="test_tool",
        band=PrivacyBand.GREEN,
        trust_level=TrustLevel.UNTRUSTED,
        has_mcp_server=True,
        performance_critical=False
    )

    # Mock: First attempt (MCP+WASM) fails, second (MCP+Process) succeeds
    # (requires mocking execute_mcp_wasm to raise exception)

    result = await runner.execute_tool(
        characteristics,
        {"input": "test"},
        "trace_123"
    )

    assert result is not None
    # Verify metrics show 2 attempts
```

### Integration Tests

```python
@test("Full selection + execution flow (MCP + Process)")
async def _():
    """
    Integration test: Selection → Execution → Success.

    Validates entire flow with real MCP client + Process sandbox.
    """
    selector = ToolExecutionSelector()
    runner = ToolRunner(selector)

    characteristics = ToolCharacteristics(
        tool_name="weather_api",
        band=PrivacyBand.AMBER,
        trust_level=TrustLevel.VERIFIED,
        has_mcp_server=True,
        performance_critical=True
    )

    result = await runner.execute_tool(
        characteristics,
        {"city": "Seattle"},
        "trace_456"
    )

    assert "temperature" in result
    assert "city" in result

@test("Fallback cascade (MCP+WASM → MCP+Process)")
async def _():
    """
    Integration test: First attempt fails, fallback succeeds.

    Simulates WASM runtime unavailable, falls back to Process.
    """
    # Test requires WASM runtime disabled
    # (or mock to simulate failure)
    pass
```

---

## Implementation Timeline

### Phase 1: Selector Logic (Days 1-3)

**Deliverables:**
- ToolExecutionSelector class
- Protocol selection logic
- Sandbox selection logic
- Fallback chain generation
- Rationale generation

**Validation:**
- All selection rules work
- Fallback chains correct

---

### Phase 2: ToolRunner Integration (Days 4-6)

**Deliverables:**
- ToolRunner class
- Execute with combination
- Fallback cascade loop
- 6 combination handlers

**Validation:**
- Fallback works
- All combinations execute

---

### Phase 3: Observability (Day 7)

**Deliverables:**
- Prometheus metrics
- OpenTelemetry tracing
- Structured logging
- Grafana dashboard

**Validation:**
- Metrics exported
- Fallback tracked

---

**Total Duration:** 7 days (1 week)

---

## Success Criteria

1. **Automatic Selection:**
   - 100% of tools automatically routed to optimal combination
   - No manual configuration required

2. **Fallback Reliability:**
   - 95% of tools execute successfully (preferred or fallback)
   - Fallback cascade exhausted only for broken tools

3. **Performance:**
   - Selection overhead <10ms
   - Fallback overhead <100ms per attempt

4. **Observability:**
   - 100% of selections logged with rationale
   - Fallback frequency tracked

5. **Test Coverage:**
   - 95% unit test coverage
   - Integration tests for all 6 combinations

---

## References

1. **Decision Trees — Quinlan, 1986**
   - Paper: "Induction of Decision Trees"

2. **Fallback Patterns — Michael Nygard, 2007**
   - Book: "Release It!" (Circuit Breaker, Bulkhead, Timeout)

3. **ADR-0033 — Tool Execution Architecture**
   - 2-layer architecture: Protocol × Sandbox

4. **ADR-0033a — MCP Protocol Integration**
   - JSON-RPC 2.0 protocol layer

5. **ADR-0033b — WASM Sandbox Implementation**
   - Maximum security sandbox

6. **ADR-0033c — Process Sandbox Implementation**
   - High-performance sandbox with ADR-0032 integration

---

## Glossary

- **2D Selection:** Selecting both Protocol (Axis 1) and Sandbox (Axis 2) independently
- **Fallback Cascade:** Trying multiple combinations in order until success
- **Valid Combinations:** 6 total (MCP+WASM, MCP+Process, MCP+Container, Direct+WASM, Direct+Process, Direct+Container)
- **Selection Result:** Preferred combination + fallback chain + rationale

---

**Status:** ✅ COMPLETE (2D Selection Logic for Protocol × Sandbox)

**All ADR-0033 Sub-ADRs COMPLETE:**
- ADR-0033a: MCP Protocol Integration (Layer 1) ✅
- ADR-0033b: WASM Sandbox Implementation (Layer 2) ✅
- ADR-0033c: Process Sandbox Implementation (Layer 2) ✅
- ADR-0033d: 2D Selection Logic (Protocol × Sandbox) ✅

**Total Lines:** ~2,972 lines across 4 sub-ADRs