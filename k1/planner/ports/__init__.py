"""k1.planner.ports -- Planner hexagonal port protocols [F11].

Re-exports all 7 port Protocols from their individual modules.
Consumers (services, adapters, factory) import from this package:

    from k1.planner.ports import IMailboxPort, ILLMPort, ...

No logic: this file contains ONLY imports and ``__all__``.

Import graph (Layer 1)
----------------------
k1.planner.ports
  -> k1.planner.ports.mailbox_port      (IMailboxPort)
  -> k1.planner.ports.llm_port          (ILLMPort)
  -> k1.planner.ports.fabric_retrieval_port  (IFabricRetrievalPort)
  -> k1.planner.ports.state_read_port   (IStateReadPort)
  -> k1.planner.ports.bridge_port       (IBridgePort)
  -> k1.planner.ports.delta_emit_port   (IDeltaEmitPort)
  -> k1.planner.ports.event_port        (IEventPort)
"""

from k1.planner.ports.bridge_port import IBridgePort  # noqa: F401
from k1.planner.ports.delta_emit_port import IDeltaEmitPort  # noqa: F401
from k1.planner.ports.event_port import IEventPort  # noqa: F401
from k1.planner.ports.fabric_retrieval_port import IFabricRetrievalPort  # noqa: F401
from k1.planner.ports.llm_port import ILLMPort  # noqa: F401
from k1.planner.ports.mailbox_port import IMailboxPort  # noqa: F401
from k1.planner.ports.state_read_port import IStateReadPort  # noqa: F401

__all__ = [
    "IMailboxPort",
    "ILLMPort",
    "IFabricRetrievalPort",
    "IStateReadPort",
    "IBridgePort",
    "IDeltaEmitPort",
    "IEventPort",
]
