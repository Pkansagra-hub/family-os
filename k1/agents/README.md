# K1 Agents Module (L4: The Workers)

## Overview

The `agents/` module implements the **L4: The Workers** layer of the K1 Cognitive Architecture. This layer provides the **agent runtime infrastructure**: spawning, lifecycle management, mailboxes, supervision, and generic execution scaffolding for dynamic agent instances. All agents follow the Actor Model (ADR-0002) with a 6-state lifecycle FSM (ADR-0005).

## Purpose

- **Runtime Infrastructure**: Agent lifecycle FSM, mailbox allocation, supervision, and base execution adapters
- **Generic Execution**: LLM calls via Model Gateway, tool calls via Fabric/Tool Provider
- **Dynamic Instantiation**: Ephemeral agent instances spawned from module templates
- **Fault Isolation**: Each agent runs in isolated actor context with supervision

**Important Boundary**: This module is for *runtime execution*, not domain agent definitions. Domain agents are defined in `k1/modules/*/agents/*.yaml` and loaded via `kernel/loader.py` into the agent registry.

## Architecture

### Core Components

- **`lifecycle.py`**: AgentLifecycleFSM implementing 6 states (PENDING→WARMING→ACTIVE→IDLE→DRAINING→TERMINATED)
- **`base.py`**: BaseAgent class providing mailbox integration, tool execution hooks, and lifecycle management
- **`dynamic/`**: Container for ephemeral runtime agent instances (not domain definitions)
- **`mailboxes/`**: Dynamic mailbox allocation with WFQ scheduling integration
- **`factory.py`**: AgentFactory for instantiating agents from module templates via Fabric resolution

### Agent Runtime Types

Agents are generic runners specialized by data (prompts, tools, personas) from modules. Runtime types include:

#### AI Agent Runners

- **PlannerRunner**: LLM reasoning for task decomposition using module-provided prompts
- **ResearchRunner**: Background synthesis using module tools
- **SafetyRunner**: Content filtering with module-defined safety rules
- **CustomRunner**: Composable execution with module-specified capabilities

#### Pure Actor Executors

- **ToolRunner**: MCP protocol execution with sandboxing
- **ModelInferenceCascade**: Hardware placement optimization (NPU→GPU→CPU→Remote)
- **WorkflowExecutor**: DAG execution with dependency resolution

### Agent Definition Flow

1. Domain agents defined in `k1/modules/<module>/agents/*.yaml`
2. Loaded by `kernel/loader.py` into `kernel/registries/agent_registry.py`
3. Fabric resolves `agent.spawn.<module>.<agent>` requests
4. `AgentFactory` instantiates runtime instance in `dynamic/` using generic runners

## Key ADRs

- **ADR-0005**: Agent Lifecycle FSM (6 States) - Core lifecycle management
- **ADR-0002**: Actor Model for Agent Isolation - Concurrency and fault isolation foundation
- **ADR-0086**: Dynamic Agent Creation Subsystem - Runtime instantiation patterns
- **ADR-0006**: 3-Phase Orchestration - Contract Net Protocol for agent coordination
- **ADR-0008**: Saga Pattern for Error Recovery - Compensation transactions
- **ADR-0027**: Model Placement Cascade - Hardware optimization for inference
- **ADR-0033**: Tool Execution Architecture - MCP protocol and sandboxing
- **ADR-0058**: Intent Classification in Voice - High-confidence voice intent recognition
- **ADR-0059**: Learning Loop Framework - Feedback integration and drift detection
- **ADR-0078**: Tool Call Batching Pipeline - Parallel tool execution
- **ADR-0079**: Learning Loop - Drift Detection v2 - Enhanced anomaly detection

## Interfaces

### BaseAgent Interface

```python
class BaseAgent(Actor):
    async def handle_message(self, msg: MailboxMessage) -> None:
        """Process incoming messages from mailbox"""

    async def execute_tool(self, tool_call: MCPToolCall) -> MCPToolResponse:
        """Execute MCP tool with sandboxing"""

    async def lifecycle_transition(self, from_state: AgentState, to_state: AgentState) -> None:
        """Handle state transitions in lifecycle FSM"""
```

