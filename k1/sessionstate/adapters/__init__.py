"""
SessionState Adapters Package - Port Implementations
=====================================================

This package contains implementations of SessionState ports.
Adapters connect SessionState to external systems.

Adapters for Standalone Mode (NOW):
- SQLiteStorageAdapter: LOCAL COLD persistence
- InMemoryStorageAdapter: Fast testing
- LocalEventAdapter: In-process event dispatch
- DirectWriterAdapter: Direct mutation
- StandaloneLifecycle: Self-managed lifecycle

Production Adapter Stubs (MS-2+ -- raise NotImplementedError):
- BridgeStorageAdapter: K0 cloud storage via Bridge
- DeltaBusAdapter: K1 Bus event dispatch
- ConciergeWriterAdapter: Concierge-routed mutations
- FabricLifecycleAdapter: Fabric-managed lifecycle
- BridgeSyncAdapter: K0 cloud sync via Bridge

See: docs/plans/sessionstate-implementation-plan.md
Epic 3.1-3.4: Interface Definition & Adapters
"""

from .bridge_storage import BridgeStorageAdapter
from .bridge_sync import BridgeSyncAdapter
from .concierge_writer import ConciergeWriterAdapter
from .delta_bus import DeltaBusAdapter
from .direct_writer import DirectWriterAdapter
from .fabric_lifecycle import FabricLifecycleAdapter
from .local_events import LocalEventAdapter
from .memory_storage import InMemoryStorageAdapter
from .sqlite_storage import SQLiteStorageAdapter
from .standalone_lifecycle import StandaloneLifecycle

__all__ = [
    # Standalone (working now)
    "SQLiteStorageAdapter",
    "InMemoryStorageAdapter",
    "LocalEventAdapter",
    "DirectWriterAdapter",
    "StandaloneLifecycle",
    # Production stubs (MS-2+)
    "BridgeStorageAdapter",
    "DeltaBusAdapter",
    "ConciergeWriterAdapter",
    "FabricLifecycleAdapter",
    "BridgeSyncAdapter",
]
