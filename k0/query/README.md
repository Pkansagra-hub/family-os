# K0 Query Recall System

**Purpose**: Driver-based query execution engine with selector resolution, WAL/FTS drivers, time budgeting, top-k limiting, and streaming support for memory recall operations.

**Layer**: Data Access (Query Path)
**Category**: Query aggregation and driver SPI
**Related ADRs**: ADR-0100 (Query Architecture), ADR-0101 (Driver SPI), ADR-0106 (Time Budgets)

---

## Overview

The query module implements **pluggable driver architecture** for memory recall with:

1. **Driver registry** resolving selectors to concrete implementations
2. **WAL driver** (primary): Timeline-based recall from `st_wal`
3. **FTS driver**: Full-text search via SQLite FTS5 virtual table
4. **Alias drivers**: Placeholders for future vector/kg/snapshot drivers
5. **Query aggregator**: Coordinates multi-selector execution with time/budget constraints
6. **Gap 31 fix**: Defensive connection cleanup to prevent SQLite leaks

**Architecture Pattern**: Strategy pattern (driver SPI) + aggregator + time slicing

**Performance Targets**: Query recall <200ms P95, driver execution <75ms P95

---

## Repository Files & Functions

### 1. `common.py`

**Purpose**: Common data structures for the query driver SPI.

#### Classes & Protocols

```python
@dataclass(slots=True)
class DriverContext:
    space_id: str
    tenant_id: str | None
    selector_index: int
    allowed_limit: int
    remaining_top_k: int
    time_budget_ms: int
    elapsed_ms: float
```

- **Purpose**: Execution context passed to every query driver
- **Budgets**: `allowed_limit` (current selector), `remaining_top_k` (total budget across selectors)
- **Time tracking**: `time_budget_ms` (total), `elapsed_ms` (consumed so far)
- **Usage**: Drivers use context to enforce limits and detect budget exhaustion

```python
@dataclass(slots=True)
class DriverExecution:
    driver: str
    selector_index: int
    selector: Mapping[str, Any]
    items: list[dict[str, Any]] = field(default_factory=list)
    next_cursor: int | None = None
    latency_ms: float = 0.0
    consumed_top_k: int = 0
    exhausted_time_budget: bool = False
    metadata: MutableMapping[str, Any] = field(default_factory=dict)
```

- **Purpose**: Result returned by a query driver
- **Cursor**: Pagination offset for resuming queries
- **Latency**: Driver execution time for observability
- **Metadata**: Driver-specific details (source table, status, BM25 scores)

```python
class QueryDriver(Protocol):
    name: str

    def supports(self, selector: Any) -> bool
    def execute(self, selector: Any, context: DriverContext) -> DriverExecution
```

- **Protocol**: Structural typing for query drivers
- **`supports()`**: Return `True` if driver can handle selector type
- **`execute()`**: Execute recall and return results with metadata

**Example Driver**:

```python
class CustomDriver(QueryDriver):
    name = "custom"

    def supports(self, selector: Any) -> bool:
        return getattr(selector, "type", None) == "custom"

    def execute(self, selector: Any, context: DriverContext) -> DriverExecution:
        items = fetch_custom_data(selector, context.allowed_limit)
        return DriverExecution(
            driver=self.name,
            selector_index=context.selector_index,
            selector={"type": "custom"},
            items=items,
            latency_ms=100.0,
            consumed_top_k=len(items),
        )
```

---

### 2. `drivers.py`

**Purpose**: Driver registry and built-in implementations (WAL, FTS, aliases).

#### Classes

```python
class DriverRegistry:
    def __init__(self, drivers: Sequence[QueryDriver] | None = None)
    def register(self, driver: QueryDriver) -> None
    def extend(self, drivers: Iterable[QueryDriver]) -> None
    def resolve(self, selector: Any) -> QueryDriver
    @property
    def drivers(self) -> Sequence[QueryDriver]
```

- **Purpose**: Registry that resolves selectors to concrete drivers
- **Resolution**: First driver where `supports(selector) == True`
- **Raises**: `LookupError` if no driver supports selector

**Example**:

```python
registry = DriverRegistry()
registry.register(WalDriver(default_limit=50, max_limit=1000))
registry.register(FtsDriver(default_limit=50, max_limit=1000))

# Resolve selector
driver = registry.resolve(selector)  # Returns WalDriver or FtsDriver
result = driver.execute(selector, context)
```

