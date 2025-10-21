# K0 Performance & Load Testing Suite

Orchestration framework for performance and load testing the k0 kernel.

## Overview

The performance suite provides:

- **Scenario Definition**: YAML-based test scenarios with JSON schema validation
- **Workload Generation**: Multi-phase load patterns (burst, sustained, ramp, spike, stress, soak)
- **Metrics Collection**: Prometheus Pushgateway integration with consistent labels
- **Artifact Capture**: Timeline JSON, OTLP traces, and metrics snapshots
- **Assertion Framework**: Phase-level and global success criteria

## Quick Start

### Running a Scenario

```bash
# Validate scenario (dry-run)
python -m k0.perf.runner --scenario k0/perf/scenarios/command_burst.yaml --dry-run

# Execute scenario
python -m k0.perf.runner --scenario k0/perf/scenarios/command_burst.yaml

# Override Pushgateway endpoint
python -m k0.perf.runner \
    --scenario k0/perf/scenarios/sse_fanout.yaml \
    --pushgateway http://pushgateway.example.com:9091
```

### Writing a Custom Scenario

Create a YAML file following `schema/scenario.schema.json`:

```yaml
name: "My Custom Test"
description: "Test description"
type: burst
duration: 300

environment:
  kernel_endpoint: "http://localhost:8000"
  prometheus_pushgateway: "http://localhost:9091"

phases:
  - name: "Load Phase"
    duration: 300
    workload:
      type: command
      rate: 100
      concurrency: 10
      payload_size: 1024
    assertions:
      max_p99_latency_ms: 500
      min_success_rate: 0.99

global_assertions:
  max_p99_latency_ms: 500
  min_success_rate: 0.98

artifacts:
  timeline: true
  telemetry_traces: true
  prometheus_snapshots: true
```

## Scenario Types

| Type | Description | Use Case |
|------|-------------|----------|
| `burst` | Sudden spike in load | Test resilience to traffic surges |
| `sustained` | Constant load over time | Baseline performance validation |
| `ramp` | Gradual load increase | Capacity planning |
| `spike` | Sharp increase then decrease | Flash crowd simulation |
| `stress` | Overload beyond capacity | Breaking point identification |
| `soak` | Extended duration test | Memory leak detection |

## Workload Types

### Command Workload
Tests write path: WAL, idempotency, receipts, outbox

```yaml
workload:
  type: command
  rate: 500            # req/sec
  concurrency: 50      # concurrent clients
  payload_size: 2048   # bytes
```

### Query Workload
Tests read path: recall queries, filtering, pagination

```yaml
workload:
  type: query
  rate: 1000           # req/sec
  concurrency: 100
  payload_size: 512
```

### SSE Workload
Tests streaming: fan-out delivery, backpressure, offsets

```yaml
workload:
  type: sse
  rate: 500            # events/sec published
  concurrency: 50      # concurrent subscribers
  payload_size: 1024
```

### Mixed Workload
Tests all ports simultaneously

```yaml
workload:
  type: mixed
  rate: 1000           # total req/sec across ports
  concurrency: 100
  payload_size: 1024
```

## Assertions

### Phase-Level Assertions
Evaluated per-phase, fail individual phases:

```yaml
assertions:
  max_p99_latency_ms: 500      # P99 latency threshold
  min_success_rate: 0.99       # Minimum success rate (0.0-1.0)
  max_error_rate: 0.01         # Maximum error rate (0.0-1.0)
```

### Global Assertions
Evaluated across entire scenario:

```yaml
global_assertions:
  max_p99_latency_ms: 500
  min_success_rate: 0.98
  max_memory_mb: 512
  max_cpu_percent: 80.0
```

## Metrics & Observability

### Prometheus Pushgateway

Scenarios push metrics with consistent labels:

```
k0_perf_requests_total{scenario="command_burst",phase="burst",outcome="success"}
k0_perf_latency_seconds{scenario="command_burst",phase="burst",quantile="0.99"}
k0_perf_errors_total{scenario="command_burst",phase="burst",error_type="timeout"}
```

Labels:
- `scenario`: Scenario name
- `phase`: Phase name
- `git_sha`: Git commit SHA (when available)
- `environment`: dev/staging/prod

### Grafana Dashboards

Performance dashboards available at:
- **Scenario Overview**: `http://grafana:3000/d/k0-perf-overview`
- **Phase Details**: `http://grafana:3000/d/k0-perf-phases`
- **Resource Usage**: `http://grafana:3000/d/k0-perf-resources`

