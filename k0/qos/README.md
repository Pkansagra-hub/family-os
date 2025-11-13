# K0 Quality-of-Service (QoS) Scheduler

**Purpose**: Work-conserving scheduler enforcing coarse port budgets with fanout/top-k budget tracking, token acquisition, and policy-driven tightening for kernel operations.

**Layer**: Infrastructure (Cross-cutting)
**Category**: Resource management and rate limiting
**Related ADRs**: ADR-0097 (QoS Budgets), ADR-0098 (Scheduler Profiles), ADR-0103 (Budget Tightening)

---

## Overview

The QoS module implements **token-based scheduling** to prevent kernel overload while maintaining fairness across ports (command, query, SSE). It provides:

1. **Port-based token buckets** with configurable limits per profile
2. **Per-request budget tracking** (fanout, top_k) with tightening API
3. **Work-conserving scheduling** (tokens released immediately on completion)
4. **Policy obligation integration** (apply QoS tightening from PEP decisions)
5. **Chaos engineering support** (scheduler starvation injection)
6. **Prometheus metrics** (token acquisitions, rejections, utilization)

**Architecture Pattern**: Token bucket + budget tracking + context injection

**Performance Targets**: Token acquisition <1ms P95, port utilization 60-80%

---

## Repository Files & Functions

### 1. `__init__.py`

**Purpose**: Export QoS public API.

```python
__all__ = [
    "QoSBudgetError",
    "QoSContext",
    "SchedulerToken",
    "Scheduler",
    "SchedulerCapacityError",
    "SchedulerProfile",
    "QoSMetrics",
    "QoSTightening",
    "apply_qos_obligations",
    "coerce_positive_int",
]
```

- **Core types**: Context tracking, scheduler, profiles, metrics
- **Policy helpers**: Obligation parsing, budget tightening

---

### 2. `context.py`

**Purpose**: Per-request QoS context with mutable budgets and scheduler access.

#### Classes

```python
@dataclass(slots=True)
class QoSContext:
    scheduler: Scheduler
    fanout_budget: int
    top_k_budget: int
```

- **Mutable budgets**: Fanout (max fan-out operations), top_k (max results)
- **Scheduler handle**: Direct token acquisition for port operations
- **Injection**: Passed via FastAPI `Depends()` to port handlers

#### Methods

```python
def tighten(self, *, fanout: int | None = None, top_k: int | None = None) -> None
```

- **Purpose**: Clamp budgets to tighter values (one-way: cannot increase)
- **Usage**: Called by policy obligation handlers to reduce budgets
- **Validation**: Raises `ValueError` if negative values provided

**Example**:

```python
qos = QoSContext(scheduler=scheduler, fanout_budget=50, top_k_budget=100)

# Apply policy tightening
qos.tighten(fanout=10, top_k=20)

assert qos.fanout_budget == 10  # Clamped from 50 to 10
assert qos.top_k_budget == 20   # Clamped from 100 to 20

# Cannot increase
qos.tighten(fanout=30)  # No effect (already 10)
assert qos.fanout_budget == 10
```

```python
def consume_fanout(self, amount: int = 1) -> None
def consume_top_k(self, amount: int = 1) -> None
```

- **Purpose**: Consume from budgets with exhaustion checking
- **Raises**: `QoSBudgetError` if budget exhausted
- **Usage**: Called by query drivers when fanning out or returning results

```python
def acquire(self, *, band: str, port: str, cost: int) -> SchedulerToken
```

- **Purpose**: Acquire scheduler token for port operation
- **Delegates**: To `Scheduler.acquire()` with band/port/cost
- **Returns**: `SchedulerToken` (context manager for auto-release)

#### Exceptions

```python
class QoSBudgetError(RuntimeError):
    """Raised when QoS budgets are exceeded."""
```

- **Usage**: Caught by port handlers → 429 Too Many Requests

---

### 3. `scheduler.py`

**Purpose**: Work-conserving scheduler with port-based token buckets.

#### Classes

```python
@dataclass(slots=True)
class SchedulerProfile:
    name: str
    description: str
    port_limits: dict[str, int]
    default_port_limit: int = 16
```

- **Profiles**: Named configurations (e.g., "balanced", "high_throughput", "constrained")
- **Port limits**: Per-port token capacity (command: 16, query: 24, sse: 32)
- **Default**: Fallback limit for unconfigured ports