### Dynamic Agent Creation

Agents are instantiated from module templates via Fabric:

```python
# Module defines agent in k1/modules/health/agents/health_agent.yaml
# Kernel loads it into agent_registry
# Fabric resolves agent.spawn.health.health_agent

agent_spec = await fabric.resolve_agent_spec("agent.spawn.health.health_agent")
agent = await agent_factory.create_agent(agent_spec, session_id)
```

This ensures domain logic stays in modules, runtime in agents/.

## Performance Characteristics

- **Activation Latency**: <50ms (IDLE→ACTIVE), <250ms (cold start)
- **Memory Footprint**: 150-500MB per agent (model-dependent)
- **Concurrent Agents**: 1-3 per session, 10-15 sessions per device
- **Tool Execution**: <3000ms E2E P95 for complex tool chains

## Fault Tolerance

- **Supervisor Monitoring**: 1Hz health checks with exponential backoff
- **Crash Recovery**: Max 3 crashes/10min → 1hr blacklist
- **Resource Cleanup**: Automatic lease revocation and memory reclamation
- **Saga Compensation**: Rollback for failed multi-agent workflows

## Security

- **Capability-Based Access**: Unforgeable tokens for tool/model access
- **Sandboxing**: WASM containers for tool execution
- **Privacy Bands**: GREEN/AMBER/RED/BLACK band enforcement
- **Audit Trail**: Immutable logs to K0 receipts

## Testing

- **Unit Tests**: Isolated agent logic with mocked mailboxes
- **Integration Tests**: End-to-end agent lifecycle and tool execution
- **Performance Benchmarks**: Latency and throughput validation
- **Chaos Testing**: Fault injection for resilience validation

## Dependencies

- `k1.bus`: EventBus, DeltaBus, MailboxRouter
- `k1.supervision`: Supervisor monitoring and recovery
- `k1.tools`: MCP runners and WASM sandboxing
- `k1.model_inference`: Hardware placement cascade
- `k1.config`: Agent templates and settings
- `k1.kernel`: Module loading and registries (agent_registry)
- `k1.fabric`: Agent spawning resolution

## Architecture Boundary

### ✅ What `k1/agents/` Contains (Runtime Infrastructure)

- Agent lifecycle FSM
- Mailbox runtime + WFQ
- Agent base class / actor wrappers
- Agent host / supervisor hooks
- Generic execution adapters (LLM via Model Gateway, tools via Fabric)
- Dynamic instances container (ephemeral objects)

### ❌ What `k1/agents/` Does NOT Contain

- Domain agent definitions (e.g., HealthAgent, FinanceAgent)
- Domain reasoning logic
- Domain prompt files
- Domain tool wiring

Those belong in `k1/modules/*/agents/*.yaml`.

### Agent Definition Location

Agent "blueprints" live in modules:

```text
k1/modules/<module_name>/agents/*.yaml
```

Examples:

- `k1/modules/health/agents/health_agent.yaml`
- `k1/modules/stress_table/agents/stress_agent.yaml`

Loaded into `kernel/registries/agent_registry.py`.

### Clean Module Addition Checklist

If you add a new feature module on Sunday morning, do you need to edit:

- `k1/agents/` ❌ NO
- `k1/k0_bridge/` ❌ NO
- `k1/fabric/` ❌ ideally NO (unless new provider type)
- Only `k1/modules/<new_module>/...` ✅ YES

If the answer is "yes only modules", your architecture is **clean**.

## Development Notes

- All agents inherit from BaseAgent and implement Actor Model
- Dynamic agents created via AgentFactory from module templates (not hardcoded)
- Lifecycle managed by AgentLifecycleFSM with supervisor oversight
- Tool execution uses MCP protocol with FlatBuffers serialization
- Model inference optimized for thermal and performance constraints
- Avoid loading Python classes from modules to prevent kernel contamination; prefer data-driven specialization</content>