See Milestone 8 documentation for dashboard setup.

### Artifacts

Captured per scenario:

```
perf-artifacts/
  command_burst_20251005_143022/
    timeline.json           # Event timeline
    traces.jsonl            # OTLP trace exports
    metrics_snapshot.txt    # Prometheus scrape
    scenario.yaml           # Scenario definition copy
    result.json             # Execution summary
```

## CI/CD Integration

### Nightly Performance Workflow

`.github/workflows/perf-nightly.yml`:

```yaml
name: Nightly Performance Tests
on:
  schedule:
    - cron: '0 2 * * *'  # 2 AM daily
  workflow_dispatch:

jobs:
  performance:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - name: Run Command Burst
        run: |
          python -m k0.perf.runner \
            --scenario k0/perf/scenarios/command_burst.yaml \
            --pushgateway http://pushgateway:9091
      - name: Upload Artifacts
        uses: actions/upload-artifact@v4
        with:
          name: perf-artifacts
          path: perf-artifacts/
```

### Performance Gates

CI can gate PRs on performance regressions:

```bash
# Run baseline comparison
python -m k0.perf.runner \
    --scenario scenarios/baseline.yaml \
    --baseline-file baseline.json \
    --fail-on-regression
```

## Scenario Library

| Scenario | Type | Duration | Description |
|----------|------|----------|-------------|
| `command_burst.yaml` | burst | 5m | Command submission spike |
| `sse_fanout.yaml` | sustained | 10m | Multi-subscriber SSE delivery |
| `scheduler_starvation.yaml` | stress | 3m | QoS scheduler saturation |
| `replay_surge.yaml` | spike | 8m | Replay catchup stress |

See `scenarios/` directory for full catalog.

## Development

### Running Tests

Validate performance suite itself:

```bash
# Run all performance framework tests
python -m ward test --path tests/performance/

# Run specific test
python -m ward test --path tests/performance/test_scenario_validation.py
```

### Adding a New Scenario

1. Create YAML in `scenarios/`
2. Validate against schema:
   ```bash
   python -m k0.perf.runner --scenario scenarios/my_test.yaml --dry-run
   ```
3. Add Ward test in `tests/performance/`
4. Update this README
5. File MCP memory with scenario purpose and baseline results

### Schema Updates

Edit `schema/scenario.schema.json`, then:

1. Update example scenarios
2. Regenerate docs: `k0/automation/generate_api_docs.py`
3. Update tests
4. File MCP memory documenting schema changes

## Troubleshooting

### Scenario Validation Fails

```
✗ Scenario validation failed: Phase durations don't match scenario duration
```

**Solution**: Ensure phase durations sum to `duration`:
```yaml
duration: 300
phases:
  - name: "Phase 1"
    duration: 150
  - name: "Phase 2"
    duration: 150  # Total: 300 ✓
```

### Pushgateway Push Fails

```
✗ Failed to push metrics to Pushgateway: Connection refused
```

**Solution**: Verify Pushgateway is running:
```bash
docker run -p 9091:9091 prom/pushgateway
```

Or override endpoint:
```bash
python -m k0.perf.runner \
    --scenario scenarios/test.yaml \
    --pushgateway http://localhost:9091
```

### Missing Artifacts

```
✗ Warning: Artifacts directory not found
```

**Solution**: Specify artifacts directory:
```bash
python -m k0.perf.runner \
    --scenario scenarios/test.yaml \
    --artifacts-dir /path/to/artifacts
```

### High Memory Usage

If scenarios consume excessive memory:

1. Reduce `concurrency` in workload config
2. Lower `rate` (req/sec)
3. Decrease `payload_size`
4. Add more phases with cooldown periods

## References

- [Milestone 9.1.3 Plan](../../docs/system_plan/README.md#milestone-913)
- [Testing Requirements](../../.github/instructions/testing-requirements.instructions.md)
- [Contracts Playbook](../../docs/development/contracts-playbook.md)
- [Deployment Quick Reference](../../docs/development/deployment-quick-reference.md)
- [Prometheus Best Practices](https://prometheus.io/docs/practices/naming/)

## Support

For issues or questions:
- Check [Troubleshooting](#troubleshooting) section
- Review [test_scenario_validation.py](../../tests/performance/test_scenario_validation.py) for examples
- File MCP memory with reproduction steps
- See [docs/development/runbooks/](../../docs/development/runbooks/) for operational guidance
