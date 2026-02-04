# Lifecycle Port Documentation

## Purpose

The Lifecycle Port (`ILifecyclePort`) manages SessionState lifecycle operations including startup, shutdown, health monitoring, and checkpointing. It allows SessionState to be managed by Fabric (production) or standalone (development/testing).

## State Machine

```
                              ┌─────────────┐
                              │   CREATED   │
                              └──────┬──────┘
                                     │ start()
                                     ▼
                              ┌─────────────┐
                       ┌──────│  STARTING   │──────┐
                       │      └──────┬──────┘      │
                  failure           │ success    failure
                       │            │              │
                       ▼            ▼              │
                  ┌─────────┐  ┌─────────────┐     │
                  │  ERROR  │  │   RUNNING   │     │
                  └─────────┘  └──────┬──────┘     │
                       ▲              │            │
                       │         stop()            │
                       │              ▼            │
                       │      ┌─────────────┐      │
                       └──────│  STOPPING   │──────┘
                              └──────┬──────┘
                                     │ success
                                     ▼
                              ┌─────────────┐
          restart via reset() │   STOPPED   │
              ┌───────────────└──────┬──────┘
              │                      │
              ▼                      ▼
         (CREATED)            (can be discarded)
```

### State Transitions

| State | Description | Valid Operations |
|-------|-------------|------------------|
| `CREATED` | Initial state, not yet started | `start()` |
| `STARTING` | Initializing, restoring from COLD | wait |
| `RUNNING` | Active, accepting mutations | `stop()`, `checkpoint()`, `health()` |
| `STOPPING` | Shutting down, final checkpoint | `checkpoint()` (final) |
| `STOPPED` | Stopped, can restart via `reset()` | `reset()` |
| `ERROR` | Error state, requires intervention | `reset()` |

### State Helper Methods

```python
state = lifecycle.state

state.can_start()      # True for CREATED, STOPPED
state.can_stop()       # True for RUNNING
state.can_checkpoint() # True for RUNNING, STOPPING
state.is_operational() # True for RUNNING
state.is_terminal()    # True for STOPPED, ERROR
```

## Interface

```python
class ILifecyclePort(ABC):
    # Properties
    @property
    def state(self) -> LifecycleState: ...
    @property
    def session_id(self) -> str: ...
    @property
    def config(self) -> LifecycleConfig: ...
    @property
    def started_at_ms(self) -> int: ...
    @property
    def checkpoint_count(self) -> int: ...
    @property
    def last_checkpoint_ms(self) -> int: ...

    # Abstract Methods
    def start(self, restore_if_exists: bool = True) -> StartResult: ...
    def stop(self, checkpoint_before_stop: bool = True) -> StopResult: ...
    def health(self) -> HealthStatus: ...
    def checkpoint(self, trigger: CheckpointTrigger = CheckpointTrigger.MANUAL) -> CheckpointResult: ...

    # Default Methods
    def request_shutdown(self, reason: str = "") -> bool: ...
    def get_uptime_ms(self) -> int: ...
    def is_running(self) -> bool: ...
    def can_checkpoint(self) -> bool: ...
```

## Enums

### LifecycleState

```python
class LifecycleState(str, Enum):
    CREATED = "created"    # Initialized but not started
    STARTING = "starting"  # Start in progress
    RUNNING = "running"    # Normal operation
    STOPPING = "stopping"  # Stop in progress
    STOPPED = "stopped"    # Fully stopped
    ERROR = "error"        # Error state
```

### CheckpointTrigger

```python
class CheckpointTrigger(str, Enum):
    PERIODIC = "periodic"   # Timer-based (e.g., every 30s)
    MANUAL = "manual"       # Explicit checkpoint() call
    STOP = "stop"           # Final checkpoint before stop
    PRESSURE = "pressure"   # Memory pressure triggered
    EMERGENCY = "emergency" # Emergency mode checkpoint
    MIGRATION = "migration" # Before tier migration
    EVICTION = "eviction"   # Before eviction to LOCAL COLD
```

### RestoreSource

