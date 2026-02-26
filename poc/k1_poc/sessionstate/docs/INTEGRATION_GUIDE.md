# SessionState Integration Guide

> **How to wire SessionState to K1 components: Bridge, DeltaBus, Concierge, Fabric.**

## Overview

SessionState uses the **Ports & Adapters** pattern for pluggable integration:

- **Standalone Mode**: Development, testing, offline operation
- **Production Mode**: Full K1 integration with Bridge, DeltaBus, Concierge, Fabric

```
┌─────────────────────────────────────────────────────────────────┐
│                       SessionStateManager                        │
├─────────────────────────────────────────────────────────────────┤
│  IStoragePort ───────► SQLiteStorageAdapter (LOCAL COLD)        │
│                   └──► BridgeStorageAdapter (K0 sync - future)  │
│                                                                  │
│  IEventPort ─────────► LocalEventAdapter (standalone)           │
│                   └──► DeltaBusAdapter (production - future)    │
│                                                                  │
│  IWriterPort ────────► DirectWriterAdapter (standalone)         │
│                   └──► ConciergeAdapter (production - future)   │
│                                                                  │
│  ILifecyclePort ─────► StandaloneLifecycle (standalone)         │
│                   └──► FabricLifecycle (production - future)    │
│                                                                  │
│  IK0SyncPort ────────► NullSyncPort (standalone)                │
│                   └──► BridgeSyncAdapter (production - future)  │
└─────────────────────────────────────────────────────────────────┘
```

---

## Integration Points

### 1. Concierge (Single Writer)

Concierge is the ONLY component that writes to SessionState.

```python
from k1.sessionstate import SessionStateFactory
from k1.concierge import ConciergeWriterAdapter

class Concierge:
    """
    Concierge manages sub-agent communication and SessionState writes.
    All mutations flow through Concierge.
    """

    def __init__(self, fabric, deltabus):
        # Create adapters
        storage = SQLiteStorageAdapter(db_path)
        events = DeltaBusAdapter(deltabus)
        lifecycle = FabricLifecycleAdapter(fabric)

        # Create writer adapter pointing back to self
        writer = ConciergeWriterAdapter(self)

        # Wire SessionState
        self.session = SessionStateFactory.create_with_ports(
            session_id=self._generate_session_id(),
            storage=storage,
            events=events,
            writer=writer,
            lifecycle=lifecycle,
        )

    def handle_sub_agent_mutation(self, request):
        """
        Sub-agents send mutation proposals to Concierge.
        Concierge validates, queues, and applies mutations.
        """
        # Validate authorization
        if not self._authorize_mutation(request):
            return MutationResponse.rejected("unauthorized")

        # Apply via SessionState
        result = self.session.mutate(
            section=request.section,
            operation=request.operation,
            data=request.data,
        )

        # Notify sub-agent of result
        return self._build_response(result)
```

**ConciergeAdapter Implementation (Future)**:

```python
from k1.sessionstate.ports import IWriterPort, MutationRequest, MutationResponse

class ConciergeWriterAdapter(IWriterPort):
    """
    Adapter that routes mutations through Concierge's queue.
    Enforces single-writer pattern and delegation chain tracking.
    """

    def __init__(self, concierge):
        self._concierge = concierge
        self._writer_id = "concierge"

    @property
    def writer_id(self) -> str:
        return self._writer_id

    @property
    def is_connected(self) -> bool:
        return self._concierge.is_running

    def request_mutation(self, request: MutationRequest) -> MutationResponse:
        # Route through Concierge's mutation queue
        return self._concierge.queue_mutation(request)

    def batch_mutations(self, batch: BatchRequest) -> BatchResult:
        return self._concierge.queue_batch(batch)

    def validate_writer(self, writer_id: str) -> WriterAuthorization:
        return self._concierge.validate_writer(writer_id)
```

---

### 2. Sub-Agents (Read Access)

Sub-agents read from SessionState but never write directly.

