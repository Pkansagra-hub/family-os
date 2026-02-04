# SessionState API Reference

> **Authoritative API documentation for SessionState consumers.**
> Generated from docstrings and implementation.

## Overview

SessionState provides session memory management for K1 with:
- 96KB total budget (48KB HOT + 48KB WARM)
- 40-turn conversation retention
- Edge-first offline support (LOCAL COLD)
- Single-writer pattern (via Concierge)
- FlatBuffer serialization (<100μs)

---

## Quick Start

```python
from k1.sessionstate import SessionStateFactory

# Create and start standalone manager
manager = SessionStateFactory.create_standalone()
manager.start()

# Mutate session state
result = manager.mutate(
    section="beliefs_active",
    operation="add",
    data={"subject": "user", "predicate": "prefers", "object": "dark mode"},
)

# Check health
snapshot = manager.get_snapshot()
print(f"HOT: {snapshot.hot_utilization_pct:.1f}%, WARM: {snapshot.warm_utilization_pct:.1f}%")

# Stop with checkpoint
manager.stop()
```

---

## Core Classes

### SessionStateManager

Central facade for all SessionState operations.

```python
class SessionStateManager:
    """
    Orchestrates HotTier, WarmTier, LocalColdTier, and kernel services
    (SizeTracker, MutationGuard, EvictionEngine, MigrationEngine).

    Pattern:
        - Single instance per session
        - Single-writer (only Concierge writes via IWriterPort)
        - Multi-reader (lock-free reads, <1ms latency)
    """
```

#### Properties

| Property | Type | Description |
|----------|------|-------------|
| `session_id` | `str` | Unique session identifier |
| `state` | `ManagerState` | Current lifecycle state |
| `is_running` | `bool` | Whether session is in RUNNING state |
| `hot` | `HotTier` | HOT tier manager (8 sections, 48KB) |
| `warm` | `WarmTier` | WARM tier manager (4 sections, 48KB) |
| `local_cold` | `LocalColdTier` | LOCAL COLD archive (K1 SQLite) |
| `size_tracker` | `SizeTracker` | Per-section byte accounting |
| `mutation_guard` | `MutationGuard` | Preflight validation engine |
| `eviction_engine` | `EvictionEngine` | WARM → LOCAL COLD eviction |
| `migration_engine` | `MigrationEngine` | HOT ↔ WARM migration |

#### Lifecycle Methods

| Method | Signature | Returns | Description |
|--------|-----------|---------|-------------|
| `start` | `start(restore_if_exists: bool = True)` | `StartResult` | Start session, optionally restore from checkpoint |
| `stop` | `stop(checkpoint_before_stop: bool = True)` | `StopResult` | Stop session, optionally checkpoint first |
| `checkpoint` | `checkpoint()` | `CheckpointResult` | Manual checkpoint to LOCAL COLD |
| `restore` | `restore(session_id: str)` | `RestoreResult` | Restore from LOCAL COLD or K0 |

#### Read Methods (Lock-Free, <1ms)

| Method | Signature | Returns | Description |
|--------|-----------|---------|-------------|
| `get_section` | `get_section(name: str)` | `Section` | Get section by name |
| `get_hot` | `get_hot()` | `HotTier` | Get HOT tier manager |
| `get_warm` | `get_warm()` | `WarmTier` | Get WARM tier manager |
| `get_local_cold` | `get_local_cold()` | `LocalColdTier` | Get LOCAL COLD tier |
| `get_snapshot` | `get_snapshot()` | `SessionSnapshot` | Get complete health snapshot |

#### Write Methods (Single Writer)

| Method | Signature | Returns | Description |
|--------|-----------|---------|-------------|
| `mutate` | `mutate(section: str, operation: str, data: Any, estimated_bytes: Optional[int] = None)` | `MutationResult` | Apply mutation to section |

