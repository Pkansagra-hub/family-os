# Chaos Testing Runbook

**Purpose**: Automated, reproducible chaos experiments for validating K0 kernel fault tolerance and recovery mechanisms.

**Related ADRs**: Pending (K0 automation architecture)

**Related Issues**: Epic E.2 (Chaos Automation), Issue E.2.1

---

## Overview

The chaos scheduler (`k0/automation/chaos_scheduler.py`) injects controlled faults into K0 to validate:

1. **Fault injection** — WAL fsync failures, scheduler degradation, network latency, telemetry outages
2. **Recovery validation** — Correctness invariants (replay parity, receipt consistency, SSE reconnection)
3. **MTTR measurement** — Mean time to recovery after faults
4. **Reporting** — JSON and Markdown reports for CI artifacts and analysis

### Chaos Profiles

Three predefined profiles for different fault intensity levels:

| Profile | fsync Failures | Scheduler Cap | Network Latency | Telemetry Drop |
|---------|---|---|---|---|
| **mild** | 5% | 50% | 0ms | 0% |
| **moderate** | 10% | 30% | 50ms | 10% |
| **aggressive** | 20% | 20% | 100ms | 20% |

---

## Quick Start

### Run a chaos experiment

```bash
# Run mild chaos experiment for 60 seconds
python -m k0.automation.chaos_scheduler \
    --profile=mild \
    --duration=60 \
    --output=chaos-report.json \
    --markdown-report=chaos-report.md
```

### Output

- **JSON report** (`chaos-report.json`): Machine-readable fault timeline and metrics
- **Markdown report** (`chaos-report.md`): Human-readable summary for review

### Exit codes

- `0` — Experiment completed, no invariant violations
- `1` — Invariant violations detected
- `2` — Configuration or runtime error

---

## Command Reference

### Required Arguments

```
--profile {mild,moderate,aggressive}
  Chaos profile to run (default: mild)
```

### Optional Arguments

```
--duration SECONDS
  Duration of chaos period in seconds (default: 60)

--output FILE
  Write JSON report to file (default: stdout)

--markdown-report FILE
  Generate human-readable Markdown report to file

--random-seed SEED
  Random seed for reproducible chaos (optional)
  - If provided, experiment is deterministic
  - Useful for regression testing

-v, --verbose
  Enable verbose logging for debugging
```

---

## Usage Examples

### 1. Smoke test (non-blocking CI)

```bash
# Fast smoke test with mild profile
python -m k0.automation.chaos_scheduler \
    --profile=mild \
    --duration=10 \
    --output=smoke-test.json
```

**Use case**: Quick validation in PR checks (takes ~10s)

### 2. Full validation test

```bash
# Comprehensive test with moderate profile
python -m k0.automation.chaos_scheduler \
    --profile=moderate \
    --duration=300 \
    --output=full-test.json \
    --markdown-report=full-test.md \
    --verbose
```

**Use case**: Full regression test suite (takes ~5 min)

### 3. Aggressive stress test

```bash
# High-intensity stress test for release validation
python -m k0.automation.chaos_scheduler \
    --profile=aggressive \
    --duration=600 \
    --output=stress-test.json \
    --markdown-report=stress-test.md \
    --random-seed=42  # Reproducible
```

**Use case**: Release testing, performance baseline validation (takes ~10 min)

### 4. Reproducible experiment

```bash
# Run experiment with fixed seed for debugging
python -m k0.automation.chaos_scheduler \
    --profile=moderate \
    --duration=60 \
    --random-seed=42 \
    --output=debug-run.json
```

**Use case**: Reproduce specific failures for debugging

---

## Reports

### JSON Report Structure

```json
{
  "experiment_id": "e032b29d",
  "profile_name": "mild",
  "start_time": "2025-01-01T00:00:00+00:00",
  "end_time": "2025-01-01T00:02:00+00:00",
  "duration_seconds": 120.0,
  "fault_events": [
    {
      "timestamp": "2025-01-01T00:00:30+00:00",
      "fault_type": "fsync_failure",
      "description": "WAL fsync failure injected (rate: 5%)",
      "metadata": {"attempt": 0, "rate": 0.05}
    }
  ],
  "recovery_checkpoints": [
    {
      "timestamp": "2025-01-01T00:02:05+00:00",
      "invariant": "replay_parity",
      "status": "passed",
      "details": "All commands replayed successfully with matching results"
    }
  ],
  "invariant_violations": [],
  "metrics": {}
}
```