**Example**:

```python
profile = SchedulerProfile(
    name="balanced",
    description="Default balanced profile",
    port_limits={"command": 16, "query": 24, "sse": 32},
    default_port_limit=16,
)
```

```python
@dataclass(slots=True)
class SchedulerToken:
    _release_cb: Callable[[str, int], None]
    port: str
    cost: int
    _released: bool = False
```

- **Context manager**: Auto-releases token on exit
- **Manual release**: Call `.release()` explicitly
- **Idempotent**: Multiple releases are safe (no-op)

**Usage**:

```python
# Context manager (preferred)
with qos.acquire(band="GREEN", port="command", cost=1) as token:
    # Token held during operation
    execute_command()
# Token auto-released here

# Manual release
token = qos.acquire(band="GREEN", port="command", cost=1)
try:
    execute_command()
finally:
    token.release()
```

```python
class Scheduler:
    def __init__(
        self,
        profile: SchedulerProfile | None = None,
        chaos_config=None,
        metrics_exporter=None,
        qos_metrics: QoSMetrics | None = None,
    )
```

- **Profile**: Scheduler profile with port limits
- **Chaos injection**: Optional capacity reduction via `apply_scheduler_starvation()`
- **Metrics**: Token acquisition/rejection tracking
- **Thread-safe**: Internal `Lock()` for active token tracking

#### Methods

```python
def acquire(self, *, band: str, port: str, cost: int) -> SchedulerToken
```

- **Purpose**: Acquire token if capacity available
- **Thread-safe**: Uses internal lock for capacity checks
- **Raises**: `SchedulerCapacityError` if port capacity exhausted
- **Metrics**: Records acquisition or rejection

**Algorithm**:

```python
with self._lock:
    current = self._active.get(port, 0)
    limit = self.profile.port_limits.get(port, self.profile.default_port_limit)

    if current + cost > limit:
        # Emit rejection metric
        self._qos_metrics.record_rejection_capacity(band=band, port=port)
        raise SchedulerCapacityError(...)

    self._active[port] = current + cost
    self._qos_metrics.record_acquisition(band=band, port=port)
    self._qos_metrics.update_port_metrics(port=port, active=current + cost, limit=limit)

return SchedulerToken(self._release, port, cost)
```

**Example**:

```python
scheduler = Scheduler(profile=balanced_profile)

# Acquire token
try:
    token = scheduler.acquire(band="GREEN", port="command", cost=1)
except SchedulerCapacityError as e:
    return 429, {"error": "Port capacity exhausted", "port": e.port}

# Use token
execute_command()

# Release token
token.release()
```

```python
def tighten(self, profile: SchedulerProfile) -> None
```

- **Purpose**: Hot-reload scheduler profile
- **Thread-safe**: Atomically updates limits and clamps active tokens
- **Usage**: Runtime profile switching without downtime

```python
def active_tokens(self, port: str) -> int
```

- **Purpose**: Query current active token count for port
- **Thread-safe**: Returns snapshot within lock
- **Usage**: Monitoring, health checks, admission control

#### Exceptions

```python
class SchedulerCapacityError(RuntimeError):
    def __init__(self, *, band: str, port: str, cost: int, limit: int)
```

- **Attributes**: `band`, `port`, `cost`, `limit`
- **Message**: Descriptive error with remaining capacity
- **Usage**: Caught by port handlers → 429 with retry-after hint

---

### 4. `policy.py`

**Purpose**: Parse policy obligations and apply QoS tightening to contexts.

#### Classes

```python
@dataclass(slots=True)
class QoSTightening:
    fanout: int | None = None
    top_k: int | None = None
    time_slice_ms: int | None = None
```

- **Purpose**: Represent tightening directives from obligations
- **Fields**: Fanout limit, top_k limit, time slice budget
- **Usage**: Returned by `apply_qos_obligations()`, consumed by port handlers

#### Functions

```python
def apply_qos_obligations(
    qos: QoSContext,
    obligations: Sequence[Any],
) -> QoSTightening
```

- **Purpose**: Apply `kernel.qos.tighten` obligations to context
- **Side effect**: Mutates `qos.fanout_budget` and `qos.top_k_budget`
- **Returns**: Tightening directives for additional limits (time_slice_ms)

