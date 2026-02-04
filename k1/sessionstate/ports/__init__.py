"""
SessionState Ports Package - Interface Definitions
===================================================

This package contains ABC/Protocol definitions for SessionState ports.
Ports define what SessionState EXPECTS from external systems.

Ports:
- IStoragePort: Persistence layer interface
- IEventPort: Event bus interface
- IWriterPort: Single-writer pattern interface
- ILifecyclePort: Lifecycle management interface
- IK0SyncPort: Optional K0 cloud sync interface

See: docs/plans/sessionstate-implementation-plan.md
Epic 3.1-3.4: Interface Definition
"""

from .events import IEventPort
from .k0_sync import IK0SyncPort
from .lifecycle import (
    CheckpointResult,
    CheckpointTrigger,
    HealthStatus,
    ILifecyclePort,
    InvalidStateError,
    LifecycleConfig,
    LifecycleState,
    PressureLevel,
    RestoreSource,
    StartResult,
    StopResult,
)
from .storage import ArchiveEntry, ArchiveResult, IStoragePort, RestoreResult
from .writer import (
    BatchRequest,
    BatchResult,
    IWriterPort,
    MutationPriority,
    MutationRequest,
    MutationResponse,
    MutationStatus,
    RejectionCategory,
    WriterAuthorization,
)

__all__ = [
    # Storage port
    "IStoragePort",
    "ArchiveResult",
    "RestoreResult",
    "ArchiveEntry",
    # Event port
    "IEventPort",
    # Writer port
    "IWriterPort",
    "MutationRequest",
    "MutationResponse",
    "BatchRequest",
    "BatchResult",
    "MutationPriority",
    "MutationStatus",
    "RejectionCategory",
    "WriterAuthorization",
    # Lifecycle port
    "ILifecyclePort",
    "LifecycleState",
    "LifecycleConfig",
    "CheckpointTrigger",
    "RestoreSource",
    "PressureLevel",
    "StartResult",
    "StopResult",
    "HealthStatus",
    "CheckpointResult",
    "InvalidStateError",
    # K0 Sync port
    "IK0SyncPort",
]
