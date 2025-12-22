"""
Capability Fabric - Request/reply by capability name.

This package provides Layer 2 of the Capability Mesh architecture,
enabling modules and pipelines to invoke capabilities without
knowing the concrete provider implementation.

Architecture (ADR-K004):
    Layer 1: BusDispatcher (event routing)
    Layer 2: CapabilityFabric (request/reply by capability) <-- THIS PACKAGE
    Layer 3: PipelineScheduler (declarative triggers)

Example:
    from k0.fabric import get_capability_registry, ResolutionStrategy

    # Register a provider
    registry = get_capability_registry()
    registry.register("score_salience", provider, handler_fn)

    # Resolve and invoke
    registered = registry.resolve("score_salience")
    if registered and registered.handler:
        result = registered.handler(content="Hello world")

Related:
- k0/runtime/schemas.py: CapabilityProvider, ProviderType
- docs/architecture/decisions-K0/k004-capability-mesh-architecture.md
"""

from k0.fabric.audit import (
    AuditEvent,
    FabricAuditor,
    FabricInvokeComplete,
    FabricInvokeError,
    FabricInvokeStart,
    FabricInvokeTimeout,
    get_fabric_auditor,
    reset_fabric_auditor,
)
from k0.fabric.fabric import (
    CapabilityFabric,
    CapabilityInvocationError,
    CapabilityNotFoundError,
    CapabilityTimeoutError,
    get_capability_fabric,
    reset_capability_fabric,
)
from k0.fabric.loader import (
    discover_and_register_capabilities,
    get_capability_loader_stats,
    load_capability_definitions,
    register_capabilities_from_definitions,
)
from k0.fabric.messages import CapabilityRequest, CapabilityResponse, RequestStatus
from k0.fabric.policy import (
    ContextPolicyEnforcer,
    get_context_policy_enforcer,
    reset_context_policy_enforcer,
)
from k0.fabric.registry import (
    CapabilityRegistry,
    RegisteredProvider,
    ResolutionStrategy,
    get_capability_registry,
    reset_capability_registry,
)

__all__ = [
    # Fabric
    "CapabilityFabric",
    "CapabilityNotFoundError",
    "CapabilityTimeoutError",
    "CapabilityInvocationError",
    "get_capability_fabric",
    "reset_capability_fabric",
    # Messages
    "CapabilityRequest",
    "CapabilityResponse",
    "RequestStatus",
    # Registry
    "CapabilityRegistry",
    "RegisteredProvider",
    "ResolutionStrategy",
    "get_capability_registry",
    "reset_capability_registry",
    # Loader (Issue 2.2.2)
    "load_capability_definitions",
    "register_capabilities_from_definitions",
    "discover_and_register_capabilities",
    "get_capability_loader_stats",
    # Audit
    "AuditEvent",
    "FabricAuditor",
    "FabricInvokeStart",
    "FabricInvokeComplete",
    "FabricInvokeError",
    "FabricInvokeTimeout",
    "get_fabric_auditor",
    "reset_fabric_auditor",
    # Policy
    "ContextPolicyEnforcer",
    "get_context_policy_enforcer",
    "reset_context_policy_enforcer",
]
