"""
k1.fabric.providers -- Provider implementations (Subsystem 5).

Canonical home for the CapabilityProvider protocol and all concrete
provider types that execute capabilities via different backends.

Provider type hierarchy:
  CapabilityProvider (Protocol)
   -> BaseProvider (ABC with common boilerplate)
       -> MCPProvider (MCP tool execution, 3.3.2)
       -> WASMProvider (sandboxed WASM execution, 3.3.3)
       -> BridgeProvider (K0 connector proxy, 3.3.4)
       -> WorkflowProvider (DAG orchestration, 3.3.5)
       -> ConciergeProvider (FSM routing, 3.3.6)
       -> AgentProvider (stub for M4, 3.3.7)

Exports:
  # Protocol + base
  CapabilityProvider     -- Protocol interface for all providers
  BaseProvider           -- ABC with timing/logging boilerplate
  ProviderError          -- Base exception
  ProviderExecutionError -- Execution failure
  ProviderTimeoutError   -- Deadline exceeded

  # MCP Provider (3.3.2)
  MCPProvider            -- MCP tool execution provider
  IMCPTransport          -- Transport port protocol
  MCPRequest             -- MCP request message
  MCPResponse            -- MCP response message
  MCPProviderError       -- MCP base exception
  MCPServerNotFoundError -- Server not reachable
  MCPToolNotFoundError   -- Tool not on server
  MCPTransportError      -- Transport-level failure

  # WASM Provider (3.3.3)
  WASMProvider           -- Sandboxed WASM execution provider
  IWASMRuntime           -- WASM runtime port protocol
  WASMModuleHandle       -- Opaque handle to loaded module
  WASMSandboxConfig      -- Sandbox configuration
  WASMExecutionResult    -- Raw WASM execution result
  WASMProviderError      -- WASM base exception
  WASMModuleLoadError    -- Module loading failed
  WASMExecutionError     -- Sandbox execution failed
  WASMMemoryLimitError   -- Sandbox memory exceeded

  # Bridge Provider (3.3.4)
  BridgeProvider         -- K0 connector proxy provider
  IBridgePort            -- Bridge access port protocol
  BridgeCommand          -- Bridge command message
  BridgeResponse         -- Bridge response message
  K0HealthMode           -- K0 health states enum
  BridgeProviderError    -- Bridge base exception
  BridgeUnavailableError -- Bridge/K0 not reachable
  BridgeOperationError   -- Bridge operation failed

  # Workflow Provider (3.3.5)
  WorkflowProvider          -- Workflow DAG execution provider
  IWorkflowRegistry         -- Workflow storage port
  IOrchestrator             -- DAG execution port
  ICapabilityLookup         -- Version-aware capability lookup port
  WorkflowSpec              -- Frozen workflow specification
  WorkflowStep              -- Single workflow step
  RunManifest               -- Pinned execution manifest
  SchemaDrift               -- Schema drift details
  DriftSeverity             -- Drift severity enum
  WorkflowProviderError     -- Base workflow exception
  WorkflowNotFoundError     -- Workflow not in registry
  WorkflowValidationError   -- Capability validation failed
  WorkflowDepthExceededError -- Depth guard triggered
  WorkflowSchemaDriftError  -- Large drift detected

  # Concierge Provider (3.3.6)
  ConciergeProvider          -- Concierge FSM routing provider
  IConciergeRouter           -- FSM routing port
  ConciergeStateRequest      -- State handler request
  ConciergeStateResponse     -- State handler response
  ConciergeProviderError     -- Base concierge exception
  ConciergeStateNotFoundError -- Unknown FSM state
  ConciergeHandlerError      -- State handler failed

  # Agent Provider (4.3.5 -- full)
  AgentProvider              -- Agent execution provider (full)
  IAgentFactory              -- Agent factory port
  AgentResult                -- Agent execution result
  AgentProviderError         -- Base agent exception
  AgentNotImplementedError   -- M3 stub error (backward compat)
  AgentSpawnError            -- Agent instantiation failed
  AgentExecutionError        -- Agent execution failed
  AgentTemplateNotFoundError -- Agent template/contract not found (4.3.5)
  AgentTimeoutError          -- Agent execution timeout (4.3.5)
  DEFAULT_AGENT_TIMEOUT_MS   -- Default agent timeout (30s) (4.3.5)

  # Agent + AgentFactory (4.3.1, 4.3.2)
  Agent                      -- Agent instance with lifecycle FSM
  AgentFactory               -- 8-step agent instantiation factory
  AgentFactoryConfig         -- Factory configuration
  AgentLifecycleError        -- Invalid lifecycle transition
  ILLMHandle                 -- LLM handle port protocol (5.1.4)
  IModelGatewayPort          -- LLM access port protocol (5.1.4)
  IDeltaBusPort              -- Delta emission port (5.1.6)
  IAgentMailbox              -- Agent mailbox port (4.4)
  ISessionStateReader        -- SessionState reader port (5.1.1)
  IDLE_TTL_S                 -- Default idle timeout (60s)

  # Agent Pool (4.3.3)
  AgentPool                  -- IDLE pool for agent reuse
  AgentPoolConfig            -- Pool configuration
  AgentPoolFullError         -- Pool at capacity

  # Delta emission (4.3.4)
  AgentDelta                 -- Structured delta payload
  DeltaEmitter               -- Batched delta emission
  DELTA_TOPIC_PATTERN        -- Topic pattern for delta bus
  DELTA_BATCH_WINDOW_MS      -- Batch window in ms
"""