```python
def build_default_registry(*, default_limit: int, max_limit: int) -> DriverRegistry
```

- **Purpose**: Factory for default registry with built-in drivers
- **Drivers**: WAL (primary), FTS (full-text), episodic/snapshot/vector/kg (aliases)
- **Usage**: Called by `QueryAggregator.__init__()` if no registry provided

```python
class WalDriver(QueryDriver):
    name = "wal"

    def __init__(self, *, default_limit: int, max_limit: int)
    def supports(self, selector: Any) -> bool
    def execute(self, selector: Any, context: DriverContext) -> DriverExecution
```

- **Purpose**: Primary driver querying `st_wal` table for timeline recall
- **Supports**: Types `wal`, `timeline`, `episodic`, `memory.timeline`, `event`, `default`
- **Query pattern**: `SELECT * FROM st_wal WHERE space_id = ? AND topic = ? AND pos < cursor ORDER BY pos DESC LIMIT ?`
- **Gap 31 fix**: Defensive connection cleanup with `connection_scope()`

**Algorithm**:

```python
def execute(self, selector: Any, context: DriverContext) -> DriverExecution:
    # Extract selector fields
    topic = getattr(selector, "topic", None)
    cursor = getattr(selector, "cursor", None)
    after = getattr(selector, "after", None)

    # Query WAL
    start = time.perf_counter()
    try:
        with connection_scope() as connection:  # Gap 31: Defensive cleanup
            rows = self._fetch_rows(
                connection,
                space_id=context.space_id,
                tenant_id=context.tenant_id,
                topic=topic,
                cursor=cursor,
                after=after,
                limit=context.allowed_limit,
            )
        latency_ms = (time.perf_counter() - start) * 1_000.0
    except Exception:
        # Connection cleanup handled by connection_scope()'s finally block
        raise

    # Convert rows to items
    items = [self._row_to_item(row) for row in rows]

    # Resolve next cursor (min wal_pos)
    next_cursor = min(item["wal_pos"] for item in items) if items else cursor

    # Check time budget
    exhausted_time_budget = context.elapsed_ms + latency_ms >= context.time_budget_ms

    return DriverExecution(
        driver=self.name,
        selector_index=context.selector_index,
        selector={"type": "wal", "topic": topic},
        items=items,
        next_cursor=next_cursor,
        latency_ms=round(latency_ms, 3),
        consumed_top_k=len(items),
        exhausted_time_budget=exhausted_time_budget,
        metadata={"source": "st_wal", "rows": len(items)},
    )
```

**Row Conversion**:

```python
def _row_to_item(self, row: sqlite3.Row) -> dict[str, Any]:
    body_value = _decode_body(row["body"]) if "body" in row.keys() else None
    return {
        "wal_pos": row["pos"],
        "tenant_id": row["tenant_id"],
        "space_id": row["space_id"],
        "topic": row["topic"],
        "commit_ts": row["commit_ts"],
        "schema_uri": row["schema_uri"],
        "schema_version": row["schema_version"],
        "device_id": row["device_id"],
        "payload_sha256": row["payload_sha256"],
        "envelope": json.loads(row["envelope_json"]),
        "body": body_value,  # Decoded JSON or base64
    }
```

**Helper Functions**:

```python
def _decode_body(body: bytes | str | None) -> Any
```

- **Purpose**: Decode body field from WAL/FTS (handles bytes, strings, JSON, base64)
- **Cases**:
  - `None` → `None`
  - `str` → Try JSON decode → fallback to plain string
  - `bytes` → UTF-8 decode → Try JSON decode → fallback to base64
- **Usage**: Called by `_row_to_item()` for both WAL and FTS drivers

```python
def _resolve_next_cursor(items: list[dict[str, Any]], cursor: int | None) -> int | None
```

- **Purpose**: Calculate next cursor (min wal_pos across items)
- **Returns**: `None` if no items, otherwise `min(item["wal_pos"])`

```python
class FtsDriver(QueryDriver):
    name = "fts"

    def __init__(self, *, default_limit: int, max_limit: int)
    def supports(self, selector: Any) -> bool
    def execute(self, selector: Any, context: DriverContext) -> DriverExecution
```

