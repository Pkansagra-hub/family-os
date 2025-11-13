# K0 Sync Module

**Purpose**: CRDT conflict resolution with audit trail logging for multi-device synchronization.

**Layer**: Synchronization & Conflict Resolution
**Category**: CRDT merge logging, vector clock conflict resolution
**Related ADRs**: ADR-0150 (CRDT Merge Logger), ADR-0151 (Vector Clock Resolution), ADR-0152 (Multi-Device Sync)

---

## Overview

The sync module provides **CRDT conflict resolution** with:

1. **Conflict resolution audit trail**: Log all CRDT merge decisions to `st_crdt_merge_log` (Migration 0004)
2. **Vector clock strategy**: Compare vector clocks to determine causality (local dominates, remote dominates, concurrent)
3. **Last-write-wins fallback**: Timestamp-based conflict resolution for legacy compatibility
4. **Merge logger**: `CRDTMergeLogger` for tracking winner/loser device IDs, vector clocks, and conflict reasons
5. **Helper function**: `resolve_conflict_with_logging()` for integrated conflict resolution + logging

**Usage Context**: Multi-device synchronization, episodic memory merging, semantic memory CRDT operations

**Research Foundations**:
- **Honda 2008**: Multiparty Session Types for synchronization protocols
- **Shapiro 2011**: CRDTs (Conflict-free Replicated Data Types)

---

## Repository Files & Functions

### 1. `crdt_merge_logger.py`

**Purpose**: Log CRDT conflict resolution events for debugging, compliance, and analytics.

#### Classes

```python
@dataclass(frozen=True)
class CRDTMergeLog:
    merge_id: str
    resource_type: str  # st_epi, st_sem, etc
    resource_id: str  # event_id, fact_id, etc
    merge_strategy: str  # last-write-wins, vector-clock, manual, semantic-merge
    winner_device_id: str
    loser_device_id: str
    winner_vector_clock: Optional[str] = None  # JSON-encoded
    loser_vector_clock: Optional[str] = None  # JSON-encoded
    conflict_reason: Optional[str] = None
    merged_at: str = ""
    tenant_id: Optional[str] = None
```

- **Purpose**: Represents a CRDT conflict resolution log entry
- **Storage**: Persisted to `st_crdt_merge_log` table (Migration 0004)
- **Vector Clocks**: JSON-encoded dict mapping device_id → version number

---

```python
class CRDTMergeLogger:
    def log_merge(
        self,
        merge_id: str,
        resource_type: str,
        resource_id: str,
        merge_strategy: str,
        winner_device_id: str,
        loser_device_id: str,
        *,
        winner_vector_clock: Optional[Dict] = None,
        loser_vector_clock: Optional[Dict] = None,
        conflict_reason: Optional[str] = None,
        tenant_id: Optional[str] = None,
        connection: Optional[sqlite3.Connection] = None,
    ) -> None
```

- **Purpose**: Log a CRDT conflict resolution event to database
- **Parameters**:
  - `merge_id`: Unique identifier (ULID or UUID)
  - `resource_type`: Table name (st_epi, st_sem, etc.)
  - `resource_id`: Event/fact ID with conflict
  - `merge_strategy`: last-write-wins, vector-clock, manual, semantic-merge
  - `winner_device_id`: Device ID of winning version
  - `loser_device_id`: Device ID of losing version
  - `winner_vector_clock`: Vector clock dict (will be JSON-encoded)
  - `loser_vector_clock`: Vector clock dict (will be JSON-encoded)
  - `conflict_reason`: Human-readable explanation
  - `tenant_id`: Optional tenant scope
- **Storage**: Inserts to `st_crdt_merge_log` with ON CONFLICT DO NOTHING
- **Defensive**: Silently logs warning if table doesn't exist (Migration 0004 not applied)

**Algorithm**:

```python
def log_merge(...) -> None:
    merged_at = datetime.now(timezone.utc).isoformat()

    # JSON-encode vector clocks
    winner_vc_json = json.dumps(winner_vector_clock) if winner_vector_clock else None
    loser_vc_json = json.dumps(loser_vector_clock) if loser_vector_clock else None

    # Insert to database
    try:
        connection.execute(
            """
            INSERT INTO st_crdt_merge_log (
                merge_id, resource_type, resource_id,
                merge_strategy, winner_device_id, loser_device_id,
                winner_vector_clock, loser_vector_clock,
                conflict_reason, merged_at, tenant_id
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (merge_id, resource_type, resource_id, merge_strategy,
             winner_device_id, loser_device_id,
             winner_vc_json, loser_vc_json,
             conflict_reason, merged_at, tenant_id)
        )
    except sqlite3.OperationalError as e:
        if "no such table" in str(e):
            # Table doesn't exist - log warning but don't fail
            print(f"Warning: st_crdt_merge_log not found - merge {merge_id} not logged")
            return
        raise CRDTMergeLoggerError(f"Failed to log merge: {e}") from e
```

