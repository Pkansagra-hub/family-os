"""
k1.orchestrator.ports -- Port interface package for the Orchestrator.

Re-exports all 8 port Protocols for the Orchestrator hexagonal architecture.

Ports 1-7 defined in Epic 1.4. Port 8 (IWorkflowStoragePort) defined in
Epic 4.1 Issue 4.1.6.

Usage::

    from k1.orchestrator.ports import (
        IMailboxPort,
        IFabricGatewayPort,
        IPlannerPort,
        IStateReadPort,
        IDeltaEmitPort,
        IBridgeWritePort,
        IEventSubscriptionPort,
        IWorkflowStoragePort,
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
from k1.orchestrator.ports.workflow_storage_port import IWorkflowStoragePort

__all__ = [
    # Port Protocols (8 ports)
    "IBridgeWritePort",
    "IDeltaEmitPort",
    "IEventSubscriptionPort",
    "IFabricGatewayPort",
    "IMailboxPort",
    "IPlannerPort",
    "IStateReadPort",
    "IWorkflowStoragePort",
    # Supporting types
    "MailboxFullError",
    "MailboxMessage",
]