- **Purpose**: Full-text search driver using SQLite FTS5 virtual table
- **Supports**: Types `fts`, `semantic`, `semantic_memory`, `fulltext`, `text`
- **Query pattern**: `SELECT * FROM st_fts WHERE st_fts MATCH 'query' AND space_id = ? ORDER BY bm25(st_fts) LIMIT ?`
- **BM25 scoring**: Relevance-ranked results (lower score = more relevant)

**Algorithm**:

```python
def execute(self, selector: Any, context: DriverContext) -> DriverExecution:
    query = getattr(selector, "query", None)
    if not query:
        # No query provided, return empty result
        return DriverExecution(
            driver=self.name,
            selector_index=context.selector_index,
            selector={"type": "fts"},
            latency_ms=0.0,
            metadata={"status": "no_query"},
        )

    # Execute FTS search
    start = time.perf_counter()
    try:
        with connection_scope() as connection:  # Gap 31: Defensive cleanup
            rows = self._search_fts(
                connection,
                space_id=context.space_id,
                tenant_id=context.tenant_id,
                topic=getattr(selector, "topic", None),
                query=query,
                limit=context.allowed_limit,
            )
        latency_ms = (time.perf_counter() - start) * 1_000.0
    except Exception:
        raise

    items = [self._row_to_item(row) for row in rows]

    return DriverExecution(
        driver=self.name,
        selector_index=context.selector_index,
        selector={"type": "fts", "query": query},
        items=items,
        latency_ms=round(latency_ms, 3),
        consumed_top_k=len(items),
        exhausted_time_budget=context.elapsed_ms + latency_ms >= context.time_budget_ms,
        metadata={"source": "st_fts", "rows": len(items), "query": query},
    )
```

**FTS Item Conversion**:

```python
def _row_to_item(self, row: sqlite3.Row) -> dict[str, Any]:
    # Same as WalDriver, but includes FTS score
    item = super()._row_to_item(row)
    item["fts_score"] = row["score"]  # BM25 relevance score
    return item
```

```python
@dataclass(slots=True)
class AliasDriver(QueryDriver):
    name: str
    supported_types: set[str]
    reason: str

    def supports(self, selector: Any) -> bool
    def execute(self, selector: Any, context: DriverContext) -> DriverExecution
```

- **Purpose**: Placeholder driver for unimplemented selector types
- **Returns**: Empty result with `status: unavailable` metadata
- **Usage**: Future drivers (vector search, knowledge graph, snapshots)

**Example**:

```python
vector_alias = AliasDriver(
    name="vector",
    supported_types={"vector", "semantic_vector", "embedding"},
    reason="vector recall driver not configured",
)

# Supports selector
assert vector_alias.supports(selector) is True  # If selector.type == "vector"

# Execute returns empty result
result = vector_alias.execute(selector, context)
assert result.items == []
assert result.metadata["status"] == "unavailable"
assert result.metadata["reason"] == "vector recall driver not configured"
```

---

### 3. `service.py`

**Purpose**: Query aggregator coordinating multi-selector execution with time/budget constraints.

#### Classes & Protocols

```python
class SelectorLike(Protocol):
    topic: str | None
    limit: int | None
    cursor: int | None
    tenant_id: str | None
    space_id: str | None
    type: str | None
    after: int | None
```

- **Purpose**: Structural protocol for selector fields
- **Usage**: Duck typing for selector objects (Pydantic models, dicts, dataclasses)

```python
@dataclass(slots=True)
class SelectorBundle:
    index: int
    driver: str
    selector: Mapping[str, Any]
    items: list[dict[str, Any]]
    next_cursor: int | None
    latency_ms: float
    metadata: dict[str, Any]

    def as_dict(self) -> dict[str, Any]
```

- **Purpose**: Envelope for a single selector's results
- **Fields**: Selector metadata, items, cursor, latency, driver name
- **Usage**: Returned in `QueryExecutionResult.bundles`

```python
@dataclass(slots=True)
class QueryExecutionResult:
    bundles: list[SelectorBundle]
    elapsed_ms: float
    consumed_top_k: int
    processed_selectors: int
    exhausted_time_budget: bool
    trace_nodes: list[dict[str, Any]]

    def bundle_payload(self) -> dict[str, Any]
```

- **Purpose**: Aggregate result from multi-selector execution
- **Trace nodes**: Per-selector latency/status for observability
- **Budget tracking**: Total top_k consumed, time elapsed, selectors processed

