"""
k1.orchestrator.ports -- Port interface package for the Orchestrator.

Re-exports all 7 port Protocols defined in Epic 1.4. The 8th port
(IWorkflowStoragePort) ships with Epic 4.1 and will be added here
when implemented.

Usage::

    from k1.orchestrator.ports import (
        IMailboxPort,
        IFabricGatewayPort,
        IPlannerPort,
        IStateReadPort,
        IDeltaEmitPort,
        IBridgeWritePort,
        IEventSubscriptionPort,
    )

Supporting types re-exported for convenience:
  - MailboxMessage (type alias for mailbox message union)
  - MailboxFullError (exception for full mailbox)
"""

from k1.orchestrator.ports.bridge_write_port import IBridgeWritePort
from k1.orchestrator.ports.delta_emit_port import IDeltaEmitPort
from k1.orchestrator.ports.event_subscription_port import IEventSubscriptionPort
from k1.orchestrator.ports.fabric_gateway_port import IFabricGatewayPort
from k1.orchestrator.ports.mailbox_port import IMailboxPort, MailboxFullError, MailboxMessage
from k1.orchestrator.ports.planner_port import IPlannerPort
from k1.orchestrator.ports.state_read_port import IStateReadPort

__all__ = [
    # Port Protocols
    "IBridgeWritePort",
    "IDeltaEmitPort",
    "IEventSubscriptionPort",
    "IFabricGatewayPort",
    "IMailboxPort",
    "IPlannerPort",
    "IStateReadPort",
    # Supporting types
    "MailboxFullError",
    "MailboxMessage",
]