```python
class RestoreSource(str, Enum):
    FRESH = "fresh"           # No restore, fresh session
    LOCAL_COLD = "local_cold" # Restored from K1 SQLite
    K0 = "k0"                 # Restored from K0 cloud (future)
    CHECKPOINT = "checkpoint" # Restored from specific checkpoint
```

### PressureLevel

```python
class PressureLevel(str, Enum):
    NORMAL = "normal"     # < 70% utilization
    ELEVATED = "elevated" # 70-85% utilization
    HIGH = "high"         # 85-95% utilization
    CRITICAL = "critical" # > 95% utilization
```

## Data Types

### StartResult

```python
@dataclass
class StartResult:
    success: bool                           # Whether start succeeded
    state: LifecycleState                   # Final state after operation
    session_id: str                         # Session that was started
    restored: bool                          # Whether session was restored
    restore_source: RestoreSource           # Where data came from
    sections_restored: List[str]            # Sections that were restored
    duration_ms: float                      # Time taken to start
    error: Optional[str]                    # Error message if failed

    # Factory methods
    @classmethod
    def success_fresh(cls, session_id, duration_ms) -> StartResult
    @classmethod
    def success_restored(cls, session_id, source, sections, duration_ms) -> StartResult
    @classmethod
    def failure(cls, error, duration_ms=0.0) -> StartResult

    # Serialization
    def to_dict(self) -> Dict[str, Any]
    @classmethod
    def from_dict(cls, data) -> StartResult
```

### StopResult

```python
@dataclass
class StopResult:
    success: bool                           # Whether stop succeeded
    state: LifecycleState                   # Final state
    checkpoint_id: Optional[str]            # Final checkpoint ID (if any)
    checkpoint_size_bytes: int              # Size of final checkpoint
    duration_ms: float                      # Time taken to stop
    error: Optional[str]                    # Error message if failed

    # Factory methods
    @classmethod
    def success_with_checkpoint(cls, checkpoint_id, size_bytes, duration_ms) -> StopResult
    @classmethod
    def success_no_checkpoint(cls, duration_ms) -> StopResult
    @classmethod
    def failure(cls, error, duration_ms=0.0) -> StopResult
```

### HealthStatus

```python
@dataclass
class HealthStatus:
    healthy: bool                    # Overall health
    state: LifecycleState            # Current state
    pressure_level: PressureLevel    # Memory pressure
    hot_utilization_pct: float       # HOT tier utilization (0.0-1.0)
    warm_utilization_pct: float      # WARM tier utilization (0.0-1.0)
    total_size_bytes: int            # Total bytes used
    last_checkpoint_ms: int          # Last checkpoint timestamp
    checkpoint_count: int            # Checkpoints since start
    uptime_ms: int                   # Time since start
    turn_count: int                  # Turns processed
    mutation_count: int              # Mutations applied
    error: Optional[str]             # Error message if in ERROR state

    # Factory methods
    @classmethod
    def healthy_running(cls, pressure, hot_pct, warm_pct, total_bytes,
                        last_checkpoint_ms, checkpoint_count, uptime_ms,
                        turn_count=0, mutation_count=0) -> HealthStatus
    @classmethod
    def unhealthy(cls, state, error, pressure=PressureLevel.NORMAL) -> HealthStatus
```

### CheckpointResult

```python
@dataclass
class CheckpointResult:
    success: bool                           # Whether checkpoint succeeded
    checkpoint_id: str                      # Unique checkpoint ID
    trigger: CheckpointTrigger              # What triggered this
    size_bytes: int                         # Total bytes checkpointed
    sections_checkpointed: List[str]        # Sections included
    duration_ms: float                      # Time taken
    sla_met: bool                           # Whether <50ms SLA was met
    error: Optional[str]                    # Error message if failed

    # SLA threshold
    SLA_THRESHOLD_MS: float = 50.0

    # Factory methods
    @classmethod
    def success_checkpoint(cls, checkpoint_id, trigger, size_bytes,
                           sections, duration_ms) -> CheckpointResult
    @classmethod
    def failure(cls, error, trigger=CheckpointTrigger.MANUAL,
                duration_ms=0.0) -> CheckpointResult
```

