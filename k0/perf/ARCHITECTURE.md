# K0 Performance Testing Architecture

**Purpose**: Technical reference for performance testing components, showing what files do and how they connect to enable repeatable load testing and baseline comparison.

**Related**: See `README.md` for user-facing documentation and quick start guide.

---

## Repository Files & Functions

### Core Components

#### 1. `runner.py`

**Purpose**: Main orchestration engine for scenario execution with CLI interface.

##### Classes & Functions

```python
@dataclass
class ScenarioConfig:
    name: str
    description: str | None
    type: str  # burst, sustained, ramp, spike, stress, soak
    duration: int  # seconds
    tags: list[str]
    environment: dict[str, Any]
    phases: list[dict[str, Any]]
    global_assertions: dict[str, Any] | None
    artifacts: dict[str, bool]

    @classmethod
    def from_yaml(cls, yaml_path: Path) -> ScenarioConfig
```

- **Purpose**: Parse and validate YAML scenario definitions
- **Validation**: Checks scenario structure against expected schema
- **Fields**:
  - `type`: Scenario pattern (burst/sustained/ramp/spike/stress/soak)
  - `phases`: Ordered list of workload phases with duration, rate, concurrency
  - `global_assertions`: Success criteria (P99 latency, success rate, resource limits)
  - `artifacts`: Toggle timeline, traces, metrics snapshots

```python
@dataclass
class ScenarioResult:
    scenario_name: str
    start_time: datetime
    end_time: datetime
    success: bool
    phases_executed: int
    total_requests: int
    success_rate: float
    p99_latency_ms: float
    errors: list[str]
    artifacts_dir: Path | None
```

- **Purpose**: Execution results summary
- **Usage**: Returned by `ScenarioRunner.execute()` for post-mortem analysis

```python
class PushgatewayClient:
    def __init__(self, endpoint: str, job_name: str = "k0-perf")
    def _build_push_url(self, labels: dict[str, str] | None = None) -> str
    def _format_metrics(self, metrics: dict[str, float]) -> str
    def push_metrics(self, metrics: dict[str, float], labels: dict[str, str] | None = None) -> None
    def delete_metrics(self, labels: dict[str, str] | None = None) -> None
```

- **Purpose**: Prometheus Pushgateway integration for metrics push
- **URL encoding**: Handles label encoding for Pushgateway API (`/metrics/job/{job}/label/{value}`)
- **Exposition format**: Converts metrics dict to Prometheus text format
- **Labels**: Supports scenario name, git_sha, environment tags for filtering
- **Error handling**: Raises `httpx.HTTPError` with descriptive context on failure

**Example metrics push**:

```python
client = PushgatewayClient("http://localhost:9091")
client.push_metrics(
    {
        "k0_perf_requests_total": 5000.0,
        "k0_perf_latency_p99_seconds": 0.45,
    },
    labels={"scenario": "command_burst", "phase": "burst", "git_sha": "abc123"},
)
```

```python
class ScenarioRunner:
    def __init__(
        self,
        config: ScenarioConfig,
        pushgateway_endpoint: str | None = None,
        artifacts_dir: Path | None = None,
        dry_run: bool = False,
    )

    def validate(self) -> list[str]
    def execute(self) -> ScenarioResult
```

- **Purpose**: Orchestrates scenario execution lifecycle
- **Validation checks**:
  - At least one phase defined
  - Phase durations sum to scenario duration
  - kernel_endpoint specified in environment
- **Execution flow** (TODO - implementation pending):
  1. Load scenario config
  2. Validate phases and assertions
  3. Execute phases sequentially with workload generation
  4. Collect metrics and push to Pushgateway
  5. Evaluate assertions (phase-level and global)
  6. Capture artifacts (timeline, traces, snapshots)
  7. Return ScenarioResult

**CLI Entry Point**:

```python
def main() -> int
```

- **Arguments**:
  - `--scenario`: Path to YAML scenario file (required)
  - `--pushgateway`: Prometheus Pushgateway endpoint (overrides config)
  - `--artifacts-dir`: Output directory for artifacts (default: `perf-artifacts/`)
  - `--dry-run`: Validate scenario without execution
- **Exit codes**:
  - `0`: Success (all assertions passed)
  - `1`: Failure (assertions failed or validation error)
  - `2`: Runtime error (config, network, etc.)
  - `130`: Interrupted by user (Ctrl+C)

**Usage**:

