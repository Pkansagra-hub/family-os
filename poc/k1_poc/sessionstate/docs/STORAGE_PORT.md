# Storage Port Documentation

## Purpose

The Storage Port (`IStoragePort`) provides LOCAL COLD persistence for SessionState.

## Edge-First Design

Storage is LOCAL FIRST:

- K1 SQLite database (always available)
- No network dependency
- SessionState works fully offline

## Bridge Alignment

The Storage Port maps to Bridge command topics:

| Section | Bridge Topic | Schema |
|---------|--------------|--------|
| checkpoint | `session.checkpoint` | `schema://session.checkpoint` |
| beliefs | `beliefs.archive` | `schema://beliefs.archive` |
| history | `history.archive` | `schema://history.archive` |
| narrative | `narrative.archive` | `schema://narrative.archive` |

Data format is FlatBuffer bytes for envelope compatibility.

## LOCAL COLD vs K0 Sync Decision Tree

```
SessionState needs to persist data
          |
          v
+-------------------+
| LOCAL COLD First  |
| (SQLiteAdapter)   |
+-------------------+
          |
          v
     Is K0 sync
     configured?
          |
    +-----+-----+
    |           |
   NO          YES
    |           |
    v           v
 [DONE]   Queue to K0
          (async, non-blocking)
                |
                v
          +-------------+
          | K0 Available?|
          +-------------+
                |
          +-----+-----+
          |           |
         NO          YES
          |           |
          v           v
     Keep in      Sync to K0
     outbox       (background)
```

**Key Principles:**

1. LOCAL COLD is PRIMARY (always written first)
2. K0 sync is OPTIONAL ENHANCEMENT (queued async)
3. Never block on K0 operations
4. Data is safe in LOCAL COLD even if K0 is unavailable

## Offline Operation Guarantees

### What Works Offline (100%)

| Operation | Behavior | SLA |
|-----------|----------|-----|
| Archive (eviction) | Writes to LOCAL COLD | <10ms |
| Restore | Reads from LOCAL COLD | <50ms |
| Checkpoint | Full session snapshot | <100ms |
| List archives | Query LOCAL COLD | <20ms |

### What Degrades Offline

| Operation | Behavior | Fallback |
|-----------|----------|----------|
| Cross-device sync | Queued in outbox | Sync when online |
| K0 restore | Unavailable | Use LOCAL COLD |
| K0 backup | Queued | Sync when online |

### No Network Dependency

SessionState NEVER requires network for:

- Reading session data
- Writing session data
- Eviction to LOCAL COLD
- Reconstruction from LOCAL COLD
- Checkpoint creation
- Checkpoint restore

## Interface

```python
class IStoragePort(ABC):
    @property
    @abstractmethod
    def is_available(self) -> bool:
        """Check if storage is available."""

    @property
    @abstractmethod
    def storage_type(self) -> str:
        """Get storage type identifier ('local', 'memory')."""

    @abstractmethod
    def archive(
        self,
        section: str,
        data: bytes,
        metadata: Dict[str, Any],
    ) -> ArchiveResult:
        """Archive data to storage."""

    @abstractmethod
    def restore(
        self,
        section: str,
        filters: Dict[str, Any],
    ) -> RestoreResult:
        """Restore data from storage."""

    @abstractmethod
    def list_archives(
        self,
        session_id: str,
    ) -> List[ArchiveEntry]:
        """List archives for a session."""

    @abstractmethod
    def delete(self, archive_id: str) -> bool:
        """Delete an archive."""
```

## Adapters

### SQLiteStorageAdapter (Production)

```python
from k1.sessionstate.adapters import SQLiteStorageAdapter

adapter = SQLiteStorageAdapter()
# or with custom path
adapter = SQLiteStorageAdapter(db_path=Path("~/.familyos/k1/custom.db"))
```

**Features:**

- WAL mode for concurrency
- Automatic schema creation
- Session-scoped queries

**Tables:**

- `st_session_checkpoints` - Full snapshots
- `st_beliefs_archive` - Evicted beliefs
- `st_history_archive` - Evicted history
- `st_narrative_archive` - Evicted narratives

### InMemoryStorageAdapter (Testing)

```python
from k1.sessionstate.adapters import InMemoryStorageAdapter

adapter = InMemoryStorageAdapter()
# Use in tests
adapter.clear()  # Clear between tests
```

**Features:**

- No disk I/O
- Fast for unit tests
- `clear()` method for test isolation

## Data Types

### ArchiveResult

```python
@dataclass
class ArchiveResult:
    success: bool
    archive_id: str
    size_bytes: int
    duration_ms: float
    error: str = ""
```

### RestoreResult

```python
@dataclass
class RestoreResult:
    success: bool
    data: Optional[bytes]
    archive_id: str
    size_bytes: int
    duration_ms: float
    error: str = ""
```

### ArchiveEntry

```python
@dataclass
class ArchiveEntry:
    archive_id: str
    session_id: str
    section: str
    size_bytes: int
    created_at_ms: int
    metadata: Dict[str, Any]
```

## SLA

- Archive: No strict SLA (background operation)
- Restore: <50ms P95 target
- Always available (local storage)

## Usage Example

```python
from k1.sessionstate.adapters import SQLiteStorageAdapter

storage = SQLiteStorageAdapter()

# Archive evicted data
result = storage.archive(
    section="beliefs_history",
    data=serialized_beliefs,
    metadata={
        "session_id": "abc-123",
        "eviction_reason": "pressure",
    },
)

if result.success:
    print(f"Archived as {result.archive_id}")

# Restore for reconstruction
result = storage.restore(
    section="beliefs_history",
    filters={"session_id": "abc-123"},
)

if result.success:
    beliefs = deserialize(result.data)
```