### LifecycleConfig

```python
@dataclass
class LifecycleConfig:
    checkpoint_interval_ms: int = 30000     # Periodic checkpoint (0 = disabled)
    restore_on_start: bool = True           # Restore from storage on start
    checkpoint_on_stop: bool = True         # Checkpoint before stop
    max_start_duration_ms: int = 5000       # Max start time
    max_stop_duration_ms: int = 5000        # Max stop time
    health_check_interval_ms: int = 0       # Health check frequency (0 = on-demand)

    # Factory methods
    @classmethod
    def default(cls) -> LifecycleConfig
    @classmethod
    def testing(cls) -> LifecycleConfig  # No timers, no restore
```

## Checkpoint Behavior

### Checkpoint Triggers

| Trigger | When | Purpose |
|---------|------|---------|
| PERIODIC | Every N seconds | Durability guarantee |
| MANUAL | Explicit call | User/system requested |
| STOP | During shutdown | Final state preservation |
| PRESSURE | Memory critical | Free memory before eviction |
| EMERGENCY | System overload | Emergency state save |
| MIGRATION | Tier migration | Pre-migration snapshot |
| EVICTION | Before eviction | Archive before purge |

### Checkpoint SLA

Target: **<50ms** for LOCAL COLD write

```python
result = lifecycle.checkpoint(CheckpointTrigger.MANUAL)
if result.success:
    print(f"Checkpoint {result.checkpoint_id}")
    print(f"Size: {result.size_bytes} bytes")
    print(f"Duration: {result.duration_ms}ms")
    print(f"SLA met: {result.sla_met}")  # True if <50ms
```

### Periodic Checkpoints

StandaloneLifecycle runs automatic checkpoints:

```python
# Default: every 30 seconds
lifecycle = StandaloneLifecycle(manager)

# Custom interval
lifecycle = StandaloneLifecycle(manager, checkpoint_interval_s=60.0)

# Disabled
lifecycle = StandaloneLifecycle(manager, checkpoint_interval_s=0)
```

### Shutdown Checkpoint

Stop performs final checkpoint by default:

```python
# With final checkpoint (default)
result = lifecycle.stop()
print(f"Final checkpoint: {result.checkpoint_id}")

# Skip final checkpoint
result = lifecycle.stop(checkpoint_before_stop=False)
```

## Adapters

### StandaloneLifecycle (Standalone Mode)

Self-managed lifecycle for development and testing. No Fabric coordination.

```python
from k1.sessionstate.adapters import StandaloneLifecycle

manager = SessionStateManager(session_id="test-session")
lifecycle = StandaloneLifecycle(
    manager,
    checkpoint_interval_s=30.0,  # Optional: override interval
)

# Start with restore
result = lifecycle.start()
if result.restored:
    print(f"Restored from {result.restore_source}")

# Check health
health = lifecycle.health()
print(f"Healthy: {health.healthy}")
print(f"Pressure: {health.pressure_level}")
print(f"Uptime: {health.uptime_ms}ms")

# Manual checkpoint
checkpoint = lifecycle.checkpoint(CheckpointTrigger.MANUAL)
print(f"Checkpoint: {checkpoint.checkpoint_id}")

# Stop with final checkpoint
result = lifecycle.stop()
print(f"Stopped, final checkpoint: {result.checkpoint_id}")
```

**Features:**
- Periodic checkpoint timer (daemon thread)
- Graceful shutdown with final checkpoint
- Health reporting with pressure monitoring
- Context manager support
- Restart capability

**Context Manager:**

```python
with StandaloneLifecycle(manager) as lifecycle:
    # SessionState is running
    health = lifecycle.health()
    print(f"Running: {health.healthy}")
# SessionState is stopped with checkpoint
```

**Restart:**

```python
lifecycle.start()
lifecycle.stop()
lifecycle.reset()  # Reset to CREATED
lifecycle.start()  # Start again
```

**Testing Utilities:**

```python
# Force error state
lifecycle.force_error("Test error")
assert lifecycle.state == LifecycleState.ERROR

# Reset from error
lifecycle.reset()
assert lifecycle.state == LifecycleState.CREATED
```