```bash
# Dry-run validation
python -m k0.perf.runner --scenario scenarios/command_burst.yaml --dry-run

# Execute scenario
python -m k0.perf.runner --scenario scenarios/sse_fanout.yaml

# Override Pushgateway
python -m k0.perf.runner \
    --scenario scenarios/replay_surge.yaml \
    --pushgateway http://pushgateway.example.com:9091
```

---

#### 2. `__init__.py`

**Purpose**: Module exports for programmatic usage.

```python
__all__ = [
    "ScenarioRunner",
    "ScenarioConfig",
    "PushgatewayClient",
]
```

- **Note**: Components exported but not yet imported (pending implementation)
- **Usage**: Enables `from k0.perf import ScenarioRunner`

---

### Configuration & Scenarios

#### 3. `schema/scenario.schema.json`

**Purpose**: JSON Schema for scenario YAML validation.

**Schema Structure**:

- **Required fields**: `name`, `type`, `duration`, `phases`
- **Scenario types**: `burst`, `sustained`, `ramp`, `spike`, `stress`, `soak`
- **Environment**: `kernel_endpoint` (required), `telemetry_endpoint`, `prometheus_pushgateway`
- **Phases**: Array of workload phases with:
  - `name`, `duration` (seconds)
  - `workload`: `type` (command/query/sse/mixed), `rate`, `concurrency`, `payload_size`
  - `assertions`: Phase-level success criteria (optional)
- **Global assertions**: Scenario-wide success criteria (optional)
- **Artifacts**: Toggle flags for `timeline`, `telemetry_traces`, `prometheus_snapshots`

**Validation constraints**:

- Duration: 1 to 86400 seconds (24 hours max)
- Rate: ≥1 req/sec
- Concurrency: ≥1 connections
- Success rate: 0.0 to 1.0
- CPU percent: 0.0 to 100.0

**Workload types**:

| Type | Description | Test Target |
|------|-------------|-------------|
| `command` | Command submission | Write path (WAL, idempotency, receipts, outbox) |
| `query` | Recall queries | Read path (filtering, pagination, indices) |
| `sse` | SSE streaming | Fan-out delivery, backpressure, offsets |
| `mixed` | All ports | Full system integration |

---

#### 4. `scenarios/*.yaml`

**Purpose**: Scenario definitions for common load patterns.

##### `scenarios/command_burst.yaml`

**Pattern**: Burst (sudden spike)
**Duration**: 5 minutes
**Phases**:

1. **Warmup** (30s): 10 req/sec, 2 concurrent, 1KB payloads
2. **Burst** (180s): 500 req/sec, 50 concurrent, 2KB payloads
   - Assertions: P99 ≤500ms, success rate ≥99%
3. **Recovery** (60s): 10 req/sec, 2 concurrent, 1KB payloads
   - Assertions: P99 ≤100ms, success rate ≥99.9%
4. **Cooldown** (30s): 1 req/sec, 1 concurrent, 512B payloads

**Global assertions**:

- P99 latency ≤500ms
- Success rate ≥98%
- Memory ≤512MB
- CPU ≤80%

**Purpose**: Test kernel resilience to traffic surges (flash crowds, retry storms)

##### `scenarios/sse_fanout.yaml`

**Pattern**: Sustained
**Focus**: SSE multi-subscriber fan-out and backpressure
**Purpose**: Validate streaming performance under sustained load

##### `scenarios/scheduler_starvation.yaml`

**Pattern**: Stress
**Focus**: QoS scheduler saturation
**Purpose**: Identify breaking points for priority queue management

---

### Baseline & Profiling

#### 5. `baselines/main.json`

**Purpose**: Performance baseline for `main` branch.

**Structure**:

```json
{
  "git_sha": "main",
  "timestamp": "2025-01-11T01:35:00+00:00",
  "branch": "main",
  "metrics": {
    "small": {
      "p50_latency_ms": 9.2,
      "p95_latency_ms": 10.8,
      "p99_latency_ms": 11.2,
      "throughput_rps": 1024.5,
      "error_rate": 0.0
    },
    "balanced": { /* ... */ },
    "large": { /* ... */ }
  },
  "checksum": "a7f3c2e8b1d9f4a6"
}
```

**Usage**:

- Regression detection: Compare PR metrics against baseline
- Trend analysis: Track performance over time
- Alert thresholds: CI gates for P99/throughput degradation

**Profile naming**:

- `small`: Lightweight workload (10 commands, 5ms processing, ~100 concurrent)
- `balanced`: Medium workload (production-like)
- `large`: Heavy workload (stress testing)

#### 6. `baselines/feature-test.json`

**Purpose**: Baseline for feature branches.

**Usage**: Branch-specific baseline for feature development without polluting main branch metrics.

---

#### 7. `profiles/*.py`

**Purpose**: Workload profile generators for baseline testing.

##### `profiles/small.py`

```python
def run_small_profile() -> dict[str, Any]:
    """Run small profile workload.

    Returns:
        Dictionary with metrics: p50_latency_ms, p95_latency_ms, p99_latency_ms,
        throughput_rps, error_rate
    """
```

- **Workload**: 10 command packets, 5ms processing, ~100 concurrent ops
- **Purpose**: Baseline latency and throughput measurement
- **Output**: JSON metrics for baseline capture

**CLI usage**:

```bash
python k0/perf/profiles/small.py
# {"p50_latency_ms": 9.2, "p95_latency_ms": 10.8, ...}
```

##### `profiles/balanced.py`

**Workload**: Medium workload, production-like traffic patterns
**Purpose**: Validate typical production performance

##### `profiles/large.py`

**Workload**: Heavy stress workload
**Purpose**: Identify capacity limits and breaking points

---

## Connections & Integration Points

### Upstream Dependencies

1. **K0 Kernel API** (`k0.kernel.app`):
   - `POST /api/v1/submit`: Command submission endpoint (tested by `command` workload)
   - `GET /api/v1/recall`: Query endpoint (tested by `query` workload)
   - `GET /api/v1/subscribe`: SSE streaming (tested by `sse` workload)

2. **Prometheus Pushgateway**:
   - Endpoint: Configurable via `environment.prometheus_pushgateway` or `--pushgateway` CLI arg
   - Metrics: Pushed after each phase and scenario completion
   - Labels: `scenario`, `phase`, `git_sha`, `environment`

3. **OpenTelemetry Collector** (optional):
   - Endpoint: `environment.telemetry_endpoint`
   - Traces: OTLP exports captured if `artifacts.telemetry_traces: true`

### Downstream Consumers

1. **CI/CD Pipelines** (`.github/workflows/perf-nightly.yml`):
   - Scheduled nightly runs of baseline scenarios
   - PR gates: Block merge on >10% P99 regression
   - Artifact upload: Timeline JSON, traces, metrics snapshots

2. **Grafana Dashboards**:
   - `k0-perf-overview`: Scenario execution summary
   - `k0-perf-phases`: Per-phase metrics breakdown
   - `k0-perf-resources`: Memory/CPU usage over time
   - Queries: Filter by `scenario`, `git_sha`, `environment` labels

3. **Baseline Comparison**:
   - `python -m k0.perf.runner --scenario scenarios/test.yaml --baseline-file baselines/main.json --fail-on-regression`
   - Compares current run against baseline P50/P95/P99/throughput
   - Exits non-zero if regression detected

### Data Flow

```
┌─────────────────────────────────────────────────────────────────┐
│ 1. Scenario Loading                                             │
│    runner.py → ScenarioConfig.from_yaml(scenarios/*.yaml)       │
│    → Validate against schema/scenario.schema.json               │
└────────────────────────┬────────────────────────────────────────┘
                         │
                         ▼
┌─────────────────────────────────────────────────────────────────┐
│ 2. Scenario Execution                                           │
│    ScenarioRunner.execute() →                                   │
│    For each phase:                                              │
│      - Generate workload (command/query/sse/mixed)              │
│      - Collect metrics (latency, throughput, errors)            │
│      - Evaluate phase assertions                                │
└────────────────────────┬────────────────────────────────────────┘
                         │
                         ▼
┌─────────────────────────────────────────────────────────────────┐
│ 3. Metrics Push                                                 │
│    PushgatewayClient.push_metrics() →                           │
│    POST /metrics/job/k0-perf/scenario/{name}/phase/{name}       │
│    → Prometheus Pushgateway                                     │
└────────────────────────┬────────────────────────────────────────┘
                         │
                         ▼
┌─────────────────────────────────────────────────────────────────┐
│ 4. Assertion Evaluation                                         │
│    Check global_assertions:                                     │
│      - max_p99_latency_ms                                       │
│      - min_success_rate                                         │
│      - max_memory_mb                                            │
│      - max_cpu_percent                                          │
└────────────────────────┬────────────────────────────────────────┘
                         │
                         ▼
┌─────────────────────────────────────────────────────────────────┐
│ 5. Artifact Generation                                          │
│    if artifacts.timeline: Write timeline.json                   │
│    if artifacts.telemetry_traces: Export traces.jsonl           │
│    if artifacts.prometheus_snapshots: Scrape metrics_snapshot   │
│    Copy scenario.yaml, write result.json                        │
└─────────────────────────────────────────────────────────────────┘
```