**Algorithm**:

```python
schedule = QoSTightening()

for obligation in obligations:
    if obligation.name != "kernel.qos.tighten":
        continue

    details = obligation.details

    # Extract fanout limit
    fanout_limit = _extract_limit(details, ("fanout", "fanout_max", "max_fanout"))
    if fanout_limit is not None:
        qos.tighten(fanout=fanout_limit)
        schedule.fanout = min(schedule.fanout or fanout_limit, fanout_limit)

    # Extract top_k limit
    top_k_limit = _extract_limit(details, ("top_k", "top_k_max"))
    if top_k_limit is not None:
        qos.tighten(top_k=top_k_limit)
        schedule.top_k = min(schedule.top_k or top_k_limit, top_k_limit)

    # Extract time slice
    time_slice_limit = _extract_limit(details, ("time_slice", "time_slice_ms", ...))
    if time_slice_limit is not None:
        schedule.time_slice_ms = min(schedule.time_slice_ms or time_slice_limit, time_slice_limit)

return schedule
```

**Example**:

```python
from k0.policy.pep_syscall import Obligation

obligations = [
    Obligation(name="kernel.qos.tighten", details={"fanout": 5, "top_k": 10}),
    Obligation(name="kernel.redact.field", details={"fields": ["ssn"]}),
]

qos = QoSContext(scheduler=scheduler, fanout_budget=50, top_k_budget=100)

# Apply obligations
schedule = apply_qos_obligations(qos, obligations)

assert qos.fanout_budget == 5   # Tightened from 50
assert qos.top_k_budget == 10   # Tightened from 100
assert schedule.fanout == 5
assert schedule.top_k == 10
```

```python
def coerce_positive_int(value: Any) -> int | None
```

- **Purpose**: Best-effort coercion of obligation details to positive integers
- **Supports**: Primitives (int, float, str), dicts (nested keys), lists (first item)
- **Returns**: Positive integer or `None` if coercion fails

**Coercion rules**:

```python
coerce_positive_int(42)              # → 42
coerce_positive_int("100")           # → 100
coerce_positive_int(3.14)            # → 3 (truncated)
coerce_positive_int({"requested": 10})  # → 10
coerce_positive_int([20, 30])        # → 20 (first item)
coerce_positive_int(-5)              # → None (negative)
coerce_positive_int("")              # → None (empty string)
coerce_positive_int(None)            # → None
```

**Helper Function**:

```python
def _extract_limit(details: Mapping[str, Any], keys: Sequence[str]) -> int | None
```

- **Purpose**: Extract limit from obligation details using key aliases
- **Example**: `_extract_limit(details, ("fanout", "fanout_max", "max_fanout"))`
- **Returns**: First successfully coerced value or `None`

---

### 5. `metrics.py`

**Purpose**: Prometheus metrics for QoS token acquisition, rejections, and port utilization.

#### Classes

```python
class QoSMetrics:
    def __init__(self, metrics_exporter: MetricsExporter)
```

- **Metrics exporter**: Shared Prometheus registry
- **Counters**: Token acquisitions, rejection reasons, total rejections
- **Gauges**: Active tokens, port utilization %, port limits

#### Methods

```python
def record_acquisition(self, *, band: str, port: str) -> None
```

- **Counter**: `qos_token_acquisitions_total{band, port}`
- **Usage**: Called by `Scheduler.acquire()` on success

```python
def record_rejection_capacity(self, *, band: str, port: str) -> None
def record_rejection_outside_hours(self, *, band: str, port: str) -> None
def record_rejection_rate_limited(self, *, band: str, port: str) -> None
```

- **Counters**:
  - `qos_rejections_capacity_total{band, port}`
  - `qos_rejections_outside_hours_total{band, port}`
  - `qos_rejections_rate_limited_total{band, port}`
  - `qos_rejections_total{band, port, reason}`

- **Usage**: Called by `Scheduler.acquire()` on rejection

```python
def set_active_tokens(self, *, port: str, count: int) -> None
def set_port_utilization(self, *, port: str, percent: float) -> None
def set_port_limit(self, *, port: str, limit: int) -> None
```

- **Gauges**:
  - `qos_active_tokens{port}`
  - `qos_port_utilization_percent{port}`
  - `qos_port_limit_tokens{port}`

