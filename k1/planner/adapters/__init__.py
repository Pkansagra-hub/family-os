"""k1.planner.adapters -- Production adapter layer [F27].

Re-exports all 7 production adapters that bridge Planner port Protocols
to real K1/K0 infrastructure.

Layer 2 (adapters):
    Import from Layer 0 (types) + Layer 1 (ports) only.
    Each adapter wraps exactly ONE infrastructure port (SS16.3).

Adapter registry (SS16.1):
    MailboxAdapter          [F28] -- IMailboxPort      -> asyncio.Queue
    LLMGatewayAdapter       [F29] -- ILLMPort          -> ILLMRequestBus (V2)
    FabricRetrievalAdapter  [F30] -- IFabricRetrievalPort -> FabricRetrieval
    SessionStateReadAdapter [F31] -- IStateReadPort    -> ISessionStateReader
    BridgeAdapter           [F32] -- IBridgePort       -> Fabric IBridgePort
    DeltaBusAdapter         [F33] -- IDeltaEmitPort    -> IDeltaBusPort
    EventBusAdapter         [F34] -- IEventPort        -> Fabric IEventPort
"""

from k1.planner.adapters.bridge_adapter import BridgeAdapter
from k1.planner.adapters.delta_bus_adapter import DeltaBusAdapter
from k1.planner.adapters.event_bus_adapter import EventBusAdapter
from k1.planner.adapters.fabric_retrieval_adapter import FabricRetrievalAdapter
from k1.planner.adapters.llm_gateway_adapter import LLMGatewayAdapter
from k1.planner.adapters.mailbox_adapter import MailboxAdapter
from k1.planner.adapters.session_state_adapter import SessionStateReadAdapter

__all__ = [
    "BridgeAdapter",
    "DeltaBusAdapter",
    "EventBusAdapter",
    "FabricRetrievalAdapter",
    "LLMGatewayAdapter",
    "MailboxAdapter",
    "SessionStateReadAdapter",
]