### Scenario Execution Lifecycle

```
START
  │
  ├─> Load YAML → ScenarioConfig.from_yaml()
  │
  ├─> Validate → ScenarioRunner.validate()
  │    └─> Check: phases non-empty, durations match, kernel_endpoint set
  │
  ├─> Phase Loop → For each phase in phases:
  │    │
  │    ├─> Workload Generation
  │    │    ├─> command: HTTP POST /api/v1/submit
  │    │    ├─> query: HTTP GET /api/v1/recall
  │    │    ├─> sse: HTTP GET /api/v1/subscribe (concurrent subscribers)
  │    │    └─> mixed: All above simultaneously
  │    │
  │    ├─> Metrics Collection
  │    │    ├─> Latency histogram (P50, P95, P99)
  │    │    ├─> Throughput (req/sec)
  │    │    ├─> Error rate (errors / total)
  │    │    └─> Resource usage (memory, CPU via psutil)
  │    │
  │    ├─> Phase Assertions
  │    │    └─> Fail phase if max_p99_latency_ms or min_success_rate violated
  │    │
  │    └─> Metrics Push → PushgatewayClient.push_metrics(labels={scenario, phase})
  │
  ├─> Global Assertions
  │    └─> Aggregate across all phases, check global_assertions
  │
  ├─> Artifact Capture
  │    ├─> timeline.json: Event timeline with timestamps
  │    ├─> traces.jsonl: OTLP trace exports
  │    ├─> metrics_snapshot.txt: Prometheus scrape
  │    ├─> scenario.yaml: Copy of input scenario
  │    └─> result.json: ScenarioResult serialized
  │
  └─> Return ScenarioResult (success: bool, metrics, errors)

END
```

---

## Testing

### Unit Tests

```python
# tests/performance/test_scenario_validation.py
def test_scenario_config_from_yaml():
    config = ScenarioConfig.from_yaml(Path("scenarios/command_burst.yaml"))
    assert config.name == "Command Burst Load Test"
    assert config.type == "burst"
    assert config.duration == 300

def test_scenario_runner_validation():
    runner = ScenarioRunner(config, dry_run=True)
    errors = runner.validate()
    assert len(errors) == 0

def test_pushgateway_client_format_metrics():
    client = PushgatewayClient("http://localhost:9091")
    formatted = client._format_metrics({"metric_name": 42.0})
    assert formatted == "metric_name 42.0\n"
```

### Integration Tests

```python
# tests/integration/test_perf_e2e.py
def test_command_burst_scenario_executes(kernel_server, pushgateway):
    runner = ScenarioRunner(
        config=ScenarioConfig.from_yaml(Path("scenarios/command_burst.yaml")),
        pushgateway_endpoint="http://localhost:9091",
    )
    result = runner.execute()
    assert result.success
    assert result.p99_latency_ms < 500
    assert result.success_rate >= 0.98
```

### Baseline Tests

```bash
# Generate baseline
python -m k0.perf.runner --scenario scenarios/command_burst.yaml
# Metrics pushed to Pushgateway, baseline updated in baselines/main.json

# Compare against baseline
python -m k0.perf.runner \
    --scenario scenarios/command_burst.yaml \
    --baseline-file baselines/main.json \
    --fail-on-regression
# Exit code 1 if P99 > baseline * 1.1
```

---

## Performance & Observability

### Metrics Pushed to Pushgateway

```
k0_perf_requests_total{scenario="command_burst",phase="burst",outcome="success"} 50000
k0_perf_latency_seconds{scenario="command_burst",phase="burst",quantile="0.99"} 0.45
k0_perf_errors_total{scenario="command_burst",phase="burst",error_type="timeout"} 50
k0_perf_throughput_rps{scenario="command_burst",phase="burst"} 500.0
k0_perf_memory_bytes{scenario="command_burst",phase="burst"} 536870912
k0_perf_cpu_percent{scenario="command_burst",phase="burst"} 75.0
```