- **Usage**: Updated on every token acquisition/release

```python
def update_port_metrics(self, *, port: str, active: int, limit: int) -> None
```

- **Convenience**: Update all 3 gauges in one call
- **Calculates**: Utilization = `(active / limit) * 100`

**Example**:

```python
metrics = QoSMetrics(metrics_exporter)

# Token acquisition
metrics.record_acquisition(band="GREEN", port="command")
metrics.update_port_metrics(port="command", active=12, limit=16)
# → qos_token_acquisitions_total{band="GREEN", port="command"} = 1
# → qos_active_tokens{port="command"} = 12
# → qos_port_utilization_percent{port="command"} = 75.0
# → qos_port_limit_tokens{port="command"} = 16

# Token rejection
metrics.record_rejection_capacity(band="RED", port="command")
# → qos_rejections_capacity_total{band="RED", port="command"} = 1
# → qos_rejections_total{band="RED", port="command", reason="capacity"} = 1
```

---

### 6. `defaults.yaml`

**Purpose**: Placeholder scheduler defaults.

```yaml
reads:
  max_fanout: 3
  top_k: 8
  per_store_slice_ms: 75
writes:
  max_concurrency: 8
sse:
  heartbeat_ms: 8000
```

- **Note**: Not actively used (profiles defined in code)
- **Future**: Load profiles from YAML for runtime configuration

---

## Connections & Integration Points

### Upstream Dependencies

1. **`k0.obs.MetricsExporter`**: Prometheus metrics registry
2. **`k0.chaos.toggles`**: Chaos engineering (scheduler starvation)
3. **`k0.policy.pep_syscall.Obligation`**: Policy obligations for tightening

### Downstream Consumers

1. **`k0.ports.command`**: Acquires tokens for command submission
2. **`k0.ports.query`**: Acquires tokens + consumes fanout/top_k budgets
3. **`k0.ports.sse`**: Acquires tokens for SSE subscriptions
4. **`k0.query.service.QueryAggregator`**: Consumes top_k budget during selector execution
5. **`k0.policy.pep_syscall`**: Emits `kernel.qos.tighten` obligations

### Data Flow

#### Token Acquisition Flow

```
┌─────────────────────────────────────────────────────────────────┐
│ 1. Port Handler Request                                          │
│    POST /k0/command.submit                                       │
└────────────────────────┬────────────────────────────────────────┘
                         │
                         ▼
┌─────────────────────────────────────────────────────────────────┐
│ 2. QoS Context Injection (FastAPI Depends)                       │
│    qos = Depends(get_qos_context)                                │
│    → QoSContext(scheduler, fanout_budget=50, top_k_budget=100)   │
└────────────────────────┬────────────────────────────────────────┘
                         │
                         ▼
┌─────────────────────────────────────────────────────────────────┐
│ 3. Policy Evaluation                                             │
│    decision = pep.evaluate_envelope(envelope)                    │
│    obligations = decision.obligations                            │
│    → [Obligation(name="kernel.qos.tighten", details={...})]     │
└────────────────────────┬────────────────────────────────────────┘
                         │
                         ▼
┌─────────────────────────────────────────────────────────────────┐
│ 4. Apply QoS Tightening                                          │
│    schedule = apply_qos_obligations(qos, obligations)            │
│    → qos.fanout_budget = 10 (tightened from 50)                 │
│    → qos.top_k_budget = 20 (tightened from 100)                 │
└────────────────────────┬────────────────────────────────────────┘
                         │
                         ▼
┌─────────────────────────────────────────────────────────────────┐
│ 5. Acquire Scheduler Token                                       │
│    token = qos.acquire(band="GREEN", port="command", cost=1)    │
│    → Scheduler.acquire() checks capacity                         │
│    → If available: return SchedulerToken                         │
│    → If exhausted: raise SchedulerCapacityError                  │
└────────────────────────┬────────────────────────────────────────┘
                         │
                 ┌───────┴───────┐
                 │               │
           ✓ Acquired       ✗ Rejected
                 │               │
                 ▼               ▼
┌────────────────────────┐  ┌────────────────────────────────────┐
│ 6a. Execute Operation  │  │ 6b. Return 429                     │
│ with token:            │  │ HTTP 429 Too Many Requests         │
│ - Gate validation      │  │ Retry-After: 5                     │
│ - PEP enforcement      │  │ metrics: qos_rejections_capacity++ │
│ - UoW transaction      │  └────────────────────────────────────┘
│ - WAL append           │
│ - Token auto-released  │
│   on completion        │
└────────────────────────┘
```

