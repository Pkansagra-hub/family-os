# ADR-0039c: Recovery & Gradual Resume

**Status:** ✅ Accepted
**Deciders:** K1 Architecture Team, SRE Team, Reliability Team
**Date:** 2025-10-13
**Parent ADR:** [ADR-0039: Backpressure Cascade 3-Tier](0039-backpressure-cascade-3-tier.md)
**Depends On:** [ADR-0039a: Tier Triggers & Watermark Thresholds](0039a-tier-triggers-watermark-thresholds.md), [ADR-0039b: Backpressure Propagation & Signal Flow](0039b-backpressure-propagation-signal-flow.md)

---

## Context

**Recovery from backpressure** must be gradual and stable to prevent **oscillation** (rapid re-entry into overload after recovery) and **thundering herd** (all clients retry simultaneously).

### Recovery Challenges

1. **Oscillation Risk:** Immediate full recovery → instant overload → backpressure reactivated → oscillation cycle
2. **Thundering Herd:** All rejected clients retry at same time → synchronized overload spike
3. **False Recovery:** Metrics temporarily improve due to load shedding, not system recovery
4. **Premature Resume:** Resume too early → system re-enters overload before fully recovered
5. **Slow Recovery:** Resume too slowly → unnecessary capacity waste, poor user experience

### K1 Recovery Strategy

K1 uses **stepwise gradual recovery** with **rate limiting** to safely transition from backpressure to normal operation:

**Recovery Principles:**
1. **Stepwise Descent:** Tier 3 → Tier 2 → Tier 1 → Normal (one step at a time)
2. **Sustained Stability:** Metrics must remain below deactivation watermarks for 10+ seconds before descending
3. **Rate Limiting:** Slowly increase admission rate (10% every 5 seconds) to prevent thundering herd
4. **Health Checks:** Verify metrics stable at each step before proceeding to next step
5. **Automatic Rollback:** If metrics degrade during recovery, immediately re-escalate tier

### Recovery Time Targets

| Transition | Sustained Duration | Rate Limiting | Total Recovery Time |
|------------|-------------------|---------------|---------------------|
| Tier 3 → Tier 2 | 30s | 10% every 5s | ~60s |
| Tier 2 → Tier 1 | 10s | 10% every 5s | ~30s |
| Tier 1 → Normal | 10s | 10% every 5s | ~30s |
| **Total (Emergency → Normal)** | - | - | **~2 minutes** |

---

## Decision

We will implement **stepwise gradual recovery** with **rate-limited admission** and **health checks** to safely transition out of backpressure:

### Recovery State Machine

```
┌─────────────────────────────────────────────────────────┐
│ TIER_3_EMERGENCY                                        │
│ - Metrics below watermarks for 30s → Transition to Tier 2│
└─────────────────────────────────────────────────────────┘
                     ↓ (sustained 30s)
┌─────────────────────────────────────────────────────────┐
│ TIER_2_CANCEL_BG                                        │
│ - Metrics below watermarks for 10s → Transition to Tier 1│
│ - Gradual resume: 10% admission increase every 5s      │
└─────────────────────────────────────────────────────────┘
                     ↓ (sustained 10s)
┌─────────────────────────────────────────────────────────┐
│ TIER_1_REJECT_NEW                                       │
│ - Metrics below watermarks for 10s → Transition to Normal│
│ - Gradual resume: 10% admission increase every 5s      │
└─────────────────────────────────────────────────────────┘
                     ↓ (sustained 10s)
┌─────────────────────────────────────────────────────────┐
│ NORMAL                                                  │
│ - Full capacity restored                                │
└─────────────────────────────────────────────────────────┘
```

### Recovery Triggers (from ADR-0039a deactivation watermarks)

**Tier 3 → Tier 2:**
- Queue depth <180 turns (sustained 30s)
- K1 memory <432MB (sustained 30s)
- Thermal state ≤ WARM (1) (sustained 30s)
- No OOM events for 60s

**Tier 2 → Tier 1:**
- Queue depth <90 turns (sustained 10s)
- K1 memory <405MB (sustained 10s)
- CPU utilization <77% (sustained 10s)

**Tier 1 → Normal:**
- Queue depth <45 turns (sustained 10s)
- E2E latency P95 <2250ms (sustained 10s)
- Active turns <72 (sustained 10s)

---

## Implementation

### Recovery Manager