```python
class QueryAggregator:
    def __init__(
        self,
        *,
        registry: DriverRegistry | None = None,
        default_limit: int = DEFAULT_SELECTOR_LIMIT,
        max_limit: int = MAX_SELECTOR_LIMIT,
    )
```

- **Purpose**: Coordinate query drivers with QoS budgets
- **Registry**: Driver resolution (default: `build_default_registry()`)
- **Limits**: `default_limit=8`, `max_limit=256`

#### Methods

```python
def execute(
    self,
    selectors: Sequence[SelectorLike],
    *,
    space_id: str,
    tenant_id: str | None,
    time_budget_ms: int,
    top_k_budget: int,
) -> QueryExecutionResult
```

- **Purpose**: Execute multi-selector query with time/budget constraints
- **Algorithm**:
  1. Validate budgets (time_budget_ms > 0, top_k_budget > 0)
  2. For each selector:
     - Resolve driver via registry
     - Check remaining top_k budget
     - Execute driver with context
     - Accumulate results
     - Check time budget exhaustion
     - Early exit if budget exhausted
  3. Return aggregated result

**Flow**:

```python
remaining_top_k = top_k_budget
total_elapsed_ms = 0.0
bundles = []
trace_nodes = []

for index, selector in enumerate(selectors):
    # Check budget
    if remaining_top_k <= 0:
        trace_nodes.append({
            "stage": "query.driver.skipped",
            "selector_index": index,
            "status": "top_k_exhausted",
        })
        break

    # Resolve driver
    driver = self._registry.resolve(selector)
    allowed_limit = self._resolve_limit(selector.limit, remaining_top_k)

    # Build context
    context = DriverContext(
        space_id=space_id,
        tenant_id=tenant_id,
        selector_index=index,
        allowed_limit=allowed_limit,
        remaining_top_k=remaining_top_k,
        time_budget_ms=time_budget_ms,
        elapsed_ms=total_elapsed_ms,
    )

    # Execute driver
    execution = driver.execute(selector, context)

    # Update budgets
    consumed_top_k += execution.consumed_top_k
    remaining_top_k = max(0, remaining_top_k - execution.consumed_top_k)
    total_elapsed_ms += execution.latency_ms

    # Add to results
    bundles.append(SelectorBundle(
        index=index,
        driver=execution.driver,
        selector=execution.selector,
        items=execution.items,
        next_cursor=execution.next_cursor,
        latency_ms=execution.latency_ms,
        metadata=execution.metadata,
    ))

    trace_nodes.append({
        "stage": f"query.driver.{execution.driver}",
        "selector_index": index,
        "latency_ms": execution.latency_ms,
        "items": len(execution.items),
    })

    # Check time budget
    if execution.exhausted_time_budget or total_elapsed_ms >= time_budget_ms:
        break

return QueryExecutionResult(
    bundles=bundles,
    elapsed_ms=total_elapsed_ms,
    consumed_top_k=consumed_top_k,
    processed_selectors=len(bundles),
    exhausted_time_budget=total_elapsed_ms >= time_budget_ms,
    trace_nodes=trace_nodes,
)
```

**Helper Methods**:

```python
def _resolve_limit(self, requested: int | None, remaining_top_k: int) -> int
```

- **Purpose**: Calculate allowed limit for selector
- **Rules**:
  1. Use `requested` if provided, else `default_limit`
  2. Clamp to `max_limit`
  3. Clamp to `remaining_top_k`
  4. Return at least 1 if budget available

**Example**:

```python
# requested=50, remaining_top_k=100, max_limit=256
allowed = aggregator._resolve_limit(50, 100)  # → 50

# requested=None, remaining_top_k=100, default_limit=8
allowed = aggregator._resolve_limit(None, 100)  # → 8

# requested=500, remaining_top_k=100, max_limit=256
allowed = aggregator._resolve_limit(500, 100)  # → 100 (clamped to remaining)

# requested=50, remaining_top_k=5, max_limit=256
allowed = aggregator._resolve_limit(50, 5)  # → 5 (clamped to remaining)
```

---

## Connections & Integration Points

### Upstream Dependencies

1. **`k0.uow.connection_pool.connection_scope()`**: SQLite connection management (Gap 31 fix)
2. **`k0.storage.wal`**: `st_wal` table for timeline recall
3. **`k0.storage.fts`**: `st_fts` virtual table for full-text search
4. **`k0.qos.context.QoSContext`**: Top-k budget tracking and consumption