**Mutation Flow:**
1. `MutationGuard.preflight()` - Check capacity
2. If rejected: emit `MutationRejectedEvent`, return rejection
3. If approved: apply mutation
4. `SizeTracker.update()` - Update byte counts
5. Check pressure levels
6. If ELEVATED: trigger `MigrationEngine`
7. If CRITICAL: trigger `EvictionEngine`
8. Emit `MutationApprovedEvent`

---

### SessionStateFactory

Factory for creating SessionStateManager instances with appropriate adapters.

```python
class SessionStateFactory:
    """
    Supports three creation modes:
    1. create_standalone(): For development, testing, offline operation
    2. create_for_testing(): For fast unit tests (in-memory)
    3. create_with_ports(): For production with injected adapters
    """
```

#### Factory Methods

| Method | Signature | Description |
|--------|-----------|-------------|
| `create_standalone` | `create_standalone(session_id: Optional[str] = None, db_path: Optional[Path] = None, checkpoint_interval_s: float = 30.0)` | SQLite LOCAL COLD, periodic checkpoints |
| `create_for_testing` | `create_for_testing(session_id: Optional[str] = None)` | In-memory storage, capture mode events |
| `create_with_ports` | `create_with_ports(session_id: str, storage: IStoragePort, events: IEventPort, writer: IWriterPort, lifecycle: ILifecyclePort, k0_sync: Optional[IK0SyncPort] = None)` | Production wiring with injected ports |

#### Convenience Functions

```python
# Module-level convenience functions
from k1.sessionstate import create_standalone, create_for_testing

manager = create_standalone(session_id="dev-123")
test_manager = create_for_testing()
```

---

## Result Dataclasses

### MutationResult

Result of a mutation operation.

```python
@dataclass
class MutationResult:
    success: bool           # Whether mutation was applied
    section: str            # Target section name
    operation: str          # Operation performed
    bytes_delta: int        # Change in bytes (+/-)
    new_size_bytes: int     # New section size
    available_bytes: int    # Remaining capacity
    pressure: PressureLevel # Pressure after mutation
    error: Optional[str]    # Error message if failed
    reason: str             # Rejection reason if rejected

    # Factory methods
    @classmethod
    def rejected(cls, section, operation, reason, available_bytes) -> MutationResult
    @classmethod
    def failure(cls, section, operation, error) -> MutationResult
```

### StartResult

Result of start operation.

```python
@dataclass
class StartResult:
    success: bool            # Whether start succeeded
    session_id: str          # Session that was started
    duration_ms: float       # Time taken to start
    restored: bool           # Whether restored from checkpoint
    restore_source: str      # 'local_cold', 'k0', or 'fresh'
    error: Optional[str]     # Error message if failed
```

### StopResult

Result of stop operation.

```python
@dataclass
class StopResult:
    success: bool                   # Whether stop succeeded
    checkpoint_id: Optional[str]    # ID of final checkpoint
    duration_ms: float              # Time taken to stop
    error: Optional[str]            # Error message if failed
```

### CheckpointResult

Result of checkpoint operation.

```python
@dataclass
class CheckpointResult:
    success: bool         # Whether checkpoint succeeded
    checkpoint_id: str    # Unique checkpoint identifier
    size_bytes: int       # Total bytes checkpointed
    duration_ms: float    # Time taken
    sla_met: bool         # Whether <50ms SLA was met
    error: Optional[str]  # Error message if failed
```

### RestoreResult

Result of restore operation.

```python
@dataclass
class RestoreResult:
    success: bool                # Whether restore succeeded
    source: str                  # 'local_cold', 'k0', or 'fresh'
    sections_restored: List[str] # Sections that were restored
    hot_restored: bool           # Whether HOT fully restored
    warm_restored: bool          # Whether WARM fully restored
    duration_ms: float           # Time taken
    sla_met: bool                # Whether SLA was met
    error: Optional[str]         # Error message if failed
```

### SessionSnapshot

