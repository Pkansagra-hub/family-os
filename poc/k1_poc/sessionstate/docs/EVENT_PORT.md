# Event Port Documentation

## Purpose

The Event Port (`IEventPort`) provides a pluggable interface for SessionState event emission.
This enables standalone operation (LocalEventAdapter) or K0 bus integration (DeltaBusAdapter).

## Interface

```python
class IEventPort(ABC):
    @property
    @abstractmethod
    def is_connected(self) -> bool:
        """Check if event bus is connected."""

    @abstractmethod
    def emit(
        self,
        event_type: str,
        payload: Any,
    ) -> None:
        """Emit an event. Fire-and-forget semantics."""

    @abstractmethod
    def subscribe(
        self,
        event_type: str,
        handler: Callable[[Any], None],
    ) -> str:
        """Subscribe to event type. Returns subscription ID."""

    @abstractmethod
    def unsubscribe(self, subscription_id: str) -> bool:
        """Unsubscribe from event. Returns True if found."""

    def emit_batch(self, events: List[Tuple[str, Any]]) -> None:
        """Emit multiple events. Default: calls emit() in loop."""
```

## Adapters

### LocalEventAdapter (Standalone)

```python
from k1.sessionstate.adapters import LocalEventAdapter

adapter = LocalEventAdapter()

# Subscribe to events
def on_mutation(event):
    print(f"Mutation: {event.section}")

sub_id = adapter.subscribe("sessionstate.mutation.approved", on_mutation)

# Events are dispatched in background thread
# Handler exceptions are logged, not propagated
```

**Features:**

- In-process dispatch with queue-based threading
- Background dispatch thread (daemon)
- Thread-safe handler management
- Capture mode for testing
- Always reports `is_connected = True`

**Lifecycle:**

```python
adapter = LocalEventAdapter()
# ... use adapter ...
adapter.stop()  # Clean shutdown - stops dispatch thread
```

**Testing Support:**

```python
adapter = LocalEventAdapter(capture_mode=True)

# Do operations that emit events
manager.mutate("beliefs", "add", data)

# Assert events
adapter.assert_emitted("sessionstate.mutation.approved", count=1)
events = adapter.drain()  # Get and clear captured events

# Wait for dispatch
adapter.wait_for_dispatch(timeout=1.0)
```

### DeltaBusAdapter (K0 Integration)

```python
from k0.bus import DeltaBus
from k1.sessionstate.adapters import DeltaBusAdapter

delta_bus = DeltaBus()
adapter = DeltaBusAdapter(delta_bus)
```

**Features:**

- Full K0 DeltaBus integration
- Cross-component event routing
- Persistent event topics
- `is_connected` reflects actual bus state

## Event Types

| Event Type | Payload Class | When Emitted |
|------------|---------------|--------------|
| `sessionstate.mutation.requested` | `MutationRequestedEvent` | Before preflight check |
| `sessionstate.mutation.approved` | `MutationApprovedEvent` | After successful mutation |
| `sessionstate.mutation.rejected` | `MutationRejectedEvent` | When preflight rejects mutation |
| `sessionstate.eviction.triggered` | `EvictionTriggeredEvent` | When eviction starts |
| `sessionstate.eviction.completed` | `EvictionCompletedEvent` | After eviction completes |
| `sessionstate.emergency.activated` | `EmergencyActivatedEvent` | When capacity >95% |
| `sessionstate.emergency.resolved` | `EmergencyResolvedEvent` | When capacity drops below threshold |
| `sessionstate.reconstruction.started` | `ReconstructionStartedEvent` | When restoring from COLD |

**EventType Enum:**

```python
from k1.sessionstate.events import EventType

# Use enum values
EventType.MUTATION_APPROVED.value  # "sessionstate.mutation.approved"
EventType.EVICTION_TRIGGERED.value  # "sessionstate.eviction.triggered"
```

## Emission Guarantees

1. **Fire-and-Forget**: `emit()` returns immediately, no delivery guarantee
2. **Handler Isolation**: One handler failure doesn't affect others
3. **Order Preserved**: Events dispatched in emission order (per type)
4. **Thread Safety**: All operations are thread-safe

## Subscription Lifecycle

```python
# Subscribe returns unique ID
sub_id = adapter.subscribe("sessionstate.mutation.approved", handler)

# Unsubscribe by ID
success = adapter.unsubscribe(sub_id)  # Returns True if found

# Handler receives payload only
def my_handler(event: MutationApprovedEvent):
    print(event.section, event.operation)
```

## Event Payloads

All events inherit from `BaseEvent`:

```python
@dataclass
class BaseEvent:
    event_id: str  # UUID
    event_type: str  # EventType value
    cognitive_trace_id: str
    timestamp_ms: int
    version: str = "1.0"

    def to_dict(self) -> Dict[str, Any]: ...
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "BaseEvent": ...
```

**Key Payloads:**

```python
@dataclass
class MutationApprovedEvent(BaseEvent):
    section: str
    operation: str
    new_size_bytes: int
    available_bytes: int

@dataclass
class EvictionTriggeredEvent(BaseEvent):
    section: str
    tier: str
    target_bytes: int
    current_bytes: int
    pressure_level: str

@dataclass
class EmergencyActivatedEvent(BaseEvent):
    current_capacity_pct: float
    threshold_pct: float
    sections_over_budget: List[str]
```

## Factory Methods

```python
from k1.sessionstate.events import SessionStateEvents

# Create events via factory
event = SessionStateEvents.mutation_approved(
    section="beliefs",
    operation="add",
    new_size_bytes=1024,
    available_bytes=9000,
    cognitive_trace_id="trace-123",
)

# Emit
adapter.emit(event.event_type, event)
```

## Usage Example

```python
from k1.sessionstate.adapters import LocalEventAdapter
from k1.sessionstate import SessionStateFactory
from k1.sessionstate.events import EventType

# Create with custom event adapter
events = LocalEventAdapter()
manager = SessionStateFactory.create_with_ports(
    event_port=events,
)

# Subscribe to emergency events
def handle_emergency(event):
    if event.current_capacity_pct > 95:
        print(f"CRITICAL: {event.sections_over_budget}")

events.subscribe(EventType.EMERGENCY_ACTIVATED.value, handle_emergency)

# Subscribe to eviction completion
def handle_eviction_done(event):
    print(f"Evicted {event.bytes_freed} from {event.section}")

events.subscribe(EventType.EVICTION_COMPLETED.value, handle_eviction_done)
```

## Related Files

- Interface: `k1/sessionstate/ports/events.py`
- Payloads: `k1/sessionstate/events.py`
- Local Adapter: `k1/sessionstate/adapters/local_events.py`
- DeltaBus Adapter: `k1/sessionstate/adapters/delta_events.py`