### Downstream Consumers

1. **`k0.ports.query.query_recall()`**: HTTP handler using `QueryAggregator.execute()`
2. **`k0.ports.sse.subscribe()`**: SSE streaming using WAL driver
3. **`k0.cli.query`**: CLI commands for recall operations

### Data Flow

#### Query Recall Flow

```
┌─────────────────────────────────────────────────────────────────┐
│ 1. Query Request                                                 │
│    POST /k0/query.recall                                         │
│    selectors = [                                                 │
│      {"type": "wal", "topic": "family.photos", "limit": 50},    │
│      {"type": "fts", "query": "birthday party"}                 │
│    ]                                                             │
└────────────────────────┬────────────────────────────────────────┘
                         │
                         ▼
┌─────────────────────────────────────────────────────────────────┐
│ 2. QueryAggregator Initialization                                │
│    aggregator = QueryAggregator(registry=default_registry)       │
│    time_budget_ms = 200                                          │
│    top_k_budget = 100                                            │
└────────────────────────┬────────────────────────────────────────┘
                         │
                         ▼
┌─────────────────────────────────────────────────────────────────┐
│ 3. Execute Selectors Sequentially                                │
│    For selector[0] (WAL):                                        │
│      - registry.resolve(selector) → WalDriver                    │
│      - context = DriverContext(                                  │
│          allowed_limit=50,                                       │
│          remaining_top_k=100,                                    │
│          elapsed_ms=0.0                                          │
│        )                                                         │
│      - execution = wal_driver.execute(selector, context)         │
│      - consumed_top_k = 50                                       │
│      - elapsed_ms = 45.0                                         │
└────────────────────────┬────────────────────────────────────────┘
                         │
                         ▼
┌─────────────────────────────────────────────────────────────────┐
│ 4. Update Budgets                                                │
│    remaining_top_k = 100 - 50 = 50                              │
│    total_elapsed_ms = 45.0                                       │
│    Check: 45.0 < 200 → continue                                  │
└────────────────────────┬────────────────────────────────────────┘
                         │
                         ▼
┌─────────────────────────────────────────────────────────────────┐
│ 5. Execute Selector[1] (FTS)                                     │
│    For selector[1] (FTS):                                        │
│      - registry.resolve(selector) → FtsDriver                    │
│      - context = DriverContext(                                  │
│          allowed_limit=50,  # min(requested, remaining_top_k)   │
│          remaining_top_k=50,                                     │
│          elapsed_ms=45.0                                         │
│        )                                                         │
│      - execution = fts_driver.execute(selector, context)         │
│      - consumed_top_k = 30                                       │
│      - elapsed_ms = 65.0                                         │
└────────────────────────┬────────────────────────────────────────┘
                         │
                         ▼
┌─────────────────────────────────────────────────────────────────┐
│ 6. Return Aggregated Result                                      │
│    QueryExecutionResult{                                         │
│      bundles=[                                                   │
│        SelectorBundle{driver="wal", items=[...50 items...]},    │
│        SelectorBundle{driver="fts", items=[...30 items...]}     │
│      ],                                                          │
│      elapsed_ms=110.0,                                           │
│      consumed_top_k=80,                                         │
│      processed_selectors=2,                                      │
│      exhausted_time_budget=False,                               │
│      trace_nodes=[...]                                          │
│    }                                                             │
└─────────────────────────────────────────────────────────────────┘
```

---

## Testing

### Unit Tests