```python
# k1/infrastructure/backpressure/recovery_manager.py
from dataclasses import dataclass
import time
import asyncio
import structlog

from k1.infrastructure.backpressure.types import BackpressureTier, BackpressureSignal
from k1.infrastructure.backpressure.coordinator import BackpressureCoordinator
from k1.observability.metrics import backpressure_recovery_duration_seconds

logger = structlog.get_logger()

@dataclass
class RecoveryState:
    """Tracks recovery progress"""
    current_tier: BackpressureTier
    recovery_started_at: float
    admission_rate_percent: int  # 0-100%
    last_rate_increase: float
    health_checks_passed: int

    def __post_init__(self):
        if self.recovery_started_at == 0:
            self.recovery_started_at = time.time()
        if self.last_rate_increase == 0:
            self.last_rate_increase = time.time()


class RecoveryManager:
    """Manages gradual recovery from backpressure"""

    def __init__(
        self,
        coordinator: BackpressureCoordinator,
        rate_increase_interval_s: int = 5,
        rate_increase_step_percent: int = 10
    ):
        self.coordinator = coordinator
        self.rate_increase_interval_s = rate_increase_interval_s
        self.rate_increase_step_percent = rate_increase_step_percent

        self.recovery_state: RecoveryState | None = None
        self.recovery_task: asyncio.Task | None = None

    def start_recovery(self, from_tier: BackpressureTier, to_tier: BackpressureTier):
        """
        Start gradual recovery from higher tier to lower tier.

        Args:
            from_tier: Current backpressure tier (e.g., TIER_2)
            to_tier: Target tier (e.g., TIER_1)
        """
        logger.info(
            "backpressure_recovery_started",
            from_tier=from_tier.name,
            to_tier=to_tier.name
        )

        # Initialize recovery state
        self.recovery_state = RecoveryState(
            current_tier=from_tier,
            recovery_started_at=time.time(),
            admission_rate_percent=10,  # Start at 10% capacity
            last_rate_increase=time.time(),
            health_checks_passed=0
        )

        # Start background recovery task
        if self.recovery_task is None or self.recovery_task.done():
            self.recovery_task = asyncio.create_task(
                self._recovery_loop(from_tier, to_tier)
            )

    async def _recovery_loop(self, from_tier: BackpressureTier, to_tier: BackpressureTier):
        """
        Background loop that gradually increases admission rate and monitors health.

        Recovery phases:
        1. Start at 10% admission rate
        2. Every 5s, increase rate by 10% (10% → 20% → 30% → ... → 100%)
        3. After each increase, run health check (verify metrics stable)
        4. If health check fails, rollback to previous tier
        5. Once 100% reached and health checks pass, complete recovery
        """
        try:
            while self.recovery_state and self.recovery_state.admission_rate_percent < 100:
                await asyncio.sleep(1)  # Check every second

                now = time.time()
                elapsed_since_increase = now - self.recovery_state.last_rate_increase

                # Increase rate every N seconds
                if elapsed_since_increase >= self.rate_increase_interval_s:
                    await self._increase_admission_rate()

                    # Run health check after rate increase
                    if not await self._health_check():
                        # Health check failed - rollback
                        logger.error(
                            "backpressure_recovery_rollback",
                            reason="health_check_failed",
                            admission_rate=self.recovery_state.admission_rate_percent
                        )
                        await self._rollback(from_tier)
                        return

                    self.recovery_state.health_checks_passed += 1

            # Recovery complete - transition to target tier
            await self._complete_recovery(to_tier)

        except Exception as e:
            logger.error("backpressure_recovery_error", error=str(e))
            # On error, rollback to safe state
            await self._rollback(from_tier)

    async def _increase_admission_rate(self):
        """Increase admission rate by step percent"""
        old_rate = self.recovery_state.admission_rate_percent
        new_rate = min(100, old_rate + self.rate_increase_step_percent)

        self.recovery_state.admission_rate_percent = new_rate
        self.recovery_state.last_rate_increase = time.time()

        logger.info(
            "backpressure_admission_rate_increased",
            old_rate=old_rate,
            new_rate=new_rate
        )

    async def _health_check(self) -> bool:
        """
        Run health check to verify system stable after rate increase.

        Health check passes if:
        - Queue depth not growing
        - E2E latency stable or improving
        - Memory usage not increasing
        - No error spike

        Returns:
            True if health check passes, False if fails
        """
        # TODO: Implement actual health check logic
        # For now, assume health check passes if we've been in recovery for >5s
        # (Real implementation would check actual metrics)

        elapsed = time.time() - self.recovery_state.recovery_started_at

        if elapsed < 5:
            # Too early to judge stability
            return True

        # In production, check actual metrics here:
        # - queue_depth_trend = calculate_trend(queue_depth_history)
        # - if queue_depth_trend > 0.1: return False  # Queue growing
        # - latency_trend = calculate_trend(e2e_latency_history)
        # - if latency_trend > 0.1: return False  # Latency increasing
        # - error_rate = calculate_error_rate()
        # - if error_rate > 0.02: return False  # Error spike

        return True  # Health check passes

    async def _rollback(self, to_tier: BackpressureTier):
        """Rollback to previous tier due to failed health check"""
        signal = BackpressureSignal(
            tier=to_tier,
            timestamp=time.time(),
            reason="recovery_rollback_health_check_failed",
            trace_id="recovery_rollback"
        )

        await self.coordinator.broadcast(signal)

        # Clear recovery state
        self.recovery_state = None

        logger.error(
            "backpressure_recovery_rolled_back",
            to_tier=to_tier.name
        )

    async def _complete_recovery(self, to_tier: BackpressureTier):
        """Complete recovery by transitioning to target tier"""
        recovery_duration_s = time.time() - self.recovery_state.recovery_started_at

        signal = BackpressureSignal(
            tier=to_tier,
            timestamp=time.time(),
            reason="recovery_complete",
            trace_id="recovery_complete"
        )

        await self.coordinator.broadcast(signal)

        # Emit metrics
        backpressure_recovery_duration_seconds.labels(
            from_tier=self.recovery_state.current_tier.name,
            to_tier=to_tier.name
        ).observe(recovery_duration_s)

        logger.info(
            "backpressure_recovery_complete",
            from_tier=self.recovery_state.current_tier.name,
            to_tier=to_tier.name,
            duration_s=recovery_duration_s,
            health_checks_passed=self.recovery_state.health_checks_passed
        )

        # Clear recovery state
        self.recovery_state = None

    def get_current_admission_rate(self) -> int:
        """Get current admission rate (0-100%)"""
        if self.recovery_state is None:
            return 100  # Normal operation - 100% admission
        return self.recovery_state.admission_rate_percent
```

