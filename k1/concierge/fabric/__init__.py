"""
Fabric Package -- Capability Registry and Mock Implementations
===============================================================

V2 Design Ref: Section 6.2 (Back tool integration), Section 14 (Demo capabilities)

Epic 7.5: CapabilityRegistry with discover/invoke + demo + family capabilities.

In production, this is the K0 Fabric's 9-step execution pipeline:
  resolve -> select -> build context -> execute -> validate.
For POC, it is an in-memory registry with deterministic mock handlers.

Exports:
  CapabilityRegistry:            In-memory capability registry with discover/invoke
  create_demo_registry:          Factory that pre-registers demo + family capabilities
  DEMO_CAPABILITIES:             7 original demo capability definitions (travel/prod/shop)
  FAMILY_CAPABILITIES:           31 family capability definitions (messaging/todo/chores/etc.)
  register_family_capabilities:  Register family capabilities into a registry
"""

from k1.concierge.fabric.capability_registry import CapabilityRegistry, create_demo_registry
from k1.concierge.fabric.demo_capabilities import DEMO_CAPABILITIES
from k1.concierge.fabric.family_capabilities import FAMILY_CAPABILITIES, register_family_capabilities

__all__ = [
    "CapabilityRegistry",
    "create_demo_registry",
    "DEMO_CAPABILITIES",
    "FAMILY_CAPABILITIES",
    "register_family_capabilities",
]