```python
# tests/k0/query/test_drivers.py
def test_wal_driver_supports():
    driver = WalDriver(default_limit=50, max_limit=1000)
    assert driver.supports(Selector(type="wal"))
    assert driver.supports(Selector(type="timeline"))
    assert not driver.supports(Selector(type="vector"))

def test_wal_driver_execute(db_connection):
    driver = WalDriver(default_limit=50, max_limit=1000)
    context = DriverContext(
        space_id="space_001",
        tenant_id="tenant_001",
        selector_index=0,
        allowed_limit=10,
        remaining_top_k=100,
        time_budget_ms=200,
        elapsed_ms=0.0,
    )

    execution = driver.execute(selector, context)
    assert execution.driver == "wal"
    assert len(execution.items) <= 10
    assert execution.consumed_top_k == len(execution.items)

def test_fts_driver_execute(db_connection):
    driver = FtsDriver(default_limit=50, max_limit=1000)
    selector = Selector(type="fts", query="family photos")

    execution = driver.execute(selector, context)
    assert execution.driver == "fts"
    assert all("fts_score" in item for item in execution.items)
    assert execution.metadata["query"] == "family photos"

# tests/k0/query/test_service.py
def test_query_aggregator_multi_selector():
    aggregator = QueryAggregator()
    selectors = [
        Selector(type="wal", limit=50),
        Selector(type="fts", query="test", limit=30),
    ]

    result = aggregator.execute(
        selectors,
        space_id="space_001",
        tenant_id="tenant_001",
        time_budget_ms=200,
        top_k_budget=100,
    )

    assert result.processed_selectors == 2
    assert result.consumed_top_k <= 100
    assert result.elapsed_ms < 200

def test_query_aggregator_top_k_exhaustion():
    aggregator = QueryAggregator()
    selectors = [
        Selector(type="wal", limit=50),
        Selector(type="wal", limit=50),
        Selector(type="wal", limit=50),  # This should be skipped
    ]

    result = aggregator.execute(
        selectors,
        space_id="space_001",
        tenant_id="tenant_001",
        time_budget_ms=1000,
        top_k_budget=80,  # Only enough for 2 selectors
    )

    assert result.processed_selectors == 2  # Third skipped
    assert result.consumed_top_k <= 80
```

### Integration Tests

```python
# tests/integration/test_query_recall.py
def test_query_recall_wal_driver(kernel_client, db_seeded):
    response = kernel_client.post("/k0/query.recall", json={
        "selectors": [
            {"type": "wal", "topic": "family.photos", "limit": 10}
        ],
        "space_id": "space_001",
        "tenant_id": "tenant_001",
    })
    assert response.status_code == 200
    result = response.json()
    assert result["status"] == "OK"
    assert len(result["events"]) <= 10

def test_query_recall_fts_driver(kernel_client, db_seeded):
    response = kernel_client.post("/k0/query.recall", json={
        "selectors": [
            {"type": "fts", "query": "birthday party", "limit": 20}
        ],
        "space_id": "space_001",
        "tenant_id": "tenant_001",
    })
    assert response.status_code == 200
    result = response.json()
    assert all("fts_score" in event for event in result["events"])
```

---

## Performance & Observability

### Metrics

- `k0_query_driver_executions_total{driver, selector_type}` (counter): Driver executions
- `k0_query_driver_latency_ms{driver}` (histogram): Driver latency (buckets: 10, 25, 50, 75, 100, 250ms)
- `k0_query_top_k_consumed{selector_type}` (histogram): Top-k consumed per selector
- `k0_query_time_budget_exhausted_total` (counter): Queries exhausting time budget

### Traces

- Span: `query.aggregator.execute` (selectors, elapsed_ms, consumed_top_k)
- Span: `query.driver.{driver_name}` (selector_index, latency_ms, items)

### Logging

```json
{
  "event": "Query driver executed",
  "driver": "wal",
  "selector_index": 0,
  "items": 50,
  "latency_ms": 45.0,
  "consumed_top_k": 50,
  "remaining_top_k": 50,
  "exhausted_time_budget": false
}
```

---

## Related Modules

- **`k0.ports.query`**: HTTP handler using `QueryAggregator`
- **`k0.storage.wal`**: WAL table for timeline recall
- **`k0.storage.fts`**: FTS5 virtual table for full-text search
- **`k0.qos.context`**: Top-k budget tracking
- **`k0.uow.connection_pool`**: SQLite connection management

---

## Related ADRs

- **ADR-0100**: Query Architecture and Driver SPI
- **ADR-0101**: Driver Registry and Resolution
- **ADR-0106**: Time Budgets and QoS Tightening

---

## Key Design Decisions

1. **Driver SPI**: Pluggable architecture for extensibility (vector, KG, snapshot drivers)
2. **Gap 31 fix**: Defensive connection cleanup prevents SQLite leaks
3. **Time budgets**: Hard stop at budget exhaustion with cursor pagination
4. **Top-k budgets**: Shared across selectors, enforced at aggregator level
5. **BM25 scoring**: FTS driver includes relevance scores in results
6. **Alias drivers**: Placeholders for unimplemented selector types
7. **Sequential execution**: Selectors processed in order (no parallelism yet)
8. **Body decoding**: Handles bytes, strings, JSON, base64 transparently
