"""
k1.fabric.ports -- Hexagonal port interfaces for the Capability Fabric.

Defines all port protocols that the Fabric uses for external communication.
These are the hexagonal boundary: ALL external I/O goes through these ports.
No subsystem bypasses a port to reach infrastructure directly.

Pattern: All ports are ``typing.Protocol`` classes (structural subtyping).
         No ABC inheritance. Enforced by type checker. ``@runtime_checkable``
         for optional isinstance() guards at construction time.

Ports:
  ISessionStateReader (5.1.1) -- Read-only SessionState access
  IEventPort          (5.1.2) -- Event emission/subscription
  IBridgePort         (5.1.3) -- K0 access via Cross-Kernel Bridge
  IModelGatewayPort   (5.1.4) -- LLM access for Agent Factory
  IPromptSystemPort   (5.1.5) -- Prompt resolution/compilation
  IDeltaBusPort       (5.1.6) -- Delta emission for agents

Supporting types:
  SessionSnapshot     -- Immutable snapshot of all SessionState sections
  SubscriptionHandle  -- Opaque handle for event unsubscription
  BridgeHealth        -- K0 health snapshot from Bridge observation
  BridgeCommandResult -- Result of a Bridge command to K0
  IFLRoute            -- IFL address routing descriptor
  ModelCapability     -- Enum of standard LLM capabilities
  ModelInfo           -- Model metadata from Model Hub
  ILLMHandle          -- Opaque LLM connection handle
  PromptTemplate      -- Resolved prompt template
  DeltaPayload        -- Single delta event from an agent

References:
  - Epic 5.1 (Port Interfaces)
  - FAB-01 (Fabric NEVER writes SessionState)
  - FAB-09 (All events carry cognitive_trace_id)
  - bridge_architecture.mmd (IFL addressing, K0 health modes)

Exports:
  ISessionStateReader, SessionSnapshot,
  IEventPort, SubscriptionHandle,
  IBridgePort, BridgeHealth, BridgeCommandResult, IFLRoute,
  IModelGatewayPort, ILLMHandle, ModelCapability, ModelInfo,
  IPromptSystemPort, PromptTemplate,
  IDeltaBusPort, DeltaPayload,
"""

from k1.fabric.ports.bridge_port import BridgeCommandResult, BridgeHealth, IBridgePort, IFLRoute
from k1.fabric.ports.delta_bus import DeltaPayload, IDeltaBusPort
from k1.fabric.ports.event_port import IEventPort, SubscriptionHandle
from k1.fabric.ports.model_gateway import ILLMHandle, IModelGatewayPort, ModelCapability, ModelInfo
from k1.fabric.ports.prompt_system import IPromptSystemPort, PromptTemplate
from k1.fabric.ports.state_reader import ISessionStateReader, SessionSnapshot

__all__ = [
    # --- 5.1.1 ISessionStateReader ---
    "ISessionStateReader",
    "SessionSnapshot",
    # --- 5.1.2 IEventPort ---
    "IEventPort",
    "SubscriptionHandle",
    # --- 5.1.3 IBridgePort ---
    "IBridgePort",
    "BridgeHealth",
    "BridgeCommandResult",
    "IFLRoute",
    # --- 5.1.4 IModelGatewayPort ---
    "IModelGatewayPort",
    "ILLMHandle",
    "ModelCapability",
    "ModelInfo",
    # --- 5.1.5 IPromptSystemPort ---
    "IPromptSystemPort",
    "PromptTemplate",
    # --- 5.1.6 IDeltaBusPort ---
    "IDeltaBusPort",
    "DeltaPayload",
]