**Example**:

```python
from k0.sync import CRDTMergeLogger

logger = CRDTMergeLogger()

# Log conflict resolution
logger.log_merge(
    merge_id="merge_123",
    resource_type="st_epi",
    resource_id="evt_abc123",
    merge_strategy="vector-clock",
    winner_device_id="device_001",
    loser_device_id="device_002",
    winner_vector_clock={"device_001": 5, "device_002": 3},
    loser_vector_clock={"device_001": 4, "device_002": 4},
    conflict_reason="Concurrent edits detected",
)
```

---

```python
def get_merge_history(
    self,
    *,
    resource_type: Optional[str] = None,
    resource_id: Optional[str] = None,
    device_id: Optional[str] = None,
    limit: int = 100,
    connection: Optional[sqlite3.Connection] = None,
) -> list[CRDTMergeLog]
```

- **Purpose**: Retrieve merge history with optional filters
- **Filters**: resource_type, resource_id, device_id (winner or loser)
- **Ordering**: `merged_at DESC` (most recent first)
- **Returns**: List of `CRDTMergeLog` entries

**Example**:

```python
# Get merge history for a specific memory
history = logger.get_merge_history(
    resource_type="st_epi",
    resource_id="evt_abc123",
    limit=10,
)

for entry in history:
    print(f"{entry.merged_at}: {entry.merge_strategy} - winner={entry.winner_device_id}")
```

---

#### Helper Function

```python
def resolve_conflict_with_logging(
    local_memory: Dict,
    remote_memory: Dict,
    resource_type: str,
    resource_id: str,
    logger: CRDTMergeLogger,
    *,
    merge_strategy: str = "vector-clock",
    connection: Optional[sqlite3.Connection] = None,
) -> Dict
```

- **Purpose**: Resolve CRDT conflict and automatically log the decision
- **Strategies**:
  - **vector-clock**: Compare vector clocks for causality determination
  - **last-write-wins**: Compare `updated_at` timestamps
- **Tiebreaker**: If concurrent (neither dominates), prefer memory with higher self-clock, then lower device_id
- **Logging**: Automatically calls `logger.log_merge()` after resolution
- **Returns**: Winning memory dict

**Vector Clock Algorithm**:

```python
def resolve_conflict_with_logging(...) -> Dict:
    if merge_strategy == "vector-clock":
        local_vc = local_memory.get("vector_clock", {})
        remote_vc = remote_memory.get("vector_clock", {})

        # Get all device IDs
        all_devices = set(local_vc.keys()) | set(remote_vc.keys())

        # Check if local dominates (all local >= remote)
        local_dominates = True
        remote_dominates = True

        for device in all_devices:
            local_val = local_vc.get(device, 0)
            remote_val = remote_vc.get(device, 0)

            if local_val < remote_val:
                local_dominates = False
            if remote_val < local_val:
                remote_dominates = False

        # Determine winner
        if local_dominates and not remote_dominates:
            winner = local_memory
            loser = remote_memory
        elif remote_dominates and not local_dominates:
            winner = remote_memory
            loser = local_memory
        else:
            # Concurrent: use self-clock tiebreaker
            local_device = local_memory.get("device_id", "")
            remote_device = remote_memory.get("device_id", "")

            local_self_clock = local_vc.get(local_device, 0)
            remote_self_clock = remote_vc.get(remote_device, 0)

            if local_self_clock > remote_self_clock:
                winner = local_memory
                loser = remote_memory
            elif remote_self_clock > local_self_clock:
                winner = remote_memory
                loser = local_memory
            else:
                # Equal self-clocks: use device_id tiebreaker
                if local_device < remote_device:
                    winner = local_memory
                    loser = remote_memory
                else:
                    winner = remote_memory
                    loser = local_memory

    elif merge_strategy == "last-write-wins":
        if local_memory.get("updated_at", "") > remote_memory.get("updated_at", ""):
            winner = local_memory
            loser = remote_memory
        else:
            winner = remote_memory
            loser = local_memory
    else:
        # Default to local
        winner = local_memory
        loser = remote_memory

    # Log the merge decision
    merge_id = str(uuid.uuid4())
    logger.log_merge(
        merge_id=merge_id,
        resource_type=resource_type,
        resource_id=resource_id,
        merge_strategy=merge_strategy,
        winner_device_id=winner.get("device_id", "unknown"),
        loser_device_id=loser.get("device_id", "unknown"),
        winner_vector_clock=winner.get("vector_clock"),
        loser_vector_clock=loser.get("vector_clock"),
        conflict_reason="Concurrent modifications detected during sync",
        tenant_id=winner.get("tenant_id"),
        connection=connection,
    )

    return winner
```

