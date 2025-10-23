"""
Dynamic Agent Creation Module (ADR-0086)

This module implements dynamic agent creation with resource-aware placement,
template-based composition, and IDLE pool reuse.

Components:
    - factory: AgentFactory singleton for agent creation
    - resource_reserver: ResourceReserver for atomic resource allocation
    - composition: CompositionEngine for prompt + tool + persona assembly

Related ADRs:
    - ADR-0086: Dynamic Agent Creation Subsystem
    - ADR-0086a: Agent Factory
    - ADR-0086c: Resource Reservation
    - ADR-0086d: Agent Composition
"""

from k1.l3_execution.agents.dynamic_creation.composition import (
    Capability,
    ComposedAgent,
    CompositionEngine,
)
from k1.l3_execution.agents.dynamic_creation.factory import (
    AgentCreationRequest,
    AgentCreationResult,
    AgentFactory,
)
from k1.l3_execution.agents.dynamic_creation.resource_reserver import (
    AcceleratorType,
    ResourceRequest,
    ResourceReservation,
    ResourceReserver,
)

__all__ = [
    "AgentFactory",
    "AgentCreationRequest",
    "AgentCreationResult",
    "ResourceReserver",
    "ResourceReservation",
    "ResourceRequest",
    "AcceleratorType",
    "CompositionEngine",
    "ComposedAgent",
    "Capability",
]