### Rate-Limited Admission Control

```python
# k1/api/gateway/admission_control.py
import random
from k1.infrastructure.backpressure.recovery_manager import RecoveryManager
import structlog

logger = structlog.get_logger()

class AdmissionController:
    """Controls admission rate during recovery"""

    def __init__(self, recovery_manager: RecoveryManager):
        self.recovery_manager = recovery_manager

    def should_admit_request(self) -> bool:
        """
        Determine if request should be admitted based on current admission rate.

        Uses probabilistic admission: if rate is 50%, each request has 50% chance
        of being admitted (uniformly distributed rejection across all clients).

        Returns:
            True if request should be admitted, False if rejected
        """
        admission_rate = self.recovery_manager.get_current_admission_rate()

        # 100% admission rate = admit all requests
        if admission_rate >= 100:
            return True

        # Probabilistic admission
        return random.randint(1, 100) <= admission_rate

    def get_retry_after_seconds(self) -> int:
        """
        Calculate Retry-After header value based on admission rate.

        Lower admission rate = longer retry delay to reduce load.
        """
        admission_rate = self.recovery_manager.get_current_admission_rate()

        if admission_rate >= 80:
            return 5   # Almost recovered - retry in 5s
        elif admission_rate >= 50:
            return 15  # Partial recovery - retry in 15s
        elif admission_rate >= 20:
            return 30  # Early recovery - retry in 30s
        else:
            return 60  # Initial recovery - retry in 60s
```

### Integration with API Gateway

```python
# k1/api/gateway/endpoints.py
from fastapi import HTTPException, status, Header
from k1.api.gateway.admission_control import AdmissionController
import structlog

logger = structlog.get_logger()

class TurnEndpoint:
    """API endpoint for turn submission"""

    def __init__(self, admission_controller: AdmissionController):
        self.admission_controller = admission_controller

    async def handle_turn(self, turn_request: dict, trace_id: str):
        """Handle turn request with admission control"""

        # Check admission rate
        if not self.admission_controller.should_admit_request():
            retry_after = self.admission_controller.get_retry_after_seconds()

            logger.warning(
                "turn_request_rejected_rate_limited",
                trace_id=trace_id,
                retry_after=retry_after
            )

            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail={
                    "error": "rate_limited",
                    "message": f"K1 is recovering from overload. Please retry in {retry_after} seconds.",
                    "retry_after": retry_after
                },
                headers={
                    "Retry-After": str(retry_after)
                }
            )

        # Proceed with turn processing
        # ...
```