### FabricLifecycleAdapter (Production - Future)

Fabric-coordinated lifecycle for production. Multi-session management.

```python
from k1.fabric import FabricLifecycleAdapter

fabric = Fabric()
adapter = FabricLifecycleAdapter(fabric, session_id="abc-123")

# Fabric controls lifecycle externally
# Coordinated with other K1 components
```

**Features:**
- Fabric-coordinated lifecycle
- Multi-session management
- Health reporting to Fabric
- Distributed checkpointing

## Startup Sequence

```
1. CREATED -> STARTING
   └─ Validate state (must be CREATED or STOPPED)

2. Restore from LOCAL COLD (if configured)
   └─ If restore_on_start=True and checkpoint exists:
      └─ Load checkpoint, hydrate sections
   └─ If no checkpoint:
      └─ Initialize empty sections

3. Start checkpoint timer (if configured)
   └─ If checkpoint_interval_ms > 0:
      └─ Create daemon Timer thread

4. STARTING -> RUNNING
   └─ Record started_at_ms
   └─ Reset checkpoint_count
```

## Shutdown Sequence

```
1. RUNNING -> STOPPING
   └─ Validate state (must be RUNNING)

2. Cancel checkpoint timer
   └─ Timer.cancel()

3. Final checkpoint (if configured)
   └─ If checkpoint_on_stop=True:
      └─ checkpoint(CheckpointTrigger.STOP)
      └─ Record checkpoint_id, size_bytes

4. Stop manager
   └─ Release resources

5. STOPPING -> STOPPED
```

## Error Handling

### InvalidStateError

Raised when an operation is invalid for the current state:

```python
from k1.sessionstate.ports.lifecycle import InvalidStateError

try:
    lifecycle.reset()  # Only valid from STOPPED or ERROR
except InvalidStateError as e:
    print(f"Current state: {e.current_state}")
    print(f"Operation: {e.operation}")
    print(f"Valid states: {e.valid_states}")
```

### Health Determination

```python
healthy = (
    state == LifecycleState.RUNNING and
    pressure_level != PressureLevel.CRITICAL
)
```

| State | Pressure | healthy |
|-------|----------|---------|
| RUNNING | NORMAL | True |
| RUNNING | ELEVATED | True |
| RUNNING | HIGH | True |
| RUNNING | CRITICAL | False |
| ERROR | any | False |
| STOPPED | any | False |

## Thread Safety

StandaloneLifecycle is thread-safe:

- State transitions protected by `RLock`
- Checkpoint timer runs on daemon thread
- `health()` safe from any thread
- Properties are atomic reads

## Integration with Fabric (Future)

In production, Fabric manages lifecycle:

```
┌─────────────────────────────────────────────────────────────┐
│                          Fabric                              │
│  ┌────────────────┐  ┌────────────────┐  ┌────────────────┐ │
│  │  SessionState  │  │  SessionState  │  │  SessionState  │ │
│  │   (session A)  │  │   (session B)  │  │   (session C)  │ │
│  │       │        │  │       │        │  │       │        │ │
│  │       ▼        │  │       ▼        │  │       ▼        │ │
│  │FabricLifecycle │  │FabricLifecycle │  │FabricLifecycle │ │
│  └───────┬────────┘  └───────┬────────┘  └───────┬────────┘ │
│          │                   │                   │          │
│          └───────────────────┴───────────────────┘          │
│                              │                              │
│                    Coordinated by Fabric                    │
│           (health checks, scaling, failover)                │
└─────────────────────────────────────────────────────────────┘
```

Fabric provides:
- Session health monitoring
- Automatic restart on failure
- Coordinated checkpointing
- Resource management

## Related Files

- Interface: [k1/sessionstate/ports/lifecycle.py](../ports/lifecycle.py)
- Adapter: [k1/sessionstate/adapters/standalone_lifecycle.py](../adapters/standalone_lifecycle.py)
- Manager: [k1/sessionstate/manager.py](../manager.py)
- Tests: [tests/k1/sessionstate/test_ports.py](../../../tests/k1/sessionstate/test_ports.py)