from k1.fabric.providers.agent_provider import (
    DEFAULT_AGENT_TIMEOUT_MS,
    DELTA_BATCH_WINDOW_MS,
    DELTA_TOPIC_PATTERN,
    IDLE_TTL_S,
    Agent,
    AgentDelta,
    AgentExecutionError,
    AgentFactory,
    AgentFactoryConfig,
    AgentLifecycleError,
    AgentNotImplementedError,
    AgentPool,
    AgentPoolConfig,
    AgentPoolFullError,
    AgentProvider,
    AgentProviderError,
    AgentResult,
    AgentSpawnError,
    AgentTemplateNotFoundError,
    AgentTimeoutError,
    DeltaEmitter,
    IAgentFactory,
    IAgentMailbox,
    IDeltaBusPort,
    ILLMHandle,
    IModelGatewayPort,
    ISessionStateReader,
)
from k1.fabric.providers.base_provider import (
    BaseProvider,
    CapabilityProvider,
    ProviderError,
    ProviderExecutionError,
    ProviderTimeoutError,
)
from k1.fabric.providers.bridge_provider import (
    BridgeCommand,
    BridgeOperationError,
    BridgeProvider,
    BridgeProviderError,
    BridgeResponse,
    BridgeUnavailableError,
    IBridgePort,
    K0HealthMode,
)
from k1.fabric.providers.concierge_provider import (
    ConciergeHandlerError,
    ConciergeProvider,
    ConciergeProviderError,
    ConciergeStateNotFoundError,
    ConciergeStateRequest,
    ConciergeStateResponse,
    IConciergeRouter,
)
from k1.fabric.providers.mcp_provider import (
    IMCPTransport,
    MCPProvider,
    MCPProviderError,
    MCPRequest,
    MCPResponse,
    MCPServerNotFoundError,
    MCPToolNotFoundError,
    MCPTransportError,
)
from k1.fabric.providers.wasm_provider import (
    IWASMRuntime,
    WASMExecutionError,
    WASMExecutionResult,
    WASMMemoryLimitError,
    WASMModuleHandle,
    WASMModuleLoadError,
    WASMProvider,
    WASMProviderError,
    WASMSandboxConfig,
)
from k1.fabric.providers.workflow_provider import (
    DriftSeverity,
    ICapabilityLookup,
    IOrchestrator,
    IWorkflowRegistry,
    RunManifest,
    SchemaDrift,
    WorkflowDepthExceededError,
    WorkflowNotFoundError,
    WorkflowProvider,
    WorkflowProviderError,
    WorkflowSchemaDriftError,
    WorkflowSpec,
    WorkflowStep,
    WorkflowValidationError,
)

__all__ = [
    # Protocol + base
    "CapabilityProvider",
    "BaseProvider",
    "ProviderError",
    "ProviderExecutionError",
    "ProviderTimeoutError",
    # MCP Provider (3.3.2)
    "MCPProvider",
    "IMCPTransport",
    "MCPRequest",
    "MCPResponse",
    "MCPProviderError",
    "MCPServerNotFoundError",
    "MCPToolNotFoundError",
    "MCPTransportError",
    # WASM Provider (3.3.3)
    "WASMProvider",
    "IWASMRuntime",
    "WASMModuleHandle",
    "WASMSandboxConfig",
    "WASMExecutionResult",
    "WASMProviderError",
    "WASMModuleLoadError",
    "WASMExecutionError",
    "WASMMemoryLimitError",
    # Bridge Provider (3.3.4)
    "BridgeProvider",
    "IBridgePort",
    "BridgeCommand",
    "BridgeResponse",
    "K0HealthMode",
    "BridgeProviderError",
    "BridgeUnavailableError",
    "BridgeOperationError",
    # Workflow Provider (3.3.5)
    "WorkflowProvider",
    "IWorkflowRegistry",
    "IOrchestrator",
    "ICapabilityLookup",
    "WorkflowSpec",
    "WorkflowStep",
    "RunManifest",
    "SchemaDrift",
    "DriftSeverity",
    "WorkflowProviderError",
    "WorkflowNotFoundError",
    "WorkflowValidationError",
    "WorkflowDepthExceededError",
    "WorkflowSchemaDriftError",
    # Concierge Provider (3.3.6)
    "ConciergeProvider",
    "IConciergeRouter",
    "ConciergeStateRequest",
    "ConciergeStateResponse",
    "ConciergeProviderError",
    "ConciergeStateNotFoundError",
    "ConciergeHandlerError",
    # Agent Provider (4.3.5 -- full)
    "AgentProvider",
    "IAgentFactory",
    "AgentResult",
    "AgentProviderError",
    "AgentNotImplementedError",
    "AgentSpawnError",
    "AgentExecutionError",
    "AgentTemplateNotFoundError",
    "AgentTimeoutError",
    "DEFAULT_AGENT_TIMEOUT_MS",
    # Agent + AgentFactory (4.3.1, 4.3.2)
    "Agent",
    "AgentFactory",
    "AgentFactoryConfig",
    "AgentLifecycleError",
    "ILLMHandle",
    "IModelGatewayPort",
    "IDeltaBusPort",
    "IAgentMailbox",
    "ISessionStateReader",
    "IDLE_TTL_S",
    # Agent Pool (4.3.3)
    "AgentPool",
    "AgentPoolConfig",
    "AgentPoolFullError",
    # Delta emission (4.3.4)
    "AgentDelta",
    "DeltaEmitter",
    "DELTA_TOPIC_PATTERN",
    "DELTA_BATCH_WINDOW_MS",
]