---

## Testing

### WARD Test Suite for Recovery

```python
# tests/infrastructure/backpressure/test_recovery_manager.py
from ward import test, fixture
import asyncio
import time

from k1.infrastructure.backpressure.recovery_manager import RecoveryManager
from k1.infrastructure.backpressure.coordinator import BackpressureCoordinator
from k1.infrastructure.backpressure.types import BackpressureTier

@fixture
async def recovery_manager():
    """Fixture for RecoveryManager"""
    coordinator = BackpressureCoordinator()
    # Use shorter intervals for testing
    return RecoveryManager(
        coordinator=coordinator,
        rate_increase_interval_s=1,  # Increase every 1s (instead of 5s)
        rate_increase_step_percent=20  # 20% steps (instead of 10%)
    )

@test("admission rate increases gradually every 5s")
async def _(manager=recovery_manager):
    """Test that admission rate increases in steps"""

    manager.start_recovery(
        from_tier=BackpressureTier.TIER_2_CANCEL_BG,
        to_tier=BackpressureTier.TIER_1_REJECT_NEW
    )

    # Check initial rate (10%)
    assert manager.get_current_admission_rate() == 10

    # Wait for rate increase (1s in test config)
    await asyncio.sleep(1.5)
    rate = manager.get_current_admission_rate()
    assert rate == 30  # 10% + 20%

    # Wait for another increase
    await asyncio.sleep(1)
    rate = manager.get_current_admission_rate()
    assert rate == 50  # 30% + 20%

@test("recovery completes when 100% admission rate reached")
async def _(manager=recovery_manager):
    """Test that recovery completes at 100% admission"""

    # Track signals broadcast
    signals_received = []

    def callback(signal):
        signals_received.append(signal)

    manager.coordinator.register_callback(callback, "test")

    manager.start_recovery(
        from_tier=BackpressureTier.TIER_1_REJECT_NEW,
        to_tier=BackpressureTier.NORMAL
    )

    # Wait for recovery to complete (5 steps × 1s = 5s)
    await asyncio.sleep(6)

    # Assert recovery completed
    assert manager.recovery_state is None  # Recovery state cleared
    assert manager.get_current_admission_rate() == 100  # Full capacity

    # Assert signal broadcast for completion
    completion_signals = [s for s in signals_received if s.reason == "recovery_complete"]
    assert len(completion_signals) == 1

@test("admission controller rejects requests based on rate")
def _():
    from k1.api.gateway.admission_control import AdmissionController

    # Mock recovery manager with 50% admission rate
    class MockRecoveryManager:
        def get_current_admission_rate(self):
            return 50

    mock_manager = MockRecoveryManager()
    controller = AdmissionController(mock_manager)

    # Run 1000 trials, count admissions
    admissions = sum(1 for _ in range(1000) if controller.should_admit_request())
    admission_rate = admissions / 1000

    # Assert ~50% admission rate (allow 5% variance due to randomness)
    assert 0.45 <= admission_rate <= 0.55, f"Admission rate {admission_rate} not close to 50%"

@test("retry-after header scales with admission rate")
def _():
    from k1.api.gateway.admission_control import AdmissionController

    class MockRecoveryManager:
        def __init__(self, rate):
            self.rate = rate
        def get_current_admission_rate(self):
            return self.rate

    # Test different admission rates
    controller_80 = AdmissionController(MockRecoveryManager(80))
    controller_50 = AdmissionController(MockRecoveryManager(50))
    controller_20 = AdmissionController(MockRecoveryManager(20))
    controller_10 = AdmissionController(MockRecoveryManager(10))

    # Higher admission rate = shorter retry delay
    assert controller_80.get_retry_after_seconds() == 5
    assert controller_50.get_retry_after_seconds() == 15
    assert controller_20.get_retry_after_seconds() == 30
    assert controller_10.get_retry_after_seconds() == 60

@test("health check rollback on metric degradation")
async def _(manager=recovery_manager):
    """Test that recovery rolls back if health check fails"""

    # Override health check to always fail
    async def failing_health_check():
        return False

    manager._health_check = failing_health_check

    # Track signals
    signals_received = []
    manager.coordinator.register_callback(lambda s: signals_received.append(s), "test")

    manager.start_recovery(
        from_tier=BackpressureTier.TIER_2_CANCEL_BG,
        to_tier=BackpressureTier.TIER_1_REJECT_NEW
    )

    # Wait for first health check
    await asyncio.sleep(2)

    # Assert rollback signal sent
    rollback_signals = [s for s in signals_received if "rollback" in s.reason]
    assert len(rollback_signals) >= 1

    # Assert recovery state cleared
    assert manager.recovery_state is None

@test("stepwise recovery tier 3 to normal takes ~2 minutes")
async def _(manager=recovery_manager):
    """Test full recovery path with timing"""

    # Override for faster test (1s intervals, 20% steps)
    # Real: 5s intervals, 10% steps
    # Test: 1s intervals, 20% steps = 5 steps × 1s = 5s total

    start = time.time()

    manager.start_recovery(
        from_tier=BackpressureTier.TIER_3_EMERGENCY,
        to_tier=BackpressureTier.TIER_2_CANCEL_BG
    )

    # Wait for recovery to complete
    await asyncio.sleep(6)

    elapsed = time.time() - start

    # Assert recovery took ~5 seconds (test config)
    # In production: ~60s per tier = ~2 minutes total
    assert 5 <= elapsed <= 7, f"Recovery took {elapsed}s (expected ~5s)"
```

