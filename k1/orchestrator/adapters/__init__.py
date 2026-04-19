"""
k1.orchestrator.adapters -- Adapter layer for the Orchestrator hexagonal ports.

Re-exports all 17 production and test adapters (Issue 6.1 in
orchestrator-implementation-plan.md, plus AdminHttpAdapter added post-plan):
  - MailboxAdapter (6.1.1) -- IMailboxPort adapter (WFQ priority mailbox)
  - FabricGatewayAdapter (6.1.2) -- IFabricGatewayPort adapter (Fabric facade wrapper)
  - PlannerAdapter (6.1.3) -- IPlannerPort adapter (Planner mailbox + CB_PLANNER)
  - StateReadAdapter (6.1.4) -- IStateReadPort adapter (SessionState reader)
  - DeltaEmitAdapter (6.1.5) -- IDeltaEmitPort adapter (event + delta bus)
  - BridgeWriteAdapter (6.1.6) -- IBridgeWritePort adapter (K0 Bridge writes)
  - EventSubscriptionAdapter (6.1.7) -- IEventSubscriptionPort adapter (event bus)
  - TestMailboxAdapter (6.1.8) -- IMailboxPort test adapter (FIFO)
  - MockFabricAdapter (6.1.9) -- IFabricGatewayPort test adapter (scriptable)
  - MockPlannerAdapter (6.1.10) -- IPlannerPort test adapter (scriptable)
  - MockStateReadAdapter (6.1.11) -- IStateReadPort test adapter (in-memory)
  - TestDeltaAdapter (6.1.12) -- IDeltaEmitPort test adapter (capture)
  - MockBridgeAdapter (6.1.13) -- IBridgeWritePort test adapter (in-memory WAL)
  - TestEventAdapter (6.1.14) -- IEventSubscriptionPort test adapter (wildcard)
  - WorkflowStorageAdapter (6.1.15) -- IWorkflowStoragePort adapter (SQLite wrapper)
  - TestWorkflowStorageAdapter (6.1.16) -- IWorkflowStoragePort test adapter (in-memory)
  - AdminHttpAdapter (post-plan) -- HTTP wrapper around IAdminPort for ops endpoints
"""

from k1.orchestrator.adapters.admin_http_adapter import AdminHttpAdapter
from k1.orchestrator.adapters.bridge_write_adapter import BridgeWriteAdapter
from k1.orchestrator.adapters.delta_emit_adapter import DeltaEmitAdapter
from k1.orchestrator.adapters.event_subscription_adapter import EventSubscriptionAdapter
from k1.orchestrator.adapters.fabric_gateway_adapter import FabricGatewayAdapter
from k1.orchestrator.adapters.mailbox_adapter import MailboxAdapter
from k1.orchestrator.adapters.mock_bridge_adapter import MockBridgeAdapter
from k1.orchestrator.adapters.mock_fabric_adapter import MockFabricAdapter
from k1.orchestrator.adapters.mock_planner_adapter import MockPlannerAdapter
from k1.orchestrator.adapters.mock_state_read_adapter import MockStateReadAdapter
from k1.orchestrator.adapters.planner_adapter import PlannerAdapter
from k1.orchestrator.adapters.state_read_adapter import StateReadAdapter
from k1.orchestrator.adapters.test_delta_adapter import TestDeltaAdapter
from k1.orchestrator.adapters.test_event_adapter import TestEventAdapter
from k1.orchestrator.adapters.test_mailbox_adapter import TestMailboxAdapter
from k1.orchestrator.adapters.test_workflow_storage_adapter import (
    TestWorkflowStorageAdapter,
)
from k1.orchestrator.adapters.workflow_storage_adapter import WorkflowStorageAdapter

__all__ = [
    "AdminHttpAdapter",
    "BridgeWriteAdapter",
    "DeltaEmitAdapter",
    "EventSubscriptionAdapter",
    "FabricGatewayAdapter",
    "MailboxAdapter",
    "MockBridgeAdapter",
    "MockFabricAdapter",
    "MockPlannerAdapter",
    "MockStateReadAdapter",
    "PlannerAdapter",
    "StateReadAdapter",
    "TestDeltaAdapter",
    "TestEventAdapter",
    "TestMailboxAdapter",
    "TestWorkflowStorageAdapter",
    "WorkflowStorageAdapter",
]