**Label dimensions**:

- `scenario`: Scenario name (e.g., "command_burst")
- `phase`: Phase name (e.g., "burst", "recovery")
- `git_sha`: Git commit SHA (e.g., "abc123")
- `environment`: Environment tag (e.g., "dev", "staging", "prod")

### Grafana Queries

```promql
# P99 latency by scenario
histogram_quantile(0.99, rate(k0_perf_latency_seconds_bucket[5m]))

# Success rate over time
sum(rate(k0_perf_requests_total{outcome="success"}[5m]))
/
sum(rate(k0_perf_requests_total[5m]))

# Memory usage trend
k0_perf_memory_bytes{scenario="command_burst"}
```

### Artifacts Directory Structure

```
perf-artifacts/
  command_burst_20251005_143022/
    timeline.json           # Event timeline with timestamps
    traces.jsonl            # OTLP trace exports (one per line)
    metrics_snapshot.txt    # Prometheus scrape at scenario end
    scenario.yaml           # Copy of input scenario definition
    result.json             # ScenarioResult serialized
```

---

## Related Modules

- **`k0.kernel`**: FastAPI server with command/query/SSE endpoints (test targets)
- **`k0.obs`**: Observability infrastructure (metrics used for baseline comparison)
- **`k0.storage`**: WAL, outbox, receipts (tested by command workload)
- **`k0.qos`**: Scheduler (tested by scheduler_starvation scenario)

---

## Related ADRs

- **ADR-0072**: Performance Testing Strategy
- **ADR-0081**: Metrics Architecture and Prometheus Integration
- **ADR-0095**: Baseline Performance Budgets

---

## Key Design Decisions

1. **YAML scenarios**: Human-readable, version-controlled, easy to share across teams
2. **JSON Schema validation**: Catch errors early, enable IDE autocomplete
3. **Pushgateway over scrape**: Scenarios are ephemeral, push model fits better than long-lived scrape targets
4. **Phase-based execution**: Gradual ramp-up/down, isolate burst effects, test recovery
5. **Baseline comparison**: Automated regression detection in CI
6. **Artifact capture**: Reproducibility and post-mortem analysis
7. **Exit codes**: CI-friendly (0=success, 1=assertion fail, 2=runtime error)

---

## TODO (Implementation Gaps)

Current state: **Framework scaffolding complete, execution engine pending**

### Pending Work

1. **Workload generators**:
   - Command workload: HTTP POST to `/api/v1/submit` with rate limiting
   - Query workload: HTTP GET to `/api/v1/recall` with filter patterns
   - SSE workload: Concurrent subscribers with offset tracking
   - Mixed workload: Parallel execution of all workload types

2. **Metrics collection**:
   - Latency histogram: Track P50/P95/P99 per phase
   - Throughput: Requests per second calculation
   - Error tracking: Count and categorize errors (timeout, 4xx, 5xx)
   - Resource monitoring: psutil for memory/CPU sampling

3. **Assertion engine**:
   - Phase-level assertion evaluation after each phase
   - Global assertion evaluation at scenario end
   - Detailed failure messages with metrics context

4. **Artifact generation**:
   - Timeline JSON: Event log with timestamps
   - OTLP trace export: Span collection from kernel
   - Prometheus snapshot: Scrape kernel `/metrics` endpoint
   - Result JSON: Serialize ScenarioResult

5. **Baseline comparison**:
   - Load baseline from `baselines/*.json`
   - Compare current metrics against baseline
   - Calculate regression percentage
   - Fail scenario if regression > threshold (e.g., 10%)

### Priority Order

1. ✅ **DONE**: Scenario schema, config loading, validation
2. ✅ **DONE**: PushgatewayClient implementation
3. ✅ **DONE**: CLI interface and dry-run mode
4. 🚧 **IN PROGRESS**: Workload generators (command, query, SSE, mixed)
5. 🚧 **IN PROGRESS**: Metrics collection and aggregation
6. ⏳ **TODO**: Assertion evaluation engine
7. ⏳ **TODO**: Artifact capture and export
8. ⏳ **TODO**: Baseline comparison logic
9. ⏳ **TODO**: Integration with CI/CD pipelines
10. ⏳ **TODO**: Grafana dashboard templates

**Milestone**: Milestone 9.1.3 - Performance Testing Framework