```python
class PlannerAgent:
    """
    Planner reads SessionState context, proposes mutations to Concierge.
    """

    def __init__(self, session_state, concierge_client):
        self.session = session_state  # Read-only view
        self.concierge = concierge_client

    def build_planning_context(self):
        """Read sections to build planning context."""
        # Read from HOT tier (lock-free, <1ms)
        beliefs = self.session.get_section("beliefs_active")
        history = self.session.get_section("history_active")
        scoreboard = self.session.get_section("scoreboard")

        context = {
            "beliefs": beliefs.list(),
            "recent_turns": history.get_recent(10),
            "active_tasks": scoreboard.get_active(),
        }
        return context

    def request_mutation(self, section, operation, data):
        """
        Propose mutation to Concierge.
        Concierge validates and applies via SessionState.
        """
        return self.concierge.propose_mutation(
            writer_id="planner",
            section=section,
            operation=operation,
            data=data,
            delegation_chain=["planner"],
        )


class BeliefAgent:
    """
    Belief agent manages belief lifecycle, proposes changes.
    """

    def __init__(self, session_state, concierge_client):
        self.session = session_state
        self.concierge = concierge_client

    def propose_belief(self, belief):
        """Propose new belief to Concierge."""
        return self.concierge.propose_mutation(
            writer_id="beliefs",
            section="beliefs_active",
            operation="add",
            data=belief,
        )

    def get_active_beliefs(self):
        """Read active beliefs (lock-free)."""
        return self.session.get_section("beliefs_active").list()
```

---

### 3. DeltaBus (Events)

SessionState emits events to DeltaBus for system-wide observability.

```python
from k0.bus import DeltaBus
from k1.sessionstate import SessionStateFactory

# DeltaBusAdapter (Future Implementation)
class DeltaBusAdapter(IEventPort):
    """
    Routes SessionState events to K0 DeltaBus.
    """

    def __init__(self, deltabus: DeltaBus):
        self._bus = deltabus
        self._subscriptions = {}

    @property
    def is_connected(self) -> bool:
        return self._bus.is_connected

    def emit(self, event_type: str, payload: Any) -> None:
        # Map to DeltaBus topic
        topic = f"sessionstate.{event_type}"
        self._bus.publish(topic, payload)

    def subscribe(self, event_type: str, handler: Callable) -> str:
        topic = f"sessionstate.{event_type}"
        sub_id = self._bus.subscribe(topic, handler)
        self._subscriptions[sub_id] = topic
        return sub_id

    def unsubscribe(self, subscription_id: str) -> bool:
        if subscription_id in self._subscriptions:
            self._bus.unsubscribe(subscription_id)
            del self._subscriptions[subscription_id]
            return True
        return False


# Usage
delta_bus = DeltaBus()
event_adapter = DeltaBusAdapter(delta_bus)

manager = SessionStateFactory.create_with_ports(
    session_id="prod-session",
    storage=sqlite_storage,
    events=event_adapter,  # Events go to DeltaBus
    writer=concierge_adapter,
    lifecycle=fabric_lifecycle,
)

# Other components can subscribe
def handle_pressure_event(event):
    print(f"Pressure alert: {event.section} at {event.pressure}")

delta_bus.subscribe("sessionstate.section.pressure", handle_pressure_event)
```

**Event Topics**:

| SessionState Event | DeltaBus Topic |
|-------------------|----------------|
| `mutation.approved` | `sessionstate.mutation.approved` |
| `mutation.rejected` | `sessionstate.mutation.rejected` |
| `eviction.triggered` | `sessionstate.eviction.triggered` |
| `eviction.completed` | `sessionstate.eviction.completed` |
| `emergency.activated` | `sessionstate.emergency.activated` |
| `emergency.resolved` | `sessionstate.emergency.resolved` |
| `checkpoint.created` | `sessionstate.checkpoint.created` |

---

### 4. Fabric (Lifecycle)

Fabric manages SessionState lifecycle (start, stop, checkpointing).

