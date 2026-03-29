"""
SessionState Package - K1 Session Memory Management
====================================================

IMPLEMENTATION PLAN: docs/plans/sessionstate-implementation-plan.md

SessionState provides:
- 96KB session memory (48KB HOT + 48KB WARM)
- 40-turn conversation retention
- Edge-first offline support (LOCAL COLD)
- Single-writer pattern (Concierge)
- FlatBuffer serialization (<100μs)

Quick Start (Standalone Mode):
    from k1.sessionstate import SessionStateFactory

    # Create standalone manager
    manager = SessionStateFactory.create_standalone()

    # Start session
    manager.start()

    # Access sections
    control = manager.get_section("control")
    control.advance_turn()

    # Mutate with write coordination
    result = manager.mutate(
        section="beliefs_active",
        operation="add",
        data={"subject": "user", "predicate": "prefers", "object": "dark mode"},
    )

    # Get snapshot
    snapshot = manager.get_snapshot()

    # Stop (with checkpoint)
    manager.stop()

Architecture:
    ┌─────────────────────────────────────────────────────────┐
    │                   SessionStateManager                    │
    │  ┌─────────┐ ┌─────────┐ ┌─────────┐ ┌─────────────────┐│
    │  │ HotTier │ │WarmTier │ │LocalCold│ │ MutationGuard   ││
    │  │  48KB   │ │  48KB   │ │ SQLite  │ │ SizeTracker     ││
    │  └─────────┘ └─────────┘ └─────────┘ │ EvictionEngine  ││
    │       ↓           ↓           ↓      │ MigrationEngine ││
    │    8 sections  4 sections  Archive   └─────────────────┘│
    └─────────────────────────────────────────────────────────┘

    Ports (Dependency Injection):
    ├── IStoragePort     → SQLiteStorageAdapter / InMemoryStorageAdapter
    ├── IEventPort       → LocalEventAdapter / DeltaBusAdapter (future)
    ├── IWriterPort      → DirectWriterAdapter / ConciergeAdapter (future)
    ├── ILifecyclePort   → StandaloneLifecycle / FabricLifecycle (future)
    └── IK0SyncPort      → NullSyncPort / BridgeSyncAdapter (future)

See README.md for full documentation.
"""

__version__ = "0.1.0"

# Adapters
from .adapters import (
    DirectWriterAdapter,
    InMemoryStorageAdapter,
    LocalEventAdapter,
    SQLiteStorageAdapter,
    StandaloneLifecycle,
)

# Event types
from .events import (
    EmergencyActivatedEvent,
    EmergencyLevel,
    EmergencyResolvedEvent,
    EventType,
    EvictionCompletedEvent,
    EvictionTriggeredEvent,
    MutationApprovedEvent,
    MutationRejectedEvent,
    MutationRequestedEvent,
    PressureLevel,
    ReconstructionStartedEvent,
    SessionStateEvents,
)

# Engines
from .eviction import EvictionEngine, EvictionResult

# Core manager and factory
from .factory import PortProtocolError, SessionStateFactory, create_for_testing, create_standalone
from .guard import Approval, MutationGuard, RejectionReason

# Local cold archive
from .local_cold import LocalColdArchive

# Logging
from .logging import (
    LogEventType,
    SessionStateJsonFormatter,
    SessionStateLogger,
    StructuredLogRecord,
    configure_logger,
    get_default_logger,
)
from .manager import (
    CheckpointResult,
    LifecycleError,
    ManagerState,
    MutationRejectedError,
    MutationResult,
    RestoreResult,
    SectionInfo,
    SectionNotFoundError,
    SessionSnapshot,
    SessionStateManager,
    StartResult,
    StopResult,
)

# Metrics
from .metrics import PressureLevelValue, SessionStateMetrics, get_default_metrics
from .migration import MigrationEngine, MigrationResult

# Ports (interfaces)
from .ports import IEventPort, IK0SyncPort, ILifecyclePort, IStoragePort, IWriterPort
from .reconstruction import ReconstructionResult, ReconstructionSLA

# Sections
from .sections import (  # HOT CORE; WARM TIER
    AffectiveNowSection,
    BeliefsActiveSection,
    BeliefsHistorySection,
    ClarificationsSection,
    ControlSection,
    HistoryActiveSection,
    HistoryRecentSection,
    MetaSection,
    NarrativeActiveSection,
    PersonaSection,
    ScoreboardSection,
    TelemetrySection,
)

# Size and guard
from .sizetracker import SizeTracker
from .snapshot import SnapshotAPI

# Tiers
from .tiers import HotTier, LocalColdTier, WarmTier

__all__ = [
    # Version
    "__version__",
    # Manager
    "SessionStateManager",
    "SessionStateFactory",
    "create_standalone",
    "create_for_testing",
    "PortProtocolError",
    "MutationResult",
    "SessionSnapshot",
    "SectionInfo",
    "ManagerState",
    "StartResult",
    "StopResult",
    "CheckpointResult",
    "RestoreResult",
    "SectionNotFoundError",
    "MutationRejectedError",
    "LifecycleError",
    # Events
    "EventType",
    "PressureLevel",
    "EmergencyLevel",
    "MutationApprovedEvent",
    "MutationRejectedEvent",
    "SectionPressureEvent",
    "TierEmergencyEvent",
    "EvictionStartedEvent",
    "EvictionCompletedEvent",
    "CheckpointCreatedEvent",
    "ReconstructionCompletedEvent",
    "SessionStateEvents",
    # Size and guard
    "SizeTracker",
    "MutationGuard",
    "Approval",
    "RejectionReason",
    # Engines
    "EvictionEngine",
    "EvictionResult",
    "MigrationEngine",
    "MigrationResult",
    "ReconstructionSLA",
    "ReconstructionResult",
    "SnapshotAPI",
    # Local cold
    "LocalColdArchive",
    # Logging
    "SessionStateLogger",
    "SessionStateJsonFormatter",
    "StructuredLogRecord",
    "LogEventType",
    "get_default_logger",
    "configure_logger",
    # Metrics
    "SessionStateMetrics",
    "PressureLevelValue",
    "get_default_metrics",
    # Ports
    "IStoragePort",
    "IEventPort",
    "IWriterPort",
    "ILifecyclePort",
    "IK0SyncPort",
    # Adapters
    "SQLiteStorageAdapter",
    "InMemoryStorageAdapter",
    "LocalEventAdapter",
    "DirectWriterAdapter",
    "StandaloneLifecycle",
    # HOT CORE Sections
    "ControlSection",
    "BeliefsActiveSection",
    "ScoreboardSection",
    "HistoryActiveSection",
    "ClarificationsSection",
    "AffectiveNowSection",
    "NarrativeActiveSection",
    "MetaSection",
    # WARM TIER Sections
    "BeliefsHistorySection",
    "HistoryRecentSection",
    "PersonaSection",
    "TelemetrySection",
    # Tiers
    "HotTier",
    "WarmTier",
    "LocalColdTier",
]
