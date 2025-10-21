# K0 Chaos Engineering Framework

Controlled fault injection module for validating system resilience without simulation code.

---

## 🎯 Quick Start

### Enable Chaos in Configuration

**File**: `k0/config/kernel.yaml`

```yaml
chaos:
  enabled: true
  wal_fsync_fail_rate: 0.05       # 5% fsync failure rate
  scheduler_starvation_multiplier: 0.3  # 30% capacity
  network_latency_ms: 100          # 100ms delay
  telemetry_outage_rate: 0.1       # 10% metric drop rate
  random_seed: null                # null=random, int=deterministic
```

**Environment Variables**:

```bash
export K0_KERNEL_CHAOS__ENABLED=true
export K0_KERNEL_CHAOS__WAL_FSYNC_FAIL_RATE=0.05
export K0_KERNEL_CHAOS__SCHEDULER_STARVATION_MULTIPLIER=0.3
export K0_KERNEL_CHAOS__NETWORK_LATENCY_MS=100
export K0_KERNEL_CHAOS__TELEMETRY_OUTAGE_RATE=0.1
```

### Deploy with Chaos

**PowerShell**:
```powershell
.\k0\deployment\scripts\deploy.ps1 `
  -Stack local-single-node `
  -Action preview `
  -Chaos `
  -ChaosFsyncFailRate 0.05 `
  -ChaosSchedulerMultiplier 0.3
```

**Bash**:
```bash
./k0/deployment/scripts/deploy.sh \
  --stack local-single-node \
  --action preview \
  --chaos \
  --chaos-fsync-fail-rate 0.05 \
  --chaos-scheduler-multiplier 0.3
```

---

## 📊 Configuration Reference

| Setting | Type | Default | Range | Description |
|---------|------|---------|-------|-------------|
| `enabled` | bool | false | - | Master toggle for chaos features |
| `wal_fsync_fail_rate` | float | 0.0 | 0.0-1.0 | Probability of WAL fsync failure (OSError) |
| `scheduler_starvation_multiplier` | float | 1.0 | 0.0-1.0 | Scheduler capacity multiplier (0.3 = 30% capacity) |
| `network_latency_ms` | int | 0 | 0+ | Network delay injection in milliseconds |
| `telemetry_outage_rate` | float | 0.0 | 0.0-1.0 | Probability of dropping metric emissions |
| `random_seed` | int? | null | - | Seed for deterministic behavior (testing) |

---

## 🏗️ Integration Points

### 1. WAL Fsync Failure

**Module**: `k0/storage/wal.py`
**Function**: `_fsync_path()`

**Behavior**:
- Raises `OSError(errno.EIO)` to simulate disk I/O failure
- **NOT simulation code**: Real error propagation
- Triggers UoW rollback and DLQ routing

**Telemetry**:
```python
k0_chaos_fsync_injected_total{} 5
```

**Example**:
```python
from k0.storage.wal import WriteAheadLog

wal = WriteAheadLog(db_path)
try:
    wal.fsync()  # May raise OSError if chaos enabled
except OSError as e:
    if e.errno == errno.EIO:
        # Handle chaos-injected failure
        ...
```

---

### 2. Scheduler Starvation

**Module**: `k0/qos/scheduler.py`
**Function**: `Scheduler.__init__()`

**Behavior**:
- Multiplies all port limits by `scheduler_starvation_multiplier`
- **NOT simulation code**: Actually reduces capacity
- Causes `SchedulerCapacityError` under load

**Telemetry**:
```python
k0_chaos_scheduler_throttled_multiplier{} 0.3
```

**Example**:
```python
from k0.qos.scheduler import Scheduler, SchedulerProfile

profile = SchedulerProfile(port_limits={"command": 100, "query": 50})
scheduler = Scheduler(profile, chaos_config=settings.chaos, metrics_exporter=metrics)
# If chaos enabled with multiplier=0.3, limits become: command=30, query=15
```

---

### 3. Network Latency

**Module**: `k0/chaos/network.py`
**Class**: `ChaosTransport(httpx.BaseTransport)`

**Behavior**:
- Wraps httpx transport with intentional delay
- Uses `time.sleep()` for real latency injection
- **Acceptable chaos pattern**: Not simulation code

**Telemetry**:
```python
k0_chaos_network_delay_seconds_bucket{le="0.1"} 45
k0_chaos_network_delay_seconds_sum{} 5.2
```

**Example**:
```python
import httpx
from k0.chaos.network import ChaosTransport

base_transport = httpx.HTTPTransport()
if settings.chaos.enabled:
    transport = ChaosTransport(base_transport, settings.chaos, metrics)
else:
    transport = base_transport

client = httpx.Client(transport=transport)
# Requests will have injected latency if chaos enabled
```

---

### 4. Telemetry Outage

**Module**: `k0/obs/metrics.py`
**Function**: `MetricsExporter.counter()`

**Behavior**:
- Probabilistically skips `metric.inc()` calls
- **NOT simulation code**: Conditionally omits real metric emission
- Creates partial observability for alert testing

**Telemetry**:
```python
k0_chaos_telemetry_dropped_total{} 12
```

**Example**:
```python
# Chaos wrapper applied internally by MetricsExporter
# Callers don't need special handling
metrics.counter("k0_commands_submitted_total").inc()
# May be dropped if chaos enabled with telemetry_outage_rate > 0
```

---

## 🧪 Testing with Chaos

### Run Chaos Test Suite

```bash
# All chaos tests
python -m ward test --path tests/chaos/

