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

Adapters for Production (FUTURE - provided by other packages):
- BridgeStorageAdapter: K0 sync (from bridge/)
- DeltaBusAdapter: Event bus (from k1/bus/)
- ConciergeAdapter: Single writer (from k1/concierge/)
- FabricLifecycle: Managed lifecycle (from k1/fabric/)

See: docs/plans/sessionstate-implementation-plan.md
Epic 3.1-3.4: Interface Definition & Adapters
"""

from .direct_writer import DirectWriterAdapter
from .local_events import LocalEventAdapter
from .memory_storage import InMemoryStorageAdapter
from .sqlite_storage import SQLiteStorageAdapter
from .standalone_lifecycle import StandaloneLifecycle

__all__ = [
    "SQLiteStorageAdapter",
    "InMemoryStorageAdapter",
    "LocalEventAdapter",
    "DirectWriterAdapter",
    "StandaloneLifecycle",
]
