# Writer Port Documentation

## Purpose

The Writer Port (`IWriterPort`) enforces the **single-writer pattern** for SessionState mutations.
This ensures data consistency, prevents race conditions, and provides an audit trail for all changes.

## Single Writer Pattern

**Rationale**: SessionState manages critical cognitive context. Concurrent uncoordinated writes could corrupt state, violate capacity budgets, or cause inconsistent memory. The single-writer pattern ensures:

1. **Serialized mutations**: One write at a time
2. **Capacity enforcement**: MutationGuard validates before apply
3. **Audit trail**: Delegation chain tracks who requested what
4. **Conflict resolution**: Concierge aggregates and prioritizes

**Writers by Mode**:

| Mode | Writer | Adapter | Coordination |
|------|--------|---------|--------------|
| Production | Concierge | ConciergeAdapter | Queue-based, multi-agent |
| Standalone | Direct | DirectWriterAdapter | Immediate, single-threaded |
| Testing | Test | DirectWriterAdapter | Mock manager/guard |

## Sub-Agent Delta Flow

Sub-agents do NOT write directly. They propose deltas to Concierge:

```
┌─────────────┐     propose delta    ┌─────────────┐
│  Sub-Agent  │ ─────────────────────► │  Concierge  │
│  (Beliefs)  │                        │  (Writer)   │
└─────────────┘                        └──────┬──────┘
                                              │
        ┌─────────────────────────────────────┘
        │ IWriterPort.request_mutation()
        ▼
┌─────────────────────────────────────────────────────────┐
│                   SessionStateManager                    │
│  ┌──────────────┐    ┌──────────────┐    ┌───────────┐ │
│  │MutationGuard │───►│   Section    │───►│SizeTracker│ │
│  │  preflight() │    │   apply()    │    │  update() │ │
│  └──────────────┘    └──────────────┘    └───────────┘ │
└─────────────────────────────────────────────────────────┘
```

## Interface

```python
class IWriterPort(ABC):
    @property
    @abstractmethod
    def writer_id(self) -> str:
        """Get writer identifier ('concierge', 'direct', 'test')."""

    @property
    @abstractmethod
    def is_connected(self) -> bool:
        """Check if writer port is ready to process mutations."""

    @abstractmethod
    def request_mutation(
        self,
        request: MutationRequest,
    ) -> MutationResponse:
        """
        Request a single mutation.

        Flow: validate → preflight → apply → respond
        Target: <5ms for typical mutations
        """

    @abstractmethod
    def batch_mutations(
        self,
        batch: BatchRequest,
    ) -> BatchResult:
        """
        Process multiple mutations in order.

        Supports stop_on_rejection for atomic-like behavior.
        Target: <10ms for batch of 5 mutations
        """

    @abstractmethod
    def validate_writer(self, writer_id: str) -> WriterAuthorization:
        """Validate writer is authorized to mutate."""
```

## Data Types

### MutationPriority

```python
class MutationPriority(str, Enum):
    CRITICAL = "critical"   # Control section, emergency
    HIGH = "high"           # User-facing (beliefs, history)
    NORMAL = "normal"       # Standard operations
    LOW = "low"             # Background (telemetry)
    DEFERRED = "deferred"   # Can be delayed
```

### MutationRequest

```python
@dataclass
class MutationRequest:
    request_id: str              # UUID for idempotency
    section: str                 # Target section
    operation: str               # 'set', 'append', 'update', 'clear', 'delete'
    data: Any                    # Operation payload
    estimated_bytes: int         # Size estimate for preflight
    writer_id: str               # Requesting writer
    cognitive_trace_id: str      # Distributed tracing
    priority: MutationPriority   # For ordering
    delegation_chain: List[str]  # Audit: [sub-agent, concierge]
    created_at_ms: int           # Request timestamp
    timeout_ms: int              # Expiration (0 = none)
    metadata: Dict[str, Any]     # Additional context

    # Factory method
    @staticmethod
    def create(section, operation, data, writer_id, cognitive_trace_id, ...) -> MutationRequest

    # Serialization
    def to_dict(self) -> Dict[str, Any]
    @classmethod
    def from_dict(cls, data) -> MutationRequest

    # Helpers
    def is_expired(self) -> bool
```

### MutationResponse

```python
@dataclass
class MutationResponse:
    request_id: str                           # Echo from request
    status: MutationStatus                    # APPLIED, REJECTED, FAILED, CANCELLED
    approved: bool                            # Quick check
    new_size_bytes: int                       # Section size after mutation
    bytes_delta: int                          # Actual change
    available_bytes: int                      # Remaining capacity
    section: str                              # Echo from request
    operation: str                            # Echo from request
    reason: str                               # Rejection reason
    rejection_category: RejectionCategory     # For programmatic handling
    error: Optional[str]                      # Exception message
    duration_ms: float                        # Processing time
    timestamp_ms: int                         # Response timestamp

    # Factory methods
    @staticmethod
    def approved(request_id, section, operation, new_size_bytes, bytes_delta, available_bytes, duration_ms) -> MutationResponse

    @staticmethod
    def rejected(request_id, section, operation, reason, category, available_bytes, duration_ms) -> MutationResponse

    @staticmethod
    def failed(request_id, section, operation, error, duration_ms) -> MutationResponse

    @staticmethod
    def cancelled(request_id, reason) -> MutationResponse
```

### RejectionCategory