#### Budget Consumption Flow (Query)

```
┌─────────────────────────────────────────────────────────────────┐
│ 1. Query Request                                                 │
│    POST /k0/query.recall                                         │
│    selectors = [                                                 │
│      {"type": "wal", "limit": 50},                              │
│      {"type": "fts", "query": "family photos"}                  │
│    ]                                                             │
└────────────────────────┬────────────────────────────────────────┘
                         │
                         ▼
┌─────────────────────────────────────────────────────────────────┐
│ 2. QoS Context + Token Acquisition                               │
│    qos = QoSContext(scheduler, fanout_budget=50, top_k_budget=100)│
│    token = qos.acquire(band="GREEN", port="query", cost=1)      │
└────────────────────────┬────────────────────────────────────────┘
                         │
                         ▼
┌─────────────────────────────────────────────────────────────────┐
│ 3. QueryAggregator.execute()                                     │
│    For each selector:                                            │
│      - Resolve driver (WalDriver, FtsDriver)                    │
│      - Check remaining_top_k budget                              │
│      - If budget exhausted: skip remaining selectors            │
└────────────────────────┬────────────────────────────────────────┘
                         │
                         ▼
┌─────────────────────────────────────────────────────────────────┐
│ 4. Driver Execution                                              │
│    driver.execute(selector, context)                             │
│    → Fetch 50 results from WAL                                  │
│    → consumed_top_k = 50                                        │
│    → qos.consume_top_k(50)                                      │
│    → remaining_top_k = 100 - 50 = 50                            │
└────────────────────────┬────────────────────────────────────────┘
                         │
                         ▼
┌─────────────────────────────────────────────────────────────────┐
│ 5. Next Selector                                                 │
│    driver.execute(selector2, context)                            │
│    → Fetch 30 results from FTS                                  │
│    → consumed_top_k = 30                                        │
│    → qos.consume_top_k(30)                                      │
│    → remaining_top_k = 50 - 30 = 20                             │
└────────────────────────┬────────────────────────────────────────┘
                         │
                         ▼
┌─────────────────────────────────────────────────────────────────┐
│ 6. Response                                                      │
│    RecallResponse{                                               │
│      bundles=[...80 results...],                                │
│      consumed_top_k=80,                                         │
│      budget_remaining=20                                        │
│    }                                                             │
│    token.release()                                              │
└─────────────────────────────────────────────────────────────────┘
```

---

## Testing

### Unit Tests

```python
# tests/k0/qos/test_scheduler.py
def test_acquire_token_success():
    profile = SchedulerProfile(name="test", port_limits={"command": 5})
    scheduler = Scheduler(profile=profile)

    token = scheduler.acquire(band="GREEN", port="command", cost=1)
    assert scheduler.active_tokens("command") == 1

    token.release()
    assert scheduler.active_tokens("command") == 0

def test_acquire_token_capacity_exceeded():
    profile = SchedulerProfile(name="test", port_limits={"command": 2})
    scheduler = Scheduler(profile=profile)

    token1 = scheduler.acquire(band="GREEN", port="command", cost=1)
    token2 = scheduler.acquire(band="GREEN", port="command", cost=1)

    with pytest.raises(SchedulerCapacityError) as exc_info:
        scheduler.acquire(band="GREEN", port="command", cost=1)

    assert exc_info.value.port == "command"
    assert exc_info.value.cost == 1
    assert exc_info.value.limit == 0  # No capacity remaining

# tests/k0/qos/test_context.py
def test_context_tighten():
    qos = QoSContext(scheduler=mock_scheduler, fanout_budget=50, top_k_budget=100)

    qos.tighten(fanout=10, top_k=20)
    assert qos.fanout_budget == 10
    assert qos.top_k_budget == 20

    # Cannot increase
    qos.tighten(fanout=30)
    assert qos.fanout_budget == 10

def test_context_consume_budget():
    qos = QoSContext(scheduler=mock_scheduler, fanout_budget=5, top_k_budget=10)

    qos.consume_fanout(3)
    assert qos.fanout_budget == 2

    with pytest.raises(QoSBudgetError):
        qos.consume_fanout(5)  # Exceeds remaining budget

# tests/k0/qos/test_policy.py
def test_apply_qos_obligations():
    obligations = [
        Obligation(name="kernel.qos.tighten", details={"fanout": 5, "top_k": 10}),
    ]

    qos = QoSContext(scheduler=mock_scheduler, fanout_budget=50, top_k_budget=100)
    schedule = apply_qos_obligations(qos, obligations)

    assert qos.fanout_budget == 5
    assert qos.top_k_budget == 10
    assert schedule.fanout == 5
    assert schedule.top_k == 10

def test_coerce_positive_int():
    assert coerce_positive_int(42) == 42
    assert coerce_positive_int("100") == 100
    assert coerce_positive_int(3.14) == 3
    assert coerce_positive_int({"requested": 10}) == 10
    assert coerce_positive_int([20, 30]) == 20
    assert coerce_positive_int(-5) is None
    assert coerce_positive_int("") is None
```

