# Dynamic Agents Submodule

## Overview

The `dynamic/` submodule contains runtime-instantiated agent implementations that are created on-demand during K1 execution. These agents follow the Actor Model (ADR-0002) and implement the 6-state lifecycle FSM (ADR-0005).

## Purpose

- **Runtime Instantiation**: Agents created dynamically via AgentFactory (ADR-0086)
- **Specialized Execution**: Task-specific agents for planning, research, safety, and custom workflows
- **Resource Management**: Pre-allocated resources with capability binding
- **Fault Isolation**: Each agent runs in supervised actor context

## Agent Implementations

### PlannerAgentInstance

**Purpose**: Spawned planner agent for complex multi-step task decomposition using LLM reasoning.

**Key Features**:
- LLM-powered plan generation with confidence scoring
- Tool registry integration for capability assessment
- SessionState access for context awareness
- DAG execution coordination

**ADRs**:
- ADR-0007: 4-Stage Planning Pipeline
- ADR-0059: Learning Loop Framework
- ADR-0086: Dynamic Agent Creation

**Performance**: <500ms plan generation, <150ms TTFT

### ResearcherAgent

**Purpose**: Background research and information synthesis agent.

**Key Features**:
- Web search and data analysis capabilities
- Multi-source information aggregation
- Background priority execution
- Knowledge graph integration

**ADRs**:
- ADR-0002: Actor Model for concurrency
- ADR-0027: Model placement optimization
- ADR-0059: Learning loop integration

**Performance**: <3000ms complex research tasks

### SafetyWatchAgent

**Purpose**: URGENT priority content filtering and safety validation.

**Key Features**:
- Real-time content safety assessment
- ML-based toxicity detection
- Privacy band enforcement
- RED band two-person rule compliance

**ADRs**:
- ADR-0010: Capability-based security
- ADR-0035: PII detection and redaction
- ADR-0052: Enhanced HITL protocols

**Performance**: <50ms safety checks, URGENT priority

### CustomAgent

**Purpose**: Flexible agent composition with prompt + tools + persona.

**Key Features**:
- Runtime prompt injection
- Tool capability binding
- Persona customization
- Template-based instantiation

**ADRs**:
- ADR-0086: Dynamic agent creation subsystem
- ADR-0086d: Agent composition pattern
- ADR-0086e: Prompt directory management

**Performance**: <100ms instantiation, configurable resources

## Architecture

### Base Classes

All dynamic agents inherit from `BaseAgent` in the parent `agents/` module:

```python
class BaseAgent(Actor):
    def __init__(self, agent_id: str, mailbox: AgentMailbox, capabilities: List[str]):
        self.agent_id = agent_id
        self.mailbox = mailbox
        self.capabilities = capabilities
        self.state = AgentState.PENDING

    async def handle_message(self, msg: MailboxMessage) -> None:
        # Actor message processing
        pass

    async def lifecycle_transition(self, from_state: AgentState, to_state: AgentState) -> None:
        # FSM state changes
        pass
```

### Creation Pattern

Dynamic agents are created via the AgentFactory:

```python
# Agent specification
spec = AgentSpec(
    type="researcher",
    capabilities=["web_search", "data_synthesis"],
    resources=ResourceSpec(memory_mb=256, placement="CPU"),
    prompt_template="researcher_v2.jinja2"
)

# Factory instantiation
agent = await agent_factory.create_agent(spec, session_id)
```

## Lifecycle Management

All dynamic agents follow the 6-state FSM:

1. **PENDING**: Agent registered, resources reserved
2. **WARMING**: Model loading, prompt initialization
3. **ACTIVE**: Processing tasks via mailbox
4. **IDLE**: Waiting for reactivation
5. **DRAINING**: Graceful shutdown, state flush
6. **TERMINATED**: Resources released

## Security & Capabilities

- **Capability Tokens**: Unforgeable tokens for tool/model access
- **Privacy Bands**: GREEN/AMBER/RED/BLACK enforcement
- **Sandboxing**: Tool execution in isolated containers
- **Audit Trail**: All actions logged to K0 receipts

## Testing

- **Unit Tests**: Isolated agent logic with mailbox mocks
- **Integration Tests**: Factory creation and lifecycle validation
- **Performance Tests**: Latency benchmarks for each agent type
- **Security Tests**: Capability enforcement validation

## Dependencies

- `k1.agents.lifecycle`: FSM implementation
- `k1.agents.base`: BaseAgent class
- `k1.orchestrator.factory`: AgentFactory for creation
- `k1.model_hub`: LLM integration for AI agents
- `k1.tools`: MCP protocol execution</content>
<parameter name="filePath">D:\familyos\k1\agents\dynamic\README.md