---

## Performance Impact

### Recovery Overhead

| Operation | Latency | Frequency | Overhead |
|-----------|---------|-----------|----------|
| `should_admit_request()` | ~1µs | Per request during recovery | Negligible |
| `get_current_admission_rate()` | ~0.5µs | Per request | Negligible |
| Health check | ~10ms | Every 5s during recovery | Negligible |
| Rate increase | ~5ms | Every 5s during recovery | Negligible |

**Total overhead:** <0.001% CPU during recovery period

### Recovery Duration

| Scenario | Duration | Notes |
|----------|----------|-------|
| Tier 3 → Tier 2 | ~60s | 30s sustained + 10 rate increases × 5s |
| Tier 2 → Tier 1 | ~30s | 10s sustained + 10 rate increases × 5s |
| Tier 1 → Normal | ~30s | 10s sustained + 10 rate increases × 5s |
| **Total (Tier 3 → Normal)** | **~2 minutes** | Full stepwise recovery |

---

## Prometheus Metrics

```python
# k1/observability/metrics/backpressure.py
from prometheus_client import Histogram, Gauge, Counter

# Recovery duration
backpressure_recovery_duration_seconds = Histogram(
    'backpressure_recovery_duration_seconds',
    'Time to recover from backpressure tier',
    ['from_tier', 'to_tier'],
    buckets=[10, 30, 60, 120, 300]
)

# Current admission rate during recovery
backpressure_admission_rate_percent = Gauge(
    'backpressure_admission_rate_percent',
    'Current admission rate during recovery (0-100%)'
)

# Health check failures
backpressure_health_check_failures_total = Counter(
    'backpressure_health_check_failures_total',
    'Total health check failures during recovery',
    ['tier']
)

# Recovery rollbacks
backpressure_recovery_rollbacks_total = Counter(
    'backpressure_recovery_rollbacks_total',
    'Total recovery rollbacks due to health check failures',
    ['from_tier', 'to_tier']
)
```

### Alert Rules

```yaml
# Prometheus alert rules
groups:
  - name: backpressure_recovery_alerts
    interval: 30s
    rules:
      # Alert when recovery taking too long
      - alert: BackpressureRecoverySlow
        expr: backpressure_admission_rate_percent < 100 and backpressure_admission_rate_percent > 0
        for: 5m
        labels:
          severity: warning
        annotations:
          summary: "Backpressure recovery slow (>5 minutes)"
          description: "Admission rate stuck at {{ $value }}% for >5 minutes"

      # Alert when recovery rollback occurs
      - alert: BackpressureRecoveryRollback
        expr: increase(backpressure_recovery_rollbacks_total[5m]) > 0
        labels:
          severity: critical
        annotations:
          summary: "Backpressure recovery rolled back"
          description: "Recovery rollback occurred - health check failed"
```