```python
class RejectionCategory(str, Enum):
    CAPACITY = "capacity"           # Size limits exceeded
    AUTHORIZATION = "authorization" # Writer not allowed
    VALIDATION = "validation"       # Invalid section/operation
    LOCKED = "locked"               # Section under eviction/migration
    EMERGENCY = "emergency"         # Emergency mode active
    INTERNAL = "internal"           # Unexpected error
```

### BatchRequest & BatchResult

```python
@dataclass
class BatchRequest:
    batch_id: str
    requests: List[MutationRequest]
    writer_id: str
    cognitive_trace_id: str
    stop_on_rejection: bool = False  # Stop at first rejection?

@dataclass
class BatchResult:
    batch_id: str
    total_requests: int
    applied_count: int
    rejected_count: int
    failed_count: int
    cancelled_count: int
    responses: List[MutationResponse]
    total_bytes_delta: int
    duration_ms: float
    stopped_early: bool
```

## Rejection Handling

When a mutation is rejected, the response includes:

1. **reason**: Human-readable explanation
2. **rejection_category**: Programmatic category
3. **available_bytes**: Current capacity (for retry decisions)

**Handling by Category**:

| Category | Meaning | Response |
|----------|---------|----------|
| CAPACITY | Over budget | Evict/migrate, then retry |
| AUTHORIZATION | Not allowed | Check writer permissions |
| VALIDATION | Invalid input | Fix request and retry |
| LOCKED | Section busy | Wait and retry |
| EMERGENCY | System overload | Back off significantly |
| INTERNAL | Bug | Log and escalate |

## Adapters

### DirectWriterAdapter (Standalone)

```python
from k1.sessionstate.adapters import DirectWriterAdapter
from k1.sessionstate.ports.writer import MutationRequest

adapter = DirectWriterAdapter(manager, guard)

# Create request via factory
request = MutationRequest.create(
    section="beliefs_active",
    operation="append",
    data={"fact": "user prefers dark mode"},
    writer_id="direct",
    cognitive_trace_id="trace-123",
    estimated_bytes=100,
)

response = adapter.request_mutation(request)

if response.approved:
    print(f"Applied: {response.bytes_delta} bytes, new size: {response.new_size_bytes}")
else:
    print(f"Rejected ({response.rejection_category}): {response.reason}")
```

**Features**:
- Immediate processing (no queue)
- Thread-safe with RLock
- Configurable authorization
- Statistics tracking

**Statistics**:
```python
stats = adapter.get_stats()
# {
#     "writer_id": "direct",
#     "total_requests": 100,
#     "applied_count": 95,
#     "rejected_count": 5,
#     "failed_count": 0,
#     "avg_duration_ms": 2.5,
#     "total_bytes_delta": 50000,
#     "pending_count": 0,
# }
```

### ConciergeAdapter (Production - Future)

```python
from k1.concierge.adapters import ConciergeWriterAdapter

adapter = ConciergeWriterAdapter(concierge, session_id)

# Mutations queued and processed by Concierge
response = adapter.request_mutation(request)
```

**Features**:
- Queue-based processing
- Multi-agent coordination
- Priority ordering
- Rate limiting
- Conflict resolution

## Mutation Flow (Detailed)

```
┌─────────┐  MutationRequest  ┌─────────────┐
│ Caller  │ ─────────────────► │ IWriterPort │
└─────────┘                    └──────┬──────┘
                                      │
     ┌────────────────────────────────┴────────────────────────────────┐
     │                                                                  │
     ▼                                                                  │
┌─────────────────┐                                                    │
│ 1. Check expiry │ ─── expired ──► MutationResponse.rejected()        │
└────────┬────────┘                 (VALIDATION)                       │
         │ not expired                                                 │
         ▼                                                             │
┌─────────────────┐                                                    │
│ 2. Validate     │ ─── unauthorized ──► MutationResponse.rejected()   │
│    writer       │                      (AUTHORIZATION)               │
└────────┬────────┘                                                    │
         │ authorized                                                  │
         ▼                                                             │
┌─────────────────┐                                                    │
│ 3. Preflight    │ ─── rejected ──► MutationResponse.rejected()       │
│    (Guard)      │                  (CAPACITY/LOCKED/EMERGENCY)       │
└────────┬────────┘                                                    │
         │ approved                                                    │
         ▼                                                             │
┌─────────────────┐                                                    │
│ 4. Apply        │ ─── exception ──► MutationResponse.failed()        │
│    (Manager)    │                                                    │
└────────┬────────┘                                                    │
         │ success                                                     │
         ▼                                                             │
┌─────────────────┐                                                    │
│ 5. Response     │ ──────────────────────────────────────────────────►│
│    (APPLIED)    │                                                    │
└─────────────────┘                                                    │
```

## Delegation Chain (Audit Trail)

The `delegation_chain` field tracks the path from origin to writer:

```python
# Sub-agent proposes delta to Concierge
request = MutationRequest.create(
    section="beliefs_active",
    operation="append",
    data={"fact": "user said they like coffee"},
    writer_id="concierge",
    cognitive_trace_id="turn-456",
    delegated_from="belief_extractor_agent",
)

# request.delegation_chain = ["belief_extractor_agent"]
```

This enables:
- **Audit**: Who requested what change?
- **Attribution**: Which agent contributed this belief?
- **Debugging**: Trace unexpected mutations

## Related Files

- Interface: [k1/sessionstate/ports/writer.py](../ports/writer.py)
- Adapter: [k1/sessionstate/adapters/direct_writer.py](../adapters/direct_writer.py)
- Guard: [k1/sessionstate/guard.py](../guard.py)
- Manager: [k1/sessionstate/manager.py](../manager.py)