# Specific subsystem
python -m ward test --path tests/chaos/test_wal_fsync_failure.py

# With coverage
python -m ward test --path tests/chaos/ --cov=k0.chaos --cov-report=html
```

### Deterministic Testing

Use `random_seed` for reproducible chaos behavior:

```yaml
chaos:
  enabled: true
  wal_fsync_fail_rate: 0.1
  random_seed: 42  # Same seed = same failures
```

**Ward Fixture**:
```python
from ward import fixture
from k0.kernel.config import ChaosSettings

@fixture
def chaos_config() -> ChaosSettings:
    return ChaosSettings(
        enabled=True,
        wal_fsync_fail_rate=0.1,
        random_seed=42,  # Deterministic for tests
    )
```

---

## 🚨 Safety Guardrails

### Production Safeguards

1. **Default Disabled**: `chaos.enabled=false` by default
2. **Explicit Enablement**: Requires configuration change + deployment
3. **Signed Config**: Cannot be enabled via unsigned environment variables alone
4. **Telemetry First**: All chaos events emit metrics for visibility
5. **Graceful Degradation**: System must survive and recover

### Recommended Limits

**Staging/Testing**:
- `wal_fsync_fail_rate`: 0.05-0.15 (5-15%)
- `scheduler_starvation_multiplier`: 0.3-0.7 (30-70% capacity)
- `network_latency_ms`: 50-200ms
- `telemetry_outage_rate`: 0.05-0.2 (5-20%)

**Production Drills** (pre-approved):
- `wal_fsync_fail_rate`: 0.01-0.05 (1-5%)
- `scheduler_starvation_multiplier`: 0.7-0.9 (70-90% capacity)
- `network_latency_ms`: 10-50ms
- `telemetry_outage_rate`: 0.01-0.05 (1-5%)

---

## 📈 Observability

### Chaos Metrics

| Metric | Type | Labels | Description |
|--------|------|--------|-------------|
| `k0_chaos_fsync_injected_total` | Counter | - | Total WAL fsync failures injected |
| `k0_chaos_scheduler_throttled_multiplier` | Gauge | - | Current capacity multiplier (1.0=normal) |
| `k0_chaos_network_delay_seconds` | Histogram | - | Injected network latency distribution |
| `k0_chaos_telemetry_dropped_total` | Counter | - | Total telemetry emissions dropped |

### Grafana Dashboards

See `docs/development/runbooks/chaos-drills.md` for:
- Chaos impact panels
- Alert correlation
- Recovery tracking

---

## 🔧 Troubleshooting

### Chaos Not Activating

**Check Configuration**:
```bash
# Verify chaos settings loaded
curl http://localhost:8080/health | jq '.config.chaos'
```

**Check Environment**:
```bash
# Verify environment variables
env | grep K0_KERNEL_CHAOS
```

**Check Logs**:
```bash
# Look for chaos toggle decisions
grep "chaos_decision" k0_kernel.log
```

### Unexpected Failures

**Disable Chaos Immediately**:
```yaml
chaos:
  enabled: false
```

**Redeploy**:
```bash
./k0/deployment/scripts/deploy.sh --stack local-single-node --action apply
```

**Verify Recovery**:
```bash
# Check telemetry shows chaos disabled
curl http://localhost:8080/metrics | grep k0_chaos
```

### Performance Degradation

**Check Chaos Metrics**:
```promql
# High fsync failure rate?
rate(k0_chaos_fsync_injected_total[5m])

# Scheduler starvation active?
k0_chaos_scheduler_throttled_multiplier < 1.0

# Excessive network latency?
histogram_quantile(0.99, rate(k0_chaos_network_delay_seconds_bucket[5m]))
```

---

## 📚 References

- **Runbook**: `docs/development/runbooks/chaos-drills.md`
- **Test Suite**: `tests/chaos/`
- **Configuration**: `k0/kernel/config.py` (`ChaosSettings`)
- **Copilot Rules**: `.github/copilot-instructions.md` (zero simulation policy)
- **ADR-003**: Deployment toolchain integration
- **Issue 9.1.4**: `docs/development/issue-9.1.4-chaos-framework-plan.md`

---

## 🚨 Critical Constraints

**ZERO SIMULATION CODE**:
- ✅ WAL fsync: Raises `OSError(errno.EIO)` (real error)
- ✅ Scheduler: Reduces port limits (real capacity)
- ✅ Network: Injects `time.sleep()` delay (acceptable for chaos)
- ✅ Telemetry: Skips `metric.inc()` (real omission)
- ❌ NO `asyncio.sleep()` in production paths
- ❌ NO fake/mock/placeholder behavior

**This is production chaos engineering, not a simulation playground.**