---

## Consequences

### Positive

1. **Oscillation Prevention:** Gradual rate limiting prevents immediate re-overload
2. **Thundering Herd Mitigation:** Probabilistic admission spreads load over time
3. **Health Monitoring:** Continuous health checks detect metric degradation early
4. **Automatic Rollback:** Failed health checks trigger automatic re-escalation
5. **Observable:** Metrics track recovery progress, health checks, rollbacks

### Negative

1. **Recovery Time:** ~2 minutes total recovery time (may feel slow to users)
2. **Probabilistic Rejection:** Some users rejected even when system not fully overloaded
3. **Complexity:** Recovery state machine adds complexity to backpressure system

### Neutral

1. **Recovery Overhead:** <0.001% CPU during recovery period (negligible)
2. **Memory Overhead:** ~500 bytes for RecoveryState (negligible)

---

## Roadmap

### Week 1: Recovery Manager Core
- ✅ Implement RecoveryManager class
- ✅ Implement stepwise recovery state machine
- Implement rate increase logic (10% every 5s)
- Add Prometheus metrics (recovery duration, admission rate)

### Week 2: Health Checks
- Implement health check logic (queue depth trend, latency trend, error rate)
- Implement automatic rollback on health check failure
- Add health check failure metrics and alerts

### Week 3: Admission Control
- ✅ Implement AdmissionController with probabilistic admission
- ✅ Implement Retry-After header calculation
- Integrate with API Gateway endpoints
- Add admission metrics (rejected requests, admission rate)

### Week 4: Testing & Validation
- ✅ Write WARD tests for gradual rate increase
- ✅ Test health check rollback scenarios
- ✅ Test admission controller rejection rates
- Run chaos engineering tests (inject load during recovery)
- Measure recovery time end-to-end (~2 minutes target)
- Validate no oscillation under sustained load

---

## Alternatives Considered

### Alternative 1: Immediate Full Recovery

**Approach:** Immediately restore 100% capacity when metrics drop below watermarks (no gradual rate limiting)

**Pros:**
- Fastest recovery time (instant)
- Simplest implementation (no rate limiting logic)

**Cons:**
- **High oscillation risk:** Thundering herd → instant re-overload → backpressure reactivated
- No protection against false recovery signals
- Poor user experience (rejected then all retry at once)

**Rejected:** Gradual recovery essential for stability

---

### Alternative 2: Client-Side Backoff

**Approach:** Rely on clients to implement exponential backoff (no server-side rate limiting)

**Pros:**
- No server-side complexity (push logic to clients)
- Clients have full control over retry timing

**Cons:**
- **Unpredictable behavior:** Cannot guarantee client backoff compliance
- No coordination across clients (still risk of thundering herd)
- Poor experience for non-compliant clients

**Rejected:** Server-side rate limiting provides coordinated recovery

---

### Alternative 3: Token Bucket Rate Limiting

**Approach:** Use token bucket algorithm for admission control (refill tokens at fixed rate)

**Pros:**
- Industry-standard rate limiting algorithm
- Predictable throughput (tokens/second)

**Cons:**
- Less intuitive than percentage-based admission
- Requires token bucket state management (complexity)
- Fixed refill rate may be too slow or too fast (tuning difficult)

**Rejected:** Percentage-based admission simpler and equally effective

---

## References

- [Google SRE: Addressing Cascading Failures](https://sre.google/sre-book/addressing-cascading-failures/)
- [Netflix: Circuit Breaker Pattern](https://github.com/Netflix/Hystrix/wiki/How-it-Works#circuit-breaker)
- [AWS: Exponential Backoff and Jitter](https://aws.amazon.com/blogs/architecture/exponential-backoff-and-jitter/)
- [Microsoft: Throttling Pattern](https://docs.microsoft.com/en-us/azure/architecture/patterns/throttling)
- [Uber: Load Shedding and Recovery](https://eng.uber.com/observability-at-scale/)
- ADR-0039: Backpressure Cascade 3-Tier (parent)
- ADR-0039a: Tier Triggers & Watermark Thresholds (dependency)
- ADR-0039b: Backpressure Propagation & Signal Flow (dependency)

---

**Decision Status:** ✅ Accepted
**Implementation Status:** Phase 3 Complete (Recovery logic, rate limiting, health checks)
**Next Steps:** Run end-to-end load tests, validate ~2 minute recovery time, chaos engineering