**Example**:

```python
from k0.sync import resolve_conflict_with_logging, CRDTMergeLogger

logger = CRDTMergeLogger()

# Local memory (device_001)
local = {
    "event_id": "evt_abc123",
    "device_id": "device_001",
    "vector_clock": {"device_001": 5, "device_002": 3},
    "content": "Had dinner with Mom at Olive Garden",
    "updated_at": "2025-11-12T10:00:00Z",
}

# Remote memory (device_002)
remote = {
    "event_id": "evt_abc123",
    "device_id": "device_002",
    "vector_clock": {"device_001": 4, "device_002": 4},
    "content": "Had dinner with Mom at Olive Garden (added location)",
    "updated_at": "2025-11-12T09:55:00Z",
}

# Resolve conflict
winner = resolve_conflict_with_logging(
    local_memory=local,
    remote_memory=remote,
    resource_type="st_epi",
    resource_id="evt_abc123",
    logger=logger,
    merge_strategy="vector-clock",
)

print(f"Winner: device {winner['device_id']}")
# → Winner: device device_001 (local dominates: 5 > 4)
```

---

### 2. `__init__.py`

**Purpose**: Export sync module public API.

**Exported Classes**:

```python
__all__ = [
    "CRDTMergeLogger",
    "CRDTMergeLog",
    "resolve_conflict_with_logging",
]
```

---

## Vector Clock Conflict Resolution

### Causality Rules

**Dominance**: Vector clock A dominates B if `A[d] >= B[d]` for all devices d, and `A[d] > B[d]` for at least one device.

| Local VC | Remote VC | Causality | Winner |
|----------|-----------|-----------|--------|
| `{d1: 5, d2: 3}` | `{d1: 4, d2: 3}` | Local dominates | Local |
| `{d1: 4, d2: 3}` | `{d1: 5, d2: 3}` | Remote dominates | Remote |
| `{d1: 5, d2: 3}` | `{d1: 4, d2: 4}` | Concurrent | Tiebreaker |

### Concurrent Conflict Tiebreakers

When neither vector clock dominates (concurrent edits):

1. **Self-clock tiebreaker**: Prefer memory with higher value for its own device_id in vector clock
   - Example: `local_vc[local_device]` vs. `remote_vc[remote_device]`
2. **Device ID tiebreaker**: If self-clocks equal, prefer lower device_id (deterministic)
   - Example: `device_001` < `device_002` → prefer device_001

**Rationale**: Self-clock tiebreaker prefers the memory that has been edited more recently on its originating device, ensuring the "freshest" local edits win.

---

## Database Schema (Migration 0004)

### `st_crdt_merge_log` Table

```sql
CREATE TABLE IF NOT EXISTS st_crdt_merge_log (
    merge_id TEXT PRIMARY KEY,
    resource_type TEXT NOT NULL,
    resource_id TEXT NOT NULL,
    merge_strategy TEXT NOT NULL,
    winner_device_id TEXT NOT NULL,
    loser_device_id TEXT NOT NULL,
    winner_vector_clock TEXT,  -- JSON-encoded
    loser_vector_clock TEXT,   -- JSON-encoded
    conflict_reason TEXT,
    merged_at TEXT NOT NULL,   -- ISO8601 timestamp
    tenant_id TEXT
);

CREATE INDEX IF NOT EXISTS idx_crdt_merge_resource ON st_crdt_merge_log(resource_type, resource_id);
CREATE INDEX IF NOT EXISTS idx_crdt_merge_device ON st_crdt_merge_log(winner_device_id, loser_device_id);
CREATE INDEX IF NOT EXISTS idx_crdt_merge_ts ON st_crdt_merge_log(merged_at DESC);
```

**Indexes**:
- `idx_crdt_merge_resource`: Query merge history by resource (e.g., all merges for event_id)
- `idx_crdt_merge_device`: Query merge history by device (e.g., all conflicts involving device_001)
- `idx_crdt_merge_ts`: Query recent merges (e.g., last 24 hours)

---

## Usage Examples

### Basic Conflict Resolution

```python
from k0.sync import CRDTMergeLogger, resolve_conflict_with_logging

logger = CRDTMergeLogger()

# Resolve conflict
winner = resolve_conflict_with_logging(
    local_memory=local_memory,
    remote_memory=remote_memory,
    resource_type="st_epi",
    resource_id="evt_abc123",
    logger=logger,
    merge_strategy="vector-clock",
)

# Use winning memory
save_to_database(winner)
```

### Manual Logging