Complete session state snapshot for diagnostics.

```python
@dataclass
class SessionSnapshot:
    session_id: str                    # Session identifier
    total_size_bytes: int              # Total bytes used
    hot_size_bytes: int                # HOT tier bytes
    warm_size_bytes: int               # WARM tier bytes
    hot_utilization_pct: float         # HOT tier % (0-100)
    warm_utilization_pct: float        # WARM tier % (0-100)
    total_utilization_pct: float       # Total % (0-100)
    pressure: PressureLevel            # Overall pressure
    sections: Dict[str, SectionInfo]   # Per-section info
    last_mutation_ms: int              # Last mutation timestamp
    is_running: bool                   # Manager running state
    timestamp_ms: int                  # Snapshot timestamp
```

### SectionInfo

Information about a single section.

```python
@dataclass
class SectionInfo:
    name: str                  # Section name
    tier: str                  # 'hot' or 'warm'
    size_bytes: int            # Current size
    budget_bytes: int          # Maximum allowed
    utilization_pct: float     # Current % (0-100)
    pressure: PressureLevel    # Section pressure
```

---

## Enums

### ManagerState

SessionStateManager lifecycle states.

```python
class ManagerState(str, Enum):
    CREATED = "created"    # Initial, not started
    STARTING = "starting"  # Initializing/restoring
    RUNNING = "running"    # Active, accepting mutations
    STOPPING = "stopping"  # Shutting down
    STOPPED = "stopped"    # Stopped, can restart
    ERROR = "error"        # Error state
```

### PressureLevel

Memory pressure levels.

```python
class PressureLevel(str, Enum):
    NORMAL = "normal"       # <80% utilization
    ELEVATED = "elevated"   # 80-90% (migration triggers)
    CRITICAL = "critical"   # 90-95% (eviction triggers)
    EMERGENCY = "emergency" # >95% (immediate action)
```

---

## Sections

### HOT CORE Sections (48KB Total)

| Section | Budget | Description | Eviction |
|---------|--------|-------------|----------|
| `control` | 8KB | System control block | NEVER |
| `beliefs_active` | 8KB | Active beliefs | On pressure |
| `scoreboard` | 6KB | Task progress | On pressure |
| `history_active` | 8KB | Recent turns | On pressure |
| `clarifications` | 4KB | Pending clarifications | On pressure |
| `affective_now` | 4KB | Current mood | On pressure |
| `narrative_active` | 4KB | Active threads | On pressure |
| `meta` | 2KB | Metadata | On pressure |

### WARM TIER Sections (48KB Total)

| Section | Budget | Eviction Priority | Description |
|---------|--------|-------------------|-------------|
| `telemetry` | 8KB | 1 (first) | Performance metrics |
| `beliefs_history` | 12KB | 2 | Belief change log |
| `history_recent` | 20KB | 3 | Recent turn archive |
| `persona` | 8KB | 4 (last) | User persona data |

---

## Exceptions

### SectionNotFoundError

Raised when a section name is invalid.

```python
class SectionNotFoundError(KeyError):
    def __init__(self, section: str):
        self.section = section
```

### MutationRejectedError

Raised when a mutation is rejected by MutationGuard.

```python
class MutationRejectedError(Exception):
    def __init__(self, reason: str, available_kb: float = 0.0):
        self.reason = reason
        self.available_kb = available_kb
```

### LifecycleError

Raised when lifecycle operation fails.

```python
class LifecycleError(Exception):
    pass
```

### PortProtocolError

Raised when a port doesn't implement required protocol.

```python
class PortProtocolError(Exception):
    def __init__(self, port_name: str, expected: type, got: type):
        self.port_name = port_name
        self.expected = expected
        self.got = got
```

---

## Ports (Interfaces)