### Markdown Report Example

```markdown
# Chaos Experiment Report

**Experiment ID**: e032b29d
**Profile**: mild
**Duration**: 120.0s
**Status**: PASSED

## Fault Injection Timeline

1. **fsync_failure** — WAL fsync failure injected (rate: 5%)
2. **scheduler_stress** — Scheduler degraded to 50% capacity
3. **network_latency** — Network latency: 42ms

## Recovery Validation (3 checks)

- [PASS] **replay_parity**: All commands replayed successfully with matching results
- [PASS] **receipt_consistency**: All receipts consistent across chaos period and recovery
- [PASS] **sse_reconnection**: SSE recovery successful: 5 connections, 50 events

## Result

All invariants validated successfully

- Faults injected: 3
- Recovery checks passed: 3
- MTTR: 120.0s
```

---

## Recovery Validation

The chaos scheduler validates four correctness invariants during recovery:

### 1. Replay Parity

**Validates**: Commands executed before chaos are re-executed with identical results.

### Checks

- Same number of commands in original and replayed sequences
- Command IDs match in order
- Result hashes match (deterministic outputs)

**Failure message example:**

```text
Result hash mismatch for command cmd_12345
```

### 2. Receipt Consistency

**Validates**: Receipts issued during chaos are not corrupted or lost during recovery.

**Checks:**

- All receipts from chaos period are present after recovery
- Receipt hashes unchanged (no data corruption)

**Failure message example:**

```text
Receipt r_abc123 lost during chaos (not found after recovery)
```

### 3. SSE Reconnection

**Validates**: SSE clients reconnect successfully and receive events after chaos period.

**Checks:**

- Active SSE connections restored
- Events delivered during chaos are not lost
- Cursor recovery works (subscribers resume from correct position)

**Failure message example:**

```text
SSE events missing: expected >=10, got 5
```

### 4. Scheduler Recovery

**Validates**: Scheduler queue depth returns to normal after chaos period.

**Checks:**

- Queue depth < maximum during normal operation
- Acceptable queue utilization (no starvation)

**Failure message example:**

```text
Scheduler queue not recovered: 1500 > 1000
```

---

## Integration with CI

### GitHub Actions Workflow

```yaml
# .github/workflows/chaos-ci.yml
name: Chaos Testing

on:
  pull_request:
    paths:
      - 'k0/**'
  schedule:
    - cron: '0 2 * * *'  # Daily at 2 AM UTC

jobs:
  chaos-smoke-test:
    name: Chaos Smoke Test (Mild)
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3

      - name: Set up Python
        uses: actions/setup-python@v4
        with:
          python-version: '3.12'

      - name: Install dependencies
        run: pip install -r k0/automation/requirements.txt

      - name: Run chaos smoke test
        run: |
          python -m k0.automation.chaos_scheduler \
            --profile=mild \
            --duration=60 \
            --output=chaos-report.json \
            --markdown-report=chaos-report.md

      - name: Upload reports
        if: always()
        uses: actions/upload-artifact@v3
        with:
          name: chaos-reports
          path: |
            chaos-report.json
            chaos-report.md

  chaos-full-test:
    name: Chaos Full Test (Moderate)
    runs-on: ubuntu-latest
    if: github.ref == 'refs/heads/main'
    timeout-minutes: 10
    steps:
      - uses: actions/checkout@v3

      - name: Set up Python
        uses: actions/setup-python@v4
        with:
          python-version: '3.12'

      - name: Install dependencies
        run: pip install -r k0/automation/requirements.txt

      - name: Run chaos full test
        run: |
          python -m k0.automation.chaos_scheduler \
            --profile=moderate \
            --duration=300 \
            --output=chaos-full-report.json \
            --markdown-report=chaos-full-report.md

      - name: Upload reports
        if: always()
        uses: actions/upload-artifact@v3
        with:
          name: chaos-full-reports
          path: |
            chaos-full-report.json
            chaos-full-report.md
```

---

## Troubleshooting

### Experiment hangs or takes too long

**Symptom**: Chaos experiment stuck, CPU/disk usage unchanged

**Causes**:

1. K0 kernel deadlocked due to fault injection
2. Network latency injection causing timeouts
3. Telemetry client blocking on OTLP endpoint failure

**Solution**:

1. Add timeout: `timeout 180s python -m k0.automation.chaos_scheduler ...`
2. Check kernel logs: `docker logs k0-kernel | tail -100`
3. Reduce duration: `--duration=30` for initial debugging
4. Try mild profile first: `--profile=mild`

