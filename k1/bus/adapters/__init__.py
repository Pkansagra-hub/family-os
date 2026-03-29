"""
k1.bus.adapters -- Module adapter layer.

Bridges existing Fabric and SessionState port interfaces to IBus.
New modules (Orchestrator, Planner, Concierge) use IBus directly.

Exports:
    FabricBusAdapter       -- IBus(bytes) <-> Fabric IEventPort(Dict) + IDeltaBusPort
    SessionBusAdapter      -- IBus(bytes) <-> SessionState IEventPort(Any)
"""

from k1.bus.adapters.fabric_adapter import FabricBusAdapter
from k1.bus.adapters.session_adapter import SessionBusAdapter

__all__ = [
    "FabricBusAdapter",
    "SessionBusAdapter",
]