| Port | Purpose | Standalone Adapter | Production Adapter |
|------|---------|-------------------|-------------------|
| `IStoragePort` | LOCAL COLD persistence | `SQLiteStorageAdapter` | `SQLiteStorageAdapter` |
| `IEventPort` | Event emission | `LocalEventAdapter` | `DeltaBusAdapter` (future) |
| `IWriterPort` | Mutation coordination | `DirectWriterAdapter` | `ConciergeAdapter` (future) |
| `ILifecyclePort` | Lifecycle management | `StandaloneLifecycle` | `FabricLifecycle` (future) |
| `IK0SyncPort` | Optional K0 cloud sync | `NullSyncPort` | `BridgeSyncAdapter` (future) |

See [PORTS_OVERVIEW.md](PORTS_OVERVIEW.md) for detailed port documentation.

---

## Events

| Event Type | Description | Payload |
|------------|-------------|---------|
| `mutation.requested` | Mutation requested | `MutationRequestedEvent` |
| `mutation.approved` | Mutation accepted | `MutationApprovedEvent` |
| `mutation.rejected` | Mutation rejected | `MutationRejectedEvent` |
| `eviction.triggered` | Eviction started | `EvictionTriggeredEvent` |
| `eviction.completed` | Eviction finished | `EvictionCompletedEvent` |
| `emergency.activated` | Emergency pressure | `EmergencyActivatedEvent` |
| `emergency.resolved` | Emergency resolved | `EmergencyResolvedEvent` |
| `reconstruction.started` | COLD restore started | `ReconstructionStartedEvent` |

---

## Complete Usage Example

```python
from k1.sessionstate import (
    SessionStateFactory,
    MutationResult,
    SessionSnapshot,
    PressureLevel,
)

# Create standalone manager
manager = SessionStateFactory.create_standalone(
    session_id="user-session-001",
    checkpoint_interval_s=30.0,
)

# Start session (restores from checkpoint if exists)
result = manager.start(restore_if_exists=True)
if not result.success:
    raise RuntimeError(f"Failed to start: {result.error}")

print(f"Session started: {result.session_id}")
print(f"Restored: {result.restored} from {result.restore_source}")

# Add belief
belief_result = manager.mutate(
    section="beliefs_active",
    operation="add",
    data={
        "subject": "user",
        "predicate": "prefers",
        "object": "dark mode",
        "confidence": 0.95,
    },
)

if belief_result.success:
    print(f"Belief added: {belief_result.bytes_delta} bytes")
    print(f"Section size: {belief_result.new_size_bytes} bytes")
    print(f"Available: {belief_result.available_bytes} bytes")
else:
    print(f"Rejected: {belief_result.reason}")

# Check health snapshot
snapshot = manager.get_snapshot()
print(f"HOT: {snapshot.hot_utilization_pct:.1f}%")
print(f"WARM: {snapshot.warm_utilization_pct:.1f}%")
print(f"Pressure: {snapshot.pressure.value}")

# Manual checkpoint
checkpoint = manager.checkpoint()
if checkpoint.success:
    print(f"Checkpoint: {checkpoint.checkpoint_id}")
    print(f"Size: {checkpoint.size_bytes} bytes")
    print(f"SLA met: {checkpoint.sla_met}")

# Stop with final checkpoint
stop_result = manager.stop(checkpoint_before_stop=True)
print(f"Stopped: {stop_result.success}")
```

---

## Related Documentation

- [INTEGRATION_GUIDE.md](INTEGRATION_GUIDE.md) - Wiring to Bridge, DeltaBus, Concierge, Fabric
- [PORTS_OVERVIEW.md](PORTS_OVERVIEW.md) - Port interfaces and adapters
- [STORAGE_PORT.md](STORAGE_PORT.md) - Storage port details
- [EVENT_PORT.md](EVENT_PORT.md) - Event port details
- [WRITER_PORT.md](WRITER_PORT.md) - Writer port details
- [LIFECYCLE_PORT.md](LIFECYCLE_PORT.md) - Lifecycle port details