```python
# Determine winner with custom logic
winner = custom_merge_logic(local_memory, remote_memory)

# Log the decision
logger.log_merge(
    merge_id=str(uuid.uuid4()),
    resource_type="st_epi",
    resource_id="evt_abc123",
    merge_strategy="manual",
    winner_device_id=winner["device_id"],
    loser_device_id=loser["device_id"],
    winner_vector_clock=winner["vector_clock"],
    loser_vector_clock=loser["vector_clock"],
    conflict_reason="Manual resolution by operator",
)
```

### Query Merge History

```python
# Get all merges for a specific memory
history = logger.get_merge_history(
    resource_type="st_epi",
    resource_id="evt_abc123",
    limit=10,
)

print(f"Found {len(history)} merge events for evt_abc123")

# Analyze conflict patterns
for entry in history:
    print(f"{entry.merged_at}: {entry.merge_strategy}")
    print(f"  Winner: {entry.winner_device_id} (VC: {entry.winner_vector_clock})")
    print(f"  Loser: {entry.loser_device_id} (VC: {entry.loser_vector_clock})")
    print(f"  Reason: {entry.conflict_reason}")
```

### Device-Specific Conflicts

```python
# Find all conflicts involving a specific device
conflicts = logger.get_merge_history(
    device_id="device_001",
    limit=50,
)

# Analyze device conflict rate
winner_count = sum(1 for c in conflicts if c.winner_device_id == "device_001")
loser_count = sum(1 for c in conflicts if c.loser_device_id == "device_001")

print(f"Device device_001 conflict stats:")
print(f"  Won: {winner_count}/{len(conflicts)} ({winner_count/len(conflicts)*100:.1f}%)")
print(f"  Lost: {loser_count}/{len(conflicts)} ({loser_count/len(conflicts)*100:.1f}%)")
```

---

## Integration Points

### Upstream Dependencies

- **Python stdlib**: `json`, `sqlite3`, `dataclasses`, `datetime`, `uuid`
- **`k0.uow.connection_pool`**: Connection pooling for database access

### Downstream Consumers

- **Multi-device sync workers**: Use `resolve_conflict_with_logging()` during sync
- **Episodic memory merging**: CRDT conflict resolution for `st_epi` table
- **Semantic memory CRDT**: Conflict resolution for `st_sem` table
- **Analytics dashboards**: Query `st_crdt_merge_log` for conflict metrics

---

## Performance & Observability

### Metrics

- **Conflict rate**: `SELECT COUNT(*) FROM st_crdt_merge_log WHERE merged_at >= ?`
- **Strategy distribution**: `SELECT merge_strategy, COUNT(*) FROM st_crdt_merge_log GROUP BY merge_strategy`
- **Device conflict rates**: Winner/loser ratios per device_id

### Performance Targets

| Operation | Latency | Throughput |
|-----------|---------|------------|
| `log_merge()` | <5ms | 200 ops/s |
| `get_merge_history()` | <10ms | 100 queries/s |
| `resolve_conflict_with_logging()` | <10ms | 100 ops/s |

---

## Error Handling

### `CRDTMergeLoggerError`

- **Raised When**: Database operation fails (except "table not found")
- **Handling**: Log error, emit metrics, fallback to in-memory logging

**Example**:

```python
from k0.sync import CRDTMergeLogger, CRDTMergeLoggerError

logger = CRDTMergeLogger()

try:
    logger.log_merge(...)
except CRDTMergeLoggerError as exc:
    logger_fallback.error(f"CRDT merge logging failed: {exc}")
    metrics.emit("crdt_merge_log_failures_total", 1.0)
```

---

## Related Modules

- **`k0.storage.wal`**: WAL entries include vector clock metadata (future)
- **`k0.workers.sync`**: Multi-device synchronization workers
- **`k0.obs`**: Metrics for conflict resolution rates

---

## Related ADRs

- **ADR-0150**: CRDT Merge Logger Design (Migration 0004)
- **ADR-0151**: Vector Clock Conflict Resolution Strategy
- **ADR-0152**: Multi-Device Synchronization Architecture

---

## Key Design Decisions

1. **Audit Trail**: All CRDT merges logged for debugging and compliance
2. **Vector Clock Strategy**: Causality-based conflict resolution (Honda 2008, Shapiro 2011)
3. **Tiebreaker Chain**: Self-clock → device_id for deterministic concurrent resolution
4. **JSON Vector Clocks**: Store as JSON strings for flexibility (no schema changes for new devices)
5. **Defensive Logging**: Silently handle missing table (Migration 0004) to avoid breaking sync
6. **Helper Function**: `resolve_conflict_with_logging()` combines resolution + logging for convenience
7. **Device-Scoped Queries**: Indexes support device-specific conflict analysis