```python
from k1.fabric import Fabric
from k1.sessionstate import SessionStateFactory

# FabricLifecycleAdapter (Future Implementation)
class FabricLifecycleAdapter(ILifecyclePort):
    """
    Fabric controls SessionState lifecycle.
    Coordinates checkpoints, shutdown, health monitoring.
    """

    def __init__(self, fabric: Fabric, manager: SessionStateManager):
        self._fabric = fabric
        self._manager = manager
        self._state = LifecycleState.CREATED
        self._config = LifecycleConfig.default()

    @property
    def state(self) -> LifecycleState:
        return self._state

    @property
    def session_id(self) -> str:
        return self._manager.session_id

    def start(self, restore_if_exists: bool = True) -> StartResult:
        # Fabric coordinates startup
        self._state = LifecycleState.STARTING
        result = self._fabric.start_component("sessionstate", self._manager)
        self._state = LifecycleState.RUNNING if result.success else LifecycleState.ERROR
        return result

    def stop(self, checkpoint_before_stop: bool = True) -> StopResult:
        self._state = LifecycleState.STOPPING
        if checkpoint_before_stop:
            self._manager.checkpoint()
        result = self._fabric.stop_component("sessionstate")
        self._state = LifecycleState.STOPPED
        return result

    def health(self) -> HealthStatus:
        snapshot = self._manager.get_snapshot()
        return HealthStatus(
            is_healthy=snapshot.pressure != PressureLevel.EMERGENCY,
            hot_utilization=snapshot.hot_utilization_pct,
            warm_utilization=snapshot.warm_utilization_pct,
        )

    def checkpoint(self, trigger: CheckpointTrigger) -> CheckpointResult:
        return self._manager.checkpoint()


# Usage
fabric = Fabric()
lifecycle_adapter = FabricLifecycleAdapter(fabric, manager)

manager = SessionStateFactory.create_with_ports(
    session_id="prod-session",
    storage=sqlite_storage,
    events=deltabus_adapter,
    writer=concierge_adapter,
    lifecycle=lifecycle_adapter,
)

# Fabric controls lifecycle
fabric.start_session(session_id="user-123")
# ... session runs ...
fabric.stop_session(session_id="user-123")
```

---

### 5. Bridge (K0 Sync) - OPTIONAL

Bridge syncs SessionState checkpoints to K0 cloud when available.

```python
from bridge import Bridge, BridgeSyncAdapter
from k1.sessionstate import SessionStateFactory

# BridgeSyncAdapter (Future Implementation)
class BridgeSyncAdapter(IK0SyncPort):
    """
    Optional async sync to K0 via Bridge.
    Best-effort, non-blocking, graceful fallback.
    """

    def __init__(self, bridge: Bridge):
        self._bridge = bridge
        self._sync_queue = []

    @property
    def is_connected(self) -> bool:
        return self._bridge.is_connected

    def sync_to_k0(self, session_id: str) -> SyncResult:
        if not self.is_connected:
            # Queue for later sync
            self._sync_queue.append(session_id)
            return SyncResult(success=False, status=SyncStatus.OFFLINE)

        # Async sync via Bridge
        return self._bridge.sync_session(session_id)

    def restore_from_k0(self, session_id: str) -> RestoreFromK0Result:
        if not self.is_connected:
            return RestoreFromK0Result(success=False, error="K0 offline")

        return self._bridge.restore_session(session_id)


# Usage
bridge = Bridge()
sync_adapter = BridgeSyncAdapter(bridge)

manager = SessionStateFactory.create_with_ports(
    session_id="user-123-session",
    storage=sqlite_storage,
    events=deltabus_adapter,
    writer=concierge_adapter,
    lifecycle=fabric_lifecycle,
    k0_sync=sync_adapter,  # Optional K0 sync
)

# K0 sync happens automatically in background
# Falls back gracefully when offline
```

**Edge-First Principle**:
- LOCAL COLD is always written first (SQLite)
- K0 sync is optional enhancement
- Never block on K0 availability
- Session works 100% offline

---

## Standalone Mode

For development, testing, or offline operation:

```python
from k1.sessionstate import SessionStateFactory

# Full standalone - no external dependencies
manager = SessionStateFactory.create_standalone(
    session_id="dev-session-001",
    db_path=Path("~/.familyos/k1/dev.db"),
    checkpoint_interval_s=30.0,
)

# All operations work offline
manager.start()

# Mutations work without Concierge
result = manager.mutate("control", "set_mode", {"mode": "planning"})

# Checkpoints save to local SQLite
manager.checkpoint()

# Stop with final checkpoint
manager.stop()
```

**Adapters Used**:
- `SQLiteStorageAdapter` - LOCAL COLD persistence
- `LocalEventAdapter` - In-process event callbacks
- `DirectWriterAdapter` - Direct mutation (bypasses Concierge)
- `StandaloneLifecycle` - Self-managed lifecycle

---

## Testing Mode

For fast unit tests with capture mode:

```python
import pytest
from k1.sessionstate import SessionStateFactory

@pytest.fixture
def session():
    """Create test session with capture mode events."""
    manager = SessionStateFactory.create_for_testing()
    manager.start()
    yield manager
    manager.stop()

def test_belief_creation(session):
    """Test belief mutation and event capture."""
    result = session.mutate(
        section="beliefs_active",
        operation="add",
        data={"subject": "user", "predicate": "likes", "object": "tests"},
    )

    assert result.success
    assert result.bytes_delta > 0

    # Assert events were captured
    events = session._event_port.get_captured_events()
    assert len(events) >= 1

    # Find mutation approved event
    approved = [e for e in events if e[0] == "mutation.approved"]
    assert len(approved) == 1

def test_pressure_handling(session):
    """Test pressure events under load."""
    # Fill section to trigger pressure
    for i in range(100):
        session.mutate(
            section="history_active",
            operation="append",
            data={"turn": i, "content": "x" * 500},
        )

    snapshot = session.get_snapshot()
    # Should have elevated pressure
    assert snapshot.pressure in [PressureLevel.ELEVATED, PressureLevel.CRITICAL]
```

**Testing Adapters**:
- `InMemoryStorageAdapter` - No disk I/O
- `LocalEventAdapter(capture_mode=True)` - Event capture
- `DirectWriterAdapter` - Direct mutation
- `StandaloneLifecycle(checkpoint_interval_s=0)` - No periodic checkpoints

---

## Production Wiring (Complete Example)

```python
from k1.sessionstate import SessionStateFactory
from k1.concierge import ConciergeWriterAdapter
from k1.fabric import FabricLifecycleAdapter
from k0.bus import DeltaBusAdapter
from bridge import BridgeSyncAdapter

def create_production_session(
    user_id: str,
    fabric: Fabric,
    deltabus: DeltaBus,
    concierge: Concierge,
    bridge: Optional[Bridge] = None,
) -> SessionStateManager:
    """
    Create production SessionState with full K1 integration.
    """
    session_id = f"{user_id}-{uuid.uuid4().hex[:8]}"

    # Create adapters
    storage = SQLiteStorageAdapter(
        db_path=Path(f"~/.familyos/k1/{user_id}/session.db")
    )
    events = DeltaBusAdapter(deltabus)
    writer = ConciergeWriterAdapter(concierge)
    lifecycle = FabricLifecycleAdapter(fabric)

    # Optional K0 sync
    k0_sync = BridgeSyncAdapter(bridge) if bridge else None

    # Create wired manager
    manager = SessionStateFactory.create_with_ports(
        session_id=session_id,
        storage=storage,
        events=events,
        writer=writer,
        lifecycle=lifecycle,
        k0_sync=k0_sync,
    )

    return manager
```

---

## Migration from Old Session Storage

If migrating from previous session storage format:

```python
from k1.sessionstate import SessionStateFactory, LocalColdArchive
from pathlib import Path

def migrate_old_sessions(old_data_dir: Path, new_db_path: Path):
    """
    Migrate old session data to new SessionState format.
    """
    # Create LOCAL COLD archive
    archive = LocalColdArchive(db_path=new_db_path)

    # Load old data
    old_beliefs = load_old_beliefs(old_data_dir / "beliefs.json")
    old_history = load_old_history(old_data_dir / "history.json")

    # Import into archive
    for belief in old_beliefs:
        archive.archive_belief(belief)

    for turn in old_history:
        archive.archive_turn(turn)

    # New sessions will restore from archive
    manager = SessionStateFactory.create_standalone(db_path=new_db_path)
    result = manager.start(restore_if_exists=True)

    print(f"Migrated: restored={result.restored}, source={result.restore_source}")
```

---

## Related Documentation

- [API_REFERENCE.md](API_REFERENCE.md) - Complete API documentation
- [PORTS_OVERVIEW.md](PORTS_OVERVIEW.md) - Port interfaces and adapters
- [STORAGE_PORT.md](STORAGE_PORT.md) - Storage port contract
- [EVENT_PORT.md](EVENT_PORT.md) - Event port contract
- [WRITER_PORT.md](WRITER_PORT.md) - Writer port contract
- [LIFECYCLE_PORT.md](LIFECYCLE_PORT.md) - Lifecycle port contract
