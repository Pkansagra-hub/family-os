"""
k1.memory_writer.ports -- Port interface package for Memory Writer v2.

Re-exports all 5 port Protocols for the MW v2 hexagonal architecture.

Ports follow the same pattern as k1/orchestrator/ports/:
  - Pure typing.Protocol classes
  - runtime_checkable for isinstance validation
  - Async methods (SessionState, Bridge, Bus may involve I/O)

Usage::

    from k1.memory_writer.ports import (
        ISessionReadPort,
        IBridgeCommandPort,
        IEventSubscriptionPort,
        IModelHubPort,
        IHealthPort,
    )
"""

from k1.memory_writer.ports.bridge_command_port import IBridgeCommandPort
from k1.memory_writer.ports.event_subscription_port import IEventSubscriptionPort
from k1.memory_writer.ports.health_port import IHealthPort
from k1.memory_writer.ports.model_hub_port import IModelHubPort
from k1.memory_writer.ports.session_read_port import ISessionReadPort

__all__ = [
    "IBridgeCommandPort",
    "IEventSubscriptionPort",
    "IHealthPort",
    "IModelHubPort",
    "ISessionReadPort",
]
