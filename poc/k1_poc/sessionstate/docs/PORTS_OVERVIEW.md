# SessionState Ports Overview

## Design Philosophy

SessionState uses the **Ports & Adapters** (Hexagonal Architecture) pattern:

- **Ports** = Interfaces defining capabilities
- **Adapters** = Implementations for specific contexts

This enables:
- Standalone mode for testing/development
- Production mode with full K1 integration
- Future extensibility without core changes

## Port Summary

| Port | Purpose | Standalone Adapter | Production Adapter |
|------|---------|-------------------|-------------------|
| `IStoragePort` | LOCAL COLD persistence | `SQLiteStorageAdapter` | `SQLiteStorageAdapter` |
| `IEventPort` | Event emission | `LocalEventAdapter` | `DeltaBusAdapter` |
| `IWriterPort` | Mutation coordination | `DirectWriterAdapter` | `ConciergeAdapter` |
| `ILifecyclePort` | Lifecycle management | `StandaloneLifecycle` | `FabricLifecycleAdapter` |
| `IK0SyncPort` | Optional K0 sync | `NullSyncPort` | `BridgeSyncAdapter` |

## Port Interfaces

### IStoragePort

```python
class IStoragePort(ABC):
    @property
    @abstractmethod
    def is_available(self) -> bool: ...

    @property
    @abstractmethod
    def storage_type(self) -> str: ...

    @abstractmethod
    def archive(self, section: str, data: bytes, metadata: dict) -> ArchiveResult: ...

    @abstractmethod
    def restore(self, section: str, filters: dict) -> RestoreResult: ...

    @abstractmethod
    def list_archives(self, session_id: str) -> List[ArchiveEntry]: ...

    @abstractmethod
    def delete(self, archive_id: str) -> bool: ...
```

### IEventPort

```python
class IEventPort(ABC):
    @property
    @abstractmethod
    def is_connected(self) -> bool: ...

    @abstractmethod
    def emit(self, event_type: str, payload: Any) -> None: ...

    @abstractmethod
    def subscribe(self, event_type: str, handler: Callable) -> str: ...

    @abstractmethod
    def unsubscribe(self, subscription_id: str) -> bool: ...
```

### IWriterPort

```python
class IWriterPort(ABC):
    @property
    @abstractmethod
    def writer_id(self) -> str: ...

    @abstractmethod
    def request_mutation(self, request: MutationRequest) -> MutationResponse: ...

    @abstractmethod
    def batch_mutations(self, requests: List[MutationRequest]) -> BatchResult: ...

    @abstractmethod
    def validate_writer(self, writer_id: str) -> bool: ...
```

### ILifecyclePort

```python
class ILifecyclePort(ABC):
    @property
    @abstractmethod
    def state(self) -> LifecycleState: ...

    @abstractmethod
    def start(self) -> StartResult: ...

    @abstractmethod
    def stop(self) -> StopResult: ...

    @abstractmethod
    def health(self) -> HealthStatus: ...

    @abstractmethod
    def checkpoint(self) -> CheckpointResult: ...
```

### IK0SyncPort

```python
class IK0SyncPort(ABC):
    @property
    @abstractmethod
    def is_connected(self) -> bool: ...

    @property
    @abstractmethod
    def sync_status(self) -> SyncStatus: ...

    @abstractmethod
    def sync_checkpoint(self, checkpoint_id: str, data: bytes) -> SyncResult: ...

    @abstractmethod
    def get_last_synced(self) -> Optional[str]: ...
```

## Creating Custom Adapters

```python
from k1.sessionstate.ports import IStoragePort, ArchiveResult, RestoreResult

class CustomStorageAdapter(IStoragePort):
    """Custom storage adapter for specific backend."""

    @property
    def is_available(self) -> bool:
        return self._check_backend()

    @property
    def storage_type(self) -> str:
        return "custom"

    def archive(self, section, data, metadata) -> ArchiveResult:
        # Custom implementation
        ...

    def restore(self, section, filters) -> RestoreResult:
        # Custom implementation
        ...
```

## Adapter Selection

```python
from k1.sessionstate import SessionStateFactory

# Standalone mode (default adapters)
manager = SessionStateFactory.create_standalone()

# Custom adapters
manager = SessionStateFactory.create_with_ports(
    storage_port=MyCustomStorage(),
    event_port=MyCustomEvents(),
    writer_port=MyCustomWriter(),
    lifecycle_port=MyCustomLifecycle(),
    k0_sync_port=MyCustomSync(),  # Optional
)
```
