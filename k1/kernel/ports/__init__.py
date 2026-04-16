"""
k1.kernel.ports -- Hexagonal port interfaces for the Kernel.

Defines all 8 port protocols that KernelService uses for external
communication. These are the hexagonal boundary: ALL Tier 1 and Tier 2
lifecycle operations go through these ports.

Pattern: All ports are ``typing.Protocol`` classes (structural subtyping).
         No ABC inheritance. Enforced by type checker. ``@runtime_checkable``
         for optional isinstance() guards at construction time.

Ports:
  IBusPort            (2.0.8) -- Bus infrastructure creation/access
  IModelHubPort       (2.0.8) -- LLM lifecycle management
  IFabricPort         (2.0.8) -- Shared and per-session Fabric lifecycle
  IBridgePort         (2.0.8) -- K0 Cross-Kernel Bridge connection
  IOrchestratorPort   (2.0.8) -- Shared Orchestrator lifecycle + S6b cross-wire
  IPlannerPort        (2.0.8) -- Shared Planner lifecycle
  ISessionManagerPort (2.0.8) -- Per-session component bag CRUD
  ILifecyclePort      (2.0.8) -- Top-level startup/shutdown/health

Supporting types:
  HealthStatus -- Aggregated health snapshot from ILifecyclePort

References:
  - Epic 2.0.8 (Port scaffolding)
  - 05_port_adapter_mapping (52 component-level ports)
  - 08_end_to_end_wiring_requirements (S1-S7, P1-P7 wiring)
  - Follows k1/orchestrator/ports/ convention (one file per port)

Usage::

    from k1.kernel.ports import (
        IBusPort,
        IModelHubPort,
        IFabricPort,
        IBridgePort,
        IOrchestratorPort,
        IPlannerPort,
        ISessionManagerPort,
        ILifecyclePort,
        HealthStatus,
    )
"""

from k1.kernel.ports.bridge_port import IBridgePort
from k1.kernel.ports.bus_port import IBusPort
from k1.kernel.ports.fabric_port import IFabricPort
from k1.kernel.ports.lifecycle_port import HealthStatus, ILifecyclePort
from k1.kernel.ports.model_hub_port import IModelHubPort
from k1.kernel.ports.orchestrator_port import IOrchestratorPort
from k1.kernel.ports.planner_port import IPlannerPort
from k1.kernel.ports.session_manager_port import ISessionManagerPort

__all__ = [
    # --- 8 Kernel Port Protocols ---
    "IBridgePort",
    "IBusPort",
    "IFabricPort",
    "ILifecyclePort",
    "IModelHubPort",
    "IOrchestratorPort",
    "IPlannerPort",
    "ISessionManagerPort",
    # --- Supporting types ---
    "HealthStatus",
]
