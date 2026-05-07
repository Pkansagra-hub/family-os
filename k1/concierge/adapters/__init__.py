"""
k1.concierge.adapters -- ALL adapters for Concierge port Protocols + startup tier nulls.

Phase 1: 8 ports × 2 (test + production) = 16 adapters.
Phase 2: 5 null/snapshot adapters for two-tier bootstrap (SIM-D-39).

Test adapters: in-memory, deterministic, no external dependencies.
Production adapters: thin wrappers around real bus/hub/fabric/SSM infrastructure.
Null adapters: no-op implementations for startup tier shared components.

All adapters satisfy their corresponding Protocol via structural subtyping.

Adapter map (import from the individual module or from this package):

    Port                  | Test Adapter              | Production Adapter
    ----------------------|---------------------------|-----------------------------
    IInputPort            | TestInputAdapter          | BusInputAdapter
    IOutputPort           | TestOutputAdapter         | BusOutputAdapter
    IClassificationPort   | StubPhase1Pipeline        | UltraBERTPhase1Pipeline
    ILLMPort              | TestModelHubBridge        | ModelHubPOCBridge
    IStatePort            | InMemoryStateAdapter      | SSMStateAdapter
    IDispatchPort         | MockDispatchAdapter       | FabricDispatchAdapter
    IDeltaPort            | create_test_bus()         | BusFactory.create_local()
    IMemoryPort           | MockMemoryAdapter         | RecallMemoryAdapter

    Null / Startup Tier (Phase 2):
    ISessionStateReader (Fabric)   | NullSessionStateReaderAdapter
    IDeltaBusPort (Fabric)         | NullDeltaBusAdapter
    IEventSubscriptionPort (Orch)  | NullEventSubscriptionAdapter
    IBridgeWritePort (Orch)        | NullBridgeWriteAdapter
    IStateReadPort (Planner)       | SnapshotStateReadAdapter

Import examples:
    from k1.concierge.adapters.test_input import TestInputAdapter
    from k1.concierge.adapters.bus_input import BusInputAdapter
    from k1.concierge.adapters.null_state_reader import NullSessionStateReaderAdapter
    from k1.concierge.adapters.snapshot_state_read import SnapshotStateReadAdapter
"""

# ---- Production adapters (safe to eagerly import — thin wrappers) ---------
from k1.concierge.adapters.bus_input import BusInputAdapter  # IInputPort
from k1.concierge.adapters.bus_output import BusOutputAdapter  # IOutputPort
from k1.concierge.adapters.fabric_dispatch import FabricDispatchAdapter  # IDispatchPort

# ---- Null / startup-tier adapters (Phase 2 — no heavy deps) ---------------
from k1.concierge.adapters.null_bridge_write import NullBridgeWriteAdapter
from k1.concierge.adapters.null_delta_bus import NullDeltaBusAdapter
from k1.concierge.adapters.null_event_subscription import NullEventSubscriptionAdapter
from k1.concierge.adapters.null_state_reader import NullSessionStateReaderAdapter
from k1.concierge.adapters.recall_memory import RecallMemoryAdapter  # IMemoryPort
from k1.concierge.adapters.snapshot_state_read import SnapshotStateReadAdapter
from k1.concierge.adapters.ssm_state import SSMStateAdapter  # IStatePort
from k1.concierge.adapters.test_classification import StubPhase1Pipeline  # IClassificationPort
from k1.concierge.adapters.test_delta import create_test_bus  # IDeltaPort
from k1.concierge.adapters.test_dispatch import MockDispatchAdapter  # IDispatchPort

# ---- Lightweight test adapters (no heavy deps, safe to eagerly import) ----
from k1.concierge.adapters.test_input import TestInputAdapter  # IInputPort
from k1.concierge.adapters.test_memory import MockMemoryAdapter  # IMemoryPort
from k1.concierge.adapters.test_output import TestOutputAdapter  # IOutputPort
from k1.concierge.adapters.test_state import InMemoryStateAdapter  # IStatePort

# ---- Heavy adapters (deferred — import from their module directly) --------
# These pull in large dependency chains (Gemini SDK, UltraBERT DLL, etc.)
# and must be imported from their individual modules:
#
#   from k1.concierge.adapters.test_llm import TestModelHubBridge
#   from k1.concierge.adapters.hub_llm import ModelHubPOCBridge
#   from k1.concierge.adapters.ultrabert_classification import UltraBERTPhase1Pipeline
#   from k1.concierge.adapters.local_delta import BusFactory

__all__ = [
    # Test adapters (eagerly imported)
    "TestInputAdapter",
    "TestOutputAdapter",
    "StubPhase1Pipeline",
    "InMemoryStateAdapter",
    "MockDispatchAdapter",
    "create_test_bus",
    "MockMemoryAdapter",
    # Production adapters (eagerly imported)
    "BusInputAdapter",
    "BusOutputAdapter",
    "SSMStateAdapter",
    "FabricDispatchAdapter",
    "RecallMemoryAdapter",
    # Null / startup-tier adapters (Phase 2)
    "NullSessionStateReaderAdapter",
    "NullDeltaBusAdapter",
    "NullEventSubscriptionAdapter",
    "NullBridgeWriteAdapter",
    "SnapshotStateReadAdapter",
]