### No faults injected

**Symptom**: Report shows `0 faults injected`

**Causes**:

1. Random seed causing unlucky sequence (low probability)
2. Fault injection hooks not integrated

**Solution**:

1. Run again with different seed: `--random-seed=$RANDOM`
2. Increase duration: `--duration=300` for more injection opportunities
3. Verify K0 chaos hooks are enabled in config

### Invariant violations detected

**Symptom**: Recovery validation fails

**Solution**:

1. **Analyze JSON report**: Check `invariant_violations` array for specific failure
2. **Review fault timeline**: Look at `fault_events` for context
3. **Inspect kernel logs**: `docker logs k0-kernel | grep -i chaos`
4. **Reproduce deterministically**: Use `--random-seed=<seed>` from failed run
5. **File issue**: Include JSON report and kernel logs

### Windows encoding issues

**Symptom**: Error like `'charmap' codec can't encode character`

**Solution**:

```bash
# Use UTF-8 encoding on Windows PowerShell
$env:PYTHONIOENCODING = 'utf-8'
python -m k0.automation.chaos_scheduler ...
```

---

## Best Practices

### 1. Start small, escalate gradually

```bash
# Week 1: Smoke tests (mild, 10s)
--profile=mild --duration=10

# Week 2: Regular tests (mild, 60s)
--profile=mild --duration=60

# Week 3: Full validation (moderate, 5min)
--profile=moderate --duration=300

# Week 4: Stress tests (aggressive, 10min)
--profile=aggressive --duration=600
```

### 2. Use reproducible seeds for regression testing

```bash
# Save seed for reproducible failure investigation
SEED=12345
python -m k0.automation.chaos_scheduler \
  --profile=moderate \
  --duration=60 \
  --random-seed=$SEED \
  --output=run-$SEED.json

# Run same experiment again for debugging
python -m k0.automation.chaos_scheduler \
  --profile=moderate \
  --duration=60 \
  --random-seed=$SEED
```

### 3. Monitor telemetry during experiments

```bash
# Terminal 1: Run chaos experiment
python -m k0.automation.chaos_scheduler \
  --profile=moderate \
  --duration=300 \
  --verbose

# Terminal 2: Monitor Prometheus metrics
watch 'curl -s http://localhost:9090/api/v1/query?query=k0_command_latency_seconds | jq'

# Terminal 3: Tail kernel logs
docker logs -f k0-kernel | grep -E 'chaos|error|recovery'
```

### 4. Analyze failures systematically

1. **Collect data**: Save JSON reports and kernel logs
2. **Identify pattern**: Check if failures are reproducible with same seed
3. **Isolate fault type**: Test each fault in isolation (`--profile=mild` modified)
4. **Fix and validate**: Rerun with same seed to verify fix

---

## Advanced Topics

### Custom fault profiles

Create custom profiles by modifying `PROFILES` dict in `chaos_scheduler.py`:

```python
PROFILES = {
    ...
    "custom": ChaosProfile(
        name="custom",
        fsync_fail_rate=0.15,
        scheduler_multiplier=0.4,
        network_latency_ms=75,
        telemetry_outage_rate=0.05,
    ),
}
```

Then run:

```bash
python -m k0.automation.chaos_scheduler --profile=custom --duration=60
```

### Integration with local tests

Use `ChaosExperiment` class in pytest tests:

```python
from k0.automation.chaos_scheduler import ChaosExperiment, PROFILES

def test_kernel_recovery_from_chaos():
    profile = PROFILES["mild"]
    experiment = ChaosExperiment(profile, duration_seconds=30, random_seed=42)
    report = experiment.run()

    # Collect recovery metrics
    passed, violations = experiment.validate_recovery(
        original_commands=[...],
        replayed_commands=[...],
    )

    assert passed, f"Recovery failed: {violations}"
    assert len(report.fault_events) > 0
```

---

## References

- **Module**: `k0/automation/chaos_scheduler.py` (850 lines)
- **Tests**: `tests/automation/test_chaos_scheduler.py` (620 lines, 40 test cases)
- **Chaos Hooks**: `k0/chaos/` (toggles, network transport, telemetry)
- **K0 Config**: `k0/kernel/config.py` (ChaosSettings dataclass)
- **Related ADR**: Pending (K0 automation architecture)

---

**Last updated**: 2025-01-11
**Status**: Production-ready for smoke tests (non-blocking CI)
**Next steps**: Integrate full validation tests into release pipeline