### Integration Tests

```python
# tests/integration/test_qos_enforcement.py
def test_command_respects_scheduler_capacity(kernel_client):
    # Submit commands until capacity exhausted
    tokens = []
    for i in range(16):  # Assuming command limit = 16
        response = kernel_client.post("/k0/command.submit", json=envelope)
        assert response.status_code == 202

    # Next request should be rejected
    response = kernel_client.post("/k0/command.submit", json=envelope)
    assert response.status_code == 429
    assert "capacity exceeded" in response.json()["error"]

def test_query_respects_top_k_budget(kernel_client):
    response = kernel_client.post("/k0/query.recall", json={
        "selectors": [
            {"type": "wal", "limit": 100},  # Exceeds budget
        ],
        "space_id": "space_001",
        "tenant_id": "tenant_001",
    })
    assert response.status_code == 200
    result = response.json()
    assert result["consumed_top_k"] <= 100  # Budget enforced
```

---

## Performance & Observability

### Metrics

- `qos_token_acquisitions_total{band, port}` (counter): Successful token acquisitions
- `qos_rejections_capacity_total{band, port}` (counter): Capacity rejections
- `qos_rejections_total{band, port, reason}` (counter): All rejections by reason
- `qos_active_tokens{port}` (gauge): Currently active tokens per port
- `qos_port_utilization_percent{port}` (gauge): Port utilization (0-100%)
- `qos_port_limit_tokens{port}` (gauge): Configured token limit per port

### Traces

- Span: `qos.acquire` (band, port, cost, outcome)
- Span: `qos.tighten` (fanout_before, fanout_after, top_k_before, top_k_after)
- Span: `qos.consume_budget` (budget_type, amount, remaining)

### Logging

```json
{
  "event": "QoS token acquired",
  "band": "GREEN",
  "port": "command",
  "cost": 1,
  "active": 12,
  "limit": 16,
  "utilization_pct": 75.0
}
```

---

## Related Modules

- **`k0.ports.command`**: Token acquisition for command submission
- **`k0.ports.query`**: Token acquisition + budget consumption
- **`k0.ports.sse`**: Token acquisition for SSE subscriptions
- **`k0.query.service`**: Top-k budget consumption during query execution
- **`k0.policy.pep_syscall`**: QoS tightening obligations
- **`k0.obs.metrics`**: Prometheus metrics exporter
- **`k0.chaos.toggles`**: Scheduler starvation injection

---

## Related ADRs

- **ADR-0097**: QoS Budget Architecture
- **ADR-0098**: Scheduler Profiles and Port Isolation
- **ADR-0103**: Policy-Driven Budget Tightening

---

## Key Design Decisions

1. **Work-conserving**: Tokens released immediately on operation completion (no fixed time slots)
2. **Port isolation**: Separate token buckets per port (command/query/sse)
3. **One-way tightening**: Budgets can only decrease, never increase (safety guarantee)
4. **Thread-safe**: Internal lock ensures atomic capacity checks and updates
5. **Context manager**: SchedulerToken supports `with` statement for auto-release
6. **Chaos integration**: Optional scheduler starvation for resilience testing
7. **Prometheus metrics**: Real-time utilization tracking for SRE dashboards
8. **Policy-driven**: PEP obligations dynamically tighten budgets per request
